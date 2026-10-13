import logging
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User, UserRole
from app.schemas.auth import Token, UserOut, UserCreate, UserLogin, PasswordChange
from app.api.deps import verify_password, create_access_token, get_current_user, get_password_hash, require_roles

logger = logging.getLogger("erp.auth")

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _authenticate_and_create_token(db: Session, username_input: str, password_input: str) -> dict:
    username_clean = (username_input or "").strip()
    user = db.query(User).filter(User.username == username_clean).first()

    # Check lockout
    now = datetime.utcnow()
    if user and user.locked_until and user.locked_until > now:
        remaining_sec = int((user.locked_until - now).total_seconds())
        remaining_min = max(1, (remaining_sec + 59) // 60)
        logger.warning("Login attempt on locked account '%s'", username_clean)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account is temporarily locked due to repeated failed attempts. Please try again in {remaining_min} minute(s)."
        )

    # Validate password
    if not user or not verify_password(password_input, user.hashed_password):
        if user:
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= 5:
                user.locked_until = now + timedelta(minutes=15)
                logger.warning("Account '%s' locked after 5 failed login attempts", username_clean)
            db.commit()
        logger.warning("Failed login attempt for username '%s'", username_clean)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate active status
    if not user.is_active:
        logger.warning("Login rejected for deactivated user '%s'", username_clean)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User account is deactivated. Contact an administrator."
        )

    # Reset failure counters & record successful login timestamp
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    db.commit()

    role_val = user.role.value if hasattr(user.role, "value") else str(user.role)
    access_token = create_access_token(
        data={"sub": user.username, "user_id": user.id, "role": role_val}
    )

    logger.info("User '%s' (role: %s) successfully authenticated", user.username, role_val)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role,
        "is_admin": user.is_admin,
    }


@router.post("/login", response_model=Token)
async def login(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Dual-protocol authentication endpoint supporting both:
    1. Modern JSON payload (application/json)
    2. Standard form-data (application/x-www-form-urlencoded, multipart/form-data)
    """
    username = None
    password = None

    content_type = request.headers.get("content-type", "").lower()
    if "application/json" in content_type:
        try:
            body = await request.json()
            if isinstance(body, dict):
                username = body.get("username")
                password = body.get("password")
        except Exception:
            pass
    elif "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        try:
            form = await request.form()
            username = form.get("username")
            password = form.get("password")
        except Exception:
            pass
    else:
        # Fallback: attempt JSON first, then Form
        try:
            body = await request.json()
            if isinstance(body, dict):
                username = body.get("username")
                password = body.get("password")
        except Exception:
            try:
                form = await request.form()
                username = form.get("username")
                password = form.get("password")
            except Exception:
                pass

    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username and password are required"
        )

    return _authenticate_and_create_token(db, username, password)


@router.post("/logout")
def logout(current_user: User = Depends(get_current_user)):
    """
    Secure session termination.
    """
    logger.info("User '%s' logged out", current_user.username)
    return {"status": "success", "message": "Logged out successfully"}


@router.get("/me", response_model=UserOut)
def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/change-password")
def change_password(
    pwd_data: PasswordChange,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not verify_password(pwd_data.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )
    if len(pwd_data.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 6 characters"
        )

    current_user.hashed_password = get_password_hash(pwd_data.new_password)
    current_user.password_changed_at = datetime.utcnow()
    db.commit()
    logger.info("Password changed for user '%s'", current_user.username)
    return {"status": "success", "message": "Password updated successfully"}


@router.post("/users", response_model=UserOut)
def create_user(
    user_in: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN]))
):
    if db.query(User).filter(User.username == user_in.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    if db.query(User).filter(User.email == user_in.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        username=user_in.username,
        email=user_in.email,
        full_name=user_in.full_name,
        role=user_in.role,
        hashed_password=get_password_hash(user_in.password),
        is_active=user_in.is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("User '%s' created by admin '%s'", user.username, current_user.username)
    return user
