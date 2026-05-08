from dataclasses import dataclass
import re


REPOSITORY_NAME_RE = re.compile(r"^[a-z0-9]+(?:(?:[._-]|__)[a-z0-9]+)*(?:/[a-z0-9]+(?:(?:[._-]|__)[a-z0-9]+)*)*$")
ALLOWED_REPOSITORY_TYPES = {"repository", "repository(plugin)"}
ALLOWED_REPOSITORY_ACTIONS = {"pull", "push", "delete"}
ALLOWED_REGISTRY_ACTIONS = {"*"}


@dataclass(frozen=True)
class RequestedScope:
    resource_type: str
    resource_name: str
    actions: tuple[str, ...]


def parse_scope_string(scope: str) -> RequestedScope:
    if not scope:
        raise ValueError("Scope cannot be empty.")

    try:
        resource_type, remainder = scope.split(":", 1)
        resource_name, actions_part = remainder.rsplit(":", 1)
    except ValueError as exc:
        raise ValueError(f"Invalid scope format: {scope}") from exc

    actions = tuple(action for action in actions_part.split(",") if action)
    if not resource_type or not resource_name or not actions:
        raise ValueError(f"Invalid scope format: {scope}")

    normalized_type = resource_type
    if resource_type in ALLOWED_REPOSITORY_TYPES:
        normalized_type = "repository"
        if not REPOSITORY_NAME_RE.fullmatch(resource_name):
            raise ValueError(f"Invalid repository scope name: {resource_name}")
        invalid_actions = [action for action in actions if action not in ALLOWED_REPOSITORY_ACTIONS]
        if invalid_actions:
            raise ValueError(f"Invalid repository scope actions: {','.join(invalid_actions)}")
    elif resource_type == "registry":
        if resource_name != "catalog":
            raise ValueError(f"Unsupported registry scope resource: {resource_name}")
        invalid_actions = [action for action in actions if action not in ALLOWED_REGISTRY_ACTIONS]
        if invalid_actions:
            raise ValueError(f"Invalid registry scope actions: {','.join(invalid_actions)}")
    else:
        raise ValueError(f"Unsupported scope resource type: {resource_type}")

    return RequestedScope(
        resource_type=normalized_type,
        resource_name=resource_name,
        actions=actions,
    )


def parse_scopes(scope_values: list[str]) -> list[RequestedScope]:
    parsed: list[RequestedScope] = []
    for value in scope_values:
        for part in value.split():
            parsed.append(parse_scope_string(part))
    return parsed
