# Kai — Your AI Coach (Backend)

---

## 🚀 Live demo & demo video

- Live: [LINK_TO_YOUR_VERCEL_DEPLOYMENT]
- Demo video: [LINK_TO_YOUR_YOUTUBE_VIDEO]

---

## Overview

Kai is a lightweight FastAPI backend powering a web-based AI coaching assistant. It handles conversational requests, generates session summaries, renders session PDFs, and synthesizes speech using ElevenLabs. The frontend is a SvelteKit app that connects to these endpoints for a natural voice-first coaching experience.

## Problem & solution

High-quality personal coaching is often expensive and unavailable on demand. Kai provides an always-available conversational assistant that helps users reflect and plan using coaching techniques (GROW + Well-Formed Outcome), delivered through voice and text.

## ✨ Features

- Real-time conversational API: `/api/conversation`
- Text-to-speech endpoint for greetings: `/api/tts`
- Structured session summaries and on-demand PDF generation: `/api/summary`, `/api/summary_pdf`
- Generated audio files saved to `server/static/audio/` and PDFs to `server/static/docs/`
- Graceful degradation when TTS is unavailable — conversation text still returns

## 🛠️ Tech stack

- Frontend: SvelteKit, Tailwind CSS
- Backend: Python, FastAPI, Requests
- TTS: ElevenLabs
- AI Gateway: Requesty (Gemini model)

## ⚙️ Environment variables

Create a `.env` in the `server/` directory with:

```
REQUESTY_API_KEY="YOUR_REQUESTY_API_KEY"
ELEVENLABS_API_KEY="YOUR_ELEVENLABS_API_KEY"
ELEVENLABS_VOICE_ID="YOUR_ELEVENLABS_VOICE_ID"
```

(Optionally keep a `.env.example` file in the repo without real secrets.)

## 🚀 Run locally (Windows)

1. From the repo root, create & activate a Python virtual environment:

```
cd server
python -m venv .venv
.\.venv\Scripts\activate
```

2. Install dependencies and start the backend:

```
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

3. Start the frontend (new terminal, from repo root):

```
cd client
npm install
npm run dev
```

The frontend runs at http://localhost:5173 and the backend at http://localhost:8000.

## 💡 Developer notes

- Generated audio files are saved in [`server/static/audio/`](server/static/audio/:1). Generated PDFs are placed under [`server/static/docs/`](server/static/docs/:1). The repo `.gitignore` is configured to ignore these generated files.
- If you change AI provider or the model payload, update the request code in [`server/main.py`](server/main.py:156).
- TTS errors are mapped to clear HTTP codes; the conversation endpoint will still return text when audio fails.

## Deployment

This project includes `vercel.json` for deployment. Vercel will route `/api/*` to the FastAPI app. See the root `vercel.json` for routing configuration.

## Troubleshooting

- If TTS returns quota errors you'll see a 429 from `/api/tts`; either add credits or switch voice/model to reduce cost.
- To stop tracking generated PDF files already committed:

```
git rm --cached server/static/docs/*.pdf
git commit -m "Stop tracking generated docs"
```
