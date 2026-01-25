# langgraph_database_backend.py
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

EXCEL_SIM_THRESHOLD = 0.75
AZURE_SEARCH_MIN_SCORE = 0.25   # general KB friendly

HISTORY_WINDOW = 6   # number of past turns used for memory reasoning

# ---------------------------------------------------------
# SINGLE LLM
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

def get_embedding(text: str):
    emb = openai_client.embeddings.create(
        model="text-embedding-3-large",
        input=text
    )
    return np.array(emb.data[0].embedding)

# ---------------------------------------------------------
# UTILS
# ---------------------------------------------------------

def sanitize(text: str):
    if not text:
        return ""
    t = text.strip()
    t = re.sub(r"^as an ai.*?\n", "", t, flags=re.I)
    return t.strip()

# ---------------------------------------------------------
# MEMORY UTILS
# ---------------------------------------------------------

def build_history(messages, limit=HISTORY_WINDOW):
    history = []
    for m in messages[-limit:]:
        if isinstance(m, HumanMessage):
            history.append(f"User: {m.content}")
        elif isinstance(m, AIMessage):
            history.append(f"Assistant: {m.content}")
    return "\n".join(history)

# ---------------------------------------------------------
# GREETING (SAME LLM)
# ---------------------------------------------------------

def is_greeting(text: str) -> bool:
    prompt = [
        SystemMessage(content="Classify message. Reply only GREETING or QUERY."),
        HumanMessage(content=text)
    ]
    try:
        resp = llm.invoke(prompt)
        return (resp.content or "").strip().upper() == "GREETING"
    except:
        return False

# ---------------------------------------------------------
# LLM ANSWER CHECKER
# ---------------------------------------------------------

def llm_says_not_found(answer_text: str) -> bool:
    prompt = [
        SystemMessage(content=(
            "Classify the assistant answer.\n"
            "Reply only with one word:\n"
            "FOUND  -> if answer contains real useful information\n"
            "NOT_FOUND -> if answer says not available, not found, no info, cannot answer, not in knowledge base"
        )),
        HumanMessage(content=f"Answer:\n{answer_text}")
    ]

    try:
        resp = llm.invoke(prompt)
        result = (resp.content or "").strip().upper()
        return result == "NOT_FOUND"
    except:
        return False   # fail-safe: assume FOUND

# ---------------------------------------------------------
# AI QUERY REWRITER (SEMANTIC SEARCH LAYER)
# ---------------------------------------------------------

def rewrite_query_with_llm(user_text: str, history_text: str):
    prompt = [
        SystemMessage(content="""
You are a semantic query rewriting agent.
Convert the user's question into a clear, searchable semantic query.
Preserve intent.
Resolve pronouns using context.
Remove ambiguity.
Expand abbreviations.
Use enterprise terminology.
Return ONLY the rewritten query.
"""),
        HumanMessage(content=f"""
Conversation context:
{history_text}

User question:
{user_text}
""")
    ]

    try:
        resp = llm.invoke(prompt)
        return sanitize(resp.content)
    except:
        return user_text

# ---------------------------------------------------------
# EXCEL
# ---------------------------------------------------------

def load_excel_texts():
    rows = []
    for blob in container_client.list_blobs(name_starts_with=FOLDER_PREFIX):
        if blob.name.endswith(".xlsx") or blob.name.endswith(".xls"):
            stream = container_client.download_blob(blob.name).readall()
            df = pd.read_excel(io.BytesIO(stream)).astype(str)

            for _, row in df.iterrows():
                text = " | ".join(f"{c}: {row[c]}" for c in df.columns)
                rows.append({
                    "filename": blob.name,
                    "content": text
                })
    return rows

def semantic_search_excel(query: str, rows):
    q_emb = get_embedding(query)
    best, best_score = None, 0

    for r in rows:
        emb = get_embedding(r["content"])
        score = np.dot(q_emb, emb) / (np.linalg.norm(q_emb) * np.linalg.norm(emb))
        if score > best_score:
            best_score = score
            best = r

    if best_score >= EXCEL_SIM_THRESHOLD:
        return best
    return None

# ---------------------------------------------------------
# AZURE SEARCH
# ---------------------------------------------------------

def azure_search(query: str, top=5):
    results = search_client.search(search_text=query, top=top)
    docs = []
    for r in results:
        docs.append({
            "title": r.get("title") or "KB Doc",
            "chunk": r.get("chunk") or "",
            "score": r.get("@search.score", 0)
        })
    return docs

# ---------------------------------------------------------
# STATE
# ---------------------------------------------------------

class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    project_name: Optional[str]
    thread_id: Optional[str]

# ---------------------------------------------------------
# CHAT NODE (MEMORY + AI SEARCH)
# ---------------------------------------------------------

def chat_node(state: ChatState):
    messages = state["messages"]

    # last user msg
    user_text = ""
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            user_text = m.content.strip()
            break

    history_text = build_history(messages)

    # ---- Greeting ----
    if is_greeting(user_text):
        yield {"messages": [AIMessage(content="Hello 👋 How can I help you today?")]}
        return

    yield {"messages": [AIMessage(content="⏳ Processing...")]}

    # ---- Excel first ----
    excel_rows = load_excel_texts()
    excel_match = semantic_search_excel(user_text, excel_rows)

    if excel_match:
        prompt = f"""
Conversation so far:
{history_text}

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

        if not llm_says_not_found(final):
            final += f"\n\n📄 Source: `{excel_match['filename']}`"
            final += "\n\n**Is your issue resolved?**"
            yield {"messages": [AIMessage(content=final)]}
            return

    # ---- AI SEMANTIC SEARCH (KB) ----
    rewritten_query = rewrite_query_with_llm(user_text, history_text)

    docs = azure_search(rewritten_query)

    if not docs:
        docs = azure_search(user_text.split("?")[0])

    docs = [d for d in docs if d["score"] >= AZURE_SEARCH_MIN_SCORE]

    if docs:
        kb = "\n\n".join(d["chunk"] for d in docs)
        refs = list(set(d["title"] for d in docs))

        prompt = f"""
Conversation so far:
{history_text}

Answer ONLY from this knowledge base:

{kb}

User question:
{user_text}
"""
        partial = ""
        for chunk in llm.stream([SystemMessage(content=prompt)]):
            tok = chunk.content or ""
            partial += tok
            yield {"messages": [AIMessage(content=tok)]}

        final = sanitize(partial)

        if not llm_says_not_found(final):
            final += f"\n\n📚 References: {', '.join(refs)}"
            final += "\n\n**Is your issue resolved?**"
            yield {"messages": [AIMessage(content=final)]}
            return

    # ---- Fallback ----
    final = (
        "I couldn’t find this information in the knowledge base.\n"
        "Please rephrase your question or ask something related to the available project data."
        "\n\n**Is your issue resolved?**"
    )

    yield {"messages": [AIMessage(content=final)]}

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
# MEMORY (UI helper only)
# ---------------------------------------------------------

_in_memory_threads = {}

def store_message(thread_id: str, role: str, content: str):
    if thread_id not in _in_memory_threads:
        _in_memory_threads[thread_id] = {"messages": []}
    _in_memory_threads[thread_id]["messages"].append({"role": role, "content": content})

def load_memory(thread_id: str):
    return _in_memory_threads.get(thread_id, {"messages": []})

def clear_memory(thread_id: str):
    if thread_id in _in_memory_threads:
        del _in_memory_threads[thread_id]

__all__ = ["chatbot", "store_message", "load_memory", "clear_memory"]
