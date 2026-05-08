import json
import os
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.auth.passwords import hash_password
from backend.auth.pats import _extract_prefix, _hash_token
from backend.bootstrap import bootstrap_admin
from backend.config import Settings, load_settings
from backend.db import make_engine, make_session_factory
from backend.models import Base, RepositoryPermission, RobotAccount, RobotToken, User

DEVELOPER_USERNAME = "developer"
DEVELOPER_EMAIL = "developer@example.com"
DEVELOPER_PASSWORD = "developer-pass-123"

READER_USERNAME = "reader"
READER_EMAIL = "reader@example.com"
READER_PASSWORD = "reader-pass-123"

ROBOT_NAME = "ci-sheldylew"
ROBOT_DESCRIPTION = "Phase 4 CI robot"
ROBOT_TOKEN_NAME = "phase4-cli"
ROBOT_TOKEN = "rcr_robot_c1c1c1c1.0123456789abcdef0123456789abcdef"
REVOKED_ROBOT_TOKEN_NAME = "phase4-revoked"
REVOKED_ROBOT_TOKEN = "rcr_robot_d2d2d2d2.fedcba9876543210fedcba9876543210"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_phase4_seed_allowed(settings: Settings) -> None:
    if settings.app_env == "development":
        return
    if os.getenv("ALLOW_PHASE4_SEED") == "1":
        return
    raise RuntimeError(
        "Phase 4 seed data is disabled outside development. "
        "Set APP_ENV=development or ALLOW_PHASE4_SEED=1 to continue."
    )


def _upsert_user(
    session: Session,
    *,
    username: str,
    email: str,
    password: str,
    is_admin: bool,
) -> User:
    user = session.scalar(select(User).where(User.username == username))
    password_hash = hash_password(password)

    if user is None:
        user = User(
            username=username,
            email=email,
            password_hash=password_hash,
            is_admin=is_admin,
            is_active=True,
        )
        session.add(user)
        session.flush()
        return user

    user.email = email
    user.password_hash = password_hash
    user.is_admin = is_admin
    user.is_active = True
    session.flush()
    return user


def _upsert_robot(session: Session, *, name: str, description: str) -> RobotAccount:
    robot = session.scalar(select(RobotAccount).where(RobotAccount.name == name))
    if robot is None:
        robot = RobotAccount(name=name, description=description, is_active=True)
        session.add(robot)
        session.flush()
        return robot

    robot.description = description
    robot.is_active = True
    session.flush()
    return robot


def _replace_permissions(
    session: Session,
    *,
    subject_type: str,
    subject_id: int,
    rows: list[dict],
) -> None:
    session.execute(
        delete(RepositoryPermission).where(
            RepositoryPermission.subject_type == subject_type,
            RepositoryPermission.subject_id == subject_id,
        )
    )
    for row in rows:
        session.add(
            RepositoryPermission(
                subject_type=subject_type,
                subject_id=subject_id,
                repository_pattern=row["repository_pattern"],
                can_pull=row["can_pull"],
                can_push=row["can_push"],
                can_delete=row["can_delete"],
            )
        )


def _replace_robot_tokens(session: Session, *, robot: RobotAccount) -> None:
    session.execute(delete(RobotToken).where(RobotToken.robot_id == robot.id))

    active_prefix = _extract_prefix(ROBOT_TOKEN, "rcr_robot")
    revoked_prefix = _extract_prefix(REVOKED_ROBOT_TOKEN, "rcr_robot")
    if active_prefix is None or revoked_prefix is None:
        raise ValueError("Phase 4 robot tokens are malformed.")

    session.add(
        RobotToken(
            robot_id=robot.id,
            name=ROBOT_TOKEN_NAME,
            token_hash=_hash_token(ROBOT_TOKEN),
            token_prefix=active_prefix,
            revoked_at=None,
        )
    )
    session.add(
        RobotToken(
            robot_id=robot.id,
            name=REVOKED_ROBOT_TOKEN_NAME,
            token_hash=_hash_token(REVOKED_ROBOT_TOKEN),
            token_prefix=revoked_prefix,
            revoked_at=_utcnow(),
        )
    )


def seed_phase4_subjects(session: Session, settings: Settings) -> dict:
    bootstrap_admin(session, settings)

    developer = _upsert_user(
        session,
        username=DEVELOPER_USERNAME,
        email=DEVELOPER_EMAIL,
        password=DEVELOPER_PASSWORD,
        is_admin=False,
    )
    reader = _upsert_user(
        session,
        username=READER_USERNAME,
        email=READER_EMAIL,
        password=READER_PASSWORD,
        is_admin=False,
    )
    robot = _upsert_robot(session, name=ROBOT_NAME, description=ROBOT_DESCRIPTION)

    _replace_permissions(
        session,
        subject_type="user",
        subject_id=developer.id,
        rows=[
            {
                "repository_pattern": "sheldylew/*",
                "can_pull": True,
                "can_push": True,
                "can_delete": False,
            }
        ],
    )
    _replace_permissions(
        session,
        subject_type="user",
        subject_id=reader.id,
        rows=[
            {
                "repository_pattern": "sheldylew/*",
                "can_pull": True,
                "can_push": False,
                "can_delete": False,
            }
        ],
    )
    _replace_permissions(
        session,
        subject_type="robot",
        subject_id=robot.id,
        rows=[
            {
                "repository_pattern": "sheldylew/*",
                "can_pull": True,
                "can_push": False,
                "can_delete": False,
            },
            {
                "repository_pattern": "sheldylew/sheldylew.com",
                "can_pull": True,
                "can_push": True,
                "can_delete": False,
            },
        ],
    )
    _replace_robot_tokens(session, robot=robot)
    session.commit()

    return {
        "users": {
            "admin": {
                "username": settings.admin_username,
                "password": settings.admin_password,
            },
            "developer": {
                "username": DEVELOPER_USERNAME,
                "password": DEVELOPER_PASSWORD,
            },
            "reader": {
                "username": READER_USERNAME,
                "password": READER_PASSWORD,
            },
        },
        "robots": {
            ROBOT_NAME: {
                "token": ROBOT_TOKEN,
                "revoked_token": REVOKED_ROBOT_TOKEN,
            }
        },
    }


def main() -> None:
    settings = load_settings()
    ensure_phase4_seed_allowed(settings)
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    Base.metadata.create_all(engine)

    with session_factory() as session:
        seeded = seed_phase4_subjects(session, settings)

    print(json.dumps(seeded))


if __name__ == "__main__":
    main()
