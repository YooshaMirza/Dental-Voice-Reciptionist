"""
FastAPI entrypoint — replaces the old Django project (instabus_backend +
api + voice_agent apps). Run with: uvicorn app.main:app
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import settings
from app.db.mongo import ensure_default_web_user
from app.auth.routes import router as auth_router
from app.calls.dashboard import router as dashboard_router
from app.calls.twilio_webhooks import router as twilio_router
from app.calls.websocket import router as websocket_router
from app.ghl.webhook import router as ghl_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%b %d %H:%M:%S",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="DCAI Voice Agent")

# Session cookie used for the server-rendered dashboard login (separate from
# the JWT API auth) — same split the old Django app had (session vs JWT).
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Mirrors the old CORS_ALLOW_ALL_ORIGINS=True dev-mode config. Tighten this
# once a real frontend origin is known.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(twilio_router)
app.include_router(ghl_router)
app.include_router(websocket_router)


@app.on_event("startup")
async def on_startup():
    ensure_default_web_user()

    from app.voice.vertex_ai_client import warm_up_token_cache
    from app.voice.ambience import warm_up_ambience_cache
    import threading

    def _warmup():
        try:
            warm_up_token_cache()
        except Exception as e:
            logger.warning(f"Token warm-up failed (will retry on first call): {e}")

    threading.Thread(target=_warmup, daemon=True).start()
    threading.Thread(target=warm_up_ambience_cache, daemon=True).start()


@app.get("/health")
async def health():
    return {"status": "ok"}
