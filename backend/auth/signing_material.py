import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from backend.config import Settings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _ensure_private_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)


def _write_bytes_with_mode(path: Path, data: bytes, mode: int) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, mode)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    os.chmod(path, mode)


def _validate_private_key_permissions(private_key_path: Path) -> None:
    file_mode = stat.S_IMODE(private_key_path.stat().st_mode)
    if file_mode & 0o077:
        raise RuntimeError(
            f"Signing key permissions are too broad on {private_key_path}; expected 0600."
        )


def _signing_paths(settings: Settings) -> tuple[Path, Path]:
    return Path(settings.auth_private_key_path), Path(settings.auth_public_cert_path)


def _bootstrap_marker_path(settings: Settings) -> Path:
    return Path(settings.auth_bootstrap_marker_path)


def _validate_signing_material(settings: Settings) -> None:
    private_key_path, public_cert_path = _signing_paths(settings)
    missing = []
    if not private_key_path.exists():
        missing.append(str(private_key_path))
    if not public_cert_path.exists():
        missing.append(str(public_cert_path))
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(f"Signing material is missing: {joined}")

    _validate_private_key_permissions(private_key_path)
    serialization.load_pem_private_key(private_key_path.read_bytes(), password=None)
    x509.load_pem_x509_certificate(public_cert_path.read_bytes())


def _write_bootstrap_marker(settings: Settings) -> None:
    marker_path = _bootstrap_marker_path(settings)
    _ensure_parent(marker_path)
    marker_path.write_text("initialized\n", encoding="utf-8")


def bootstrap_signing_material(settings: Settings) -> None:
    private_key_path, public_cert_path = _signing_paths(settings)
    marker_path = _bootstrap_marker_path(settings)
    has_private = private_key_path.exists()
    has_public = public_cert_path.exists()

    if marker_path.exists():
        _validate_signing_material(settings)
        return

    if has_private != has_public:
        raise RuntimeError("Signing material bootstrap is incomplete; expected both key and certificate.")

    if has_private and has_public:
        _validate_signing_material(settings)
        _write_bootstrap_marker(settings)
        return

    private_key_path = Path(settings.auth_private_key_path)
    public_cert_path = Path(settings.auth_public_cert_path)

    _ensure_private_parent(private_key_path)
    _ensure_parent(public_cert_path)

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "registry-control-plane-dev")]
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(_utcnow() - timedelta(minutes=1))
        .not_valid_after(_utcnow() + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(private_key, hashes.SHA256())
    )

    _write_bytes_with_mode(
        private_key_path,
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ),
        0o600,
    )
    _write_bytes_with_mode(public_cert_path, cert.public_bytes(serialization.Encoding.PEM), 0o644)
    _write_bootstrap_marker(settings)


def require_signing_material(settings: Settings) -> None:
    _validate_signing_material(settings)
