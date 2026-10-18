import asyncio
from contextlib import asynccontextmanager
import time
from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from prometheus_client import make_asgi_app

from app import config
from app.metrics import (
    http_request_duration_seconds,
    http_requests_total,
    tasks_created_total,
)
from app.storage import MemoryStore, PostgresStore


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


def create_app(store=None) -> FastAPI:
    if store is None:
        storage_type = config.get_storage()
        if storage_type == "postgres":
            store = PostgresStore(config.get_database_url())
        else:
            store = MemoryStore()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store.init()
        yield
        if hasattr(store, "close"):
            store.close()

    app = FastAPI(title="Task API", lifespan=lifespan)
    app.state.store = store

    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        raw_path = request.url.path
        if raw_path in (
            "/metrics",
            "/metrics/",
            "/healthz",
            "/healthz/",
            "/readyz",
            "/readyz/",
        ) or raw_path.startswith("/metrics/"):
            return await call_next(request)

        start_time = time.perf_counter()
        status_code = "500"
        try:
            response = await call_next(request)
            status_code = str(response.status_code)
            return response
        except Exception:
            status_code = "500"
            raise
        finally:
            duration = time.perf_counter() - start_time
            route = request.scope.get("route")
            if route and hasattr(route, "path"):
                route_path = route.path
            else:
                route_path = "unmatched"
            http_requests_total.labels(
                method=request.method, path=route_path, status=status_code
            ).inc()
            http_request_duration_seconds.labels(
                method=request.method, path=route_path
            ).observe(duration)

    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz():
        if not store.ping():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not ready",
            )
        return {"status": "ready"}

    @app.post("/tasks", status_code=status.HTTP_201_CREATED)
    def create_task(payload: TaskCreate):
        task = store.create(payload.title)
        tasks_created_total.inc()
        return task

    @app.get("/tasks")
    def list_tasks():
        return store.list()

    @app.get("/tasks/{task_id}")
    def get_task(task_id: int):
        task = store.get(task_id)
        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
            )
        return task

    @app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_task(task_id: int):
        deleted = store.delete(task_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
            )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    if config.is_fault_injection_enabled():

        @app.get("/debug/error")
        def debug_error():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Injected error",
            )

        @app.get("/debug/slow")
        async def debug_slow(ms: int = Query(default=100)):
            clamped_ms = max(0, min(ms, 5000))
            await asyncio.sleep(clamped_ms / 1000.0)
            return {"status": "slow", "slept_ms": clamped_ms}

    return app


app = create_app()
