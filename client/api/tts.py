import sys
import os

# --- THE FIX ---
# Add the parent directory (which is the client directory) to the Python path
# Then add the server directory, which is a sibling to the client directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'server')))
# --- END OF FIX ---

from server.main import app as full_app
from fastapi.testclient import TestClient

app = TestClient(full_app)

def handler(request):
    response = app.post("/api/tts", json=request.json)
    return response