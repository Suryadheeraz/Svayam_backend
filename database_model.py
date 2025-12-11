# database.py
from sqlalchemy import (
    create_engine, Column, String, Integer, ForeignKey, DateTime, Text
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime
import uuid

DATABASE_URL = "sqlite:///./users.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# ---------------------------------------------------------
# USER TABLE
# ---------------------------------------------------------
class User(Base):
    __tablename__ = "users"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    name = Column(String)
    password = Column(String)
    role = Column(String)

    # Relationship: One user → Many conversations
    conversations = relationship("Conversation", back_populates="user")
    user_projects = relationship("UserProject", back_populates="user")

# ---------------------------------------------------------
# PROJECT TABLE (NEW)
# ---------------------------------------------------------
class Project(Base):
    __tablename__ = "projects"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    project_uuid = Column(String, unique=True, index=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)

    conversations = relationship("Conversation", back_populates="project")

# ---------------------------------------------------------
# USER-PROJECT TABLE (NEW)
# ---------------------------------------------------------
class UserProject(Base):
    __tablename__ = "user_projects"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    project_id = Column(Integer, ForeignKey("projects.id"))

    # Relationships
    user = relationship("User", back_populates="user_projects")
    project = relationship("Project")


# ---------------------------------------------------------
# CONVERSATION TABLE
# ---------------------------------------------------------
class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = {"extend_existing": True}

    conversation_uuid = Column(
        String,
        primary_key=True,
        unique=True,
        index=True,
        default=lambda: str(uuid.uuid4())
    )

    user_id = Column(Integer, ForeignKey("users.id"))
    topic = Column(String, default="New Chat")
    created_at = Column(DateTime, default=datetime.utcnow)
    project_id = Column(Integer, ForeignKey("projects.id"))


    # Relationship
    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete")
    project = relationship("Project", back_populates="conversations")


# ---------------------------------------------------------
# MESSAGE TABLE
# ---------------------------------------------------------
class Message(Base):
    __tablename__ = "messages"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    conversation_uuid = Column(String, ForeignKey("conversations.conversation_uuid"))
    sender = Column(String)  # "user" or "assistant"
    text = Column(Text)      # text is better as Text type
    timestamp = Column(DateTime, default=datetime.utcnow)

    # Relationship
    conversation = relationship("Conversation", back_populates="messages")


# ---------------------------------------------------------
# REFRESH TOKEN TABLE
# ---------------------------------------------------------
class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String, unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

# ---------------------------------------------------------
# FEEDBACK TABLE (NEW!)
# ---------------------------------------------------------
class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    conversation_uuid = Column(String, ForeignKey("conversations.conversation_uuid"))
    user_id = Column(Integer, ForeignKey("users.id"))
    rating = Column(Integer)  # 1-5 stars
    comment = Column(Text, nullable=True)
    message_count = Column(Integer, default=0)
    timestamp = Column(DateTime, default=datetime.utcnow)

    # Relationships
    conversation = relationship("Conversation")
    user = relationship("User")


# ---------------------------------------------------------
# CREATE TABLES
# ---------------------------------------------------------
def init_db():
    Base.metadata.create_all(bind=engine)
