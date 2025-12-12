from database_model import SessionLocal, User

db = SessionLocal()

users = [
    # ("admin@company.com", "Dheeraz", "admin123", "admin"),
    ("kumar@user.com", "Kumar", "kumar123", "user"),
    ("kumar@admin.com", "kumar", "admin123", "admin")
    # ("alice.smith@company.com", "Alice Smith", "pass123", "user")
]

for email, name, pwd, role in users:
    u = User(email=email, name=name, password=pwd, role=role)
    db.add(u)

db.commit()
db.close()

print("Users added!")
