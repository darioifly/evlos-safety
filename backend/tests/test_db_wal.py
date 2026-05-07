"""F-012: WAL mode + busy_timeout + persistent read connection."""
import sqlite3
import threading
import time

import pytest

from database.db_manager import DatabaseManager


@pytest.fixture
def tmp_db(tmp_path):
    db_path = tmp_path / "test.db"
    return DatabaseManager(db_path=str(db_path))


def test_wal_mode_enabled(tmp_db):
    conn = sqlite3.connect(tmp_db.db_path)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"


def test_busy_timeout_set(tmp_db):
    conn = tmp_db.get_connection()
    try:
        timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        assert timeout >= 5000
    finally:
        conn.close()


def test_concurrent_read_during_write_does_not_lock(tmp_db):
    """In rollback-journal mode this would raise 'database is locked'.
    With WAL it must succeed within the busy_timeout."""
    w = tmp_db.get_connection()
    w.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY, v INTEGER)")
    w.execute("INSERT INTO t (v) VALUES (1)")
    w.commit()
    w.close()

    errors = []

    def writer():
        try:
            c = tmp_db.get_connection()
            c.execute("BEGIN IMMEDIATE")
            c.execute("INSERT INTO t (v) VALUES (2)")
            time.sleep(0.5)
            c.commit()
            c.close()
        except Exception as e:
            errors.append(("writer", repr(e)))

    def reader():
        try:
            time.sleep(0.1)
            c = tmp_db.get_connection()
            rows = c.execute("SELECT COUNT(*) FROM t").fetchone()
            c.close()
            assert rows[0] >= 1
        except Exception as e:
            errors.append(("reader", repr(e)))

    tw = threading.Thread(target=writer)
    tr = threading.Thread(target=reader)
    tw.start(); tr.start()
    tw.join(); tr.join()

    assert errors == [], f"WAL test failed: {errors}"


def test_close_releases_persistent_connection(tmp_db):
    """db.close() must not raise and must allow re-use of get_connection()."""
    tmp_db.close()
    # Subsequent one-shot connections should still work.
    c = tmp_db.get_connection()
    assert c.execute("SELECT 1").fetchone()[0] == 1
    c.close()
