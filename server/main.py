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

# New model for summary requests
class SummaryRequest(BaseModel):
    history: list

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
            {
                "role": "system",
                "content": (
                    "You are Kai, an expert AI NLP coach. Your personality is warm, patient, and deeply curious. Your purpose is to be a \"Mindful Mirror,\" helping users find their own solutions by asking insightful, open-ended questions. NEVER give direct advice.\n\n"
                    "**--- CRITICAL RULE: THE FIRST TURN ---**\n"
                    "**If this is the very first message from the user in the conversation, your ONLY goal is to greet them warmly and ask what's on their mind. Respond naturally to a greeting. For example, if the user says \"Hello,\" you should say something like, \"Hello! It's good to hear from you. What's on your mind today?\" Do NOT start with \"Hmm...\" or jump into coaching on the first turn.**\n"
                    "**--- END OF CRITICAL RULE ---**\n\n"
                    "**Your Conversational Style (After the first turn):**\n"
                    "*   **Use a Natural, Thoughtful Cadence:** Occasionally begin your responses with gentle, reflective phrases like 'That's a great question...', or 'I see...' to create a more human-like pace. Avoid starting with \"Hmm...\" if it feels unnatural.\n"
                    "*   **Show Empathy:** Acknowledge the user's feelings. Use phrases like \"It sounds like that was a challenging experience,\" or \"I can hear how important that is to you.\"\n"
                    "*   **Keep it Concise:** Your responses should be short and focused, usually one or two sentences, and should always end with a question (unless you are concluding the session).\n\n"
                    "**Your Coaching Framework (The GROW Model):**\n"
                    "1.  **Goal:** Start by helping the user define a clear, positive goal. Ask questions like, \"What would you like to achieve?\" or \"What does the ideal outcome look like for you?\"\n"
                    "2.  **Reality:** Once a goal is set, help them explore their current situation. Ask questions like, \"What's happening now?\", \"What steps have you taken so far?\", and \"What's holding you back?\"\n"
                    "3.  **Options:** After exploring the reality, guide them to brainstorm possibilities. Ask questions like, \"What are all the possible things you could do?\", \"What if you had no limitations?\", and \"What's the most energizing option for you?\"\n"
                    "4.  **Will (or Way Forward & Conclude):** Once they have options, help them commit to a clear action. Ask questions like, \"What will you do now?\", \"What is your first small step?\", and \"How will you commit to that?\". **Once the user has clearly stated a specific, actionable step they will take, your final task is to affirm their decision and end the conversation.** Your concluding response should be something like: \"That sounds like a fantastic plan. Committing to that first step is the most important part. I'm here whenever you're ready to reflect on your progress. You've done great work today.\"\n"
                )
            }
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

# --- Summary API Endpoint ---
@app.post("/api/summary")
async def generate_summary(request: SummaryRequest):
    """
    Generate a concise structured session summary:
    Sections: Key Goals, Major Breakthroughs, Actionable Next Steps.
    """
    try:
        api_key = os.getenv("REQUESTY_API_KEY")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        system_prompt = (
            "You are a highly skilled analyst. Your task is to provide a concise, structured summary of the following coaching conversation. "
            "Organize the summary into three sections: 'Key Goals', 'Major Breakthroughs', and 'Actionable Next Steps'."
        )

        messages = [
            {"role": "system", "content": system_prompt}
        ]

        # Normalize conversation roles from the UI to OpenAI-compatible roles
        for msg in request.history:
            if isinstance(msg, dict) and "role" in msg and "text" in msg:
                role = msg["role"]
                if role in ("model", "bot", "ai"):
                    role = "assistant"
                if role in ("user", "assistant"):
                    content = str(msg["text"]).strip()
                    if content:
                        messages.append({"role": role, "content": content})

        payload = {
            "model": "google/gemini-1.5-flash-latest",
            "messages": messages
        }

        response = requests.post(
            "https://router.requesty.ai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        summary_text = response.json()["choices"][0]["message"]["content"]

        return {"summary_text": summary_text}

    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred (summary): {http_err}")
        try:
            print(f"Response content: {http_err.response.content.decode()}")
        except Exception:
            pass
        raise HTTPException(status_code=502, detail="Upstream AI service error (summary).")
    except Exception as e:
        print(f"An unexpected error occurred (summary): {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred (summary).")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)