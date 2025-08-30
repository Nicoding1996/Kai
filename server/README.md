# Kai - The AI NLP Coach (Backend)

This directory contains the Python FastAPI backend for the "Kai" application.

## Setup

1.  **Create a virtual environment:**
    ```bash
    python -m venv .venv
    ```

2.  **Activate the virtual environment:**
    *   **Windows:**
        ```bash
        .venv\Scripts\activate
        ```
    *   **macOS/Linux:**
        ```bash
        source .venv/bin/activate
        ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Create a `.env` file:**
    Create a `.env` file in this directory and add your API keys:
    ```
    GOOGLE_API_KEY="YOUR_GOOGLE_API_KEY"
    ELEVENLABS_API_KEY="YOUR_ELEVENLABS_API_KEY"
    ```

## Running the Server

To run the FastAPI server, use the following command:

```bash
uvicorn main:app --reload
```

The server will be available at `http://127.0.0.1:8000`.