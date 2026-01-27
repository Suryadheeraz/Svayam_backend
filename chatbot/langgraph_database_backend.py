# langgraph_database_backend.py
import os, io, re, sqlite3
from typing import TypedDict, Annotated, Optional, List, Dict, Any
from pathlib import Path
from functools import lru_cache

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

EXCEL_SIM_THRESHOLD = 0.75
HISTORY_WINDOW = 6

# ---------------------------------------------------------
# LLM
# ---------------------------------------------------------

llm = AzureChatOpenAI(
    azure_endpoint=os.getenv("AZURE_GPT4O_ENDPOINT"),
    deployment_name=os.getenv("AZURE_GPT4O_DEPLOYMENT"),
    openai_api_version=os.getenv("AZURE_GPT4O_API_VERSION"),
    api_key=os.getenv("AZURE_GPT4O_API_KEY"),
    temperature=0,
    streaming=True
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

search_client = SearchClient(
    endpoint=AZURE_SEARCH_ENDPOINT,
    index_name=SEARCH_INDEX,
    credential=AzureKeyCredential(AZURE_SEARCH_KEY)
)

# ---------------------------------------------------------
# EMBEDDINGS
# ---------------------------------------------------------

@lru_cache(maxsize=4096)
def get_embedding(text: str):
    text = (text or "").strip()
    emb = openai_client.embeddings.create(
        model="text-embedding-3-large",
        input=text
    )
    return np.array(emb.data[0].embedding, dtype=np.float32)

def cosine_sim(a, b):
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0
    return float(np.dot(a, b) / denom)

# ---------------------------------------------------------
# UTILS
# ---------------------------------------------------------

def sanitize(text: str):
    if not text:
        return ""
    return re.sub(r"^as an ai.*?\n", "", text.strip(), flags=re.I)

def build_history(messages, limit=HISTORY_WINDOW):
    lines = []
    for m in messages[-limit:]:
        if isinstance(m, HumanMessage):
            lines.append(f"User: {m.content}")
        elif isinstance(m, AIMessage):
            lines.append(f"Assistant: {m.content}")
    return "\n".join(lines)

# ---------------------------------------------------------
# INTENT CLASSIFIER
# ---------------------------------------------------------

def classify_user_intent(text: str) -> str:
    prompt = [
        SystemMessage(content=(
            "Classify the user's message into ONLY one label:\n"
            "GREETING, FAREWELL, THANKS, SMALLTALK, QUERY"
        )),
        HumanMessage(content=text or "")
    ]
    try:
        resp = llm.invoke(prompt)
        label = (resp.content or "").strip().upper()
        return label
    except:
        return "QUERY"

# ---------------------------------------------------------
# SIMPLE NOT-FOUND CHECK
# ---------------------------------------------------------

def simple_not_found(answer: str) -> bool:
    if not answer:
        return True
    t = answer.lower()
    patterns = ["not found", "no info", "cannot answer", "not available", "do not have"]
    return any(p in t for p in patterns)

# ---------------------------------------------------------
# EXCEL SEARCH
# ---------------------------------------------------------

def load_excel_texts():
    rows = []
    for blob in container_client.list_blobs(name_starts_with=FOLDER_PREFIX):
        if blob.name.lower().endswith((".xlsx", ".xls")):
            try:
                stream = container_client.download_blob(blob.name).readall()
                df = pd.read_excel(io.BytesIO(stream)).astype(str)
            except:
                continue

            for _, row in df.iterrows():
                text = " | ".join(f"{c}: {row[c]}" for c in df.columns)
                rows.append({"filename": blob.name, "content": text})
    return rows

def semantic_search_excel(query: str, rows):
    if not rows:
        return None
    q_emb = get_embedding(query)
    best, best_score = None, 0
    for r in rows:
        emb = get_embedding(r["content"])
        score = cosine_sim(q_emb, emb)
        if score > best_score:
            best_score = score
            best = r
    if best_score >= EXCEL_SIM_THRESHOLD:
        return best
    return None

# ---------------------------------------------------------
# AZURE SEARCH (ORIGINAL TEXT ONLY)
# ---------------------------------------------------------

def azure_search(query: str, top=5):
    if not query.strip():
        return []

    results = search_client.search(
        search_text=query,
        top=top,
        query_type="simple"       # <-- IMPORTANT
    )

    docs = []
    for r in results:
        docs.append({
            "title": r.get("title") or "KB Doc",
            "chunk": (r.get("chunk") or "").strip(),
            "score": r.get("@search.score", 0)
        })
    return docs

# ---------------------------------------------------------
# STATE TYPE
# ---------------------------------------------------------

class ChatState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    project_name: Optional[str]
    thread_id: Optional[str]

# ---------------------------------------------------------
# MAIN CHAT NODE
# ---------------------------------------------------------

def chat_node(state: ChatState):
    messages = state["messages"]

    user_text = ""
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            user_text = m.content.strip()
            break

    history = build_history(messages)

    # Handle greetings / thanks / bye
    intent = classify_user_intent(user_text)
    if intent == "GREETING":
        yield {"messages": [AIMessage(content="Hello 👋 How can I help you today?")]}
        return
    if intent in ("THANKS", "FAREWELL"):
        yield {"messages": [AIMessage(content="You're welcome! Let me know if you need anything else. 😊")]}
        return
    if intent == "SMALLTALK":
        yield {"messages": [AIMessage(content="I’m here and ready to help! What would you like to do today?")]}
        return

    yield {"messages": [AIMessage(content="⏳ Processing...")]}

    # ---------------------------
    # 1. EXCEL SEARCH
    # ---------------------------
    rows = load_excel_texts()
    excel_match = semantic_search_excel(user_text, rows)

    if excel_match:
        prompt = f"""
Conversation:
{history}

Answer ONLY using this data:
{excel_match['content']}

User question:
{user_text}
"""
        partial = ""
        for chunk in llm.stream([SystemMessage(content=prompt)]):
            tok = chunk.content or ""
            partial += tok
            yield {"messages": [AIMessage(content=tok)]}

        final = sanitize(partial)
        if final and not simple_not_found(final):
            final += f"\n\n📄 Source: `{excel_match['filename']}`"
            final += "\n\n**Is your issue resolved?**"
            yield {"messages": [AIMessage(content=final)]}
            return

    # ---------------------------
    # 2. KB SEARCH (ORIGINAL QUERY ONLY)
    # ---------------------------
    docs = azure_search(user_text)

    # Keep ANY doc with valid text
    docs = [d for d in docs if d["chunk"]]

    if docs:
        kb_text = "\n\n".join(d["chunk"] for d in docs)
        refs = [d["title"] for d in docs]

        prompt = f"""
Conversation:
{history}

Answer ONLY using this knowledge base:
{kb_text}

User question:
{user_text}
"""
        partial = ""
        for chunk in llm.stream([SystemMessage(content=prompt)]):
            tok = chunk.content or ""
            partial += tok
            yield {"messages": [AIMessage(content=tok)]}

        final = sanitize(partial)
        if final and not simple_not_found(final):
            final += f"\n\n📚 References: {', '.join(refs)}"
            final += "\n\n**Is your issue resolved?**"
            yield {"messages": [AIMessage(content=final)]}
            return

    # ---------------------------
    # Fallback
    # ---------------------------
    fallback = (
        "I couldn't find this information in the knowledge base.\n"
        "Please rephrase your question or ask something else.\n\n"
        "**Is your issue resolved?**"
    )
    yield {"messages": [AIMessage(content=fallback)]}

# ---------------------------------------------------------
# GRAPH
# ---------------------------------------------------------

conn = sqlite3.connect("chatbot.db", check_same_thread=False)
checkpointer = SqliteSaver(conn)

graph = StateGraph(ChatState)
graph.add_node("chat_node", chat_node)
graph.add_edge(START, "chat_node")
graph.add_edge("chat_node", END)

chatbot = graph.compile(checkpointer=checkpointer)

# ---------------------------------------------------------
# MEMORY HELPERS
# ---------------------------------------------------------

_in_memory_threads = {}

def store_message(thread_id, role, content):
    if thread_id not in _in_memory_threads:
        _in_memory_threads[thread_id] = {"messages": []}
    _in_memory_threads[thread_id]["messages"].append({"role": role, "content": content})

def load_memory(thread_id):
    return _in_memory_threads.get(thread_id, {"messages": []})

def clear_memory(thread_id):
    if thread_id in _in_memory_threads:
        del _in_memory_threads[thread_id]

__all__ = ["chatbot", "store_message", "load_memory", "clear_memory"]