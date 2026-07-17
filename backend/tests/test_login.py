import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import Base, engine
from main import app

client = TestClient(app)


def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_login_returns_token_for_valid_credentials():
    client.post(
        "/auth/register",
        json={"email": "login@example.com", "password": "StrongPass123!"},
    )

    response = client.post(
        "/auth/login",
        json={"email": "login@example.com", "password": "StrongPass123!"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert "access_token" in body
