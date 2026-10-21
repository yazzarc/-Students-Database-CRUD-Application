"""Small SQLite repository. User values are always bound parameters."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .schemas import StudentCreate

STUDENT_FIELDS = tuple(StudentCreate.model_fields)
SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    student_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL CHECK(length(trim(name)) BETWEEN 2 AND 100),
    date_of_birth TEXT NOT NULL,
    email TEXT COLLATE NOCASE UNIQUE,
    phone TEXT,
    course TEXT COLLATE NOCASE,
    address TEXT,
    enrollment_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (email IS NOT NULL OR phone IS NOT NULL),
    CHECK (enrollment_date >= date_of_birth)
);
CREATE INDEX IF NOT EXISTS idx_students_course ON students(course);
CREATE INDEX IF NOT EXISTS idx_students_birth ON students(date_of_birth);
"""


class StudentNotFound(Exception):
    pass


class DuplicateEmail(Exception):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)

    @contextmanager
    def connection(self):
        # Open, use and close in the same worker thread. Never share connections.
        conn = sqlite3.connect(str(self.path), timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)

    def health(self):
        with self.connection() as conn:
            conn.execute("SELECT 1 FROM students LIMIT 1").fetchone()

    @staticmethod
    def _fetch(conn, student_id: int) -> dict:
        row = conn.execute("SELECT * FROM students WHERE student_id = ?", (student_id,)).fetchone()
        if row is None:
            raise StudentNotFound
        return dict(row)

    def get(self, student_id: int) -> dict:
        with self.connection() as conn:
            return self._fetch(conn, student_id)

    def create(self, student: StudentCreate) -> dict:
        data = student.model_dump(mode="json")
        now = utc_now()
        try:
            with self.connection() as conn:
                cursor = conn.execute(
                    "INSERT INTO students (name, date_of_birth, email, phone, course, address, enrollment_date, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    tuple(data[key] for key in STUDENT_FIELDS) + (now, now),
                )
                return self._fetch(conn, cursor.lastrowid)
        except sqlite3.IntegrityError as exc:
            if "students.email" in str(exc):
                raise DuplicateEmail from exc
            raise

    def update(self, student_id: int, changes: dict, *, replace: bool = False) -> dict:
        try:
            with self.connection() as conn:
                # Serialize read-merge-write so concurrent PATCHes cannot overwrite
                # unrelated fields from a stale record.
                conn.execute("BEGIN IMMEDIATE")
                current = self._fetch(conn, student_id)
                merged = changes if replace else {**{key: current[key] for key in STUDENT_FIELDS}, **changes}
                valid = StudentCreate.model_validate(merged).model_dump(mode="json")
                conn.execute(
                    "UPDATE students SET name=?, date_of_birth=?, email=?, phone=?, course=?, address=?, "
                    "enrollment_date=?, updated_at=? WHERE student_id=?",
                    tuple(valid[key] for key in STUDENT_FIELDS) + (utc_now(), student_id),
                )
                return self._fetch(conn, student_id)
        except sqlite3.IntegrityError as exc:
            if "students.email" in str(exc):
                raise DuplicateEmail from exc
            raise

    def delete(self, student_id: int):
        with self.connection() as conn:
            result = conn.execute("DELETE FROM students WHERE student_id=?", (student_id,))
            if result.rowcount == 0:
                raise StudentNotFound

    def list(self, *, name=None, course=None, email=None, born_after=None, born_before=None, limit=20, offset=0) -> dict:
        clauses, params = [], []
        if name is not None:
            # instr treats %, _ and quotes literally; no wildcard surprises.
            clauses.append("instr(lower(name), lower(?)) > 0")
            params.append(name)
        if course is not None:
            clauses.append("course = ? COLLATE NOCASE")
            params.append(course)
        if email is not None:
            clauses.append("email = ? COLLATE NOCASE")
            params.append(str(email))
        if born_after is not None:
            clauses.append("date_of_birth > ?")
            params.append(str(born_after))
        if born_before is not None:
            clauses.append("date_of_birth < ?")
            params.append(str(born_before))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.connection() as conn:
            # Count and page use one consistent read snapshot.
            conn.execute("BEGIN")
            total = conn.execute("SELECT COUNT(*) FROM students" + where, params).fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM students" + where + " ORDER BY student_id ASC LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
            return {"total": total, "limit": limit, "offset": offset, "items": [dict(row) for row in rows]}
