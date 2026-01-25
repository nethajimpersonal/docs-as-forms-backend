"""Authentication utilities for JWT token generation and verification."""

import os
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import json
import logging

logger = logging.getLogger(__name__)

# Security configuration
SECRET_KEY = os.getenv("SECRET_KEY", "B1abcD23efGHIjklMNO456pqrSTUvwxYZ7890abCDEfghIJklMNOpQRstuVWXYZ")
# Security configuration
SECRET_KEY = os.getenv("SECRET_KEY", "B1abcD23efGHIjklMNO456pqrSTUvwxYZ7890abCDEfghIJklMNOpQRstuVWXYZ")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 90

# Note: Passwords are stored as plaintext for development purposes only
# In production, use proper password hashing (bcrypt, argon2, etc.)

# Path to users database
USERS_FILE = "db/users.json"


def verify_password(plain_password: str, stored_password: str) -> bool:
    """Verify a plain password against the stored password (plaintext comparison)."""
    return plain_password == stored_password


def get_password_hash(password: str) -> str:
    """Return password as plaintext (no encryption).
    
    WARNING: This is for development only. Never use in production!
    """
    return password


def load_users() -> list:
    """Load users from JSON file."""
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, "r") as f:
                return json.load(f)
        return []
    except Exception as e:
        logger.error(f"Error loading users: {str(e)}")
        return []


def authenticate_user(username: str, password: str) -> Optional[dict]:
    """Authenticate a user by username and password."""
    users = load_users()
    for user in users:
        if user["username"] == username:
            if verify_password(password, user["password"]):
                return user
            return None
    return None


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[dict]:
    """Verify a JWT token and return the payload."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        logger.error(f"Token verification error: {str(e)}")
        return None


def save_users(users: list) -> None:
    """Save users to JSON file."""
    try:
        os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
        with open(USERS_FILE, "w") as f:
            json.dump(users, f, indent=4)
        logger.info(f"Users saved successfully to {USERS_FILE}")
    except IOError as e:
        logger.error(f"IO error while writing to {USERS_FILE}: {str(e)}")
        raise Exception(f"Cannot save users file: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error while saving users: {str(e)}")
        raise Exception(f"Unexpected error saving users: {str(e)}")


def user_exists(username: str, email: str) -> bool:
    """Check if a user already exists by username or email."""
    users = load_users()
    for user in users:
        if user["username"] == username or user["email"] == email:
            return True
    return False
