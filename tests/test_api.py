from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_upload_rejects_unknown_extension():
    resp = client.post("/upload", files={"file": ("evil.exe", b"binary")})
    assert resp.status_code == 400


def test_documents_returns_list():
    resp = client.get("/documents")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_delete_unknown_document_404():
    resp = client.delete("/documents/no-such-id")
    assert resp.status_code == 404


def test_chat_validates_body():
    resp = client.post("/chat", json={})
    assert resp.status_code == 422
