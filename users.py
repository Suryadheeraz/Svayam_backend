# api/users.py
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
import random
import string

from database import User, get_db
from security import get_current_admin_user, get_password_hash

router = APIRouter(
    prefix="/admin", # All routes in this file will start with /admin
    tags=["Admin"]
)

def generate_password(length=10):
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(random.choice(chars) for _ in range(length))

@router.get("/users")
def get_all_users(db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)):
    """
    Get a list of all users. (Admin Only)
    """
    users = db.query(User).all()
    return {
        "users": [
            {
                "id": f"usr{str(u.id).zfill(3)}",
                "email": u.email,
                "name": u.name,
                "role": u.role,
                "lastLogin": "N/A", # You can add this field later
            }
            for u in users
        ]
    }

@router.post("/create")
def create_user(data: dict, db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)):
    """
    Create a new user. (Admin Only)
    """
    email = data.get("email")
    name = data.get("name")
    role = data.get("role", "user")

    if not email or not name:
        raise HTTPException(status_code=400, detail="Email and name required")

    exists = db.query(User).filter(User.email == email).first()
    if exists:
        raise HTTPException(status_code=400, detail="User already exists")

    # Generate a secure password
    new_password = generate_password()
    hashed_password = get_password_hash(new_password)

    new_user = User(email=email, name=name, hashed_password=hashed_password, role=role)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "message": "User created successfully",
        "email": new_user.email,
        "name": new_user.name,
        "role": new_user.role,
        "generated_password": new_password, # Send the one-time password back
    }

# @router.put("/users/{email}")
# def update_user(email: str, data: dict, db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)):
#     """
#     Update a user's name or role. (Admin Only)
#     """
#     user = db.query(User).filter(User.email == email).first()
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")

#     user.name = data.get("name", user.name)
#     user.role = data.get("role", user.role)
#     db.commit()
#     db.refresh(user)

#     return {
#         "message": f"User {email} updated successfully",
#         "user": {"email": user.email, "name": user.name, "role": user.role}
#     }

@router.put("/users/{email}")
def update_user(email: str, data: dict, db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)):
    """
    Update a user's name or role. (Admin Only)
    Email updates are NOT allowed.
    """
    user = db.query(User).filter(User.email == email).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # --- Check for Self-Role Change ---
    new_role = data.get("role")
    if email == admin.email and new_role and new_role != user.role:
        raise HTTPException(status_code=400, detail="You cannot change your own role")
    # ----------------------------------

    # Update name if provided
    user.name = data.get("name", user.name)
    
    # Update role if provided (and allowed)
    if new_role:
        user.role = new_role
    
    db.commit()
    db.refresh(user)

    return {
        "message": f"User {email} updated successfully",
        "user": {"id": f"usr{str(user.id).zfill(3)}", "email": user.email, "name": user.name, "role": user.role}
    }

@router.delete("/users/{email}")
def delete_user(email: str, db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)):
    """
    Delete a user. (Admin Only)
    """
    # Enforce rule: Admin cannot delete themselves
    if email == admin.email:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")

    if email == "admin@company.com":
        raise HTTPException(status_code=400, detail="Cannot delete default admin user")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db.delete(user)
    db.commit()

    return {"message": f"User {email} deleted successfully"}