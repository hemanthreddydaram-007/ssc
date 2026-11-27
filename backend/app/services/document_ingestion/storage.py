from __future__ import annotations

import shutil
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Protocol


class StorageBackend(Protocol):
    """Abstract private file storage backend."""

    def save_from_path(self, storage_key: str, src_path: Path) -> None: ...

    def save_bytes(self, storage_key: str, data: bytes) -> None: ...

    def open_read(self, storage_key: str) -> BinaryIO: ...

    def exists(self, storage_key: str) -> bool: ...

    def delete(self, storage_key: str) -> bool: ...

    def delete_prefix(self, prefix: str) -> bool: ...


class LocalPrivateStorage:
    """Local filesystem storage outside the public web root with traversal guards."""

    def __init__(self, storage_root: Path) -> None:
        self.root = storage_root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve_key(self, storage_key: str) -> Path:
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
        candidate = (self.root / Path(*parts)).resolve()
        if not candidate.is_relative_to(self.root):
            raise ValueError("Invalid storage key escaping storage root")
        return candidate

    def save_from_path(self, storage_key: str, src_path: Path) -> None:
        dest = self._resolve_key(storage_key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src_path, dest)

    def save_bytes(self, storage_key: str, data: bytes) -> None:
        dest = self._resolve_key(storage_key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

    def open_read(self, storage_key: str) -> BinaryIO:
        target = self._resolve_key(storage_key)
        return target.open("rb")

    def exists(self, storage_key: str) -> bool:
        target = self._resolve_key(storage_key)
        return target.is_file()

    def delete(self, storage_key: str) -> bool:
        target = self._resolve_key(storage_key)
        if target.is_file():
            target.unlink()
            return True
        return False

    def delete_prefix(self, prefix: str) -> bool:
        target = self._resolve_key(prefix)
        if target.is_dir():
            shutil.rmtree(target)
            return True
        if target.is_file():
            target.unlink()
            return True
        return False
