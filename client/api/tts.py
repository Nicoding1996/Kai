import sys
from pathlib import Path

# Ensure the repository root (which contains the "server" package) is on sys.path
CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent.parent  # .../client/api -> .../ (repo root)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Import the FastAPI ASGI app defined in server/main.py
from server.main import app as full_app  # noqa: E402


# Vercel Python Serverless Function entrypoint:
# This ASGI wrapper rewrites the incoming path to the FastAPI route defined in server/main.py.
# The client calls /api/tts, and server.main defines @app.post("/api/tts"), so we normalize the path.
async def app(scope, receive, send):
    if scope.get("type") in ("http", "websocket"):
        local_scope = dict(scope)
        # Force the path that FastAPI expects
        local_scope["path"] = "/api/tts"
        await full_app(local_scope, receive, send)
    else:
        # For non-http/websocket (e.g. lifespan), just pass through
        await full_app(scope, receive, send)