"""Exclusive OS-backed file locks on Windows and POSIX."""

from contextlib import contextmanager
import errno
import os
from pathlib import Path
import time
from typing import Iterator


@contextmanager
def exclusive_file_lock(path: Path, *, blocking: bool = True) -> Iterator[None]:
    """Hold a process lock; the OS also releases it if the process crashes.

    Keep the lock file in place: deleting it on release could let two processes
    lock different files under the same pathname.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt

            # Windows locks a byte range, so make byte zero exist.
            if path.stat().st_size == 0:
                handle.write(b"\0")
                handle.flush()
            while True:
                handle.seek(0)
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as error:
                    if error.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise
                    if not blocking:
                        raise BlockingIOError(errno.EAGAIN, "file is already locked", str(path)) from error
                    time.sleep(0.1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
            fcntl.flock(handle.fileno(), flags)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
