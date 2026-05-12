import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from backend.auth.passwords import hash_password
from backend.auth.pats import issue_personal_access_token
from backend.bootstrap import bootstrap_admin
from backend.config import Settings, load_settings
from backend.db import make_engine, make_session_factory
from backend.models import (
    AuditEvent,
    Base,
    CachedManifestSummary,
    GcJob,
    PersonalAccessToken,
    Repository,
    RepositoryPermission,
    RepositoryTag,
    User,
    WebSession,
)
from backend.phase4_seed import ensure_phase4_seed_allowed

FIXTURE_COUNT = 60
FIXTURE_USER_PREFIX = "page-user-"
FIXTURE_TOKEN_PREFIX = "page-seed-token-"
FIXTURE_SESSION_PREFIX = "page-seed-session-"
FIXTURE_AUDIT_PREFIX = "page-seed-audit-"
FIXTURE_JOB_PREFIX = "page-seed-fixture:"
FIXTURE_PERMISSION_PREFIX = "page-seed/"
FIXTURE_REPO_PREFIX = "sheldylew/page-seed-"
FIXTURE_TAG_REPO = "sheldylew/page-seed-tags"
ACTIVITY_USERNAME = "page-activity-user"
ACTIVITY_EMAIL = "page-activity-user@example.com"
ACTIVITY_PASSWORD = "page-activity-user-pass"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _upsert_user(
    session: Session,
    *,
    username: str,
    email: str,
    password: str,
    is_admin: bool = False,
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


def _clear_repo_fixtures(session: Session) -> None:
    repo_names = [
        *[f"{FIXTURE_REPO_PREFIX}{index:03d}" for index in range(1, FIXTURE_COUNT + 1)],
        FIXTURE_TAG_REPO,
    ]
    repo_ids = session.scalars(select(Repository.id).where(Repository.name.in_(repo_names))).all()
    if repo_ids:
        session.execute(delete(RepositoryTag).where(RepositoryTag.repository_id.in_(repo_ids)))
        session.execute(delete(Repository).where(Repository.id.in_(repo_ids)))
    session.execute(
        delete(CachedManifestSummary).where(
            or_(
                CachedManifestSummary.repository_name.like(f"{FIXTURE_REPO_PREFIX}%"),
                CachedManifestSummary.repository_name == FIXTURE_TAG_REPO,
            )
        )
    )


def seed_pagination_fixtures(session: Session, settings: Settings) -> dict:
    bootstrap_admin(session, settings)
    admin = session.scalar(select(User).where(User.username == settings.admin_username))
    if admin is None:
        raise RuntimeError("Admin bootstrap failed before pagination seeding.")

    activity_user = _upsert_user(
        session,
        username=ACTIVITY_USERNAME,
        email=ACTIVITY_EMAIL,
        password=ACTIVITY_PASSWORD,
    )

    page_users: list[User] = []
    for index in range(1, FIXTURE_COUNT + 1):
        user = _upsert_user(
            session,
            username=f"{FIXTURE_USER_PREFIX}{index:03d}",
            email=f"{FIXTURE_USER_PREFIX}{index:03d}@example.com",
            password=f"page-user-pass-{index:03d}",
        )
        page_users.append(user)

    page_user_ids = [user.id for user in page_users]
    session.execute(
        delete(RepositoryPermission).where(
            RepositoryPermission.subject_type == "user",
            RepositoryPermission.subject_id.in_(page_user_ids),
            RepositoryPermission.repository_pattern.like(f"{FIXTURE_PERMISSION_PREFIX}%"),
        )
    )
    session.execute(
        delete(PersonalAccessToken).where(
            PersonalAccessToken.user_id == admin.id,
            PersonalAccessToken.name.like(f"{FIXTURE_TOKEN_PREFIX}%"),
        )
    )
    session.execute(delete(WebSession).where(WebSession.csrf_token.like(f"{FIXTURE_SESSION_PREFIX}%")))
    session.execute(delete(AuditEvent).where(AuditEvent.action.like(f"{FIXTURE_AUDIT_PREFIX}%")))
    session.execute(delete(GcJob).where(GcJob.log_output.like(f"{FIXTURE_JOB_PREFIX}%")))
    _clear_repo_fixtures(session)
    session.flush()

    now = _utcnow()
    base_time = now - timedelta(minutes=FIXTURE_COUNT + 5)

    for index, user in enumerate(page_users, start=1):
        session.add(
            RepositoryPermission(
                subject_type="user",
                subject_id=user.id,
                repository_pattern=f"{FIXTURE_PERMISSION_PREFIX}{index:03d}/*",
                can_pull=True,
                can_push=False,
                can_delete=False,
                created_at=base_time + timedelta(seconds=index),
            )
        )

    for index in range(1, FIXTURE_COUNT + 1):
        issue_personal_access_token(session, user_id=admin.id, name=f"{FIXTURE_TOKEN_PREFIX}{index:03d}")

    for index in range(1, FIXTURE_COUNT + 1):
        created_at = base_time + timedelta(minutes=index)
        session.add(
            WebSession(
                user_id=admin.id,
                session_hash=f"{index:064x}",
                csrf_token=f"{FIXTURE_SESSION_PREFIX}{index:03d}",
                expires_at=now + timedelta(days=7),
                last_seen_at=created_at,
                created_at=created_at,
            )
        )
        session.add(
            AuditEvent(
                actor_type="user",
                actor_id=admin.id,
                action=f"{FIXTURE_AUDIT_PREFIX}{index:03d}",
                target_type="user",
                target_id=activity_user.id,
                metadata_json={"repo": f"{FIXTURE_REPO_PREFIX}{index:03d}"},
                created_at=base_time + timedelta(seconds=index),
            )
        )
        session.add(
            GcJob(
                status="succeeded",
                requested_by=admin.id,
                dry_run=False,
                delete_untagged=False,
                prune_empty_dirs=False,
                started_at=created_at,
                finished_at=created_at + timedelta(seconds=5),
                log_output=f"{FIXTURE_JOB_PREFIX}{index:03d}",
                created_at=created_at,
                updated_at=created_at,
            )
        )

    for index in range(1, FIXTURE_COUNT + 1):
        created_at = base_time + timedelta(seconds=index)
        repository = Repository(
            name=f"{FIXTURE_REPO_PREFIX}{index:03d}",
            visibility="private",
            created_at=created_at,
            updated_at=created_at,
            last_seen_at=created_at,
        )
        session.add(repository)
        session.flush()
        session.add(
            RepositoryTag(
                repository_id=repository.id,
                name="latest",
                manifest_digest=f"sha256:page-seed-{index:03d}",
                media_type="application/vnd.oci.image.manifest.v1+json",
                pushed_at=created_at,
                last_seen_at=created_at,
                created_at=created_at,
                updated_at=created_at,
            )
        )

    tag_repository = Repository(
        name=FIXTURE_TAG_REPO,
        visibility="private",
        created_at=base_time,
        updated_at=base_time,
        last_seen_at=base_time,
    )
    session.add(tag_repository)
    session.flush()
    for index in range(1, FIXTURE_COUNT + 1):
        created_at = base_time + timedelta(seconds=index)
        session.add(
            RepositoryTag(
                repository_id=tag_repository.id,
                name=f"v{index:03d}",
                manifest_digest=f"sha256:page-seed-tags-{index:03d}",
                media_type="application/vnd.oci.image.manifest.v1+json",
                pushed_at=created_at,
                last_seen_at=created_at,
                created_at=created_at,
                updated_at=created_at,
            )
        )

    session.commit()

    return {
        "activity_user_id": activity_user.id,
        "activity_username": ACTIVITY_USERNAME,
        "default_page_size_fixture_count": FIXTURE_COUNT,
        "tag_repository": FIXTURE_TAG_REPO,
    }


def main() -> None:
    settings = load_settings()
    ensure_phase4_seed_allowed(settings)
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    Base.metadata.create_all(engine)

    with session_factory() as session:
        seeded = seed_pagination_fixtures(session, settings)

    print(json.dumps(seeded))


if __name__ == "__main__":
    main()
