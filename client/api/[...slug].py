import sys
from pathlib import Path

# Ensure the repository root (which contains the "server" package) is on sys.path
CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent.parent  # .../client/api -> repo root
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Import the FastAPI ASGI app defined in server/main.py
from server.main import app as full_app  # noqa: E402


# Vercel Python Serverless Function entrypoint (dynamic catch‑all under /api/*).
# Our FastAPI declares routes with "/api/*" prefixes (e.g., "/api/tts").
# Vercel's function scope usually contains the path AFTER "/api", like "/tts".
# We normalize it back to "/api/..." so FastAPI route matching succeeds.
async def app(scope, receive, send):
    if scope.get("type") in ("http", "websocket"):
        local_scope = dict(scope)
        path = local_scope.get("path", "/") or "/"

        # If Vercel passed "/conversation", "/tts", "/summary", etc., prefix it with "/api"
        if not path.startswith("/api/"):
            if path == "/":
                # request to "/api" root
                new_path = "/api"
            else:
                new_path = "/api" + path
            local_scope["path"] = new_path

        await full_app(local_scope, receive, send)
    else:
        # lifespan and other events pass through unchanged
        await full_app(scope, receive, send)