import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from backend.ws_handler import websocket_handler

# show chatbot lifecycle logs in the terminal 

logging.basicConfig(level=logging.INFO, format="%(name)s | %(message)s")
logging.getLogger("chatbot").setLevel(logging.INFO)
from chatbot.router import router as chat_router
from chatbot.session import cleanup_expired, save_all_sessions, cleanup_output_dir
from backend.parquet_handler import router as parquet_router
import s3_client

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    # Startup: ensure S3 bucket exists, launch background session cleanup task
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, s3_client.ensure_bucket)
    task  = asyncio.create_task(cleanup_expired())
    logger.info("Backend started — session cleanup task running")
    yield
    # Shutdown: save sessions to disk, clean temp files, cancel task
    logger.info("Shutting down — saving sessions and cleaning temp files…")
    task.cancel()
    await save_all_sessions()
    cleanup_output_dir()
    logger.info("Shutdown cleanup complete")


app = FastAPI(title="Live Markdown Preview API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://localhost", "http://localhost:80"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Session-ID"],
)

@app.get("/health")
async def health_check():
    return {"status": "ok"}

app.include_router(chat_router)
app.include_router(parquet_router)
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket_handler(websocket)