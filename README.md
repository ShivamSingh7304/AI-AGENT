# AI Agent

A flexible personal AI assistant built with Python, LangChain, Streamlit, and Groq. It combines chat, document retrieval, web/weather tools, desktop file access, and image generation into a single workspace-friendly agent.

## Features

- Conversational agent powered by Groq and LangChain
- PDF indexing and retrieval using FAISS + embeddings
- Streamlit web interface for chat and document upload
- Desktop file read/write/append tools for local file workflows
- Web search and weather lookup tools
- Image generation tool using a Hugging Face Gradio Space
- Session-based chat history and agent message memory

## Project structure

```text
AI-AGENT/
├── app.py                     # Streamlit UI entry point
├── SOUL.md                   # Agent identity and operating rules
├── pyproject.toml            # Project metadata and dependencies
├── requirements.txt          # Minimal dependency list
├── .env.example              # Example environment file
├── data/                     # Uploaded PDFs
├── logs/                     # Runtime logs
├── vector_store/             # FAISS index output
├── src/
│   └── ai_agent/
│       ├── agent/            # Agent initialization and chat logic
│       ├── core/             # Shared config
│       ├── tools/
│       │   ├── file_read_write/
│       │   ├── image_gen/
│       │   ├── rag/
│       │   ├── weather/
│       │   └── websearch/
│       └── __init__.py
└── README.md
```

## Tech stack

- Python 3.12+
- Streamlit
- LangChain + LangGraph
- Groq LLM
- FAISS + sentence-transformers for RAG
- PyPDF for PDF parsing
- Tavily for web search
- Gradio client for image generation

## Environment setup

1. Create and activate a virtual environment:

```bash
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies:

```bash
pip install -r requirements.txt
# or, if using the project config
pip install -e .
```

3. Create a `.env` file with the required environment variables. At minimum, add your API keys for the services you use, for example:

> If a tool does not require a given key, it can be left unset.

For chat persistence, create a Neon PostgreSQL project and copy its connection
string into `DATABASE_URL` in `.env`. Use the connection string provided by
Neon (including its password); do not commit `.env`. This app connects through
Neon's PostgreSQL wire protocol using SQLAlchemy and psycopg.

Run the initial schema migration before starting the app:

```bash
alembic upgrade head
```

## Running the app

Start the API in one terminal from the project root:

```bash
uv run uvicorn ai_agent.api.main:app --app-dir src --host 127.0.0.1 --port 8000
```

The API initializes one shared agent when it starts. Chat history is still
loaded separately for each session, so sessions do not share conversation
messages.

Then start the Streamlit interface in a second terminal:

```bash
uv run streamlit run app.py
```

The API documentation is available at `http://127.0.0.1:8000/docs`. The API
binds to localhost by default; do not expose it to a network without adding
authentication and deployment-appropriate upload controls.

The Streamlit UI uses this API by default. Set `AI_AGENT_API_URL` in `.env` if
you run the API at a different address.

### API endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Check that the API is running |
| `GET`, `POST` | `/sessions` | List or create chat sessions |
| `DELETE` | `/sessions/{session_id}` | Delete a chat session and its managed files |
| `GET`, `POST` | `/sessions/{session_id}/messages` | Read history or send a message |
| `POST` | `/sessions/{session_id}/messages/stream` | Stream an agent reply as NDJSON |
| `POST` | `/sessions/{session_id}/messages/persist` | Save the displayed user/assistant turn atomically |
| `GET`, `POST` | `/sessions/{session_id}/documents` | List or upload/index PDFs |
| `PATCH` | `/sessions/{session_id}/documents/active` | Choose the PDF used for RAG |

The chat UI lets you:

- ask questions to the agent
- see your submitted message immediately and receive the assistant reply as it streams; both are saved atomically after the response is displayed
- attach a PDF in the chat composer and build a session-specific FAISS index
- ask document-grounded questions using retrieval
- trigger image generation requests

## PDF RAG workflow

1. Attach a PDF from the `+` button in the chat composer. The API saves it,
   builds a session-specific FAISS index, and selects it for that chat.
2. To switch between PDFs already attached to the chat, use the sidebar's
   **RAG source** selector.
3. Ask a question about the PDF. The selected PDF is searched and relevant
   passages are included as context for the agent's answer.

## Agent behavior

The agent is guided by the rules in `SOUL.md`, which define:

- retrieval-first behavior for document questions
- careful handling of tool use
- privacy and safety expectations
- clear separation between verified PDF evidence and general model knowledge

## Example usage

- “Summarize the uploaded PDF.”
- “What does the report say about page 12?”
- “Generate an image of a modern AI office.”
- “What is the weather in London?”
- “Read the file notes.txt from my Desktop and summarize it.”

## Notes

- The app writes uploaded PDF sources under the `data/uploads` folder.
- The FAISS index is stored under `vector_store/faiss_index`.
- Logs are written to the `logs/agent.log` file.
- Some tools may require API keys and internet access to work correctly.
- Chat sessions, messages, PDF metadata, and generated-image paths are stored
  in Neon PostgreSQL. Each chat has separate FAISS indexes for its PDFs, while
  PDF files, FAISS indexes, and generated images remain on the app's local
  filesystem. Back up those files separately; moving the app to another host
  requires moving them or using shared/object storage.
- Existing PDFs indexed into the old shared FAISS index must be uploaded and
  indexed again so the new session-specific index and database references can
  be created.
- The saved-session picker is not user authentication. Do not expose this app
  to untrusted users until access control is added.

## License

This project is currently unlicensed unless added later.
