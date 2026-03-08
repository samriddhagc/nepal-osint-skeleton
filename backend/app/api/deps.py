"""API dependencies for dependency injection."""
from typing import AsyncGenerator, Callable, List
from uuid import UUID

from fastapi import Depends, HTTPException, Request, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.user import User, UserRole
from app.services.auth_service import AuthService

# HTTP Bearer token scheme
security = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session dependency."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_current_user(
    request: Request,
    token: str | None = Query(default=None),
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """Get the current authenticated user from the JWT token.

    Uses a short-lived DB session that closes immediately after the user
    lookup — does NOT hold a connection for the entire request duration.
    This halves connection pressure vs the old approach where auth held
    its own get_db session open alongside the endpoint's session.
    """
    if credentials:
        raw_token = credentials.credentials
    elif token and request.method.upper() == "GET":
        raw_token = token
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = AuthService.decode_token(raw_token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Short-lived session — closes immediately after user fetch.
    # The old code used Depends(get_db) which held the connection open
    # for the entire request lifecycle, doubling pool pressure.
    async with AsyncSessionLocal() as db:
        auth_service = AuthService(db)
        user = await auth_service.get_user_by_id(UUID(payload.sub))

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is disabled",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_user_optional(
    request: Request,
    token: str | None = Query(default=None),
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User | None:
    """
    Get the current user if authenticated, otherwise return None.
    Useful for routes that work differently for authenticated vs anonymous users.
    """
    if not credentials and not token:
        return None

    try:
        return await get_current_user(
            request=request,
            token=token,
            credentials=credentials,
        )
    except HTTPException:
        return None


def require_role(allowed_roles: List[UserRole]) -> Callable:
    """
    Create a dependency that requires the user to have one of the specified roles.

    Usage:
        @router.get("/admin")
        async def admin_route(user: User = Depends(require_role([UserRole.DEV]))):
            ...
    """
    async def role_checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {[r.value for r in allowed_roles]}",
            )
        return user

    return role_checker


# Convenience dependencies for common role combinations
async def require_analyst(
    user: User = Depends(get_current_user),
) -> User:
    """Require analyst or dev role."""
    if not user.is_analyst_or_above():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requires analyst or dev role",
        )
    return user


async def require_dev(
    user: User = Depends(get_current_user),
) -> User:
    """Require dev role."""
    if not user.is_dev():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requires dev role",
        )
    return user
