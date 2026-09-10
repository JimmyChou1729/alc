"""Transactional product queue and event projections over package-owned runs."""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

TERMINAL = {"completed", "cancelled"}


class Store:
    def __init__(self, project: str | Path):
        self.project = Path(project).expanduser().resolve()
        self.project.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root = self.project / ".alc" / "web"
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root / "state.sqlite3"
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValueError("This Web database requires a newer ALC version.")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, state TEXT NOT NULL, control TEXT,
                    created REAL NOT NULL, updated REAL NOT NULL, spec TEXT NOT NULL,
                    phase TEXT NOT NULL DEFAULT 'queued', detail TEXT NOT NULL DEFAULT '{}',
                    result TEXT, error TEXT, resume_input TEXT,
                    generation INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
                    created REAL NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL,
                    source_key TEXT UNIQUE
                );
                CREATE INDEX IF NOT EXISTS job_events ON events(job_id, sequence);
                CREATE TABLE IF NOT EXISTS job_presentation (job_id TEXT PRIMARY KEY, title TEXT, deleted INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sources (id TEXT PRIMARY KEY, value TEXT NOT NULL);
                PRAGMA user_version=1;
            """)
        os.chmod(self.path, 0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def create(self, spec: dict[str, Any]) -> dict[str, Any]:
        job_id, now = uuid.uuid4().hex, time.time()
        with self.connect() as db:
            db.execute(
                "INSERT INTO jobs(id,state,created,updated,spec) VALUES(?,?,?,?,?)",
                (job_id, "queued", now, now, json.dumps(spec)),
            )
            self._event(db, job_id, "job.created", {})
        return self.get(job_id)

    def get(self, job_id: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError("Job not found.")
        result = dict(row)
        for key in ("spec", "detail", "result", "error", "resume_input"):
            result[key] = json.loads(result[key]) if result[key] else None
        if result.get("error"):
            from .errors import explain_error
            result["error"]["user_message"] = explain_error(result["error"], result["spec"].get("provider"))
        from .presentation import document_title
        with self.connect() as db:
            display = db.execute("SELECT title,deleted FROM job_presentation WHERE job_id=?", (job_id,)).fetchone()
        result["display_title"] = (display["title"] if display else None) or document_title(self, result) or result["spec"].get("title", "未命名任务")
        result["deleted"] = bool(display and display["deleted"])
        return result

    def rename(self, job_id: str, title: str) -> dict:
        title = title.strip()
        if not title or len(title) > 500:
            raise ValueError("任务名称请输入1–500个字符。")
        self.get(job_id)
        with self.connect() as db:
            db.execute("INSERT INTO job_presentation(job_id,title) VALUES(?,?) ON CONFLICT(job_id) DO UPDATE SET title=excluded.title", (job_id,title))
        return self.get(job_id)

    def delete(self, job_id: str) -> None:
        # Retain saved work on disk; deletion only removes an idle job from the list.
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError("Job not found.")
            if row[0] not in {"completed", "cancelled", "paused", "failed", "needs_input", "delivery_failed"}:
                raise ValueError("请先暂停或取消任务，再删除。")
            db.execute("INSERT INTO job_presentation(job_id,deleted) VALUES(?,1) ON CONFLICT(job_id) DO UPDATE SET deleted=1", (job_id,))

    def list(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            ids = [
                r[0]
                for r in db.execute(
                    "SELECT id FROM jobs WHERE id NOT IN (SELECT job_id FROM job_presentation WHERE deleted=1) ORDER BY created DESC LIMIT 500"
                )
            ]
        return [self.get(job_id) for job_id in ids]

    def summaries(self) -> list[dict[str, Any]]:
        return [
            {k: j[k] for k in ("id", "state", "phase", "created", "display_title")} | {"spec": {"title": j["spec"].get("title", "")}}
            for j in self.list() if not j["deleted"]
        ]

    def active_ids(self) -> list[str]:
        with self.connect() as db:
            return [
                r[0]
                for r in db.execute(
                    "SELECT id FROM jobs WHERE state IN ('running','delivering','pausing','cancelling')"
                )
            ]

    def pending_ids(self, limit: int) -> list[str]:
        with self.connect() as db:
            return [
                r[0]
                for r in db.execute(
                    "SELECT id FROM jobs WHERE state='queued' ORDER BY created LIMIT ?",
                    (max(0, limit),),
                )
            ]

    def bind_unstarted_runtime(self, job_id: str, runtime: dict) -> bool:
        """Bind a pristine job under its worker lease; never migrate saved work."""
        root = self.job_directory(job_id)
        allowed = {"worker.lock", "worker.log", "provider.json"}
        if root.exists() and any(p.name not in allowed for p in root.iterdir()):
            return False
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if (row is None or row["phase"] != "queued"
                or row["state"] not in {"running", "needs_input", "queued"}
                or json.loads(row["detail"] or "{}")
                or json.loads(row["result"] or "null")):
                return False
            spec = json.loads(row["spec"])
            spec["runtime"] = runtime
            db.execute("UPDATE jobs SET spec=?, updated=? WHERE id=?",
                       (json.dumps(spec), time.time(), job_id))
        return True

    def resume_ocr_review(self, job_id: str, runtime: dict) -> dict:
        """Continue a verified completed OCR candidate under the caller's worker lease."""
        root = self.job_directory(job_id)
        if (root / "project").exists() or (root / "source-export").exists():
            raise ValueError("Cannot migrate a review after downstream work has started.")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if (row is None or row["state"] != "needs_input" or row["phase"] != "ocr_proofread"
                    or (json.loads(row["error"] or "{}") or {}).get("code") != "ocr_review_required"
                    or json.loads(row["result"] or "null")):
                raise ValueError("This task is not awaiting its first OCR review.")
            display = db.execute("SELECT deleted FROM job_presentation WHERE job_id=?", (job_id,)).fetchone()
            if display and display[0]:
                raise ValueError("任务已从列表删除，不能继续运行。")
            spec = json.loads(row["spec"])
            old = spec.get("runtime", {})
            if any(old.get(k) != runtime.get(k) for k in ("schema_version", "python", "libraries")):
                raise ValueError("Runtime libraries changed; restore the saved runtime before continuing.")
            allowed = {"ac-document", "alc-ocr-proofread", "alc-web"}
            if set(old.get("packages", {})) != set(runtime.get("packages", {})) or any(
                old["packages"][name].get("version") != value.get("version")
                or (name not in allowed and old["packages"][name] != value)
                for name, value in runtime.get("packages", {}).items()
            ):
                raise ValueError("Downstream runtime changed; restore it before continuing.")
            spec["runtime"] = runtime
            db.execute("UPDATE jobs SET spec=?,state='queued',control=NULL,resume_input=NULL,error=NULL,updated=? WHERE id=?", (json.dumps(spec), time.time(), job_id))
            self._event(db, job_id, "ocr.review_continued", {"previous_runtime": old, "runtime": runtime})
        return self.get(job_id)

    def update(self, job_id: str, **fields: Any) -> None:
        if set(fields) - {
            "state",
            "control",
            "phase",
            "detail",
            "result",
            "error",
            "resume_input",
            "generation",
        }:
            raise ValueError("Invalid job fields.")
        values = {
            k: (
                json.dumps(v)
                if k in {"detail", "result", "error", "resume_input"} and v is not None
                else v
            )
            for k, v in fields.items()
        }
        values["updated"] = time.time()
        with self.connect() as db:
            if "state" in values:
                db.execute("BEGIN IMMEDIATE")
                current = db.execute(
                    "SELECT control FROM jobs WHERE id=?", (job_id,)
                ).fetchone()
                if current and current[0] in {"pause", "cancel"}:
                    values["state"] = (
                        "cancelled" if current[0] == "cancel" else "paused"
                    )
                    fields["state"] = values["state"]
            db.execute(
                "UPDATE jobs SET " + ",".join(f"{k}=?" for k in values) + " WHERE id=?",
                (*values.values(), job_id),
            )
            self._event(
                db,
                job_id,
                "job.updated",
                {
                    k: ({"progress": v.get("progress", {})} if k == "detail" else v)
                    for k, v in fields.items()
                    if k != "resume_input"
                },
            )

    def schedule_recovery(self, job_id: str, *, now: float | None = None) -> bool:
        from .recovery import transient_provider_failure
        now = time.time() if now is None else now
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if (row is None or row["state"] not in {"failed", "needs_input"}
                or row["control"] is not None):
                return False
            if not json.loads(row["spec"]).get("automatic_recovery", False):
                return False
            if not transient_provider_failure(json.loads(row["error"] or "{}")):
                return False
            detail = json.loads(row["detail"] or "{}")
            recovery = detail.get("auto_recovery", {})
            attempts = recovery.get("attempts", 0)
            if attempts >= 3 or recovery.get("retry_at") is not None:
                return False
            detail["auto_recovery"] = {"attempts": attempts + 1, "retry_at": now + 30 * 2**attempts}
            db.execute("UPDATE jobs SET detail=?,updated=? WHERE id=?", (json.dumps(detail),now,job_id))
            self._event(db, job_id, "job.recovery_wait", detail["auto_recovery"])
        return True

    def resume_due_recoveries(self, *, now: float | None = None) -> int:
        from .recovery import transient_provider_failure
        now = time.time() if now is None else now
        count = 0
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("SELECT * FROM jobs WHERE state IN ('failed','needs_input') AND control IS NULL AND id NOT IN (SELECT job_id FROM job_presentation WHERE deleted=1)").fetchall()
            for row in rows:
                if not json.loads(row["spec"]).get("automatic_recovery", False) or not transient_provider_failure(json.loads(row["error"] or "{}")):
                    continue
                detail = json.loads(row["detail"] or "{}")
                recovery = detail.get("auto_recovery", {})
                due = recovery.get("retry_at")
                if due is None or due > now:
                    continue
                recovery["retry_at"] = None
                db.execute("UPDATE jobs SET state='queued',error=NULL,resume_input=NULL,detail=?,updated=? WHERE id=?",
                           (json.dumps(detail),now,row["id"]))
                self._event(db,row["id"],"job.recovery_resumed", {"attempts":recovery["attempts"]})
                count += 1
        return count


    def control(
        self, job_id: str, action: str, resume_input: dict | None = None
    ) -> dict:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state,detail FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError("Job not found.")
            state = row[0]
            allowed = {
                "pause": {"queued", "running", "delivering", "pausing", "needs_input", "failed"},
                "cancel": {
                    "queued",
                    "running",
                    "delivering",
                    "pausing",
                    "paused",
                    "failed",
                    "needs_input",
                    "cancelling",
                    "delivery_failed",
                },
                "resume": {"paused", "failed", "needs_input"},
                "retry_delivery": {"delivery_failed"},
            }
            if state == "cancelled" and action == "cancel":
                return self.get(job_id)
            display = db.execute("SELECT deleted FROM job_presentation WHERE job_id=?", (job_id,)).fetchone()
            if display and display[0]:
                raise ValueError("任务已从列表删除，不能继续运行。")
            if state not in allowed[action]:
                raise ValueError(
                    "This action is not available in the current job state."
                )
            next_state = {
                "pause": "paused" if state in {"queued", "needs_input", "failed"} else "pausing",
                "cancel": (
                    "cancelling"
                    if state in {"running", "delivering", "pausing", "cancelling"}
                    else "cancelled"
                ),
                "resume": "queued",
                "retry_delivery": "queued",
            }[action]
            control = (
                action if action in {"pause", "cancel", "retry_delivery"} else None
            )
            detail = json.loads(row["detail"] or "{}")
            if "auto_recovery" in detail:
                detail["auto_recovery"]["retry_at"] = None
                db.execute("UPDATE jobs SET detail=? WHERE id=?", (json.dumps(detail),job_id))
            db.execute(
                "UPDATE jobs SET state=?,control=?,resume_input=?,error=NULL,updated=? WHERE id=?",
                (
                    next_state,
                    control,
                    json.dumps(resume_input) if resume_input is not None else None,
                    time.time(),
                    job_id,
                ),
            )
            self._event(
                db, job_id, "job.control", {"action": action, "state": next_state}
            )
        return self.get(job_id)

    def claim(self, job_id: str) -> bool:
        with self.connect() as db:
            changed = db.execute(
                "UPDATE jobs SET state='running', generation=generation+1, updated=? WHERE id=? AND state='queued'",
                (time.time(), job_id),
            ).rowcount
            if changed:
                self._event(db, job_id, "job.started", {})
        return bool(changed)

    def finish(self, job_id: str, result: dict) -> None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT control FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            if row is None:
                raise KeyError("Job not found.")
            state = (
                "cancelled"
                if row[0] == "cancel"
                else "paused" if row[0] == "pause" else "completed"
            )
            db.execute(
                "UPDATE jobs SET state=?,phase=?,result=?,error=NULL,updated=? WHERE id=?",
                (state, "completed", json.dumps(result), time.time(), job_id),
            )
            self._event(db, job_id, "job.finished", {"state": state})

    def event(
        self, job_id: str, kind: str, data: dict, *, source_key: str | None = None
    ) -> None:
        with self.connect() as db:
            self._event(db, job_id, kind, data, source_key=source_key)

    @staticmethod
    def _event(
        db: Any, job_id: str, kind: str, data: dict, *, source_key: str | None = None
    ) -> None:
        db.execute(
            "INSERT OR IGNORE INTO events(job_id,created,kind,data,source_key) VALUES(?,?,?,?,?)",
            (job_id, time.time(), kind, json.dumps(data, allow_nan=False), source_key),
        )

    def events(self, job_id: str, after: int = 0, limit: int = 200) -> list[dict]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM events WHERE job_id=? AND sequence>? ORDER BY sequence LIMIT ?",
                (job_id, after, limit),
            ).fetchall()
        return [{**dict(r), "data": json.loads(r["data"])} for r in rows]

    def save_setting(self, key: str, value: Any) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value)),
            )

    def merge_setting(self, key: str, name: str, value: Any) -> None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT value FROM settings WHERE key=?", (key,)
            ).fetchone()
            values = json.loads(row[0]) if row else {}
            values[name] = value
            db.execute(
                "INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(values)),
            )

    def recent_events(self, job_id: str, limit: int = 30) -> list[dict]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM events WHERE job_id=? AND kind!='job.updated' ORDER BY sequence DESC LIMIT ?",
                (job_id, limit),
            ).fetchall()
        return [{**dict(r), "data": json.loads(r["data"])} for r in reversed(rows)]

    def setting(self, key: str, default: Any = None) -> Any:
        with self.connect() as db:
            row = db.execute(
                "SELECT value FROM settings WHERE key=?", (key,)
            ).fetchone()
        return json.loads(row[0]) if row else default

    def source(self, source_id: str) -> dict:
        with self.connect() as db:
            row = db.execute(
                "SELECT value FROM sources WHERE id=?", (source_id,)
            ).fetchone()
        if row is None:
            raise KeyError("Source not found.")
        return json.loads(row[0])

    def add_source(self, source_id: str, value: dict) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO sources VALUES(?,?)", (source_id, json.dumps(value))
            )

    def job_directory(self, job_id: str) -> Path:
        if len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
            raise ValueError("Invalid job ID.")
        return self.root / "jobs" / job_id
