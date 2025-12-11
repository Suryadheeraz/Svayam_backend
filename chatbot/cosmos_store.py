# cosmos_store.py
# from azure.cosmos import CosmosClient, PartitionKey, exceptions
# from dotenv import load_dotenv
# import os
# from datetime import datetime
# import uuid

# load_dotenv()

# COSMOS_ENDPOINT = os.getenv("COSMOS_ENDPOINT")
# COSMOS_KEY = os.getenv("COSMOS_KEY")
# COSMOS_DATABASE = os.getenv("COSMOS_DATABASE", "svayamams")
# COSMOS_CONTAINER = os.getenv("COSMOS_CONTAINER", "chat-conversations")

# if not COSMOS_ENDPOINT or not COSMOS_KEY:
#     raise RuntimeError("COSMOS_ENDPOINT or COSMOS_KEY is not set in environment/.env")

# # Create client
# client = CosmosClient(COSMOS_ENDPOINT, COSMOS_KEY)

# def _get_db_and_container():
#     db = client.create_database_if_not_exists(id=COSMOS_DATABASE)
#     container = db.create_container_if_not_exists(
#         id=COSMOS_CONTAINER,
#         partition_key=PartitionKey(path="/thread_id"),
#         offer_throughput=400
#     )
#     return db, container

# # Append a single message document to the container
# def append_message(thread_id: str, role: str, content: str, metadata: dict = None):
#     _, container = _get_db_and_container()
#     msg_doc = {
#         "id": str(uuid.uuid4()),
#         "thread_id": thread_id,
#         "role": role,
#         "content": content,
#         "timestamp": datetime.utcnow().isoformat() + "Z",
#         "metadata": metadata or {}
#     }
#     return container.create_item(body=msg_doc)

# # Load all messages for a thread ordered by timestamp (asc)
# def load_messages(thread_id: str, max_items: int = 1000):
#     _, container = _get_db_and_container()
#     query = "SELECT c.id, c.thread_id, c.role, c.content, c.timestamp FROM c WHERE c.thread_id = @thread_id ORDER BY c.timestamp ASC"
#     params = [{"name": "@thread_id", "value": thread_id}]
#     items = list(container.query_items(query=query, parameters=params, enable_cross_partition_query=False, max_item_count=max_items))
#     return items

# # Return recent threads with a preview (the most recent message content)
# def list_threads_with_preview(limit: int = 100):
#     """
#     Returns a list of dicts: [{"thread_id": "...", "preview": "...", "timestamp": "..."} ...]
#     Implementation: query recent messages globally ordered by timestamp desc, then keep first occurrence per thread_id (latest message).
#     """
#     _, container = _get_db_and_container()
#     # fetch recent messages (limit * 5 to increase chance of catching distinct threads)
#     top_k = max(limit * 5, 200)
#     query = f"SELECT TOP {top_k} c.thread_id, c.content, c.timestamp FROM c ORDER BY c.timestamp DESC"
#     items = list(container.query_items(query=query, enable_cross_partition_query=True, max_item_count=top_k))
#     seen = {}
#     results = []
#     for it in items:
#         tid = it.get("thread_id")
#         if not tid:
#             continue
#         if tid in seen:
#             continue
#         seen[tid] = True
#         results.append({
#             "thread_id": tid,
#             "preview": (it.get("content")[:200] + " ...") if it.get("content") and len(it.get("content")) > 200 else it.get("content") or "",
#             "timestamp": it.get("timestamp")
#         })
#         if len(results) >= limit:
#             break
#     return results

# # Optional: read a single doc (not used much)
# def read_message(item_id: str, partition_key: str):
#     _, container = _get_db_and_container()
#     try:
#         return container.read_item(item=item_id, partition_key=partition_key)
#     except exceptions.CosmosResourceNotFoundError:
#         return None

# # Delete ALL messages for a thread
# def delete_thread(thread_id: str):
#     _, container = _get_db_and_container()

#     # Query all items for the thread_id
#     query = "SELECT c.id, c.thread_id FROM c WHERE c.thread_id = @thread_id"
#     params = [{"name": "@thread_id", "value": thread_id}]
#     items = list(container.query_items(
#         query=query,
#         parameters=params,
#         enable_cross_partition_query=False
#     ))

#     # Delete each message document
#     for item in items:
#         try:
#             container.delete_item(
#                 item=item["id"],
#                 partition_key=item["thread_id"]
#             )
#         except Exception as e:
#             print(f"Failed to delete item {item['id']}: {str(e)}")

#     return True


# chatbot/cosmos_store.py
# # cosmos_store.py - FIXED VERSION with proper timeout configuration
# from azure.cosmos import CosmosClient, PartitionKey, exceptions
# from azure.core.pipeline.transport import RequestsTransport
# from dotenv import load_dotenv
# import os
# from datetime import datetime
# import uuid
# import time
# import requests

# load_dotenv()

# COSMOS_ENDPOINT = os.getenv("COSMOS_ENDPOINT")
# COSMOS_KEY = os.getenv("COSMOS_KEY")
# COSMOS_DATABASE = os.getenv("COSMOS_DATABASE", "svayamams")
# COSMOS_CONTAINER = os.getenv("COSMOS_CONTAINER", "chat-conversations")

# # ===================================================================
# # CRITICAL: Configure timeouts at the HTTP transport level
# # ===================================================================
# _client = None
# _db = None
# _container = None
# _initialization_error = None
# _max_retries = 3

# # Configure requests session with proper timeouts
# def create_transport_with_timeout(timeout_seconds=30):
#     """
#     Create a custom transport with configurable timeout.
#     This is the ONLY way to override the SDK's default 3-second timeout.
#     """
#     session = requests.Session()
    
#     # Configure adapter with timeouts
#     adapter = requests.adapters.HTTPAdapter(
#         pool_connections=10,
#         pool_maxsize=10,
#         max_retries=0  # We handle retries ourselves
#     )
#     session.mount("https://", adapter)
#     session.mount("http://", adapter)
    
#     # Monkey-patch the request method to include timeout
#     original_request = session.request
#     def request_with_timeout(*args, **kwargs):
#         kwargs.setdefault('timeout', timeout_seconds)
#         return original_request(*args, **kwargs)
#     session.request = request_with_timeout
    
#     return RequestsTransport(session=session)


# def _get_db_and_container():
#     """
#     Lazy initialization with proper timeout handling.
#     """
#     global _client, _db, _container, _initialization_error
    
#     # Return cached connection
#     if _db is not None and _container is not None:
#         return _db, _container
    
#     # Return cached error
#     if _initialization_error is not None:
#         raise _initialization_error
    
#     # Check configuration
#     if not COSMOS_ENDPOINT or not COSMOS_KEY:
#         _initialization_error = RuntimeError(
#             "COSMOS_ENDPOINT or COSMOS_KEY is not set in environment/.env"
#         )
#         raise _initialization_error
    
#     retry_count = 0
#     last_error = None
    
#     while retry_count < _max_retries:
#         try:
#             print(f"🔄 Initializing Cosmos DB (attempt {retry_count + 1}/{_max_retries})...")
#             print(f"   Endpoint: {COSMOS_ENDPOINT}")
#             start_time = time.time()
            
#             # ============================================================
#             # CRITICAL FIX: Use custom transport with 30-second timeout
#             # ============================================================
#             transport = create_transport_with_timeout(timeout_seconds=30)
            
#             _client = CosmosClient(
#                 COSMOS_ENDPOINT,
#                 credential=COSMOS_KEY,
#                 transport=transport,  # <-- This overrides the 3s timeout
#                 connection_timeout=30,
#                 request_timeout=30,
#                 retry_total=1,
#                 retry_backoff_max=5,
#             )
            
#             print(f"📡 Testing database connection...")
            
#             # Test connection
#             _db = _client.create_database_if_not_exists(id=COSMOS_DATABASE)
#             print(f"✅ Database '{COSMOS_DATABASE}' connected")
            
#             _container = _db.create_container_if_not_exists(
#                 id=COSMOS_CONTAINER,
#                 partition_key=PartitionKey(path="/thread_id"),
#                 offer_throughput=400
#             )
            
#             elapsed = time.time() - start_time
#             print(f"✅ Cosmos DB ready! ({elapsed:.2f}s)")
#             print(f"   - Container: {COSMOS_CONTAINER}")
            
#             return _db, _container
            
#         except exceptions.CosmosHttpResponseError as e:
#             last_error = e
#             print(f"❌ HTTP Error (attempt {retry_count + 1}): {e.status_code} - {e.message}")
            
#             # Don't retry authentication errors
#             if e.status_code in [401, 403]:
#                 _initialization_error = ConnectionError(
#                     f"Authentication failed: Check COSMOS_KEY in .env file"
#                 )
#                 raise _initialization_error
                
#         except requests.exceptions.Timeout as e:
#             last_error = e
#             print(f"❌ Timeout (attempt {retry_count + 1}): Connection took >30s")
#             print(f"   This indicates network/firewall issues")
            
#         except requests.exceptions.ConnectionError as e:
#             last_error = e
#             print(f"❌ Connection Error (attempt {retry_count + 1}): {str(e)}")
#             print(f"   Cannot reach {COSMOS_ENDPOINT}")
            
#         except Exception as e:
#             last_error = e
#             error_type = type(e).__name__
#             print(f"❌ {error_type} (attempt {retry_count + 1}): {str(e)}")
        
#         retry_count += 1
#         if retry_count < _max_retries:
#             wait_time = 2 ** retry_count
#             print(f"⏳ Retrying in {wait_time}s...")
#             time.sleep(wait_time)
    
#     # All retries exhausted
#     _initialization_error = ConnectionError(
#         f"Cosmos DB connection failed after {_max_retries} attempts. "
#         f"Last error: {type(last_error).__name__}: {str(last_error)}"
#     )
    
#     print(f"\n{'='*70}")
#     print(f"❌ COSMOS DB CONNECTION FAILED")
#     print(f"{'='*70}")
#     print(f"Endpoint: {COSMOS_ENDPOINT}")
#     print(f"Database: {COSMOS_DATABASE}")
#     print(f"Container: {COSMOS_CONTAINER}")
#     print(f"\n⚠️  MOST LIKELY CAUSE: Firewall blocking connection")
#     print(f"\nTroubleshooting:")
#     print(f"1. Go to Azure Portal → Cosmos DB → Networking → Firewall")
#     print(f"2. Add your IP address: Check https://whatismyip.com")
#     print(f"3. Or enable 'Allow access from Azure Portal' temporarily")
#     print(f"4. Verify Key: Check if COSMOS_KEY is correct")
#     print(f"5. Test connectivity: ping svayam-cosmos.documents.azure.com")
#     print(f"{'='*70}\n")
    
#     raise _initialization_error


# # ===================================================================
# # PUBLIC API - WITH GRACEFUL DEGRADATION
# # ===================================================================

# def append_message(thread_id: str, role: str, content: str, metadata: dict = None):
#     """Append message - fails gracefully if Cosmos unavailable."""
#     try:
#         _, container = _get_db_and_container()
        
#         msg_doc = {
#             "id": str(uuid.uuid4()),
#             "thread_id": thread_id,
#             "role": role,
#             "content": content,
#             "timestamp": datetime.utcnow().isoformat() + "Z",
#             "metadata": metadata or {}
#         }
        
#         return container.create_item(body=msg_doc)
        
#     except Exception as e:
#         print(f"⚠️  Failed to append message to Cosmos: {e}")
#         # Don't crash - let in-memory storage handle it
#         return None


# def load_messages(thread_id: str, max_items: int = 1000):
#     """Load messages - returns empty list if Cosmos unavailable."""
#     try:
#         _, container = _get_db_and_container()
        
#         query = """
#             SELECT c.id, c.thread_id, c.role, c.content, c.timestamp 
#             FROM c 
#             WHERE c.thread_id = @thread_id 
#             ORDER BY c.timestamp ASC
#         """
#         params = [{"name": "@thread_id", "value": thread_id}]
        
#         items = list(container.query_items(
#             query=query, 
#             parameters=params, 
#             enable_cross_partition_query=False, 
#             max_item_count=max_items
#         ))
        
#         return items
        
#     except Exception as e:
#         print(f"⚠️  Failed to load messages from Cosmos: {e}")
#         # Return empty list - in-memory storage will be used instead
#         return []


# def list_threads_with_preview(limit: int = 100):
#     """List threads - returns empty list if unavailable."""
#     try:
#         _, container = _get_db_and_container()
        
#         top_k = max(limit * 5, 200)
#         query = f"""
#             SELECT TOP {top_k} c.thread_id, c.content, c.timestamp 
#             FROM c 
#             ORDER BY c.timestamp DESC
#         """
        
#         items = list(container.query_items(
#             query=query, 
#             enable_cross_partition_query=True, 
#             max_item_count=top_k
#         ))
        
#         seen = {}
#         results = []
        
#         for it in items:
#             tid = it.get("thread_id")
#             if not tid or tid in seen:
#                 continue
                
#             seen[tid] = True
#             content = it.get("content") or ""
            
#             results.append({
#                 "thread_id": tid,
#                 "preview": (content[:200] + " ...") if len(content) > 200 else content,
#                 "timestamp": it.get("timestamp")
#             })
            
#             if len(results) >= limit:
#                 break
        
#         return results
        
#     except Exception as e:
#         print(f"⚠️  Failed to list threads: {e}")
#         return []


# def read_message(item_id: str, partition_key: str):
#     """Read single message - returns None if unavailable."""
#     try:
#         _, container = _get_db_and_container()
        
#         try:
#             return container.read_item(item=item_id, partition_key=partition_key)
#         except exceptions.CosmosResourceNotFoundError:
#             return None
            
#     except Exception as e:
#         print(f"⚠️  Failed to read message: {e}")
#         return None


# def delete_thread(thread_id: str):
#     """Delete thread - fails gracefully."""
#     try:
#         _, container = _get_db_and_container()

#         query = "SELECT c.id, c.thread_id FROM c WHERE c.thread_id = @thread_id"
#         params = [{"name": "@thread_id", "value": thread_id}]
        
#         items = list(container.query_items(
#             query=query,
#             parameters=params,
#             enable_cross_partition_query=False
#         ))

#         deleted_count = 0
#         for item in items:
#             try:
#                 container.delete_item(
#                     item=item["id"],
#                     partition_key=item["thread_id"]
#                 )
#                 deleted_count += 1
#             except Exception as e:
#                 print(f"⚠️  Failed to delete {item['id']}: {e}")

#         print(f"🗑️  Deleted {deleted_count} messages from thread: {thread_id}")
#         return True
        
#     except Exception as e:
#         print(f"⚠️  Failed to delete thread: {e}")
#         # Don't crash - in-memory storage will be cleared
#         return False


# # ===================================================================
# # UTILITIES
# # ===================================================================

# def health_check():
#     """Check Cosmos DB health."""
#     try:
#         _, container = _get_db_and_container()
        
#         query = "SELECT TOP 1 c.id FROM c"
#         list(container.query_items(query=query, enable_cross_partition_query=True))
        
#         return {
#             "status": "healthy",
#             "database": COSMOS_DATABASE,
#             "container": COSMOS_CONTAINER,
#             "endpoint": COSMOS_ENDPOINT
#         }
        
#     except Exception as e:
#         return {
#             "status": "unhealthy",
#             "error": str(e),
#             "database": COSMOS_DATABASE,
#             "container": COSMOS_CONTAINER,
#             "endpoint": COSMOS_ENDPOINT
#         }


# def reset_connection():
#     """Reset connection."""
#     global _client, _db, _container, _initialization_error
    
#     if _client:
#         try:
#             _client.close()
#         except:
#             pass
    
#     _client = None
#     _db = None
#     _container = None
#     _initialization_error = None
    
#     print("🔄 Cosmos DB connection reset")


# def is_available():
#     """Check if Cosmos DB is currently available."""
#     global _initialization_error
#     return _initialization_error is None and _db is not None

# cosmos_store.py
from azure.cosmos import CosmosClient, PartitionKey, exceptions
from dotenv import load_dotenv
import os
from datetime import datetime
import uuid

load_dotenv()

COSMOS_ENDPOINT = os.getenv("COSMOS_ENDPOINT")
COSMOS_KEY = os.getenv("COSMOS_KEY")
COSMOS_DATABASE = os.getenv("COSMOS_DATABASE", "svayamams")
COSMOS_CONTAINER = os.getenv("COSMOS_CONTAINER", "chat-conversations")

if not COSMOS_ENDPOINT or not COSMOS_KEY:
    raise RuntimeError("COSMOS_ENDPOINT or COSMOS_KEY is not set in environment/.env")

# Cosmos client
client = CosmosClient(COSMOS_ENDPOINT, COSMOS_KEY)

# =====================================================
#  Get DB + container (partition key = /project_name)
# =====================================================
def _get_db_and_container():
    db = client.create_database_if_not_exists(id=COSMOS_DATABASE)
    container = db.create_container_if_not_exists(
        id=COSMOS_CONTAINER,
        partition_key=PartitionKey(path="/project_name"),   # << IMPORTANT
        offer_throughput=400
    )
    return db, container


# =====================================================
#  Append message
# =====================================================
def append_message(project_name: str, thread_id: str, role: str, content: str, metadata: dict = None):
    _, container = _get_db_and_container()

    msg = {
        "id": str(uuid.uuid4()),
        "project_name": project_name,      # << partition key
        "thread_id": thread_id,
        "role": role,
        "content": content,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "metadata": metadata or {},
    }

    return container.create_item(body=msg)


# =====================================================
#  Load messages for a thread (partition-safe)
# =====================================================
def load_messages(project_name: str, thread_id: str, max_items: int = 1000):
    _, container = _get_db_and_container()

    query = """
        SELECT c.id, c.thread_id, c.role, c.content, c.timestamp
        FROM c
        WHERE c.project_name = @project_name AND c.thread_id = @thread_id
        ORDER BY c.timestamp ASC
    """

    params = [
        {"name": "@project_name", "value": project_name},
        {"name": "@thread_id", "value": thread_id},
    ]

    return list(container.query_items(
        query=query,
        parameters=params,
        enable_cross_partition_query=False,   # works because project_name is the partition
        max_item_count=max_items
    ))


# =====================================================
#  List threads with preview (same project only)
# =====================================================
def list_threads_with_preview(project_name: str, limit: int = 100):
    _, container = _get_db_and_container()

    top_k = max(limit * 5, 200)

    query = f"""
        SELECT TOP {top_k} c.thread_id, c.content, c.timestamp
        FROM c
        WHERE c.project_name = @project_name
        ORDER BY c.timestamp DESC
    """

    params = [{"name": "@project_name", "value": project_name}]

    items = list(container.query_items(
        query=query,
        parameters=params,
        enable_cross_partition_query=False
    ))

    seen = set()
    results = []

    for it in items:
        tid = it.get("thread_id")
        if not tid or tid in seen:
            continue
        seen.add(tid)

        preview = (it.get("content") or "")
        if len(preview) > 200:
            preview = preview[:200] + " ..."

        results.append({
            "thread_id": tid,
            "preview": preview,
            "timestamp": it.get("timestamp")
        })

        if len(results) >= limit:
            break

    return results


# =====================================================
#  Read single message (debug)
# =====================================================
def read_message(project_name: str, item_id: str):
    _, container = _get_db_and_container()
    try:
        return container.read_item(
            item=item_id,
            partition_key=project_name
        )
    except exceptions.CosmosResourceNotFoundError:
        return None


# =====================================================
#  Delete all messages for a thread (partition-safe)
# =====================================================
def delete_thread(project_name: str, thread_id: str):
    _, container = _get_db_and_container()

    query = """
        SELECT c.id
        FROM c
        WHERE c.project_name = @project_name AND c.thread_id = @thread_id
    """

    params = [
        {"name": "@project_name", "value": project_name},
        {"name": "@thread_id", "value": thread_id},
    ]

    items = list(container.query_items(
        query=query,
        parameters=params,
        enable_cross_partition_query=False
    ))

    deleted = 0
    for doc in items:
        try:
            container.delete_item(
                item=doc["id"],
                partition_key=project_name
            )
            deleted += 1
        except Exception as e:
            print(f"Error deleting {doc['id']}: {e}")

    print(f"🗑️ Deleted {deleted} messages from thread {thread_id} in project {project_name}")
    return True


# =====================================================
#  Cosmos connectivity test
# =====================================================
_cosmos_available = None

def is_available() -> bool:
    global _cosmos_available

    if _cosmos_available is True:
        return True

    try:
        client.get_database_client(COSMOS_DATABASE).read()
        _cosmos_available = True
        return True
    except Exception:
        _cosmos_available = False
        return False
