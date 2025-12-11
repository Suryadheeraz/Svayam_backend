from database_model import engine, Feedback

# Create only the new feedback table
Feedback.__table__.create(bind=engine, checkfirst=True)

print("✅ Feedback table created successfully!")