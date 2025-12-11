# models.py

import uuid
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional 

# UserLogin model has been removed

class UserCreateAdmin(BaseModel):
    name: str = Field(..., min_length=2)
    email: EmailStr
    role: str = Field(..., min_length=2)

class UserUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2)
    email: Optional[EmailStr] = None
    role: Optional[str] = Field(None, min_length=2)

class UserResponse(BaseModel):
    id: uuid.UUID
    name: str
    email: EmailStr
    role: str
    lastLogin: datetime

    class Config:
        from_attributes = True # Renamed from orm_mode

class UserInDB(BaseModel):
    id: uuid.UUID
    name: str
    email: EmailStr
    role: str
    lastLogin: datetime
    hashed_password: str

# --- ADD THIS NEW MODEL ---
class DeleteItemRequest(BaseModel):
    path: str
    type: str # 'file' or 'folder'

# --- ADD THIS NEW MODEL ---
class RenameItemRequest(BaseModel):
    old_path: str
    new_name: str
    type: str # 'file' or 'folder'