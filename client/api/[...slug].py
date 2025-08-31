# Expose the FastAPI ASGI app directly for Vercel's Python Runtime.
# The FastAPI app already defines routes under /api/*.
from server.main import app as app