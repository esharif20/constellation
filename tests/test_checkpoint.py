import stat

from constellation.checkpoint import open_checkpointer


def _mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def test_the_file_is_0600_in_a_0700_directory_even_when_the_directory_already_existed(tmp_path):
    folder = tmp_path / "cache"
    folder.mkdir(mode=0o755)
    folder.chmod(0o755)
    db = folder / "x.sqlite"
    db.write_text("")
    db.chmod(0o644)

    open_checkpointer(db).conn.close()

    assert (_mode(folder), _mode(db)) == (0o700, 0o600)


def test_missing_parents_are_created_private(tmp_path):
    db = tmp_path / "a" / "b" / "x.sqlite"
    open_checkpointer(db).conn.close()
    assert (_mode(db.parent), _mode(db)) == (0o700, 0o600)


def test_deleted_rows_are_overwritten(tmp_path):
    saver = open_checkpointer(tmp_path / "x.sqlite")
    assert saver.conn.execute("PRAGMA secure_delete").fetchone() == (1,)
    saver.conn.close()
