"""
Authentication tests — registration, login, and access-control.
"""


class TestRegistration:
    def test_successful_registration_returns_token(self, client):
        resp = client.post(
            "/auth/register",
            json={"email": "new@example.com", "password": "password123"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert body["user"]["email"] == "new@example.com"

    def test_duplicate_registration_returns_409(self, client):
        payload = {"email": "dup@example.com", "password": "password123"}
        client.post("/auth/register", json=payload)
        resp = client.post("/auth/register", json=payload)
        assert resp.status_code == 409
        assert "email" in resp.json()["detail"].lower() or "exists" in resp.json()["detail"].lower()

    def test_registration_normalises_email_to_lowercase(self, client):
        resp = client.post(
            "/auth/register",
            json={"email": "Mixed@Example.COM", "password": "password123"},
        )
        assert resp.status_code == 201
        assert resp.json()["user"]["email"] == "mixed@example.com"

    def test_short_password_is_rejected(self, client):
        resp = client.post(
            "/auth/register",
            json={"email": "short@example.com", "password": "abc"},
        )
        assert resp.status_code == 422


class TestLogin:
    def test_successful_login_returns_token(self, client, registered_user):
        resp = client.post(
            "/auth/login",
            json={"email": registered_user["email"], "password": registered_user["password"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    def test_wrong_password_returns_401(self, client, registered_user):
        resp = client.post(
            "/auth/login",
            json={"email": registered_user["email"], "password": "wrongpassword"},
        )
        assert resp.status_code == 401

    def test_unknown_email_returns_401(self, client):
        resp = client.post(
            "/auth/login",
            json={"email": "nobody@example.com", "password": "password123"},
        )
        assert resp.status_code == 401


class TestAuthProtection:
    def test_list_documents_without_token_returns_401(self, client):
        resp = client.get("/documents")
        assert resp.status_code == 401

    def test_upload_document_without_token_returns_401(self, client):
        resp = client.post("/documents", files={"file": ("x.pdf", b"%PDF-1.4", "application/pdf")})
        assert resp.status_code == 401

    def test_get_me_without_token_returns_401(self, client):
        resp = client.get("/auth/me")
        assert resp.status_code == 401

    def test_get_me_with_valid_token_returns_user(self, client, registered_user, auth_headers):
        resp = client.get("/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["email"] == registered_user["email"]

    def test_invalid_token_returns_401(self, client):
        resp = client.get("/documents", headers={"Authorization": "Bearer not.a.token"})
        assert resp.status_code == 401
