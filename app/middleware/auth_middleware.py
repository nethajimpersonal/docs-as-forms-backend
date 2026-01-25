"""Authentication middleware for JWT token verification."""

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from app.utils.auth_utils import verify_token
import logging
import re

logger = logging.getLogger(__name__)

# Routes excluded from authentication
EXCLUDED_ROUTES = [
    "/api/user/register",
    "/api/user/login",
    "/api/health",
    "/api/docs",
    "/api/redoc",
    "/api/openapi.json",
]


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware for JWT authentication on protected routes."""
    
    def __init__(self, app):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next):
        """Process the request and verify JWT token for protected routes."""
        
        # Check if the route is excluded from authentication
        if self._is_excluded_route(request.url.path):
            return await call_next(request)
        
        # Extract the token from the Authorization header
        auth_header = request.headers.get("Authorization")
        
        if not auth_header:
            logger.warning(f"Missing Authorization header for route: {request.url.path}")
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing authorization token"}
            )
        
        # Extract the token from "Bearer <token>"
        try:
            scheme, token = auth_header.split()
            if scheme.lower() != "bearer":
                logger.warning(f"Invalid auth scheme: {scheme}")
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid authentication scheme"}
                )
        except ValueError:
            logger.warning("Invalid Authorization header format")
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid authorization header format"}
            )
        
        # Verify the token
        payload = verify_token(token)
        if not payload:
            logger.warning(f"Invalid or expired token for route: {request.url.path}")
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired token"}
            )
        
        # Add user info to request state
        request.state.user = payload
        request.state.user_id = payload.get("user_id")
        request.state.username = payload.get("sub")
        
        logger.info(f"Authenticated user {payload.get('sub')} accessing {request.url.path}")
        
        response = await call_next(request)
        return response
    
    @staticmethod
    def _is_excluded_route(path: str) -> bool:
        """Check if a route is in the excluded routes list."""
        for excluded in EXCLUDED_ROUTES:
            # Exact match
            if path == excluded:
                return True
            # Pattern match (e.g., /docs/*)
            if excluded.endswith("*"):
                pattern = excluded.replace("*", ".*")
                if re.match(f"^{pattern}$", path):
                    return True
        return False
    
    @staticmethod
    def add_excluded_route(route: str) -> None:
        """Add a route to the excluded routes list."""
        if route not in EXCLUDED_ROUTES:
            EXCLUDED_ROUTES.append(route)
            logger.info(f"Added {route} to excluded routes")
    
    @staticmethod
    def remove_excluded_route(route: str) -> None:
        """Remove a route from the excluded routes list."""
        if route in EXCLUDED_ROUTES:
            EXCLUDED_ROUTES.remove(route)
            logger.info(f"Removed {route} from excluded routes")
    
    @staticmethod
    def get_excluded_routes() -> list:
        """Get the list of excluded routes."""
        return EXCLUDED_ROUTES.copy()
