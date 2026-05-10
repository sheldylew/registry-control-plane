from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import parse_qs, urlparse

import httpx

from backend.auth.registry_tokens import encode_registry_token
from backend.config import Settings

MANIFEST_ACCEPT = ", ".join(
    [
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    ]
)


class RegistryClientError(Exception):
    pass


class RegistryNotFoundError(RegistryClientError):
    pass


@dataclass(frozen=True)
class ManifestDetails:
    name: str
    tag: str
    digest: Optional[str]
    media_type: Optional[str]
    config_digest: Optional[str]
    config_media_type: Optional[str]
    layers: list[dict]
    total_size: int
    architectures: list[str]
    created_at: Optional[str]
    history_count: Optional[int]
    children_truncated: bool = False
    history_truncated: bool = False


@dataclass(frozen=True)
class TagSummary:
    tag: str
    digest: Optional[str]
    media_type: Optional[str]
    total_size: int
    architectures: list[str]
    created_at: Optional[str]
    history_count: Optional[int]
    children_truncated: bool = False
    history_truncated: bool = False


@dataclass(frozen=True)
class HistoryVariant:
    platform: Optional[str]
    manifest_digest: Optional[str]
    config_digest: Optional[str]
    created_at: Optional[str]
    entries: list[dict]
    history_truncated: bool = False


def _build_internal_auth_header(settings: Settings, scopes: list[dict]) -> str:
    token, _issued_at = encode_registry_token(
        settings,
        subject_name="registry-control-plane",
        service=settings.token_service,
        access_entries=scopes,
    )
    return f"Bearer {token}"


def _next_last_from_link(link_header: Optional[str]) -> Optional[str]:
    if not link_header:
        return None

    raw_target, _separator, raw_meta = link_header.partition(";")
    if 'rel="next"' not in raw_meta:
        return None
    target = raw_target.strip().strip("<>")
    if not target:
        return None

    query = parse_qs(urlparse(target).query)
    values = query.get("last")
    if not values:
        return None
    return values[0]


def _parse_created_at(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).astimezone(timezone.utc)
    except ValueError:
        return None


def _format_platform_label(os_name: Optional[str], architecture: Optional[str]) -> Optional[str]:
    parts = [os_name, architecture]
    resolved = "/".join(part for part in parts if part)
    return resolved or None


class RegistryClient:
    def __init__(
        self,
        *,
        settings: Settings,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self._settings = settings
        self._client = httpx.Client(
            base_url=settings.registry_internal_url.rstrip("/"),
            transport=transport,
            timeout=10.0,
        )

    def close(self) -> None:
        self._client.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        scopes: list[dict],
        params: Optional[dict] = None,
        headers: Optional[dict] = None,
    ) -> httpx.Response:
        request_headers = {
            "Authorization": _build_internal_auth_header(self._settings, scopes),
        }
        if headers:
            request_headers.update(headers)

        response = self._client.request(method, path, params=params, headers=request_headers)
        if response.status_code == 404:
            raise RegistryNotFoundError(path)
        response.raise_for_status()
        return response

    def list_repositories(self) -> list[str]:
        repositories, _meta = self.list_repositories_bounded()
        return repositories

    def list_tags(self, repository_name: str) -> list[str]:
        response = self._request(
            "GET",
            f"/v2/{repository_name}/tags/list",
            scopes=[{"type": "repository", "name": repository_name, "actions": ["pull"]}],
        )
        payload = response.json()
        tags = payload.get("tags") or []
        return sorted(tags)

    def delete_manifest(self, repository_name: str, digest: str) -> None:
        response = self._request(
            "DELETE",
            f"/v2/{repository_name}/manifests/{digest}",
            scopes=[{"type": "repository", "name": repository_name, "actions": ["delete"]}],
        )
        if response.status_code not in {202, 200}:
            response.raise_for_status()

    def _read_blob_json(self, repository_name: str, digest: str) -> dict:
        response = self._request(
            "GET",
            f"/v2/{repository_name}/blobs/{digest}",
            scopes=[{"type": "repository", "name": repository_name, "actions": ["pull"]}],
        )
        return response.json()

    def _read_manifest_json(self, repository_name: str, reference: str) -> dict:
        response = self._request(
            "GET",
            f"/v2/{repository_name}/manifests/{reference}",
            scopes=[{"type": "repository", "name": repository_name, "actions": ["pull"]}],
            headers={"Accept": MANIFEST_ACCEPT},
        )
        return response.json()

    def _extract_platform(self, manifest_entry: dict) -> Optional[str]:
        platform = manifest_entry.get("platform") or {}
        return _format_platform_label(platform.get("os"), platform.get("architecture"))

    def _variant_from_manifest(
        self,
        repository_name: str,
        *,
        manifest_payload: dict,
        manifest_digest: Optional[str],
        platform: Optional[str],
        max_history_entries: Optional[int] = None,
    ) -> HistoryVariant:
        config = manifest_payload.get("config") or {}
        config_digest = config.get("digest")
        entries: list[dict] = []
        created_at: Optional[str] = None
        resolved_platform = platform
        if config_digest:
            config_payload = self._read_blob_json(repository_name, config_digest)
            created_at = config_payload.get("created")
            history_entries = config_payload.get("history") or []
            history_truncated = max_history_entries is not None and len(history_entries) > max_history_entries
            entries = history_entries[:max_history_entries] if max_history_entries is not None else history_entries
            if resolved_platform is None:
                resolved_platform = _format_platform_label(
                    config_payload.get("os"),
                    config_payload.get("architecture"),
                )
        else:
            history_truncated = False
        return HistoryVariant(
            platform=resolved_platform,
            manifest_digest=manifest_digest,
            config_digest=config_digest,
            created_at=created_at,
            entries=entries,
            history_truncated=history_truncated,
        )

    def get_manifest_details(
        self,
        repository_name: str,
        reference: str,
        *,
        max_manifest_children: Optional[int] = None,
        max_history_entries: Optional[int] = None,
    ) -> ManifestDetails:
        headers = {"Accept": MANIFEST_ACCEPT}
        scopes = [{"type": "repository", "name": repository_name, "actions": ["pull"]}]
        head = self._request(
            "HEAD",
            f"/v2/{repository_name}/manifests/{reference}",
            scopes=scopes,
            headers=headers,
        )
        manifest_response = self._request(
            "GET",
            f"/v2/{repository_name}/manifests/{reference}",
            scopes=scopes,
            headers=headers,
        )
        payload = manifest_response.json()
        media_type = head.headers.get("Content-Type") or payload.get("mediaType")
        layers = payload.get("layers") or []
        manifests = payload.get("manifests") or []
        config = payload.get("config") or {}
        config_size = config.get("size") or 0
        architectures: list[str] = []
        created_at: Optional[str] = None
        history_count: Optional[int] = None

        if manifests:
            children_truncated = max_manifest_children is not None and len(manifests) > max_manifest_children
            manifests_to_inspect = manifests[:max_manifest_children] if max_manifest_children is not None else manifests
            total_size = sum(entry.get("size") or 0 for entry in manifests)
            child_created_times: list[datetime] = []
            resolved_architectures: set[str] = set()
            for entry in manifests_to_inspect:
                child_digest = entry.get("digest")
                if not child_digest:
                    continue
                try:
                    child_manifest = self._read_manifest_json(repository_name, child_digest)
                except RegistryNotFoundError:
                    continue
                child_config = child_manifest.get("config") or {}
                child_config_digest = child_config.get("digest")
                if not child_config_digest:
                    continue
                try:
                    child_config_payload = self._read_blob_json(repository_name, child_config_digest)
                except RegistryNotFoundError:
                    continue
                platform_label = self._extract_platform(entry) or _format_platform_label(
                    child_config_payload.get("os"),
                    child_config_payload.get("architecture"),
                )
                if platform_label:
                    resolved_architectures.add(platform_label)
                child_created = _parse_created_at(child_config_payload.get("created"))
                if child_created is not None:
                    child_created_times.append(child_created)
            architectures = sorted(resolved_architectures)
            if child_created_times:
                created_at = min(child_created_times).isoformat().replace("+00:00", "Z")
            history_truncated = False
        else:
            children_truncated = False
            total_size = config_size + sum(layer.get("size") or 0 for layer in layers)
            if config.get("digest"):
                config_payload = self._read_blob_json(repository_name, config["digest"])
                architecture = config_payload.get("architecture")
                os_name = config_payload.get("os")
                if architecture or os_name:
                    architectures = ["/".join(part for part in [os_name, architecture] if part)]
                created_at = config_payload.get("created")
                history = config_payload.get("history") or []
                history_count = len(history)
                history_truncated = max_history_entries is not None and len(history) > max_history_entries
            else:
                history_truncated = False

        return ManifestDetails(
            name=repository_name,
            tag=reference,
            digest=head.headers.get("Docker-Content-Digest"),
            media_type=media_type,
            config_digest=config.get("digest"),
            config_media_type=config.get("mediaType"),
            layers=layers,
            total_size=total_size,
            architectures=architectures,
            created_at=created_at,
            history_count=history_count,
            children_truncated=children_truncated,
            history_truncated=history_truncated,
        )

    def list_tag_summaries(self, repository_name: str) -> list[TagSummary]:
        summaries, _meta = self.list_tag_summaries_bounded(repository_name)
        return summaries

    def list_tag_summaries_for_tags(
        self,
        repository_name: str,
        tags: list[str],
        *,
        max_manifest_children: Optional[int] = None,
        max_history_entries: Optional[int] = None,
    ) -> list[TagSummary]:
        summaries: list[TagSummary] = []
        for tag in tags:
            try:
                details = self.get_manifest_details(
                    repository_name,
                    tag,
                    max_manifest_children=max_manifest_children,
                    max_history_entries=max_history_entries,
                )
            except RegistryNotFoundError:
                continue
            summaries.append(
                TagSummary(
                    tag=tag,
                    digest=details.digest,
                    media_type=details.media_type,
                    total_size=details.total_size,
                    architectures=details.architectures,
                    created_at=details.created_at,
                    history_count=details.history_count,
                    children_truncated=details.children_truncated,
                    history_truncated=details.history_truncated,
                )
            )
        return summaries

    def list_tag_summaries_bounded(
        self,
        repository_name: str,
        *,
        max_tags: Optional[int] = None,
        max_manifest_children: Optional[int] = None,
        max_history_entries: Optional[int] = None,
    ) -> tuple[list[TagSummary], dict]:
        tags = self.list_tags(repository_name)
        limited_tags = tags[:max_tags] if max_tags is not None else tags
        summaries = self.list_tag_summaries_for_tags(
            repository_name,
            limited_tags,
            max_manifest_children=max_manifest_children,
            max_history_entries=max_history_entries,
        )
        return summaries, {
            "truncated": max_tags is not None and len(tags) > max_tags,
            "returned": len(summaries),
            "available": len(tags),
        }

    def get_tag_history(self, repository_name: str, reference: str) -> list[HistoryVariant]:
        variants, _meta = self.get_tag_history_bounded(repository_name, reference)
        return variants

    def list_repositories_bounded(
        self,
        *,
        max_pages: Optional[int] = None,
    ) -> tuple[list[str], dict]:
        repositories: list[str] = []
        next_last: Optional[str] = None
        pages_fetched = 0

        while True:
            if max_pages is not None and pages_fetched >= max_pages:
                break
            params = {"n": 100}
            if next_last:
                params["last"] = next_last
            response = self._request(
                "GET",
                "/v2/_catalog",
                scopes=[{"type": "registry", "name": "catalog", "actions": ["*"]}],
                params=params,
            )
            pages_fetched += 1
            payload = response.json()
            repositories.extend(payload.get("repositories", []))
            next_last = _next_last_from_link(response.headers.get("Link"))
            if not next_last:
                break

        return sorted(set(repositories)), {
            "truncated": next_last is not None,
            "pages_fetched": pages_fetched,
        }

    def get_tag_history_bounded(
        self,
        repository_name: str,
        reference: str,
        *,
        max_manifest_children: Optional[int] = None,
        max_history_entries: Optional[int] = None,
    ) -> tuple[list[HistoryVariant], dict]:
        manifest_payload = self._read_manifest_json(repository_name, reference)
        manifests = manifest_payload.get("manifests") or []
        if manifests:
            manifests_to_inspect = manifests[:max_manifest_children] if max_manifest_children is not None else manifests
            variants: list[HistoryVariant] = []
            for entry in manifests_to_inspect:
                child_digest = entry.get("digest")
                if not child_digest:
                    continue
                try:
                    child_manifest = self._read_manifest_json(repository_name, child_digest)
                except RegistryNotFoundError:
                    continue
                variants.append(
                    self._variant_from_manifest(
                        repository_name,
                        manifest_payload=child_manifest,
                        manifest_digest=child_digest,
                        platform=self._extract_platform(entry),
                        max_history_entries=max_history_entries,
                    )
                )
            return variants, {
                "truncated": max_manifest_children is not None and len(manifests) > max_manifest_children,
                "returned": len(variants),
                "available": len(manifests),
            }

        return [
            self._variant_from_manifest(
                repository_name,
                manifest_payload=manifest_payload,
                manifest_digest=None,
                platform=None,
                max_history_entries=max_history_entries,
            )
        ], {
            "truncated": False,
            "returned": 1,
            "available": 1,
        }
