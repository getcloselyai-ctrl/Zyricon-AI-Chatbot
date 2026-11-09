# Zyricon | AI Chatbot

<p align="center">
  <img src="https://readme-typing-svg.demolab.com?font=Inter&weight=600&size=27&duration=3500&pause=1200&color=94A3B8&center=true&vCenter=true&width=650&lines=Zyricon+AI;Intelligent+Conversations.;A+Smarter+AI+Workspace." alt="Zyricon AI" />
</p>

<p align="center">
  <strong>A Full-Stack AI Conversational Platform</strong>
  <br />
  An intelligent workspace for AI-powered conversations, document analysis, conversation management and contextual memory.
</p>

<p align="center">
  <a href="https://zyricon-web-pg.onrender.com/">
    <img src="https://img.shields.io/badge/ACCESS_APPLICATION-Launch_Zyricon-334155?style=for-the-badge&labelColor=111827" alt="Launch Zyricon" />
  </a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/React-19-64748B?style=flat-square&logo=react&logoColor=white" />
  <img src="https://img.shields.io/badge/FastAPI-Backend-64748B?style=flat-square&logo=fastapi&logoColor=white" />
  <img src="https://img.shields.io/badge/Python-Backend-64748B?style=flat-square&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Google_Gemini-AI-64748B?style=flat-square&logo=google&logoColor=white" />
  <img src="https://img.shields.io/badge/SQLite-Database-64748B?style=flat-square&logo=sqlite&logoColor=white" />
</p>

---

## Overview

Zyricon is a full-stack AI conversational application developed to provide an integrated environment for interacting with large language models.

Built using React, FastAPI and Google's Gemini API, the platform combines conversational AI capabilities with persistent conversation management, document processing and contextual memory functionality.

The application focuses on usability, modular architecture and the integration of modern AI capabilities into a practical web interface.

## Core Capabilities

| Capability | Implementation |
|---|---|
| AI Conversations | Gemini-powered conversational interface |
| Response Streaming | Progressive assistant response generation |
| Conversation Management | Create, search, rename, delete and retrieve conversations |
| Document Analysis | Processing of documents, spreadsheets and images |
| Contextual Memory | Memory management and automatic-memory controls |
| Rich Text Rendering | Markdown and GitHub-flavored Markdown |
| Code Presentation | Syntax highlighting and code-copy functionality |
| User Interface | Responsive interface with animated transitions |

## Technology Stack

**Frontend**
- React 19
- Vite
- JavaScript
- Lucide React
- React Markdown
- Remark GFM
- Highlight.js

**Backend**
- Python
- FastAPI
- Uvicorn
- Pydantic
- Google Gen AI SDK

**Database**
- SQLite

**Document Processing**
- PyMuPDF
- python-docx
- Pandas
- OpenPyXL

**Deployment**
- Render

## Architecture

The application follows a frontend-backend architecture, with the React client communicating with a FastAPI backend that integrates Gemini AI and SQLite persistence.

```text
              CLIENT
                |
                v
          REACT FRONTEND
             (Vite)
                |
                v
          FASTAPI BACKEND
                |
         +------+------+
         |             |
         v             v
     GEMINI API      SQLITE
         |
         v
    AI GENERATION
         |
         v
    RESPONSE STREAM
         |
         v
     REACT CLIENT
```

## Repository Structure

```text
Zyricon-AI-Chatbot/
│
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── App.css
│   │   ├── index.css
│   │   └── main.jsx
│   │
│   ├── index.html
│   ├── package.json
│   ├── package-lock.json
│   ├── vite.config.js
│   └── eslint.config.js
│
└── .gitignore
```

## Local Development

### Requirements

- Python 3.10 or later
- Node.js 20.19+ or 22.12+
- Google Gemini API key

### 1. Clone the repository

```bash
git clone https://github.com/getcloselyai-ctrl/Zyricon-AI-Chatbot.git

cd Zyricon-AI-Chatbot
```

### 2. Configure the backend

```bash
cd backend

python -m venv .venv
```

Activate the virtual environment.

**Windows PowerShell**

```powershell
.venv\Scripts\Activate.ps1
```

**macOS / Linux**

```bash
source .venv/bin/activate
```

Install the dependencies:

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Create a `.env` file inside the backend directory.

```env
GEMINI_API_KEY=your_actual_api_key
```

Obtain an API key from [Google AI Studio](https://aistudio.google.com/).

### 4. Launch the backend

```bash
uvicorn main:app --reload --port 8000
```

Backend endpoint:

`http://127.0.0.1:8000`

Interactive API documentation:

`http://127.0.0.1:8000/docs`

### 5. Launch the frontend

Open a separate terminal.

```bash
cd frontend

npm install

npm run dev
```

Access the development server at the local URL provided by Vite, typically:

`http://localhost:5173`

## Supported File Formats

| File Category | Formats |
|---|---|
| Documents | PDF, DOCX, TXT |
| Spreadsheets | CSV, XLSX |
| Images | PNG, JPG, JPEG, WEBP |

**Upload constraints**
- Maximum 5 attachments per message.
- Maximum 10 MB per attachment.

## Configuration and Security

- Store sensitive credentials in environment variables.
- Never commit API keys or `.env` files.
- Configure backend CORS origins for the deployment environment.
- Ensure database persistence is configured appropriately for hosted deployments.
- Review authentication, rate limiting, data retention and upload validation before production use.

## Engineering Scope

The project demonstrates practical implementation of:

- Large Language Model integration
- Full-stack application architecture
- RESTful API development
- Database persistence
- Document processing pipelines
- Contextual memory management
- Asynchronous response streaming
- Frontend-backend integration
- Application deployment

## Potential Enhancements

- Authentication and user-specific workspaces
- Advanced retrieval-augmented generation (RAG)
- Extended contextual memory capabilities
- Multi-model AI integration
- Voice interaction
- Conversation export and organization

## Developer

**Akshat Doshi**

Data Science | Machine Learning | AI Engineering

[GitHub Profile](https://github.com/getcloselyai-ctrl)

---

<p align="center">
  <strong>ZYRICON</strong>
  <br />
  <sub>Intelligence. Context. Productivity.</sub>
</p>
