"""The one place a LangGraph checkpoint file is opened (shared by `review` and the scan graph)."""

import os
import sqlite3
from pathlib import Path

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

SECURE_DELETE = "PRAGMA secure_delete=ON"  # pragma: no mutate  (SQL is case-insensitive)


def open_checkpointer(path: Path, state_types: tuple[tuple[str, str], ...] = ()) -> SqliteSaver:
    """A SqliteSaver on `path`: file 0600 in a 0700 directory, deleted rows overwritten.
    A checkpointer saves the graph's State after every step; SQLite is the file it is saved in.
    Reading a checkpoint rebuilds Python objects, so only built-in types plus `state_types` (module, class) may be rebuilt:
    a planted or foreign file cannot make us construct anything else."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)  # pragma: no mutate  (the chmod below sets it anyway; this closes the gap)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:  # a directory we do not own: the file inside is still 0600
        pass
    os.close(os.open(path, os.O_WRONLY | os.O_CREAT, 0o600))  # pragma: no mutate  (chmod below)
    os.chmod(path, 0o600)
    connection = sqlite3.connect(path, check_same_thread=False)  # pragma: no mutate  (equivalent: None is falsy)
    connection.execute(SECURE_DELETE)  # a finished scan's rows must not linger in free pages
    return SqliteSaver(connection, serde=JsonPlusSerializer(allowed_msgpack_modules=list(state_types)))
