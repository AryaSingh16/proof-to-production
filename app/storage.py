from datetime import datetime, timezone
import threading
import time
from typing import Any, Dict, List, Optional
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


class MemoryStore:
    def __init__(self) -> None:
        self._tasks: Dict[int, Dict[str, Any]] = {}
        self._counter: int = 1
        self._lock = threading.Lock()

    def init(self) -> None:
        pass

    def ping(self) -> bool:
        return True

    def create(self, title: str) -> Dict[str, Any]:
        with self._lock:
            task_id = self._counter
            self._counter += 1
            task = {
                "id": task_id,
                "title": title,
                "done": False,
                "created_at": datetime.now(timezone.utc),
            }
            self._tasks[task_id] = task
            return task

    def list(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._tasks.values())

    def get(self, id: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._tasks.get(id)

    def delete(self, id: int) -> bool:
        with self._lock:
            if id in self._tasks:
                del self._tasks[id]
                return True
            return False


class PostgresStore:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.pool = ConnectionPool(
            conninfo=self.database_url,
            min_size=1,
            max_size=4,
            kwargs={"row_factory": dict_row},
            open=False,
        )

    def init(self) -> None:
        if self.pool.closed:
            self.pool.open()
        last_exc = None
        for attempt in range(30):
            try:
                with self.pool.connection(timeout=5.0) as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            CREATE TABLE IF NOT EXISTS tasks (
                                id SERIAL PRIMARY KEY,
                                title TEXT NOT NULL,
                                done BOOLEAN NOT NULL DEFAULT false,
                                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                            )
                        """)
                    conn.commit()
                return
            except Exception as e:
                last_exc = e
                time.sleep(2)
        if last_exc:
            raise last_exc

    def ping(self) -> bool:
        try:
            if self.pool.closed:
                self.pool.open()
            with self.pool.connection(timeout=2.0) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
            return True
        except Exception:
            return False

    def create(self, title: str) -> Dict[str, Any]:
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO tasks (title) VALUES (%s) RETURNING id, title, done, created_at",
                    (title,),
                )
                task = cur.fetchone()
            conn.commit()
            return dict(task)

    def list(self) -> List[Dict[str, Any]]:
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, title, done, created_at FROM tasks ORDER BY id ASC"
                )
                tasks = cur.fetchall()
            return [dict(t) for t in tasks]

    def get(self, id: int) -> Optional[Dict[str, Any]]:
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, title, done, created_at FROM tasks WHERE id = %s",
                    (id,),
                )
                task = cur.fetchone()
            return dict(task) if task else None

    def delete(self, id: int) -> bool:
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM tasks WHERE id = %s RETURNING id",
                    (id,),
                )
                task = cur.fetchone()
            conn.commit()
            return task is not None

    def close(self) -> None:
        self.pool.close()
