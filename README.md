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

## Running the app

Start the Streamlit interface from the project root:

```bash
streamlit run app.py
```

This launches the chat UI where you can:

- ask questions to the agent
- upload a PDF
- build a FAISS index for the PDF
- ask document-grounded questions using retrieval
- trigger image generation requests

## PDF RAG workflow

1. Upload a PDF from the sidebar.
2. Click “Build / replace index”.
3. Ask questions related to the uploaded PDF.
4. The app automatically performs retrieval when the question looks document-related.
5. The retrieved passages are included as context before the agent answers.

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

## License

This project is currently unlicensed unless added later.
