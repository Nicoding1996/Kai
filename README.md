# Kai - Your AI Coach

An immersive, voice-interactive AI coach available 24/7, designed to help you find your own solutions through the power of conversation.

---


## The Vision

High-quality personal coaching is a powerful tool for growth, but it's often inaccessible due to cost, scheduling, and the simple difficulty of finding the right coach. Our team was inspired to solve this.** We wanted to use the power of modern AI to create a supportive, insightful coaching experience that was available to anyone, anytime.

## What it Does

**Kai** is a personal AI coach that provides a safe, non-judgmental space to explore your goals and challenges. Through natural, voice-driven conversation, Kai guides you using proven NLP frameworks to help you overcome limiting beliefs, clarify your objectives, and commit to actionable steps.

## ✨ Core Features

*   **Immersive, Orb-Centric UI:** A clean, minimalist interface that focuses on the conversation, with a central orb that animates and reacts to the flow of dialogue.
*   **Dual Interaction Modes:**
    *   **Focus Mode:** A deliberate "Tap-to-Start, Tap-to-Stop" interaction.
    *   **Hands-Free Mode:** A magical conversational mode with automatic silence detection for a seamless, natural flow.
*   **Advanced AI Coaching:** Kai's intelligence is driven by a sophisticated system prompt that combines the conversational **GROW model** with the deep, analytical questions from the NLP **Well-Formed Outcome pattern**.
*   **Custom AI Personality & Voice:** Kai has a warm, empathetic persona and a unique, calming voice generated in real-time by ElevenLabs.
*   **Downloadable Session Summaries:** At the end of a session, download a beautifully formatted summary in either **Markdown or PDF format**, outlining your key goals, breakthroughs, and actionable next steps.

###  browsers-compatibility-and-important-notes
This application uses the Web Speech API for real-time voice recognition. This is an experimental browser technology that is currently best supported by desktop versions of **Google Chrome**.

For the best experience, please use Google Chrome to view the live demo. If you are using the Brave browser, you must **disable Shields** for this site for the speech recognition to function correctly.

## 🛠️ Tech Stack

*   **Frontend:** SvelteKit, Tailwind CSS
*   **Backend:** Python, FastAPI
*   **AI Gateway:** Requesty
*   **AI Model:** Gemini 1.5 Flash
*   **Text-to-Speech:** ElevenLabs
*   **Deployment:** Vercel
*   **Core AI Assistant:** Roocode / Kilo Code

## ⚙️ Running the Project Locally

**1. Prerequisites:**
*   You will need your own API keys from [Requesty](https://app.requesty.ai/) and [ElevenLabs](https://elevenlabs.io/).

**2. Setup:**
*   Clone this repository.
*   In the `server/` directory, create a file named `.env` and populate it using the `.env.example` file as a template.

**3. Run the Backend:**
```bash
# From the project's root directory
cd server
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python main.py


# From the project's root directory, in a new terminal
cd client
npm install
npm run dev
