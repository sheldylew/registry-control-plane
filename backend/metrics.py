from __future__ import annotations

from collections import Counter


_COUNTERS = Counter(
    {
        "registry_auth_token_requests_total": 0,
        "registry_auth_token_denied_total": 0,
        "registry_auth_scope_grants_total": 0,
        "registry_auth_scope_denials_total": 0,
        "registry_public_pull_tokens_issued_total": 0,
        "registry_ui_logins_total": 0,
        "registry_ui_login_failures_total": 0,
    }
)


def increment(name: str, amount: int = 1) -> None:
    _COUNTERS[name] += amount


def snapshot() -> dict[str, int]:
    return dict(_COUNTERS)


def reset() -> None:
    for key in list(_COUNTERS.keys()):
        _COUNTERS[key] = 0


def render_prometheus_text() -> str:
    lines = [
        "# TYPE registry_auth_token_requests_total counter",
        f"registry_auth_token_requests_total {_COUNTERS['registry_auth_token_requests_total']}",
        "# TYPE registry_auth_token_denied_total counter",
        f"registry_auth_token_denied_total {_COUNTERS['registry_auth_token_denied_total']}",
        "# TYPE registry_auth_scope_grants_total counter",
        f"registry_auth_scope_grants_total {_COUNTERS['registry_auth_scope_grants_total']}",
        "# TYPE registry_auth_scope_denials_total counter",
        f"registry_auth_scope_denials_total {_COUNTERS['registry_auth_scope_denials_total']}",
        "# TYPE registry_public_pull_tokens_issued_total counter",
        f"registry_public_pull_tokens_issued_total {_COUNTERS['registry_public_pull_tokens_issued_total']}",
        "# TYPE registry_ui_logins_total counter",
        f"registry_ui_logins_total {_COUNTERS['registry_ui_logins_total']}",
        "# TYPE registry_ui_login_failures_total counter",
        f"registry_ui_login_failures_total {_COUNTERS['registry_ui_login_failures_total']}",
    ]
    return "\n".join(lines) + "\n"
