import os
from dataclasses import dataclass
from typing import Optional


def _get_csv_env(name: str) -> tuple[str, ...]:
    value = os.getenv(name, "")
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _get_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_env: str
    database_url: str
    registry_internal_url: str
    registry_storage_root: str
    compose_project_dir: str
    registry_service_name: str
    registry_gc_config_path: str
    token_issuer: str
    token_service: str
    token_ttl_seconds: int
    public_registry_origin: str
    auth_private_key_path: str
    auth_public_cert_path: str
    internal_api_base_url: str
    csrf_trusted_origins: tuple[str, ...] = ()
    auth_bootstrap_marker_path: str = ".local-data/auth/bootstrap-complete"
    setup_token_path: str = ".local-data/setup-token.json"
    setup_complete_marker_path: str = ".local-data/setup-complete"
    registry_notifications_token_path: str = ".local-data/registry-events-token"
    registry_config_template_path: str = "docker/registry-config.yml.tmpl"
    registry_rendered_config_path: str = ".local-data/registry-config.yml"
    maintenance_min_gate_seconds: float = 1.0
    registry_catalog_max_pages: int = 10
    dashboard_max_repositories: int = 50
    repository_tags_max_items: int = 100
    manifest_children_max_items: int = 25
    history_entries_max_items: int = 50
    admin_username: Optional[str] = None
    admin_password: Optional[str] = None
    admin_email: Optional[str] = None
    login_rate_limit_attempts: int = 5
    login_rate_limit_window_seconds: int = 60
    auth_token_rate_limit_attempts: int = 10
    auth_token_rate_limit_window_seconds: int = 60
    setup_rate_limit_attempts: int = 5
    setup_rate_limit_window_seconds: int = 60
    log_retention_days: int = 30
    web_session_retention_days: int = 30
    token_record_retention_days: int = 90
    session_cookie_name: str = "rcr_session"
    session_cookie_secure: bool = False
    session_lifetime_seconds: int = 28800

    def __post_init__(self) -> None:
        if self.app_env not in {"development", "production"}:
            raise ValueError("APP_ENV must be 'development' or 'production'.")
        if self.app_env == "production" and not self.session_cookie_secure:
            raise ValueError("SESSION_COOKIE_SECURE must be true when APP_ENV=production.")
        if self.app_env == "production" and self.public_registry_origin and not self.public_registry_origin.startswith("https://"):
            raise ValueError("PUBLIC_REGISTRY_ORIGIN must use https:// when APP_ENV=production.")
        if self.log_retention_days < 1:
            raise ValueError("LOG_RETENTION_DAYS must be at least 1.")
        if self.web_session_retention_days < 1:
            raise ValueError("WEB_SESSION_RETENTION_DAYS must be at least 1.")
        if self.token_record_retention_days < 1:
            raise ValueError("TOKEN_RECORD_RETENTION_DAYS must be at least 1.")
        if self.registry_catalog_max_pages < 1:
            raise ValueError("REGISTRY_CATALOG_MAX_PAGES must be at least 1.")
        if self.dashboard_max_repositories < 1:
            raise ValueError("DASHBOARD_MAX_REPOSITORIES must be at least 1.")
        if self.repository_tags_max_items < 1:
            raise ValueError("REPOSITORY_TAGS_MAX_ITEMS must be at least 1.")
        if self.manifest_children_max_items < 1:
            raise ValueError("MANIFEST_CHILDREN_MAX_ITEMS must be at least 1.")
        if self.history_entries_max_items < 1:
            raise ValueError("HISTORY_ENTRIES_MAX_ITEMS must be at least 1.")


def load_settings() -> Settings:
    return Settings(
        app_env=os.getenv("APP_ENV", "development").lower(),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./.local-data/app.db"),
        registry_internal_url=os.getenv("REGISTRY_INTERNAL_URL", "http://registry:5000"),
        registry_storage_root=os.getenv(
            "REGISTRY_STORAGE_ROOT",
            "/registry-data/docker/registry/v2/repositories",
        ),
        compose_project_dir=os.getenv("COMPOSE_PROJECT_DIR", "."),
        registry_service_name=os.getenv("REGISTRY_SERVICE_NAME", "registry"),
        registry_gc_config_path=os.getenv("REGISTRY_GC_CONFIG_PATH", "/etc/docker/registry/config.yml"),
        maintenance_min_gate_seconds=float(os.getenv("MAINTENANCE_MIN_GATE_SECONDS", "1.0")),
        token_issuer=os.getenv("TOKEN_ISSUER", "sheldylew-registry"),
        token_service=os.getenv("TOKEN_SERVICE", "sheldylew-registry"),
        token_ttl_seconds=int(os.getenv("TOKEN_TTL_SECONDS", "900")),
        public_registry_origin=os.getenv(
            "PUBLIC_REGISTRY_ORIGIN",
            "http://localhost:8080" if os.getenv("APP_ENV", "development").lower() == "development" else "",
        ).rstrip("/"),
        auth_private_key_path=os.getenv("AUTH_PRIVATE_KEY_PATH", ".local-data/auth/auth-private.pem"),
        auth_public_cert_path=os.getenv("AUTH_PUBLIC_CERT_PATH", ".local-data/auth/auth-cert.pem"),
        auth_bootstrap_marker_path=os.getenv(
            "AUTH_BOOTSTRAP_MARKER_PATH",
            ".local-data/auth/bootstrap-complete",
        ),
        setup_token_path=os.getenv("SETUP_TOKEN_PATH", ".local-data/setup-token.json"),
        setup_complete_marker_path=os.getenv("SETUP_COMPLETE_MARKER_PATH", ".local-data/setup-complete"),
        registry_notifications_token_path=os.getenv(
            "REGISTRY_NOTIFICATIONS_TOKEN_PATH",
            ".local-data/registry-events-token",
        ),
        registry_config_template_path=os.getenv("REGISTRY_CONFIG_TEMPLATE_PATH", "docker/registry-config.yml.tmpl"),
        registry_rendered_config_path=os.getenv("REGISTRY_RENDERED_CONFIG_PATH", ".local-data/registry-config.yml"),
        internal_api_base_url=os.getenv("INTERNAL_API_BASE_URL", "http://api:8000"),
        csrf_trusted_origins=_get_csv_env("CSRF_TRUSTED_ORIGINS"),
        admin_username=os.getenv("ADMIN_USERNAME"),
        admin_password=os.getenv("ADMIN_PASSWORD"),
        admin_email=os.getenv("ADMIN_EMAIL"),
        registry_catalog_max_pages=int(os.getenv("REGISTRY_CATALOG_MAX_PAGES", "10")),
        dashboard_max_repositories=int(os.getenv("DASHBOARD_MAX_REPOSITORIES", "50")),
        repository_tags_max_items=int(os.getenv("REPOSITORY_TAGS_MAX_ITEMS", "100")),
        manifest_children_max_items=int(os.getenv("MANIFEST_CHILDREN_MAX_ITEMS", "25")),
        history_entries_max_items=int(os.getenv("HISTORY_ENTRIES_MAX_ITEMS", "50")),
        login_rate_limit_attempts=int(os.getenv("LOGIN_RATE_LIMIT_ATTEMPTS", "5")),
        login_rate_limit_window_seconds=int(os.getenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "60")),
        auth_token_rate_limit_attempts=int(os.getenv("AUTH_TOKEN_RATE_LIMIT_ATTEMPTS", "10")),
        auth_token_rate_limit_window_seconds=int(os.getenv("AUTH_TOKEN_RATE_LIMIT_WINDOW_SECONDS", "60")),
        setup_rate_limit_attempts=int(os.getenv("SETUP_RATE_LIMIT_ATTEMPTS", "5")),
        setup_rate_limit_window_seconds=int(os.getenv("SETUP_RATE_LIMIT_WINDOW_SECONDS", "60")),
        log_retention_days=int(os.getenv("LOG_RETENTION_DAYS", "30")),
        web_session_retention_days=int(os.getenv("WEB_SESSION_RETENTION_DAYS", "30")),
        token_record_retention_days=int(os.getenv("TOKEN_RECORD_RETENTION_DAYS", "90")),
        session_cookie_secure=_get_bool_env("SESSION_COOKIE_SECURE", False),
        session_lifetime_seconds=int(os.getenv("SESSION_LIFETIME_SECONDS", "28800")),
    )


settings = load_settings()
