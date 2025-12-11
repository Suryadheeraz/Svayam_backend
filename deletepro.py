from database_model import SessionLocal, Project

db = SessionLocal()

projects_to_delete = ["Sewa", "Project2"]  # old projects you want to remove

for name in projects_to_delete:
    proj = db.query(Project).filter(Project.name == name).first()
    if proj:
        db.delete(proj)
        print(f"Deleted project: {name}")
    else:
        print(f"Project not found: {name}")

db.commit()
db.close()

print("Cleanup complete.")
