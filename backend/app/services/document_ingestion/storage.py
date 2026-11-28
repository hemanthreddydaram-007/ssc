from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Protocol

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.models.document import StoredFile

logger = logging.getLogger(__name__)

_DB_CHUNK_BYTES = 4 * 1024 * 1024
_CHUNK_MANIFEST_PREFIX = b"__SSC_CHUNKED_BLOB_V1__:"


def _part_key(clean_key: str, idx: int) -> str:
    return f"{clean_key}__part_{idx:04d}"


def _part_prefix(clean_key: str) -> str:
    return f"{clean_key}__part_"


class StorageBackend(Protocol):
    """Abstract private file storage backend."""

    def save_from_path(self, storage_key: str, src_path: Path) -> None: ...

    def save_bytes(self, storage_key: str, data: bytes) -> None: ...

    def open_read(self, storage_key: str) -> BinaryIO: ...

    def ensure_local_file(self, storage_key: str) -> Path: ...

    def exists(self, storage_key: str) -> bool: ...

    def delete(self, storage_key: str) -> bool: ...

    def delete_prefix(self, prefix: str) -> bool: ...


class LocalPrivateStorage:
    """Private filesystem storage backed by optional PostgreSQL/DB blob persistence.

    Writing persists to both the local private directory and `stored_files` when a DB
    session/factory is attached, and reads transparently rehydrate missing local files
    after ephemeral container restarts (e.g. Render free tier).
    """

    def __init__(
        self,
        storage_root: Path,
        *,
        db: Session | None = None,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self.root = storage_root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        if session_factory is not None:
            self._session_factory: sessionmaker[Session] | None = session_factory
        elif db is not None:
            self._session_factory = sessionmaker(
                bind=db.get_bind(),
                autocommit=False,
                autoflush=False,
                expire_on_commit=False,
            )
        else:
            self._session_factory = None

    def _normalize_key(self, storage_key: str) -> str:
        if "\x00" in storage_key:
            raise ValueError("Storage key cannot contain null bytes")
        if storage_key.startswith("\\\\") or storage_key.startswith("//"):
            raise ValueError("UNC paths are not allowed as storage keys")
        normalized = storage_key.replace("\\", "/").lstrip("/")
        if not normalized:
            raise ValueError("Storage key cannot be empty")
        parts = [part for part in PurePosixPath(normalized).parts if part and part != "/"]
        if not parts:
            raise ValueError("Storage key cannot be empty")
        if any(part in {".", ".."} for part in parts):
            raise ValueError("Relative traversal segments are not allowed in storage keys")
        if ":" in parts[0]:
            raise ValueError("Drive-letter prefixes are not allowed in storage keys")
        return "/".join(parts)

    def _resolve_key(self, storage_key: str) -> Path:
        clean_key = self._normalize_key(storage_key)
        candidate = (self.root / Path(*clean_key.split("/"))).resolve()
        if not candidate.is_relative_to(self.root):
            raise ValueError("Invalid storage key escaping storage root")
        return candidate

    def _upsert_db_row(self, db: Session, key: str, data: bytes) -> None:
        existing = db.get(StoredFile, key)
        if existing is None:
            db.add(
                StoredFile(
                    storage_key=key,
                    content_bytes=data,
                    size_bytes=len(data),
                )
            )
        else:
            existing.content_bytes = data
            existing.size_bytes = len(data)

    def _save_db_blob(self, clean_key: str, data: bytes) -> None:
        if self._session_factory is None:
            return
        db = self._session_factory()
        try:
            db.execute(
                sa_delete(StoredFile).where(StoredFile.storage_key.startswith(_part_prefix(clean_key)))
            )
            self._upsert_db_row(db, clean_key, data)
            db.commit()
        finally:
            db.close()

    def _save_db_blob_from_path(self, clean_key: str, src_path: Path) -> None:
        """Persist file to DB, streaming 4 MB chunks for large files to prevent OOM."""
        if self._session_factory is None:
            return
        file_size = src_path.stat().st_size
        if file_size <= _DB_CHUNK_BYTES:
            self._save_db_blob(clean_key, src_path.read_bytes())
            return

        db = self._session_factory()
        try:
            db.execute(
                sa_delete(StoredFile).where(
                    (StoredFile.storage_key == clean_key)
                    | StoredFile.storage_key.startswith(_part_prefix(clean_key))
                )
            )
            db.commit()

            parts = 0
            with src_path.open("rb") as fh:
                while chunk := fh.read(_DB_CHUNK_BYTES):
                    self._upsert_db_row(db, _part_key(clean_key, parts), chunk)
                    db.commit()
                    parts += 1

            manifest_payload = _CHUNK_MANIFEST_PREFIX + json.dumps(
                {"parts": parts, "size": file_size}
            ).encode("utf-8")
            self._upsert_db_row(db, clean_key, manifest_payload)
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            logger.warning(
                "DB blob persistence skipped/failed for large key %s (%d bytes); local copy kept",
                clean_key,
                file_size,
                exc_info=True,
            )
        finally:
            db.close()

    def _fetch_db_blob_to_path(self, clean_key: str, target: Path) -> bool:
        """Rehydrate DB blob (single row or chunked manifest) directly to local disk."""
        if self._session_factory is None:
            return False
        db = self._session_factory()
        try:
            head = db.execute(
                select(StoredFile.content_bytes).where(StoredFile.storage_key == clean_key)
            ).scalar_one_or_none()
            if head is None:
                return False

            target.parent.mkdir(parents=True, exist_ok=True)
            if head.startswith(_CHUNK_MANIFEST_PREFIX):
                meta = json.loads(head[len(_CHUNK_MANIFEST_PREFIX) :].decode("utf-8"))
                parts = int(meta.get("parts", 0))
                with target.open("wb") as out:
                    for idx in range(parts):
                        chunk = db.execute(
                            select(StoredFile.content_bytes).where(
                                StoredFile.storage_key == _part_key(clean_key, idx)
                            )
                        ).scalar_one_or_none()
                        if chunk is None:
                            target.unlink(missing_ok=True)
                            return False
                        out.write(chunk)
                return True

            target.write_bytes(head)
            return True
        finally:
            db.close()

    def _db_blob_exists(self, clean_key: str) -> bool:
        if self._session_factory is None:
            return False
        db = self._session_factory()
        try:
            return (
                db.execute(
                    select(StoredFile.storage_key).where(StoredFile.storage_key == clean_key)
                ).scalar_one_or_none()
                is not None
            )
        finally:
            db.close()

    def _delete_db_key(self, clean_key: str) -> bool:
        if self._session_factory is None:
            return False
        db = self._session_factory()
        try:
            res = db.execute(
                sa_delete(StoredFile).where(
                    (StoredFile.storage_key == clean_key)
                    | StoredFile.storage_key.startswith(_part_prefix(clean_key))
                )
            )
            db.commit()
            return bool(res.rowcount and res.rowcount > 0)
        finally:
            db.close()

    def _delete_db_prefix(self, clean_prefix: str) -> bool:
        if self._session_factory is None:
            return False
        db = self._session_factory()
        try:
            prefix_slash = f"{clean_prefix.rstrip('/')}/"
            res = db.execute(
                sa_delete(StoredFile).where(
                    (StoredFile.storage_key == clean_prefix)
                    | StoredFile.storage_key.startswith(prefix_slash)
                )
            )
            db.commit()
            return bool(res.rowcount and res.rowcount > 0)
        finally:
            db.close()

    def save_from_path(self, storage_key: str, src_path: Path) -> None:
        clean_key = self._normalize_key(storage_key)
        dest = self._resolve_key(storage_key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src_path, dest)
        if self._session_factory is not None:
            self._save_db_blob_from_path(clean_key, src_path)

    def save_bytes(self, storage_key: str, data: bytes) -> None:
        clean_key = self._normalize_key(storage_key)
        dest = self._resolve_key(storage_key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        if self._session_factory is not None:
            self._save_db_blob(clean_key, data)

    def ensure_local_file(self, storage_key: str) -> Path:
        clean_key = self._normalize_key(storage_key)
        target = self._resolve_key(storage_key)
        if target.is_file():
            return target
        if not self._fetch_db_blob_to_path(clean_key, target):
            raise FileNotFoundError(f"Stored file not found: {clean_key}")
        return target

    def open_read(self, storage_key: str) -> BinaryIO:
        target = self.ensure_local_file(storage_key)
        return target.open("rb")

    def exists(self, storage_key: str) -> bool:
        clean_key = self._normalize_key(storage_key)
        target = self._resolve_key(storage_key)
        if target.is_file():
            return True
        return self._db_blob_exists(clean_key)

    def delete(self, storage_key: str) -> bool:
        clean_key = self._normalize_key(storage_key)
        target = self._resolve_key(storage_key)
        removed_local = False
        if target.is_file():
            target.unlink()
            removed_local = True
        removed_db = self._delete_db_key(clean_key)
        return removed_local or removed_db

    def delete_prefix(self, prefix: str) -> bool:
        clean_prefix = self._normalize_key(prefix)
        target = self._resolve_key(prefix)
        removed_local = False
        if target.is_dir():
            shutil.rmtree(target)
            removed_local = True
        elif target.is_file():
            target.unlink()
            removed_local = True
        removed_db = self._delete_db_prefix(clean_prefix)
        return removed_local or removed_db
