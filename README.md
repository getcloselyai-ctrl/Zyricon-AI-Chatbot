# Zyricon — AI Assistant

Zyricon is a full-stack AI chat application built with **React**, **Vite**, **FastAPI**, and **Google Gemini**. It provides a dark chat workspace with streaming assistant responses, persistent conversations, file attachments, and an editable memory manager.

> This repository contains the application source. API credentials and local conversation data are intentionally excluded.

## Features

- Streaming assistant responses powered by the Gemini API
- Persistent conversation history backed by SQLite
- Create, rename, delete, search, and reopen conversations
- Upload and analyze supported documents, spreadsheets, text files, and images
- Markdown rendering, GitHub-flavored Markdown, syntax-highlighted code blocks, and copy actions
- Memory manager with automatic-memory controls and editable saved memories
- Responsive dark interface with animated message and intro transitions

## Technology stack

**Frontend:** React 19, Vite, JavaScript, Lucide React, React Markdown, Remark GFM, Highlight.js  
**Backend:** Python, FastAPI, Uvicorn, Pydantic, Google Gen AI SDK, SQLite  
**Document processing:** PyMuPDF, python-docx, pandas, openpyxl

## Project structure

```text
Zyricon-AI-Chatbot/
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── App.css
│   │   ├── index.css
│   │   └── main.jsx
│   ├── index.html
│   ├── package.json
│   ├── package-lock.json
│   ├── vite.config.js
│   └── eslint.config.js
└── .gitignore
```

## Prerequisites

- Python 3.10 or newer
- Node.js 20.19+ or 22.12+ (required by current Vite releases)
- A Google Gemini API key

## Run locally

### 1. Clone the repository

```bash
git clone https://github.com/getcloselyai-ctrl/Zyricon-AI-Chatbot.git
cd Zyricon-AI-Chatbot
```

### 2. Configure and start the backend

```bash
cd backend
python -m venv .venv
```

Activate the virtual environment:

**Windows PowerShell**

```powershell
.venv\Scripts\Activate.ps1
```

**macOS / Linux**

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` inside `backend/` and replace the placeholder with your Gemini API key:

```env
GEMINI_API_KEY=your_actual_api_key
```

Start the API:

```bash
uvicorn main:app --reload --port 8000
```

The API runs at `http://127.0.0.1:8000`. Interactive API documentation is available at `http://127.0.0.1:8000/docs`.

### 3. Start the frontend

Open a second terminal from the repository root:

```bash
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite (normally `http://localhost:5173`).

## Configuration notes

- The frontend currently targets the local backend at `http://127.0.0.1:8000`. For a hosted deployment, update the API base URL in `frontend/src/App.jsx` and configure the backend CORS origins for the deployed frontend domain.
- The backend creates `zyricon.db` locally on first run. This database is not included in version control. Conversation history is therefore local to the backend instance unless persistent storage is configured for deployment.
- Keep `backend/.env` private. Never paste API keys into source code or commit them.

## Supported attachments

The frontend accepts PDF, DOCX, TXT, CSV, XLSX, PNG, JPG, JPEG, and WEBP files. The current UI enforces a maximum of five attachments per message and a 10 MB limit per file.

## Security

- Do not commit `.env` files, API keys, SQLite databases, user uploads, or local environment folders.
- Rotate the Gemini API key immediately if it is ever exposed publicly.
- Before deploying publicly, review authentication, rate limiting, CORS allowlists, data retention, and file-upload handling for your intended usage.

## License

No license has been added yet. Unless a license is added, normal copyright restrictions apply to reuse of this source.
