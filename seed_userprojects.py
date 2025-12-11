from database_model import SessionLocal, User, Project, UserProject

db = SessionLocal()

# Fetch users
users = db.query(User).all()

# Fetch projects
projects = db.query(Project).all()

for user in users:
    for project in projects:
        # Check if mapping already exists
        existing = db.query(UserProject).filter_by(
            user_id=user.id, 
            project_id=project.id
        ).first()

        if not existing:
            print(f"Assigning {user.email} → {project.name}")
            db.add(UserProject(user_id=user.id, project_id=project.id))
        else:
            print(f"{user.email} already assigned to {project.name}")

db.commit()
db.close()

print("User → Project assignments completed!")
