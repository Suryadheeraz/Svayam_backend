# langgraph_database_backend.py

import os, io, re, sqlite3
from typing import TypedDict, Annotated, Optional
from pathlib import Path

import pandas as pd
import numpy as np
import requests
from dotenv import load_dotenv

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph.message import add_messages

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langchain_openai import AzureChatOpenAI

from azure.storage.blob import BlobServiceClient
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from azure.core.pipeline.transport import RequestsTransport
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

# ---------------------------------------------------------
# LLM CONFIG
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
# BLOB EXCEL LOADER
# ---------------------------------------------------------

def load_excel_texts():
    all_rows = []

    for blob in container_client.list_blobs(name_starts_with=FOLDER_PREFIX):
        if blob.name.endswith(".xlsx") or blob.name.endswith(".xls"):
            stream = container_client.download_blob(blob.name).readall()
            df = pd.read_excel(io.BytesIO(stream)).head(20)
            df = df.astype(str)
            text_dump = df.to_string(index=False)

            all_rows.append({
                "filename": blob.name,
                "content": text_dump
            })

    return all_rows

# ---------------------------------------------------------
# SEMANTIC SEARCH (EXCEL)
# ---------------------------------------------------------

def semantic_search_excel(question, excel_rows, threshold=0.75):
    q_emb = get_embedding(question)

    best_match = None
    best_score = 0

    for item in excel_rows:
        content_emb = get_embedding(item["content"])
        score = np.dot(q_emb, content_emb) / (np.linalg.norm(q_emb) * np.linalg.norm(content_emb))

        if score > best_score:
            best_score = score
            best_match = item

    if best_score > threshold:
        return best_match, best_score

    return None, best_score

# ---------------------------------------------------------
# AZURE SEARCH
# ---------------------------------------------------------

def azure_search(query: str, top: int = 3):
    results = search_client.search(search_text=query, top=top)
    docs = []
    for r in results:
        chunk = r.get("chunk") or ""
        title = r.get("title") or "KB Doc"
        docs.append({"title": title, "chunk": chunk})
    return docs

# ---------------------------------------------------------
# SANITIZER
# ---------------------------------------------------------

def sanitize_ai_response(raw: str, user_text: str):
    if not raw:
        return ""
    txt = raw.strip()
    txt = re.sub(re.escape(user_text), "", txt, flags=re.IGNORECASE).strip()
    txt = re.sub(r"^(as an ai|you asked|your question).*?(\.|:|\n)", "", txt, flags=re.IGNORECASE).strip()
    return txt

# ---------------------------------------------------------
# STATE
# ---------------------------------------------------------

class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    project_name: Optional[str]

# ---------------------------------------------------------
# HYBRID CHAT NODE
# ---------------------------------------------------------

def chat_node(state: ChatState):
    messages = state["messages"]

    # last user msg
    user_text = ""
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            user_text = m.content
            break

    # -------------------------------
    # STEP 1 — EXCEL (BLOB SEMANTIC)
    # -------------------------------
    excel_rows = load_excel_texts()
    excel_match, score = semantic_search_excel(user_text, excel_rows)

    # -------------------------------
    # STEP 2 — AZURE SEARCH
    # -------------------------------
    search_docs = []
    if not excel_match:
        search_docs = azure_search(user_text)

    # -------------------------------
    # PROMPT ROUTING
    # -------------------------------

    if excel_match:
        system_prompt = f"""
You are an enterprise support assistant.
Answer ONLY from ticket system data.

Source File: {excel_match['filename']}
Content:
{excel_match['content']}

User Question: {user_text}
Answer:
"""
        llm_messages = [SystemMessage(content=system_prompt)]

    elif search_docs:
        block = "\n\n".join(
            f"Title: {d['title']}\nContent: {d['chunk']}"
            for d in search_docs
        )

        system_prompt = f"""
You are an enterprise support assistant.
Answer using enterprise knowledge base only.

Knowledge Base:
{block}

User Question: {user_text}
Answer:
"""
        llm_messages = [SystemMessage(content=system_prompt)]

    else:
        system_prompt = "You are a helpful enterprise assistant."
        llm_messages = [SystemMessage(content=system_prompt)] + messages

    # -------------------------------
    # STREAMING
    # -------------------------------
    partial = ""
    for chunk in llm.stream(llm_messages):
        token = chunk.content or ""
        partial += token
        yield {"messages": [AIMessage(content=token)]}

    cleaned = sanitize_ai_response(partial, user_text)
    cleaned += "\n\n**Is your issue resolved?**"

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
        _in_memory_threads[thread_id] = []
    _in_memory_threads[thread_id].append({"role": role, "content": content})

def load_memory(thread_id: str):
    return _in_memory_threads.get(thread_id, [])

def clear_memory(thread_id: str):
    if thread_id in _in_memory_threads:
        del _in_memory_threads[thread_id]

__all__ = ["chatbot", "store_message", "load_memory", "clear_memory"]