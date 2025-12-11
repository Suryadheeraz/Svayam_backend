from database_model import SessionLocal, Project

db = SessionLocal()

projects_to_delete = ["Sewa", "Project2"]   # Old projects

for name in projects_to_delete:
    row = db.query(Project).filter(Project.name == name).first()
    if row:
        print("Deleting:", name)
        db.delete(row)

db.commit()
db.close()
print("Done!")
