from __future__ import annotations
import logging
import sys
from pathlib import Path
from time import perf_counter
from uuid import uuid4
import streamlit as st
# --------------------------------------------------# Project setup# --------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))
from ai_agent.core.logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)
from ai_agent.api import client as api_client
def render_chat_message(message: dict) -> None:
    """Render a saved chat message, including an optional generated image."""
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        for document in message.get("documents", []):
            st.caption(f"RAG source: {document['filename']}")
        if message.get("pending_save"):
            st.caption("This message has not been saved yet.")

        image_path = message.get("image_path")
        if image_path and Path(image_path).is_file():
            st.image(
                image_path,
                caption="Generated image",
                use_container_width=True,
            )
def show_pending_save(session_id: str, pending_turn: dict) -> None:
    st.error(
        "The answer is displayed, but the chat could not be saved. "
        "Retry saving before sending another message. "
        f"Details: {pending_turn.get('save_error', 'unknown save error')}"
    )
    if st.button(
        "Retry saving this response",
        key=f"retry_save_{session_id}_{pending_turn['turn_id']}",
    ):
        try:
            api_client.persist_message_turn(
                session_id,
                pending_turn["turn_id"],
                pending_turn["user_content"],
                pending_turn["assistant_content"],
                document_id=pending_turn["document_id"],
                image_path=pending_turn["image_path"],
            )
            st.session_state.pending_turns.pop(session_id, None)
            logger.info(
                "Retried saving chat turn %s for session %s",
                pending_turn["turn_id"],
                session_id,
            )
            st.rerun()
        except api_client.APIClientError as exc:
            logger.exception(
                "Retry failed for chat turn %s",
                pending_turn["turn_id"],
            )
            pending_turn["save_error"] = str(exc)
            st.error(str(exc))
def process_chat_input(session_id: str) -> None:
    """Submit composer text and PDF attachments through the FastAPI backend."""
    pending_turn = st.session_state.get("pending_turns", {}).get(session_id)
    if pending_turn is not None:
        show_pending_save(session_id, pending_turn)
        return
    submission = st.chat_input(
        "Message your agent… use + to attach a PDF",
        accept_file=True,
        file_type=["pdf"],
        key=f"chat_input_{session_id}",
    )
    if submission is None:
        return
    prompt = getattr(submission, "text", submission).strip()
    attached_files = getattr(submission, "files", [])
    attached_document_id = None
    user_container = None
    if prompt:
        user_container = st.chat_message("user")
        with user_container:
            st.markdown(prompt)
    try:
        for uploaded_file in attached_files:
            with st.spinner(f"Uploading and indexing {uploaded_file.name}..."):
                document = api_client.upload_document(
                    session_id,
                    uploaded_file.name,
                    uploaded_file.getvalue(),
                )
            logger.info(
                "Attached PDF %s to session %s",
                document["filename"],
                session_id,
            )
            attached_document_id = document["id"]
        if not prompt and attached_files:
            st.success(
                f"PDF indexed and ready for RAG: {document['filename']}"
            )
            st.rerun()
        if not prompt:
            return
        turn_id = str(uuid4())
        turn_started_at = perf_counter()
        completed_turn = {}
        with st.chat_message("assistant"):
            thinking_placeholder = st.empty()
            thinking_placeholder.markdown("_Thinking..._")
            def response_chunks():
                try:
                    for chunk in api_client.stream_message(
                        session_id,
                        prompt,
                        document_id=attached_document_id,
                        on_complete=completed_turn.update,
                    ):
                        thinking_placeholder.empty()
                        yield chunk
                finally:
                    thinking_placeholder.empty()
            try:
                displayed_answer = st.write_stream(response_chunks())
            except api_client.APIClientError as exc:
                logger.exception(
                    "Streaming chat API request failed for session %s",
                    session_id,
                )
                st.error(str(exc))
                return
            answer = completed_turn.get("answer")
            if not isinstance(answer, str):
                logger.error(
                    "Streaming completed without an answer for session %s",
                    session_id,
                )
                st.error("The agent stream completed without an answer.")
                return
            if isinstance(displayed_answer, str) and displayed_answer != answer:
                logger.warning(
                    "Rendered and completed answers differ for session %s",
                    session_id,
                )
            linked_documents = completed_turn.get("documents", [])
            if user_container is not None:
                for document in linked_documents:
                    user_container.caption(
                        f"RAG source: {document['filename']}"
                    )
            image_path = completed_turn.get("image_path")
            if image_path and Path(image_path).is_file():
                st.image(
                    image_path,
                    caption="Generated image",
                    use_container_width=True,
                )
            persist_request = {
                "turn_id": turn_id,
                "user_content": prompt,
                "assistant_content": answer,
                "document_id": (
                    linked_documents[0]["id"] if linked_documents else None
                ),

                "image_path": image_path,
            }
            persistence_started_at = perf_counter()
            save_status = st.empty()
            save_status.caption("Answer shown. Saving to chat history…")
            try:
                api_client.persist_message_turn(
                    session_id,
                    turn_id,
                    prompt,
                    answer,
                    document_id=persist_request["document_id"],
                    image_path=image_path,
                )
                logger.info(
                    "Persisted displayed chat turn %s for session %s in %.3fs",
                    turn_id,
                    session_id,
                    perf_counter() - persistence_started_at,
                )
                save_status.caption("Saved to chat history.")
            except api_client.APIClientError as exc:
                logger.exception(
                    "Could not save displayed chat turn %s",
                    turn_id,
                )
                persist_request["documents"] = linked_documents
                persist_request["save_error"] = str(exc)
                st.session_state.setdefault("pending_turns", {})[
                    session_id
                ] = persist_request
                save_status.empty()
                show_pending_save(session_id, persist_request)
        logger.info(
            "Completed UI chat turn for session %s in %.3fs",
            session_id,
            perf_counter() - turn_started_at,
        )
    except api_client.APIClientError as exc:
        logger.exception("Chat API request failed for session %s", session_id)
        st.error(str(exc))
    except Exception as exc:
        logger.exception("Chat submission failed for session %s", session_id)
        st.error(f"Could not submit your message: {exc}")
# --------------------------------------------------# Main application# --------------------------------------------------
def main() -> None:
    st.set_page_config(
        page_title="AI Agent",
        page_icon="A",
        layout="wide",
    )
# --------------------------------------------------# UI styling# --------------------------------------------------
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap');
        :root { --app-bg:#fff; --sidebar-bg:#f7f7f8; --text:#202123; --muted:#6b7280; --border:#e5e7eb; --user-bubble:#f4f4f4; }
        .stApp { background:var(--app-bg); color:var(--text); font-family:'DM Sans',sans-serif; }
        [data-testid="stSidebar"] { background:var(--sidebar-bg); border-right:1px solid var(--border); }
        [data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2,[data-testid="stSidebar"] h3,h1,h2,h3,p,label { font-family:'DM Sans',sans-serif; color:var(--text); }
        [data-testid="stSidebar"] .stButton > button { text-align:left; border-radius:10px; border:1px solid transparent; background:transparent; color:var(--text); min-height:2.6rem; }
        [data-testid="stSidebar"] .stButton > button:hover { background:#ececee; border-color:var(--border); }
        [data-testid="stSidebar"] .stButton > button[kind="primary"] { background:#e8e8eb; border-color:#dedee2; color:var(--text); }
        [data-testid="stChatMessage"] { display:flex; width:100%; max-width:100%; box-sizing:border-box; border:0; border-radius:0; padding:.85rem 1rem; background:transparent; margin:0 auto; gap:.7rem; }
        /* Each chat row spans the available width; position the message content itself. */
        [data-testid="stChatMessage"] { display:flex !important; width:100% !important; }
        /* USER: hide the left avatar and push the bubble itself to the right.
           The important flex/width overrides prevent Streamlit's default content
           column from stretching across the entire row. */
        [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="chatAvatarIcon-user"] { display:none !important; }
        [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="stChatMessageContent"] {
            flex:0 1 auto !important;
            width:fit-content !important;
            max-width:min(78%,760px) !important;
            margin-left:auto !important;
            margin-right:0 !important;
            background:var(--user-bubble);
            border:1px solid var(--border);
            border-radius:18px;
            padding:.75rem 1rem;
            text-align:left;
        }
        /* AI: keep response content on the left. */
        [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) [data-testid="chatAvatarIcon-assistant"] { display:flex !important; }
        [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) [data-testid="stChatMessageContent"] {
            flex:0 1 auto !important;
            width:fit-content !important;
            max-width:min(82%,820px) !important;
            margin-left:0 !important;
            margin-right:auto !important;
            background:transparent;
            border:1px solid var(--border);
            border-radius:18px;
            padding:.75rem 1rem;
            text-align:left;
        }
        [data-testid="stChatMessageContent"] { min-width:0; overflow-wrap:anywhere; }
        [data-testid="stChatInput"] { border:1px solid #d9d9df; border-radius:24px; background:#fff; box-shadow:0 4px 18px rgba(0,0,0,.06); }
        [data-testid="stChatInput"]:focus-within { border-color:#a7a7b0; box-shadow:0 0 0 2px rgba(16,163,127,.10); }
        [data-testid="stChatInput"] textarea { background:transparent; border:0; border-radius:24px; }
        .stButton > button { border-radius:10px; min-height:2.6rem; font-weight:600; }
        .eyebrow { color:var(--muted); font-size:.76rem; letter-spacing:.04em; margin-bottom:.35rem; }
        .brand-mark { display:inline-flex; align-items:center; justify-content:center; width:2.2rem; height:2.2rem; margin-bottom:.75rem; border-radius:10px; background:#202123; color:#fff; font-weight:800; }
        hr { border-color:var(--border); }
        @media(max-width:700px) { [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="stChatMessageContent"],[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) [data-testid="stChatMessageContent"] { max-width:92%; } }
        </style>
        """,
        unsafe_allow_html=True,
    )
# --------------------------------------------------# Session state# --------------------------------------------------
    try:
        session_rows = api_client.list_sessions()
        if not session_rows:
            created_session = api_client.create_session()
            st.session_state.session_id = created_session["id"]
            logger.info(
                "Created initial chat session: %s",
                st.session_state.session_id,
            )
        elif st.session_state.get("session_id") not in {
            row["id"] for row in session_rows
        }:
            st.session_state.session_id = session_rows[0]["id"]
            logger.info(
                "Selected most recent chat session: %s",
                st.session_state.session_id,
            )
    except Exception as exc:
        logger.exception("Could not initialize saved Neon chat sessions")
        st.error(
            "Could not load saved chats from Neon. Check DATABASE_URL, "
            "network access, and that `alembic upgrade head` has been run. "
            f"Details: {exc}"
        )
        st.stop()
# --------------------------------------------------# Sidebar# --------------------------------------------------
    with st.sidebar:
        st.markdown(
            '<div class="brand-mark">A</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="eyebrow">Knowledge workspace</div>',
            unsafe_allow_html=True,
        )
        st.title("AI Agent")
        st.divider()
        st.subheader("Your chats")
        if st.button("＋  New chat", use_container_width=True):
            try:
                created_session = api_client.create_session()
                st.session_state.session_id = created_session["id"]
                logger.info(
                    "Created new chat session: %s",
                    st.session_state.session_id,
                )
                st.rerun()
            except Exception as exc:
                logger.exception("Could not create a new chat session")
                st.error(f"Could not create a new chat: {exc}")
        for session_row in session_rows:
            is_current_session = (
                session_row["id"] == st.session_state.session_id
            )
            if st.button(
                session_row["title"] or "New conversation",
                key=f"chat_{session_row['id']}",
                type="primary" if is_current_session else "secondary",
                use_container_width=True,
                help=f"Open chat {session_row['id']}",
            ):
                st.session_state.session_id = session_row["id"]
                st.rerun()
        selected_session_id = st.session_state.session_id
        logger.debug("Active chat session: %s", selected_session_id)

    try:
        st.session_state.chat_history = api_client.list_messages(
            st.session_state.session_id
        )
        pending_turn = st.session_state.get("pending_turns", {}).get(
            st.session_state.session_id
        )
        if pending_turn is not None:
            st.session_state.chat_history.extend(
                [
                    {
                        "id": f"pending-user-{pending_turn['turn_id']}",
                        "role": "user",
                        "content": pending_turn["user_content"],
                        "documents": pending_turn.get("documents", []),
                        "pending_save": True,
                    },
                    {
                        "id": f"pending-assistant-{pending_turn['turn_id']}",
                        "role": "assistant",
                        "content": pending_turn["assistant_content"],
                        "image_path": pending_turn["image_path"],
                        "pending_save": True,
                    },
                ]
            )

    except Exception as exc:
        logger.exception(
            "Could not load history for chat session %s",
            st.session_state.session_id,
        )
        st.error(f"Could not load this chat's history: {exc}")
        st.stop()
# --------------------------------------------------# Main workspace# --------------------------------------------------
    st.markdown(
        '<div class="eyebrow">Your assistant</div>',
        unsafe_allow_html=True,
    )
    st.title("How can I help?")
    if not st.session_state.chat_history:
        st.markdown("### What are we working on?")
        st.caption(
            "Ask a question, search your indexed PDF, "
            "or generate an image."
        )
# Display previous messages and generated images.
    for saved_message in st.session_state.chat_history:
        render_chat_message(saved_message)
    process_chat_input(st.session_state.session_id)

if __name__ == "__main__":
    main()
