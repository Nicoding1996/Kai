import os
import requests
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
import uuid
from fastapi.middleware.cors import CORSMiddleware

# Load environment variables
load_dotenv()

app = FastAPI()

# --- CORS Configuration ---
origins = [
    "http://localhost:5173",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Client Initialization ---
elevenlabs_client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

# --- Static File Serving ---
os.makedirs("server/static/audio", exist_ok=True)
app.mount("/static", StaticFiles(directory="server/static"), name="static")

# --- Pydantic Models ---
class ConversationRequest(BaseModel):
    text: str
    history: list

class ConversationResponse(BaseModel):
    text: str
    audio_url: str

# --- API Endpoint ---
@app.post("/api/conversation", response_model=ConversationResponse)
async def handle_conversation(request: ConversationRequest):
    try:
        api_key = os.getenv("REQUESTY_API_KEY")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        
        messages = [
            {"role": "system", "content": "You are Kai, a helpful AI NLP coach. Your goal is to be a mindful mirror, guiding users to their own solutions through curious, non-judgmental questions. Keep your responses concise."}
        ]
        # Include only recent user/assistant turns; exclude any UI 'system' rows
        for message in request.history[-8:]:
            if 'role' in message and 'text' in message:
                role = message['role']
                # Map UI roles to API roles
                if role in ('model', 'bot', 'ai'):
                    role = 'assistant'
                if role in ('user', 'assistant'):
                    content = str(message['text']).strip()
                    if content:
                        messages.append({"role": role, "content": content})
        
        messages.append({"role": "user", "content": request.text})

        # --- THIS IS THE ONLY PART THAT MATTERS ---
        # We use the one correct URL and the one correct model name.
        payload = {
            "model": "google/gemini-1.5-flash-latest",
            "messages": messages
        }
        
        # Debug: uncomment to inspect payload shape if needed
        # print("Payload being sent to router:", payload)
        response = requests.post(
            "https://router.requesty.ai/v1/chat/completions",
            headers=headers,
            json=payload
        )
        # --- END OF CRITICAL SECTION ---

        response.raise_for_status()
        ai_text_response = response.json()["choices"][0]["message"]["content"]

        voice_id = os.getenv("ELEVENLABS_VOICE_ID")
        audio_stream = elevenlabs_client.text_to_speech.stream(
            text=ai_text_response,
            voice_id=voice_id,
        )

        file_name = f"{uuid.uuid4()}.mp3"
        file_path = f"server/static/audio/{file_name}"
        
        with open(file_path, "wb") as f:
            for chunk in audio_stream:
                f.write(chunk)
        
        audio_url = f"/static/audio/{file_name}"

        return ConversationResponse(text=ai_text_response, audio_url=audio_url)

    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
        print(f"Response content: {http_err.response.content.decode()}")
        raise HTTPException(status_code=502, detail="Upstream AI service error.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)