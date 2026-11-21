import asyncio
import logging
import sqlite3
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated
from weakref import WeakValueDictionary

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from .config import Settings
from .database import Database
from .gateway import Gateway, ProvidersUnavailable
from .schemas import ChatRequest, ChatResponse, HealthResponse, HistoryResponse


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    database = Database(settings.database)
    gateway = Gateway(settings)
    session_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await run_in_threadpool(database.initialize)
        with gateway.enable():
            yield

    app = FastAPI(
        lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None, redirect_slashes=False
    )

    @app.middleware("http")
    async def protect_error_details(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        try:
            return await call_next(request)
        except Exception as error:
            logging.getLogger(__name__).error("Request failed (%s)", type(error).__name__)
            return JSONResponse(status_code=500, content={"detail": "internal server error"})

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.origins),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Simulate-Failure"],
    )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, error: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"detail": [
                {"loc": issue["loc"], "msg": issue["msg"], "type": issue["type"]}
                for issue in error.errors()
            ]},
        )

    @app.get("/health")
    def health() -> HealthResponse:
        try:
            database.ping()
        except sqlite3.Error:
            raise HTTPException(503, "database unavailable") from None
        if not gateway.cache_enabled or len(gateway.key_ids) < 2:
            raise HTTPException(503, "gateway unavailable")
        return HealthResponse(keys_configured=len(gateway.key_ids), cache_enabled=True)

    @app.post("/chat")
    async def chat(
        body: ChatRequest,
        failure_header: Annotated[str | None, Header(alias="X-Simulate-Failure")] = None,
    ) -> ChatResponse:
        lock = session_locks.get(body.session_id)
        if lock is None:
            lock = session_locks[body.session_id] = asyncio.Lock()
        async with lock:
            stored_prompt, messages = await run_in_threadpool(database.context, body.session_id)
            system_prompt = body.system_prompt
            if system_prompt is None:
                system_prompt = settings.default_prompt if stored_prompt is None else stored_prompt
            if system_prompt:
                messages.insert(0, {"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": body.message})
            try:
                reply, metadata = await gateway.resolve(messages, failure_header)
            except ProvidersUnavailable:
                raise HTTPException(503, "all providers unavailable") from None
            await run_in_threadpool(
                database.save_turn, body.session_id, system_prompt, body.message, reply, metadata
            )
        return ChatResponse(session_id=body.session_id, reply=reply, metadata=metadata)

    @app.get("/sessions/{session_id:path}/messages")
    def history(session_id: str) -> HistoryResponse:
        messages = database.history(session_id)
        if messages is None:
            raise HTTPException(404, "session not found")
        return HistoryResponse.model_validate({"session_id": session_id, "messages": messages})

    return app
