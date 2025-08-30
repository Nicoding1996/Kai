import os
import requests
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
import uuid
from fastapi.middleware.cors import CORSMiddleware

# PDF generation (simple Markdown-ish rendering)
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

# Load environment variables
load_dotenv()

app = FastAPI()

# --- Helper to extract text from OpenAI-compatible responses ---
def extract_message_text(resp_json):
    """
    Be resilient to provider variations:
    - message.content: string
    - message.content: [ {type:'text', text:'...'}, ... ]
    - message.text: string
    Returns empty string if nothing sensible found.
    """
    try:
        choices = resp_json.get("choices") or []
        if not choices:
            return ""
        msg = choices[0].get("message") or {}
        content = msg.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = []
            for c in content:
                if isinstance(c, dict):
                    if "text" in c and isinstance(c["text"], str):
                        parts.append(c["text"])
                    elif c.get("type") == "text" and isinstance(c.get("text"), str):
                        parts.append(c["text"])
                    elif isinstance(c.get("content"), str):
                        parts.append(c["content"])
                elif isinstance(c, str):
                    parts.append(c)
            return "\n".join(parts).strip()
        # Some providers put plain text on 'text'
        if isinstance(msg.get("text"), str):
            return msg["text"].strip()
    except Exception:
        pass
    return ""

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
os.makedirs("server/static/docs", exist_ok=True)
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

# Simple TTS request for playing arbitrary text (e.g., initial greeting)
class TTSRequest(BaseModel):
    text: str

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
                    """You are Kai, an expert AI NLP coach. Your personality is warm, patient, and deeply curious. Your purpose is to be a "Mindful Mirror," helping users find their own solutions by asking insightful, open-ended questions. NEVER give direct advice.

--- CRITICAL RULE: THE FIRST TURN ---
If this is the very first message from the user in the conversation, your ONLY goal is to greet them warmly and ask what's on their mind. Respond naturally to a greeting.
--- END OF CRITICAL RULE ---

Your Conversational Style (After the first turn):
- Use a Natural, Thoughtful Cadence.
- Show Empathy.
- Keep it Concise and end with a question (unless concluding).

Your Coaching Framework (GROW Model enhanced with Well-Formed Outcome):
1. Goal: Help the user define a clear, positive goal.
   Start with: "What would you like to achieve?"
   Deepen with: "What will it look, sound, and feel like when you have that?"

2. Reality: Help them explore their current situation.
   Start with: "What's happening now regarding that goal?"
   Deepen with: "What, if anything, is stopping you?" and "What resources (internal or external) do you already have to help you?"

3. Options: Guide them to brainstorm possibilities.
   Start with: "What are all the possible things you could do?"
   Deepen with: "What would you do if you knew you couldn't fail?"

4. Will & Conclude: Help them commit to action and define success.
   Start with: "What is the very first small step you will take?"
   Deepen with: "How will you know you've successfully achieved your goal? What will be the evidence?"
   Conclusion Trigger: Once the user has clearly stated a specific action they will take, affirm their decision and end the conversation gracefully.
"""
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
        resp_json = response.json()
        ai_text_response = extract_message_text(resp_json)
        if not ai_text_response:
            # Provide a sane fallback so the client doesn't crash
            ai_text_response = "I created your summary, but the response format was unexpected."

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
            "You are a highly skilled analyst. Your task is to provide a concise, well-structured summary of the following coaching conversation. "
            "**Format the entire summary using Markdown.** Use headings for 'Key Goals', 'Major Breakthroughs', and 'Actionable Next Steps', "
            "and use bullet points for the items in each section."
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
        resp_json = response.json()
        summary_text = extract_message_text(resp_json)
        if not summary_text:
            summary_text = "Summary could not be extracted from the provider response."

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

# --- Summary PDF API Endpoint ---
@app.post("/api/summary_pdf")
async def generate_summary_pdf(request: SummaryRequest):
    """
    Generate a Markdown-formatted summary (like /api/summary) and deliver it as a PDF file.
    """
    try:
        # 1) First, reuse the summarization call to get Markdown text
        api_key = os.getenv("REQUESTY_API_KEY")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        system_prompt = (
            "You are a highly skilled analyst. Your task is to provide a concise, well-structured summary of the following coaching conversation. "
            "**Format the entire summary using Markdown.** Use headings for 'Key Goals', 'Major Breakthroughs', and 'Actionable Next Steps', "
            "and use bullet points for the items in each section."
        )

        messages = [{"role": "system", "content": system_prompt}]
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
        resp_json = response.json()
        summary_md = extract_message_text(resp_json)
        if not summary_md:
            summary_md = "Summary could not be extracted from the provider response."

        # 2) Convert basic Markdown to a simple PDF
        file_name = f"{uuid.uuid4()}.pdf"
        file_path = f"server/static/docs/{file_name}"

        styles = getSampleStyleSheet()
        doc = SimpleDocTemplate(file_path, pagesize=letter, title="Kai Session Summary")
        flow = []

        def add_paragraph(text, style=styles["BodyText"], space=6):
            flow.append(Paragraph(text, style))
            flow.append(Spacer(1, space))

        bullets = []
        for raw_line in summary_md.splitlines():
            line = raw_line.rstrip()
            if not line.strip():
                # flush any pending bullets
                if bullets:
                    flow.append(ListFlowable([ListItem(Paragraph(x, styles["BodyText"])) for x in bullets], bulletType="bullet"))
                    flow.append(Spacer(1, 6))
                    bullets.clear()
                flow.append(Spacer(1, 6))
                continue

            if line.startswith("# "):
                # flush bullets
                if bullets:
                    flow.append(ListFlowable([ListItem(Paragraph(x, styles["BodyText"])) for x in bullets], bulletType="bullet"))
                    flow.append(Spacer(1, 6))
                    bullets.clear()
                add_paragraph(f"<b>{line[2:].strip()}</b>", styles["Heading1"], space=10)
            elif line.startswith("## "):
                if bullets:
                    flow.append(ListFlowable([ListItem(Paragraph(x, styles["BodyText"])) for x in bullets], bulletType="bullet"))
                    flow.append(Spacer(1, 6))
                    bullets.clear()
                add_paragraph(f"<b>{line[3:].strip()}</b>", styles["Heading2"], space=8)
            elif line.lstrip().startswith(("- ", "* ")):
                bullets.append(line.lstrip()[2:].strip())
            else:
                # normal paragraph
                if bullets:
                    flow.append(ListFlowable([ListItem(Paragraph(x, styles["BodyText"])) for x in bullets], bulletType="bullet"))
                    flow.append(Spacer(1, 6))
                    bullets.clear()
                add_paragraph(line, styles["BodyText"], space=6)

        if bullets:
            flow.append(ListFlowable([ListItem(Paragraph(x, styles["BodyText"])) for x in bullets], bulletType="bullet"))
            flow.append(Spacer(1, 6))
            bullets.clear()

        doc.build(flow)

        pdf_url = f"/static/docs/{file_name}"
        return {"pdf_url": pdf_url}

    except Exception as e:
        print(f"PDF summary error: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate PDF summary.")

# --- Text-to-Speech API Endpoint (for initial greeting etc.) ---
@app.post("/api/tts")
async def tts(request: TTSRequest):
    try:
        text = request.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="Text is required.")
        voice_id = os.getenv("ELEVENLABS_VOICE_ID")
        audio_stream = elevenlabs_client.text_to_speech.stream(
            text=text,
            voice_id=voice_id,
        )
        file_name = f"{uuid.uuid4()}.mp3"
        file_path = f"server/static/audio/{file_name}"
        with open(file_path, "wb") as f:
            for chunk in audio_stream:
                f.write(chunk)
        audio_url = f"/static/audio/{file_name}"
        return {"audio_url": audio_url}
    except Exception as e:
        print(f"TTS error: {e}")
        raise HTTPException(status_code=500, detail="Failed to synthesize speech.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)