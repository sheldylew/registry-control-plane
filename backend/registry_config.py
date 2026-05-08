from backend.config import Settings


def render_registry_config(
    template: str,
    settings: Settings,
    *,
    public_registry_origin: str | None = None,
) -> str:
    return template.format(
        public_registry_origin=public_registry_origin or settings.public_registry_origin,
        token_service=settings.token_service,
        token_issuer=settings.token_issuer,
    )
