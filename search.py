# # api/search.py

# import os
# import time
# from fastapi import APIRouter, HTTPException, BackgroundTasks
# from azure.core.credentials import AzureKeyCredential
# from azure.search.documents.indexes import SearchIndexerClient
# from dotenv import load_dotenv

# # --- Load Environment Variables ---
# load_dotenv()
# SEARCH_SERVICE = os.getenv("SEARCH_SERVICE")
# SEARCH_API_KEY = os.getenv("SEARCH_KEY")
# INDEXER_NAME = "svayam-ams-sewa-indexer" # From your notebook
# POLL_INTERVAL = 10  # seconds

# # --- Check for configuration ---
# if not SEARCH_SERVICE or not SEARCH_API_KEY:
#     print("Warning: SEARCH_SERVICE or SEARCH_KEY environment variables not set.")
    
# router = APIRouter(
#     prefix="/api/search",
#     tags=["Search"]
# )

# def trigger_indexer_logic():
#     """
#     This is the long-running function from your notebook.
#     It will run in the background.
#     """
#     if not SEARCH_SERVICE or not SEARCH_API_KEY:
#         print("Indexer trigger failed: Search credentials not configured on server.")
#         return

#     print(f"--- BACKGROUND TASK STARTED: Triggering Indexer '{INDEXER_NAME}' ---")
#     try:
#         client = SearchIndexerClient(endpoint=SEARCH_SERVICE, credential=AzureKeyCredential(SEARCH_API_KEY))

#         # Step 1: Reset the indexer (forces full re-index)
#         print(f"  Resetting indexer '{INDEXER_NAME}' ...")
#         client.reset_indexer(INDEXER_NAME)
#         print("  Indexer reset — forcing full re-index.")

#         # Step 2: Start the indexer
#         print(f"  Starting indexer '{INDEXER_NAME}' ...")
#         client.run_indexer(INDEXER_NAME)
#         print("  Indexer is now running...")

#         # Step 3: Poll until completion
#         while True:
#             status = client.get_indexer_status(INDEXER_NAME)
#             last_result = status.last_result

#             if last_result:
#                 state = last_result.status
#                 print(f"  Current status: {state}")

#                 if state in ["success", "transientFailure", "persistentFailure"]:
#                     print(f"\n--- BACKGROUND TASK FINISHED: Indexer '{INDEXER_NAME}' completed with status: {state} ---")
#                     if last_result.error_message:
#                         print(f"  Error details: {last_result.error_message}")
#                     break
#             else:
#                 print("  Waiting for status update...")

#             time.sleep(POLL_INTERVAL)
#     except Exception as e:
#         print(f"\n--- BACKGROUND TASK FAILED: An exception occurred ---")
#         print(e)

# @router.post("/run-indexer", status_code=202)
# async def run_indexer(background_tasks: BackgroundTasks):
#     """
#     API endpoint to trigger the indexer.
#     It responds IMMEDIATELY and runs the actual task in the background.
#     """
#     print("Received request to run indexer...")
#     background_tasks.add_task(trigger_indexer_logic)
    
#     return {"message": "Indexer run has been successfully triggered. The process will run in the background."}

# api/search.py
import os
import time
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexerClient
from dotenv import load_dotenv

# --- Load Environment Variables ---
load_dotenv()
SEARCH_SERVICE = os.getenv("SEARCH_SERVICE")
SEARCH_API_KEY = os.getenv("SEARCH_KEY")
# Removed global INDEXER_NAME constant
POLL_INTERVAL = 10  # seconds

# --- Check for configuration ---
if not SEARCH_SERVICE or not SEARCH_API_KEY:
    print("Warning: SEARCH_SERVICE or SEARCH_KEY environment variables not set.")
    
router = APIRouter(
    prefix="/api/search",
    tags=["Search"]
)

def trigger_indexer_logic(project_name: str = None):
    """
    Runs the indexer in the background.
    If project_name is provided, constructs the indexer name dynamically.
    Otherwise defaults to the legacy 'sewa' indexer.
    """
    if not SEARCH_SERVICE or not SEARCH_API_KEY:
        print("Indexer trigger failed: Search credentials not configured on server.")
        return

    # --- DYNAMIC INDEXER NAME ---
    if project_name:
        # Ensure sanitized format matches creation logic (lowercase, dashes)
        clean_name = project_name.strip().replace(" ", "-").lower()
        indexer_name = f"svayam-ams-{clean_name}-indexer"
    else:
        indexer_name = "svayam-ams-sewa-indexer" # Fallback default
    # ----------------------------

    print(f"--- BACKGROUND TASK STARTED: Triggering Indexer '{indexer_name}' ---")
    try:
        client = SearchIndexerClient(endpoint=SEARCH_SERVICE, credential=AzureKeyCredential(SEARCH_API_KEY))

        # Step 1: Reset the indexer (forces full re-index)
        print(f"  Resetting indexer '{indexer_name}' ...")
        client.reset_indexer(indexer_name)
        print("  Indexer reset — forcing full re-index.")

        # Step 2: Start the indexer
        print(f"  Starting indexer '{indexer_name}' ...")
        client.run_indexer(indexer_name)
        print("  Indexer is now running...")

        # Step 3: Poll until completion
        while True:
            status = client.get_indexer_status(indexer_name)
            last_result = status.last_result

            if last_result:
                state = last_result.status
                print(f"  Current status: {state}")

                if state in ["success", "transientFailure", "persistentFailure"]:
                    print(f"\n--- BACKGROUND TASK FINISHED: Indexer '{indexer_name}' completed with status: {state} ---")
                    if last_result.error_message:
                        print(f"  Error details: {last_result.error_message}")
                    break
            else:
                print("  Waiting for status update...")

            time.sleep(POLL_INTERVAL)
            
    except Exception as e:
        print(f"\n--- BACKGROUND TASK FAILED: An exception occurred ---")
        print(e)

@router.post("/run-indexer", status_code=202)
async def run_indexer(
    background_tasks: BackgroundTasks, 
    project_name: str = Query(None) # <--- Accepts project name from URL
):
    """
    API endpoint to trigger the indexer.
    It responds IMMEDIATELY and runs the actual task in the background.
    Passes project_name to the background task.
    """
    target_desc = project_name if project_name else "default (sewa)"
    print(f"Received request to run indexer for: {target_desc}...")
    
    # Pass the argument to the background function
    background_tasks.add_task(trigger_indexer_logic, project_name)
    
    return {"message": f"Indexer run triggered for {target_desc}. Process running in background."}
