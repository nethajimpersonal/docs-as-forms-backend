from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from app.routers.form_router import router
from app.exceptions import FormException
from app.middleware.auth_middleware import AuthMiddleware
from fastapi.middleware.cors import CORSMiddleware
import logging
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Legal Report Form Backend",
    description="API for creating and filling legal report form templates",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

# Include routers
app.include_router(router, prefix="/api")

# Auth Middleware - Add before CORS
app.add_middleware(AuthMiddleware)

# CORS Middleware
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global exception handlers

@app.exception_handler(FormException)
async def form_exception_handler(request: Request, exc: FormException):
    """Handle custom form exceptions."""
    logger.error(f"Form exception: {str(exc)}")
    return JSONResponse(
        status_code=400,
        content={"detail": f"Form error: {str(exc)}"}
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors."""
    logger.error(f"Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Invalid request data",
            "errors": exc.errors()
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle all uncaught exceptions."""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Please try again later."}
    )

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    logger.info("Health check performed")
    return {"status": "healthy"}

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Legal Report Form Backend API",
        "docs": "/docs",
        "health": "/health"
    }

if __name__ == "__main__":
    logger.info("Starting application...")