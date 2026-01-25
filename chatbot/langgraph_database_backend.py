
import os, io, re, sqlite3
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

# ---------------------------------------------------------
# REFERENCE APPEND DECISION
# ---------------------------------------------------------

_NO_INFO_PATTERNS = [
    r"\b(i\s*don'?t\s*(?:find|see|have)|cannot\s*(?:find|locate)|can't\s*(?:find|locate))\b",
    r"\b(no\s+(?:relevant|related)\s+(?:info|information|data|results))\b",
    r"\b(not\s+(?:found|available|present|in\s+(?:the\s+)?kb|in\s+(?:the\s+)?knowledge\s+base))\b",
    r"\b(i\s*(?:do\s+not|don't)\s*(?:know|have enough information))\b",
    r"\b(unable\s+to\s+(?:find|locate|answer|determine))\b",
    r"\b(out\s+of\s+scope|not\s+in\s+scope)\b",
    r"\b(no\s+match(?:es)?|no\s+matching\s+results)\b",
    r"\b(i\s+can\s+only\s+provide\s+information\s+based\s+on\s+the\s+provided\s+knowledge\s+base)\b"
]

def should_add_references(answer_text: str) -> bool:
    """
    Heuristic to decide whether to append references/sources.
    If the answer looks like a 'no info / not found' response, return False.
    Otherwise True.
    """
    if not answer_text:
        return False

    text = answer_text.strip().lower()
    for pat in _NO_INFO_PATTERNS:
        if re.search(pat, text):
            return False

    # Avoid references on extremely short / generic replies
    if len(text) < 30:
        return False

    return True

# ---------------------------------------------------------
# GREETING
# ---------------------------------------------------------

def llm_is_greeting(text: str) -> bool:
    try:
        prompt = [
            SystemMessage(content="Reply only with GREETING or ⏳ Processing..."),
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

def semantic_search_excel(question, excel_rows):
    q_emb = get_embedding(question)

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

# ---------------------------------------------------------
# CHAT NODE
# ---------------------------------------------------------

def chat_node(state: ChatState):
    messages = state["messages"]

    # last user msg
    user_text = ""
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            user_text = m.content.strip()
            break

    # ---------- GREETING ----------
    if llm_is_greeting(user_text):
        yield {"messages": [AIMessage(content="Hello 👋 How can I assist you today?")]}
        return

    yield {"messages": [AIMessage(content="⏳ Processing your request...")]}

    # ---------- EXCEL ----------
    excel_rows = load_excel_texts()
    excel_match, excel_score = semantic_search_excel(user_text, excel_rows)

    # ===== CASE 1: EXCEL =====
    if excel_match:
        system_prompt = f"""
Answer ONLY from this data:

{excel_match['content']}

User Question: {user_text}
Answer:
"""
        llm_messages = [SystemMessage(content=system_prompt)]

        partial = ""
        for chunk in llm_stream.stream(llm_messages):
            token = chunk.content or ""
            partial += token
            yield {"messages": [AIMessage(content=token)]}

        cleaned = sanitize_ai_response(partial, user_text)

        # Only add source if the answer looks confident/relevant
        if should_add_references(cleaned):
            cleaned += f"\n\n📄 **Source:** `{excel_match['filename']}`"

        cleaned += "\n\n**Is your issue resolved?**"

        yield {"messages": [AIMessage(content=cleaned)]}
        return

    # ---------- AI SEARCH ----------
    raw_docs = azure_search(user_text)

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
Answer ONLY from this knowledge base:

{block}

User Question: {user_text}
Answer:
"""
        llm_messages = [SystemMessage(content=system_prompt)]

        partial = ""
        for chunk in llm_stream.stream(llm_messages):
            token = chunk.content or ""
            partial += token
            yield {"messages": [AIMessage(content=token)]}

        cleaned = sanitize_ai_response(partial, user_text)

        # Only add references if the answer looks confident/relevant
        if should_add_references(cleaned):
            cleaned += f"\n\n📚 **References:** {', '.join(refs)}"

        cleaned += "\n\n**Is your issue resolved?**"

        yield {"messages": [AIMessage(content=cleaned)]}
        return

    # ===== CASE 3: NOT FOUND =====
    cleaned = (
        "I'm sorry, I can only provide information based on the provided knowledge base. "
        "If you have questions related to the project content, feel free to ask!"
        "\n\n**Is your issue resolved?**"
    )
    yield {"messages": [AIMessage(content=cleaned)]}

# ---------------------------------------------------------
# GRAPH
# ---------------------------------------------------------

conn = sqlite3.connect("chatbot.db", check_same_thread=False)
checkpointer = SqliteSaver(conn=conn)

graph = StateGraph(ChatState)
graph.add_node("chat_node", chat_node)
graph.add_edge(START, "chat_node")
graph.add_edge("chat_node", END)

chatbot = graph.compile(checkpointer=checkpointer)

# ---------------------------------------------------------
# MEMORY STORE
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
