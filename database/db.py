"""SQLite access layer (no Kivy imports)."""
from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Iterable

APP_DIR_NAME = "debt_manager_pro"
DB_FILE_NAME = "debt_manager.db"
ENV_DB_PATH = "DEBT_MANAGER_DB"


def default_db_path(base_dir: str | None = None) -> str:
    """Resolve the database file path.

    Priority: ``DEBT_MANAGER_DB`` environment variable -> explicit ``base_dir``
    (Kivy's ``App.user_data_dir`` on Android) -> ``ANDROID_PRIVATE`` -> user
    home directory for desktop runs.
    """
    override = os.environ.get(ENV_DB_PATH)
    if override:
        return os.path.abspath(os.path.expanduser(override))
    if base_dir:
        folder = os.path.abspath(os.path.expanduser(base_dir))
    else:
        folder = os.environ.get("ANDROID_PRIVATE") or os.path.join(
            os.path.expanduser("~"), f".{APP_DIR_NAME}"
        )
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, DB_FILE_NAME)


class Database:
    """Thin, thread-local SQLite wrapper with explicit transactions.

    * ``PRAGMA foreign_keys=ON`` on every connection (SQLite defaults to OFF).
    * WAL journaling for file databases (better crash safety on Android).
    * ``isolation_level=None`` so transactions are explicit; every write goes
      through :meth:`transaction` which uses ``BEGIN IMMEDIATE``.
    """

    def __init__(self, path: str | None = None):
        self.path = path or default_db_path()
        self._local = threading.local()
        self._connections: list[sqlite3.Connection] = []
        self._lock = threading.Lock()
        self._closed = False

    # -- connections -----------------------------------------------------
    @property
    def connection(self) -> sqlite3.Connection:
        if self._closed:
            raise RuntimeError("database is closed")
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._create_connection()
        return conn

    def _create_connection(self) -> sqlite3.Connection:
        if self.path != ":memory:":
            directory = os.path.dirname(os.path.abspath(self.path))
            if directory:
                os.makedirs(directory, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        if self.path != ":memory:":
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
        self._local.conn = conn
        with self._lock:
            self._connections.append(conn)
        return conn

    def connect(self) -> sqlite3.Connection:
        return self.connection

    # -- helpers ---------------------------------------------------------
    def execute(self, sql: str, params: Iterable = ()) -> sqlite3.Cursor:
        return self.connection.execute(sql, tuple(params))

    def query(self, sql: str, params: Iterable = ()) -> list[sqlite3.Row]:
        return list(self.connection.execute(sql, tuple(params)).fetchall())

    def query_one(self, sql: str, params: Iterable = ()):
        return self.connection.execute(sql, tuple(params)).fetchone()

    @contextmanager
    def transaction(self):
        """Atomic write transaction; nested calls use SAVEPOINTs."""
        conn = self.connection
        if conn.in_transaction:
            conn.execute("SAVEPOINT nested_tx")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK TO nested_tx")
                conn.execute("RELEASE nested_tx")
                raise
            else:
                conn.execute("RELEASE nested_tx")
            return
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        else:
            conn.execute("COMMIT")

    def close(self) -> None:
        with self._lock:
            connections = list(self._connections)
            self._connections.clear()
        for conn in connections:
            try:
                conn.close()
            except sqlite3.Error:
                pass
        self._local = threading.local()
        self._closed = True

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def integrity_check(db: Database) -> str:
    row = db.query_one("PRAGMA integrity_check")
    return row[0] if row else "unknown"
