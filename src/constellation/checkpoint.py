"""The one place a LangGraph checkpoint file is opened (shared by `review` and the scan graph)."""

import fcntl
import os
import sqlite3
from pathlib import Path

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

SECURE_DELETE = "PRAGMA secure_delete=ON"  # pragma: no mutate  (SQL is case-insensitive)
PRIVATE_NOFOLLOW = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW  # a symlink in the way is refused, never followed


class Checkpointer(SqliteSaver):
    lock_fd: int | None = None


def _private(path: Path) -> int:
    fd = os.open(path, PRIVATE_NOFOLLOW, 0o600)  # pragma: no mutate  (chmod by the caller)
    os.fchmod(fd, 0o600)
    return fd


def open_checkpointer(path: Path, state_types: tuple[tuple[str, str], ...] = (), lock: bool = False) -> Checkpointer:
    """A SqliteSaver on `path`: file 0600 in a 0700 directory, deleted rows overwritten.
    A checkpointer saves the graph's State after every step; SQLite is the file it is saved in.
    Reading a checkpoint rebuilds Python objects, so only built-in types plus `state_types` (module, class) may be rebuilt:
    a planted or foreign file cannot make us construct anything else.
    `lock`: take an exclusive non-blocking flock on `<path>.lock`, so only one scan at a time uses the file; if another holds it,
    BlockingIOError (an OSError) is raised. Release with close_checkpointer."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)  # pragma: no mutate  (the chmod below sets it anyway; this closes the gap)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:  # a directory we do not own: the file inside is still 0600
        pass
    lock_fd = None
    if lock:
        lock_fd = _private(path.with_name(path.name + ".lock"))
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(lock_fd)
            raise
    try:
        os.close(_private(path))
        connection = sqlite3.connect(path, check_same_thread=False)  # pragma: no mutate  (equivalent: None is falsy)
        connection.execute(SECURE_DELETE)  # a finished scan's rows must not linger in free pages
    except BaseException:
        if lock_fd is not None:
            os.close(lock_fd)
        raise
    saver = Checkpointer(connection, serde=JsonPlusSerializer(allowed_msgpack_modules=list(state_types)))
    saver.lock_fd = lock_fd
    return saver


def close_checkpointer(saver: Checkpointer) -> None:
    saver.conn.close()
    if saver.lock_fd is not None:
        os.close(saver.lock_fd)  # closing the descriptor releases the flock
