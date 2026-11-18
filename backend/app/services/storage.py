"""File storage abstraction: local disk or AWS S3. All downloads go through authorized API routes."""
import mimetypes
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import StoredFile, User

ALLOWED_TYPES = {
    "application/pdf", "image/png", "image/jpeg", "image/webp", "image/gif",
    "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint", "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain", "text/csv", "application/zip",
}
IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}

# magic-byte signatures to stop content-type spoofing
_SIGNATURES = {
    "application/pdf": [b"%PDF"],
    "image/png": [b"\x89PNG"],
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/gif": [b"GIF8"],
    "image/webp": [b"RIFF"],
}


class Storage:
    def save(self, key: str, data: bytes, content_type: str) -> None: ...
    def load(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


class LocalStorage(Storage):
    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root not in p.parents:
            raise HTTPException(400, "Invalid storage key")
        return p

    def save(self, key, data, content_type):
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def load(self, key):
        p = self._path(key)
        if not p.exists():
            raise HTTPException(404, "File content missing from storage")
        return p.read_bytes()

    def delete(self, key):
        p = self._path(key)
        if p.exists():
            p.unlink()


class S3Storage(Storage):
    def __init__(self):
        import boto3

        if not settings.AWS_S3_BUCKET:
            raise RuntimeError("AWS_S3_BUCKET is not configured")
        self.bucket = settings.AWS_S3_BUCKET
        self.client = boto3.client(
            "s3", region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
        )

    def save(self, key, data, content_type):
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type,
                               ServerSideEncryption="AES256")

    def load(self, key):
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def delete(self, key):
        self.client.delete_object(Bucket=self.bucket, Key=key)


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        _storage = S3Storage() if settings.STORAGE_BACKEND == "s3" else LocalStorage(settings.LOCAL_STORAGE_PATH)
    return _storage


def _detect_type(filename: str, declared: str | None) -> str:
    guessed = mimetypes.guess_type(filename)[0]
    return guessed or declared or "application/octet-stream"


def store_bytes(db: Session, data: bytes, filename: str, content_type: str, user: User | None,
                entity_type: str | None = None, entity_id: int | None = None, category: str | None = None,
                description: str | None = None) -> StoredFile:
    safe_name = Path(filename).name[:200] or "file"
    key = f"{entity_type or 'misc'}/{uuid.uuid4().hex}{Path(safe_name).suffix.lower()[:10]}"
    get_storage().save(key, data, content_type)
    f = StoredFile(storage_key=key, original_name=safe_name, content_type=content_type, size_bytes=len(data),
                   entity_type=entity_type, entity_id=entity_id, category=category, description=description,
                   uploaded_by_id=user.id if user else None)
    db.add(f)
    db.flush()
    return f


async def store_upload(db: Session, upload: UploadFile, user: User, entity_type: str, entity_id: int | None = None,
                       category: str | None = None, description: str | None = None,
                       allowed: set[str] | None = None) -> StoredFile:
    data = await upload.read()
    if not data:
        raise HTTPException(400, "Uploaded file is empty")
    if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"File exceeds {settings.MAX_UPLOAD_MB} MB limit")
    ctype = _detect_type(upload.filename or "", upload.content_type)
    if ctype not in (allowed or ALLOWED_TYPES):
        raise HTTPException(415, f"File type {ctype} is not allowed")
    sigs = _SIGNATURES.get(ctype)
    if sigs and not any(data.startswith(s) for s in sigs):
        raise HTTPException(415, "File content does not match its type")
    return store_bytes(db, data, upload.filename or "file", ctype, user, entity_type, entity_id, category, description)


def delete_file(db: Session, f: StoredFile) -> None:
    try:
        get_storage().delete(f.storage_key)
    finally:
        db.delete(f)
