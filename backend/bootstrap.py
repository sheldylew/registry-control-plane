from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.auth.passwords import hash_password
from backend.config import Settings
from backend.models import User


def bootstrap_admin(session: Session, settings: Settings) -> Optional[User]:
    existing_admin = session.scalar(select(User).where(User.is_admin.is_(True)))
    if existing_admin is not None:
        return None

    if not (settings.admin_username and settings.admin_password and settings.admin_email):
        return None

    user = User(
        username=settings.admin_username,
        email=settings.admin_email,
        password_hash=hash_password(settings.admin_password),
        is_admin=True,
        is_active=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
