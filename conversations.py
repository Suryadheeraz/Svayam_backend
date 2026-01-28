# # api/conversations.py
# import os
# from typing import List, Dict, Any, Optional
# from fastapi import APIRouter, HTTPException, Depends
# from azure.cosmos import CosmosClient, exceptions
# from pydantic import BaseModel
# from datetime import datetime

# # Security Imports
# from database import User
# from security import get_current_user, get_current_admin_user

# from dotenv import load_dotenv
# load_dotenv()

# router = APIRouter(prefix="/api/conversations", tags=["Conversations"])

# # --- Configuration ---
# COSMOS_ENDPOINT = os.getenv("COSMOS_ENDPOINT")
# COSMOS_KEY = os.getenv("COSMOS_KEY")
# DATABASE_NAME = os.getenv("COSMOS_DATABASE", "svayam-db")
# CONTAINER_NAME = os.getenv("COSMOS_CONTAINER", "conversations")

# # --- Initialize Cosmos Client ---
# try:
#     cosmos_client = CosmosClient(COSMOS_ENDPOINT, COSMOS_KEY)
#     database = cosmos_client.get_database_client(DATABASE_NAME)
#     container = database.get_container_client(CONTAINER_NAME)
#     print(f"✅ Connected to Cosmos DB: {DATABASE_NAME}/{CONTAINER_NAME}")
# except Exception as e:
#     print(f"⚠️ Cosmos DB Connection Failed: {e}")
#     container = None

# # --- Models ---
# class Message(BaseModel):
#     sender: str
#     text: str
#     timestamp: Optional[str] = None

# class ConversationModel(BaseModel):
#     id: str
#     topic: str
#     user: str # User Name or Email
#     userId: str # Link to SQL User ID
#     startDate: str
#     isResolved: bool
#     category: Optional[str] = "General"
#     priority: Optional[str] = "Low"
#     messages: List[Message] = []

# # --- Endpoints ---

# @router.get("/", response_model=List[Dict[str, Any]])
# def get_all_conversations(admin: User = Depends(get_current_admin_user)):
#     """
#     Fetch ALL conversations from Cosmos DB (For Admin Dashboard).
#     """
#     if not container:
#         raise HTTPException(500, "Database connection unavailable")
    
#     try:
#         # Query all items, ordered by date descending (assuming 'startDate' exists)
#         # Note: Cosmos DB queries are case-sensitive
#         query = "SELECT * FROM c ORDER BY c._ts DESC"
#         items = list(container.query_items(
#             query=query,
#             enable_cross_partition_query=True
#         ))
#         return items
#     except exceptions.CosmosHttpResponseError as e:
#         raise HTTPException(500, f"Cosmos DB Error: {e.message}")

# @router.get("/my", response_model=List[Dict[str, Any]])
# def get_my_conversations(current_user: User = Depends(get_current_user)):
#     """
#     Fetch only conversations belonging to the logged-in user.
#     """
#     if not container:
#         raise HTTPException(500, "Database connection unavailable")
    
#     try:
#         # Filter by the user's email or ID
#         # Assuming your Cosmos document has a 'userId' or 'userEmail' field
#         query = "SELECT * FROM c WHERE c.userEmail = @email ORDER BY c._ts DESC"
#         params = [{"name": "@email", "value": current_user.email}]
        
#         items = list(container.query_items(
#             query=query,
#             parameters=params,
#             enable_cross_partition_query=True
#         ))
#         return items
#     except exceptions.CosmosHttpResponseError as e:
#         raise HTTPException(500, f"Cosmos DB Error: {e.message}")

# # Optional: Endpoint to create a new conversation (for testing)
# @router.post("/create")
# def create_conversation(conv: ConversationModel, user: User = Depends(get_current_user)):
#     if not container:
#         raise HTTPException(500, "Database connection unavailable")
    
#     # Enforce user identity
#     new_item = conv.dict()
#     new_item['user'] = user.name
#     new_item['userEmail'] = user.email
#     new_item['startDate'] = datetime.now().strftime("%Y-%m-%d")
    
#     try:
#         container.create_item(body=new_item)
#         return {"message": "Conversation created", "id": conv.id}
#     except exceptions.CosmosHttpResponseError as e:
#         raise HTTPException(500, f"Failed to save: {e.message}")



# # api/conversations.py
# from fastapi import APIRouter, HTTPException, Depends
# from typing import List, Dict, Any
# import uuid
# from datetime import datetime

# # Import your existing security and user models
# from database import User
# from security import get_current_user, get_current_admin_user

# # Import the helper file you uploaded
# import cosmos_store

# router = APIRouter(prefix="/api/conversations", tags=["Conversations"])

# # --- Helper to Map Cosmos format to Frontend format ---
# def map_cosmos_to_frontend(thread_id, messages, metadata=None):
#     """
#     Converts raw Cosmos DB messages into the Conversation object expected by React.
#     """
#     mapped_messages = []
    
#     # Defaults
#     topic = "New Conversation"
#     user_name = "Unknown User"
#     start_date = datetime.utcnow().isoformat()
#     is_resolved = False
#     priority = "Medium"
#     category = "General"

#     # Try to find metadata in the first message
#     if messages:
#         first_msg = messages[0]
#         msg_meta = first_msg.get("metadata", {})
        
#         # Extract metadata if available
#         if msg_meta:
#             topic = msg_meta.get("topic", topic)
#             user_name = msg_meta.get("userName", user_name)
#             priority = msg_meta.get("priority", priority)
#             category = msg_meta.get("category", category)
#             is_resolved = msg_meta.get("isResolved", False)
            
#         start_date = first_msg.get("timestamp", start_date)

#     for msg in messages:
#         # Map 'role' -> 'sender' and 'content' -> 'text'
#         role = msg.get("role")
#         sender = "ai" if role == "assistant" else "user"
        
#         mapped_messages.append({
#             "sender": sender,
#             "text": msg.get("content"),
#             "timestamp": msg.get("timestamp")
#         })

#     return {
#         "id": thread_id,
#         "topic": topic,
#         "user": user_name,
#         "startDate": start_date,
#         "isResolved": is_resolved,
#         "priority": priority,
#         "category": category,
#         "messages": mapped_messages
#     }

# # ==========================
# # ENDPOINTS
# # ==========================

# @router.get("/", response_model=List[Dict[str, Any]])
# def get_all_conversations(admin: User = Depends(get_current_admin_user)):
#     """
#     Admin: Fetch ALL recent conversations.
#     """
#     try:
#         # 1. Get list of recent thread IDs
#         threads = cosmos_store.list_threads_with_preview(limit=50)
        
#         conversations = []
#         for thread in threads:
#             t_id = thread['thread_id']
#             # 2. Load full messages for each thread to build the details
#             msgs = cosmos_store.load_messages(t_id)
#             if msgs:
#                 conv_obj = map_cosmos_to_frontend(t_id, msgs)
#                 conversations.append(conv_obj)
                
#         return conversations
#     except Exception as e:
#         print(f"Error fetching conversations: {e}")
#         raise HTTPException(status_code=500, detail=str(e))

# @router.get("/my", response_model=List[Dict[str, Any]])
# def get_my_conversations(user: User = Depends(get_current_user)):
#     """
#     User: Fetch only MY conversations.
#     Note: Since cosmos_store.py doesn't filter by user, we must query directly here.
#     """
#     try:
#         # We access the container directly to filter by user email stored in metadata
#         _, container = cosmos_store._get_db_and_container()
        
#         # Query to find threads where the first message's metadata contains this user's email
#         # Note: This assumes we store 'userEmail' in metadata (see create endpoint)
#         query = f"""
#         SELECT DISTINCT VALUE c.thread_id 
#         FROM c 
#         WHERE c.metadata.userEmail = '{user.email}'
#         """
        
#         thread_ids = list(container.query_items(query=query, enable_cross_partition_query=True))
        
#         conversations = []
#         for t_id in thread_ids:
#             msgs = cosmos_store.load_messages(t_id)
#             if msgs:
#                 conv_obj = map_cosmos_to_frontend(t_id, msgs)
#                 conversations.append(conv_obj)
                
#         return conversations
#     except Exception as e:
#         print(f"Error fetching my conversations: {e}")
#         raise HTTPException(status_code=500, detail=str(e))

# @router.post("/create")
# def create_conversation(data: Dict[str, Any], user: User = Depends(get_current_user)):
#     """
#     Create a new conversation thread.
#     """
#     try:
#         thread_id = str(uuid.uuid4())
#         initial_message = data.get("message", "New Chat Started")
#         topic = data.get("topic", "New Inquiry")
        
#         # Store critical info in metadata so we can filter later
#         metadata = {
#             "topic": topic,
#             "userEmail": user.email,
#             "userName": user.name,
#             "priority": "Medium",
#             "category": "General",
#             "isResolved": False
#         }
        
#         # Use cosmos_store to save
#         cosmos_store.append_message(thread_id, "user", initial_message, metadata)
        
#         return {"message": "Conversation created", "id": thread_id}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

# api/conversations.py

import pip_system_certs.wrapt_requests

import os
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends
from azure.cosmos import CosmosClient, PartitionKey, exceptions
from pydantic import BaseModel

# --- Security & Database Imports ---
from database_model import User
from main import get_current_user, get_current_admin_user
from main import get_db

from dotenv import load_dotenv
load_dotenv()

router = APIRouter(prefix="/api/conversations", tags=["Conversations"])

# =========================================================
# 1. COSMOS DB CONFIGURATION & CONNECTION
# =========================================================

# Use the AZURE_ names to match your existing .env file
COSMOS_ENDPOINT = os.getenv("COSMOS_ENDPOINT")
COSMOS_KEY = os.getenv("COSMOS_KEY")
COSMOS_DATABASE = os.getenv("COSMOS_DATABASE", "svayam-db")
COSMOS_CONTAINER = os.getenv("COSMOS_CONTAINER", "conversations")

if not COSMOS_ENDPOINT or not COSMOS_KEY:
    print("⚠️ Warning: Cosmos DB credentials missing in .env")

# Initialize Client with increased timeout
try:
    client = CosmosClient(COSMOS_ENDPOINT, COSMOS_KEY, connection_timeout=60, read_timeout=60, connection_verify=False)
    print(f"✅ Cosmos Client initialized for: {COSMOS_ENDPOINT}")
except Exception as e:
    print(f"❌ Failed to initialize Cosmos Client: {e}")
    client = None

def _get_container():
    """Helper to get the container client, creating DB/Container if needed."""
    if not client:
        raise HTTPException(500, "Cosmos DB client is not initialized.")
    
    try:
        db = client.create_database_if_not_exists(id=COSMOS_DATABASE)
        container = db.create_container_if_not_exists(
            id=COSMOS_CONTAINER,
            partition_key=PartitionKey(path="/thread_id"),
        )
        return container
    except Exception as e:
        raise HTTPException(500, f"Failed to connect to container: {e}")

# =========================================================
# 2. STORAGE HELPER FUNCTIONS (Embedded from cosmos_store.py)
# =========================================================

def append_message(thread_id: str, role: str, content: str, metadata: dict = None):
    """Appends a single message document to the container."""
    container = _get_container()
    msg_doc = {
        "id": str(uuid.uuid4()),
        "thread_id": thread_id,
        "role": role,
        "content": content,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "metadata": metadata or {}
    }
    return container.create_item(body=msg_doc)

def load_messages(thread_id: str, max_items: int = 1000):
    """Load all messages for a thread ordered by timestamp."""
    container = _get_container()
    # Select metadata too so we can recover Topic/User details
    query = "SELECT c.id, c.thread_id, c.role, c.content, c.timestamp, c.metadata FROM c WHERE c.thread_id = @thread_id ORDER BY c.timestamp ASC"
    params = [{"name": "@thread_id", "value": thread_id}]
    
    items = list(container.query_items(
        query=query, 
        parameters=params, 
        enable_cross_partition_query=False, # Single partition query
        max_item_count=max_items
    ))
    return items

def list_recent_threads(limit: int = 50):
    """
    Finds unique thread IDs from the most recent messages.
    Used for the Admin Dashboard.
    """
    container = _get_container()
    # Fetch recent messages to find active threads
    top_k = max(limit * 100, 1000) # Fetch more to ensure we find enough distinct threads
    query = f"SELECT TOP {top_k} c.thread_id, c.timestamp FROM c ORDER BY c.timestamp DESC"
    
    items = list(container.query_items(query=query, enable_cross_partition_query=True))
    
    seen_threads = set()
    unique_thread_ids = []
    
    for item in items:
        tid = item.get("thread_id")
        if tid and tid not in seen_threads:
            seen_threads.add(tid)
            unique_thread_ids.append(tid)
            if len(unique_thread_ids) >= limit:
                break
                
    return unique_thread_ids

def list_user_threads(user_email: str):
    """
    Finds threads belonging to a specific user based on metadata.
    Used for the User Sidebar.
    """
    container = _get_container()
    # Query finds all thread_ids where ANY message has this user's email in metadata
    query = "SELECT DISTINCT VALUE c.thread_id FROM c WHERE c.metadata.userEmail = @email"
    params = [{"name": "@email", "value": user_email}]
    
    thread_ids = list(container.query_items(
        query=query, 
        parameters=params, 
        enable_cross_partition_query=True
    ))
    return thread_ids

# =========================================================
# 3. DATA MAPPING
# =========================================================

def map_cosmos_to_frontend(thread_id, messages):
    # """
    # Converts raw Cosmos messages into the Conversation object structure expected by React.
    # """
    # mapped_messages = []
    
    # # Default values
    # topic = "New Conversation"
    # user_name = "Unknown User"
    # start_date = datetime.utcnow().strftime("%Y-%m-%d")
    # is_resolved = False
    # priority = "Medium"
    # category = "General"
    
    # # 1. Extract Metadata from the FIRST message (usually system or first user msg)
    # if messages:
    #     first_msg = messages[0]
    #     meta = first_msg.get("metadata", {})
        
    #     # If metadata is missing in first msg, try finding it in ANY message
    #     if not meta:
    #         for m in messages:
    #             if m.get("metadata"):
    #                 meta = m.get("metadata")
    #                 break
        
    #     if meta:
    #         topic = meta.get("topic", topic)
    #         user_name = meta.get("userName", user_name)
    #         priority = meta.get("priority", priority)
    #         category = meta.get("category", category)
    #         is_resolved = meta.get("isResolved", False)

    #     # Format timestamp for UI
    #     raw_ts = first_msg.get("timestamp")
    #     if raw_ts:
    #         try:
    #             dt = datetime.fromisoformat(raw_ts.replace("Z", ""))
    #             start_date = dt.strftime("%Y-%m-%d")
    #         except: pass

    # # 2. Map Messages
    # for msg in messages:
    #     role = msg.get("role")
    #     sender = "ai" if role == "assistant" else "user"
    #     mapped_messages.append({
    #         "sender": sender,
    #         "text": msg.get("content"),
    #         "timestamp": msg.get("timestamp")
    #     })

    # return {
    #     "id": thread_id,
    #     "topic": topic,
    #     "user": user_name,
    #     "startDate": start_date,
    #     "isResolved": is_resolved,
    #     "priority": priority,
    #     "category": category,
    #     "messages": mapped_messages
    # }
    """
    Converts raw Cosmos messages into the Conversation object structure expected by React.
    """
    mapped_messages = []
    
    # Default values
    topic = "New Conversation"
    user_name = "Unknown User"
    start_date = datetime.utcnow().strftime("%Y-%m-%d")
    is_resolved = False
    priority = "Medium"
    category = "General"
    
    # 1. Extract Metadata from the FIRST message
    if messages:
        first_msg = messages[0]
        meta = first_msg.get("metadata", {})
        
        # If metadata is missing in first msg, try finding it in ANY message
        if not meta:
            for m in messages:
                if m.get("metadata"):
                    meta = m.get("metadata")
                    break
        
        if meta:
            topic = meta.get("topic") # Get exact topic
            user_name = meta.get("userName", user_name)
            priority = meta.get("priority", priority)
            category = meta.get("category", category)
            is_resolved = meta.get("isResolved", False)

        # --- FIX: Smart Fallback for Title ---
        # If topic is still missing or generic, use the first message text
        if not topic or topic == "New Conversation":
            if first_msg.get("content"):
                # Use first 40 chars of message
                topic = first_msg.get("content")[:40] + "..."
            else:
                topic = f"Conversation #{thread_id[:4]}"
        # -------------------------------------

        # Format timestamp for UI
        raw_ts = first_msg.get("timestamp")
        if raw_ts:
            try:
                dt = datetime.fromisoformat(raw_ts.replace("Z", ""))
                start_date = dt.strftime("%Y-%m-%d")
            except: pass

    # 2. Map Messages
    for msg in messages:
        role = msg.get("role")
        sender = "ai" if role == "assistant" else "user"
        mapped_messages.append({
            "sender": sender,
            "text": msg.get("content"),
            "timestamp": msg.get("timestamp")
        })

    return {
        "id": thread_id,
        "topic": topic, # <--- Now populated with real data
        "user": user_name,
        "startDate": start_date,
        "isResolved": is_resolved,
        "priority": priority,
        "category": category,
        "messages": mapped_messages
    }

# =========================================================
# 4. API ENDPOINTS
# =========================================================

@router.get("/", response_model=List[Dict[str, Any]])
def get_all_conversations(admin: User = Depends(get_current_admin_user)):
    """
    ADMIN: Get all recent conversations.
    """
    try:
        # 1. Find recent threads
        thread_ids = list_recent_threads(limit=20)
        
        conversations = []
        for tid in thread_ids:
            # 2. Load details for each thread
            msgs = load_messages(tid)
            if msgs:
                conv = map_cosmos_to_frontend(tid, msgs)
                conversations.append(conv)
                
        return conversations
    except Exception as e:
        print(f"Error getting all conversations: {e}")
        # Return empty list instead of crashing if DB fails
        return []

@router.get("/my", response_model=List[Dict[str, Any]])
def get_my_conversations(user: User = Depends(get_current_user)):
    """
    USER: Get only my conversations.
    """
    try:
        # 1. Find my threads
        thread_ids = list_user_threads(user.email)
        
        conversations = []
        for tid in thread_ids:
            # 2. Load details
            msgs = load_messages(tid)
            if msgs:
                conv = map_cosmos_to_frontend(tid, msgs)
                conversations.append(conv)
        
        # Sort by date desc (newest first)
        conversations.sort(key=lambda x: x['startDate'], reverse=True)
        return conversations
    except Exception as e:
        print(f"Error getting my conversations: {e}")
        return []

@router.post("/create")
def create_conversation(data: Dict[str, Any], user: User = Depends(get_current_user)):
    """
    Create a new conversation thread.
    """
    try:
        thread_id = str(uuid.uuid4())
        initial_message = data.get("message", "New Chat Started")
        topic = data.get("topic", "New Inquiry")
        
        # Metadata to store with the message so we can find it later
        metadata = {
            "topic": topic,
            "userEmail": user.email,
            "userName": user.name,
            "priority": "Medium",
            "category": "General",
            "isResolved": False
        }
        
        append_message(thread_id, "user", initial_message, metadata)
        
        return {"message": "Conversation created", "id": thread_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/conversations")
def get_all_conversations(db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)):
    convs = db.query(Conversation).order_by(Conversation.created_at.desc()).all()
    return [{
        "conversation_uuid": c.uuid,
        "topic": c.topic,
        "startDate": c.created_at,
        "isResolved": c.is_resolved,
        "user": c.user_email
    } for c in convs]
