from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def student(**changes):
    return {"name": "Asha Demo", "date_of_birth": "2006-04-12", "email": "asha.demo@example.com",
            "course": "Python", "enrollment_date": "2026-01-10", **changes}


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(tmp_path / "students.db"))) as test_client:
        yield test_client


def create(client, **changes):
    response = client.post("/students", json=student(**changes))
    assert response.status_code == 201, response.text
    return response.json()


def test_complete_crud_lifecycle(client):
    response = client.post("/students", json=student())
    assert response.status_code == 201
    saved = response.json()
    path = f"/students/{saved['student_id']}"
    assert response.headers["location"] == path
    assert client.get(path).json() == saved
    assert client.get("/students").json()["total"] == 1
    patched = client.patch(path, json={"course": "Data Science"})
    assert patched.status_code == 200
    assert patched.json()["course"] == "Data Science"
    assert patched.json()["email"] == saved["email"]
    assert patched.json()["created_at"] == saved["created_at"]
    assert patched.json()["updated_at"] >= saved["updated_at"]
    replaced = client.put(path, json=student(name="Asha Updated", course=None))
    assert replaced.status_code == 200
    assert replaced.json()["student_id"] == saved["student_id"]
    assert replaced.json()["course"] is None
    deleted = client.delete(path)
    assert deleted.status_code == 204 and deleted.content == b""
    assert client.get(path).status_code == 404
    assert client.get("/students").json()["total"] == 0


@pytest.mark.parametrize("changes", [
    {"name": " "}, {"name": "x"}, {"name": "x" * 101},
    {"email": "not-an-email"}, {"email": None, "phone": None},
    {"email": " ", "phone": " "}, {"phone": "abc1234567"}, {"phone": "123456"},
    {"phone": "1" * 16}, {"date_of_birth": "2025-02-30"},
    {"date_of_birth": (date.today() + timedelta(days=1)).isoformat()},
    {"enrollment_date": "2000-01-01"}, {"student_id": 999}, {"unexpected": "value"},
])
def test_invalid_create_is_rejected_without_writes(client, changes):
    assert client.post("/students", json=student(**changes)).status_code == 422
    assert client.get("/students").json()["total"] == 0


def test_phone_only_contact_and_whitespace_normalization(client):
    result = create(client, name="  Noor Demo  ", email=None, phone="+1 (202) 555-0100", course=" ")
    assert result["name"] == "Noor Demo"
    assert result["email"] is None and result["course"] is None


def test_duplicate_email_case_insensitive_and_update_rollback(client):
    first = create(client)
    assert client.post("/students", json=student(email="ASHA.DEMO@EXAMPLE.COM")).status_code == 409
    other = create(client, name="Ravi Demo", email="ravi.demo@example.com")
    response = client.patch(f"/students/{other['student_id']}", json={"email": first["email"], "name": "Wrong change"})
    assert response.status_code == 409
    unchanged = client.get(f"/students/{other['student_id']}").json()
    assert unchanged["name"] == "Ravi Demo" and unchanged["email"] == "ravi.demo@example.com"


@pytest.mark.parametrize("patch", [{}, {"name": None}, {"date_of_birth": None}, {"enrollment_date": None},
                                   {"email": None}, {"enrollment_date": "2001-01-01"}, {"student_id": 5}])
def test_invalid_patch_preserves_existing_record(client, patch):
    original = create(client)
    path = f"/students/{original['student_id']}"
    assert client.patch(path, json=patch).status_code == 422
    assert client.get(path).json() == original


def test_clear_optional_fields_but_keep_one_contact(client):
    original = create(client, phone="+1-202-555-0101", address="Fictional address")
    response = client.patch(f"/students/{original['student_id']}", json={"email": None, "address": None})
    assert response.status_code == 200
    assert response.json()["email"] is None and response.json()["address"] is None
    assert response.json()["phone"] is not None


def test_put_requires_complete_record_and_resets_optional_fields(client):
    original = create(client, phone="+1-202-555-0102", address="Fictional address")
    path = f"/students/{original['student_id']}"
    assert client.put(path, json={"course": "Python"}).status_code == 422
    response = client.put(path, json=student())
    assert response.status_code == 200
    assert response.json()["phone"] is None and response.json()["address"] is None


@pytest.mark.parametrize("method,body", [("get", None), ("delete", None), ("patch", {"name": "New Name"}), ("put", student())])
def test_missing_student_returns_404(client, method, body):
    response = client.request(method, "/students/99999", **({"json": body} if body else {}))
    assert response.status_code == 404
    assert response.json() == {"detail": "Student not found."}


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1", "born_after=bad", "email=bad",
                                  "offset=9223372036854775808", "born_after=2010-01-01&born_before=2000-01-01"])
def test_invalid_queries(client, query):
    assert client.get("/students?" + query).status_code == 422


def test_combined_filters_pagination_and_exclusive_dates(client):
    create(client)
    create(client, name="Ravi Demo", email="ravi.demo@example.com", date_of_birth="2005-12-31")
    create(client, name="Noor Demo", email="noor.demo@example.com", course="Java", date_of_birth="2007-01-01")
    result = client.get("/students", params={"name": "DEMO", "course": "python", "born_after": "2005-12-31"}).json()
    assert result["total"] == 1 and result["items"][0]["name"] == "Asha Demo"
    page = client.get("/students", params={"limit": 1, "offset": 1}).json()
    assert page["total"] == 3 and len(page["items"]) == 1 and page["items"][0]["name"] == "Ravi Demo"
    assert client.get("/students?offset=99").json()["items"] == []
    assert client.get("/students", params={"email": "ASHA.DEMO@EXAMPLE.COM"}).json()["total"] == 1
    before = client.get("/students?born_before=2006-04-12").json()
    assert before["total"] == 1 and before["items"][0]["name"] == "Ravi Demo"


def test_sql_injection_and_wildcards_are_literal(client):
    create(client, name="O'Neil Demo")
    for value in ["' OR 1=1 --", "%", "_", "'; DROP TABLE students; --"]:
        assert client.get("/students", params={"name": value}).json()["total"] == 0
    assert client.get("/students", params={"name": "O'Neil"}).json()["total"] == 1
    assert client.get("/students").json()["total"] == 1


def test_persistence_after_application_restart(tmp_path):
    settings = Settings(tmp_path / "persistent.db")
    with TestClient(create_app(settings)) as first:
        saved = create(first)
    assert settings.database_path.is_file()
    with TestClient(create_app(settings)) as second:
        assert second.get(f"/students/{saved['student_id']}").json() == saved
        second.patch(f"/students/{saved['student_id']}", json={"course": "Updated"})
    with TestClient(create_app(settings)) as third:
        assert third.get(f"/students/{saved['student_id']}").json()["course"] == "Updated"
        assert third.delete(f"/students/{saved['student_id']}").status_code == 204
    with TestClient(create_app(settings)) as fourth:
        assert fourth.get("/students").json()["total"] == 0


def test_parallel_partial_updates_preserve_distinct_fields(client):
    saved = create(client)
    path = f"/students/{saved['student_id']}"
    changes = [{"course": "Concurrent course"}, {"address": "Concurrent address"}, {"phone": "+1-202-555-0103"}]
    with ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(pool.map(lambda patch: client.patch(path, json=patch), changes))
    assert all(r.status_code == 200 for r in responses)
    result = client.get(path).json()
    for patch in changes:
        for key, value in patch.items():
            assert result[key] == value


def test_health_docs_and_openapi(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/docs").status_code == 200
    paths = client.get("/openapi.json").json()["paths"]
    assert {"get", "post"} <= set(paths["/students"])
    assert {"get", "put", "patch", "delete"} <= set(paths["/students/{student_id}"])


def test_invalid_ids(client):
    for value in ("0", "-1", "not-a-number", "9223372036854775808"):
        assert client.get("/students/" + value).status_code == 422


def test_assistant_count_year_filter_and_privacy(client):
    create(client)
    create(client, name="Ravi Demo", email="ravi.demo@example.com", date_of_birth="2005-12-31")
    count = client.post("/ask", json={"question": "How many students are there?"}).json()
    assert count["answer"] == "There are 2 students in the database."
    result = client.post("/ask", json={"question": "List students born after 2005."}).json()
    assert result["total_matches"] == 1 and result["records"][0]["name"] == "Asha Demo"
    assert set(result["records"][0]) == {"student_id", "name", "date_of_birth", "course"}
    assert result["filters"] == {"born_after": "2005-12-31"}
    assert client.post("/ask", json={"question": "List students in course Python"}).json()["total_matches"] == 2


def test_assistant_empty_unknown_disabled_and_bounded_results(client):
    assert client.post("/ask", json={"question": "List students"}).json()["answer"].startswith("No students")
    assert client.post("/ask", json={"question": "DROP TABLE students"}).status_code == 422
    assert client.post("/ask", json={"question": "List students born after 9999"}).status_code == 422
    assert client.post("/ask", json={"question": "Count students", "use_ai": True}).status_code == 503
    for i in range(51):
        create(client, email=f"demo{i}@example.com")
    result = client.post("/ask", json={"question": "List students"}).json()
    assert result["total_matches"] == 51 and result["shown"] == 50 and result["truncated"] is True
    assert "first 50" in result["answer"]


@pytest.mark.parametrize("outcome", ["success", "unreachable", "malformed"])
def test_optional_ollama_contract_and_failure_handling(tmp_path, monkeypatch, outcome):
    original_client = httpx.Client
    captured = []

    def handler(request):
        import json
        captured.append(json.loads(request.content))
        assert str(request.url) == "http://127.0.0.1:11434/api/chat"
        if outcome == "unreachable":
            raise httpx.ConnectError("not running", request=request)
        if outcome == "malformed":
            return httpx.Response(200, json={"oops": True})
        return httpx.Response(200, json={"message": {"content": "One matching student is shown."}})

    with TestClient(create_app(Settings(tmp_path / "ai.db", ollama_enabled=True))) as client:
        create(client)
        monkeypatch.setattr(httpx, "Client", lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs))
        result = client.post("/ask", json={"question": "List students", "use_ai": True})
        assert captured and captured[0]["stream"] is False
        assert "asha.demo@example.com" not in str(captured)
        if outcome == "success":
            assert result.status_code == 200
            assert result.json()["source"] == "sqlite+ollama"
            assert result.json()["total_matches"] == 1
            assert "Asha Demo" in result.json()["answer"]
        else:
            assert result.status_code == 503
        assert client.get("/students").json()["total"] == 1
