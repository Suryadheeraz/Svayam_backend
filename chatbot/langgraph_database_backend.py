# langgraph_database_backend.py
import os
import sqlite3
from typing import TypedDict, Annotated

from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langchain_openai import ChatOpenAI, AzureChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph.message import add_messages

# optional retrieval
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from azure.core.pipeline.transport import RequestsTransport
import requests


load_dotenv()

llm = AzureChatOpenAI(
    azure_endpoint=os.getenv("AZURE_GPT4O_ENDPOINT"),
    deployment_name=os.getenv("AZURE_GPT4O_DEPLOYMENT"),
    openai_api_version=os.getenv("AZURE_GPT4O_API_VERSION"),
    api_key=os.getenv("AZURE_GPT4O_API_KEY"),
    temperature=0,
    streaming=True
)
classifier_llm = llm


AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX")

if AZURE_SEARCH_ENDPOINT and AZURE_SEARCH_KEY:
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=0, pool_maxsize=0)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"Connection": "close"})
    transport = RequestsTransport(session=session)


def get_search_client(project_name: str):
    if not project_name:
        return None

    index_name = f"svayam-ams-{project_name}"

    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=0, pool_maxsize=0)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"Connection": "close"})
    transport = RequestsTransport(session=session)

    return SearchClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        index_name=index_name,
        credential=AzureKeyCredential(AZURE_SEARCH_KEY),
        transport=transport,
    )


def retrieve_docs(query: str, project_id: str, top: int = 3):
    """Fetch relevant docs from Azure Search (if configured)."""
    search_client = get_search_client(project_id)
    if not search_client or not query:
        return []

    results = search_client.search(search_text=query, top=top)
    docs = []
    for r in results:
        text = r.get("chunk") or r.get("content") or r.get("text") or ""
        if not text:
            continue
        if len(text) > 1200:
            text = text[:1200] + " ... [truncated]"
        title = (
            r.get("title")
            or r.get("metadata_storage_name")
            or r.get("file_name")
            or "Unknown Document"
        )
        docs.append({"id": r.get("id"), "title": title, "chunk": text})
    return docs


def is_greeting(text: str) -> bool:
    if not text or not text.strip():
        return False

    prompt = f"""
Classify the following user message as either GREETING or QUERY.

Message: "{text}"

Definitions:
- GREETING = A social greeting with NO request, NO issue, NO question.
- QUERY = Any message asking for help, describing a problem, or requiring information.

Respond with exactly one word: GREETING or QUERY.
"""
    try:
        resp = classifier_llm.invoke([HumanMessage(content=prompt)])
        output = (resp.content or "").strip().upper()
        return output == "GREETING"
    except Exception:
        return False


def sanitize_ai_response(raw_text: str, user_text: str) -> str:
    if not raw_text:
        return ""
    txt = raw_text.strip()
    user = (user_text or "").strip()
    import re

    txt = re.sub(r"^\s*(GREETING|QUERY)\s*$", "", txt, flags=re.IGNORECASE).strip()
    if user:
        txt = re.sub(re.escape(user), "", txt, flags=re.IGNORECASE).strip()
    txt = re.sub(
        r"^(you asked|regarding your query|your question was|as you asked|about your question).*?(\.|:|\n)",
        "",
        txt,
        flags=re.IGNORECASE,
    ).strip()
    return txt.strip()


class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def chat_node(state: ChatState,config: dict):
    messages = state.get("messages", [])

    user_text = ""
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            user_text = getattr(m, "content", "") or ""
            break

    project_name = config.get("configurable", {}).get("project_name") 
    greeting = is_greeting(user_text)
    
    if not project_name:
        print("⚠️  WARNING: No project_name in config!")  # ✅ Added warning
    else:
        print(f"💬 Processing message for project: {project_name}")
        
    retrieved = retrieve_docs(user_text, project_name, top=3) if (user_text and not greeting) else []

    if retrieved:
        blocks = []
        for i, d in enumerate(retrieved, start=1):
            blocks.append(f"Source [{i}]\nTitle: {d['title']}\nContent: {d['chunk']}")
        retrieved_block = "\n\n".join(blocks)
        system_prompt = (
            "You are an enterprise support assistant. Use the retrieved context when answering.\n\n"
            f"Retrieved Context:\n{retrieved_block}"
        )
    else:
        system_prompt = "You are a helpful enterprise assistant."

    response = llm.invoke([SystemMessage(content=system_prompt)] + messages)
    answer = getattr(response, "content", "").strip()

    if answer.upper() in ("GREETING", "QUERY"):
        answer = ""

    cleaned = sanitize_ai_response(answer, user_text)

    if not greeting:
        cleaned += "\n\n**Is your issue resolved?**"

    return {"messages": [AIMessage(content=cleaned)]}


conn = sqlite3.connect("chatbot.db", check_same_thread=False)
checkpointer = SqliteSaver(conn=conn)

graph = StateGraph(ChatState)
graph.add_node("chat_node", chat_node)
graph.add_edge(START, "chat_node")
graph.add_edge("chat_node", END)

chatbot = graph.compile(checkpointer=checkpointer)

__all__ = ["chatbot"]

