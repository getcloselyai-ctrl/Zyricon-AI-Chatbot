import os
import sqlite3
import threading
import json
import io
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from google import genai

# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = "gemini-3.5-flash-lite"
DATABASE_PATH = BASE_DIR / "zyricon.db"

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

app = FastAPI(
    title="Zyricon API",
    description="AI assistant with persistent conversation history",
    version="4.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "https://zyricon-web-pg.onrender.com",
        "https://zyricon-web.onrender.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_cancelled_requests = set()
_cancel_lock = threading.Lock()


# --------------------------------------------------
# DATABASE
# --------------------------------------------------

def get_db():
    connection = sqlite3.connect(DATABASE_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id)
                    REFERENCES conversations(id)
                    ON DELETE CASCADE
            )
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_conversation
            ON messages(conversation_id, id)
        """)
        columns = {
            row["name"]
            for row in db.execute("PRAGMA table_info(messages)").fetchall()
        }
        if "attachments_json" not in columns:
            db.execute("""
                ALTER TABLE messages
                ADD COLUMN attachments_json TEXT NOT NULL DEFAULT '[]'
            """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS conversation_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                message_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                extracted_text TEXT,
                file_data BLOB,
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id)
                    REFERENCES conversations(id)
                    ON DELETE CASCADE,
                FOREIGN KEY (message_id)
                    REFERENCES messages(id)
                    ON DELETE CASCADE
            )
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversation_files
            ON conversation_files(conversation_id, message_id)
        """)

        # Persistent user memory.
        db.execute("""
            CREATE TABLE IF NOT EXISTS user_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'general',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_memories_category
            ON user_memories(category)
        """)

        # Application settings.
        db.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        db.execute("""
            INSERT OR IGNORE INTO app_settings (key, value, updated_at)
            VALUES ('automatic_memory', 'true', ?)
        """, (now_iso(),))


# --------------------------------------------------
# UTILITIES
# --------------------------------------------------

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def is_cancelled(request_id):
    if not request_id:
        return False
    with _cancel_lock:
        return request_id in _cancelled_requests


def mark_cancelled(request_id):
    if not request_id:
        return
    with _cancel_lock:
        _cancelled_requests.add(request_id)


def clear_cancelled(request_id):
    if not request_id:
        return
    with _cancel_lock:
        _cancelled_requests.discard(request_id)


def require_client():
    if client is None:
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY is missing. Add it to backend/.env.",
        )


def conversation_exists(conversation_id):
    with get_db() as db:
        row = db.execute(
            "SELECT id FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
    return row is not None


def get_setting(key, default=None):
    with get_db() as db:
        row = db.execute(
            "SELECT value FROM app_settings WHERE key = ?",
            (key,),
        ).fetchone()
    return row["value"] if row else default


def set_setting(key, value):
    with get_db() as db:
        db.execute("""
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
        """, (key, str(value), now_iso()))


def automatic_memory_enabled():
    return get_setting("automatic_memory", "true").lower() == "true"


# --------------------------------------------------
# PYDANTIC MODELS
# --------------------------------------------------

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10000)
    request_id: str | None = None


class CreateConversationRequest(BaseModel):
    title: str = Field(default="New chat", min_length=1, max_length=100)


class RenameConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=100)


class EditMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=10000)


class RequestControl(BaseModel):
    request_id: str = Field(min_length=1, max_length=100)


class MemoryCreateRequest(BaseModel):
    memory: str = Field(min_length=2, max_length=500)
    category: str = Field(default="general", max_length=50)


class MemoryUpdateRequest(BaseModel):
    memory: str = Field(min_length=2, max_length=500)
    category: str = Field(default="general", max_length=50)


class MemorySettingsRequest(BaseModel):
    automatic_memory: bool


# --------------------------------------------------
# CONVERSATION HELPERS
# --------------------------------------------------

def get_conversation_messages(conversation_id):
    with get_db() as db:
        rows = db.execute("""
            SELECT id, conversation_id, role, content,
                   created_at, attachments_json
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id ASC
        """, (conversation_id,)).fetchall()

    results = []
    for row in rows:
        item = dict(row)
        try:
            item["attachments"] = json.loads(
                item.pop("attachments_json") or "[]"
            )
        except (TypeError, json.JSONDecodeError):
            item["attachments"] = []
            item.pop("attachments_json", None)
        results.append(item)

    return results


def add_message(conversation_id, role, content, attachments=None):
    with get_db() as db:
        cursor = db.execute("""
            INSERT INTO messages (
                conversation_id, role, content,
                created_at, attachments_json
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            conversation_id,
            role,
            content,
            now_iso(),
            json.dumps(attachments or []),
        ))
        message_id = cursor.lastrowid
        db.execute("""
            UPDATE conversations
            SET updated_at = ?
            WHERE id = ?
        """, (now_iso(), conversation_id))
    return message_id


def update_conversation_title_if_new(conversation_id, message):
    title = message.strip().replace("\n", " ")
    if not title:
        return

    title = title[:45] + ("..." if len(title) > 45 else "")

    with get_db() as db:
        row = db.execute(
            "SELECT title FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()

        if row and row["title"] == "New chat":
            db.execute("""
                UPDATE conversations
                SET title = ?, updated_at = ?
                WHERE id = ?
            """, (title, now_iso(), conversation_id))


# --------------------------------------------------
# PERSISTENT USER MEMORY HELPERS
# --------------------------------------------------

def get_all_memories():
    with get_db() as db:
        rows = db.execute("""
            SELECT id, memory, category, created_at, updated_at
            FROM user_memories
            ORDER BY updated_at DESC, id DESC
        """).fetchall()
    return [dict(row) for row in rows]


def get_memory_context():
    memories = get_all_memories()
    if not memories:
        return ""

    lines = [
        f"- [{item['category']}] {item['memory']}"
        for item in memories[:50]
    ]
    return "\n".join(lines)


def save_memory(memory, category="general"):
    memory = memory.strip()
    category = category.strip().lower() or "general"

    if len(memory) < 2:
        return None

    with get_db() as db:
        existing = db.execute("""
            SELECT id FROM user_memories
            WHERE LOWER(memory) = LOWER(?)
        """, (memory,)).fetchone()

        if existing:
            db.execute("""
                UPDATE user_memories
                SET category = ?, updated_at = ?
                WHERE id = ?
            """, (category, now_iso(), existing["id"]))
            return existing["id"]

        cursor = db.execute("""
            INSERT INTO user_memories (
                memory, category, created_at, updated_at
            )
            VALUES (?, ?, ?, ?)
        """, (memory, category, now_iso(), now_iso()))

        return cursor.lastrowid


def delete_memory(memory_id):
    with get_db() as db:
        cursor = db.execute(
            "DELETE FROM user_memories WHERE id = ?",
            (memory_id,),
        )
    return cursor.rowcount > 0


def clear_all_memories():
    with get_db() as db:
        db.execute("DELETE FROM user_memories")


# --------------------------------------------------
# FILE MEMORY HELPERS
# --------------------------------------------------

MAX_MEMORY_FILES = 20
MAX_MEMORY_TEXT_CHARS = 80000
MAX_MEMORY_IMAGES = 3


def load_conversation_file_context(conversation_id, before_message_id=None):
    with get_db() as db:
        if before_message_id is None:
            rows = db.execute("""
                SELECT id, name, mime_type, extracted_text,
                       file_data, created_at
                FROM conversation_files
                WHERE conversation_id = ?
                ORDER BY id DESC
                LIMIT ?
            """, (conversation_id, MAX_MEMORY_FILES)).fetchall()
        else:
            rows = db.execute("""
                SELECT id, name, mime_type, extracted_text,
                       file_data, created_at
                FROM conversation_files
                WHERE conversation_id = ?
                  AND message_id <= ?
                ORDER BY id DESC
                LIMIT ?
            """, (
                conversation_id,
                before_message_id,
                MAX_MEMORY_FILES,
            )).fetchall()

    return [dict(row) for row in reversed(rows)]


def file_context_parts(files):
    parts = []
    remaining_chars = MAX_MEMORY_TEXT_CHARS
    image_count = 0

    for file in files:
        extracted = file.get("extracted_text") or ""

        if extracted and remaining_chars > 0:
            excerpt = extracted[:remaining_chars]
            remaining_chars -= len(excerpt)
            parts.append({
                "text": (
                    f"\n\nPreviously uploaded file: {file['name']}\n"
                    f"{excerpt}"
                )
            })

        elif (
            file.get("file_data")
            and (file.get("mime_type") or "").startswith("image/")
            and image_count < MAX_MEMORY_IMAGES
        ):
            parts.append({
                "inline_data": {
                    "mime_type": file["mime_type"],
                    "data": file["file_data"],
                }
            })
            image_count += 1

    return parts


# --------------------------------------------------
# GEMINI RESPONSE GENERATION
# --------------------------------------------------

def generate_reply(conversation_id, current_message, before_message_id=None):
    require_client()

    history = get_conversation_messages(conversation_id)

    if before_message_id is not None:
        history = [
            message for message in history
            if message["id"] < before_message_id
        ]

    history = history[-20:]

    contents = []
    for message in history:
        if message["role"] not in ("user", "assistant"):
            continue
        contents.append({
            "role": "model" if message["role"] == "assistant" else "user",
            "parts": [{"text": message["content"]}],
        })

    current_parts = [{"text": current_message}]

    file_context = load_conversation_file_context(
        conversation_id,
        before_message_id,
    )
    current_parts.extend(file_context_parts(file_context))

    memory_context = get_memory_context()

    system_instruction = (
        "You are Zyricon, a helpful AI assistant. "
        "Use the conversation history and relevant uploaded file context "
        "to answer accurately. "
        "The following are saved facts and preferences about the user. "
        "Use them only when relevant. Do not invent additional memories.\n\n"
        f"SAVED USER MEMORIES:\n{memory_context or 'No saved memories.'}"
    )

    contents.append({
        "role": "user",
        "parts": current_parts,
    })

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=contents,
        config={
            "system_instruction": system_instruction,
            "temperature": 0.7,
        },
    )

    return response.text or "I couldn't generate a response. Please try again."


def generate_reply_stream(conversation_id, current_message, before_message_id=None):
    """Yield Gemini response text as soon as each generated chunk is available."""
    require_client()

    history = get_conversation_messages(conversation_id)
    if before_message_id is not None:
        history = [
            message for message in history
            if message["id"] < before_message_id
        ]

    history = history[-20:]
    contents = []

    for message in history:
        if message["role"] not in ("user", "assistant"):
            continue
        contents.append({
            "role": "model" if message["role"] == "assistant" else "user",
            "parts": [{"text": message["content"]}],
        })

    current_parts = [{"text": current_message}]
    file_context = load_conversation_file_context(
        conversation_id,
        before_message_id,
    )
    current_parts.extend(file_context_parts(file_context))

    memory_context = get_memory_context()
    system_instruction = (
        "You are Zyricon, a helpful AI assistant. "
        "Use the conversation history and relevant uploaded file context "
        "to answer accurately. "
        "The following are saved facts and preferences about the user. "
        "Use them only when relevant. Do not invent additional memories.\n\n"
        f"SAVED USER MEMORIES:\n{memory_context or 'No saved memories.'}"
    )

    contents.append({
        "role": "user",
        "parts": current_parts,
    })

    response_stream = client.models.generate_content_stream(
        model=MODEL_NAME,
        contents=contents,
        config={
            "system_instruction": system_instruction,
            "temperature": 0.7,
        },
    )

    for chunk in response_stream:
        chunk_text = getattr(chunk, "text", None)
        if chunk_text:
            yield chunk_text


def stream_reply_response(
    conversation_id,
    user_message,
    request_id,
    before_message_id=None,
    user_message_id=None,
):
    """Return an SSE response and persist the completed (or stopped) answer."""
    def event_stream():
        full_reply = ""
        saved_message = False

        try:
            for token in generate_reply_stream(
                conversation_id,
                user_message,
                before_message_id=before_message_id,
            ):
                if is_cancelled(request_id):
                    break

                full_reply += token
                payload = {"type": "token", "text": token}
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

            cancelled = is_cancelled(request_id)

            if not full_reply and not cancelled:
                full_reply = "I couldn't generate a response. Please try again."
                payload = {"type": "token", "text": full_reply}
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

            if full_reply:
                add_message(conversation_id, "assistant", full_reply)
                saved_message = True

            if full_reply and not cancelled:
                extract_and_save_memories(
                    conversation_id,
                    user_message,
                    full_reply,
                )

            done_payload = {
                "type": "done",
                "success": not cancelled,
                "cancelled": cancelled,
                "conversation_id": conversation_id,
                "message_id": user_message_id,
                "model": MODEL_NAME,
            }
            yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"

        except Exception as error:
            print(f"Streaming generation error: {error}")
            if full_reply and not saved_message:
                add_message(conversation_id, "assistant", full_reply)
            error_payload = {
                "type": "error",
                "message": f"AI response failed: {str(error)}",
            }
            yield f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n"

        finally:
            clear_cancelled(request_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# --------------------------------------------------
# AUTOMATIC MEMORY EXTRACTION
# --------------------------------------------------

def extract_and_save_memories(conversation_id, user_message, assistant_reply):
    if not automatic_memory_enabled() or client is None:
        return

    try:
        existing_memories = get_memory_context()

        prompt = f"""
You are Zyricon's long-term memory extraction system.

Identify only useful, stable facts or preferences about the user
that are likely to help in future conversations.

Examples:
- Long-term goals
- Ongoing projects
- Professional skills and interests
- Stable communication preferences
- Important non-sensitive constraints

Do NOT save:
- Passwords, API keys, tokens, or secret codes
- Financial account credentials
- Precise home addresses or live location
- Highly sensitive personal information
- Temporary questions or one-time requests
- Facts that are only about another person
- Guesses or assumptions

Return ONLY valid JSON in this format:
{{
  "memories": [
    {{
      "memory": "Short factual statement",
      "category": "general"
    }}
  ]
}}

Allowed categories:
general, goal, project, work, preference, skill

If there is nothing worth remembering, return:
{{"memories": []}}

Existing memories:
{existing_memories or "None"}

User message:
{user_message[:5000]}

Assistant reply:
{assistant_reply[:3000]}
"""

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config={
                "temperature": 0.1,
                "response_mime_type": "application/json",
            },
        )

        parsed = json.loads(response.text or '{"memories": []}')
        extracted = parsed.get("memories", [])

        if not isinstance(extracted, list):
            return

        for item in extracted[:5]:
            if not isinstance(item, dict):
                continue

            memory = str(item.get("memory", "")).strip()
            category = str(item.get("category", "general")).strip().lower()

            if category not in {
                "general", "goal", "project",
                "work", "preference", "skill",
            }:
                category = "general"

            if 2 <= len(memory) <= 500:
                save_memory(memory, category)

    except Exception as error:
        # Memory extraction must never break normal chat responses.
        print(f"Automatic memory extraction failed: {error}")


# --------------------------------------------------
# INITIALIZE DATABASE
# --------------------------------------------------

initialize_database()
# --------------------------------------------------
# BASIC ROUTES
# --------------------------------------------------

@app.get("/")
def root():
    return {
        "message": "Zyricon API is running",
        "version": "4.1.0",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "database": "connected",
        "gemini_configured": client is not None,
    }


# --------------------------------------------------
# CONVERSATION ROUTES
# --------------------------------------------------

@app.get("/conversations")
def list_conversations():
    with get_db() as db:
        rows = db.execute("""
            SELECT
                c.id,
                c.title,
                c.created_at,
                c.updated_at,
                (
                    SELECT content
                    FROM messages
                    WHERE conversation_id = c.id
                    ORDER BY id DESC
                    LIMIT 1
                ) AS last_message
            FROM conversations c
            ORDER BY c.updated_at DESC
        """).fetchall()

    return [dict(row) for row in rows]


@app.post("/conversations")
def create_conversation(request: CreateConversationRequest):
    conversation_id = str(uuid4())
    timestamp = now_iso()

    with get_db() as db:
        db.execute("""
            INSERT INTO conversations (
                id, title, created_at, updated_at
            )
            VALUES (?, ?, ?, ?)
        """, (
            conversation_id,
            request.title.strip(),
            timestamp,
            timestamp,
        ))

    return {
        "id": conversation_id,
        "title": request.title.strip(),
        "created_at": timestamp,
        "updated_at": timestamp,
    }


@app.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    with get_db() as db:
        conversation = db.execute("""
            SELECT id, title, created_at, updated_at
            FROM conversations
            WHERE id = ?
        """, (conversation_id,)).fetchone()

        if not conversation:
            raise HTTPException(
                status_code=404,
                detail="Conversation not found",
            )

        messages = db.execute("""
            SELECT id, conversation_id, role, content,
                   created_at, attachments_json
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id ASC
        """, (conversation_id,)).fetchall()

    message_results = []

    for message in messages:
        item = dict(message)
        try:
            item["attachments"] = json.loads(
                item.pop("attachments_json") or "[]"
            )
        except (TypeError, json.JSONDecodeError):
            item.pop("attachments_json", None)
            item["attachments"] = []

        message_results.append(item)

    return {
        **dict(conversation),
        "messages": message_results,
    }


@app.patch("/conversations/{conversation_id}")
def rename_conversation(
    conversation_id: str,
    request: RenameConversationRequest,
):
    with get_db() as db:
        cursor = db.execute("""
            UPDATE conversations
            SET title = ?, updated_at = ?
            WHERE id = ?
        """, (
            request.title.strip(),
            now_iso(),
            conversation_id,
        ))

    if cursor.rowcount == 0:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    return {
        "success": True,
        "id": conversation_id,
        "title": request.title.strip(),
    }


@app.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str):
    with get_db() as db:
        cursor = db.execute(
            "DELETE FROM conversations WHERE id = ?",
            (conversation_id,),
        )

    if cursor.rowcount == 0:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    return {
        "success": True,
        "message": "Conversation deleted",
    }


# --------------------------------------------------
# NORMAL CHAT
# --------------------------------------------------

@app.post("/conversations/{conversation_id}/messages/stream")
def send_message_stream(
    conversation_id: str,
    request: ChatRequest,
):
    if not conversation_exists(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")

    require_client()
    request_id = request.request_id or str(uuid4())
    clear_cancelled(request_id)

    user_message = request.message.strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    update_conversation_title_if_new(conversation_id, user_message)
    user_message_id = add_message(conversation_id, "user", user_message)

    return stream_reply_response(
        conversation_id,
        user_message,
        request_id,
        user_message_id=user_message_id,
    )


@app.post("/conversations/{conversation_id}/messages")
def send_message(
    conversation_id: str,
    request: ChatRequest,
):
    if not conversation_exists(conversation_id):
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    require_client()

    request_id = request.request_id or str(uuid4())
    clear_cancelled(request_id)

    user_message = request.message.strip()

    if not user_message:
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty",
        )

    update_conversation_title_if_new(
        conversation_id,
        user_message,
    )

    user_message_id = add_message(
        conversation_id,
        "user",
        user_message,
    )

    try:
        reply = generate_reply(
            conversation_id,
            user_message,
        )

        if is_cancelled(request_id):
            return {
                "success": False,
                "cancelled": True,
                "conversation_id": conversation_id,
            }

        add_message(
            conversation_id,
            "assistant",
            reply,
        )

        # Extract persistent memories after saving the reply.
        extract_and_save_memories(
            conversation_id,
            user_message,
            reply,
        )

        return {
            "success": True,
            "reply": reply,
            "model": MODEL_NAME,
            "conversation_id": conversation_id,
            "message_id": user_message_id,
        }

    except HTTPException:
        raise

    except Exception as error:
        print(f"Chat generation error: {error}")
        raise HTTPException(
            status_code=500,
            detail=f"AI response failed: {str(error)}",
        )

    finally:
        clear_cancelled(request_id)


# --------------------------------------------------
# STOP GENERATION
# --------------------------------------------------

@app.post("/conversations/{conversation_id}/stop")
def stop_generation(
    conversation_id: str,
    request: RequestControl,
):
    if not conversation_exists(conversation_id):
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    mark_cancelled(request.request_id)

    return {
        "success": True,
        "cancelled": True,
        "request_id": request.request_id,
    }


# --------------------------------------------------
# EDIT MESSAGE
# --------------------------------------------------

@app.patch(
    "/conversations/{conversation_id}/messages/{message_id}"
)
def edit_message(
    conversation_id: str,
    message_id: int,
    request: EditMessageRequest,
):
    if not conversation_exists(conversation_id):
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    content = request.content.strip()

    if not content:
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty",
        )

    with get_db() as db:
        message = db.execute("""
            SELECT id, role
            FROM messages
            WHERE id = ? AND conversation_id = ?
        """, (
            message_id,
            conversation_id,
        )).fetchone()

        if not message:
            raise HTTPException(
                status_code=404,
                detail="Message not found",
            )

        if message["role"] != "user":
            raise HTTPException(
                status_code=400,
                detail="Only user messages can be edited",
            )

        db.execute("""
            UPDATE messages
            SET content = ?
            WHERE id = ?
        """, (content, message_id))

        # Remove all later messages and their associated uploaded files.
        db.execute("""
            DELETE FROM messages
            WHERE conversation_id = ? AND id > ?
        """, (conversation_id, message_id))

        db.execute("""
            UPDATE conversations
            SET updated_at = ?
            WHERE id = ?
        """, (now_iso(), conversation_id))

    return {
        "success": True,
        "message_id": message_id,
        "content": content,
    }


# --------------------------------------------------
# REPLY TO AN EDITED MESSAGE
# --------------------------------------------------

@app.post(
    "/conversations/{conversation_id}/messages/{message_id}/reply/stream"
)
def reply_to_edited_message_stream(
    conversation_id: str,
    message_id: int,
    request: RequestControl,
):
    if not conversation_exists(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    require_client()

    with get_db() as db:
        message = db.execute("""
            SELECT id, role, content
            FROM messages
            WHERE id = ? AND conversation_id = ?
        """, (message_id, conversation_id)).fetchone()

    if not message or message["role"] != "user":
        raise HTTPException(status_code=404, detail="Edited user message not found")

    clear_cancelled(request.request_id)
    return stream_reply_response(
        conversation_id,
        message["content"],
        request.request_id,
        before_message_id=message_id,
        user_message_id=message_id,
    )


@app.post(
    "/conversations/{conversation_id}/messages/{message_id}/reply"
)
def reply_to_edited_message(
    conversation_id: str,
    message_id: int,
    request: RequestControl,
):
    if not conversation_exists(conversation_id):
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    require_client()

    with get_db() as db:
        message = db.execute("""
            SELECT id, role, content
            FROM messages
            WHERE id = ? AND conversation_id = ?
        """, (
            message_id,
            conversation_id,
        )).fetchone()

    if not message or message["role"] != "user":
        raise HTTPException(
            status_code=404,
            detail="Edited user message not found",
        )

    request_id = request.request_id
    clear_cancelled(request_id)

    try:
        reply = generate_reply(
            conversation_id,
            message["content"],
            before_message_id=message_id,
        )

        if is_cancelled(request_id):
            return {
                "success": False,
                "cancelled": True,
            }

        add_message(
            conversation_id,
            "assistant",
            reply,
        )

        extract_and_save_memories(
            conversation_id,
            message["content"],
            reply,
        )

        return {
            "success": True,
            "reply": reply,
            "model": MODEL_NAME,
        }

    except HTTPException:
        raise

    except Exception as error:
        print(f"Edited reply error: {error}")
        raise HTTPException(
            status_code=500,
            detail=f"Reply generation failed: {str(error)}",
        )

    finally:
        clear_cancelled(request_id)


# --------------------------------------------------
# REGENERATE ASSISTANT RESPONSE
# --------------------------------------------------

@app.post(
    "/conversations/{conversation_id}/messages/{message_id}/regenerate/stream"
)
def regenerate_message_stream(
    conversation_id: str,
    message_id: int,
    request: RequestControl,
):
    if not conversation_exists(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    require_client()

    with get_db() as db:
        assistant_message = db.execute("""
            SELECT id, role
            FROM messages
            WHERE id = ? AND conversation_id = ?
        """, (message_id, conversation_id)).fetchone()

        if not assistant_message or assistant_message["role"] != "assistant":
            raise HTTPException(status_code=404, detail="Assistant message not found")

        previous_user_message = db.execute("""
            SELECT id, content
            FROM messages
            WHERE conversation_id = ?
              AND role = 'user'
              AND id < ?
            ORDER BY id DESC
            LIMIT 1
        """, (conversation_id, message_id)).fetchone()

        if not previous_user_message:
            raise HTTPException(status_code=400, detail="No user message found for regeneration")

        db.execute("""
            DELETE FROM messages
            WHERE conversation_id = ? AND id >= ?
        """, (conversation_id, message_id))

    clear_cancelled(request.request_id)
    return stream_reply_response(
        conversation_id,
        previous_user_message["content"],
        request.request_id,
        user_message_id=previous_user_message["id"],
    )


@app.post(
    "/conversations/{conversation_id}/messages/{message_id}/regenerate"
)
def regenerate_message(
    conversation_id: str,
    message_id: int,
    request: RequestControl,
):
    if not conversation_exists(conversation_id):
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    require_client()

    with get_db() as db:
        assistant_message = db.execute("""
            SELECT id, role
            FROM messages
            WHERE id = ? AND conversation_id = ?
        """, (
            message_id,
            conversation_id,
        )).fetchone()

        if not assistant_message or assistant_message["role"] != "assistant":
            raise HTTPException(
                status_code=404,
                detail="Assistant message not found",
            )

        previous_user_message = db.execute("""
            SELECT id, content
            FROM messages
            WHERE conversation_id = ?
              AND role = 'user'
              AND id < ?
            ORDER BY id DESC
            LIMIT 1
        """, (
            conversation_id,
            message_id,
        )).fetchone()

        if not previous_user_message:
            raise HTTPException(
                status_code=400,
                detail="No user message found for regeneration",
            )

        # Delete the old assistant response and all later turns.
        db.execute("""
            DELETE FROM messages
            WHERE conversation_id = ? AND id >= ?
        """, (
            conversation_id,
            message_id,
        ))

    request_id = request.request_id
    clear_cancelled(request_id)

    try:
        reply = generate_reply(
            conversation_id,
            previous_user_message["content"],
        )

        if is_cancelled(request_id):
            return {
                "success": False,
                "cancelled": True,
            }

        add_message(
            conversation_id,
            "assistant",
            reply,
        )

        extract_and_save_memories(
            conversation_id,
            previous_user_message["content"],
            reply,
        )

        return {
            "success": True,
            "reply": reply,
            "model": MODEL_NAME,
        }

    except HTTPException:
        raise

    except Exception as error:
        print(f"Regeneration error: {error}")
        raise HTTPException(
            status_code=500,
            detail=f"Regeneration failed: {str(error)}",
        )

    finally:
        clear_cancelled(request_id)
        # --------------------------------------------------
# FILE EXTRACTION
# --------------------------------------------------

MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_FILES_PER_MESSAGE = 5
MAX_EXTRACTED_CHARS = 30000

ALLOWED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".txt",
    ".csv",
    ".xlsx",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
}


def extract_pdf_text(file_bytes):
    try:
        import fitz

        document = fitz.open(
            stream=file_bytes,
            filetype="pdf",
        )

        text_parts = []

        for page in document:
            text_parts.append(page.get_text())

        document.close()

        return "\n".join(text_parts)[:MAX_EXTRACTED_CHARS]

    except Exception as error:
        print(f"PDF extraction error: {error}")
        return ""


def extract_docx_text(file_bytes):
    try:
        from docx import Document

        document = Document(io.BytesIO(file_bytes))

        paragraphs = [
            paragraph.text
            for paragraph in document.paragraphs
            if paragraph.text.strip()
        ]

        table_text = []

        for table in document.tables:
            for row in table.rows:
                cells = [
                    cell.text.strip()
                    for cell in row.cells
                ]
                table_text.append(" | ".join(cells))

        result = "\n".join(paragraphs + table_text)

        return result[:MAX_EXTRACTED_CHARS]

    except Exception as error:
        print(f"DOCX extraction error: {error}")
        return ""


def extract_txt_text(file_bytes):
    try:
        return file_bytes.decode(
            "utf-8",
            errors="replace",
        )[:MAX_EXTRACTED_CHARS]

    except Exception as error:
        print(f"TXT extraction error: {error}")
        return ""


def extract_csv_text(file_bytes):
    try:
        import pandas as pd

        dataframe = pd.read_csv(
            io.BytesIO(file_bytes),
            nrows=500,
        )

        result = dataframe.to_string(index=False)

        return result[:MAX_EXTRACTED_CHARS]

    except Exception as error:
        print(f"CSV extraction error: {error}")
        return ""


def extract_xlsx_text(file_bytes):
    try:
        import pandas as pd

        excel_file = pd.ExcelFile(
            io.BytesIO(file_bytes)
        )

        output = []

        for sheet_name in excel_file.sheet_names[:5]:
            dataframe = pd.read_excel(
                excel_file,
                sheet_name=sheet_name,
                nrows=500,
            )

            output.append(
                f"\nSHEET: {sheet_name}\n"
                f"{dataframe.to_string(index=False)}"
            )

        return "\n".join(output)[:MAX_EXTRACTED_CHARS]

    except Exception as error:
        print(f"XLSX extraction error: {error}")
        return ""


def extract_file_content(filename, file_bytes):
    extension = Path(filename).suffix.lower()

    if extension == ".pdf":
        return extract_pdf_text(file_bytes)

    if extension == ".docx":
        return extract_docx_text(file_bytes)

    if extension == ".txt":
        return extract_txt_text(file_bytes)

    if extension == ".csv":
        return extract_csv_text(file_bytes)

    if extension == ".xlsx":
        return extract_xlsx_text(file_bytes)

    return ""


# --------------------------------------------------
# FILE VALIDATION
# --------------------------------------------------

def validate_uploaded_file(upload):
    filename = upload.filename or "unnamed_file"
    extension = Path(filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {filename}",
        )

    return filename, extension


async def read_uploaded_file(upload):
    file_bytes = await upload.read()

    if not file_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"{upload.filename} is empty.",
        )

    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"{upload.filename} exceeds the 10 MB limit.",
        )

    return file_bytes


# --------------------------------------------------
# SAVE ATTACHMENT TO DATABASE
# --------------------------------------------------

def save_conversation_file(
    conversation_id,
    message_id,
    filename,
    mime_type,
    file_bytes,
    extracted_text,
):
    with get_db() as db:
        cursor = db.execute("""
            INSERT INTO conversation_files (
                conversation_id,
                message_id,
                name,
                mime_type,
                size_bytes,
                extracted_text,
                file_data,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            conversation_id,
            message_id,
            filename,
            mime_type,
            len(file_bytes),
            extracted_text,
            file_bytes if mime_type.startswith("image/") else None,
            now_iso(),
        ))

        return cursor.lastrowid


# --------------------------------------------------
# ATTACHMENT CHAT ENDPOINT
# --------------------------------------------------

@app.post(
    "/conversations/{conversation_id}/messages/with-attachments/stream"
)
async def send_message_with_attachments_stream(
    conversation_id: str,
    message: str = Form(""),
    request_id: str = Form(""),
    files: list[UploadFile] = File(...),
):
    if not conversation_exists(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    require_client()

    if not files:
        raise HTTPException(status_code=400, detail="Please attach at least one file.")
    if len(files) > MAX_FILES_PER_MESSAGE:
        raise HTTPException(status_code=400, detail="You can upload a maximum of 5 files per message.")

    request_id = request_id or str(uuid4())
    clear_cancelled(request_id)

    user_message = message.strip()
    uploaded_files = []
    attachment_metadata = []

    try:
        for upload in files:
            filename, extension = validate_uploaded_file(upload)
            file_bytes = await read_uploaded_file(upload)
            mime_type = upload.content_type or "application/octet-stream"
            extracted_text = extract_file_content(filename, file_bytes)

            uploaded_files.append({
                "filename": filename,
                "extension": extension,
                "mime_type": mime_type,
                "file_bytes": file_bytes,
                "extracted_text": extracted_text,
            })
            attachment_metadata.append({
                "name": filename,
                "type": mime_type,
                "size": len(file_bytes),
            })

        file_names = ", ".join(item["filename"] for item in uploaded_files)
        effective_message = user_message or f"Please analyze the following uploaded files: {file_names}"

        update_conversation_title_if_new(conversation_id, effective_message)
        message_id = add_message(
            conversation_id,
            "user",
            effective_message,
            attachment_metadata,
        )

        for item in uploaded_files:
            save_conversation_file(
                conversation_id=conversation_id,
                message_id=message_id,
                filename=item["filename"],
                mime_type=item["mime_type"],
                file_bytes=item["file_bytes"],
                extracted_text=item["extracted_text"],
            )

        return stream_reply_response(
            conversation_id,
            effective_message,
            request_id,
            user_message_id=message_id,
        )

    except HTTPException:
        clear_cancelled(request_id)
        raise
    except Exception as error:
        clear_cancelled(request_id)
        print(f"Streaming attachment processing error: {error}")
        raise HTTPException(status_code=500, detail=f"File processing failed: {str(error)}")
    finally:
        for upload in files:
            await upload.close()


@app.post(
    "/conversations/{conversation_id}/messages/with-attachments"
)
async def send_message_with_attachments(
    conversation_id: str,
    message: str = Form(""),
    request_id: str = Form(""),
    files: list[UploadFile] = File(...),
):
    if not conversation_exists(conversation_id):
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    require_client()

    if not files:
        raise HTTPException(
            status_code=400,
            detail="Please attach at least one file.",
        )

    if len(files) > MAX_FILES_PER_MESSAGE:
        raise HTTPException(
            status_code=400,
            detail="You can upload a maximum of 5 files per message.",
        )

    request_id = request_id or str(uuid4())
    clear_cancelled(request_id)

    user_message = message.strip()

    uploaded_files = []
    attachment_metadata = []

    try:
        # Read and validate all files before writing the message.
        for upload in files:
            filename, extension = validate_uploaded_file(upload)
            file_bytes = await read_uploaded_file(upload)

            mime_type = (
                upload.content_type
                or "application/octet-stream"
            )

            extracted_text = extract_file_content(
                filename,
                file_bytes,
            )

            uploaded_files.append({
                "filename": filename,
                "extension": extension,
                "mime_type": mime_type,
                "file_bytes": file_bytes,
                "extracted_text": extracted_text,
            })

            attachment_metadata.append({
                "name": filename,
                "type": mime_type,
                "size": len(file_bytes),
            })

        file_names = ", ".join(
            item["filename"]
            for item in uploaded_files
        )

        effective_message = user_message or (
            f"Please analyze the following uploaded files: {file_names}"
        )

        update_conversation_title_if_new(
            conversation_id,
            effective_message,
        )

        # Save the user message first.
        message_id = add_message(
            conversation_id,
            "user",
            effective_message,
            attachment_metadata,
        )

        # Store extracted file content and image bytes.
        for item in uploaded_files:
            save_conversation_file(
                conversation_id=conversation_id,
                message_id=message_id,
                filename=item["filename"],
                mime_type=item["mime_type"],
                file_bytes=item["file_bytes"],
                extracted_text=item["extracted_text"],
            )

        # Generate a response using the new file context.
        reply = generate_reply(
            conversation_id,
            effective_message,
        )

        if is_cancelled(request_id):
            return {
                "success": False,
                "cancelled": True,
                "conversation_id": conversation_id,
            }

        add_message(
            conversation_id,
            "assistant",
            reply,
        )

        extract_and_save_memories(
            conversation_id,
            effective_message,
            reply,
        )

        return {
            "success": True,
            "reply": reply,
            "model": MODEL_NAME,
            "conversation_id": conversation_id,
            "message_id": message_id,
            "attachments": attachment_metadata,
        }

    except HTTPException:
        raise

    except Exception as error:
        print(f"Attachment processing error: {error}")

        raise HTTPException(
            status_code=500,
            detail=f"File processing failed: {str(error)}",
        )

    finally:
        clear_cancelled(request_id)

        for upload in files:
            await upload.close()


# --------------------------------------------------
# FILE MEMORY INFORMATION
# --------------------------------------------------

@app.get(
    "/conversations/{conversation_id}/files"
)
def get_conversation_files(conversation_id: str):
    if not conversation_exists(conversation_id):
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    with get_db() as db:
        rows = db.execute("""
            SELECT
                id,
                conversation_id,
                message_id,
                name,
                mime_type,
                size_bytes,
                created_at
            FROM conversation_files
            WHERE conversation_id = ?
            ORDER BY id DESC
        """, (conversation_id,)).fetchall()

    return {
        "conversation_id": conversation_id,
        "files": [dict(row) for row in rows],
    }


# --------------------------------------------------
# CONVERSATION FILE MEMORY STATUS
# --------------------------------------------------

@app.get(
    "/conversations/{conversation_id}/files/count"
)
def get_conversation_file_count(conversation_id: str):
    if not conversation_exists(conversation_id):
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    with get_db() as db:
        row = db.execute("""
            SELECT
                COUNT(*) AS total_files,
                COALESCE(SUM(size_bytes), 0) AS total_bytes
            FROM conversation_files
            WHERE conversation_id = ?
        """, (conversation_id,)).fetchone()

    return {
        "conversation_id": conversation_id,
        "total_files": row["total_files"],
        "total_bytes": row["total_bytes"],
    }
    # --------------------------------------------------
# MEMORY MANAGER API
# --------------------------------------------------

@app.get("/memory")
def get_memories():
    """
    Return all saved user memories.
    Expected frontend response:
    {
        "memories": [...]
    }
    """
    return {
        "memories": get_all_memories()
    }


@app.post("/memory")
def create_memory(request: MemoryCreateRequest):
    """
    Add a memory manually.
    """
    memory_text = request.memory.strip()
    category = request.category.strip() or "general"

    if not memory_text:
        raise HTTPException(
            status_code=400,
            detail="Memory cannot be empty.",
        )

    try:
        memory_id = save_memory(
            memory_text,
            category,
        )

        with get_db() as db:
            row = db.execute("""
                SELECT id, memory, category, created_at
                FROM user_memories
                WHERE id = ?
            """, (memory_id,)).fetchone()

        return {
            "success": True,
            "memory": dict(row) if row else None,
        }

    except Exception as error:
        print(f"Create memory error: {error}")

        raise HTTPException(
            status_code=500,
            detail="Could not save memory.",
        )


@app.patch("/memory/{memory_id}")
def update_memory(
    memory_id: int,
    request: MemoryUpdateRequest,
):
    """
    Edit an existing memory.
    """
    memory_text = request.memory.strip()
    category = request.category.strip() or "general"

    if not memory_text:
        raise HTTPException(
            status_code=400,
            detail="Memory cannot be empty.",
        )

    with get_db() as db:
        existing = db.execute("""
            SELECT id
            FROM user_memories
            WHERE id = ?
        """, (memory_id,)).fetchone()

        if not existing:
            raise HTTPException(
                status_code=404,
                detail="Memory not found.",
            )

        db.execute("""
            UPDATE user_memories
            SET memory = ?, category = ?
            WHERE id = ?
        """, (
            memory_text,
            category,
            memory_id,
        ))

        updated = db.execute("""
            SELECT id, memory, category, created_at
            FROM user_memories
            WHERE id = ?
        """, (memory_id,)).fetchone()

    return {
        "success": True,
        "memory": dict(updated),
    }


@app.delete("/memory/{memory_id}")
def remove_memory(memory_id: int):
    """
    Delete one saved memory.
    """
    with get_db() as db:
        cursor = db.execute("""
            DELETE FROM user_memories
            WHERE id = ?
        """, (memory_id,))

        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=404,
                detail="Memory not found.",
            )

    return {
        "success": True,
        "message": "Memory deleted.",
    }


@app.delete("/memory")
def remove_all_memories():
    """
    Clear all saved memories.
    """
    with get_db() as db:
        db.execute("DELETE FROM user_memories")

    return {
        "success": True,
        "message": "All memories cleared.",
    }


# --------------------------------------------------
# AUTOMATIC MEMORY SETTINGS
# --------------------------------------------------

@app.get("/memory/settings")
def get_memory_settings():
    """
    Return the automatic memory setting.
    """
    return {
        "automatic_memory": automatic_memory_enabled()
    }


@app.put("/memory/settings")
def update_memory_settings(
    request: MemorySettingsRequest,
):
    """
    Enable or disable automatic memory extraction.
    """
    set_setting(
        "automatic_memory",
        "true" if request.automatic_memory else "false",
    )

    return {
        "success": True,
        "automatic_memory": automatic_memory_enabled(),
    }


# --------------------------------------------------
# BACKEND STARTUP CHECK
# --------------------------------------------------

@app.get("/system/status")
def system_status():
    """
    Basic status information for Zyricon.
    """
    return {
        "success": True,
        "application": "Zyricon",
        "database": "connected",
        "automatic_memory": automatic_memory_enabled(),
    }