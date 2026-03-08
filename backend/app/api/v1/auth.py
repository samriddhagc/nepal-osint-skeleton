"""Authentication API endpoints."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user, require_dev
from app.config import get_settings
from app.models.user import User, UserRole
from app.services.auth_service import AuthService
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    SimpleRegisterRequest,
    SendOTPRequest,
    VerifyOTPSignupRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserResponse,
    PasswordChangeRequest,
    GoogleAuthRequest,
    SetUsernameRequest,
    UserCreate,
    UserUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


# ============================================================
# Public Endpoints (No Authentication Required)
# ============================================================


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate user and return tokens.

    Returns JWT access and refresh tokens on successful authentication.
    """
    auth_service = AuthService(db)
    user = await auth_service.authenticate(request.email, request.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = auth_service.create_access_token(user)
    refresh_token = auth_service.create_refresh_token(user)

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user=UserResponse.model_validate(user),
    )


@router.post("/google", response_model=LoginResponse)
async def google_auth(
    request: GoogleAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate with Google OAuth ID token.

    For new users, creates a consumer account. Returns JWT tokens.
    """
    auth_service = AuthService(db)

    try:
        user, is_new = await auth_service.google_authenticate(
            request.id_token, request.username
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Google auth error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google ID token",
        )

    access_token = auth_service.create_access_token(user)
    refresh_token = auth_service.create_refresh_token(user)

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user=UserResponse.model_validate(user),
    )


@router.post("/guest", response_model=LoginResponse)
async def guest_login(
    db: AsyncSession = Depends(get_db),
):
    """
    Create a guest session with limited access.

    Creates a temporary consumer account with shorter token expiry.
    """
    auth_service = AuthService(db)
    user = await auth_service.create_guest_user()

    # Guest tokens expire sooner
    guest_expire_minutes = settings.guest_token_expire_hours * 60
    access_token = auth_service.create_access_token(user, expires_minutes=guest_expire_minutes)
    refresh_token = auth_service.create_refresh_token(user)

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=guest_expire_minutes * 60,
        user=UserResponse.model_validate(user),
    )


@router.post("/send-otp")
async def send_otp(
    request: SendOTPRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Send a 6-digit OTP to the user's email for signup verification.

    Rate limited to 1 OTP per email per 60 seconds.
    Returns a generic success message to prevent email enumeration.
    """
    auth_service = AuthService(db)
    result = await auth_service.send_otp(
        email=request.email,
        password=request.password,
        username=request.username or None,
    )
    return result


@router.post("/signup", response_model=LoginResponse)
async def signup(
    request: VerifyOTPSignupRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Verify OTP and complete signup. Creates a consumer account and returns tokens.
    """
    auth_service = AuthService(db)

    try:
        user = await auth_service.verify_otp_and_signup(
            email=request.email,
            password=request.password,
            username=request.username,
            otp_code=request.otp_code,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    access_token = auth_service.create_access_token(user)
    refresh_token = auth_service.create_refresh_token(user)

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user=UserResponse.model_validate(user),
    )


@router.post("/register-simple", response_model=LoginResponse)
async def register_simple(
    request: SimpleRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Simple registration without OTP verification.

    Auto-derives username from email prefix. Returns tokens immediately.
    """
    auth_service = AuthService(db)
    import re

    # Check if user already exists
    existing = await auth_service.get_user_by_email(request.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists",
        )

    # Auto-derive username from email prefix
    base_username = re.sub(r"[^a-zA-Z0-9_]", "_", request.email.split("@")[0])[:16]
    if len(base_username) < 3:
        base_username = base_username + "_user"

    # Ensure uniqueness
    username = base_username
    suffix = 1
    while not await auth_service.is_username_available(username):
        username = f"{base_username}_{suffix}"
        suffix += 1

    user_data = UserCreate(
        email=request.email,
        password=request.password,
        username=username,
        role=UserRole.CONSUMER,
    )

    try:
        user = await auth_service.create_user(user_data)
    except Exception as e:
        logger.error(f"Simple register error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration failed. Please try again.",
        )

    access_token = auth_service.create_access_token(user)
    refresh_token = auth_service.create_refresh_token(user)

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user=UserResponse.model_validate(user),
    )


@router.get("/check-username/{username}")
async def check_username(
    username: str,
    db: AsyncSession = Depends(get_db),
):
    """Check if a username is available."""
    auth_service = AuthService(db)
    available = await auth_service.is_username_available(username)
    return {"username": username, "available": available}


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Refresh an access token using a refresh token.

    Returns a new access token if the refresh token is valid.
    """
    auth_service = AuthService(db)
    result = await auth_service.refresh_access_token(request.refresh_token)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    new_access_token, _ = result

    return TokenResponse(
        access_token=new_access_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


# ============================================================
# Authenticated User Endpoints
# ============================================================


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
):
    """Get current authenticated user's information."""
    return UserResponse.model_validate(current_user)


@router.post("/set-username", response_model=UserResponse)
async def set_username(
    request: SetUsernameRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Set or update the current user's username."""
    auth_service = AuthService(db)

    try:
        user = await auth_service.set_username(current_user, request.username)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    return UserResponse.model_validate(user)


@router.post("/change-password")
async def change_password(
    request: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change the current user's password."""
    # Only local auth users can change password
    if current_user.auth_provider != "local":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password management is not available for {current_user.auth_provider} accounts",
        )

    auth_service = AuthService(db)
    success = await auth_service.change_password(
        current_user,
        request.current_password,
        request.new_password,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    return {"message": "Password changed successfully"}


# ============================================================
# Admin Endpoints (Dev Role Required)
# ============================================================


@router.post("/register", response_model=UserResponse)
async def register_user(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_dev),
):
    """
    Register a new user (dev only).

    Only users with the 'dev' role can create new users.
    """
    auth_service = AuthService(db)

    # Check if user already exists
    existing = await auth_service.get_user_by_email(request.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists",
        )

    # Check username availability
    if not await auth_service.is_username_available(request.username):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username is already taken",
        )

    user_data = UserCreate(
        email=request.email,
        password=request.password,
        full_name=request.full_name,
        username=request.username,
        role=request.role,
    )

    user = await auth_service.create_user(user_data)
    return UserResponse.model_validate(user)


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    role: Optional[UserRole] = Query(None),
    is_active: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_dev),
):
    """List all users (dev only)."""
    auth_service = AuthService(db)
    users = await auth_service.list_users(
        skip=skip,
        limit=limit,
        role=role,
        is_active=is_active,
    )
    return [UserResponse.model_validate(u) for u in users]


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    update_data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_dev),
):
    """Update a user's information (dev only)."""
    from uuid import UUID

    auth_service = AuthService(db)
    user = await auth_service.get_user_by_id(UUID(user_id))

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Prevent demoting self
    if str(user.id) == str(current_user.id) and update_data.role and update_data.role != current_user.role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own role",
        )

    updated_user = await auth_service.update_user(user, update_data)
    return UserResponse.model_validate(updated_user)


@router.delete("/users/{user_id}")
async def deactivate_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_dev),
):
    """Deactivate a user (dev only). Does not delete, just sets is_active=False."""
    from uuid import UUID

    auth_service = AuthService(db)
    user = await auth_service.get_user_by_id(UUID(user_id))

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Prevent deactivating self
    if str(user.id) == str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate yourself",
        )

    await auth_service.update_user(user, UserUpdate(is_active=False))
    return {"message": f"User {user.email} has been deactivated"}
