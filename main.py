# # main.py
# # At the top of main.py, after imports
# import logging
# import traceback
# import time
# # Enable detailed logging
# logging.basicConfig(level=logging.DEBUG)
# logger = logging.getLogger(__name__)

# from fastapi import FastAPI, HTTPException, Depends, Header, Body, APIRouter
# from fastapi.middleware.cors import CORSMiddleware
# from database import SessionLocal, User, Conversation, Message, RefreshToken, init_db
# from jose import jwt, JWTError
# from datetime import datetime, timedelta
# import secrets
# import random
# import string
# import uuid

# # Chatbot imports (from folder: chatbot/)
# from chatbot.langgraph_database_backend import chatbot
# from chatbot.cosmos_store import append_message, load_messages, list_threads_with_preview
# from langchain_core.messages import HumanMessage, SystemMessage

# # ----------------------------------------------------------------------
# # FASTAPI APP
# # ----------------------------------------------------------------------

# app = FastAPI()

# # Enable CORS for frontend
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=[
#         "http://localhost:3000",
#         "http://127.0.0.1:3000",
#         "https://wonderful-grass-043c527003.azurestaticapps.net",
#     ],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*", "Authorization"],
#     expose_headers=["Authorization"],
# )

# init_db()

# # ----------------------------------------------------------------------
# # CONFIG
# # ----------------------------------------------------------------------

# SECRET_KEY = "change_this_to_a_strong_random_secret"
# ALGORITHM = "HS256"
# ACCESS_TOKEN_EXPIRE_MINUTES = 60
# REFRESH_TOKEN_EXPIRE_DAYS = 30


# # ----------------------------------------------------------------------
# # HELPERS
# # ----------------------------------------------------------------------

# def generate_password(length=10):
#     chars = string.ascii_letters + string.digits + "!@#$%^&*"
#     return ''.join(random.choice(chars) for _ in range(length))


# def create_access_token(data: dict, expires_delta: timedelta | None = None):
#     to_encode = data.copy()
#     expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
#     to_encode.update({"exp": expire})
#     encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
#     return encoded_jwt


# def create_refresh_token():
#     return secrets.token_urlsafe(32)


# def get_user_by_id(user_id: int):
#     """Helper to get user data (returns dict, not ORM object)"""
#     db = SessionLocal()
#     user = db.query(User).filter(User.id == user_id).first()
    
#     if not user:
#         db.close()
#         return None
    
   
#     user_data = {
#         "id": user.id,
#         "email": user.email,
#         "name": user.name,
#         "role": user.role
#     }
#     db.close()
#     return user_data

# # ----------------------------------------------------------------------
# # JWT AUTH MIDDLEWARE
# # ----------------------------------------------------------------------

# def get_current_user(authorization: str = Header(None)):
#     if not authorization:
#         raise HTTPException(401, "Missing Authorization header")

#     if not authorization.startswith("Bearer "):
#         raise HTTPException(401, "Invalid auth format")

#     token = authorization.replace("Bearer ", "").strip()

#     try:
#         payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
#         user_id = payload.get("sub")

#         if not user_id:
#             raise HTTPException(401, "Invalid token payload")

#         db = SessionLocal()
#         user = db.query(User).filter(User.id == user_id).first()
#         db.close()

#         if not user:
#             raise HTTPException(401, "User not found")

#         return int(user_id)

#     except JWTError:
#         raise HTTPException(401, "Invalid or expired token")


# # ----------------------------------------------------------------------
# # AUTH ROUTES
# # ----------------------------------------------------------------------

# @app.post("/login")
# def login(data: dict):
#     email = data.get("email")
#     password = data.get("password")

#     db = SessionLocal()
#     user = db.query(User).filter(User.email == email).first()

#     if not user or user.password != password:
#         db.close()
#         raise HTTPException(401, "Invalid credentials")

#     # 👇 EXTRACT USER DATA BEFORE CLOSING SESSION (FIX)
#     user_id = user.id
#     user_email = user.email
#     user_name = user.name
#     user_role = user.role

#     access_token = create_access_token({"sub": str(user_id), "email": user_email})
#     refresh_token_value = create_refresh_token()

#     rt = RefreshToken(
#         user_id=user_id,
#         token=refresh_token_value,
#         expires_at=datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
#     )
#     db.add(rt)
#     db.commit()
#     db.close()

#     # 👇 NOW USE THE EXTRACTED VARIABLES (FIX)
#     return {
#         "access_token": access_token,
#         "refresh_token": refresh_token_value,
#         "user": {
#             "email": user_email,
#             "name": user_name,
#             "role": user_role
#         }
#     }

# @app.post("/refresh")
# def refresh_token(data: dict):
#     refresh_token_value = data.get("refresh_token")
#     if not refresh_token_value:
#         raise HTTPException(400, "refresh_token required")

#     db = SessionLocal()
#     rt = db.query(RefreshToken).filter(RefreshToken.token == refresh_token_value).first()

#     if not rt:
#         db.close()
#         raise HTTPException(401, "Invalid refresh token")

#     if rt.expires_at < datetime.utcnow():
#         db.delete(rt)
#         db.commit()
#         db.close()
#         raise HTTPException(401, "Refresh token expired")

#     user = db.query(User).filter(User.id == rt.user_id).first()
    
#     # 👇 EXTRACT USER DATA BEFORE CLOSING SESSION (FIX)
#     user_id = user.id
#     user_email = user.email
    
#     access_token = create_access_token({"sub": str(user_id), "email": user_email})
#     db.close()

#     return {"access_token": access_token}


# @app.post("/logout")
# def logout(user_id: int = Depends(get_current_user)):
#     db = SessionLocal()
#     db.query(RefreshToken).filter(RefreshToken.user_id == user_id).delete()
#     db.commit()
#     db.close()
#     return {"message": "Logged out"}


# # ----------------------------------------------------------------------
# # ADMIN ROUTES
# # ----------------------------------------------------------------------

# @app.get("/admin/users")
# def list_users(user_id: int = Depends(get_current_user)):
#     db = SessionLocal()
#     admin = db.query(User).filter(User.id == user_id).first()

#     if not admin or admin.role != "admin":
#         db.close()
#         raise HTTPException(403, "Only admins can view users")

#     users = db.query(User).all()
#     db.close()

#     return {"users": [
#         {"id": u.id, "email": u.email, "name": u.name, "role": u.role}
#         for u in users
#     ]}


# @app.post("/admin/create")
# def create_user(data: dict, user_id: int = Depends(get_current_user)):
#     db = SessionLocal()
#     admin = db.query(User).filter(User.id == user_id).first()

#     if not admin or admin.role != "admin":
#         db.close()
#         raise HTTPException(403, "Only admins can create users")

#     email = data.get("email")
#     name = data.get("name")
#     role = data.get("role", "user")

#     if db.query(User).filter(User.email == email).first():
#         db.close()
#         raise HTTPException(400, "User already exists")

#     password = generate_password()
#     user = User(email=email, name=name, password=password, role=role)

#     db.add(user)
#     db.commit()
#     db.close()

#     return {"message": "User created", "generated_password": password}


# @app.put("/admin/users/{email}")
# def update_user(email: str, data: dict, user_id: int = Depends(get_current_user)):
#     db = SessionLocal()
#     admin = db.query(User).filter(User.id == user_id).first()

#     if not admin or admin.role != "admin":
#         db.close()
#         raise HTTPException(403, "Only admins can update users")

#     user = db.query(User).filter(User.email == email).first()
#     if not user:
#         db.close()
#         raise HTTPException(404, "User not found")

#     if "name" in data:
#         user.name = data["name"]
#     if "role" in data:
#         user.role = data["role"]
#     if "password" in data:
#         user.password = data["password"]

#     db.commit()
#     db.close()

#     return {"message": "User updated"}


# @app.delete("/admin/users/{email}")
# def delete_user(email: str, user_id: int = Depends(get_current_user)):
#     db = SessionLocal()
#     admin = db.query(User).filter(User.id == user_id).first()

#     if not admin or admin.role != "admin":
#         db.close()
#         raise HTTPException(403, "Only admins can delete users")

#     user = db.query(User).filter(User.email == email).first()
#     if not user:
#         db.close()
#         raise HTTPException(404, "User not found")

#     db.delete(user)
#     db.commit()
#     db.close()

#     return {"message": "User deleted"}


# # ----------------------------------------------------------------------
# # CONVERSATIONS (Updated to use LangGraph + Cosmos)
# # ----------------------------------------------------------------------

# @app.get("/conversations")
# def get_conversations(user_id: int = Depends(get_current_user)):
#     """Get all conversations for current user"""
#     db = SessionLocal()
    
#     # Get from SQL database (for conversation metadata)
#     convos = db.query(Conversation).filter(
#         Conversation.user_id == user_id
#     ).order_by(Conversation.created_at.desc()).all()
    
#     db.close()

#     return [
#         {
#             "conversation_uuid": c.conversation_uuid,
#             "topic": c.topic,
#             "created_at": c.created_at.isoformat(),
#             "is_resolved": False,
#         }
#         for c in convos
#     ]


# @app.post("/conversations/start")
# def start_conversation(user_id: int = Depends(get_current_user)):
#     """Create a new conversation thread"""
#     db = SessionLocal()
    
#     # Create conversation in SQL database
#     convo = Conversation(
#         conversation_uuid=str(uuid.uuid4()),
#         user_id=user_id,
#         topic="New Chat"
#     )
#     db.add(convo)
#     db.commit()
#     db.refresh(convo)

#     data = {
#         "conversation_uuid": convo.conversation_uuid,
#         "topic": convo.topic,
#         "created_at": convo.created_at.isoformat(),
#         "is_resolved": False,
#     }

#     db.close()
#     return data


# @app.get("/conversations/{conversation_uuid}")
# def get_conversation(conversation_uuid: str, user_id: int = Depends(get_current_user)):
#     """Get conversation details"""
#     db = SessionLocal()
    
#     convo = db.query(Conversation).filter(
#         Conversation.conversation_uuid == conversation_uuid,
#         Conversation.user_id == user_id
#     ).first()
    
#     if not convo:
#         db.close()
#         raise HTTPException(404, "Conversation not found")
    
#     # Get message count from Cosmos
#     try:
#         cosmos_messages = load_messages(conversation_uuid)
#         message_count = len(cosmos_messages)
#     except:
#         message_count = 0
    
#     db.close()
    
#     return {
#         "conversation_uuid": convo.conversation_uuid,
#         "topic": convo.topic,
#         "created_at": convo.created_at.isoformat(),
#         "is_resolved": False,
#         "message_count": message_count
#     }


# @app.get("/conversations/{conversation_uuid}/messages")
# def get_messages(conversation_uuid: str, user_id: int = Depends(get_current_user)):
#     """Get all messages from Cosmos DB"""
#     db = SessionLocal()
    
#     # Verify user owns this conversation
#     convo = db.query(Conversation).filter(
#         Conversation.conversation_uuid == conversation_uuid,
#         Conversation.user_id == user_id
#     ).first()
    
#     if not convo:
#         db.close()
#         raise HTTPException(404, "Conversation not found")
    
#     db.close()
    
#     # Load messages from Cosmos DB
#     try:
#         cosmos_messages = load_messages(conversation_uuid)
        
#         result = [
#             {
#                 "role": m.get("role", "assistant"),
#                 "content": m.get("content", ""),
#                 "timestamp": m.get("timestamp", datetime.utcnow().isoformat())
#             }
#             for m in cosmos_messages
#         ]
        
#         return result
        
#     except Exception as e:
#         raise HTTPException(500, f"Failed to load messages: {str(e)}")


# @app.post("/conversations/{conversation_uuid}/messages")
# def add_message(
#     conversation_uuid: str, 
#     payload: dict = Body(...), 
#     user_id: int = Depends(get_current_user)
# ):
#     start_time = time.time()
#     print(f"\n🕐 [{time.strftime('%H:%M:%S')}] Request received")
#     print(f"💬 Message: {payload.get('text')}")
    
#     # ... save user message ...
    
#     print(f"🕑 [{time.strftime('%H:%M:%S')}] Calling LangGraph...")

#     """Send message and get AI response using LangGraph"""
    
#     # Debug logging
#     logger.info(f"🔍 POST /conversations/{conversation_uuid}/messages")
#     logger.info(f"🔍 User ID: {user_id}")
#     logger.info(f"🔍 Payload: {payload}")
    
#     text = payload.get("text")

#     if not text:
#         raise HTTPException(400, "Message text is required")

#     db = SessionLocal()

#     try:
#         # Verify user owns this conversation
#         convo = db.query(Conversation).filter(
#             Conversation.conversation_uuid == conversation_uuid,
#             Conversation.user_id == user_id
#         ).first()

#         if not convo:
#             logger.error(f"❌ Conversation not found: {conversation_uuid}")
#             db.close()
#             raise HTTPException(404, "Conversation not found")
        
#         logger.info(f"✅ Conversation found: {convo.topic}")
        
#         # Extract convo data before using it later
#         convo_topic = convo.topic
        
#         user = get_user_by_id(user_id)
#         logger.info(f"✅ User data: {user}")

#         # Save user message to Cosmos DB
#         logger.info("📤 Saving user message to Cosmos...")
#         append_message(conversation_uuid, "user", text)
#         logger.info("✅ User message saved to Cosmos")
#         print(f"✅ User message saved to Cosmos DB")
#         print(f"   Thread ID: {conversation_uuid}")
#         print(f"   Role: user")
#         print(f"   Content: {text}")
        

#         # Prepare messages for LangGraph
#         logger.info("🤖 Preparing LangGraph messages...")
#         sys_msg = SystemMessage(content=f"thread_id:{conversation_uuid}")
#         user_msg = HumanMessage(content=text)
#         messages = [sys_msg, user_msg]

#         # Configure LangGraph
#         config = {
#             "configurable": {"thread_id": conversation_uuid},
#             "metadata": {
#                 "thread_id": conversation_uuid,
#                 "user_id": user_id,
#                 "user_email": user["email"] if user else "unknown"
#             },
#             "run_name": "conversation_turn",
#         }

#         logger.info("🤖 Calling LangGraph chatbot.stream()...")
#         # Stream response from LangGraph
#         collected_response = ""
#         for message_chunk, metadata in chatbot.stream(
#             {'messages': messages},
#             config=config,
#             stream_mode='messages'
#         ):
#             chunk_text = getattr(message_chunk, "content", str(message_chunk))
#             if chunk_text:
#                 collected_response += chunk_text

#         print(f"🕒 [{time.strftime('%H:%M:%S')}] LangGraph responded")

#             # ... save response ...
    
#         end_time = time.time()
#         duration = end_time - start_time
    
#         print(f"🕓 [{time.strftime('%H:%M:%S')}] Total time: {duration:.2f} seconds")
#         print(f"{'='*60}\n")

#         logger.info(f"✅ LangGraph response: {collected_response[:100]}...")

#         # Save assistant response to Cosmos DB
#         logger.info("📤 Saving assistant response to Cosmos...")
#         append_message(conversation_uuid, "assistant", collected_response)
#         logger.info("✅ Assistant response saved to Cosmos")

#         # Update conversation topic if it's the first message
#         if convo_topic == "New Chat":
#             new_topic = text[:50] + ("..." if len(text) > 50 else "")
#             convo.topic = new_topic
#             db.commit()
#             logger.info(f"✅ Updated conversation topic: {new_topic}")

#         db.close()

#         return {
#             "role": "assistant",
#             "content": collected_response,
#             "timestamp": datetime.utcnow().isoformat()
#         }

#     except Exception as e:
#         logger.error(f" ERROR in add_message: {str(e)}")
#         logger.error(traceback.format_exc())
#         db.close()
#         raise HTTPException(500, f"Failed to process message: {str(e)}")

# # ----------------------------------------------------------------------
# # DIRECT CHAT ENDPOINT (No conversation tracking)
# # ----------------------------------------------------------------------

# @app.post("/chat")
# def chat_endpoint(query: dict, user_id: int = Depends(get_current_user)):
#     """Direct chat without conversation tracking"""
#     user_message = query.get("message")
    
#     if not user_message:
#         raise HTTPException(400, "Message is required")

#     try:
#         # Generate temporary thread ID
#         temp_thread_id = str(uuid.uuid4())
        
#         # Prepare messages for LangGraph
#         sys_msg = SystemMessage(content=f"thread_id:{temp_thread_id}")
#         user_msg = HumanMessage(content=user_message)
#         messages = [sys_msg, user_msg]
        
#         # Save to Cosmos (optional - for logging)
#         append_message(temp_thread_id, "user", user_message)
        
#         # Configure LangGraph
#         user = get_user_by_id(user_id)
#         config = {
#             "configurable": {"thread_id": temp_thread_id},
#             "metadata": {
#                 "thread_id": temp_thread_id,
#                 "user_id": user_id,
#                 "user_email": user.email if user else "unknown",
#                 "mode": "direct_chat"
#             },
#             "run_name": "direct_chat",
#         }
        
#         # Get response from LangGraph
#         collected_response = ""
#         for message_chunk, metadata in chatbot.stream(
#             {'messages': messages},
#             config=config,
#             stream_mode='messages'
#         ):
#             chunk_text = getattr(message_chunk, "content", str(message_chunk))
#             if chunk_text:
#                 collected_response += chunk_text
        
#         # Save response to Cosmos (optional - for logging)
#         append_message(temp_thread_id, "assistant", collected_response)

#         return {
#             "response": collected_response,
#             "conversation_uuid": temp_thread_id
#         }
        
#     except Exception as e:
#         raise HTTPException(500, f"Chat error: {str(e)}")

# #main.py
# import logging
# import traceback
# import time
# import secrets
# import random
# import string
# import uuid
# from datetime import datetime, timedelta

# # Enable detailed logging
# logging.basicConfig(level=logging.DEBUG)
# logger = logging.getLogger(__name__)

# from fastapi import FastAPI, HTTPException, Depends, Body
# from fastapi.middleware.cors import CORSMiddleware
# from sqlalchemy.orm import Session
# from jose import jwt, JWTError

# # Database imports
# from database import SessionLocal, User, Conversation, RefreshToken, init_db

# # Chatbot imports
# from chatbot.langgraph_database_backend import chatbot
# from chatbot.cosmos_store import append_message, load_messages
# from langchain_core.messages import HumanMessage, SystemMessage
# from sqlalchemy import func
# from database import Feedback

# # ----------------------------------------------------------------------
# # FASTAPI APP
# # ----------------------------------------------------------------------

# app = FastAPI()

# # Enable CORS
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=[
#         "http://localhost:3000",
#         "http://127.0.0.1:3000",
#         "https://wonderful-grass-043c527003.azurestaticapps.net",
#     ],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*", "Authorization"],
#     expose_headers=["Authorization"],
# )

# init_db()

# # ----------------------------------------------------------------------
# # CONFIG
# # ----------------------------------------------------------------------

# SECRET_KEY = "change_this_to_a_strong_random_secret"
# ALGORITHM = "HS256"
# ACCESS_TOKEN_EXPIRE_MINUTES = 60
# REFRESH_TOKEN_EXPIRE_DAYS = 30

# # ----------------------------------------------------------------------
# # DEPENDENCIES
# # ----------------------------------------------------------------------

# def get_db():
#     """Database session dependency"""
#     db = SessionLocal()
#     try:
#         yield db
#     finally:
#         db.close()


# def get_current_user(
#     authorization: str = Depends(lambda: None),
#     db: Session = Depends(get_db)
# ) -> User:
#     """
#     Extract and validate JWT token, return User ORM object.
#     Now properly integrated with FastAPI dependency injection.
#     """
#     # Get authorization from header manually if not provided
#     from fastapi import Header, Request
#     from starlette.requests import Request as StarletteRequest
    
#     # This is a workaround - ideally use Header() directly
#     if authorization is None:
#         raise HTTPException(401, "Missing Authorization header")
    
#     if not authorization.startswith("Bearer "):
#         raise HTTPException(401, "Invalid auth format")

#     token = authorization.replace("Bearer ", "").strip()

#     try:
#         payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
#         user_id = payload.get("sub")

#         if not user_id:
#             raise HTTPException(401, "Invalid token payload")

#         user = db.query(User).filter(User.id == int(user_id)).first()

#         if not user:
#             raise HTTPException(401, "User not found")

#         return user

#     except JWTError:
#         raise HTTPException(401, "Invalid or expired token")


# # Simpler version using Header directly
# from fastapi import Header

# def get_current_user_simple(
#     authorization: str = Header(None),
#     db: Session = Depends(get_db)
# ) -> User:
#     """Get current authenticated user"""
#     if not authorization:
#         raise HTTPException(401, "Missing Authorization header")

#     if not authorization.startswith("Bearer "):
#         raise HTTPException(401, "Invalid auth format")

#     token = authorization.replace("Bearer ", "").strip()

#     try:
#         payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
#         user_id = payload.get("sub")

#         if not user_id:
#             raise HTTPException(401, "Invalid token payload")

#         user = db.query(User).filter(User.id == int(user_id)).first()

#         if not user:
#             raise HTTPException(401, "User not found")

#         return user

#     except JWTError:
#         raise HTTPException(401, "Invalid or expired token")


# # Use this one as get_current_user
# get_current_user = get_current_user_simple


# def get_current_admin_user(
#     current_user: User = Depends(get_current_user)
# ) -> User:
#     """Ensure current user is admin"""
#     if current_user.role != "admin":
#         raise HTTPException(403, "Admin access required")
#     return current_user


# # ----------------------------------------------------------------------
# # HELPERS
# # ----------------------------------------------------------------------

# def generate_password(length=10):
#     chars = string.ascii_letters + string.digits + "!@#$%^&*"
#     return ''.join(random.choice(chars) for _ in range(length))


# def create_access_token(data: dict, expires_delta: timedelta = None):
#     to_encode = data.copy()
#     expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
#     to_encode.update({"exp": expire})
#     return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# def create_refresh_token():
#     return secrets.token_urlsafe(32)


# # ----------------------------------------------------------------------
# # AUTH ROUTES
# # ----------------------------------------------------------------------

# @app.post("/login")
# def login(data: dict, db: Session = Depends(get_db)):
#     email = data.get("email")
#     password = data.get("password")

#     user = db.query(User).filter(User.email == email).first()

#     if not user or user.password != password:
#         raise HTTPException(401, "Invalid credentials")

#     # Extract data while session is active
#     user_id = user.id
#     user_email = user.email
#     user_name = user.name
#     user_role = user.role

#     access_token = create_access_token({"sub": str(user_id), "email": user_email})
#     refresh_token_value = create_refresh_token()

#     rt = RefreshToken(
#         user_id=user_id,
#         token=refresh_token_value,
#         expires_at=datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
#     )
#     db.add(rt)
#     db.commit()

#     return {
#         "access_token": access_token,
#         "refresh_token": refresh_token_value,
#         "user": {
#             "email": user_email,
#             "name": user_name,
#             "role": user_role
#         }
#     }


# @app.post("/refresh")
# def refresh_token(data: dict, db: Session = Depends(get_db)):
#     refresh_token_value = data.get("refresh_token")
#     if not refresh_token_value:
#         raise HTTPException(400, "refresh_token required")

#     rt = db.query(RefreshToken).filter(RefreshToken.token == refresh_token_value).first()

#     if not rt:
#         raise HTTPException(401, "Invalid refresh token")

#     if rt.expires_at < datetime.utcnow():
#         db.delete(rt)
#         db.commit()
#         raise HTTPException(401, "Refresh token expired")

#     user = db.query(User).filter(User.id == rt.user_id).first()
    
#     # Extract while session active
#     user_id = user.id
#     user_email = user.email
    
#     access_token = create_access_token({"sub": str(user_id), "email": user_email})

#     return {"access_token": access_token}


# @app.post("/logout")
# def logout(
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     db.query(RefreshToken).filter(RefreshToken.user_id == current_user.id).delete()
#     db.commit()
#     return {"message": "Logged out"}


# # ----------------------------------------------------------------------
# # ADMIN ROUTES
# # ----------------------------------------------------------------------

# @app.get("/admin/users")
# def list_users(
#     admin: User = Depends(get_current_admin_user),
#     db: Session = Depends(get_db)
# ):
#     users = db.query(User).all()
#     return {"users": [
#         {"id": u.id, "email": u.email, "name": u.name, "role": u.role}
#         for u in users
#     ]}


# @app.post("/admin/create")
# def create_user(
#     data: dict,
#     admin: User = Depends(get_current_admin_user),
#     db: Session = Depends(get_db)
# ):
#     email = data.get("email")
#     name = data.get("name")
#     role = data.get("role", "user")

#     if db.query(User).filter(User.email == email).first():
#         raise HTTPException(400, "User already exists")

#     password = generate_password()
#     user = User(email=email, name=name, password=password, role=role)

#     db.add(user)
#     db.commit()

#     return {"message": "User created", "generated_password": password}


# @app.put("/admin/users/{email}")
# def update_user(
#     email: str,
#     data: dict,
#     admin: User = Depends(get_current_admin_user),
#     db: Session = Depends(get_db)
# ):
#     user = db.query(User).filter(User.email == email).first()
#     if not user:
#         raise HTTPException(404, "User not found")

#     if "name" in data:
#         user.name = data["name"]
#     if "role" in data:
#         user.role = data["role"]
#     if "password" in data:
#         user.password = data["password"]

#     db.commit()
#     return {"message": "User updated"}


# @app.delete("/admin/users/{email}")
# def delete_user(
#     email: str,
#     admin: User = Depends(get_current_admin_user),
#     db: Session = Depends(get_db)
# ):
#     user = db.query(User).filter(User.email == email).first()
#     if not user:
#         raise HTTPException(404, "User not found")

#     db.delete(user)
#     db.commit()
#     return {"message": "User deleted"}


# # ----------------------------------------------------------------------
# # CONVERSATIONS
# # ----------------------------------------------------------------------

# @app.get("/conversations")
# def get_conversations(
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """Get all conversations for current user"""
#     convos = db.query(Conversation).filter(
#         Conversation.user_id == current_user.id
#     ).order_by(Conversation.created_at.desc()).all()

#     return [
#         {
#             "conversation_uuid": c.conversation_uuid,
#             "topic": c.topic,
#             "created_at": c.created_at.isoformat(),
#             "is_resolved": False,
#         }
#         for c in convos
#     ]


# @app.post("/conversations/start")
# def start_conversation(
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """Create a new conversation thread"""
#     convo = Conversation(
#         conversation_uuid=str(uuid.uuid4()),
#         user_id=current_user.id,
#         topic="New Chat"
#     )
#     db.add(convo)
#     db.commit()
#     db.refresh(convo)

#     return {
#         "conversation_uuid": convo.conversation_uuid,
#         "topic": convo.topic,
#         "created_at": convo.created_at.isoformat(),
#         "is_resolved": False,
#     }


# @app.get("/conversations/{conversation_uuid}")
# def get_conversation(
#     conversation_uuid: str,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """Get conversation details"""
#     convo = db.query(Conversation).filter(
#         Conversation.conversation_uuid == conversation_uuid,
#         Conversation.user_id == current_user.id
#     ).first()
    
#     if not convo:
#         raise HTTPException(404, "Conversation not found")
    
#     # Get message count from Cosmos
#     try:
#         cosmos_messages = load_messages(conversation_uuid)
#         message_count = len(cosmos_messages)
#     except:
#         message_count = 0
    
#     return {
#         "conversation_uuid": convo.conversation_uuid,
#         "topic": convo.topic,
#         "created_at": convo.created_at.isoformat(),
#         "is_resolved": False,
#         "message_count": message_count
#     }


# @app.get("/conversations/{conversation_uuid}/messages")
# def get_messages(
#     conversation_uuid: str,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """Get all messages from Cosmos DB"""
#     # Verify user owns this conversation
#     convo = db.query(Conversation).filter(
#         Conversation.conversation_uuid == conversation_uuid,
#         Conversation.user_id == current_user.id
#     ).first()
    
#     if not convo:
#         raise HTTPException(404, "Conversation not found")
    
#     # Load messages from Cosmos DB
#     try:
#         cosmos_messages = load_messages(conversation_uuid)
        
#         return [
#             {
#                 "role": m.get("role", "assistant"),
#                 "content": m.get("content", ""),
#                 "timestamp": m.get("timestamp", datetime.utcnow().isoformat())
#             }
#             for m in cosmos_messages
#         ]
        
#     except Exception as e:
#         logger.error(f"Failed to load messages: {str(e)}")
#         raise HTTPException(500, f"Failed to load messages: {str(e)}")


# @app.post("/conversations/{conversation_uuid}/messages")
# def add_message(
#     conversation_uuid: str,
#     payload: dict = Body(...),
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     timings = {}
#     total_start = time.time()

#     # ---------------- Verify conversation ----------------
#     t = time.time()
#     convo = db.query(Conversation).filter(
#         Conversation.conversation_uuid == conversation_uuid,
#         Conversation.user_id == current_user.id
#     ).first()
#     timings["verify_conversation"] = time.time() - t

#     if not convo:
#         raise HTTPException(404, "Conversation not found")

#     # ---------------- Save user message ----------------
#     t = time.time()
#     # append_message(conversation_uuid, "user", payload["text"])
#     timings["save_user_msg"] = time.time() - t

#     # ---------------- Call LangGraph ----------------
#     t = time.time()
#     collected_response = ""
#     sys_msg = SystemMessage(content=f"thread_id:{conversation_uuid}")
#     user_msg = HumanMessage(content=payload["text"])

#     for chunk, meta in chatbot.stream(
#         {"messages": [sys_msg, user_msg]},
#         config={"configurable": {"thread_id": conversation_uuid}},
#         stream_mode="messages"
#     ):
#         txt = getattr(chunk, "content", "")
#         if txt:
#             collected_response += txt

#     timings["ai_processing"] = time.time() - t

#     # ---------------- Save AI message ----------------
#     t = time.time()
#     # append_message(conversation_uuid, "assistant", collected_response)
#     timings["save_ai_msg"] = time.time() - t

#     timings["total"] = time.time() - total_start

# #         # =====================================================================
# #     #              🔥 AUTO TITLE GENERATION (AFTER 2–5 MESSAGES)
# #     # =====================================================================
# #     try:
# #         cosmos_msgs = load_messages(conversation_uuid)
# #         msg_count = len(cosmos_msgs)

# # # Trigger only after 2 or 3 full turns (4 or 6 total messages)
# #         if convo.topic == "New Chat" and msg_count in (4, 6):
  

# #             logger.info(f"🔍 Generating AI title (msg_count={msg_count})...")

# #             # Prepare history text for summarization
# #             history_text = "\n".join([
# #                 f"{m.get('role')}: {m.get('content')}" for m in cosmos_msgs[:6]
# #             ])

# #             title_prompt = (
# #             "Summarize this conversation into a very short title.\n"
# #             "Rules:\n"
# #             "- Max 4 words\n"
# #             "- No punctuation\n"
# #             "- No special characters\n"
# #             "- Title MUST be short, like: 'SAP BTP Overview', 'Login Issue', 'API Errors', 'Sales Data Problem'\n"
# #             "- Never exceed 28 characters\n\n"
# #             f"Conversation so far:\n{history_text}"
# #         )

# #             title_sys = SystemMessage(content="You generate short conversation titles only.")
# #             title_user = HumanMessage(content=title_prompt)

# #             generated_title = ""

# #             for chunk, meta in chatbot.stream(
# #                 {"messages": [title_sys, title_user]},
# #                 config={"configurable": {"thread_id": f"title-{conversation_uuid}"}},
# #                 stream_mode="messages"
# #             ):
# #                 part = getattr(chunk, "content", "")
# #                 if part:
# #                     generated_title += part

# #             generated_title = generated_title.strip()

# #             # Keep it clean
# #             MAX_TITLE_LEN = 28
# #             if len(generated_title) > MAX_TITLE_LEN:
# #                 words = generated_title.split()
# #                 short = ""
# #                 for w in words:
# #                     if len(short + " " + w) <= MAX_TITLE_LEN:
# #                         short = (short + " " + w).strip()
# #                     else:
# #                         break
# #             generated_title = short


# #             # Save to DB
# #             convo.topic = generated_title
# #             db.commit()

# #             logger.info(f"✅ Title generated: {generated_title}")

# #     except Exception as e:
# #         logger.error(f"❌ Title generation failed: {e}")

# #     # =====================================================================

#     timings["total"] = time.time() - total_start


#     # ---------------- Print ONE summary ----------------
#     logger.info("\n=== AI TIMING REPORT ===")
#     for step, sec in timings.items():
#         logger.info(f"{step}: {sec:.3f}s")
#     logger.info("========================\n")

#     return {
#         "role": "assistant",
#         "content": collected_response,
#         "timestamp": datetime.utcnow().isoformat()
#     }

# # from chatbot.langgraph_database_backend import delete_langgraph_thread

# from chatbot.cosmos_store import delete_thread
# from fastapi import BackgroundTasks

# @app.delete("/conversations/{conversation_uuid}")
# def delete_conversation(conversation_uuid: str,
#                         background: BackgroundTasks,
#                         current_user: User = Depends(get_current_user),
#                         db: Session = Depends(get_db)):

#     # Step 1: Validate conversation
#     convo = db.query(Conversation).filter(
#         Conversation.conversation_uuid == conversation_uuid,
#         Conversation.user_id == current_user.id
#     ).first()

#     if not convo:
#         raise HTTPException(404, "Conversation not found")

#     # Step 2: Remove from SQL instantly
#     db.delete(convo)
#     db.commit()

#     # Step 3: Run slow deletes in background
#     background.add_task(delete_thread, conversation_uuid)

#     # Step 4: Send immediate success to frontend
#     return {"status": "success", "message": "Conversation deleted"}




# # ----------------------------------------------------------------------
# # DIRECT CHAT ENDPOINT
# # ----------------------------------------------------------------------

# @app.post("/chat")
# def chat_endpoint(
#     query: dict,
#     current_user: User = Depends(get_current_user)
# ):
#     """Direct chat without conversation tracking"""
#     user_message = query.get("message")
    
#     if not user_message:
#         raise HTTPException(400, "Message is required")

#     try:
#         # Generate temporary thread ID
#         temp_thread_id = str(uuid.uuid4())
        
#         # Prepare messages for LangGraph
#         sys_msg = SystemMessage(content=f"thread_id:{temp_thread_id}")
#         user_msg = HumanMessage(content=user_message)
#         messages = [sys_msg, user_msg]
        
#         # Save to Cosmos (for logging)
#         append_message(temp_thread_id, "user", user_message)
        
#         # Configure LangGraph
#         config = {
#             "configurable": {"thread_id": temp_thread_id},
#             "metadata": {
#                 "thread_id": temp_thread_id,
#                 "user_id": current_user.id,
#                 "user_email": current_user.email,
#                 "mode": "direct_chat"
#             },
#             "run_name": "direct_chat",
#         }
        
#         # Get response from LangGraph
#         collected_response = ""
#         for message_chunk, metadata in chatbot.stream(
#             {'messages': messages},
#             config=config,
#             stream_mode='messages'
#         ):
#             chunk_text = getattr(message_chunk, "content", str(message_chunk))
#             if chunk_text:
#                 collected_response += chunk_text
        
#         # Save response to Cosmos
#         append_message(temp_thread_id, "assistant", collected_response)

#         return {
#             "response": collected_response,
#             "conversation_uuid": temp_thread_id
#         }
        
#     except Exception as e:
#         logger.error(f"Chat error: {str(e)}")
#         raise HTTPException(500, f"Chat error: {str(e)}")
    






# @app.post("/conversations/{conversation_uuid}/feedback")
# def submit_feedback(
#     conversation_uuid: str,
#     payload: dict = Body(...),
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """Submit feedback for a conversation"""
#     try:
#         # Verify user owns this conversation
#         convo = db.query(Conversation).filter(
#             Conversation.conversation_uuid == conversation_uuid,
#             Conversation.user_id == current_user.id
#         ).first()
        
#         if not convo:
#             raise HTTPException(404, "Conversation not found")
        
#         # Check if feedback already exists
#         existing_feedback = db.query(Feedback).filter(
#             Feedback.conversation_uuid == conversation_uuid,
#             Feedback.user_id == current_user.id
#         ).first()
        
#         if existing_feedback:
#             raise HTTPException(400, "Feedback already submitted for this conversation")
        
#         # Create new feedback
#         feedback = Feedback(
#             conversation_uuid=conversation_uuid,
#             user_id=current_user.id,
#             rating=payload.get("rating"),
#             comment=payload.get("comment", ""),
#             message_count=payload.get("message_count", 0)
#         )
        
#         db.add(feedback)
#         db.commit()
#         db.refresh(feedback)
        
#         logger.info(f"✅ Feedback saved: {feedback.id} - Rating: {feedback.rating}/5")
        
#         return {
#             "success": True,
#             "message": "Feedback submitted successfully",
#             "feedback_id": feedback.id
#         }
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"❌ Failed to save feedback: {str(e)}")
#         raise HTTPException(500, f"Failed to save feedback: {str(e)}")


# @app.get("/conversations/{conversation_uuid}/feedback")
# def get_feedback(
#     conversation_uuid: str,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """Check if feedback exists for a conversation"""
#     try:
#         feedback = db.query(Feedback).filter(
#             Feedback.conversation_uuid == conversation_uuid,
#             Feedback.user_id == current_user.id
#         ).first()
        
#         if not feedback:
#             return {"exists": False}
        
#         return {
#             "exists": True,
#             "rating": feedback.rating,
#             "comment": feedback.comment,
#             "timestamp": feedback.timestamp.isoformat()
#         }
        
#     except Exception as e:
#         logger.error(f"❌ Failed to check feedback: {str(e)}")
#         raise HTTPException(500, f"Failed to check feedback: {str(e)}")


# @app.get("/admin/feedback/stats")
# def get_feedback_stats(
#     admin: User = Depends(get_current_admin_user),
#     db: Session = Depends(get_db)
# ):
#     """Get overall feedback statistics (Admin only)"""
#     try:
#         # Get all feedback
#         total = db.query(func.count(Feedback.id)).scalar() or 0
        
#         if total == 0:
#             return {
#                 "total": 0,
#                 "average": 0,
#                 "positive": 0,
#                 "negative": 0,
#                 "by_rating": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
#             }
        
#         # Calculate average
#         avg_rating = db.query(func.avg(Feedback.rating)).scalar()
        
#         # Count positive (4-5) and negative (1-2)
#         positive = db.query(func.count(Feedback.id)).filter(
#             Feedback.rating >= 4
#         ).scalar() or 0
        
#         negative = db.query(func.count(Feedback.id)).filter(
#             Feedback.rating <= 2
#         ).scalar() or 0
        
#         # Count by rating
#         by_rating = {}
#         for rating in range(1, 6):
#             count = db.query(func.count(Feedback.id)).filter(
#                 Feedback.rating == rating
#             ).scalar() or 0
#             by_rating[rating] = count
        
#         return {
#             "total": total,
#             "average": round(float(avg_rating), 2) if avg_rating else 0,
#             "positive": positive,
#             "negative": negative,
#             "by_rating": by_rating
#         }
        
#     except Exception as e:
#         logger.error(f"❌ Failed to get feedback stats: {str(e)}")
#         raise HTTPException(500, f"Failed to get feedback stats: {str(e)}")


# @app.get("/admin/feedback/list")
# def list_all_feedback(
#     admin: User = Depends(get_current_admin_user),
#     db: Session = Depends(get_db),
#     limit: int = 50,
#     offset: int = 0
# ):
#     """Get list of all feedback (Admin only)"""
#     try:
#         feedbacks = db.query(Feedback).order_by(
#             Feedback.timestamp.desc()
#         ).limit(limit).offset(offset).all()
        
#         result = []
#         for fb in feedbacks:
#             # Get conversation topic
#             convo = db.query(Conversation).filter(
#                 Conversation.conversation_uuid == fb.conversation_uuid
#             ).first()
            
#             # Get user email
#             user = db.query(User).filter(User.id == fb.user_id).first()
            
#             result.append({
#                 "id": fb.id,
#                 "conversation_uuid": fb.conversation_uuid,
#                 "conversation_topic": convo.topic if convo else "Unknown",
#                 "user_email": user.email if user else "Unknown",
#                 "rating": fb.rating,
#                 "comment": fb.comment or "",
#                 "message_count": fb.message_count,
#                 "timestamp": fb.timestamp.isoformat()
#             })
        
#         total_count = db.query(func.count(Feedback.id)).scalar() or 0
        
#         return {
#             "feedbacks": result,
#             "total": total_count
#         }
        
#     except Exception as e:
#         logger.error(f"❌ Failed to list feedback: {str(e)}")
#         raise HTTPException(500, f"Failed to list feedback: {str(e)}")


# from fastapi import UploadFile, File, Form
# import os

# UPLOAD_DIR = "uploaded_files"
# os.makedirs(UPLOAD_DIR, exist_ok=True)


# # --------------------------------------
# # 1️⃣ Upload Image (PNG/JPG)
# # --------------------------------------
# @app.post("/conversations/{conversation_uuid}/upload-image")
# async def upload_image(
#     conversation_uuid: str,
#     file: UploadFile = File(...),
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     # Validate conversation ownership
#     convo = db.query(Conversation).filter(
#         Conversation.conversation_uuid == conversation_uuid,
#         Conversation.user_id == current_user.id
#     ).first()

#     if not convo:
#         raise HTTPException(404, "Conversation not found")

#     # Save file locally
#     filepath = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}_{file.filename}")
#     with open(filepath, "wb") as f:
#         f.write(await file.read())

#     # Save message to Cosmos
#     append_message(conversation_uuid, "user", f"[IMAGE-UPLOADED] {filepath}")

#     return {
#         "success": True,
#         "filename": file.filename,
#         "stored_as": filepath
#     }



# # --------------------------------------
# # 2️⃣ Upload Document (PDF/DOC/TXT)
# # --------------------------------------
# @app.post("/conversations/{conversation_uuid}/upload-document")
# async def upload_document(
#     conversation_uuid: str,
#     file: UploadFile = File(...),
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     # Validate conversation ownership
#     convo = db.query(Conversation).filter(
#         Conversation.conversation_uuid == conversation_uuid,
#         Conversation.user_id == current_user.id
#     ).first()

#     if not convo:
#         raise HTTPException(404, "Conversation not found")

#     # Save file
#     filepath = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}_{file.filename}")
#     with open(filepath, "wb") as f:
#         f.write(await file.read())

#     # Save message to Cosmos
#     append_message(conversation_uuid, "user", f"[DOCUMENT-UPLOADED] {filepath}")

#     return {
#         "success": True,
#         "filename": file.filename,
#         "stored_as": filepath
#     }



# # --------------------------------------
# # 3️⃣ Send Text + Files Together (ChatGPT Style)
# # --------------------------------------
# @app.post("/conversations/{conversation_uuid}/messages-with-files")
# async def send_message_with_files(
#     conversation_uuid: str,
#     content: str = Form(...),
#     files: list[UploadFile] = File(default=[]),
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     # Validate ownership
#     convo = db.query(Conversation).filter(
#         Conversation.conversation_uuid == conversation_uuid,
#         Conversation.user_id == current_user.id
#     ).first()

#     if not convo:
#         raise HTTPException(404, "Conversation not found")

#     uploaded_files = []

#     # Save each file
#     for file in files:
#         filepath = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}_{file.filename}")
#         with open(filepath, "wb") as f:
#             f.write(await file.read())

#         uploaded_files.append(filepath)

#     # Store user message in Cosmos
#     append_message(
#         conversation_uuid,
#         "user",
#         f"[FILES]: {uploaded_files}\n\n{content}"
#     )

#     # Call LangGraph
#     collected_response = ""
#     sys_msg = SystemMessage(content=f"thread_id:{conversation_uuid}")
#     user_msg = HumanMessage(content=content)

#     for chunk, meta in chatbot.stream(
#         {"messages": [sys_msg, user_msg]},
#         config={"configurable": {"thread_id": conversation_uuid}},
#         stream_mode="messages"
#     ):
#         txt = getattr(chunk, "content", "")
#         if txt:
#             collected_response += txt

#     # Save AI reply
#     append_message(conversation_uuid, "assistant", collected_response)

#     return {
#         "role": "assistant",
#         "content": collected_response,
#         "uploaded_files": uploaded_files,
#         "timestamp": datetime.utcnow().isoformat()
#     }



# main.py - Fixed with Streamlit-style Hybrid Storage
# import logging
# import time
# import secrets
# import random
# import string
# import uuid
# import os
# import asyncio
# from datetime import datetime, timedelta
# from typing import Optional
# import atexit
# from threading import Lock

# logging.basicConfig(level=logging.DEBUG)
# logger = logging.getLogger(__name__)

# from fastapi import FastAPI, HTTPException, Depends, Body, Header, BackgroundTasks
# from fastapi.middleware.cors import CORSMiddleware
# from sqlalchemy.orm import Session
# from jose import jwt, JWTError
# from passlib.context import CryptContext

# # Database imports
# from database import SessionLocal, User, Conversation, RefreshToken, Feedback, init_db

# # Chatbot imports
# from chatbot.langgraph_database_backend import chatbot
# from chatbot.cosmos_store import append_message, load_messages, delete_thread, list_threads_with_preview
# from langchain_core.messages import HumanMessage, SystemMessage
# from sqlalchemy import func

# # Password hashing
# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# from langchain_openai import AzureChatOpenAI
# from langchain_core.messages import HumanMessage

# # Fast mini-model just for summarizing chat titles
# title_llm = AzureChatOpenAI(
#         azure_endpoint=os.getenv("AZURE_GPT4O_ENDPOINT"),
#         deployment_name=os.getenv("AZURE_GPT4O_DEPLOYMENT"),
#         openai_api_version=os.getenv("AZURE_GPT4O_API_VERSION"),
#         api_key=os.getenv("AZURE_GPT4O_API_KEY"),
#         temperature=0,
#         streaming=True
#     )

# async def generate_chat_title(messages):
#     """
#     Generate a 4–5 word conversation title from initial messages.
#     """
#     prompt = f"""
#     Create a VERY short 4–5 word title summarizing this conversation.
#     Messages:
#     {messages}

#     Only return the title. No quotes.
#     """

#     try:
#         result = title_llm.invoke([HumanMessage(content=prompt)])
#         title = result.content.strip()
#         # Safety: remove newlines / long titles
#         return title[:50]
#     except Exception as e:
#         logger.error(f"Title generation failed: {e}")
#         return "New Chat"


# # ----------------------------------------------------------------------
# # HYBRID STORAGE MANAGER (Based on Streamlit Logic)
# # ----------------------------------------------------------------------
# # Fixed HybridStorageManager with proper thread-safety
# import logging
# from threading import Lock
# from datetime import datetime
# from typing import List, Dict

# logger = logging.getLogger(__name__)

# class HybridStorageManager:
#     """
#     Thread-safe hybrid storage manager for chat messages.
    
#     Stores messages in-memory for fast access, with periodic flush to Cosmos DB.
#     """
    
#     def __init__(self):
#         self.memory: Dict[str, List[Dict]] = {}  # {thread_id: [{role, content}, ...]}
#         self.active_threads: Dict[str, datetime] = {}  # {thread_id: last_activity}
#         self.lock = Lock()  # Protects all shared state
#         logger.info("✅ HybridStorageManager initialized")

#     def add_message(self, thread_id: str, role: str, content: str):
#         """Add a message to in-memory storage (thread-safe)"""
#         with self.lock:
#             if thread_id not in self.memory:
#                 self.memory[thread_id] = []
#                 logger.debug(f"📝 Created new thread in memory: {thread_id}")

#             self.memory[thread_id].append({
#                 "role": role,
#                 "content": content,
#                 "timestamp": datetime.utcnow().isoformat()
#             })

#             self.active_threads[thread_id] = datetime.utcnow()
            
#             msg_count = len(self.memory[thread_id])
#             logger.debug(f"💬 Added {role} message to {thread_id} ({msg_count} total)")

#     def get_messages(self, thread_id: str) -> List[Dict]:
#         """Get messages from in-memory storage (thread-safe)"""
#         with self.lock:
#             return self.memory.get(thread_id, []).copy()  # Return copy to prevent external modifications

#     def clear_memory(self, thread_id: str):
#         """Clear a thread from in-memory storage (thread-safe)"""
#         with self.lock:
#             removed_msgs = len(self.memory.get(thread_id, []))
#             self.memory.pop(thread_id, None)
#             self.active_threads.pop(thread_id, None)
#             logger.info(f"🗑️  Cleared {thread_id} from memory ({removed_msgs} messages)")

#     def flush_to_cosmos(self, thread_id: str, clear_after: bool = False) -> int:
#         """
#         Flush in-memory messages to Cosmos DB (thread-safe)
        
#         Args:
#             thread_id: Thread to flush
#             clear_after: Whether to clear from memory after flushing
            
#         Returns:
#             Number of messages flushed
#         """
#         with self.lock:
#             if thread_id not in self.memory:
#                 logger.debug(f"⚠️  No messages to flush for {thread_id}")
#                 return 0

#             msgs = self.memory[thread_id].copy()

#         # Release lock before I/O operations
#         try:
#             # Get existing message count from Cosmos
#             try:
#                 from chatbot.cosmos_store import load_messages, append_message
#                 cosmos_msgs = load_messages(thread_id)
#                 existing_count = len(cosmos_msgs)
#                 logger.debug(f"📊 Cosmos has {existing_count} messages for {thread_id}")
#             except Exception as e:
#                 logger.warning(f"⚠️  Could not load from Cosmos: {e}")
#                 existing_count = 0

#             # Only append new messages
#             new_msgs = msgs[existing_count:]
            
#             if not new_msgs:
#                 logger.debug(f"✅ All messages already in Cosmos for {thread_id}")
#                 if clear_after:
#                     self.clear_memory(thread_id)
#                 return 0

#             # Append new messages to Cosmos
#             count = 0
#             for m in new_msgs:
#                 try:
#                     append_message(
#                         thread_id,
#                         m["role"],
#                         m["content"],
#                         metadata={"saved_from": "fastapi-memory", "timestamp": m.get("timestamp")}
#                     )
#                     count += 1
#                 except Exception as e:
#                     logger.error(f"❌ Failed to append message to Cosmos: {e}")
#                     # Continue with other messages

#             logger.info(f"💾 Flushed {count}/{len(new_msgs)} new messages to Cosmos for {thread_id}")

#             # Clear from memory if requested
#             if clear_after:
#                 self.clear_memory(thread_id)

#             return count

#         except Exception as e:
#             logger.error(f"❌ Error during flush_to_cosmos: {e}")
#             return 0

#     def load_from_cosmos(self, thread_id: str, force_reload: bool = False) -> int:
#         """
#         Load messages from Cosmos DB into memory (thread-safe)
        
#         Args:
#             thread_id: Thread to load
#             force_reload: If True, reload even if already in memory
            
#         Returns:
#             Number of messages loaded
#         """
#         with self.lock:
#             # Check if already loaded
#             if thread_id in self.memory and not force_reload:
#                 logger.debug(f"✅ Thread {thread_id} already in memory ({len(self.memory[thread_id])} messages)")
#                 return len(self.memory[thread_id])

#         # Release lock before I/O operation
#         try:
#             from chatbot.cosmos_store import load_messages
#             cosmos_msgs = load_messages(thread_id)
            
#             # Re-acquire lock to update memory
#             with self.lock:
#                 self.memory[thread_id] = [
#                     {
#                         "role": m["role"],
#                         "content": m["content"],
#                         "timestamp": m.get("timestamp", datetime.utcnow().isoformat())
#                     }
#                     for m in cosmos_msgs
#                 ]
                
#                 if cosmos_msgs:
#                     self.active_threads[thread_id] = datetime.utcnow()
                
#                 msg_count = len(cosmos_msgs)
#                 logger.info(f"📥 Loaded {msg_count} messages from Cosmos for {thread_id}")
#                 return msg_count

#         except Exception as e:
#             logger.error(f"❌ Error loading from Cosmos: {e}")
#             # Initialize empty thread on error
#             with self.lock:
#                 if thread_id not in self.memory:
#                     self.memory[thread_id] = []
#             return 0

#     def sync_all_active(self) -> int:
#         """Flush all active threads to Cosmos (thread-safe)"""
#         with self.lock:
#             thread_ids = list(self.active_threads.keys())
        
#         total = 0
#         for tid in thread_ids:
#             try:
#                 count = self.flush_to_cosmos(tid, clear_after=False)
#                 total += count
#             except Exception as e:
#                 logger.error(f"❌ Error syncing thread {tid}: {e}")
        
#         logger.info(f"🔄 Synced {total} messages across {len(thread_ids)} threads")
#         return total

#     def shutdown_flush(self):
#         """Emergency flush on shutdown"""
#         logger.info("🛑 SHUTDOWN: Flushing all active threads...")
#         try:
#             total = self.sync_all_active()
#             logger.info(f"✅ Shutdown complete: {total} messages saved")
#         except Exception as e:
#             logger.error(f"❌ Error during shutdown flush: {e}")

#     def get_stats(self) -> Dict:
#         """Get storage statistics (thread-safe)"""
#         with self.lock:
#             return {
#                 "active_threads": len(self.active_threads),
#                 "total_messages": sum(len(msgs) for msgs in self.memory.values()),
#                 "threads": list(self.active_threads.keys()),
#                 "thread_sizes": {
#                     tid: len(msgs) for tid, msgs in self.memory.items()
#                 }
#             }

# # Initialize storage manager
# storage_manager = HybridStorageManager()

# # Register shutdown handler
# atexit.register(storage_manager.shutdown_flush)

# # ----------------------------------------------------------------------
# # FASTAPI APP
# # ----------------------------------------------------------------------
# app = FastAPI()

# # CORS
# ALLOWED_ORIGINS = [
#     "http://localhost:3000",
#     "http://127.0.0.1:3000",
#     "https://wonderful-grass-043c527003.azurestaticapps.net"
# ]

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=ALLOWED_ORIGINS,
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# init_db()

# # ----------------------------------------------------------------------
# # CONFIG
# # ----------------------------------------------------------------------
# SECRET_KEY = os.getenv("SECRET_KEY", "change_this_to_a_strong_random_secret")
# ALGORITHM = "HS256"
# ACCESS_TOKEN_EXPIRE_MINUTES = 60
# REFRESH_TOKEN_EXPIRE_DAYS = 30

# # ----------------------------------------------------------------------
# # DEPENDENCIES
# # ----------------------------------------------------------------------
# def get_db():
#     db = SessionLocal()
#     try:
#         yield db
#     finally:
#         db.close()

# def get_current_user(
#     authorization: str = Header(None),
#     db: Session = Depends(get_db)
# ) -> User:
#     if not authorization:
#         raise HTTPException(401, "Missing Authorization header")
#     if not authorization.startswith("Bearer "):
#         raise HTTPException(401, "Invalid auth format")
    
#     token = authorization.replace("Bearer ", "").strip()
    
#     try:
#         payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
#         user_id = payload.get("sub")
#         if not user_id:
#             raise HTTPException(401, "Invalid token payload")
        
#         user = db.query(User).filter(User.id == int(user_id)).first()
#         if not user:
#             raise HTTPException(401, "User not found")
        
#         return user
#     except JWTError:
#         raise HTTPException(401, "Invalid or expired token")

# def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
#     if current_user.role != "admin":
#         raise HTTPException(403, "Admin access required")
#     return current_user

# # ----------------------------------------------------------------------
# # HELPERS
# # ----------------------------------------------------------------------
# def create_access_token(data: dict, expires_delta: timedelta = None):
#     to_encode = data.copy()
#     expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
#     to_encode.update({"exp": expire})
#     return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# def create_refresh_token():
#     return secrets.token_urlsafe(32)

# # ----------------------------------------------------------------------
# # AUTH ROUTES
# # ----------------------------------------------------------------------
# @app.post("/login")
# def login(data: dict, db: Session = Depends(get_db)):
#     email = data.get("email")
#     password = data.get("password")
    
#     user = db.query(User).filter(User.email == email).first()
#     if not user:
#         raise HTTPException(401, "Invalid credentials")
    
#     # TODO: Use pwd_context.verify() in production
#     if user.password != password:
#         raise HTTPException(401, "Invalid credentials")
    
#     access_token = create_access_token({"sub": str(user.id), "email": user.email})
#     refresh_token_value = create_refresh_token()
    
#     rt = RefreshToken(
#         user_id=user.id,
#         token=refresh_token_value,
#         expires_at=datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
#     )
#     db.add(rt)
#     db.commit()
    
#     return {
#         "access_token": access_token,
#         "refresh_token": refresh_token_value,
#         "user": {"email": user.email, "name": user.name, "role": user.role}
#     }

# @app.post("/logout")
# def logout(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
#     # Auto-save all active conversations on logout
#     storage_manager.sync_all_active()
    
#     db.query(RefreshToken).filter(RefreshToken.user_id == current_user.id).delete()
#     db.commit()
#     return {"message": "Logged out"}

# # ----------------------------------------------------------------------
# # CONVERSATION ROUTES (Streamlit-style)
# # ----------------------------------------------------------------------

# @app.get("/conversations")
# def get_conversations(
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """Get all conversations (from SQL + Cosmos previews)"""
#     convos = db.query(Conversation).filter(
#         Conversation.user_id == current_user.id
#     ).order_by(Conversation.created_at.desc()).all()
    
#     # Try to get previews from Cosmos
#     try:
#         cosmos_threads = list_threads_with_preview(limit=100)
#         preview_map = {t["thread_id"]: t["preview"] for t in cosmos_threads}
#     except:
#         preview_map = {}
    
#     return [
#         {
#             "conversation_uuid": c.conversation_uuid,
#             "topic": c.topic,
#             "preview": preview_map.get(c.conversation_uuid, ""),
#             "created_at": c.created_at.isoformat(),
#             "is_resolved": False,
#         }
#         for c in convos
#     ]

# @app.post("/conversations/start")
# def start_conversation(
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """
#     Start new conversation - AUTO-SAVES all active threads first
#     (Matches Streamlit: start_new_chat() → flush current → create new)
#     """
    
#     # 🔥 AUTO-SAVE: Flush all active threads before creating new one
#     storage_manager.sync_all_active()
#     logger.info("🆕 Starting new chat - flushed all active threads")
    
#     # Create new conversation
#     convo = Conversation(
#         conversation_uuid=str(uuid.uuid4()),
#         user_id=current_user.id,
#         topic="New Chat"
#     )
#     db.add(convo)
#     db.commit()
#     db.refresh(convo)
    
#     return {
#         "conversation_uuid": convo.conversation_uuid,
#         "topic": convo.topic,
#         "created_at": convo.created_at.isoformat(),
#         "is_resolved": False,
#     }

# @app.get("/conversations/{conversation_uuid}/messages")
# def get_messages(
#     conversation_uuid: str,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """
#     Get messages - AUTO-SAVES previous conversation, then loads this one
#     (Matches Streamlit: load_thread_from_cosmos_with_autosave)
#     """
#     # 1️⃣ Verify conversation ownership
#     convo = db.query(Conversation).filter(
#         Conversation.conversation_uuid == conversation_uuid,
#         Conversation.user_id == current_user.id
#     ).first()
    
#     if not convo:
#         raise HTTPException(404, "Conversation not found")
    
#     try:
#         # 2️⃣ AUTO-SAVE: Flush all OTHER active threads before loading this one
#         logger.info(f"🔄 Auto-saving other threads before loading {conversation_uuid}")
        
#         with storage_manager.lock:
#             other_threads = [
#                 tid for tid in storage_manager.active_threads.keys()
#                 if tid != conversation_uuid
#             ]
        
#         for thread_id in other_threads:
#             try:
#                 count = storage_manager.flush_to_cosmos(thread_id, clear_after=False)
#                 if count > 0:
#                     logger.info(f"💾 Auto-saved {count} messages from {thread_id}")
#             except Exception as e:
#                 logger.error(f"⚠️  Failed to auto-save {thread_id}: {e}")
#                 # Continue with other threads
        
#         # 3️⃣ Load this conversation from Cosmos if not in memory
#         logger.info(f"📥 Loading conversation {conversation_uuid}")
#         storage_manager.load_from_cosmos(conversation_uuid, force_reload=False)
        
#         # 4️⃣ Get messages from memory
#         messages = storage_manager.get_messages(conversation_uuid)
        
#         logger.info(f"✅ Retrieved {len(messages)} messages for {conversation_uuid}")
        
#         return [
#             {
#                 "role": m["role"],
#                 "content": m["content"],
#                 "timestamp": m.get("timestamp", datetime.utcnow().isoformat())
#             }
#             for m in messages
#         ]
        
#     except HTTPException:
#         raise  # Re-raise HTTP exceptions
#     except Exception as e:
#         logger.error(f"❌ Error in get_messages: {e}", exc_info=True)
#         raise HTTPException(
#             status_code=500,
#             detail=f"Failed to load messages: {str(e)}"
#         )
# import time

# # main.py - Enhanced timing instrumentation

# from contextlib import contextmanager

# # Timing context manager
# @contextmanager
# def timer(name: str, timings: dict):
#     """Context manager to track timing for code blocks"""
#     start = time.time()
#     yield
#     timings[name] = time.time() - start


# @app.post("/conversations/{conversation_uuid}/messages")
# def add_message(
#     conversation_uuid: str,
#     payload: dict = Body(...),
#     background: BackgroundTasks = None,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     timings = {}
#     total_start = time.time()
    
#     # -----------------------------------
#     # 1️⃣ Verify conversation
#     # -----------------------------------
#     with timer("verify_conversation", timings):
#         convo = db.query(Conversation).filter(
#             Conversation.conversation_uuid == conversation_uuid,
#             Conversation.user_id == current_user.id
#         ).first()
    
#     if not convo:
#         raise HTTPException(404, "Conversation not found")
    
#     user_text = payload.get("text", "")
    
#     # -----------------------------------
#     # 2️⃣ Save user message to InMemory
#     # -----------------------------------
#     with timer("memory_save_user", timings):
#         storage_manager.add_message(conversation_uuid, "user", user_text)
    
#     # -----------------------------------
#     # 3️⃣ Prepare messages for LangGraph
#     # -----------------------------------
#     with timer("prepare_messages", timings):
#         sys_msg = SystemMessage(content=f"thread_id:{conversation_uuid}")
#         user_msg = HumanMessage(content=user_text)
    
#     # -----------------------------------
#     # 4️⃣ LangGraph / OpenAI call - DETAILED BREAKDOWN
#     # -----------------------------------
#     collected_response = ""
#     chunk_count = 0
#     first_token_time = None
#     streaming_start = time.time()
    
#     # Track individual chunk timings
#     chunk_timings = []
#     last_chunk_time = streaming_start
    
#     logger.info(f"🚀 Starting LangGraph stream for: {conversation_uuid}")
    
#     for chunk, meta in chatbot.stream(
#         {"messages": [sys_msg, user_msg]},
#         config={"configurable": {"thread_id": conversation_uuid}},
#         stream_mode="messages"
#     ):
#         txt = getattr(chunk, "content", "")
#         if txt:
#             current_time = time.time()
            
#             # Track time to first token
#             if first_token_time is None:
#                 first_token_time = current_time - streaming_start
#                 logger.info(f"⏱️  Time to first token: {first_token_time:.3f}s")
            
#             # Track inter-chunk delays
#             chunk_delay = current_time - last_chunk_time
#             chunk_timings.append(chunk_delay)
#             last_chunk_time = current_time
            
#             collected_response += txt
#             chunk_count += 1
            
#             # Log every 5 chunks
#             if chunk_count % 5 == 0:
#                 logger.info(f"📝 Received {chunk_count} chunks, {len(collected_response)} chars so far")
    
#     streaming_end = time.time()
#     timings["langgraph_total"] = streaming_end - streaming_start
#     timings["time_to_first_token"] = first_token_time or 0
#     timings["streaming_duration"] = streaming_end - streaming_start - (first_token_time or 0)
    
#     # Calculate streaming stats
#     if chunk_timings:
#         timings["avg_chunk_delay"] = sum(chunk_timings) / len(chunk_timings)
#         timings["max_chunk_delay"] = max(chunk_timings)
#         timings["min_chunk_delay"] = min(chunk_timings)
    
#     logger.info(f"✅ LangGraph complete: {chunk_count} chunks, {len(collected_response)} chars")
    
#     # -----------------------------------
#     # 5️⃣ Save AI message to memory
#     # -----------------------------------
#     with timer("memory_save_ai", timings):
#         storage_manager.add_message(conversation_uuid, "assistant", collected_response)
    
#     # Resolution check
#     show_resolved = "Is your issue resolved?" in collected_response
    
#     timings["total_time"] = time.time() - total_start
    
#     # Summarize AFTER sending response (zero added time for user)
#     try:
#         if convo.topic == "New Chat":
#             msgs = storage_manager.get_messages(conversation_uuid)

#         # Only generate title after 4 messages (user+AI twice)
#         if len(msgs) >= 4:
#             text_msgs = [
#                 f"{m['role']}: {m['content']}"
#                 for m in msgs[:4]
#             ]

#             # Now safe to call
#             title = asyncio.run(generate_chat_title(text_msgs))

#             convo.topic = title
#             db.commit()

#             logger.info(f"📝 Updated chat title: {title}")
#     except Exception as e:
#         logger.error(f"❌ Title generation failed: {e}")

#     # -----------------------------------
#     # 🟩 ENHANCED TIMING REPORT
#     # -----------------------------------
#     logger.info("\n" + "="*60)
#     logger.info("⏱️  DETAILED TIMING REPORT (Chat Message)")
#     logger.info("="*60)
    
#     # Calculate percentages
#     total = timings["total_time"]
    
#     logger.info(f"{'Step':<30} {'Time (s)':<12} {'% of Total':<12}")
#     logger.info("-"*60)
    
#     for step in ["verify_conversation", "memory_save_user", "prepare_messages", 
#                  "langgraph_total", "memory_save_ai", "total_time"]:
#         if step in timings:
#             duration = timings[step]
#             percentage = (duration / total * 100) if total > 0 else 0
#             logger.info(f"{step:<30} {duration:>8.3f}s    {percentage:>6.1f}%")
    
#     logger.info("-"*60)
#     logger.info("\n📊 LangGraph Breakdown:")
#     logger.info(f"  Time to first token:    {timings.get('time_to_first_token', 0):.3f}s")
#     logger.info(f"  Streaming duration:     {timings.get('streaming_duration', 0):.3f}s")
#     logger.info(f"  Total chunks received:  {chunk_count}")
#     logger.info(f"  Total characters:       {len(collected_response)}")
    
#     if chunk_timings:
#         logger.info(f"  Avg chunk delay:        {timings.get('avg_chunk_delay', 0):.4f}s")
#         logger.info(f"  Max chunk delay:        {timings.get('max_chunk_delay', 0):.4f}s")
#         logger.info(f"  Min chunk delay:        {timings.get('min_chunk_delay', 0):.4f}s")
    
#     logger.info("="*60 + "\n")
    
#     return {
#         "role": "assistant",
#         "content": collected_response,
#         "topic": convo.topic,  
#         "timestamp": datetime.utcnow().isoformat(),
#         "show_resolved": show_resolved,
#         "debug_timing": timings if os.getenv("DEBUG_TIMING") == "true" else None
#     }

# @app.post("/conversations/{conversation_uuid}/flush")
# def manual_flush(
#     conversation_uuid: str,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """
#     Manual flush endpoint - called by frontend when switching conversations
#     (Matches Streamlit: flush_thread_to_cosmos)
#     """
#     convo = db.query(Conversation).filter(
#         Conversation.conversation_uuid == conversation_uuid,
#         Conversation.user_id == current_user.id
#     ).first()
    
#     if not convo:
#         raise HTTPException(404, "Conversation not found")
    
#     count = storage_manager.flush_to_cosmos(conversation_uuid, clear_after=False)
    
#     return {
#         "success": True,
#         "messages_flushed": count,
#         "message": f"Flushed {count} messages to Cosmos DB"
#     }

# @app.post("/conversations/{conversation_uuid}/resolve")
# def mark_resolved(
#     conversation_uuid: str,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """
#     Mark conversation as resolved - flushes to Cosmos
#     (Matches Streamlit: mark_resolved_and_start_new)
#     """
#     convo = db.query(Conversation).filter(
#         Conversation.conversation_uuid == conversation_uuid,
#         Conversation.user_id == current_user.id
#     ).first()
    
#     if not convo:
#         raise HTTPException(404, "Conversation not found")
    
#     # Flush to Cosmos
#     count = storage_manager.flush_to_cosmos(conversation_uuid, clear_after=True)
    
#     logger.info(f"✅ Resolved: {conversation_uuid} | {count} messages saved")
    
#     return {
#         "success": True,
#         "message": "Conversation marked as resolved and saved",
#         "messages_saved": count
#     }

# @app.delete("/conversations/{conversation_uuid}")
# def delete_conversation(
#     conversation_uuid: str,
#     background: BackgroundTasks,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """Delete conversation - flushes before deletion"""
    
#     convo = db.query(Conversation).filter(
#         Conversation.conversation_uuid == conversation_uuid,
#         Conversation.user_id == current_user.id
#     ).first()
    
#     if not convo:
#         raise HTTPException(404, "Conversation not found")
    
#     # Flush any pending messages
#     storage_manager.flush_to_cosmos(conversation_uuid, clear_after=False)
    
#     # Clear from InMemory
#     storage_manager.clear_memory(conversation_uuid)
    
#     # Delete from SQL
#     db.delete(convo)
#     db.commit()
    
#     # Delete from Cosmos in background
#     background.add_task(delete_thread, conversation_uuid)
    
#     return {"status": "success", "message": "Conversation deleted"}

# # ----------------------------------------------------------------------
# # FEEDBACK
# # ----------------------------------------------------------------------
# @app.post("/conversations/{conversation_uuid}/feedback")
# def submit_feedback(
#     conversation_uuid: str,
#     payload: dict = Body(...),
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """Submit feedback - auto-saves conversation first"""
    
#     convo = db.query(Conversation).filter(
#         Conversation.conversation_uuid == conversation_uuid,
#         Conversation.user_id == current_user.id
#     ).first()
    
#     if not convo:
#         raise HTTPException(404, "Conversation not found")
    
#     # 🔥 AUTO-SAVE: Flush conversation before accepting feedback
#     storage_manager.flush_to_cosmos(conversation_uuid, clear_after=True)
    
#     existing_feedback = db.query(Feedback).filter(
#         Feedback.conversation_uuid == conversation_uuid,
#         Feedback.user_id == current_user.id
#     ).first()
    
#     if existing_feedback:
#         raise HTTPException(400, "Feedback already submitted")
    
#     feedback = Feedback(
#         conversation_uuid=conversation_uuid,
#         user_id=current_user.id,
#         rating=payload.get("rating"),
#         comment=payload.get("comment", ""),
#         message_count=payload.get("message_count", 0)
#     )
    
#     db.add(feedback)
#     db.commit()
#     db.refresh(feedback)
    
#     logger.info(f"✅ Feedback: {feedback.id} - Rating: {feedback.rating}/5")
    
#     return {
#         "success": True,
#         "message": "Feedback submitted and conversation saved",
#         "feedback_id": feedback.id
#     }

# # ----------------------------------------------------------------------
# # HEALTH & MONITORING
# # ----------------------------------------------------------------------
# @app.get("/health")
# def health_check():
#     return {
#         "status": "healthy",
#         "active_threads": len(storage_manager.active_threads),
#         "threads": list(storage_manager.active_threads.keys()),
#         "timestamp": datetime.utcnow().isoformat()
#     }

# @app.get("/admin/storage/stats")
# def get_storage_stats(admin: User = Depends(get_current_admin_user)):
#     """Admin: View storage statistics"""
#     return {
#         "active_threads": len(storage_manager.active_threads),
#         "threads": list(storage_manager.active_threads.keys()),
#         "thread_activity": {
#             tid: activity.isoformat()
#             for tid, activity in storage_manager.active_threads.items()
#         }
#     }

# @app.post("/admin/sync-all")
# def admin_sync_all(admin: User = Depends(get_current_admin_user)):
#     """Admin: Force sync all active threads"""
#     count = storage_manager.sync_all_active()
#     return {
#         "success": True,
#         "threads_synced": count,
#         "message": f"Synced {count} active threads to Cosmos DB"
#     }


#main.py
# import logging
# import time
# import secrets
# import uuid
# import os
# import asyncio
# from datetime import datetime, timedelta
# from typing import Optional, List, Dict
# import atexit
# from threading import Lock, Thread
# from queue import Queue
# from collections import deque
# from contextlib import contextmanager

# logging.basicConfig(level=logging.DEBUG)
# logger = logging.getLogger(__name__)

# from fastapi import FastAPI, HTTPException, Depends, Body, Header, BackgroundTasks
# from fastapi.middleware.cors import CORSMiddleware
# from sqlalchemy.orm import Session
# from jose import jwt, JWTError
# from passlib.context import CryptContext

# # Database imports
# from database_model import SessionLocal, User, Conversation, RefreshToken, Feedback, init_db, Project, UserProject

# # Chatbot imports
# from chatbot.langgraph_database_backend import chatbot
# from chatbot.cosmos_store import append_message, load_messages, delete_thread, list_threads_with_preview
# from langchain_core.messages import HumanMessage, SystemMessage
# from sqlalchemy import func

# # Password hashing
# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# from langchain_openai import AzureChatOpenAI

# # Fast mini-model just for summarizing chat titles
# title_llm = AzureChatOpenAI(
#     azure_endpoint=os.getenv("AZURE_GPT4O_ENDPOINT"),
#     deployment_name=os.getenv("AZURE_GPT4O_DEPLOYMENT"),
#     openai_api_version=os.getenv("AZURE_GPT4O_API_VERSION"),
#     api_key=os.getenv("AZURE_GPT4O_API_KEY"),
#     temperature=0,
#     streaming=True
# )

# async def generate_chat_title(messages):
#     """Generate a 4–5 word conversation title from initial messages."""
#     prompt = f"""
#     Create a VERY short 4–5 word title summarizing this conversation.
#     Messages:
#     {messages}

#     Only return the title. No quotes.
#     """

#     try:
#         result = title_llm.invoke([HumanMessage(content=prompt)])
#         title = result.content.strip()
#         return title[:50]
#     except Exception as e:
#         logger.error(f"Title generation failed: {e}")
#         return "New Chat"


# # ======================================================================
# # 🚀 OPTIMIZED HYBRID STORAGE MANAGER (WITH TIMING LOGS)
# # ======================================================================
# class OptimizedHybridStorageManager:
#     """
#     High-performance hybrid storage with:
#     - Background async flushing
#     - Batch operations
#     - Smart caching
#     - Non-blocking operations
#     - Detailed timing logs
#     """
    
#     def __init__(self):
#         self.memory: Dict[str, List[Dict]] = {}
#         self.active_threads: Dict[str, datetime] = {}
#         self.dirty_threads: set = set()  # Tracks threads needing flush
#         self.lock = Lock()
        
#         # Background flush queue
#         self.flush_queue: Queue = Queue()
#         self.flush_worker_running = True
#         self.flush_thread = Thread(target=self._background_flush_worker, daemon=True)
#         self.flush_thread.start()
        
#         # Cache for Cosmos-loaded threads
#         self.cosmos_loaded: set = set()
        
#         logger.info("✅ OptimizedHybridStorageManager initialized")

#     def add_message(self, thread_id: str, role: str, content: str):
#         """Add message to memory - INSTANT (no I/O)"""
#         start = time.time()
        
#         with self.lock:
#             if thread_id not in self.memory:
#                 self.memory[thread_id] = []

#             self.memory[thread_id].append({
#                 "role": role,
#                 "content": content,
#                 "timestamp": datetime.utcnow().isoformat()
#             })

#             self.active_threads[thread_id] = datetime.utcnow()
#             self.dirty_threads.add(thread_id)
        
#         duration = (time.time() - start) * 1000  # ms
#         logger.debug(f"⏱️  Memory add_message: {duration:.1f}ms")

#     def get_messages(self, thread_id: str) -> List[Dict]:
#         """Get messages - INSTANT (from memory)"""
#         start = time.time()
        
#         with self.lock:
#             result = self.memory.get(thread_id, []).copy()
        
#         duration = (time.time() - start) * 1000  # ms
#         logger.debug(f"⏱️  Memory get_messages: {duration:.1f}ms ({len(result)} messages)")
        
#         return result

#     def queue_flush(self, thread_id: str, priority: bool = False):
#         """
#         Queue thread for background flush - NON-BLOCKING
        
#         Args:
#             thread_id: Thread to flush
#             priority: If True, flush immediately in foreground
#         """
#         if priority:
#             # Synchronous flush for critical operations (logout, delete)
#             self._do_flush(thread_id)
#         else:
#             # Background flush - returns instantly
#             self.flush_queue.put(thread_id)
#             logger.debug(f"📤 Queued {thread_id} for background flush")

#     def _background_flush_worker(self):
#         """Background thread that processes flush queue"""
#         logger.info("🔄 Background flush worker started")
        
#         while self.flush_worker_running:
#             try:
#                 # Process batch of flushes
#                 batch = []
                
#                 # Collect up to 5 threads or wait 1s
#                 timeout = 1.0
#                 try:
#                     thread_id = self.flush_queue.get(timeout=timeout)
#                     batch.append(thread_id)
                    
#                     # Grab more from queue (non-blocking)
#                     while len(batch) < 5:
#                         try:
#                             thread_id = self.flush_queue.get_nowait()
#                             batch.append(thread_id)
#                         except:
#                             break
                            
#                 except:
#                     continue
                
#                 # Process batch
#                 batch_start = time.time()
#                 total_flushed = 0
                
#                 for thread_id in batch:
#                     try:
#                         count = self._do_flush(thread_id)
#                         total_flushed += count
#                     except Exception as e:
#                         logger.error(f"❌ Background flush failed for {thread_id}: {e}")
                
#                 if total_flushed > 0:
#                     logger.info(f"💾 Background batch flush: {total_flushed} msgs in {(time.time() - batch_start):.3f}s")
                        
#             except Exception as e:
#                 logger.error(f"❌ Flush worker error: {e}")

#     def _do_flush(self, thread_id: str) -> int:
#         """Actually flush a thread to Cosmos DB"""
#         flush_start = time.time()
        
#         with self.lock:
#             if thread_id not in self.memory or thread_id not in self.dirty_threads:
#                 return 0
            
#             msgs = self.memory[thread_id].copy()

#         try:
#             # Get existing count from Cosmos
#             load_start = time.time()
#             try:
#                 cosmos_msgs = load_messages(thread_id)
#                 existing_count = len(cosmos_msgs)
#                 logger.info(f"⏱️  Cosmos load_messages: {(time.time() - load_start):.3f}s")
#             except:
#                 existing_count = 0

#             # Only append NEW messages
#             new_msgs = msgs[existing_count:]
            
#             if not new_msgs:
#                 with self.lock:
#                     self.dirty_threads.discard(thread_id)
#                 return 0

#             # Batch append to Cosmos
#             append_start = time.time()
#             count = 0
#             for m in new_msgs:
#                 try:
#                     msg_start = time.time()
#                     append_message(
#                         thread_id,
#                         m["role"],
#                         m["content"],
#                         metadata={"timestamp": m.get("timestamp")}
#                     )
#                     count += 1
#                     logger.debug(f"⏱️  Cosmos append_message: {(time.time() - msg_start):.3f}s")
#                 except Exception as e:
#                     logger.error(f"❌ Append failed: {e}")

#             total_append_time = time.time() - append_start
#             logger.info(f"⏱️  Total Cosmos append ({count} msgs): {total_append_time:.3f}s (avg: {total_append_time/count if count > 0 else 0:.3f}s/msg)")

#             # Mark as clean
#             with self.lock:
#                 self.dirty_threads.discard(thread_id)

#             total_flush_time = time.time() - flush_start
#             logger.info(f"💾 Flush complete for {thread_id}: {count} messages in {total_flush_time:.3f}s")

#             return count

#         except Exception as e:
#             logger.error(f"❌ Flush error: {e}")
#             return 0

#     def load_from_cosmos(self, thread_id: str, force_reload: bool = False) -> int:
#         """
#         Load from Cosmos - WITH CACHING (only loads once unless forced)
#         """
#         load_start = time.time()
        
#         with self.lock:
#             # Check cache first
#             if thread_id in self.cosmos_loaded and not force_reload:
#                 if thread_id in self.memory:
#                     logger.debug(f"⚡ Cache hit for {thread_id}")
#                     return len(self.memory[thread_id])

#         try:
#             cosmos_start = time.time()
#             cosmos_msgs = load_messages(thread_id)
#             logger.info(f"⏱️  Cosmos load_messages: {(time.time() - cosmos_start):.3f}s ({len(cosmos_msgs)} messages)")
            
#             with self.lock:
#                 self.memory[thread_id] = [
#                     {
#                         "role": m["role"],
#                         "content": m["content"],
#                         "timestamp": m.get("timestamp", datetime.utcnow().isoformat())
#                     }
#                     for m in cosmos_msgs
#                 ]
                
#                 if cosmos_msgs:
#                     self.active_threads[thread_id] = datetime.utcnow()
#                     self.cosmos_loaded.add(thread_id)  # Mark as cached
                
#                 total_load_time = time.time() - load_start
#                 logger.info(f"📥 Loaded {len(cosmos_msgs)} messages in {total_load_time:.3f}s")
                
#                 return len(cosmos_msgs)

#         except Exception as e:
#             logger.error(f"❌ Load error: {e}")
#             with self.lock:
#                 if thread_id not in self.memory:
#                     self.memory[thread_id] = []
#             return 0

#     def sync_dirty_threads(self) -> int:
#         """Synchronously flush only DIRTY threads (for critical operations)"""
#         sync_start = time.time()
        
#         with self.lock:
#             dirty = list(self.dirty_threads)
        
#         logger.info(f"🔄 Syncing {len(dirty)} dirty threads...")
        
#         total = 0
#         for tid in dirty:
#             count = self._do_flush(tid)
#             total += count
        
#         logger.info(f"⏱️  Total sync time: {(time.time() - sync_start):.3f}s ({total} messages)")
        
#         return total

#     def shutdown_flush(self):
#         """Emergency shutdown - flush all dirty threads"""
#         logger.info("🛑 SHUTDOWN: Flushing dirty threads...")
        
#         self.flush_worker_running = False
        
#         try:
#             total = self.sync_dirty_threads()
#             logger.info(f"✅ Shutdown complete: {total} messages saved")
#         except Exception as e:
#             logger.error(f"❌ Shutdown error: {e}")

#     def clear_memory(self, thread_id: str):
#         """Clear thread from memory"""
#         with self.lock:
#             self.memory.pop(thread_id, None)
#             self.active_threads.pop(thread_id, None)
#             self.dirty_threads.discard(thread_id)
#             self.cosmos_loaded.discard(thread_id)

#     def get_stats(self) -> Dict:
#         """Get statistics"""
#         with self.lock:
#             return {
#                 "active_threads": len(self.active_threads),
#                 "dirty_threads": len(self.dirty_threads),
#                 "cached_threads": len(self.cosmos_loaded),
#                 "total_messages": sum(len(msgs) for msgs in self.memory.values()),
#             }

# # Initialize optimized storage manager
# storage_manager = OptimizedHybridStorageManager()

# # Register shutdown handler
# atexit.register(storage_manager.shutdown_flush)

# # ======================================================================
# # FASTAPI APP
# # ======================================================================
# app = FastAPI()

# # CORS
# ALLOWED_ORIGINS = [
#     "http://localhost:3000",
#     "http://127.0.0.1:3000",
#     "https://wonderful-grass-043c527003.azurestaticapps.net"
# ]

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=ALLOWED_ORIGINS,
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# init_db()

# # Config
# SECRET_KEY = os.getenv("SECRET_KEY", "change_this_to_a_strong_random_secret")
# ALGORITHM = "HS256"
# ACCESS_TOKEN_EXPIRE_MINUTES = 60
# REFRESH_TOKEN_EXPIRE_DAYS = 30

# # ======================================================================
# # DEPENDENCIES
# # ======================================================================
# def get_db():
#     db = SessionLocal()
#     try:
#         yield db
#     finally:
#         db.close()

# def get_current_user(
#     authorization: str = Header(None),
#     db: Session = Depends(get_db)
# ) -> User:
#     if not authorization:
#         raise HTTPException(401, "Missing Authorization header")
#     if not authorization.startswith("Bearer "):
#         raise HTTPException(401, "Invalid auth format")
    
#     token = authorization.replace("Bearer ", "").strip()
    
#     try:
#         payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
#         user_id = payload.get("sub")
#         if not user_id:
#             raise HTTPException(401, "Invalid token payload")
        
#         user = db.query(User).filter(User.id == int(user_id)).first()
#         if not user:
#             raise HTTPException(401, "User not found")
        
#         return user
#     except JWTError:
#         raise HTTPException(401, "Invalid or expired token")

# def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
#     if current_user.role != "admin":
#         raise HTTPException(403, "Admin access required")
#     return current_user

# # ======================================================================
# # HELPERS
# # ======================================================================
# def create_access_token(data: dict, expires_delta: timedelta = None):
#     to_encode = data.copy()
#     expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
#     to_encode.update({"exp": expire})
#     return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# def create_refresh_token():
#     return secrets.token_urlsafe(32)

# # ======================================================================
# # AUTH ROUTES
# # ======================================================================
# @app.post("/login")
# def login(data: dict, db: Session = Depends(get_db)):
#     email = data.get("email")
#     password = data.get("password")
    
#     user = db.query(User).filter(User.email == email).first()
#     if not user or user.password != password:
#         raise HTTPException(401, "Invalid credentials")
    
#     access_token = create_access_token({"sub": str(user.id), "email": user.email})
#     refresh_token_value = create_refresh_token()
    
#     rt = RefreshToken(
#         user_id=user.id,
#         token=refresh_token_value,
#         expires_at=datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
#     )
#     db.add(rt)
#     db.commit()
    
#     return {
#         "access_token": access_token,
#         "refresh_token": refresh_token_value,
#         "user": {"email": user.email, "name": user.name, "role": user.role}
#     }

# @app.post("/logout")
# def logout(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
#     # Priority flush on logout (synchronous)
#     storage_manager.sync_dirty_threads()
    
#     db.query(RefreshToken).filter(RefreshToken.user_id == current_user.id).delete()
#     db.commit()
#     return {"message": "Logged out"}

# @app.get("/projects")
# def list_projects(email: str, db: Session = Depends(get_db)):
#     user = db.query(User).filter(User.email == email).first()
#     if not user:
#         return []
    
#     user_projects = (
#         db.query(Project)
#         .join(UserProject, UserProject.project_id == Project.id)
#         .filter(UserProject.user_id == user.id)
#         .all()
#     )
    
#     return [{"project_id": p.project_uuid, "name": p.name} for p in user_projects]

# # ======================================================================
# # 🚀 OPTIMIZED CONVERSATION ROUTES
# # ======================================================================
# @app.get("/conversations")
# def get_conversations(
#     project_id: Optional[str] = None,  # Accept project_uuid as query param
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """Get conversations, filtered by Project if provided"""
#     start = time.time()
    
#     # Start base query: Filter by User
#     query = db.query(Conversation).filter(Conversation.user_id == current_user.id)

#     # Apply Project Filter if provided
#     if project_id:
#         # Find the internal Integer ID for the given Project UUID
#         project = db.query(Project).filter(Project.project_uuid == project_id).first()
#         if project:
#             query = query.filter(Conversation.project_id == project.id)
#         else:
#             # If project ID is sent but doesn't exist, return empty list
#             return []

#     # Execute Query
#     convos = query.order_by(Conversation.created_at.desc()).all()
    
#     logger.info(f"⏱️  SQL query conversations: {(time.time() - start):.3f}s")
    
#     return [
#         {
#             "conversation_uuid": c.conversation_uuid,
#             "topic": c.topic,
#             "created_at": c.created_at.isoformat(),
#             "is_resolved": False,
#             "project_id": project_id # Return the UUID so frontend knows
#         }
#         for c in convos
#     ]

# from pydantic import BaseModel
# class StartConversationRequest(BaseModel):
#     project_id: str # Changed from int to str to accept UUID (e.g., "project_a")

# @app.post("/conversations/start")
# def start_conversation(
#     req: StartConversationRequest,
#     user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     # 1. Resolve UUID string ("project_a") to Internal ID (1)
#     project = db.query(Project).filter(Project.project_uuid == req.project_id).first()
    
#     if not project:
#         # If project doesn't exist in DB yet, handle gracefully or error
#         # For this example, we'll error, assuming you created projects in DB
#         raise HTTPException(status_code=404, detail="Project not found")

#     conv = Conversation(
#         user_id=user.id,
#         project_id=project.id, # Use the internal Integer ID
#         topic="New Chat"
#     )

#     db.add(conv)
#     db.commit()
#     db.refresh(conv)

#     return {
#         "conversation_uuid": conv.conversation_uuid,
#         "project_id": req.project_id, # Return the UUID string
#         "topic": conv.topic,
#         "created_at": conv.created_at,
#     }


# @app.get("/conversations/{conversation_uuid}/messages")
# def get_messages(
#     conversation_uuid: str,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """
#     🚀 OPTIMIZED: Get messages - FAST (no blocking auto-save)
#     """
#     start = time.time()
    
#     # Verify ownership
#     verify_start = time.time()
#     convo = db.query(Conversation).filter(
#         Conversation.conversation_uuid == conversation_uuid,
#         Conversation.user_id == current_user.id
#     ).first()
    
#     if not convo:
#         raise HTTPException(404, "Conversation not found")
    
#     logger.info(f"⏱️  SQL verify conversation: {(time.time() - verify_start)*1000:.1f}ms")
    
#     try:
#         # Queue OTHER threads for background flush (NON-BLOCKING)
#         queue_start = time.time()
#         with storage_manager.lock:
#             other_threads = [
#                 tid for tid in storage_manager.dirty_threads
#                 if tid != conversation_uuid
#             ]
        
#         for tid in other_threads:
#             storage_manager.queue_flush(tid, priority=False)
        
#         logger.info(f"⏱️  Queue other threads: {(time.time() - queue_start)*1000:.1f}ms")
        
#         # Load from Cosmos (uses cache if already loaded)
#         load_start = time.time()
#         storage_manager.load_from_cosmos(conversation_uuid, force_reload=False)
#         logger.info(f"⏱️  Load from Cosmos (or cache): {(time.time() - load_start):.3f}s")
        
#         # Get messages from memory - INSTANT
#         messages = storage_manager.get_messages(conversation_uuid)
        
#         total_time = time.time() - start
#         logger.info(f"⏱️  Total get_messages: {total_time:.3f}s")
        
#         return [
#             {
#                 "role": m["role"],
#                 "content": m["content"],
#                 "timestamp": m.get("timestamp", datetime.utcnow().isoformat())
#             }
#             for m in messages
#         ]
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"❌ Error: {e}", exc_info=True)
#         raise HTTPException(500, f"Failed to load messages: {str(e)}")

# @app.post("/conversations/{conversation_uuid}/messages")
# def add_message(
#     conversation_uuid: str,
#     payload: dict = Body(...),
#     background: BackgroundTasks = None,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """
#     🚀 OPTIMIZED: Add message - FAST streaming response
#     """
#     total_start = time.time()
    
#     logger.info("="*80)
#     logger.info(f"🚀 NEW MESSAGE REQUEST: {conversation_uuid}")
#     logger.info("="*80)
    
#     # Verify conversation
#     verify_start = time.time()
#     convo = db.query(Conversation).filter(
#         Conversation.conversation_uuid == conversation_uuid,
#         Conversation.user_id == current_user.id
#     ).first()
    
#     if not convo:
#         raise HTTPException(404, "Conversation not found")
    
#     logger.info(f"⏱️  SQL verify: {(time.time() - verify_start)*1000:.1f}ms")
    
#     user_text = payload.get("text", "")
    
#     # Save user message to memory - INSTANT
#     save_user_start = time.time()
#     storage_manager.add_message(conversation_uuid, "user", user_text)
#     logger.info(f"⏱️  Save user message to memory: {(time.time() - save_user_start)*1000:.1f}ms")
    
#     # Prepare messages
#     prep_start = time.time()
#     sys_msg = SystemMessage(content=f"thread_id:{conversation_uuid}")
#     user_msg = HumanMessage(content=user_text)
#     logger.info(f"⏱️  Prepare messages: {(time.time() - prep_start)*1000:.1f}ms")
    
#     # LangGraph streaming
#     collected_response = ""
#     chunk_count = 0
#     first_token_time = None
#     streaming_start = time.time()
    
#     logger.info("🤖 Starting AI processing...")
    
#     for chunk, meta in chatbot.stream(
#         {"messages": [sys_msg, user_msg]},
#         config={"configurable": {"thread_id": conversation_uuid}},
#         stream_mode="messages"
#     ):
#         txt = getattr(chunk, "content", "")
#         if txt:
#             current_time = time.time()
            
#             if first_token_time is None:
#                 first_token_time = current_time - streaming_start
#                 logger.info(f"⏱️  Time to first token: {first_token_time:.3f}s")
            
#             collected_response += txt
#             chunk_count += 1
    
#     streaming_end = time.time()
#     ai_total_time = streaming_end - streaming_start
#     logger.info(f"⏱️  AI processing (LangGraph streaming): {ai_total_time:.3f}s")
#     logger.info(f"📊 Received {chunk_count} chunks")
    
#     # Save AI message - INSTANT
#     save_ai_start = time.time()
#     storage_manager.add_message(conversation_uuid, "assistant", collected_response)
#     logger.info(f"⏱️  Save AI message to memory: {(time.time() - save_ai_start)*1000:.1f}ms")
    
#     # Queue background flush (NON-BLOCKING)
#     flush_start = time.time()
#     storage_manager.queue_flush(conversation_uuid, priority=False)
#     logger.info(f"⏱️  Queue background flush: {(time.time() - flush_start)*1000:.1f}ms")
    
#     show_resolved = "Is your issue resolved?" in collected_response
    
#     total_time = time.time() - total_start
    
#     # Title generation in BACKGROUND (non-blocking)
#     if convo.topic == "New Chat":
#         def update_title():
#             try:
#                 title_start = time.time()
#                 msgs = storage_manager.get_messages(conversation_uuid)
#                 if len(msgs) >= 4:
#                     text_msgs = [f"{m['role']}: {m['content']}" for m in msgs[:4]]
#                     title = asyncio.run(generate_chat_title(text_msgs))
                    
#                     # Update in database
#                     db_session = SessionLocal()
#                     try:
#                         conv = db_session.query(Conversation).filter(
#                             Conversation.conversation_uuid == conversation_uuid
#                         ).first()
#                         if conv:
#                             conv.topic = title
#                             db_session.commit()
#                             logger.info(f"⏱️  Title generation: {(time.time() - title_start):.3f}s")
#                             logger.info(f"📝 Updated title: {title}")
#                     finally:
#                         db_session.close()
#             except Exception as e:
#                 logger.error(f"❌ Title generation failed: {e}")
        
#         background.add_task(update_title)
    
#     # Final timing report
#     logger.info("="*80)
#     logger.info("⏱️  TIMING BREAKDOWN")
#     logger.info("="*80)
#     logger.info(f"Total request time:     {total_time:.3f}s")
#     logger.info(f"AI processing:          {ai_total_time:.3f}s ({(ai_total_time/total_time)*100:.1f}%)")
#     logger.info(f"Time to first token:    {first_token_time:.3f}s")
#     logger.info(f"Memory operations:      ~0.002s (instant)")
#     logger.info(f"Background tasks:       Queued (non-blocking)")
#     logger.info("="*80 + "\n")
    
#     return {
#         "role": "assistant",
#         "content": collected_response,
#         "topic": convo.topic,
#         "timestamp": datetime.utcnow().isoformat(),
#         "show_resolved": show_resolved,
#     }

# @app.post("/conversations/{conversation_uuid}/resolve")
# def mark_resolved(
#     conversation_uuid: str,
#     background: BackgroundTasks,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """Mark resolved - priority flush (synchronous)"""
#     start = time.time()
    
#     convo = db.query(Conversation).filter(
#         Conversation.conversation_uuid == conversation_uuid,
#         Conversation.user_id == current_user.id
#     ).first()
    
#     if not convo:
#         raise HTTPException(404, "Conversation not found")
    
#     # Priority flush (synchronous for critical operation)
#     flush_start = time.time()
#     count = storage_manager._do_flush(conversation_uuid)
#     logger.info(f"⏱️  Priority flush: {(time.time() - flush_start):.3f}s")
    
#     storage_manager.clear_memory(conversation_uuid)
    
#     logger.info(f"⏱️  Total mark_resolved: {(time.time() - start):.3f}s")
    
#     return {
#         "success": True,
#         "message": "Conversation resolved",
#         "messages_saved": count
#     }

# @app.delete("/conversations/{conversation_uuid}")
# def delete_conversation(
#     conversation_uuid: str,
#     background: BackgroundTasks,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """Delete conversation - priority flush before deletion"""
#     start = time.time()
    
#     convo = db.query(Conversation).filter(
#         Conversation.conversation_uuid == conversation_uuid,
#         Conversation.user_id == current_user.id
#     ).first()
    
#     if not convo:
#         raise HTTPException(404, "Conversation not found")
    
#     # Priority flush (synchronous)
#     flush_start = time.time()
#     storage_manager._do_flush(conversation_uuid)
#     logger.info(f"⏱️  Priority flush before delete: {(time.time() - flush_start):.3f}s")
    
#     storage_manager.clear_memory(conversation_uuid)
    
#     # Delete from SQL
#     db_start = time.time()
#     db.delete(convo)
#     db.commit()
#     logger.info(f"⏱️  SQL delete: {(time.time() - db_start)*1000:.1f}ms")
    
#     # Delete from Cosmos in background
#     background.add_task(delete_thread, conversation_uuid)
    
#     return {"status": "success", "message": "Conversation deleted"}

# @app.post("/conversations/{conversation_uuid}/feedback")
# def submit_feedback(
#     conversation_uuid: str,
#     payload: dict = Body(...),
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """Submit feedback - priority flush"""
    
#     convo = db.query(Conversation).filter(
#         Conversation.conversation_uuid == conversation_uuid,
#         Conversation.user_id == current_user.id
#     ).first()
    
#     if not convo:
#         raise HTTPException(404, "Conversation not found")
    
#     # Priority flush
#     storage_manager.queue_flush(conversation_uuid, priority=True)
    
#     existing_feedback = db.query(Feedback).filter(
#         Feedback.conversation_uuid == conversation_uuid,
#         Feedback.user_id == current_user.id
#     ).first()
    
#     if existing_feedback:
#         raise HTTPException(400, "Feedback already submitted")
    
#     feedback = Feedback(
#         conversation_uuid=conversation_uuid,
#         user_id=current_user.id,
#         rating=payload.get("rating"),
#         comment=payload.get("comment", ""),
#         message_count=payload.get("message_count", 0)
#     )
    
#     db.add(feedback)
#     db.commit()
    
#     return {"success": True, "message": "Feedback submitted"}

# @app.get("/projects/{project_id}/conversations")
# def get_conversations(project_id: str, db: Session = Depends(get_db)):
#     project = db.query(Project).filter(Project.project_uuid == project_id).first()
#     if not project:
#         return []

#     conversations = (
#         db.query(Conversation)
#         .filter(Conversation.project_id == project.id)
#         .all()
#     )

#     return [
#         {
#             "conversation_uuid": c.conversation_uuid,
#             "topic": c.topic,
#             "created_at": c.created_at,
#             "is_resolved": False,
#         }
#         for c in conversations
#     ]

# # ======================================================================
# # HEALTH & MONITORING
# # ======================================================================
# @app.get("/health")
# def health_check():
#     stats = storage_manager.get_stats()
#     return {
#         "status": "healthy",
#         "storage": stats,
#         "timestamp": datetime.utcnow().isoformat()
#     }

# @app.get("/admin/storage/stats")
# def get_storage_stats(admin: User = Depends(get_current_admin_user)):
#     return storage_manager.get_stats()

# @app.post("/admin/sync-all")
# def admin_sync_all(admin: User = Depends(get_current_admin_user)):
#     count = storage_manager.sync_dirty_threads()
#     return {
#         "success": True,
#         "messages_synced": count
#     }

# @app.post("/projects/{project_id}/conversations/start")
# def start_conversation(project_id: str, user_email: str, db: Session = Depends(get_db)):
#     project = db.query(Project).filter(Project.project_uuid == project_id).first()
#     user = db.query(User).filter(User.email == user_email).first()

#     new_conv = Conversation(
#         user_id=user.id,
#         project_id=project.id
#     )
    
#     db.add(new_conv)
#     db.commit()
#     db.refresh(new_conv)

#     return {
#         "conversation_uuid": new_conv.conversation_uuid,
#         "topic": new_conv.topic,
#         "created_at": new_conv.created_at
#     }
# @app.get("/projects")
# def get_user_projects(email: str, db: Session = Depends(get_db)):
#     user = db.query(User).filter(User.email == email).first()
#     if not user:
#         raise HTTPException(404, "User not found")

#     user_projects = (
#         db.query(Project)
#         .join(UserProject, Project.id == UserProject.project_id)
#         .filter(UserProject.user_id == user.id)
#         .all()
#     )

#     return [
#         {
#             "id": p.id,
#             "project_uuid": p.project_uuid,
#             "name": p.name
#         }
#         for p in user_projects
#     ]

# @app.get("/projects/{project_id}/conversations")
# def get_project_conversations(project_id: int, db: Session = Depends(get_db)):
#     conversations = (
#         db.query(Conversation)
#         .filter(Conversation.project_id == project_id)
#         .order_by(Conversation.created_at.desc())
#         .all()
#     )

#     return [
#         {
#             "conversation_uuid": c.conversation_uuid,
#             "topic": c.topic,
#             "created_at": c.created_at,
#             "project_id": c.project_id,
#             "user_id": c.user_id
#         }
#         for c in conversations
#     ]

# import logging
# import time
# import secrets
# import uuid
# import os
# import asyncio
# from datetime import datetime, timedelta
# from typing import Optional, List, Dict
# import atexit
# from threading import Lock, Thread
# from queue import Queue
# from collections import deque
# from contextlib import contextmanager

# # Set logging to INFO to see our timing logs
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# from fastapi import FastAPI, HTTPException, Depends, Body, Header, BackgroundTasks
# from fastapi.middleware.cors import CORSMiddleware
# from sqlalchemy.orm import Session
# from jose import jwt, JWTError
# from passlib.context import CryptContext
# from pydantic import BaseModel

# # Database imports
# from database_model import SessionLocal, User, Conversation, RefreshToken, Feedback, init_db, Project, UserProject

# # Chatbot imports
# from chatbot.langgraph_database_backend import chatbot
# from chatbot.cosmos_store import append_message, load_messages, delete_thread
# from langchain_core.messages import HumanMessage, SystemMessage





# # Password hashing
# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# from langchain_openai import AzureChatOpenAI

# # Fast mini-model just for summarizing chat titles
# title_llm = AzureChatOpenAI(
#     azure_endpoint=os.getenv("AZURE_GPT4O_ENDPOINT"),
#     deployment_name=os.getenv("AZURE_GPT4O_DEPLOYMENT"),
#     openai_api_version=os.getenv("AZURE_GPT4O_API_VERSION"),
#     api_key=os.getenv("AZURE_GPT4O_API_KEY"),
#     temperature=0,
#     streaming=True
# )

# async def generate_chat_title(messages):
#     """Generate a 4–5 word conversation title from initial messages."""
#     prompt = f"""
#     Create a VERY short 4–5 word title summarizing this conversation.
#     Messages:
#     {messages}

#     Only return the title. No quotes.
#     """
#     try:
#         start = time.time()
#         result = await title_llm.ainvoke([HumanMessage(content=prompt)])
#         duration = time.time() - start
#         title = result.content.strip()[:50]
#         logger.info(f"⏱️  Title Gen ({duration:.3f}s): {title}")
#         return title
#     except Exception as e:
#         logger.error(f"Title generation failed: {e}")
#         return "New Chat"

# # ======================================================================
# # 🚀 OPTIMIZED HYBRID STORAGE MANAGER (WITH TIMING LOGS)
# # ======================================================================
# # main.py - Complete OptimizedHybridStorageManager class
# # Replace your existing class with this complete version

# class OptimizedHybridStorageManager:
#     def __init__(self):
#         self.memory: Dict[str, List[Dict]] = {}
#         self.active_threads: Dict[str, datetime] = {}
#         self.dirty_threads: set = set()
#         self.lock = Lock()
        
#         self.flush_queue: Queue = Queue()
#         self.flush_worker_running = True
#         self.flush_thread = Thread(target=self._background_flush_worker, daemon=True)
#         self.flush_thread.start()
        
#         self.cosmos_loaded: set = set()
#         logger.info("✅ OptimizedHybridStorageManager initialized")

#     def add_message(self, thread_id: str, role: str, content: str):
#         """Add message to memory - INSTANT (no I/O)"""
#         start = time.time()
        
#         with self.lock:
#             if thread_id not in self.memory:
#                 self.memory[thread_id] = []

#             self.memory[thread_id].append({
#                 "role": role,
#                 "content": content,
#                 "timestamp": datetime.utcnow().isoformat()
#             })

#             self.active_threads[thread_id] = datetime.utcnow()
#             self.dirty_threads.add(thread_id)
        
#         duration = (time.time() - start) * 1000  # ms
#         logger.info(f"⚡ Memory Write ({role}): {duration:.4f}ms (INSTANT)")

#     def get_messages(self, thread_id: str) -> List[Dict]:
#         """Get messages - INSTANT (from memory)"""
#         start = time.time()
        
#         with self.lock:
#             result = self.memory.get(thread_id, []).copy()
        
#         duration = (time.time() - start) * 1000  # ms
#         logger.info(f"⚡ Memory Read: {duration:.4f}ms ({len(result)} msgs)")
        
#         return result

#     def queue_flush(self, thread_id: str, priority: bool = False):
#         """Queue thread for background flush - NON-BLOCKING"""
#         if priority:
#             self._do_flush(thread_id)
#         else:
#             self.flush_queue.put(thread_id)
#             logger.info(f"📥 Queued Background Flush: {thread_id} (Non-blocking)")

#     def _background_flush_worker(self):
#         """Background thread that processes flush queue"""
#         logger.info("🔄 Background flush worker started")
        
#         while self.flush_worker_running:
#             try:
#                 # Process batch of flushes
#                 batch = []
                
#                 # Collect up to 5 threads or wait 1s
#                 timeout = 1.0
#                 try:
#                     thread_id = self.flush_queue.get(timeout=timeout)
#                     batch.append(thread_id)
                    
#                     # Grab more from queue (non-blocking)
#                     while len(batch) < 5:
#                         try:
#                             thread_id = self.flush_queue.get_nowait()
#                             batch.append(thread_id)
#                         except:
#                             break
                            
#                 except:
#                     continue
                
#                 # Process batch
#                 for thread_id in batch:
#                     try:
#                         self._do_flush(thread_id)
#                     except Exception as e:
#                         logger.error(f"❌ Background flush failed for {thread_id}: {e}")
                        
#             except Exception as e:
#                 logger.error(f"❌ Flush worker error: {e}")

#     def _do_flush(self, thread_id: str) -> int:
#         """Flush to Cosmos - fails gracefully if unavailable."""
#         flush_start = time.time()
        
#         with self.lock:
#             if thread_id not in self.memory or thread_id not in self.dirty_threads:
#                 return 0
#             msgs = self.memory[thread_id].copy()

#         try:
#             # Check if Cosmos is available
#             from chatbot.cosmos_store import is_available
#             if not is_available():
#                 logger.warning(f"⚠️  Cosmos unavailable - keeping {len(msgs)} msgs in memory")
#                 # Don't mark as clean - will retry later
#                 return 0

#             # Get existing count
#             try:
#                 cosmos_msgs = load_messages(project_id, thread_id)
#                 existing_count = len(cosmos_msgs)
#             except:
#                 existing_count = 0

#             # Only append NEW messages
#             new_msgs = msgs[existing_count:]
            
#             if not new_msgs:
#                 with self.lock:
#                     self.dirty_threads.discard(thread_id)
#                 return 0

#             # Batch append
#             count = 0
#             for m in new_msgs:
#                 result = append_message(
#                     thread_id,
#                     m["role"],
#                     m["content"],
#                     metadata={"timestamp": m.get("timestamp")}
#                 )
#                 if result:  # Only count if successful
#                     count += 1

#             # Only mark as clean if all messages were saved
#             if count == len(new_msgs):
#                 with self.lock:
#                     self.dirty_threads.discard(thread_id)
#                 logger.info(f"💾 DB Write: {count} msgs in {time.time() - flush_start:.3f}s")
#             else:
#                 logger.warning(f"⚠️  Partial flush: {count}/{len(new_msgs)} msgs saved")

#             return count

#         except Exception as e:
#             logger.error(f"❌ Flush error: {e}")
#             logger.warning(f"⚠️  Messages remain in memory (will retry)")
#             return 0

#     def load_from_cosmos(self, thread_id: str, force_reload: bool = False) -> int:
#         """
#         Load from Cosmos - WITH GRACEFUL FALLBACK
#         If Cosmos is unavailable, continues with in-memory storage only.
#         """
#         load_start = time.time()
        
#         with self.lock:
#             # Check cache first
#             if thread_id in self.cosmos_loaded and not force_reload:
#                 if thread_id in self.memory:
#                     logger.info(f"⚡ Cache Hit: Loaded from Memory (0ms)")
#                     return len(self.memory[thread_id])

#         try:
#             cosmos_start = time.time()
#             cosmos_msgs = load_messages(project_id ,thread_id)  # Returns [] if Cosmos unavailable
#             db_latency = (time.time() - cosmos_start)
            
#             # If Cosmos returned empty, check if it's really empty or just unavailable
#             from chatbot.cosmos_store import is_available
            
#             if not cosmos_msgs and not is_available():
#                 # Cosmos is unavailable - use memory-only mode
#                 logger.warning(f"⚠️  Cosmos DB unavailable - using memory-only mode")
#                 with self.lock:
#                     if thread_id not in self.memory:
#                         self.memory[thread_id] = []
#                 return 0
            
#             with self.lock:
#                 # Only overwrite if memory is NOT dirty
#                 if thread_id not in self.dirty_threads:
#                     self.memory[thread_id] = [
#                         {
#                             "role": m["role"],
#                             "content": m["content"],
#                             "timestamp": m.get("timestamp", datetime.utcnow().isoformat())
#                         }
#                         for m in cosmos_msgs
#                     ]
#                     if cosmos_msgs:
#                         self.active_threads[thread_id] = datetime.utcnow()
#                     self.cosmos_loaded.add(thread_id)
                
#             logger.info(f"📥 DB Read: {len(cosmos_msgs)} msgs in {db_latency:.3f}s")
#             return len(cosmos_msgs)

#         except Exception as e:
#             logger.error(f"❌ Load error: {e}")
#             with self.lock:
#                 if thread_id not in self.memory:
#                     self.memory[thread_id] = []
#             return 0

#     def sync_dirty_threads(self) -> int:
#         """Synchronously flush only DIRTY threads (for critical operations)"""
#         with self.lock:
#             dirty = list(self.dirty_threads)
        
#         total = 0
#         for tid in dirty:
#             total += self._do_flush(tid)
#         return total

#     def shutdown_flush(self):
#         """Emergency shutdown - flush all dirty threads"""
#         logger.info("🛑 Shutting down storage manager...")
        
#         # Stop background worker
#         self.flush_worker_running = False
        
#         # Wait for background thread to finish (max 5 seconds)
#         if self.flush_thread.is_alive():
#             self.flush_thread.join(timeout=5)
        
#         # Flush all dirty threads synchronously
#         try:
#             flushed = self.sync_dirty_threads()
#             logger.info(f"✅ Shutdown complete - flushed {flushed} messages")
#         except Exception as e:
#             logger.error(f"❌ Shutdown flush error: {e}")
        
#     def clear_memory(self, thread_id: str):
#         """Clear thread from memory"""
#         with self.lock:
#             self.memory.pop(thread_id, None)
#             self.active_threads.pop(thread_id, None)
#             self.dirty_threads.discard(thread_id)
#             self.cosmos_loaded.discard(thread_id)

#     def get_stats(self) -> Dict:
#         """Get statistics"""
#         with self.lock:
#             return {
#                 "active_threads": len(self.active_threads),
#                 "dirty_threads": len(self.dirty_threads),
#                 "cached_threads": len(self.cosmos_loaded),
#                 "total_messages": sum(len(msgs) for msgs in self.memory.values()),
#             }
# # Initialize optimized storage manager
# storage_manager = OptimizedHybridStorageManager()

# # Register shutdown handler
# atexit.register(storage_manager.shutdown_flush)

# # ======================================================================
# # FASTAPI APP
# # ======================================================================
# app = FastAPI()

# # CORS
# ALLOWED_ORIGINS = [
#     "http://localhost:3000",
#     "http://127.0.0.1:3000",
#     "https://wonderful-grass-043c527003.azurestaticapps.net"
# ]

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=ALLOWED_ORIGINS,
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# init_db()

# # Config
# SECRET_KEY = os.getenv("SECRET_KEY", "change_this_to_a_strong_random_secret")
# ALGORITHM = "HS256"
# ACCESS_TOKEN_EXPIRE_MINUTES = 60
# REFRESH_TOKEN_EXPIRE_DAYS = 30


# # ======================================================================
# # DEPENDENCIES
# # ======================================================================
# def get_db():
#     db = SessionLocal()
#     try:
#         yield db
#     finally:
#         db.close()

# def get_current_user(
#     authorization: str = Header(None),
#     db: Session = Depends(get_db)
# ) -> User:
#     if not authorization:
#         raise HTTPException(401, "Missing Authorization header")
#     if not authorization.startswith("Bearer "):
#         raise HTTPException(401, "Invalid auth format")
    
#     token = authorization.replace("Bearer ", "").strip()
    
#     try:
#         payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
#         user_id = payload.get("sub")
#         if not user_id:
#             raise HTTPException(401, "Invalid token payload")
        
#         user = db.query(User).filter(User.id == int(user_id)).first()
#         if not user:
#             raise HTTPException(401, "User not found")
        
#         return user
#     except JWTError:
#         raise HTTPException(401, "Invalid or expired token")

# def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
#     if current_user.role != "admin":
#         raise HTTPException(403, "Admin access required")
#     return current_user

# # ======================================================================
# # HELPERS
# # ======================================================================

# from knowledgebase import router as kb_router   
# app.include_router(kb_router)


# def create_access_token(data: dict, expires_delta: timedelta = None):
#     to_encode = data.copy()
#     expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
#     to_encode.update({"exp": expire})
#     return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# def create_refresh_token():
#     return secrets.token_urlsafe(32)

# # ======================================================================
# # AUTH ROUTES
# # ======================================================================
# @app.post("/login")
# def login(data: dict, db: Session = Depends(get_db)):
#     email = data.get("email")
#     password = data.get("password")
    
#     user = db.query(User).filter(User.email == email).first()
#     if not user or user.password != password:
#         raise HTTPException(401, "Invalid credentials")
    
#     access_token = create_access_token({"sub": str(user.id), "email": user.email})
#     refresh_token_value = create_refresh_token()
    
#     rt = RefreshToken(
#         user_id=user.id,
#         token=refresh_token_value,
#         expires_at=datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
#     )
#     db.add(rt)
#     db.commit()
    
#     return {
#         "access_token": access_token,
#         "refresh_token": refresh_token_value,
#         "user": {"email": user.email, "name": user.name, "role": user.role}
#     }

# @app.post("/logout")
# def logout(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
#     # Priority flush on logout (synchronous)
#     storage_manager.sync_dirty_threads()
    
#     db.query(RefreshToken).filter(RefreshToken.user_id == current_user.id).delete()
#     db.commit()
#     return {"message": "Logged out"}

# @app.get("/projects")
# def list_projects(email: str, db: Session = Depends(get_db)):
#     user = db.query(User).filter(User.email == email).first()
#     if not user:
#         return []
    
#     # Return actual DB projects
#     projects = db.query(Project).all()
    
#     return [{"project_id": p.project_uuid, "name": p.name} for p in projects]

# # ======================================================================
# # 🚀 OPTIMIZED CONVERSATION ROUTES
# # ======================================================================

# @app.get("/conversations")
# def get_conversations(
#     project_id: Optional[str] = None, 
#     current_user: User = Depends(get_current_user), 
#     db: Session = Depends(get_db)
# ):
#     """Get all conversations - FAST (SQL only, no Cosmos)"""
#     start = time.time()
    
#     query = db.query(Conversation).filter(Conversation.user_id == current_user.id)

#     if project_id:
#         project = db.query(Project).filter(Project.project_uuid == project_id).first()
#         if project:
#             query = query.filter(Conversation.project_id == project.id)
#         else:
#             return []
#     else:
#         # STRICT: Return nothing if no project is selected
#         return []

#     convos = query.order_by(Conversation.created_at.desc()).all()
    
#     logger.info(f"⏱️  SQL List Conversations: {(time.time() - start):.3f}s")
    
#     return [
#         {
#             "conversation_uuid": c.conversation_uuid,
#             "topic": c.topic,
#             "created_at": c.created_at.isoformat(),
#             "is_resolved": False,
#             "project_id": project_id
#         }
#         for c in convos
#     ]

# class StartConversationRequest(BaseModel):
#     project_id: str

# @app.post("/conversations/start")
# def start_conversation(
#     req: StartConversationRequest,
#     user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     project = db.query(Project).filter(Project.project_uuid == req.project_id).first()
    
#     if not project:
#         raise HTTPException(status_code=404, detail=f"Project '{req.project_id}' not found.")

#     conv = Conversation(
#         user_id=user.id,
#         project_id=project.id, 
#         topic="New Chat"
#     )

#     db.add(conv)
#     db.commit()
#     db.refresh(conv)

#     return {
#         "conversation_uuid": conv.conversation_uuid,
#         "project_id": req.project_id,
#         "topic": conv.topic,
#         "created_at": conv.created_at,
#     }


# @app.get("/conversations/{conversation_uuid}/messages")
# def get_messages(
#     conversation_uuid: str,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """
#     🚀 OPTIMIZED: Get messages - FAST (no blocking auto-save)
#     """
#     convo = db.query(Conversation).filter(
#         Conversation.conversation_uuid == conversation_uuid,
#         Conversation.user_id == current_user.id
#     ).first()
    
#     if not convo:
#         raise HTTPException(404, "Conversation not found")
    
#     # Load from Cosmos (uses cache if already loaded)
#     storage_manager.load_from_cosmos(conversation_uuid)
        
#     # Get messages from memory - INSTANT
#     messages = storage_manager.get_messages(conversation_uuid)
    
#     return [
#         {
#             "role": m["role"],
#             "content": m["content"],
#             "timestamp": m.get("timestamp", datetime.utcnow().isoformat())
#         }
#         for m in messages
#     ]

# @app.post("/conversations/{conversation_uuid}/messages")
# def add_message(
#     conversation_uuid: str,
#     payload: dict = Body(...),
#     background: BackgroundTasks = None,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """
#     🚀 OPTIMIZED: Add message with Project Filtering, Instant Title Update & Detailed Logs
#     """
#     total_start = time.time()
    
#     logger.info("="*60)
#     logger.info(f"🚀 REQUEST STARTED: {conversation_uuid}")
#     logger.info("="*60)
    
#     # 1. Fetch Conversation & Project Info
#     convo = db.query(Conversation).filter(
#         Conversation.conversation_uuid == conversation_uuid,
#         Conversation.user_id == current_user.id
#     ).first()
    
#     if not convo:
#         raise HTTPException(404, "Conversation not found")
    
#     # Get the project UUID to help AI filter search results
#     project_filter = convo.project.project_uuid if convo.project else None

#     # 2. LOAD HISTORY FIRST (Fixes vanishing messages)
#     storage_manager.load_from_cosmos(conversation_uuid)

#     user_text = payload.get("text", "")
    
#     # 3. Save user message to memory - INSTANT
#     save_user_start = time.time()
#     storage_manager.add_message(conversation_uuid, "user", user_text)
#     save_user_time = time.time() - save_user_start
    
#     sys_msg = SystemMessage(content=f"thread_id:{conversation_uuid}")
#     user_msg = HumanMessage(content=user_text)
    
#     collected_response = ""
#     chunk_count = 0
#     first_token_time = None
#     ai_start = time.time()
    
#     # 4. Stream AI Response (Pass project_filter to config)
#     for chunk, meta in chatbot.stream(
#         {"messages": [sys_msg, user_msg]},
#         config={
#             "configurable": {
#                 "thread_id": conversation_uuid,
#                 "project_id": project_filter  # <--- PASSING PROJECT ID HERE
#             }
#         },
#         stream_mode="messages"
#     ):
#         txt = getattr(chunk, "content", "")
#         if txt:
#             if first_token_time is None:
#                 first_token_time = time.time() - ai_start
#                 logger.info(f"🤖 AI First Token: {first_token_time:.3f}s")
            
#             collected_response += txt
#             chunk_count += 1
    
#     ai_total_time = time.time() - ai_start
#     logger.info(f"🤖 AI Total Time: {ai_total_time:.3f}s ({chunk_count} chunks)")
    
#     # 5. Save AI message - INSTANT
#     save_ai_start = time.time()
#     storage_manager.add_message(conversation_uuid, "assistant", collected_response)
#     save_ai_time = time.time() - save_ai_start

#     storage_manager.queue_flush(conversation_uuid, priority=False)
    
#     # 6. Title generation (Background)
#     if convo.topic == "New Chat":
#         msgs = storage_manager.get_messages(conversation_uuid)
#         if len(msgs) >= 4:
#             async def update_title_task(conv_uuid, message_history):
#                 try:
#                     text_msgs = [f"{m['role']}: {m['content']}" for m in message_history[:4]]
#                     title = await generate_chat_title(text_msgs)
#                     new_db = SessionLocal()
#                     try:
#                         c = new_db.query(Conversation).filter(Conversation.conversation_uuid == conv_uuid).first()
#                         if c:
#                             c.topic = title
#                             new_db.commit()
#                             logger.info(f"📝 Title Updated in DB: {title}")
#                     finally:
#                         new_db.close()
#                 except Exception as e:
#                     logger.error(f"Title gen error: {e}")

#             background.add_task(update_title_task, conversation_uuid, msgs)
            
#             # Refresh object to return updated topic immediately if DB updated fast enough
#             db.refresh(convo)

#     show_resolved = "Is your issue resolved?" in collected_response
    
#     total_time = time.time() - total_start

#     # ========================================================
#     # 📊 FINAL PERFORMANCE LOGS
#     # ========================================================
#     logger.info("="*60)
#     logger.info(f"🏁 REQUEST COMPLETE: {total_time:.3f}s total")
#     logger.info(f"   - User Msg Save:  {save_user_time:.4f}s (Instant)")
#     logger.info(f"   - AI Processing:  {ai_total_time:.3f}s")
#     logger.info(f"   - AI Msg Save:    {save_ai_time:.4f}s (Instant)")
#     logger.info(f"   - DB Write:       Queued (Background)")
#     logger.info("="*60 + "\n")

#     return {
#         "role": "assistant",
#         "content": collected_response,
#         "topic": convo.topic, 
#         "timestamp": datetime.utcnow().isoformat(),
#         "show_resolved": show_resolved,
#     }
# @app.post("/conversations/{conversation_uuid}/resolve")
# def mark_resolved(
#     conversation_uuid: str,
#     background: BackgroundTasks,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     convo = db.query(Conversation).filter(
#         Conversation.conversation_uuid == conversation_uuid,
#         Conversation.user_id == current_user.id
#     ).first()
    
#     if not convo:
#         raise HTTPException(404, "Conversation not found")
    
#     # Priority flush (synchronous)
#     storage_manager._do_flush(conversation_uuid)
#     storage_manager.clear_memory(conversation_uuid)
    
#     return {
#         "success": True,
#         "message": "Conversation resolved"
#     }

# @app.delete("/conversations/{conversation_uuid}")
# def delete_conversation(
#     conversation_uuid: str,
#     background: BackgroundTasks,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """Delete conversation - priority flush before deletion"""
#     convo = db.query(Conversation).filter(
#         Conversation.conversation_uuid == conversation_uuid,
#         Conversation.user_id == current_user.id
#     ).first()
    
#     if not convo:
#         raise HTTPException(404, "Conversation not found")
    
#     # Priority flush (synchronous)
#     storage_manager._do_flush(conversation_uuid)
#     storage_manager.clear_memory(conversation_uuid)
    
#     # Delete from SQL
#     db.delete(convo)
#     db.commit()
    
#     # Delete from Cosmos in background
#     background.add_task(delete_thread, conversation_uuid)
    
#     return {"status": "success", "message": "Conversation deleted"}

# @app.post("/conversations/{conversation_uuid}/feedback")
# def submit_feedback(
#     conversation_uuid: str,
#     payload: dict = Body(...),
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     convo = db.query(Conversation).filter(
#         Conversation.conversation_uuid == conversation_uuid,
#         Conversation.user_id == current_user.id
#     ).first()
    
#     if not convo:
#         raise HTTPException(404, "Conversation not found")
    
#     storage_manager.queue_flush(conversation_uuid, priority=True)
    
#     existing_feedback = db.query(Feedback).filter(
#         Feedback.conversation_uuid == conversation_uuid,
#         Feedback.user_id == current_user.id
#     ).first()
    
#     if existing_feedback:
#         raise HTTPException(400, "Feedback already submitted")
    
#     feedback = Feedback(
#         conversation_uuid=conversation_uuid,
#         user_id=current_user.id,
#         rating=payload.get("rating"),
#         comment=payload.get("comment", ""),
#         message_count=payload.get("message_count", 0)
#     )
    
#     db.add(feedback)
#     db.commit()
    
#     return {"success": True, "message": "Feedback submitted"}

# # ======================================================================
# # HEALTH & MONITORING
# # ======================================================================
# @app.get("/health")
# def health_check():
#     stats = storage_manager.get_stats()
#     return {
#         "status": "healthy",
#         "storage": stats,
#         "timestamp": datetime.utcnow().isoformat()
#     }

# @app.get("/admin/storage/stats")
# def get_storage_stats(admin: User = Depends(get_current_admin_user)):
#     return storage_manager.get_stats()

# @app.post("/admin/sync-all")
# def admin_sync_all(admin: User = Depends(get_current_admin_user)):
#     count = storage_manager.sync_dirty_threads()
#     return {
#         "success": True,
#         "messages_synced": count
#     }

# @app.get("/admin/users")
# def get_all_users(admin: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
#     users = db.query(User).all()
#     return {"users": [{"id": u.id, "email": u.email, "name": u.name, "role": u.role} for u in users]}

# @app.get("/api/admin/analytics")
# def get_analytics(current_user=Depends(get_current_user)):
#     """
#     Fetches AI usage stats from LangSmith, including DAILY trends.
#     """
#     if current_user.role != "admin":
#         raise HTTPException(status_code=403, detail="Not authorized")

#     try:
#         client = Client()
#         project_name = os.getenv("LANGCHAIN_PROJECT", "svayam-chatbot-prod")

#         # Fetch runs from last 7 days
#         runs = list(client.list_runs(
#             project_name=project_name,
#             is_root=True, 
#             start_time=datetime.now() - timedelta(days=7)
#         ))
#     except Exception as e:
#         print(f"LangSmith Connection Error: {e}")
#         return {"total_requests": 0, "total_tokens": 0, "total_cost": 0, "avg_latency": 0, "daily_trends": []}

#     # --- AGGREGATION LOGIC ---
#     total_runs = len(runs)
#     total_tokens = 0
#     total_cost = 0.0
#     total_latency = 0.0
    
#     # Dictionary to group data by date: "2023-10-27": { ...stats... }
#     daily_map = defaultdict(lambda: {"requests": 0, "tokens": 0, "cost": 0.0, "latency_sum": 0.0})

#     for run in runs:
#         # Get Date string (YYYY-MM-DD)
#         date_str = run.start_time.strftime("%Y-%m-%d")
        
#         # 1. Requests
#         daily_map[date_str]["requests"] += 1
        
#         # 2. Tokens
#         tokens = run.total_tokens or 0
#         total_tokens += tokens
#         daily_map[date_str]["tokens"] += tokens
        
#         # 3. Cost
#         cost = 0.0
#         if hasattr(run, "total_cost") and run.total_cost:
#             cost = float(run.total_cost)
#             total_cost += cost
#             daily_map[date_str]["cost"] += cost

#         # 4. Latency
#         latency = 0.0
#         if run.end_time and run.start_time:
#             latency = (run.end_time - run.start_time).total_seconds()
#             total_latency += latency
#             daily_map[date_str]["latency_sum"] += latency

#     # Calculate Averages and formatting
#     avg_latency = (total_latency / total_runs) if total_runs > 0 else 0
    
#     # Convert daily_map to a sorted list for the frontend graph
#     daily_trends = []
#     # Ensure we cover the last 7 days even if empty
#     for i in range(6, -1, -1):
#         day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
#         stats = daily_map.get(day, {"requests": 0, "tokens": 0, "cost": 0.0, "latency_sum": 0.0})
        
#         # Calculate daily avg latency
#         daily_avg_latency = (stats["latency_sum"] / stats["requests"]) if stats["requests"] > 0 else 0
        
#         daily_trends.append({
#             "date": day, # X-Axis value
#             "requests": stats["requests"],
#             "tokens": stats["tokens"],
#             "cost": round(stats["cost"], 4),
#             "avg_latency": round(daily_avg_latency, 2)
#         })

#     return {
#         "total_requests": total_runs,
#         "total_tokens": total_tokens,
#         "total_cost": round(total_cost, 4),
#         "avg_latency": round(avg_latency, 2),
#         "daily_trends": daily_trends # <--- New List for Graphs
#     }

# main.py (corrected for NEW Cosmos schema: partition key = /project_id)
# main.py
import logging
import time
import secrets
import uuid
import os
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, DefaultDict
import atexit
from threading import Lock, Thread
from queue import Queue
from collections import defaultdict
from contextlib import contextmanager

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI + dependencies
from fastapi import FastAPI, HTTPException, Depends, Body, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from passlib.context import CryptContext
from pydantic import BaseModel

# Local DB models (adjust import path if necessary)
from database_model import (
    SessionLocal,
    User,
    Conversation,
    RefreshToken,
    Feedback,
    init_db,
    Project,
    UserProject,
)

# Chatbot backends
from chatbot.langgraph_database_backend import chatbot
# cosmos_store must implement:
# append_message(project_name, thread_id, role, content, metadata),
# load_messages(project_name, thread_id, max_items),
# delete_thread(project_name, thread_id),
# is_available()
from chatbot.cosmos_store import (
    append_message,
    load_messages,
    delete_thread,
    cosmos_is_available,
)

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_openai import AzureChatOpenAI


# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Mini LLM for chat title generation (async)
title_llm = AzureChatOpenAI(
    azure_endpoint=os.getenv("AZURE_GPT4O_ENDPOINT"),
    deployment_name=os.getenv("AZURE_GPT4O_DEPLOYMENT"),
    openai_api_version=os.getenv("AZURE_GPT4O_API_VERSION"),
    api_key=os.getenv("AZURE_GPT4O_API_KEY"),
    temperature=0,
    streaming=True,
)

async def generate_chat_title(messages):
    prompt = f"""
Create a VERY short 4–5 word title summarizing this conversation.
Messages:
{messages}

Only return the title. No quotes.
"""
    try:
        start = time.time()
        result = await title_llm.ainvoke([HumanMessage(content=prompt)])
        duration = time.time() - start
        title = (result.content or "").strip()[:50]
        logger.info(f"⏱️  Title Gen ({duration:.3f}s): {title}")
        return title or "New Chat"
    except Exception as e:
        logger.error(f"Title generation failed: {e}")
        return "New Chat"

# ======================================================================
# OptimizedHybridStorageManager (project_name as partition key)
# ======================================================================

class OptimizedHybridStorageManager:
    """
    In-memory buffer + background flush worker.
    Uses project_name as partition key when flushing to Cosmos.
    """

    def __init__(self):
        self.memory: Dict[str, List[Dict]] = {}
        self.active_threads: Dict[str, datetime] = {}
        self.dirty_threads: set = set()
        self.lock = Lock()

        self.flush_queue: Queue = Queue()
        self.flush_worker_running = True
        self.flush_thread = Thread(target=self._background_flush_worker, daemon=True)
        self.flush_thread.start()

        self.cosmos_loaded: set = set()
        # thread_id -> project_name mapping (must be set when creating or first message)
        self.thread_to_project: Dict[str, str] = {}
        logger.info("✅ OptimizedHybridStorageManager initialized")

    def add_message(self, thread_id: str, role: str, content: str, project_name: Optional[str] = None, metadata: Optional[Dict] = None):
        """Add message to memory; optionally record the project_name mapping."""
        start = time.time()
        with self.lock:
            if thread_id not in self.memory:
                self.memory[thread_id] = []
            self.memory[thread_id].append({
                "role": role,
                "content": content,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "metadata": metadata or {}
            })
            if project_name:
                self.thread_to_project[thread_id] = project_name
            self.active_threads[thread_id] = datetime.utcnow()
            self.dirty_threads.add(thread_id)
        duration = (time.time() - start) * 1000
        logger.info(f"⚡ Memory Write ({role}): {duration:.4f}ms (INSTANT)")

    def get_messages(self, thread_id: str) -> List[Dict]:
        start = time.time()
        with self.lock:
            result = list(self.memory.get(thread_id, []))
        duration = (time.time() - start) * 1000
        logger.info(f"⚡ Memory Read: {duration:.4f}ms ({len(result)} msgs)")
        return result

    def queue_flush(self, thread_id: str, project_name: Optional[str] = None, priority: bool = False):
        """Queue thread for background flush. If priority, flush sync."""
        if project_name:
            with self.lock:
                self.thread_to_project[thread_id] = project_name
        if priority:
            self._do_flush(thread_id, project_name)
        else:
            self.flush_queue.put(thread_id)
            logger.info(f"📥 Queued Background Flush: {thread_id} (Non-blocking)")

    def _background_flush_worker(self):
        logger.info("🔄 Background flush worker started")
        while self.flush_worker_running:
            try:
                try:
                    thread_id = self.flush_queue.get(timeout=1.0)
                except Exception:
                    continue

                batch = [thread_id]
                while len(batch) < 5:
                    try:
                        batch.append(self.flush_queue.get_nowait())
                    except Exception:
                        break

                for tid in batch:
                    try:
                        with self.lock:
                            proj = self.thread_to_project.get(tid)
                        self._do_flush(tid, proj)
                    except Exception as e:
                        logger.error(f"❌ Background flush failed for {tid}: {e}")

            except Exception as e:
                logger.error(f"❌ Flush worker error: {e}")

    def _do_flush(self, thread_id: str, project_name: Optional[str] = None) -> int:
        """Flush messages for a thread to Cosmos using project_name as partition key."""
        flush_start = time.time()
        with self.lock:
            if thread_id not in self.memory or thread_id not in self.dirty_threads:
                return 0
            msgs = list(self.memory[thread_id])
            if not project_name:
                project_name = self.thread_to_project.get(thread_id)

        if not project_name:
            logger.warning(f"⚠️  No project_name for thread {thread_id}; cannot flush to Cosmos. Keeping in memory.")
            return 0

        try:
            if not cosmos_is_available():
                logger.warning(f"⚠️  Cosmos unavailable - keeping {len(msgs)} msgs in memory for {thread_id}")
                return 0

            # Load existing messages from Cosmos to avoid duplicates
            try:
                existing = load_messages(project_name, thread_id)
                existing_count = len(existing)
            except Exception:
                existing_count = 0

            new_msgs = msgs[existing_count:]
            if not new_msgs:
                with self.lock:
                    self.dirty_threads.discard(thread_id)
                return 0

            count = 0
            for m in new_msgs:
                res = append_message(project_name, thread_id, m["role"], m["content"], metadata=m.get("metadata", {}))
                if res:
                    count += 1

            if count == len(new_msgs):
                with self.lock:
                    self.dirty_threads.discard(thread_id)
                logger.info(f"💾 DB Write: {count} msgs for {thread_id} in {time.time() - flush_start:.3f}s")
            else:
                logger.warning(f"⚠️  Partial flush for {thread_id}: {count}/{len(new_msgs)} saved")

            return count
        except Exception as e:
            logger.error(f"❌ Flush error: {e}")
            logger.warning("⚠️  Messages remain in memory (will retry)")
            return 0

    def load_from_cosmos(self, thread_id: str, project_name: Optional[str] = None, force_reload: bool = False) -> int:
        with self.lock:
            if thread_id in self.cosmos_loaded and not force_reload:
                if thread_id in self.memory:
                    logger.info("⚡ Cache Hit: Loaded from Memory (0ms)")
                    return len(self.memory[thread_id])
            if not project_name:
                project_name = self.thread_to_project.get(thread_id)

        if not project_name:
            logger.info(f"ℹ️  No project_name for thread {thread_id}; skipping Cosmos load (memory-only).")
            with self.lock:
                if thread_id not in self.memory:
                    self.memory[thread_id] = []
            return 0

        try:
            cosmos_start = time.time()
            cosmos_msgs = load_messages(project_name, thread_id)  # may raise
            db_latency = (time.time() - cosmos_start)

            if not cosmos_msgs and not cosmos_is_available():
                logger.warning("⚠️  Cosmos DB unavailable - using memory-only mode")
                with self.lock:
                    if thread_id not in self.memory:
                        self.memory[thread_id] = []
                return 0

            with self.lock:
                if thread_id not in self.dirty_threads:
                    self.memory[thread_id] = [
                        {
                            "role": m["role"],
                            "content": m["content"],
                            "timestamp": m.get("timestamp", datetime.utcnow().isoformat()),
                            "metadata": m.get("metadata", {})
                        }
                        for m in cosmos_msgs
                    ]
                    if cosmos_msgs:
                        self.active_threads[thread_id] = datetime.utcnow()
                    self.cosmos_loaded.add(thread_id)
                    # record mapping
                    self.thread_to_project[thread_id] = project_name

            logger.info(f"📥 DB Read: {len(cosmos_msgs)} msgs in {db_latency:.3f}s")
            return len(cosmos_msgs)
        except Exception as e:
            logger.error(f"❌ Load error: {e}")
            with self.lock:
                if thread_id not in self.memory:
                    self.memory[thread_id] = []
            return 0

    def sync_dirty_threads(self) -> int:
        with self.lock:
            dirty = list(self.dirty_threads)
        total = 0
        for tid in dirty:
            proj = None
            with self.lock:
                proj = self.thread_to_project.get(tid)
            total += self._do_flush(tid, proj)
        return total

    def shutdown_flush(self):
        logger.info("🛑 Shutting down storage manager...")
        self.flush_worker_running = False
        if self.flush_thread.is_alive():
            self.flush_thread.join(timeout=5)
        try:
            flushed = self.sync_dirty_threads()
            logger.info(f"✅ Shutdown complete - flushed {flushed} messages")
        except Exception as e:
            logger.error(f"❌ Shutdown flush error: {e}")

    def clear_memory(self, thread_id: str):
        with self.lock:
            self.memory.pop(thread_id, None)
            self.active_threads.pop(thread_id, None)
            self.dirty_threads.discard(thread_id)
            self.cosmos_loaded.discard(thread_id)
            self.thread_to_project.pop(thread_id, None)

    def get_stats(self) -> Dict:
        with self.lock:
            return {
                "active_threads": len(self.active_threads),
                "dirty_threads": len(self.dirty_threads),
                "cached_threads": len(self.cosmos_loaded),
                "total_messages": sum(len(msgs) for msgs in self.memory.values()),
            }

# Initialize storage manager
storage_manager = OptimizedHybridStorageManager()
atexit.register(storage_manager.shutdown_flush)

# ======================================================================
# FastAPI app + CORS
# ======================================================================
app = FastAPI()

ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "https://wonderful-grass-043c527003.azurestaticapps.net",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# init SQL DB
init_db()

# JWT config
SECRET_KEY = os.getenv("SECRET_KEY", "change_this_to_a_strong_random_secret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

# -------------------------------------------------------------------------
# Dependencies / Auth helpers
# -------------------------------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(authorization: str = Header(None), db: Session = Depends(get_db)) -> User:
    if not authorization:
        raise HTTPException(401, "Missing Authorization header")
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Invalid auth format")
    token = authorization.replace("Bearer ", "").strip()
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(401, "Invalid token payload")
        user = db.query(User).filter(User.id == int(user_id)).first()
        if not user:
            raise HTTPException(401, "User not found")
        return user
    except JWTError:
        raise HTTPException(401, "Invalid or expired token")

def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(403, "Admin access required")
    return current_user


# include knowledgebase routes (if exists)
try:
    from knowledgebase import router as kb_router
    app.include_router(kb_router)
except Exception as e:
    import traceback
    traceback.print_exc()
    raise


# token helpers
def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token():
    return secrets.token_urlsafe(32)

# -------------------------------------------------------------------------
# Auth endpoints
# -------------------------------------------------------------------------
@app.post("/login")
def login(data: dict, db: Session = Depends(get_db)):
    email = data.get("email")
    password = data.get("password")
    user = db.query(User).filter(User.email == email).first()
    if not user or user.password != password:
        raise HTTPException(401, "Invalid credentials")
    access_token = create_access_token({"sub": str(user.id), "email": user.email})
    refresh_token_value = create_refresh_token()
    rt = RefreshToken(user_id=user.id, token=refresh_token_value, expires_at=datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
    db.add(rt)
    db.commit()
    return {"access_token": access_token, "refresh_token": refresh_token_value, "user": {"email": user.email, "name": user.name, "role": user.role}}

@app.post("/logout")
def logout(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    storage_manager.sync_dirty_threads()
    db.query(RefreshToken).filter(RefreshToken.user_id == current_user.id).delete()
    db.commit()
    return {"message": "Logged out"}

@app.post("/refresh")
def refresh_token(payload: dict, db: Session = Depends(get_db)):
    refresh_token_value = payload.get("refresh_token")

    rt = db.query(RefreshToken).filter(
        RefreshToken.token == refresh_token_value,
        RefreshToken.expires_at > datetime.utcnow()
    ).first()

    if not rt:
        raise HTTPException(401, "Invalid refresh token")

    user = db.query(User).filter(User.id == rt.user_id).first()
    if not user:
        raise HTTPException(401, "User not found")

    access_token = create_access_token(
        {"sub": str(user.id), "email": user.email}
    )

    return {"access_token": access_token}


# -------------------------------------------------------------------------
# Projects
# -------------------------------------------------------------------------
@app.get("/projects")
def list_projects(email: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return []
    projects = db.query(Project).all()
    return [{
        "project_uuid": p.project_uuid,  # UUID for value
        "display_name": p.name,           # Name for display
        "name": p.name                    # Cosmos partition key
    } for p in projects]

# -------------------------------------------------------------------------
# Conversations endpoints
# -------------------------------------------------------------------------
@app.get("/conversations")
def get_conversations(
    project_id: Optional[str] = None,  # Receives UUID from frontend
    current_user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    start = time.time()
    query = db.query(Conversation).filter(Conversation.user_id == current_user.id)
    
    if project_id:
        project = db.query(Project).filter(Project.project_uuid == project_id).first()
        if project:
            query = query.filter(Conversation.project_id == project.id)
        else:
            return []
    else:
        return []
    
    convos = query.order_by(Conversation.created_at.desc()).all()
    logger.info(f"⏱️  SQL List Conversations: {(time.time() - start):.3f}s")
    
    return [{
        "conversation_uuid": c.conversation_uuid, 
        "topic": c.topic, 
        "created_at": c.created_at.isoformat(), 
        "is_resolved": False, 
        "project_id": project_id  # Return UUID for frontend
    } for c in convos]


class StartConversationRequest(BaseModel):
    project_id: str  # UUID from frontend

@app.post("/conversations/start")
def start_conversation(
    req: StartConversationRequest, 
    user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.project_uuid == req.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail=f"Project not found.")
    
    conv = Conversation(user_id=user.id, project_id=project.id, topic="New Chat")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    
    return {
        "conversation_uuid": conv.conversation_uuid, 
        "project_id": req.project_id,
        "topic": conv.topic, 
        "created_at": conv.created_at
    }


@app.get("/conversations/{conversation_uuid}/messages")
def get_messages(
    conversation_uuid: str, 
    current_user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    convo = db.query(Conversation).filter(
        Conversation.conversation_uuid == conversation_uuid, 
        Conversation.user_id == current_user.id
    ).first()
    if not convo:
        raise HTTPException(404, "Conversation not found")
    
    # ✅ Get project_name for Cosmos partition key
    project_name = convo.project.name if convo.project else None
    
    storage_manager.load_from_cosmos(conversation_uuid, project_name)
    messages = storage_manager.get_messages(conversation_uuid)
    return [{
        "role": m["role"], 
        "content": m["content"], 
        "timestamp": m.get("timestamp", datetime.utcnow().isoformat())
    } for m in messages]


@app.post("/conversations/{conversation_uuid}/messages")
def add_message(
    conversation_uuid: str, 
    payload: dict = Body(...), 
    background: BackgroundTasks = None, 
    current_user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    total_start = time.time()
    logger.info("=" * 60)
    logger.info(f"🚀 REQUEST STARTED: {conversation_uuid}")
    logger.info("=" * 60)

    convo = db.query(Conversation).filter(
        Conversation.conversation_uuid == conversation_uuid, 
        Conversation.user_id == current_user.id
    ).first()
    if not convo:
        raise HTTPException(404, "Conversation not found")
    
    # ✅ Get project_name for Cosmos partition key
    project_name = convo.project.name if convo.project else None

    # ensure history loaded first
    storage_manager.load_from_cosmos(conversation_uuid, project_name)

    user_text = payload.get("text", "")
    save_user_start = time.time()
    storage_manager.add_message(conversation_uuid, "user", user_text, project_name=project_name)
    save_user_time = time.time() - save_user_start

    sys_msg = SystemMessage(content=f"thread_id:{conversation_uuid}")
    user_msg = HumanMessage(content=user_text)
    collected_response = ""
    chunk_count = 0
    first_token_time = None
    ai_start = time.time()

    # ✅ Pass project_name in config for retrieval
    for chunk, meta in chatbot.stream(
        {"messages": [sys_msg, user_msg]},
        config={
            "configurable": {
                "thread_id": conversation_uuid, 
                "project_name": project_name  # ✅ Cosmos partition key
            }
        },
        stream_mode="messages",
    ):
        txt = getattr(chunk, "content", "")
        if txt:
            if first_token_time is None:
                first_token_time = time.time() - ai_start
                logger.info(f"🤖 AI First Token: {first_token_time:.3f}s")
            collected_response += txt
            chunk_count += 1

    ai_total_time = time.time() - ai_start
    logger.info(f"🤖 AI Total Time: {ai_total_time:.3f}s ({chunk_count} chunks)")

    save_ai_start = time.time()
    storage_manager.add_message(conversation_uuid, "assistant", collected_response, project_name=project_name)
    save_ai_time = time.time() - save_ai_start

    storage_manager.queue_flush(conversation_uuid, project_name=project_name, priority=False)

    # Title generation background
    if convo.topic == "New Chat":
        msgs = storage_manager.get_messages(conversation_uuid)
        if len(msgs) >= 4:
            async def update_title_task(conv_uuid, message_history):
                try:
                    text_msgs = [f"{m['role']}: {m['content']}" for m in message_history[:4]]
                    title = await generate_chat_title(text_msgs)
                    new_db = SessionLocal()
                    try:
                        c = new_db.query(Conversation).filter(Conversation.conversation_uuid == conv_uuid).first()
                        if c:
                            c.topic = title
                            new_db.commit()
                            logger.info(f"📝 Title Updated in DB: {title}")
                    finally:
                        new_db.close()
                except Exception as e:
                    logger.error(f"Title gen error: {e}")

            background.add_task(update_title_task, conversation_uuid, msgs)
            db.refresh(convo)

    show_resolved = "Is your issue resolved?" in (collected_response or "")
    total_time = time.time() - total_start
    logger.info("=" * 60)
    logger.info(f"🏁 REQUEST COMPLETE: {total_time:.3f}s total")
    logger.info(f"   - User Msg Save:  {save_user_time:.4f}s (Instant)")
    logger.info(f"   - AI Processing:  {ai_total_time:.3f}s")
    logger.info(f"   - AI Msg Save:    {save_ai_time:.4f}s (Instant)")
    logger.info(f"   - DB Write:       Queued (Background)")
    logger.info("=" * 60 + "\n")

    return {
        "role": "assistant", 
        "content": collected_response, 
        "topic": convo.topic, 
        "timestamp": datetime.utcnow().isoformat(), 
        "show_resolved": show_resolved
    }


@app.post("/conversations/{conversation_uuid}/resolve")
def mark_resolved(
    conversation_uuid: str, 
    background: BackgroundTasks, 
    current_user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    convo = db.query(Conversation).filter(
        Conversation.conversation_uuid == conversation_uuid, 
        Conversation.user_id == current_user.id
    ).first()
    if not convo:
        raise HTTPException(404, "Conversation not found")
    
    # ✅ Get project_name for Cosmos
    project_name = convo.project.name if convo.project else None
    storage_manager._do_flush(conversation_uuid, project_name)
    storage_manager.clear_memory(conversation_uuid)
    return {"success": True, "message": "Conversation resolved"}


@app.delete("/conversations/{conversation_uuid}")
def delete_conversation(
    conversation_uuid: str, 
    background: BackgroundTasks, 
    current_user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    convo = db.query(Conversation).filter(
        Conversation.conversation_uuid == conversation_uuid, 
        Conversation.user_id == current_user.id
    ).first()
    if not convo:
        raise HTTPException(404, "Conversation not found")
    
    # ✅ Get project_name for Cosmos
    project_name = convo.project.name if convo.project else None
    storage_manager._do_flush(conversation_uuid, project_name)
    storage_manager.clear_memory(conversation_uuid)
    db.delete(convo)
    db.commit()
    
    # ✅ Pass project_name to delete_thread for Cosmos partition
    background.add_task(delete_thread, project_name, conversation_uuid)
    return {"status": "success", "message": "Conversation deleted"}


@app.post("/conversations/{conversation_uuid}/feedback")
def submit_feedback(
    conversation_uuid: str, 
    payload: dict = Body(...), 
    current_user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    convo = db.query(Conversation).filter(
        Conversation.conversation_uuid == conversation_uuid, 
        Conversation.user_id == current_user.id
    ).first()
    if not convo:
        raise HTTPException(404, "Conversation not found")
    
    # ✅ Get project_name for Cosmos
    project_name = convo.project.name if convo.project else None
    storage_manager.queue_flush(conversation_uuid, project_name=project_name, priority=True)
    
    existing_feedback = db.query(Feedback).filter(
        Feedback.conversation_uuid == conversation_uuid, 
        Feedback.user_id == current_user.id
    ).first()
    if existing_feedback:
        raise HTTPException(400, "Feedback already submitted")
    
    feedback = Feedback(
        conversation_uuid=conversation_uuid, 
        user_id=current_user.id, 
        rating=payload.get("rating"), 
        comment=payload.get("comment", ""), 
        message_count=payload.get("message_count", 0)
    )
    db.add(feedback)
    db.commit()
    return {"success": True, "message": "Feedback submitted"}
# -------------------------------------------------------------------------
# Health & admin endpoints
# -------------------------------------------------------------------------
@app.get("/health")
def health_check():
    stats = storage_manager.get_stats()
    return {"status": "healthy", "storage": stats, "timestamp": datetime.utcnow().isoformat()}

@app.get("/admin/storage/stats")
def get_storage_stats(admin: User = Depends(get_current_admin_user)):
    return storage_manager.get_stats()

@app.post("/admin/sync-all")
def admin_sync_all(admin: User = Depends(get_current_admin_user)):
    count = storage_manager.sync_dirty_threads()
    return {"success": True, "messages_synced": count}

@app.get("/admin/users")
def get_all_users(admin: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    users = db.query(User).all()
    return {"users": [{"id": u.id, "email": u.email, "name": u.name, "role": u.role} for u in users]}

@app.get("/admin/all-conversations")
def admin_all_conversations(
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    convs = db.query(Conversation).order_by(Conversation.created_at.desc()).all()

    return [
        {
            "conversation_uuid": c.conversation_uuid,
            "topic": c.topic,
            "startDate": c.created_at,
            "isResolved": False,  # SQL model does not track resolution
            "user": c.user.email if c.user else None,
            "project": c.project.name if c.project else None
        }
        for c in convs
    ]


# -------------------------------------------------------------------------
# Analytics (LangSmith) - optional
# -------------------------------------------------------------------------
try:
    from langsmith import Client
except Exception:
    Client = None
    logger.info("LangSmith client not installed; analytics endpoint will return default values")

@app.get("/api/admin/analytics")
def get_analytics(current_user=Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    if Client is None:
        return {"total_requests": 0, "total_tokens": 0, "total_cost": 0, "avg_latency": 0, "daily_trends": []}
    try:
        client = Client()
        project_name = os.getenv("LANGCHAIN_PROJECT", "svayam-chatbot-prod")
        runs = list(client.list_runs(project_name=project_name, is_root=True, start_time=datetime.now() - timedelta(days=7)))
    except Exception as e:
        logger.error(f"LangSmith Connection Error: {e}")
        return {"total_requests": 0, "total_tokens": 0, "total_cost": 0, "avg_latency": 0, "daily_trends": []}

    total_runs = len(runs)
    total_tokens = 0
    total_cost = 0.0
    total_latency = 0.0

    daily_map: DefaultDict[str, Dict] = defaultdict(lambda: {"requests": 0, "tokens": 0, "cost": 0.0, "latency_sum": 0.0})
    for run in runs:
        date_str = run.start_time.strftime("%Y-%m-%d")
        daily_map[date_str]["requests"] += 1
        tokens = getattr(run, "total_tokens", 0) or 0
        total_tokens += tokens
        daily_map[date_str]["tokens"] += tokens
        cost = float(getattr(run, "total_cost", 0) or 0)
        total_cost += cost
        daily_map[date_str]["cost"] += cost
        if run.end_time and run.start_time:
            latency = (run.end_time - run.start_time).total_seconds()
            total_latency += latency
            daily_map[date_str]["latency_sum"] += latency

    avg_latency = (total_latency / total_runs) if total_runs > 0 else 0
    daily_trends = []
    for i in range(6, -1, -1):
        day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        stats = daily_map.get(day, {"requests": 0, "tokens": 0, "cost": 0.0, "latency_sum": 0.0})
        daily_avg_latency = (stats["latency_sum"] / stats["requests"]) if stats["requests"] > 0 else 0
        daily_trends.append({"date": day, "requests": stats["requests"], "tokens": stats["tokens"], "cost": round(stats["cost"], 4), "avg_latency": round(daily_avg_latency, 2)})

    return {"total_requests": total_runs, "total_tokens": total_tokens, "total_cost": round(total_cost, 4), "avg_latency": round(avg_latency, 2), "daily_trends": daily_trends}

# Entrypoint guard for Uvicorn
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=int(os.getenv("PORT", 8000)), reload=True)
    
@app.get("/admin/users")
def admin_list_users(
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    users = db.query(User).all()

    # return in the shape frontend expects
    return {
        "users": [
            {
                "email": u.email,
                "name": u.name,
                "role": u.role
            }
            for u in users
        ]
    }

@app.post("/admin/create")
def admin_create_user(data: dict, admin: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    user = User(
        email=data["email"],
        name=data["name"],     
        password=data["password"],
        role=data["role"]
    )
    db.add(user)
    db.commit()
    return {"message": "User created successfully"}
@app.put("/admin/users/{email}")
def admin_update_user(email: str, data: dict, admin: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(404, "User not found")

    if "name" in data:
        user.name = data["name"]

    if "role" in data:
        user.role = data["role"]

    if "password" in data:
        user.password = data["password"]

    db.commit()
    return {"message": "User updated successfully"}
@app.delete("/admin/users/{email}")
def admin_delete_user(email: str, admin: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(404, "User not found")

    db.delete(user)
    db.commit()
    return {"message": "User deleted successfully"}


# =========================================================
# COSMOS DB CHAT STORAGE (Moved from conversations.py)
# =========================================================

from azure.cosmos import CosmosClient, PartitionKey
from fastapi import APIRouter

cosmos_router = APIRouter(prefix="/api/conversations", tags=["Conversations"])

COSMOS_ENDPOINT = os.getenv("COSMOS_ENDPOINT")
COSMOS_KEY = os.getenv("COSMOS_KEY")
COSMOS_DATABASE = os.getenv("COSMOS_DATABASE", "svayam-db")
COSMOS_CONTAINER = os.getenv("COSMOS_CONTAINER", "conversations")

client = None
if COSMOS_ENDPOINT and COSMOS_KEY:
    try:
        client = CosmosClient(COSMOS_ENDPOINT, COSMOS_KEY, connection_verify=False)
        print("Cosmos connected")
    except Exception as e:
        print("⚠️ Cosmos init failed:", e)

def _get_container():
    if not client:
        raise HTTPException(500, "Cosmos not initialized")
    db = client.create_database_if_not_exists(id=COSMOS_DATABASE)
    container = db.create_container_if_not_exists(
        id=COSMOS_CONTAINER,
        partition_key=PartitionKey(path="/thread_id"),
        offer_throughput=400
    )
    return container

def append_message(project_name, thread_id, role, content, metadata=None, **kwargs):
    """
    New signature: accepts project_name because HybridStorageManager passes it.
    """
    c = _get_container()

    doc = {
        "id": str(uuid.uuid4()),
        "project_name": project_name,
        "thread_id": thread_id,
        "role": role,
        "content": content,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "metadata": metadata or {}
    }

    return c.create_item(body=doc)


def load_messages(project_name, thread_id, **kwargs):
    """
    New signature: HybridStorageManager passes (project_name, thread_id)
    """
    c = _get_container()

    q = """
    SELECT * FROM c 
    WHERE c.thread_id=@tid 
    ORDER BY c.timestamp ASC
    """

    params = [{"name": "@tid", "value": thread_id}]
    return list(c.query_items(q, parameters=params, enable_cross_partition_query=True))


def delete_thread(project_name, thread_id, **kwargs):
    """
    Needed by delete conversation.
    """
    c = _get_container()
    q = "SELECT c.id FROM c WHERE c.thread_id=@tid"
    params = [{"name": "@tid", "value": thread_id}]
    items = list(c.query_items(q, parameters=params, enable_cross_partition_query=True))
    
    for item in items:
        c.delete_item(item["id"], partition_key=thread_id)

def list_recent_threads(limit=20):
    c = _get_container()
    q = f"SELECT TOP {limit*50} c.thread_id, c.timestamp FROM c ORDER BY c.timestamp DESC"
    rows = list(c.query_items(q, enable_cross_partition_query=True))
    seen = set()
    threads = []
    for r in rows:
        tid = r.get("thread_id")
        if tid and tid not in seen:
            seen.add(tid)
            threads.append(tid)
            if len(threads) >= limit:
                break
    return threads

def list_user_threads(email):
    c = _get_container()
    q = "SELECT DISTINCT VALUE c.thread_id FROM c WHERE c.metadata.userEmail=@e"
    return list(c.query_items(q, parameters=[{"name":"@e", "value": email}], enable_cross_partition_query=True))

def map_cosmos_to_frontend(thread_id, messages):
    mapped = []
    topic = "New Conversation"
    user_name = "Unknown"
    start_date = datetime.utcnow().strftime("%Y-%m-%d")
    priority = "Medium"
    category = "General"
    is_resolved = False

    if messages:
        meta = messages[0].get("metadata", {})
        if meta:
            topic = meta.get("topic") or topic
            user_name = meta.get("userName", user_name)
            priority = meta.get("priority", priority)
            category = meta.get("category", category)
            is_resolved = meta.get("isResolved", False)
        raw_ts = messages[0].get("timestamp")
        if raw_ts:
            try:
                dt = datetime.fromisoformat(raw_ts.replace("Z",""))
                start_date = dt.strftime("%Y-%m-%d")
            except:
                pass

    for m in messages:
        mapped.append({
            "sender": "ai" if m.get("role") == "assistant" else "user",
            "text": m.get("content"),
            "timestamp": m.get("timestamp")
        })

    return {
        "id": thread_id,
        "topic": topic,
        "user": user_name,
        "startDate": start_date,
        "priority": priority,
        "category": category,
        "isResolved": is_resolved,
        "messages": mapped
    }
@cosmos_router.get("/")
def admin_conversations(admin: User = Depends(get_current_admin_user)):
    thread_ids = list_recent_threads(20)
    result = []
    for tid in thread_ids:
        msgs = load_messages(tid)
        if msgs:
            result.append(map_cosmos_to_frontend(tid, msgs))
    return result

@cosmos_router.get("/my")
def my_conversations(user: User = Depends(get_current_user)):
    thread_ids = list_user_threads(user.email)
    result = []
    for tid in thread_ids:
        msgs = load_messages(tid)
        if msgs:
            result.append(map_cosmos_to_frontend(tid, msgs))
    return sorted(result, key=lambda x: x["startDate"], reverse=True)

@cosmos_router.post("/create")
def create_conversation(data: dict, user: User = Depends(get_current_user)):
    thread_id = str(uuid.uuid4())
    message = data.get("message", "New Chat Started")
    topic = data.get("topic", "New Inquiry")
    metadata = {
        "topic": topic,
        "userEmail": user.email,
        "userName": user.name,
        "priority": "Medium",
        "category": "General",
        "isResolved": False
    }
    append_message(thread_id, "user", message, metadata)
    return {"message": "created", "id": thread_id}

app.include_router(cosmos_router)

