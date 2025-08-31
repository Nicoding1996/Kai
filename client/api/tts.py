from server.main import app as full_app
from fastapi.testclient import TestClient

# Use the FastAPI app directly via TestClient inside the serverless function
app = TestClient(full_app)

def handler(request):
    # Forward to FastAPI's /api/tts endpoint
    response = app.post("/api/tts", json=request.json)
    return response