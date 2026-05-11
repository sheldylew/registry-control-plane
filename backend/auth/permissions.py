from dataclasses import dataclass
import re
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.auth.scopes import RequestedScope
from backend.models import Repository, RepositoryPermission


REPOSITORY_PATTERN_RE = re.compile(r"^[a-z0-9]+(?:(?:[._-]|__)[a-z0-9]+)*(?:/[a-z0-9]+(?:(?:[._-]|__)[a-z0-9]+)*)*$")
REPOSITORY_NAMESPACE_PATTERN_RE = re.compile(r"^[a-z0-9]+(?:(?:[._-]|__)[a-z0-9]+)*$")


@dataclass(frozen=True)
class AllowedAccess:
    resource_type: str
    resource_name: str
    actions: tuple[str, ...]


def validate_repository_pattern(pattern: str) -> str:
    value = pattern.strip()
    if not value:
        raise ValueError("Repository pattern is required.")
    if value == "*":
        raise ValueError("Global '*' repository permissions are not allowed.")
    if value.endswith("/*"):
        namespace = value[:-2]
        if not REPOSITORY_NAMESPACE_PATTERN_RE.fullmatch(namespace):
            raise ValueError("Repository wildcard patterns must use the form 'namespace/*'.")
        return value
    if not REPOSITORY_PATTERN_RE.fullmatch(value):
        raise ValueError("Repository patterns must be an exact repository name or 'namespace/*'.")
    return value


def validate_repository_name(repository_name: str) -> str:
    value = repository_name.strip()
    if not value:
        raise ValueError("Repository name is required.")
    if value == "*" or value.endswith("/*"):
        raise ValueError("Repository visibility must target an exact repository name.")
    if not REPOSITORY_PATTERN_RE.fullmatch(value):
        raise ValueError("Repository name must be an exact repository path.")
    return value


def _pattern_matches(pattern: str, repository_name: str) -> bool:
    if pattern == "*":
        return True
    if pattern.endswith("/*"):
        namespace = pattern[:-2]
        return repository_name.startswith(f"{namespace}/")
    return pattern == repository_name


def _pattern_rank(pattern: str, repository_name: str) -> tuple[int, int]:
    if pattern == repository_name:
        return (3, len(pattern))
    if pattern.endswith("/*") and _pattern_matches(pattern, repository_name):
        return (2, len(pattern))
    if pattern == "*":
        return (1, 1)
    return (0, 0)


def _row_actions(permission: RepositoryPermission) -> set[str]:
    actions: set[str] = set()
    if permission.can_pull:
        actions.add("pull")
    if permission.can_push:
        actions.add("push")
    if permission.can_delete:
        actions.add("delete")
    return actions


def _repository_actions_from_permission_rows(
    permissions: list[RepositoryPermission],
    *,
    repository_name: str,
) -> set[str]:
    exact_matches = [perm for perm in permissions if perm.repository_pattern == repository_name]
    if exact_matches:
        return set().union(*[_row_actions(permission) for permission in exact_matches])

    wildcard_matches = [
        permission
        for permission in permissions
        if _pattern_matches(permission.repository_pattern, repository_name)
    ]
    if not wildcard_matches:
        return set()

    best_rank = max(_pattern_rank(permission.repository_pattern, repository_name) for permission in wildcard_matches)
    best_matches = [
        permission
        for permission in wildcard_matches
        if _pattern_rank(permission.repository_pattern, repository_name) == best_rank
    ]
    return set().union(*[_row_actions(permission) for permission in best_matches])


def _repository_actions_for_subject(
    session: Session,
    *,
    subject_type: str,
    subject_id: Optional[int],
    repository_name: str,
) -> set[str]:
    if subject_id is None:
        return set()
    permissions = session.scalars(
        select(RepositoryPermission).where(
            RepositoryPermission.subject_type == subject_type,
            RepositoryPermission.subject_id == subject_id,
        )
    ).all()
    return _repository_actions_from_permission_rows(permissions, repository_name=repository_name)


def _public_repository_names(session: Session, repository_names: list[str]) -> set[str]:
    if not repository_names:
        return set()

    public_names: set[str] = set()
    chunk_size = 500
    for offset in range(0, len(repository_names), chunk_size):
        chunk = repository_names[offset:offset + chunk_size]
        public_names.update(
            session.scalars(
                select(Repository.name).where(
                    Repository.name.in_(chunk),
                    Repository.visibility == "public",
                )
            ).all()
        )
    return public_names


def is_repository_public(session: Session, repository_name: str) -> bool:
    repository = session.scalar(select(Repository).where(Repository.name == repository_name))
    return repository is not None and repository.visibility == "public"


def resolve_allowed_access(
    session: Session,
    *,
    subject_type: str,
    subject_id: Optional[int],
    is_admin: bool,
    requested_scopes: list[RequestedScope],
) -> list[AllowedAccess]:
    allowed: list[AllowedAccess] = []

    for scope in requested_scopes:
        if is_admin:
            allowed_actions = set(scope.actions)
        elif scope.resource_type == "repository":
            allowed_actions = set()
            if is_repository_public(session, scope.resource_name):
                allowed_actions.add("pull")
            allowed_actions.update(_repository_actions_for_subject(
                session,
                subject_type=subject_type,
                subject_id=subject_id,
                repository_name=scope.resource_name,
            ))
        elif scope.resource_type == "registry" and scope.resource_name == "catalog":
            global_actions = _repository_actions_for_subject(
                session,
                subject_type=subject_type,
                subject_id=subject_id,
                repository_name="*",
            )
            allowed_actions = {"*"} if "pull" in global_actions and "*" in scope.actions else set()
        else:
            allowed_actions = set()

        intersected_actions = tuple(action for action in scope.actions if action in allowed_actions)
        allowed.append(
            AllowedAccess(
                resource_type=scope.resource_type,
                resource_name=scope.resource_name,
                actions=intersected_actions,
            )
        )

    return allowed


def can_access_repository(
    session: Session,
    *,
    subject_type: str,
    subject_id: Optional[int],
    is_admin: bool,
    repository_name: str,
    action: str,
) -> bool:
    if is_admin:
        return True
    if action == "pull" and is_repository_public(session, repository_name):
        return True
    return action in _repository_actions_for_subject(
        session,
        subject_type=subject_type,
        subject_id=subject_id,
        repository_name=repository_name,
    )


def filter_visible_repositories(
    session: Session,
    *,
    subject_type: str,
    subject_id: Optional[int],
    is_admin: bool,
    repository_names: list[str],
) -> list[str]:
    if is_admin:
        return sorted(repository_names)

    public_names = _public_repository_names(session, repository_names)
    permissions = []
    if subject_id is not None:
        permissions = session.scalars(
            select(RepositoryPermission).where(
                RepositoryPermission.subject_type == subject_type,
                RepositoryPermission.subject_id == subject_id,
            )
        ).all()

    visible = [
        repository_name
        for repository_name in repository_names
        if repository_name in public_names or "pull" in _repository_actions_from_permission_rows(
            permissions,
            repository_name=repository_name,
        )
    ]
    return sorted(visible)
