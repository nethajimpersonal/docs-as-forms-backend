# Generated Files Storage System

## Overview
The system now stores filled templates in a dedicated `generated` folder and tracks all form submissions using a separate `form_submissions.json` database file.

## File Structure

```
project_root/
├── forms.json                    # Form definitions (unchanged)
├── form_submissions.json         # Form submission references & tracking
├── generated/                    # Folder for all filled documents
│   ├── sample-form_20260124_143022.docx
│   ├── sample-form_20260124_150512.docx
│   └── ...
├── templates/                    # Original templates
│   ├── form_uuid1.docx
│   ├── form_uuid2.docx
│   └── ...
```

## Generated Files Database Structure

### `form_submissions.json`

```json
{
  "form-id-1": [
    {
      "submission_id": "uuid-1",
      "file_path": "generated/sample-form_20260124_143022.docx",
      "filename": "sample-form_20260124_143022.docx",
      "created_at": "2026-01-24T14:30:22",
      "values_used": {
        "client_name": "John Doe",
        "case_number": "2026-CV-00123",
        ...
      }
    },
    {
      "submission_id": "uuid-2",
      "file_path": "generated/sample-form_20260124_150512.docx",
      "filename": "sample-form_20260124_150512.docx",
      "created_at": "2026-01-24T15:05:12",
      "values_used": {
        "client_name": "Jane Smith",
        "case_number": "2026-CV-00456",
        ...
      }
    }
  ],
  "form-id-2": [
    {
      "submission_id": "uuid-3",
      ...
    }
  ]
}
```

## Key Features

### 1. **Unique File Naming**
- Format: `{form_name}_{timestamp}.docx`
- Example: `sample-form_20260124_143022.docx`
- Timestamp format: `YYYYMMDD_HHMMSS`
- Special characters sanitized for safe filenames

### 2. **Complete Tracking**
Each generated file record includes:
- `submission_id` - Unique identifier for the generated file
- `file_path` - Relative path to the file
- `filename` - Original filename for download
- `created_at` - ISO timestamp of creation
- `values_used` - Complete values used to fill the form (for audit/reference)

### 3. **Organized Storage**
- All filled documents in `generated/` folder
- Original templates remain in `templates/` folder
- Clear separation of concerns

## New API Endpoints

### 1. **Fill Form (Enhanced)**
```
POST /forms/{form_id}/fill
```
**Response Headers:**
- `X-File-ID` - The file ID of the generated document for tracking

**Response:** Filled DOCX file + file ID header

### 2. **List Generated Files**
```
GET /forms/{form_id}/generated
```
**Returns:**
```json
{
  "form_id": "form-id-1",
  "total_generated": 5,
  "files": [
    {
      "submission_id": "uuid-1",
      "file_path": "generated/...",
      "filename": "...",
      "created_at": "2026-01-24T14:30:22.123456",
      "values_used": {...}
    },
    ...
  ]
}
```

### 3. **Download Specific Generated File**
```
GET /forms/{form_id}/generated/{submission_id}
```
**Returns:** The DOCX file

## Example Workflow

### Step 1: Fill Form
```javascript
const formData = new FormData();
formData.append('values', JSON.stringify({
  client_name: "John Doe",
  case_number: "2026-CV-00123"
}));

const response = await fetch('http://localhost:8000/api/forms/sample-form/fill', {
  method: 'POST',
  body: formData
});

// Get file ID from response header
const fileId = response.headers.get('X-File-ID');
console.log('Generated File ID:', fileId);

// Download file
const blob = await response.blob();
```

### Step 2: List All Generated Files for Form
```javascript
const response = await fetch('http://localhost:8000/api/forms/sample-form/generated');
const data = await response.json();

console.log(`Total generated files: ${data.total_generated}`);
data.files.forEach(file => {
  console.log(`- ${file.filename} (${file.created_at})`);
});
```

### Step 3: Download Specific Generated File
```javascript
const response = await fetch('http://localhost:8000/api/forms/sample-form/generated/uuid-1');
const blob = await response.blob();
// Download or use blob...
```

## Benefits

✅ **Non-destructive** - Original templates never modified  
✅ **Audit Trail** - All generated files tracked with values used  
✅ **Scalable** - One form can have unlimited generated files  
✅ **Retrievable** - Download any previously generated file by ID  
✅ **Organized** - Clear folder structure and database  
✅ **Timestamped** - Automatic creation timestamps for all files  
✅ **Unique IDs** - Every generated file has unique submission_id for reference  

## Database Functions

Available in `app/utils/form_utils.py`:

```python
# Load the generated files database
form_submissions = load_form_submissions()

# Save updated database
save_form_submissions(form_submissions)

# Get all generated files for a form
files = get_form_submissions(form_id)

# Register a new generated file (called automatically by fill_template)
submission_id = add_form_submission_file(form_id, file_path, values)
```
