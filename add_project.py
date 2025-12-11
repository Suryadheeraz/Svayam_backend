# migration_add_projects.py

from sqlalchemy import inspect
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database_model import Base, engine, SessionLocal, User, Conversation, Project, UserProject
import uuid


# ---------------------------------------------------------
# STEP 1 — Add project_id column if missing (SQLite limitation)
# ---------------------------------------------------------
def add_project_column():
    inspector = inspect(engine)
    columns = [col["name"] for col in inspector.get_columns("conversations")]

    if "project_id" not in columns:
        print("➕ Adding project_id column to conversations table...")
        engine.execute("ALTER TABLE conversations ADD COLUMN project_id INTEGER")
    else:
        print("✔ project_id column already exists")


# ---------------------------------------------------------
# STEP 2 — Create new tables: projects, user_projects
# ---------------------------------------------------------
def create_new_tables():
    print("🔧 Creating new tables if missing...")
    Base.metadata.create_all(bind=engine)


# ---------------------------------------------------------
# STEP 3 — Insert SEWA and PROJECT2 if not exist
# ---------------------------------------------------------
def create_projects(db):
    sewa = db.query(Project).filter(Project.name == "Sewa").first()
    project2 = db.query(Project).filter(Project.name == "Project2").first()

    if not sewa:
        print("➕ Creating SEWA project")
        sewa = Project(name="Sewa")
        db.add(sewa)

    if not project2:
        print("➕ Creating Project2")
        project2 = Project(name="Project2")
        db.add(project2)

    db.commit()
    return sewa, project2


# ---------------------------------------------------------
# STEP 4 — Assign all users to both projects
# ---------------------------------------------------------
def assign_users_to_projects(db, sewa, project2):
    users = db.query(User).all()

    for u in users:
        if not db.query(UserProject).filter_by(user_id=u.id, project_id=sewa.id).first():
            db.add(UserProject(user_id=u.id, project_id=sewa.id))
            print(f"✔ Assigned {u.email} → Sewa")

        if not db.query(UserProject).filter_by(user_id=u.id, project_id=project2.id).first():
            db.add(UserProject(user_id=u.id, project_id=project2.id))
            print(f"✔ Assigned {u.email} → Project2")

    db.commit()


# ---------------------------------------------------------
# STEP 5 — Assign all existing conversations to SEWA
# ---------------------------------------------------------
def assign_existing_conversations(db, sewa):
    conversations = db.query(Conversation).all()

    for c in conversations:
        if not c.project_id:
            c.project_id = sewa.id
            print(f"✔ Conversation {c.conversation_uuid} assigned to Sewa")

    db.commit()


# ---------------------------------------------------------
# RUN MIGRATION
# ---------------------------------------------------------
def migrate():
    print("\n🚀 RUNNING MULTI-PROJECT MIGRATION\n")

    add_project_column()
    create_new_tables()

    db = SessionLocal()

    sewa, project2 = create_projects(db)
    assign_users_to_projects(db, sewa, project2)
    assign_existing_conversations(db, sewa)

    print("\n🎉 Migration Completed Successfully!\n")


if __name__ == "__main__":
    migrate()
