import sys
import os

# --- THE FIX ---
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'server')))
# --- END OF FIX ---

from server.main import app as full_app
from fastapi.testclient import TestClient

app = TestClient(full_app)

def handler(request):
    # Reconstruct the original path for FastAPI
    original_path = f"/api/{request.query_params.get('slug', '')}"
    
    # Forward the request to the FastAPI app
    response = app.request(
        method=request.method,
        url=original_path,
        json=request.json if request.method == "POST" else None
    )
    return response