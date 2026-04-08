from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Depends, Query
from fastapi.responses import FileResponse, JSONResponse
from app.models.form import FormCreate, FormFill
from app.utils.form_utils import (
    load_forms, save_forms, fill_template, 
    load_form_submissions, get_form_submissions,
    validate_sections_against_document, validate_form_fields,
    extract_placeholders_from_document,
    add_saved_form_submission,
    load_saved_form_submissions,
    save_saved_form_submissions,
    delete_saved_form_submission
)
from app.utils.auth_utils import (
    authenticate_user, create_access_token, get_password_hash, 
    load_users, save_users, user_exists
)
from app.exceptions import (
    FormNotFound, FormCreationError, TemplateFillingError, 
    InvalidFieldsError, FileOperationError, StorageError
)
from app.constants.font_constants import FontFamily
import json
import os
import uuid
import shutil
import logging
import tempfile
from datetime import datetime, timedelta
from urllib.parse import quote

router = APIRouter()

# Configure logging
logger = logging.getLogger(__name__)

# Directory to store templates
TEMPLATES_DIR = "templates"
os.makedirs(TEMPLATES_DIR, exist_ok=True)

# File upload size limit (50MB)
MAX_FILE_SIZE = 50 * 1024 * 1024


def build_docx_download_headers(filename: str) -> dict:
    quoted_filename = quote(filename)
    return {
        "Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quoted_filename}",
        "X-Content-Type-Options": "nosniff",
    }


@router.get("/fonts/families")
async def get_font_families():
    """Return supported font families for UI dropdowns."""
    logger.info("Fetching supported font families")
    font_families = [font.value for font in FontFamily]
    return {
        "font_families": font_families,
        "total": len(font_families)
    }



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
        
        styles = fields_dict.get("style", {})
        
        form = {
            "id": form_id,
            "template_id": template_id,
            "fields": fields_dict,
            "template_path": template_path,
            "created_at": datetime.now().isoformat(),
            "style": styles,
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

@router.post("/forms/{form_id}/submit")
async def fill_form(
    form_id: str,
    values: str = Form(...),
):
    """Fill form template with provided values and optional font settings."""
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
        
        try:
            filled_path, submission_id = fill_template(
                form["template_path"], 
                values_dict, 
                form_id=form_id,
                form_name=form_id,  # Use form_id as the name for filename
                font_family=form.get("style", {}).get("font_family"),
                font_size=form.get("style", {}).get("font_size")
            )
            logger.info(f"Form filled successfully: {form_id}, Submission ID: {submission_id}")
            return FileResponse(
                filled_path, 
                media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                filename=os.path.basename(filled_path),
                headers={"X-Submission-ID": submission_id}  # Return submission ID in response header
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

@router.get("/forms/{form_id}/form-submissions")
async def list_form_submissions(form_id: str):
    """List all form submissions for a form."""
    try:
        logger.info(f"Listing form submissions for form: {form_id}")
        
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
        
        # Get form submissions
        form_submissions = get_form_submissions(form_id)
        logger.info(f"Retrieved {len(form_submissions)} form submissions for form {form_id}")
        
        return {
            "form_id": form_id,
            "total_form_submissions": len(form_submissions),
            "form_submissions": form_submissions
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error listing form submissions for {form_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred while listing form submissions")


@router.get("/submitted/{form_id}/{submission_id}/save")
async def save_form_submission(form_id: str, submission_id: str, reference_text: str):
    """Save values_used for a generated submission by form_id and submission_id."""
    try:
        logger.info(f"Saving form submission for form: {form_id}, submission: {submission_id}")

        # Verify form exists
        try:
            forms = load_forms()
        except StorageError as e:
            logger.error(f"Storage error while loading forms: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to retrieve forms")

        form = next((f for f in forms if f["id"] == form_id), None)
        if not form:
            logger.warning(f"Form not found while saving submission: {form_id}")
            raise HTTPException(status_code=404, detail=f"Form with ID '{form_id}' not found")

        # Verify form submission file belongs to form
        try:
            form_submissions = load_form_submissions()
        except StorageError as e:
            logger.error(f"Storage error while loading form submissions: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to retrieve form submissions")

        form_submissions_for_form = form_submissions.get(form_id, [])
        submission_record = next((f for f in form_submissions_for_form if f.get("submission_id") == submission_id), None)
        if not submission_record:
            logger.warning(f"Submission not found for form while saving submission: form={form_id}, submission={submission_id}")
            raise HTTPException(
                status_code=404,
                detail=f"Submission with ID '{submission_id}' not found for form '{form_id}'"
            )

        saved_submission_id = add_saved_form_submission(
            form_id=form_id,
            submission_id=submission_id,
            values_used=submission_record.get("values_used", {}),
            reference_text=reference_text
        )

        logger.info(f"Saved form submission: {saved_submission_id}")
        return {
            "message": "Form submission saved successfully",
            "form_id": form_id,
            "submission_id": submission_id,
            "reference_text": reference_text,
            "saved_submission_id": saved_submission_id,
            "saved_values": submission_record.get("values_used", {})
        }

    except HTTPException:
        raise
    except StorageError as e:
        logger.error(f"Storage error while saving form submission: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to save form submission")
    except Exception as e:
        logger.error(f"Unexpected error while saving form submission: {str(e)}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred while saving form submission")


@router.get("/saved/{form_id}")
async def get_saved_submissions_by_form_id(form_id: str, search_text: str = ""):
    """Fetch saved submissions for a given form_id, optionally filtered by reference_text."""
    try:
        logger.info(f"Fetching saved submissions for form: {form_id}")

        try:
            saved_form_submissions = load_saved_form_submissions()
        except StorageError as e:
            logger.error(f"Storage error while loading saved form submissions: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to retrieve saved form submissions")

        matches = saved_form_submissions.get(form_id, [])

        # Filter by reference_text when search_text is provided.
        if search_text:
            search_term = search_text.lower()
            matches = [
                submission
                for submission in matches
                if search_term in str(submission.get("reference_text", "")).lower()
            ]

        return {
            "form_id": form_id,
            "search_text": search_text,
            "total_saved_submissions": len(matches),
            "saved_submissions": matches,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error while fetching saved submissions for form {form_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred while fetching saved submissions")


@router.get("/saved/{submission_id}/re-generate")
async def regenerate_saved_submission(submission_id: str, form_id: str = Query(...)):
    """Regenerate a saved submission DOCX and cache it under the saved folder."""
    try:
        logger.info(f"Regenerating saved submission: form={form_id}, submission={submission_id}")

        # Verify form exists
        try:
            forms = load_forms()
        except StorageError as e:
            logger.error(f"Storage error while loading forms: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to retrieve forms")

        form = next((f for f in forms if f["id"] == form_id), None)
        if not form:
            raise HTTPException(status_code=404, detail=f"Form with ID '{form_id}' not found")

        # Find saved submission entry for this form and submission
        try:
            saved_form_submissions = load_saved_form_submissions()
        except StorageError as e:
            logger.error(f"Storage error while loading saved form submissions: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to retrieve saved form submissions")

        form_saved_entries = saved_form_submissions.get(form_id, [])
        saved_entry = next((s for s in form_saved_entries if s.get("submission_id") == submission_id), None)
        if not saved_entry:
            raise HTTPException(
                status_code=404,
                detail=f"Saved submission with ID '{submission_id}' not found for form '{form_id}'"
            )

        # If already regenerated and file still exists, return cached file.
        cached_file_path = saved_entry.get("regenerated_file_path")
        if cached_file_path and not os.path.isabs(cached_file_path):
            cached_file_path = os.path.abspath(cached_file_path)

        if saved_entry.get("is_regenerated") and cached_file_path and os.path.exists(cached_file_path):
            cached_filename = os.path.basename(cached_file_path)
            return FileResponse(
                cached_file_path,
                media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                filename=cached_filename,
                headers=build_docx_download_headers(cached_filename)
            )

        values_used = saved_entry.get("values_used", {})
        if not isinstance(values_used, dict):
            raise HTTPException(status_code=400, detail="Saved submission values are invalid")

        reference_text = str(saved_entry.get("reference_text", "saved")).strip() or "saved"
        safe_reference_text = "".join(
            character if character.isalnum() or character in (" ", "-", "_") else "_"
            for character in reference_text
        ).strip()
        safe_reference_text = safe_reference_text or "saved"

        # Generate DOCX from saved values without re-registering in form_submissions.
        generated_path, _ = fill_template(
            form["template_path"],
            values_used,
            form_id=None,
            form_name=safe_reference_text,
            font_family=form.get("style", {}).get("font_family"),
            font_size=form.get("style", {}).get("font_size")
        )

        saved_dir = os.path.abspath("saved")
        os.makedirs(saved_dir, exist_ok=True)
        saved_filename = f"{safe_reference_text}.docx"
        saved_file_path = os.path.join(saved_dir, saved_filename)

        # Move generated file into saved cache location.
        if os.path.exists(saved_file_path):
            os.remove(saved_file_path)
        shutil.move(generated_path, saved_file_path)

        # Persist regeneration state to avoid regenerating next time.
        saved_entry["is_regenerated"] = True
        saved_entry["regenerated_file_path"] = saved_file_path
        saved_entry["regenerated_at"] = datetime.now().isoformat()
        save_saved_form_submissions(saved_form_submissions)

        return FileResponse(
            saved_file_path,
            media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            filename=saved_filename,
            headers=build_docx_download_headers(saved_filename)
        )

    except HTTPException:
        raise
    except StorageError as e:
        logger.error(f"Storage error while regenerating saved submission: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to regenerate saved submission")
    except Exception as e:
        logger.error(f"Unexpected error while regenerating saved submission: {str(e)}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred while regenerating saved submission")


@router.delete("/saved/{form_id}/{submission_id}")
async def delete_saved_submission(form_id: str, submission_id: str):
    """Delete a saved submission object by form_id and submission_id."""
    try:
        logger.info(f"Deleting saved submission for form: {form_id}, submission: {submission_id}")

        try:
            deleted_count = delete_saved_form_submission(form_id=form_id, submission_id=submission_id)
        except StorageError as e:
            logger.error(f"Storage error while deleting saved submission: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to delete saved submission")

        if deleted_count == 0:
            raise HTTPException(
                status_code=404,
                detail=f"Saved submission not found for form '{form_id}' and submission '{submission_id}'"
            )

        return {
            "message": "Saved submission deleted successfully",
            "form_id": form_id,
            "submission_id": submission_id,
            "deleted_count": deleted_count
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error while deleting saved submission for form {form_id}, submission {submission_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred while deleting saved submission")

@router.get("/submitted/{submission_id}")
async def download_generated_file_by_id(submission_id: str):
    """Download a generated file directly by submission_id."""
    try:
        logger.info(f"Downloading generated file: {submission_id}")
        
        # Load all form submissions and search across all forms
        try:
            from app.utils.form_utils import load_form_submissions
            all_form_submissions = load_form_submissions()
        except StorageError as e:
            logger.error(f"Storage error while loading form submissions: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to retrieve form submissions")
        
        # Find the file across all forms
        submission_record = None
        for form_id, files in all_form_submissions.items():
            submission_record = next((f for f in files if f["submission_id"] == submission_id), None)
            if submission_record:
                break
        
        if not submission_record:
            logger.warning(f"Generated file not found: {submission_id}")
            raise HTTPException(status_code=404, detail=f"Generated file with ID '{submission_id}' not found")
        
        file_path = submission_record["file_path"]
        if not os.path.exists(file_path):
            logger.error(f"Generated file path does not exist: {file_path}")
            raise HTTPException(status_code=500, detail="Generated file not found on server")
        
        logger.info(f"Serving generated file: {file_path}")
        return FileResponse(
            file_path, 
            media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            filename=submission_record["filename"]
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error downloading generated file {submission_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred while downloading the file")

@router.get("/templates/{template_id}")
async def download_template(template_id: str):
    """Download form template by template_id."""
    try:
        logger.info(f"Downloading template: {template_id}")
        
        # Always serve the stored .docx file and force download
        template_filename = f"{template_id}.docx"
        template_path = os.path.join(TEMPLATES_DIR, template_filename)
        
        if not os.path.exists(template_path):
            logger.warning(f"Template file not found: {template_path}")
            raise HTTPException(status_code=404, detail=f"Template with ID '{template_id}' not found")
        
        logger.info(f"Template download initiated: {template_id}")
        return FileResponse(
            template_path, 
            media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            filename=template_filename
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error downloading template {template_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred while downloading the template")
