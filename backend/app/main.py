"""FastAPI entry point. The Vite dev server proxies /api here, so no CORS is needed."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from app.ai import api as ai_api
from app.ai import seed
from app.api import actor, audit, cases, documents, exceptions, facts, health, home, ingest, intake, investigate, proposals, replies, uploads
from app.cases import home as home_rules
from app.core.errors import install_error_handlers
from app.db.session import SessionLocal


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Prompts missing from the registry are loaded from the YAML seeds on start."""
    with SessionLocal() as session:
        seed.seed_prompts(session)
    yield


app = FastAPI(title="Immigration Case Co-Pilot API", lifespan=lifespan)
install_error_handlers(app)


@app.middleware("http")
async def clear_home_cache_on_write(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Any write may change a case's urgency, so the next home request recomputes."""
    response = await call_next(request)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        home_rules.clear_cache()
    return response

app.include_router(health.router)
app.include_router(actor.router)
app.include_router(audit.router)
app.include_router(cases.router)
app.include_router(documents.router)
app.include_router(exceptions.router)
app.include_router(facts.router)
app.include_router(home.router)
app.include_router(ingest.router)
app.include_router(intake.router)
app.include_router(investigate.router)
app.include_router(proposals.router)
app.include_router(replies.router)
app.include_router(uploads.router)
app.include_router(ai_api.router)
app.add_exception_handler(ai_api.ApiError, ai_api.api_error_handler)
