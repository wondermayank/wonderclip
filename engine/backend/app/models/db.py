"""Tiny SQLite store. Thread-safe via a single lock (workload is one user, low QPS)."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS uploads (
    id          TEXT PRIMARY KEY,
    sha256      TEXT NOT NULL UNIQUE,
    filename    TEXT NOT NULL,
    ext         TEXT NOT NULL,
    size_bytes  INTEGER NOT NULL,
    video_json  TEXT NOT NULL,
    created_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id             TEXT PRIMARY KEY,
    upload_id      TEXT NOT NULL UNIQUE,      -- one job per upload: prevents duplicate jobs
    status         TEXT NOT NULL,             -- queued | <stage> | completed | failed | cancelled
    progress       REAL NOT NULL DEFAULT 0,   -- overall 0..1
    stage_progress REAL NOT NULL DEFAULT 0,   -- current stage 0..1
    live_text      TEXT NOT NULL DEFAULT '',  -- latest transcribed line, for the UI
    error_code     TEXT,
    error_message  TEXT,
    failed_stage   TEXT,
    attempts       INTEGER NOT NULL DEFAULT 0,
    cancel         INTEGER NOT NULL DEFAULT 0,
    created_at     REAL NOT NULL,
    updated_at     REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS clips (
    id              TEXT PRIMARY KEY,
    job_id          TEXT NOT NULL,
    idx             INTEGER NOT NULL,
    start_time      REAL NOT NULL,
    end_time        REAL NOT NULL,
    title           TEXT NOT NULL,
    hook            TEXT NOT NULL,
    reason          TEXT NOT NULL,
    editorial_score INTEGER NOT NULL,
    transcript      TEXT NOT NULL,
    source          TEXT NOT NULL,            -- 'ai' or 'fallback'
    duration        REAL NOT NULL,            -- verified by ffprobe
    layout          TEXT NOT NULL DEFAULT 'original',  -- track | native | fit | original (Phase 2)
    caption_style   TEXT,
    face_coverage   REAL NOT NULL DEFAULT 0,
    style_json      TEXT,                     -- full CaptionStyle used for the current render
    word_edits_json TEXT NOT NULL DEFAULT '{}', -- {"<transcript word index>": "corrected text"}
    status          TEXT NOT NULL DEFAULT 'ready',  -- ready | queued | rendering | failed
    version         INTEGER NOT NULL DEFAULT 1,
    error_message   TEXT,
    created_at      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS clips_job ON clips(job_id);
CREATE TABLE IF NOT EXISTS fetches (
    id             TEXT PRIMARY KEY,
    url            TEXT NOT NULL,
    rights_confirmed_at REAL NOT NULL,      -- user ticked "I own this video or have permission"
    status         TEXT NOT NULL,           -- queued | downloading | completed | failed
    progress       REAL NOT NULL DEFAULT 0,
    title          TEXT,
    upload_id      TEXT,
    error_code     TEXT,
    error_message  TEXT,
    created_at     REAL NOT NULL,
    updated_at     REAL NOT NULL
);
"""

ACTIVE = ("queued", "extracting_audio", "transcribing", "finding_highlights",
          "tracking_speakers", "creating_captions", "rendering_clips")


class Database:
    def __init__(self, path: Path) -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._migrate()
            self._conn.commit()

    def _migrate(self) -> None:
        """Add columns introduced after a DB was created (CREATE IF NOT EXISTS won't)."""
        added = {
            "clips": [("layout", "TEXT NOT NULL DEFAULT 'original'"), ("caption_style", "TEXT"),
                      ("face_coverage", "REAL NOT NULL DEFAULT 0"), ("style_json", "TEXT"),
                      ("word_edits_json", "TEXT NOT NULL DEFAULT '{}'"),
                      ("status", "TEXT NOT NULL DEFAULT 'ready'"), ("version", "INTEGER NOT NULL DEFAULT 1"),
                      ("error_message", "TEXT")],
        }
        for table, cols in added.items():
            have = {r[1] for r in self._conn.execute(f"PRAGMA table_info({table})")}
            for name, decl in cols:
                if name not in have:
                    self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")

    # ---------- helpers ----------
    def _q(self, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, args).fetchall()]

    def _x(self, sql: str, args: tuple = ()) -> None:
        with self._lock:
            self._conn.execute(sql, args)
            self._conn.commit()

    # ---------- uploads ----------
    @staticmethod
    def _upload(d: dict | None) -> dict | None:
        if d is not None:
            d["video"] = json.loads(d.pop("video_json"))
        return d

    def get_upload(self, upload_id: str) -> dict[str, Any] | None:
        rows = self._q("SELECT * FROM uploads WHERE id = ?", (upload_id,))
        return self._upload(rows[0] if rows else None)

    def get_upload_by_hash(self, sha256: str) -> dict[str, Any] | None:
        rows = self._q("SELECT * FROM uploads WHERE sha256 = ?", (sha256,))
        return self._upload(rows[0] if rows else None)

    def insert_upload(self, *, id: str, sha256: str, filename: str, ext: str,
                      size_bytes: int, video: dict, created_at: float) -> None:
        self._x("INSERT INTO uploads VALUES (?,?,?,?,?,?,?)",
                (id, sha256, filename, ext, size_bytes, json.dumps(video), created_at))

    def uploads_older_than(self, ts: float) -> list[dict[str, Any]]:
        return self._q("SELECT id, ext FROM uploads WHERE created_at < ?", (ts,))

    def delete_upload(self, upload_id: str) -> None:
        self._x("DELETE FROM uploads WHERE id = ?", (upload_id,))

    # ---------- jobs ----------
    def create_job(self, job_id: str, upload_id: str) -> None:
        now = time.time()
        self._x("INSERT INTO jobs (id, upload_id, status, created_at, updated_at) VALUES (?,?,?,?,?)",
                (job_id, upload_id, "queued", now, now))

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        rows = self._q("SELECT * FROM jobs WHERE id = ?", (job_id,))
        return rows[0] if rows else None

    def get_job_by_upload(self, upload_id: str) -> dict[str, Any] | None:
        rows = self._q("SELECT * FROM jobs WHERE upload_id = ?", (upload_id,))
        return rows[0] if rows else None

    def update_job(self, job_id: str, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = time.time()
        cols = ", ".join(f"{k} = ?" for k in fields)
        self._x(f"UPDATE jobs SET {cols} WHERE id = ?", (*fields.values(), job_id))

    def reset_job(self, job_id: str) -> None:
        """Back to queued for a retry/regenerate. Old clips are removed."""
        self._x("DELETE FROM clips WHERE job_id = ?", (job_id,))
        self.update_job(job_id, status="queued", progress=0.0, stage_progress=0.0, live_text="",
                        error_code=None, error_message=None, failed_stage=None, cancel=0)

    def active_jobs(self) -> list[dict[str, Any]]:
        marks = ",".join("?" * len(ACTIVE))
        return self._q(f"SELECT * FROM jobs WHERE status IN ({marks}) ORDER BY created_at", ACTIVE)

    def list_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._q("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,))

    def jobs_older_than(self, ts: float) -> list[dict[str, Any]]:
        marks = ",".join("?" * len(ACTIVE))
        return self._q(f"SELECT id FROM jobs WHERE updated_at < ? AND status NOT IN ({marks})", (ts, *ACTIVE))

    def delete_job(self, job_id: str) -> None:
        self._x("DELETE FROM clips WHERE job_id = ?", (job_id,))
        self._x("DELETE FROM jobs WHERE id = ?", (job_id,))

    # ---------- clips ----------
    def insert_clip(self, **c: Any) -> None:
        c.setdefault("created_at", time.time())
        cols = ", ".join(c)
        self._x(f"INSERT INTO clips ({cols}) VALUES ({','.join('?' * len(c))})", tuple(c.values()))

    def get_clip(self, clip_id: str) -> dict[str, Any] | None:
        rows = self._q("SELECT * FROM clips WHERE id = ?", (clip_id,))
        return rows[0] if rows else None

    def list_clips(self, job_id: str) -> list[dict[str, Any]]:
        return self._q("SELECT * FROM clips WHERE job_id = ? ORDER BY idx", (job_id,))

    def update_clip(self, clip_id: str, **fields: Any) -> None:
        if fields:
            cols = ", ".join(f"{k} = ?" for k in fields)
            self._x(f"UPDATE clips SET {cols} WHERE id = ?", (*fields.values(), clip_id))

    # ---------- link fetches ----------
    def create_fetch(self, fetch_id: str, url: str) -> None:
        now = time.time()
        self._x("INSERT INTO fetches (id, url, rights_confirmed_at, status, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?)", (fetch_id, url, now, "queued", now, now))

    def get_fetch(self, fetch_id: str) -> dict[str, Any] | None:
        rows = self._q("SELECT * FROM fetches WHERE id = ?", (fetch_id,))
        return rows[0] if rows else None

    def update_fetch(self, fetch_id: str, **fields: Any) -> None:
        fields["updated_at"] = time.time()
        cols = ", ".join(f"{k} = ?" for k in fields)
        self._x(f"UPDATE fetches SET {cols} WHERE id = ?", (*fields.values(), fetch_id))

    def pending_fetches(self) -> list[dict[str, Any]]:
        return self._q("SELECT * FROM fetches WHERE status IN ('queued', 'downloading') ORDER BY created_at")

    def pending_clip_renders(self) -> list[dict[str, Any]]:
        return self._q("SELECT * FROM clips WHERE status IN ('queued', 'rendering') ORDER BY created_at")
