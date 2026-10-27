"""Telemetry persistence layer for PALIMPSEST using SQLite in WAL mode.

Architecture:
- Concurrency & Reliability: A dedicated background writer thread consumes insert/update
  tasks from a standard `queue.Queue()`. This guarantees that SQLite writes are strictly
  serialized on one thread while keeping async request handlers completely non-blocking.
- WAL Mode: Both writer and reader connections enable `PRAGMA journal_mode = WAL;` and
  `PRAGMA busy_timeout = 5000;` so readers never block writers and writers never block readers.
- Error Isolation: Every database operation is wrapped in `try ... except` so any disk
  or SQLite error is logged and isolated without interrupting de-obfuscation runs.
- Precision: 64-bit integer values in witnesses, expected, and actual are stored as TEXT
  to eliminate precision truncation.
"""
import json
import logging
import queue
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from backend.app.config import settings

logger = logging.getLogger("palimpsest.telemetry")


def stringify_witness(witness: Optional[Dict[str, Any]]) -> Optional[str]:
    """Serializes a witness dictionary into JSON with all values converted to strings."""
    if witness is None:
        return None
    string_witness = {k: str(v) for k, v in witness.items()}
    return json.dumps(string_witness)


class TelemetryDB:
    """Manages telemetry persistence with a dedicated single-writer thread."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.DATABASE_PATH
        self._write_queue: queue.Queue = queue.Queue()
        self._writer_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._initialized = False

    def init_db(self, db_path: Optional[str] = None) -> None:
        """Initializes tables and WAL mode on the SQLite database."""
        if db_path:
            self.db_path = db_path

        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA busy_timeout = 5000;")
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS runs (
                        run_id TEXT PRIMARY KEY,
                        timestamp TEXT NOT NULL,
                        expression TEXT NOT NULL,
                        obf_nodes INTEGER NOT NULL,
                        final_status TEXT NOT NULL,
                        final_expr TEXT,
                        compression_pct REAL,
                        attempts INTEGER NOT NULL,
                        total_ms REAL NOT NULL,
                        backend TEXT NOT NULL,
                        model_name TEXT,
                        max_iterations INTEGER NOT NULL
                    );
                """)
                # Migration: add model_name column if table already exists without it
                cursor = conn.execute("PRAGMA table_info(runs);")
                columns = [row[1] for row in cursor.fetchall()]
                if "model_name" not in columns:
                    conn.execute("ALTER TABLE runs ADD COLUMN model_name TEXT;")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS attempts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        run_id TEXT NOT NULL,
                        iteration INTEGER NOT NULL,
                        candidate TEXT NOT NULL,
                        status TEXT NOT NULL,
                        latency_ms REAL NOT NULL,
                        witness_json TEXT,
                        expected TEXT,
                        actual TEXT,
                        raw_output TEXT,
                        FOREIGN KEY (run_id) REFERENCES runs (run_id)
                    );
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_attempts_run_id ON attempts(run_id);
                """)
            conn.close()
            self._initialized = True
            logger.info("Telemetry database initialized at %s", self.db_path)
        except Exception as exc:
            logger.error("Failed to initialize telemetry database: %s", exc)

    def start_writer(self) -> None:
        """Starts the dedicated background writer thread."""
        if self._writer_thread and self._writer_thread.is_alive():
            return

        if not self._initialized:
            self.init_db()

        self._stop_event.clear()
        self._writer_thread = threading.Thread(
            target=self._writer_loop,
            name="palimpsest-telemetry-writer",
            daemon=True,
        )
        self._writer_thread.start()
        logger.info("Telemetry background writer thread started.")

    def stop_writer(self, wait: bool = True) -> None:
        """Stops the background writer thread cleanly, draining remaining queue tasks."""
        self._stop_event.set()
        self._write_queue.put(None)  # Sentinel to unblock queue.get()
        if wait and self._writer_thread and self._writer_thread.is_alive():
            self._writer_thread.join(timeout=3.0)
        logger.info("Telemetry background writer thread stopped.")

    def _writer_loop(self) -> None:
        """Loop executed by the single writer thread."""
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA busy_timeout = 5000;")

            while not self._stop_event.is_set() or not self._write_queue.empty():
                try:
                    task = self._write_queue.get(timeout=0.2)
                except queue.Empty:
                    continue

                if task is None:
                    break

                action, data = task
                try:
                    if action == "insert_run":
                        with conn:
                            conn.execute("""
                                INSERT OR REPLACE INTO runs (
                                    run_id, timestamp, expression, obf_nodes,
                                    final_status, final_expr, compression_pct,
                                    attempts, total_ms, backend, model_name, max_iterations
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                            """, (
                                data["run_id"],
                                data.get("timestamp", datetime.now(timezone.utc).isoformat()),
                                data["expression"],
                                data["obf_nodes"],
                                data["final_status"],
                                data.get("final_expr"),
                                data.get("compression_pct"),
                                data.get("attempts", 0),
                                data.get("total_ms", 0.0),
                                data.get("backend", "fake"),
                                data.get("model_name"),
                                data.get("max_iterations", 5),
                            ))
                    elif action == "update_run_status":
                        with conn:
                            conn.execute("""
                                UPDATE runs
                                SET final_status = ?,
                                    final_expr = COALESCE(?, final_expr),
                                    compression_pct = COALESCE(?, compression_pct),
                                    attempts = COALESCE(?, attempts),
                                    total_ms = COALESCE(?, total_ms)
                                WHERE run_id = ?;
                            """, (
                                data["final_status"],
                                data.get("final_expr"),
                                data.get("compression_pct"),
                                data.get("attempts"),
                                data.get("total_ms"),
                                data["run_id"],
                            ))
                    elif action == "insert_attempt":
                        with conn:
                            conn.execute("""
                                INSERT INTO attempts (
                                    run_id, iteration, candidate, status,
                                    latency_ms, witness_json, expected, actual, raw_output
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                            """, (
                                data["run_id"],
                                data["iteration"],
                                data["candidate"],
                                data["status"],
                                data.get("latency_ms", 0.0),
                                stringify_witness(data.get("witness")),
                                str(data["expected"]) if data.get("expected") is not None else None,
                                str(data["actual"]) if data.get("actual") is not None else None,
                                data.get("raw_output", ""),
                            ))
                except Exception as exc:
                    logger.error("Error executing telemetry write (%s): %s", action, exc)
                finally:
                    self._write_queue.task_done()
        except Exception as exc:
            logger.error("Telemetry writer thread failed: %s", exc)
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def record_run(self, run_data: Dict[str, Any]) -> None:
        """Enqueues a run record for persistent storage."""
        try:
            self._write_queue.put(("insert_run", run_data))
        except Exception as exc:
            logger.error("Failed to enqueue run telemetry: %s", exc)

    def update_run(self, update_data: Dict[str, Any]) -> None:
        """Enqueues a run update (e.g. for cancellation or completion)."""
        try:
            self._write_queue.put(("update_run_status", update_data))
        except Exception as exc:
            logger.error("Failed to enqueue run update: %s", exc)

    def record_attempt(self, attempt_data: Dict[str, Any]) -> None:
        """Enqueues an attempt record for persistent storage."""
        try:
            self._write_queue.put(("insert_attempt", attempt_data))
        except Exception as exc:
            logger.error("Failed to enqueue attempt telemetry: %s", exc)

    def sync(self, timeout: float = 2.0) -> None:
        """Blocks until all currently enqueued write tasks have been processed."""
        try:
            self._write_queue.join()
        except Exception:
            pass

    # Read Operations (Read-only, thread-safe, non-blocking via WAL)
    def _get_read_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        return conn

    def get_history(
        self,
        limit: int = 50,
        offset: int = 0,
        exclude_fake: bool = False,
    ) -> List[Dict[str, Any]]:
        """Returns paginated history of past runs."""
        try:
            self.sync()
            with self._get_read_conn() as conn:
                query = """
                    SELECT run_id, timestamp, expression, obf_nodes,
                           final_status, final_expr, compression_pct,
                           attempts, total_ms, backend, model_name, max_iterations
                    FROM runs
                """
                params: List[Any] = []
                if exclude_fake:
                    query += " WHERE LOWER(backend) != 'fake' "
                query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?;"
                params.extend([limit, offset])
                cur = conn.execute(query, tuple(params))
                return [dict(row) for row in cur.fetchall()]
        except Exception as exc:
            logger.error("Error reading run history: %s", exc)
            return []

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Returns details of a specific run along with its attempts."""
        try:
            self.sync()
            with self._get_read_conn() as conn:
                cur = conn.execute("""
                    SELECT run_id, timestamp, expression, obf_nodes,
                           final_status, final_expr, compression_pct,
                           attempts, total_ms, backend, model_name, max_iterations
                    FROM runs
                    WHERE run_id = ?;
                """, (run_id,))
                run_row = cur.fetchone()
                if not run_row:
                    return None

                run_dict = dict(run_row)

                cur_att = conn.execute("""
                    SELECT iteration, candidate, status, latency_ms,
                           witness_json, expected, actual, raw_output
                    FROM attempts
                    WHERE run_id = ?
                    ORDER BY iteration ASC;
                """, (run_id,))

                attempts_list = []
                for row in cur_att.fetchall():
                    att = dict(row)
                    # Parse witness_json back to dict of strings
                    if att.get("witness_json"):
                        try:
                            att["witness"] = json.loads(att["witness_json"])
                        except Exception:
                            att["witness"] = {}
                    else:
                        att["witness"] = {}
                    att.pop("witness_json", None)
                    attempts_list.append(att)

                run_dict["attempts_history"] = attempts_list
                return run_dict
        except Exception as exc:
            logger.error("Error reading run %s: %s", run_id, exc)
            return None

    def get_stats(self, exclude_fake: bool = False) -> Dict[str, Any]:
        """Calculates aggregate statistics over runs, optionally excluding FAKE runs."""
        try:
            self.sync()
            with self._get_read_conn() as conn:
                where_clause = " WHERE LOWER(backend) != 'fake'" if exclude_fake else ""
                cur = conn.execute(f"""
                    SELECT
                        COUNT(*) as total_runs,
                        SUM(CASE WHEN final_status = 'VERIFIED_EQUIVALENT' THEN 1 ELSE 0 END) as verified_runs,
                        SUM(CASE WHEN final_status IN ('FAILED', 'REJECTED_UNSAFE', 'ERROR', 'CANCELLED') THEN 1 ELSE 0 END) as failed_runs,
                        AVG(CASE WHEN final_status = 'VERIFIED_EQUIVALENT' THEN compression_pct ELSE NULL END) as avg_compression,
                        AVG(total_ms) as avg_latency_ms,
                        AVG(attempts) as avg_attempts
                    FROM runs{where_clause};
                """)
                row = cur.fetchone()
                if not row or row["total_runs"] == 0:
                    return {
                        "total_runs": 0,
                        "verified_runs": 0,
                        "failed_runs": 0,
                        "success_rate_pct": 0.0,
                        "avg_compression_pct": 0.0,
                        "avg_latency_ms": 0.0,
                        "avg_attempts": 0.0,
                    }

                total = row["total_runs"]
                verified = row["verified_runs"] or 0
                failed = row["failed_runs"] or 0
                success_rate = round((verified / total) * 100, 2) if total > 0 else 0.0
                avg_comp = round(row["avg_compression"] or 0.0, 2)
                avg_lat = round(row["avg_latency_ms"] or 0.0, 2)
                avg_att = round(row["avg_attempts"] or 0.0, 2)

                return {
                    "total_runs": total,
                    "verified_runs": verified,
                    "failed_runs": failed,
                    "success_rate_pct": success_rate,
                    "avg_compression_pct": avg_comp,
                    "avg_latency_ms": avg_lat,
                    "avg_attempts": avg_att,
                }
        except Exception as exc:
            logger.error("Error computing stats: %s", exc)
            return {
                "total_runs": 0,
                "verified_runs": 0,
                "failed_runs": 0,
                "success_rate_pct": 0.0,
                "avg_compression_pct": 0.0,
                "avg_latency_ms": 0.0,
                "avg_attempts": 0.0,
            }


# Global default database instance
telemetry_db = TelemetryDB()
