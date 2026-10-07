"""Public compatibility imports for OS file locks."""

from novelwb.utils.file_locks import FileLock, LockTimeoutError, lock_path

__all__ = ["FileLock", "LockTimeoutError", "lock_path"]
