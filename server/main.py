import os
import requests
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
import uuid
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

app = FastAPI()

origins = ["http://localhost:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

elevenlabs_client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

os.makedirs("server/static/audio", exist_ok=True)
app.mount("/static", StaticFiles(directory="server/static"), name="static")

class ConversationRequest(BaseModel):
    text: str
    history: list

class ConversationResponse(BaseModel):
    text: str
    audio_url: str

@app.post("/api/conversation", response_model=ConversationResponse)
async def handle_conversation(request: ConversationRequest):
    try:
        api_key = os.getenv("REQUESTY_API_KEY")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        
        # Construct the messages payload from history
        messages = [
            {"role": "system", "content": "You are Kai, a helpful and empathetic AI NLP coach..."}
        ]
        for message in request.history:
            messages.append({"role": message['role'], "content": message['text']})
        
        payload = {
            "model": "roquesty/gemini-2.5-pro",
            "messages": messages
        }
        
        # Corrected URL
        response = requests.post("https://api.requesty.ai/v1/chat/completions", headers=headers, json=payload)
        response.raise_for_status() # This will raise an error for 4xx or 5xx responses
        ai_text_response = response.json()["choices"][0]["message"]["content"]

        voice_id = os.getenv("ELEVENLABS_VOICE_ID")
        audio_stream = elevenlabs_client.generate(
            text=ai_text_response,
            voice=voice_id,
            model="eleven_multilingual_v2"
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
        print(f"Response content: {http_err.response.content}")
        raise HTTPException(status_code=http_err.response.status_code, detail="Error from AI service.")
    except Exception as e:
        print(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred.")

# (We are removing the summary endpoint for now to focus on the core functionality)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


# Final version for hackathon
