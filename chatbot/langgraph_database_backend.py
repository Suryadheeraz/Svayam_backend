
import os, io, re, sqlite3, json
from typing import TypedDict, Annotated, Optional
from pathlib import Path

import pandas as pd
import numpy as np
from dotenv import load_dotenv

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph.message import add_messages

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langchain_openai import AzureChatOpenAI

from azure.storage.blob import BlobServiceClient
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from openai import AzureOpenAI

load_dotenv()

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------

BLOB_CONN_STR = os.getenv("AZURE_STORAGE_CONN_STR")
CONTAINER_NAME = "svayamams"
FOLDER_PREFIX = "SEWA/Tickets"

AZURE_SEARCH_ENDPOINT = os.getenv("SEARCH_ENDPOINT")
AZURE_SEARCH_KEY = os.getenv("SEARCH_KEY1")
SEARCH_INDEX = "svayam-ams-sewa"

EXCEL_SIM_THRESHOLD = 0.78
AZURE_SEARCH_MIN_SCORE = 0.65   # strict filter

# Conversation context configuration
CTX_MAX_TURNS = 6         # look back up to 6 messages (3 user+assistant pairs)
CTX_MAX_CHARS = 900       # keep contextual query compact for embedding/search
CTX_STRIP_PATTERNS = [
    r"^⏳.*$",                      # status tokens like "Processing..."
    r"^\*\*is your issue resolved\?\*\*$",  # closing line
]

# Running summary constraints
SUMMARY_MAX_WORDS = 120

# ---------------------------------------------------------
# LLM CONFIG
# ---------------------------------------------------------

llm_stream = AzureChatOpenAI(
    azure_endpoint=os.getenv("AZURE_GPT4O_ENDPOINT"),
    deployment_name=os.getenv("AZURE_GPT4O_DEPLOYMENT"),
    openai_api_version=os.getenv("AZURE_GPT4O_API_VERSION"),
    api_key=os.getenv("AZURE_GPT4O_API_KEY"),
    temperature=0,
    streaming=True
)

llm_intent = AzureChatOpenAI(
    azure_endpoint=os.getenv("AZURE_GPT4O_ENDPOINT"),
    deployment_name=os.getenv("AZURE_GPT4O_DEPLOYMENT"),
    openai_api_version=os.getenv("AZURE_GPT4O_API_VERSION"),
    api_key=os.getenv("AZURE_GPT4O_API_KEY"),
    temperature=0,
    streaming=False
)

openai_client = AzureOpenAI(
    azure_endpoint=os.getenv("AZURE_GPT4O_ENDPOINT"),
    api_key=os.getenv("AZURE_GPT4O_API_KEY"),
    api_version="2024-12-01-preview"
)

# ---------------------------------------------------------
# CLIENTS
# ---------------------------------------------------------

blob_service = BlobServiceClient.from_connection_string(BLOB_CONN_STR)
container_client = blob_service.get_container_client(CONTAINER_NAME)

# NOTE: AzureKeyCredential requires a valid key set in env
search_client = SearchClient(
    endpoint=AZURE_SEARCH_ENDPOINT,
    index_name=SEARCH_INDEX,
    credential=AzureKeyCredential(AZURE_SEARCH_KEY)
)

# ---------------------------------------------------------
# EMBEDDINGS
# ---------------------------------------------------------

def get_embedding(text: str):
    emb = openai_client.embeddings.create(
        model="text-embedding-3-large",
        input=text
    )
    return np.array(emb.data[0].embedding)

# ---------------------------------------------------------
# UTILS
# ---------------------------------------------------------

def summarize_for_sidebar(text: str, max_words=6):
    text = re.sub(r"\s+", " ", text).strip()
    words = text.split(" ")
    return " ".join(words[:max_words])

def sanitize_ai_response(raw: str, user_text: str):
    if not raw:
        return ""
    txt = raw.strip()
    txt = re.sub(re.escape(user_text), "", txt, flags=re.IGNORECASE).strip()
    txt = re.sub(r"^(as an ai|you asked|your question).*?(\.|:|\n)", "", txt, flags=re.IGNORECASE).strip()
    return txt

def _strip_trivial_lines(text: str) -> str:
    if not text:
        return ""
    t = text.strip()
    for pat in CTX_STRIP_PATTERNS:
        if re.search(pat, t, flags=re.IGNORECASE):
            return ""
    return t

def build_history_text(messages: list[BaseMessage], max_turns: int = CTX_MAX_TURNS, max_chars: int = CTX_MAX_CHARS) -> str:
    """
    Build a compact conversation history: last N messages (excluding system),
    cleaned of trivial/status lines, clipped to max_chars.
    """
    collected = []
    count = 0
    for m in reversed(messages):
        if isinstance(m, SystemMessage):
            continue
        role = "User" if isinstance(m, HumanMessage) else "Assistant"
        content = _strip_trivial_lines(m.content or "")
        if not content:
            continue
        collected.append(f"{role}: {content}")
        count += 1
        if count >= max_turns:
            break
    # reverse back to chronological order
    collected = list(reversed(collected))
    history = "\n".join(collected)
    if len(history) > max_chars:
        history = history[-max_chars:]  # keep tail where most recent context is
    return history

def build_contextual_query(user_text: str, history_text: str, running_summary: str | None, max_chars: int = CTX_MAX_CHARS) -> str:
    """
    Build the context-aware query for retrieval (embeddings + Azure Search).
    """
    parts = []
    if running_summary:
        parts.append("Running Summary:\n" + running_summary.strip())
    if history_text:
        parts.append("Recent Messages:\n" + history_text.strip())
    parts.append("Current user question:\n" + user_text.strip())

    base = "\n\n".join(parts).strip()
    if len(base) > max_chars:
        base = base[-max_chars:]
    return base

# ---------------------------------------------------------
# RUNNING SUMMARY (SQLite)
# ---------------------------------------------------------

def init_summary_store(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS thread_summaries (
            thread_id TEXT PRIMARY KEY,
            summary   TEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

def get_thread_summary(conn: sqlite3.Connection, thread_id: str) -> str:
    if not thread_id:
        return ""
    row = conn.execute("SELECT summary FROM thread_summaries WHERE thread_id = ?", (thread_id,)).fetchone()
    return row[0] if row else ""

def upsert_thread_summary(conn: sqlite3.Connection, thread_id: str, summary: str):
    if not thread_id:
        return
    conn.execute("""
        INSERT INTO thread_summaries (thread_id, summary)
        VALUES (?, ?)
        ON CONFLICT(thread_id) DO UPDATE SET
            summary = excluded.summary,
            updated_at = CURRENT_TIMESTAMP
    """, (thread_id, summary))
    conn.commit()

def update_running_summary(
    thread_id: Optional[str],
    conn: sqlite3.Connection,
    prev_summary: str,
    last_user: str,
    last_assistant: str
):
    """
    Update the running summary using the previous summary + last turn.
    Keeps it concise and accumulative.
    """
    if not thread_id:
        return  # cannot persist without a thread id

    sys = (
        "Update the running summary of a dialogue given the previous summary and the latest turn. "
        f"Keep it concise (<= {SUMMARY_MAX_WORDS} words), factual, and useful for future retrieval. "
        "Capture key entities, user goals/requests, steps taken, decisions, and any unresolved items. "
        "Return ONLY the updated summary text without any prefix/suffix."
    )
    hm = (
        f"PREVIOUS SUMMARY:\n{prev_summary or '(none)'}\n\n"
        f"LATEST TURN:\nUser: {last_user}\nAssistant: {last_assistant}\n\n"
        "UPDATED SUMMARY:"
    )
    try:
        resp = llm_intent.invoke([SystemMessage(content=sys), HumanMessage(content=hm)])
        new_summary = (resp.content or "").strip()
        upsert_thread_summary(conn, thread_id, new_summary)
    except Exception as e:
        # fail quietly; do not break the chat on summarization errors
        pass

# ---------------------------------------------------------
# LLM ANSWER VERIFIER
# ---------------------------------------------------------

_VERIFY_SYSTEM = (
    "You are a strict answer verifier. "
    "Given the user's question and the model's answer, classify whether the answer is a "
    "substantive, on-topic answer ('ANSWER') or a refusal/deflection/out-of-scope/not-found ('NO_ANSWER'). "
    "Do not be lenient. If the answer apologizes, says it cannot provide information, "
    "lacks concrete content relevant to the question, or states limitations (e.g., no real-time data), label 'NO_ANSWER'. "
    "If the answer includes concrete, relevant content that addresses the question, label 'ANSWER'. "
    "Return only compact JSON with keys: answer_status ('ANSWER'|'NO_ANSWER'), reason (short)."
)

def verify_answer_with_llm(question: str, answer: str, kb_excerpt: str = "") -> dict:
    """
    Uses a small LLM call (non-streaming) to classify the answer as ANSWER or NO_ANSWER.
    Returns a dict: { 'answer_status': 'ANSWER'|'NO_ANSWER', 'reason': '...' }
    Falls back to a safe default (NO_ANSWER) if parsing fails.
    """
    try:
        prompt = [
            SystemMessage(content=_VERIFY_SYSTEM),
            HumanMessage(content=(
                "USER_QUESTION:\n"
                f"{question}\n\n"
                "MODEL_ANSWER:\n"
                f"{answer}\n\n"
                "OPTIONAL_KB_EXCERPT (may be empty):\n"
                f"{kb_excerpt}\n\n"
                "Respond with JSON only."
            ))
        ]
        resp = llm_intent.invoke(prompt)
        raw = (resp.content or "").strip()
        raw = raw.strip("` \n\t")
        if raw.startswith("{") and raw.endswith("}"):
            parsed = json.loads(raw)
        else:
            m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
            parsed = json.loads(m.group(0)) if m else {}

        status = (parsed.get("answer_status") or "").strip().upper()
        reason = (parsed.get("reason") or "").strip()
        if status not in ("ANSWER", "NO_ANSWER"):
            return {"answer_status": "NO_ANSWER", "reason": "Invalid verifier status"}
        return {"answer_status": status, "reason": reason or "n/a"}
    except Exception as e:
        return {"answer_status": "NO_ANSWER", "reason": f"Verifier error: {e}"}

def heuristic_noinfo(answer_text: str) -> bool:
    """
    Minimal conservative fallback in case verifier fails.
    """
    if not answer_text:
        return True
    t = answer_text.strip().lower()
    if len(t) < 40:
        return True
    if any(p in t for p in [
        "i'm sorry", "sorry", "cannot provide", "can't provide",
        "i do not have", "i don't have", "out of scope",
        "outside the knowledge base", "not related to the knowledge base",
        "i can only provide information based on", "unable to answer"
    ]):
        return True
    return False

# ---------------------------------------------------------
# GREETING
# ---------------------------------------------------------

def llm_is_greeting(text: str) -> bool:
    try:
        prompt = [
            SystemMessage(content="Reply only with GREETING or QUERY_PROCESSING"),
            HumanMessage(content=f'Message: "{text}"')
        ]
        resp = llm_intent.invoke(prompt)
        return (resp.content or "").strip().upper() == "GREETING"
    except:
        return False

# ---------------------------------------------------------
# EXCEL LOADER
# ---------------------------------------------------------

def load_excel_texts():
    all_rows = []

    for blob in container_client.list_blobs(name_starts_with=FOLDER_PREFIX):
        if blob.name.endswith(".xlsx") or blob.name.endswith(".xls"):
            stream = container_client.download_blob(blob.name).readall()
            df = pd.read_excel(io.BytesIO(stream))
            df = df.astype(str)

            for idx, row in df.iterrows():
                row_text = " | ".join(
                    f"{col}: {row[col]}" for col in df.columns
                )

                all_rows.append({
                    "filename": blob.name,
                    "row_index": int(idx),
                    "content": row_text
                })

    return all_rows

# ---------------------------------------------------------
# EXCEL SEMANTIC SEARCH
# ---------------------------------------------------------

def semantic_search_excel(context_query: str, excel_rows):
    """
    Use the context-aware query (with running summary + chat history) for embeddings similarity.
    """
    q_emb = get_embedding(context_query)

    best_match = None
    best_score = 0

    for item in excel_rows:
        content_emb = get_embedding(item["content"])
        score = np.dot(q_emb, content_emb) / (np.linalg.norm(q_emb) * np.linalg.norm(content_emb))

        if score > best_score:
            best_score = score
            best_match = item

    if best_score >= EXCEL_SIM_THRESHOLD:
        return best_match, best_score

    return None, best_score

# ---------------------------------------------------------
# AZURE SEARCH
# ---------------------------------------------------------

def azure_search(query: str, top: int = 5):
    # Pass the context-aware query directly
    results = search_client.search(search_text=query, top=top)
    docs = []
    for r in results:
        score = r.get("@search.score", 0)
        chunk = r.get("chunk") or ""
        title = r.get("title") or "KB Doc"

        docs.append({
            "title": title,
            "chunk": chunk,
            "score": score
        })
    return docs

# ---------------------------------------------------------
# STATE
# ---------------------------------------------------------

class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    project_name: Optional[str]
    # NEW: carry thread_id in state so we can persist and retrieve running summary
    thread_id: Optional[str]

# ---------------------------------------------------------
# CHAT NODE
# ---------------------------------------------------------

def chat_node(state: ChatState):
    messages = state["messages"]
    thread_id = state.get("thread_id")

    # last user msg
    user_text = ""
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            user_text = (m.content or "").strip()
            break

    # ---------- GREETING ----------
    if llm_is_greeting(user_text):
        yield {"messages": [AIMessage(content="Hello 👋 How can I assist you today?")]}
        return

    yield {"messages": [AIMessage(content="⏳ Processing your request...")]}

    # ---------- Build context-aware query ----------
    history_text = build_history_text(messages, CTX_MAX_TURNS, CTX_MAX_CHARS)
    prev_summary = get_thread_summary(conn, thread_id) if thread_id else ""
    context_query = build_contextual_query(user_text, history_text, prev_summary, CTX_MAX_CHARS)

    # ---------- EXCEL ----------
    excel_rows = load_excel_texts()
    excel_match, excel_score = semantic_search_excel(context_query, excel_rows)

    # ===== CASE 1: EXCEL =====
    if excel_match:
        system_prompt = f"""
You are answering with the help of structured Excel row data. Use the running summary and conversation context to resolve pronouns and maintain continuity.

Running Summary:
{prev_summary or '(none)'}

Conversation Context:
{history_text}

Answer ONLY from this data (do not invent):
{excel_match['content']}

User Question:
{user_text}

Answer:
"""
        llm_messages = [SystemMessage(content=system_prompt)]

        partial = ""
        for chunk in llm_stream.stream(llm_messages):
            token = chunk.content or ""
            partial += token
            yield {"messages": [AIMessage(content=token)]}

        cleaned = sanitize_ai_response(partial, user_text)

        # ---- LLM verification ----
        verdict = verify_answer_with_llm(
            question=user_text,
            answer=cleaned,
            kb_excerpt=excel_match["content"]
        )
        add_refs = (verdict.get("answer_status") == "ANSWER")
        if not add_refs and not heuristic_noinfo(cleaned):
            pass

        if add_refs:
            cleaned += f"\n\n📄 **Source:** `{excel_match['filename']}`"

        cleaned += "\n\n**Is your issue resolved?**"

        # ---- Update running summary with last turn ----
        update_running_summary(thread_id, conn, prev_summary, user_text, cleaned)

        yield {"messages": [AIMessage(content=cleaned)]}
        return

    # ---------- AI SEARCH ----------
    raw_docs = azure_search(context_query)

    search_docs = [
        d for d in raw_docs
        if d["score"] >= AZURE_SEARCH_MIN_SCORE
        and len(d["chunk"].strip()) > 30
    ]

    # ===== CASE 2: AI SEARCH =====
    if search_docs:
        refs = list(set(d["title"] for d in search_docs))
        block = "\n\n".join(d["chunk"] for d in search_docs)

        system_prompt = f"""
You are answering from the internal knowledge base. Use the running summary and conversation context to resolve pronouns and maintain continuity.
If the answer is not present in the provided snippets, say you do not have that information.

Running Summary:
{prev_summary or '(none)'}

Conversation Context:
{history_text}

Knowledge Base Snippets (authoritative):
{block}

User Question:
{user_text}

Answer:
"""
        llm_messages = [SystemMessage(content=system_prompt)]

        partial = ""
        for chunk in llm_stream.stream(llm_messages):
            token = chunk.content or ""
            partial += token
            yield {"messages": [AIMessage(content=token)]}

        cleaned = sanitize_ai_response(partial, user_text)

        # ---- LLM verification ----
        verdict = verify_answer_with_llm(
            question=user_text,
            answer=cleaned,
            kb_excerpt=block
        )
        add_refs = (verdict.get("answer_status") == "ANSWER")
        if not add_refs and not heuristic_noinfo(cleaned):
            pass

        if add_refs:
            cleaned += f"\n\n📚 **References:** {', '.join(refs)}"

        cleaned += "\n\n**Is your issue resolved?**"

        # ---- Update running summary with last turn ----
        update_running_summary(thread_id, conn, prev_summary, user_text, cleaned)

        yield {"messages": [AIMessage(content=cleaned)]}
        return

    # ===== CASE 3: NOT FOUND =====
    cleaned = (
        "I'm sorry, I can only provide information based on the provided knowledge base. "
        "If you have questions related to the project content, feel free to ask!"
        "\n\n**Is your issue resolved?**"
    )

    # ---- Update running summary (even for 'not found' helps continuity) ----
    update_running_summary(thread_id, conn, prev_summary, user_text, cleaned)

    yield {"messages": [AIMessage(content=cleaned)]}

# ---------------------------------------------------------
# GRAPH
# ---------------------------------------------------------

conn = sqlite3.connect("chatbot.db", check_same_thread=False)
checkpointer = SqliteSaver(conn=conn)
init_summary_store(conn)  # ensure the summary table exists

graph = StateGraph(ChatState)
graph.add_node("chat_node", chat_node)
graph.add_edge(START, "chat_node")
graph.add_edge("chat_node", END)

chatbot = graph.compile(checkpointer=checkpointer)

# ---------------------------------------------------------
# MEMORY STORE (UI-only helper)
# ---------------------------------------------------------

_in_memory_threads = {}

def store_message(thread_id: str, role: str, content: str):
    if thread_id not in _in_memory_threads:
        _in_memory_threads[thread_id] = {
            "messages": [],
            "summary": ""
        }

    _in_memory_threads[thread_id]["messages"].append({
        "role": role,
        "content": content
    })

    if role == "user" and not _in_memory_threads[thread_id]["summary"]:
        _in_memory_threads[thread_id]["summary"] = summarize_for_sidebar(content)

def load_memory(thread_id: str):
    return _in_memory_threads.get(thread_id, {"messages": [], "summary": ""})

def clear_memory(thread_id: str):
    if thread_id in _in_memory_threads:
        del _in_memory_threads[thread_id]

__all__ = ["chatbot", "store_message", "load_memory", "clear_memory"]
