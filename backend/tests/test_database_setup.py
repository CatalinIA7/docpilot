import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import Base
from models import User


def test_database_initializes_and_persists_users():
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()
    try:
        user = User(email="demo@example.com", password_hash="hashed")
        session.add(user)
        session.commit()
        session.refresh(user)

        stored_user = session.query(User).filter_by(email="demo@example.com").first()
        assert stored_user is not None
        assert stored_user.email == "demo@example.com"
    finally:
        session.close()
