"""Authentication service for JWT token management and user operations."""
import logging
import secrets
import uuid as uuid_mod
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

import bcrypt
import jwt
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.email_otp import EmailOTP
from app.models.user import User, UserRole
from app.schemas.auth import TokenPayload, UserCreate, UserUpdate

logger = logging.getLogger(__name__)
settings = get_settings()


class AuthService:
    """Service for authentication operations."""

    def __init__(self, db: AsyncSession):
        """Initialize auth service."""
        self.db = db

    # ============================================================
    # Password Hashing
    # ============================================================

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using bcrypt."""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )

    # ============================================================
    # JWT Token Management
    # ============================================================

    @staticmethod
    def create_access_token(user: User, expires_minutes: Optional[int] = None) -> str:
        """Create a JWT access token for a user."""
        now = datetime.now(timezone.utc)
        minutes = expires_minutes or settings.jwt_access_token_expire_minutes
        expire = now + timedelta(minutes=minutes)

        payload = {
            "sub": str(user.id),
            "email": user.email,
            "role": user.role.value,
            "exp": int(expire.timestamp()),
            "iat": int(now.timestamp()),
            "type": "access",
        }

        return jwt.encode(
            payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )

    @staticmethod
    def create_refresh_token(user: User) -> str:
        """Create a JWT refresh token for a user."""
        now = datetime.now(timezone.utc)
        expire = now + timedelta(days=settings.jwt_refresh_token_expire_days)

        payload = {
            "sub": str(user.id),
            "email": user.email,
            "role": user.role.value,
            "exp": int(expire.timestamp()),
            "iat": int(now.timestamp()),
            "type": "refresh",
        }

        return jwt.encode(
            payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )

    @staticmethod
    def decode_token(token: str) -> Optional[TokenPayload]:
        """Decode and validate a JWT token."""
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
            )
            return TokenPayload(**payload)
        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None

    # ============================================================
    # User Operations
    # ============================================================

    async def get_user_by_id(self, user_id: UUID) -> Optional[User]:
        """Get a user by their ID."""
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get a user by their email."""
        result = await self.db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def get_user_by_google_id(self, google_id: str) -> Optional[User]:
        """Get a user by their Google ID."""
        result = await self.db.execute(
            select(User).where(User.google_id == google_id)
        )
        return result.scalar_one_or_none()

    async def get_user_by_username(self, username: str) -> Optional[User]:
        """Get a user by their username (case-insensitive)."""
        result = await self.db.execute(
            select(User).where(func.lower(User.username) == username.lower())
        )
        return result.scalar_one_or_none()

    async def is_username_available(self, username: str) -> bool:
        """Check if a username is available (case-insensitive)."""
        existing = await self.get_user_by_username(username)
        return existing is None

    async def create_user(self, user_data: UserCreate) -> User:
        """Create a new user."""
        user = User(
            email=user_data.email,
            password_hash=self.hash_password(user_data.password) if user_data.password else None,
            full_name=user_data.full_name,
            username=user_data.username,
            google_id=user_data.google_id,
            auth_provider=user_data.auth_provider,
            avatar_url=user_data.avatar_url,
            role=user_data.role,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        logger.info(f"Created user: {user.email} with role {user.role.value} via {user.auth_provider}")
        return user

    async def update_user(self, user: User, update_data: UserUpdate) -> User:
        """Update a user's information."""
        if update_data.full_name is not None:
            user.full_name = update_data.full_name
        if update_data.role is not None:
            user.role = update_data.role
        if update_data.is_active is not None:
            user.is_active = update_data.is_active

        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def update_last_login(self, user: User) -> None:
        """Update user's last login timestamp."""
        user.last_login_at = datetime.now(timezone.utc)
        await self.db.commit()

    async def change_password(
        self,
        user: User,
        current_password: str,
        new_password: str,
    ) -> bool:
        """Change a user's password."""
        if not user.password_hash or not self.verify_password(current_password, user.password_hash):
            return False

        user.password_hash = self.hash_password(new_password)
        await self.db.commit()
        return True

    async def set_username(self, user: User, username: str) -> User:
        """Set or update a user's username with uniqueness check."""
        if not await self.is_username_available(username):
            raise ValueError("Username is already taken")

        user.username = username
        await self.db.commit()
        await self.db.refresh(user)
        logger.info(f"Username set for user {user.email}: {username}")
        return user

    # ============================================================
    # Authentication Flow
    # ============================================================

    async def authenticate(self, email: str, password: str) -> Optional[User]:
        """Authenticate a user with email and password."""
        user = await self.get_user_by_email(email)
        if not user:
            logger.warning(f"Login attempt for non-existent user: {email}")
            return None

        if not user.is_active:
            logger.warning(f"Login attempt for inactive user: {email}")
            return None

        # Only local users can log in with password
        if user.auth_provider != "local":
            logger.warning(f"Password login attempt for {user.auth_provider} user: {email}")
            return None

        if not user.password_hash or not self.verify_password(password, user.password_hash):
            logger.warning(f"Invalid password for user: {email}")
            return None

        await self.update_last_login(user)
        logger.info(f"User authenticated: {email}")
        return user

    async def google_authenticate(
        self, id_token_str: str, username: Optional[str] = None
    ) -> tuple[User, bool]:
        """
        Authenticate via Google ID token.

        Returns:
            Tuple of (user, is_new_user)
        """
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests

        if not settings.google_client_id:
            raise ValueError("Google OAuth is not configured")

        # Verify the Google ID token
        idinfo = google_id_token.verify_oauth2_token(
            id_token_str,
            google_requests.Request(),
            settings.google_client_id,
        )

        google_id = idinfo["sub"]
        email = idinfo["email"]
        full_name = idinfo.get("name")
        avatar_url = idinfo.get("picture")

        # Check if user exists by Google ID
        user = await self.get_user_by_google_id(google_id)
        if user:
            await self.update_last_login(user)
            return user, False

        # Check if user exists by email (link accounts)
        user = await self.get_user_by_email(email)
        if user:
            user.google_id = google_id
            user.auth_provider = "google"
            if avatar_url and not user.avatar_url:
                user.avatar_url = avatar_url
            await self.update_last_login(user)
            await self.db.commit()
            await self.db.refresh(user)
            return user, False

        # New user — auto-derive username from email (same pattern as send_otp)
        import re as re_mod
        if not username:
            base = re_mod.sub(r"[^a-zA-Z0-9_]", "_", email.split("@")[0])[:16]
            if len(base) < 3:
                base = base + "_user"
            username = base
            suffix = 1
            while not await self.is_username_available(username):
                username = f"{base}_{suffix}"
                suffix += 1

        user_data = UserCreate(
            email=email,
            full_name=full_name,
            username=username,
            google_id=google_id,
            auth_provider="google",
            avatar_url=avatar_url,
            role=UserRole.CONSUMER,
        )
        user = await self.create_user(user_data)
        return user, True

    # ============================================================
    # Email OTP Verification
    # ============================================================

    async def send_otp(self, email: str, password: str, username: Optional[str] = None) -> dict:
        """Validate inputs, generate OTP, store hash, send email.

        Returns a generic success message to prevent email enumeration.
        """
        import re as re_mod
        from app.services.email_service import send_otp_email

        # Check if email already registered — return same response to prevent enumeration
        existing = await self.get_user_by_email(email)
        if existing:
            return {
                "message": "If this email is not yet registered, a verification code will be sent",
                "email": email,
                "expires_in_seconds": 600,
            }

        # Auto-derive username from email if not provided
        if not username:
            base = re_mod.sub(r"[^a-zA-Z0-9_]", "_", email.split("@")[0])[:16]
            if len(base) < 3:
                base = base + "_user"
            username = base
            suffix = 1
            while not await self.is_username_available(username):
                username = f"{base}_{suffix}"
                suffix += 1

        # Check username availability
        if not await self.is_username_available(username):
            return {
                "message": "If this email is not yet registered, a verification code will be sent",
                "email": email,
                "expires_in_seconds": 600,
            }

        # Rate limit: 1 OTP per email per 60 seconds
        existing_otp = await self.db.get(EmailOTP, email)
        if existing_otp:
            age = (datetime.now(timezone.utc) - existing_otp.created_at).total_seconds()
            if age < 60:
                return {
                    "message": "If this email is not yet registered, a verification code will be sent",
                    "email": email,
                    "expires_in_seconds": 600,
                }

        # Generate 6-digit OTP
        otp_code = f"{secrets.randbelow(1_000_000):06d}"
        otp_hash = self.hash_password(otp_code)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

        # Upsert: one active OTP per email
        if existing_otp:
            existing_otp.code_hash = otp_hash
            existing_otp.expires_at = expires_at
            existing_otp.attempts = 0
            existing_otp.created_at = datetime.now(timezone.utc)
        else:
            self.db.add(EmailOTP(
                email=email,
                code_hash=otp_hash,
                expires_at=expires_at,
                attempts=0,
            ))
        await self.db.commit()

        email_sent = send_otp_email(email, otp_code)

        result = {
            "message": "If this email is not yet registered, a verification code will be sent",
            "email": email,
            "expires_in_seconds": 600,
        }
        # In dev mode (no Resend API key), include OTP in response for testing
        if not email_sent:
            result["dev_otp"] = otp_code

        return result

    async def verify_otp_and_signup(
        self, email: str, password: str, username: Optional[str], otp_code: str
    ) -> User:
        """Verify OTP, check uniqueness, create user."""
        import re as re_mod

        otp = await self.db.get(EmailOTP, email)
        if not otp:
            raise ValueError("No verification code found. Please request a new one.")

        if otp.attempts >= 5:
            raise ValueError("Too many attempts. Please request a new code.")

        if datetime.now(timezone.utc) > otp.expires_at:
            raise ValueError("Verification code expired. Please request a new one.")

        otp.attempts += 1

        if not self.verify_password(otp_code, otp.code_hash):
            await self.db.commit()
            remaining = 5 - otp.attempts
            raise ValueError(f"Invalid code. {remaining} attempt(s) remaining.")

        # Re-check email uniqueness (race condition guard)
        existing = await self.get_user_by_email(email)
        if existing:
            raise ValueError("Email already registered.")

        # Auto-derive username from email if not provided
        if not username:
            base = re_mod.sub(r"[^a-zA-Z0-9_]", "_", email.split("@")[0])[:16]
            if len(base) < 3:
                base = base + "_user"
            username = base
            suffix = 1
            while not await self.is_username_available(username):
                username = f"{base}_{suffix}"
                suffix += 1

        # Re-check username uniqueness
        if not await self.is_username_available(username):
            raise ValueError("Username is already taken.")

        # Create user
        user_data = UserCreate(
            email=email,
            password=password,
            username=username,
            role=UserRole.CONSUMER,
            auth_provider="local",
        )
        user = await self.create_user(user_data)

        # Clean up OTP
        await self.db.delete(otp)
        await self.db.commit()

        logger.info(f"User created via OTP verification: {email}")
        return user

    async def create_guest_user(self) -> User:
        """Create a guest user with auto-generated credentials."""
        guest_id = uuid_mod.uuid4().hex[:8]
        email = f"guest_{guest_id}@guest.nepalosint.dev"
        username = f"guest_{guest_id}"

        user_data = UserCreate(
            email=email,
            username=username,
            auth_provider="guest",
            role=UserRole.CONSUMER,
        )
        user = await self.create_user(user_data)
        logger.info(f"Created guest user: {email}")
        return user

    async def refresh_access_token(self, refresh_token: str) -> Optional[tuple[str, User]]:
        """
        Refresh an access token using a refresh token.

        Returns:
            Tuple of (new_access_token, user) or None if invalid
        """
        payload = self.decode_token(refresh_token)
        if not payload:
            return None

        if payload.type != "refresh":
            logger.warning("Attempted to refresh with non-refresh token")
            return None

        user = await self.get_user_by_id(UUID(payload.sub))
        if not user or not user.is_active:
            return None

        new_access_token = self.create_access_token(user)
        return new_access_token, user

    # ============================================================
    # User Listing (for admin)
    # ============================================================

    async def list_users(
        self,
        skip: int = 0,
        limit: int = 100,
        role: Optional[UserRole] = None,
        is_active: Optional[bool] = None,
    ) -> list[User]:
        """List users with optional filters."""
        query = select(User)

        if role is not None:
            query = query.where(User.role == role)
        if is_active is not None:
            query = query.where(User.is_active == is_active)

        query = query.offset(skip).limit(limit).order_by(User.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())
