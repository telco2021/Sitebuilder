"""Upload storage confined to the site's directory, with content sniffing."""

from __future__ import annotations

import secrets
from pathlib import Path

from liquid.constants import UPLOAD_EXTENSIONS
from liquid.textutil import FormError

_MAGIC = {
    ".png": b"\x89PNG\r\n\x1a\n",
    ".jpg": b"\xff\xd8\xff",
    ".jpeg": b"\xff\xd8\xff",
    ".gif": b"GIF8",
    ".webp": b"RIFF",
    ".pdf": b"%PDF",
}


def sniff(suffix: str, payload: bytes) -> None:
    expected = _MAGIC[suffix]
    if not payload.startswith(expected):
        raise FormError("The file contents do not match its extension.")
    if suffix == ".webp" and b"WEBP" not in payload[8:16]:
        raise FormError("The file contents do not match its extension.")


def store_upload(upload_root: Path, site_id: int, filename: str, payload: bytes, limit: int) -> tuple[str, str, str]:
    if len(payload) == 0:
        raise FormError("Choose a file to upload.")
    if len(payload) > limit:
        raise FormError("That file is larger than the upload limit.")
    suffix = Path(filename or "").suffix.lower()
    if suffix not in UPLOAD_EXTENSIONS:
        raise FormError("Upload a PNG, JPEG, GIF, WebP, or PDF file.")
    sniff(suffix, payload)
    stored = f"{secrets.token_hex(16)}{suffix}"
    directory = (upload_root / str(site_id)).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    destination = (directory / stored).resolve()
    if not destination.is_relative_to(directory):
        raise FormError("The file could not be stored.")
    destination.write_bytes(payload)
    return stored, UPLOAD_EXTENSIONS[suffix], Path(filename).name[-180:]


def media_path(upload_root: Path, site_id: int, stored_name: str) -> Path:
    directory = (upload_root / str(site_id)).resolve()
    path = (directory / stored_name).resolve()
    if path.parent != directory or not path.is_file():
        raise FileNotFoundError(stored_name)
    return path
