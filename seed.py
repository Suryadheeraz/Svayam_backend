from database_model import SessionLocal, User

db = SessionLocal()

users = [
    ("admin@company.com", "Admin", "admin123", "admin"),
    ("john.doe@company.com", "John Doe", "pass123", "user"),
    ("alice.smith@company.com", "Alice Smith", "pass123", "user"),
]

for email, name, pwd, role in users:
    u = User(email=email, name=name, password=pwd, role=role)
    db.add(u)

db.commit()
db.close()

print("Users added!")
