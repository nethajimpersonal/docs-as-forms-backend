"""Custom exception classes for the application."""

class FormException(Exception):
    """Base exception for form-related errors."""
    pass

class FormNotFound(FormException):
    """Raised when a form is not found."""
    pass

class FormCreationError(FormException):
    """Raised when form creation fails."""
    pass

class TemplateFillingError(FormException):
    """Raised when template filling fails."""
    pass

class InvalidFieldsError(FormException):
    """Raised when fields are invalid."""
    pass

class FileOperationError(FormException):
    """Raised when file operations fail."""
    pass

class StorageError(FormException):
    """Raised when storage operations fail."""
    pass
