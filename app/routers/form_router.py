from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Depends
from fastapi.responses import FileResponse, JSONResponse
from app.models.form import FormCreate, FormFill
from app.utils.form_utils import (
    load_forms, save_forms, fill_template, 
    load_generated_files, get_generated_files,
    validate_sections_against_document, validate_form_fields,
    extract_placeholders_from_document
)
from app.utils.auth_utils import (
    authenticate_user, create_access_token, get_password_hash, 
    load_users, save_users, user_exists
)
from app.exceptions import (
    FormNotFound, FormCreationError, TemplateFillingError, 
    InvalidFieldsError, FileOperationError, StorageError
)
import json
import os
import uuid
import shutil
import logging
import tempfile
from datetime import datetime, timedelta

router = APIRouter()

# Configure logging
logger = logging.getLogger(__name__)

# Directory to store templates
TEMPLATES_DIR = "templates"
os.makedirs(TEMPLATES_DIR, exist_ok=True)

# File upload size limit (50MB)
MAX_FILE_SIZE = 50 * 1024 * 1024



# Login endpoint (expects JSON body)
from fastapi import Body
from pydantic import BaseModel

class LoginRequest(BaseModel):
    username: str
    password: str

@router.post("/user/login")
async def login(payload: LoginRequest):
    """
    Login endpoint that returns a JWT token.
    Expects JSON body: {"username": ..., "password": ...}
    """
    username = payload.username
    password = payload.password
    logger.info(f"Login attempt for user: {username}")
    user = authenticate_user(username, password)
    if not user:
        logger.warning(f"Failed login attempt for user: {username}")
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )
    # Create access token with 30 minute expiration
    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": user["username"], "user_id": user["id"]},
        expires_delta=access_token_expires
    )
    logger.info(f"Successful login for user: {username}")
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "full_name": user["full_name"]
        }
    }


@router.post("/user/register")
async def register(
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...)
):
    """
    Register a new user.
    
    Args:
        username: User's username (must be unique)
        email: User's email (must be unique)
        password: User's password
        full_name: User's full name
    
    Returns:
        User object with success message
    """
    logger.info(f"Registration attempt for user: {username}, email: {email}")
    
    # Validate input
    if not username or not email or not password or not full_name:
        logger.warning(f"Registration failed: Missing required fields")
        raise HTTPException(
            status_code=400,
            detail="All fields (username, email, password, full_name) are required"
        )
    
    # Validate username format (alphanumeric and underscore only)
    if not username.replace("_", "").isalnum():
        logger.warning(f"Registration failed: Invalid username format: {username}")
        raise HTTPException(
            status_code=400,
            detail="Username must contain only alphanumeric characters and underscores"
        )
    
    # Validate email format (basic check)
    if "@" not in email or "." not in email:
        logger.warning(f"Registration failed: Invalid email format: {email}")
        raise HTTPException(
            status_code=400,
            detail="Invalid email format"
        )
    
    # Validate password length
    if len(password) < 6:
        logger.warning(f"Registration failed: Password too short for user: {username}")
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 6 characters long"
        )
    
    # Check if user already exists
    if user_exists(username, email):
        logger.warning(f"Registration failed: User already exists - username: {username}, email: {email}")
        raise HTTPException(
            status_code=409,
            detail="Username or email already exists"
        )
    
    try:
        # Load current users
        users = load_users()
        
        # Create new user
        new_user = {
            "id": str(uuid.uuid4()),
            "username": username,
            "email": email,
            "password": get_password_hash(password),
            "full_name": full_name,
            "disabled": False
        }
        
        # Add to users list
        users.append(new_user)
        
        # Save users
        save_users(users)
        
        logger.info(f"User registered successfully: {username}")
        
        return {
            "message": "User registered successfully",
            "user": {
                "id": new_user["id"],
                "username": new_user["username"],
                "email": new_user["email"],
                "full_name": new_user["full_name"]
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during registration: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="An error occurred during registration"
        )


# Validate uploaded file
def validate_file_upload(file: UploadFile) -> None:
    """Validate uploaded file."""
    if not file.filename:
        raise InvalidFieldsError("No filename provided")
    if not file.filename.endswith('.docx'):
        raise InvalidFieldsError("Only .docx files are supported")

@router.post("/forms")
async def create_form(fields: str = Form(...), file: UploadFile = File(...)):
    """Create a new form with template."""
    temp_file_path = None
    try:
        logger.info("Creating new form")
        
        # Validate and parse fields
        try:
            fields_dict = json.loads(fields)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON for fields: {str(e)}")
            raise HTTPException(status_code=400, detail="Invalid JSON format for fields")
        
        if not isinstance(fields_dict, dict):
            logger.error("Fields must be a dictionary")
            raise HTTPException(status_code=400, detail="Fields must be a JSON object")
        
        if not fields_dict:
            logger.error("Fields dictionary is empty")
            raise HTTPException(status_code=400, detail="Fields cannot be empty")
        
        # Validate file upload
        validate_file_upload(file)
        
        # Read file content
        file_content = await file.read()
        if len(file_content) > MAX_FILE_SIZE:
            logger.error(f"File size exceeds limit: {len(file_content)}")
            raise HTTPException(status_code=413, detail=f"File size exceeds {MAX_FILE_SIZE / (1024*1024):.0f}MB limit")
        
        if len(file_content) == 0:
            logger.error("Uploaded file is empty")
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        
        # Save to temporary location for validation
        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as temp_file:
            temp_file_path = temp_file.name
            temp_file.write(file_content)
        
        logger.info(f"Temporary file created for validation: {temp_file_path}")
        
        # Validate form fields against document placeholders (check only sections)
        try:
            validation_result = validate_sections_against_document(temp_file_path, json.loads(fields_dict['sections']))
            
            if not validation_result["valid"]:
                logger.warning(f"Form validation failed: {validation_result}")
                
                # Clean up temp file
                try:
                    os.remove(temp_file_path)
                except:
                    pass
                
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "Form validation failed",
                        "unknown_keys": validation_result["unknown_keys"]
                    }
                )
            
            logger.info(f"Form validation passed: {len(validation_result['matched_keys'])} matched keys")
        
        except FileOperationError as e:
            logger.error(f"Error validating form: {str(e)}")
            # Clean up temp file
            try:
                os.remove(temp_file_path)
            except:
                pass
            raise HTTPException(status_code=500, detail=f"Failed to validate form: {str(e)}")
        
        # Generate form ID and template ID, save template
        form_id = str(uuid.uuid4())
        template_id = str(uuid.uuid4())
        template_filename = f"{template_id}.docx"
        template_path = os.path.join(TEMPLATES_DIR, template_filename)
        
        try:
            with open(template_path, "wb") as buffer:
                buffer.write(file_content)
            logger.info(f"Template saved to {template_path}")
        except IOError as e:
            logger.error(f"Failed to save template file: {str(e)}")
            # Clean up temp file
            try:
                os.remove(temp_file_path)
            except:
                pass
            raise HTTPException(status_code=500, detail="Failed to save template file")
        
        form = {
            "id": form_id,
            "template_id": template_id,
            "fields": fields_dict,
            "template_path": template_path,
            "validation": {
                "total_field_keys": validation_result["total_field_keys"],
                "matched_keys": validation_result["matched_keys"]
            }
        }
        
        # Save form to storage
        try:
            forms = load_forms()
            forms.append(form)
            save_forms(forms)
            logger.info(f"Form created successfully with ID: {form_id}")
            
            # Clean up temp file
            try:
                os.remove(temp_file_path)
            except:
                pass
            
            return {
                "message": "Form created successfully",
                "form_id": form_id,
                "validation": validation_result
            }
        except StorageError as e:
            logger.error(f"Storage error while creating form: {str(e)}")
            # Try to cleanup files
            try:
                os.remove(template_path)
                os.remove(temp_file_path)
            except:
                pass
            raise HTTPException(status_code=500, detail="Failed to save form metadata")
        
    except HTTPException:
        raise
    finally:
        # Clean up temporary file if it still exists
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception as e:
                logger.warning(f"Failed to clean up temporary file {temp_file_path}: {str(e)}")
    
@router.get("/forms")
async def list_forms():
    """List all forms."""
    try:
        logger.info("Listing all forms")
        forms = load_forms()
        logger.info(f"Retrieved {len(forms)} forms")
        return {"data": forms}
    except StorageError as e:
        logger.error(f"Storage error while listing forms: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve forms")
    except Exception as e:
        logger.error(f"Unexpected error listing forms: {str(e)}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred while listing forms")

@router.delete("/forms/{form_id}")
async def delete_form(form_id: str):
    """Delete a form and all associated files."""
    try:
        logger.info(f"Deleting form: {form_id}")
        
        # Load forms
        try:
            forms = load_forms()
        except StorageError as e:
            logger.error(f"Storage error while loading forms: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to retrieve forms")
        
        # Find the form
        form = next((f for f in forms if f["id"] == form_id), None)
        if not form:
            logger.warning(f"Form not found: {form_id}")
            raise HTTPException(status_code=404, detail=f"Form with ID '{form_id}' not found")
        
        # Remove template file
        template_path = form.get("template_path")
        if template_path and os.path.exists(template_path):
            try:
                os.remove(template_path)
                logger.info(f"Template file deleted: {template_path}")
            except Exception as e:
                logger.error(f"Failed to delete template file {template_path}: {str(e)}")
        
        # Remove form from storage
        try:
            forms = [f for f in forms if f["id"] != form_id]
            save_forms(forms)
            logger.info(f"Form {form_id} successfully deleted from storage")
            
            return {
                "message": "Form deleted successfully",
                "form_id": form_id
            }
        except StorageError as e:
            logger.error(f"Storage error while deleting form: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to delete form metadata")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting form {form_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred while deleting the form")

@router.post("/forms/{form_id}/fill")
async def fill_form(form_id: str, values: str = Form(...)):
    """Fill form template with provided values."""
    try:
        logger.info(f"Filling form: {form_id}")
        
        # Validate and parse values
        try:
            values_dict = json.loads(values)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON for values: {str(e)}")
            raise HTTPException(status_code=400, detail="Invalid JSON format for values")
        
        if not isinstance(values_dict, dict):
            logger.error("Values must be a dictionary")
            raise HTTPException(status_code=400, detail="Values must be a JSON object")
        
        # Load and find form
        try:
            forms = load_forms()
        except StorageError as e:
            logger.error(f"Storage error while loading forms: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to retrieve forms")
        
        form = next((f for f in forms if f["id"] == form_id), None)
        if not form:
            logger.warning(f"Form not found: {form_id}")
            raise HTTPException(status_code=404, detail=f"Form with ID '{form_id}' not found")
        
        # Fill template
        try:
            filled_path, file_id = fill_template(
                form["template_path"], 
                values_dict, 
                form_id=form_id,
                form_name=form_id  # Use form_id as the name for filename
            )
            logger.info(f"Form filled successfully: {form_id}, File ID: {file_id}")
            return FileResponse(
                filled_path, 
                media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                filename=os.path.basename(filled_path),
                headers={"X-File-ID": file_id}  # Return file ID in response header
            )
        except TemplateFillingError as e:
            logger.error(f"Template filling error for form {form_id}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to fill template: {str(e)}")
        except FileOperationError as e:
            logger.error(f"File operation error for form {form_id}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Template file error: {str(e)}")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error filling form {form_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred while filling the form")

async def list_generated_files(form_id: str):
    """List all generated files for a form."""
    try:
        logger.info(f"Listing generated files for form: {form_id}")
        
        # Verify form exists
        try:
            forms = load_forms()
        except StorageError as e:
            logger.error(f"Storage error while loading forms: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to retrieve forms")
        
        form = next((f for f in forms if f["id"] == form_id), None)
        if not form:
            logger.warning(f"Form not found: {form_id}")
            raise HTTPException(status_code=404, detail=f"Form with ID '{form_id}' not found")
        
        # Get generated files
        generated_files = get_generated_files(form_id)
        logger.info(f"Retrieved {len(generated_files)} generated files for form {form_id}")
        
        return {
            "form_id": form_id,
            "total_generated": len(generated_files),
            "files": generated_files
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error listing generated files for {form_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred while listing generated files")

@router.get("/generated/{file_id}")
async def download_generated_file_by_id(file_id: str):
    """Download a generated file directly by file_id."""
    try:
        logger.info(f"Downloading generated file: {file_id}")
        
        # Load all generated files and search across all forms
        try:
            from app.utils.form_utils import load_generated_files
            all_generated_files = load_generated_files()
        except StorageError as e:
            logger.error(f"Storage error while loading generated files: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to retrieve generated files")
        
        # Find the file across all forms
        file_record = None
        for form_id, files in all_generated_files.items():
            file_record = next((f for f in files if f["file_id"] == file_id), None)
            if file_record:
                break
        
        if not file_record:
            logger.warning(f"Generated file not found: {file_id}")
            raise HTTPException(status_code=404, detail=f"Generated file with ID '{file_id}' not found")
        
        file_path = file_record["file_path"]
        if not os.path.exists(file_path):
            logger.error(f"Generated file path does not exist: {file_path}")
            raise HTTPException(status_code=500, detail="Generated file not found on server")
        
        logger.info(f"Serving generated file: {file_path}")
        return FileResponse(
            file_path, 
            media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            filename=file_record["filename"]
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error downloading generated file {file_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred while downloading the file")

@router.get("/templates/{template_id}")
async def view_template(template_id: str):
    """View form template by template_id."""
    try:
        logger.info(f"Viewing template: {template_id}")
        
        template_filename = f"{template_id}"
        template_path = os.path.join(TEMPLATES_DIR, template_filename)
        
        if not os.path.exists(template_path):
            logger.warning(f"Template file not found: {template_path}")
            raise HTTPException(status_code=404, detail=f"Template with ID '{template_id}' not found")
        
        logger.info(f"Template view initiated: {template_id}")
        return FileResponse(
            template_path, 
            media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error viewing template {template_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred while viewing the template")
