import os
from azure.storage.blob import ContainerClient
from dotenv import load_dotenv

# Load the .env file
load_dotenv()

# Get connection string and container name from .env
CONN_STR = os.environ.get("AZURE_STORAGE_CONN_STR")
STORAGE_CONTAINER = "svayamams" # As seen in your screenshot

if not CONN_STR:
    raise ValueError("AZURE_STORAGE_CONN_STR is not set in your .env file")

# Create a single, reusable client
try:
    container_client = ContainerClient.from_connection_string(
        CONN_STR, 
        container_name=STORAGE_CONTAINER
    )
    # Test the connection by getting container properties
    container_client.get_container_properties()
    print(f"✅ Successfully connected to blob container: {STORAGE_CONTAINER}")
except Exception as e:
    print(f"❌ FAILED to connect to blob container: {STORAGE_CONTAINER}")
    print(e)
    container_client = None