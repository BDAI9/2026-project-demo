"""SQLite 저장소: 모임방, 참여자, 잇플 거래추적번호 순번, AI 추정 캐시."""

from __future__ import annotations

import json
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from .options import MAX_PARTICIPANTS

KST = timezone(timedelta(hours=9))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS rooms (
    id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS participants (
    id TEXT PRIMARY KEY, room_id TEXT NOT NULL, token TEXT NOT NULL,
    data TEXT NOT NULL, updated_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS participants_room ON participants(room_id);
CREATE TABLE IF NOT EXISTS trace_sequence (
    institution TEXT NOT NULL, day TEXT NOT NULL, sequence INTEGER NOT NULL,
    PRIMARY KEY (institution, day));
CREATE TABLE IF NOT EXISTS estimates (
    place_id TEXT NOT NULL, allergens TEXT NOT NULL, data TEXT NOT NULL, created_at REAL NOT NULL,
    PRIMARY KEY (place_id, allergens));
"""


class Store:
    def __init__(self, path: str = "moim.sqlite3"):
        self.path = path
        self._lock = threading.Lock()
        with self._db() as db:
            db.executescript(_SCHEMA)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        try:
            yield db
        finally:
            db.close()

    # ---- 방 ----
    def create_room(self, title: str) -> str:
        room_id = secrets.token_urlsafe(6)
        with self._db() as db:
            db.execute("INSERT INTO rooms VALUES (?, ?, ?)", (room_id, title, time.time()))
        return room_id

    def get_room(self, room_id: str):
        with self._db() as db:
            row = db.execute("SELECT id, title FROM rooms WHERE id = ?", (room_id,)).fetchone()
            if not row:
                return None
            people = db.execute(
                "SELECT id, data FROM participants WHERE room_id = ? ORDER BY updated_at", (room_id,)).fetchall()
        return {"id": row[0], "title": row[1],
                "participants": [dict(json.loads(d), id=pid) for pid, d in people]}

    # ---- 참여자 ----
    def add_participant(self, room_id: str, data: dict) -> tuple[str, str]:
        with self._lock, self._db() as db:
            count = db.execute("SELECT COUNT(*) FROM participants WHERE room_id = ?", (room_id,)).fetchone()[0]
            if count >= MAX_PARTICIPANTS:
                raise ValueError(f"한 모임에는 최대 {MAX_PARTICIPANTS}명까지 참여할 수 있어요.")
            pid, token = secrets.token_urlsafe(6), secrets.token_urlsafe(16)
            db.execute("INSERT INTO participants VALUES (?, ?, ?, ?, ?)",
                       (pid, room_id, token, json.dumps(data, ensure_ascii=False), time.time()))
        return pid, token

    def update_participant(self, room_id: str, pid: str, token: str, data: dict) -> bool:
        with self._db() as db:
            cur = db.execute(
                "UPDATE participants SET data = ?, updated_at = ? WHERE id = ? AND room_id = ? AND token = ?",
                (json.dumps(data, ensure_ascii=False), time.time(), pid, room_id, token))
        return cur.rowcount == 1

    def delete_participant(self, room_id: str, pid: str, token: str) -> bool:
        with self._db() as db:
            cur = db.execute("DELETE FROM participants WHERE id = ? AND room_id = ? AND token = ?",
                             (pid, room_id, token))
        return cur.rowcount == 1

    # ---- 잇플 거래추적번호: 기관명 + YYYYMMDD + 10자리 순번 ----
    def next_trace_number(self, institution: str) -> str:
        day = datetime.now(KST).strftime("%Y%m%d")
        with self._lock, self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR IGNORE INTO trace_sequence VALUES (?, ?, 0)", (institution, day))
            db.execute("UPDATE trace_sequence SET sequence = sequence + 1 WHERE institution = ? AND day = ?",
                       (institution, day))
            seq = db.execute("SELECT sequence FROM trace_sequence WHERE institution = ? AND day = ?",
                             (institution, day)).fetchone()[0]
            db.execute("COMMIT")
        if seq >= 10 ** 10:
            raise ValueError("오늘 사용할 수 있는 거래추적번호를 모두 썼어요.")
        return f"{institution}{day}{seq:010d}"

    # ---- AI 추정 캐시 ----
    def get_estimates(self, place_ids: list[str], allergens: list[str]) -> dict:
        key = json.dumps(sorted(allergens), ensure_ascii=False)
        out = {}
        with self._db() as db:
            for pid in place_ids:
                row = db.execute("SELECT data FROM estimates WHERE place_id = ? AND allergens = ?",
                                 (pid, key)).fetchone()
                if row:
                    out[pid] = json.loads(row[0])
        return out

    def save_estimates(self, estimates: dict, allergens: list[str]) -> None:
        key = json.dumps(sorted(allergens), ensure_ascii=False)
        with self._db() as db:
            for pid, data in estimates.items():
                db.execute("INSERT OR REPLACE INTO estimates VALUES (?, ?, ?, ?)",
                           (pid, key, json.dumps(data, ensure_ascii=False), time.time()))
