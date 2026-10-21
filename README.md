# Student Records API

**EWB Python Backend Development Internship** | FastAPI + SQLite | Version 1.0.0

A complete backend for creating, listing, filtering, updating and deleting student records. Records live in a SQLite file and survive server restarts. Interactive Swagger documentation provides a browser interface for trying every endpoint.

**Report cover fields for name, intern ID and college are intentionally blank.** Fill these before submission. All sample students are fictional and all sample email addresses use `example.com`.

## 1. Prerequisites

- Python **3.14** is the verified version; Python 3.11 or newer is intended to work.
- A terminal and internet access for the initial package installation.
- No separate database server, API key or paid service is required.
- Ollama is optional. The core project works without it.

## 2. Install and start

Open a terminal inside the extracted `ewb-student-crud` folder.

### Windows PowerShell

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

If `py` is unavailable, use `python` for the first command. Activation is unnecessary, so these commands do not depend on PowerShell's script execution policy.

### macOS / Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000/docs** for Swagger UI or **http://127.0.0.1:8000/redoc** for the API reference. The health check is **http://127.0.0.1:8000/health**. Stop the server with `Ctrl+C`.

`requirements.txt` contains runtime dependencies; `requirements-dev.txt` adds pytest. `requirements-lock.txt` captures all dependency versions from the verified environment. Install the lock file instead of the dev file to reproduce those versions exactly. Swagger UI loads its UI assets from a CDN; when offline, use the JSON API, `/openapi.json`, or the demo script.

## 3. Quick demonstration

Keep the server running. Open another terminal in the project folder:

```powershell
.\.venv\Scripts\python.exe -m scripts.seed
.\.venv\Scripts\python.exe -m scripts.demo
```

On macOS/Linux replace the executable with `.venv/bin/python`.

- `seed` inserts five fictional students through the API. Repeating it skips existing sample emails.
- `demo` runs real HTTP requests for create, read, filter, PATCH, PUT, duplicate-email rejection, invalid-input rejection, count and delete. It cleans up only the record it creates.
- `examples/requests.http` contains requests for the VS Code REST Client extension.
- `examples/postman_collection.json` can be imported into Postman; run its requests in order.
- `docs/live-demo.json` records actual requests and responses from verification, including server-generated IDs and timestamps.

## 4. API reference

| Method | Route | Success | Behavior |
|---|---|---:|---|
| GET | `/health` | 200 | Check application and database access |
| POST | `/students` | 201 | Create and return a student; `Location` header points to the new resource |
| GET | `/students` | 200 | Return a filtered, paginated collection |
| GET | `/students/{student_id}` | 200 | Retrieve one student |
| PUT | `/students/{student_id}` | 200 | Replace all editable fields |
| PATCH | `/students/{student_id}` | 200 | Update only supplied fields |
| DELETE | `/students/{student_id}` | 204 | Delete a student; empty response body |
| POST | `/ask` | 200 | Read-only questions; optional Ollama commentary |

### Create request

```json
{
  "name": "Asha Demo",
  "date_of_birth": "2006-04-12",
  "email": "asha.demo@example.com",
  "course": "Python",
  "address": "Fictional Campus, Block A",
  "enrollment_date": "2026-01-10"
}
```

The response includes these values plus `student_id`, `phone`, `created_at` and `updated_at`. IDs are database-assigned positive integers and cannot be supplied or edited. Dates use `YYYY-MM-DD`; timestamps use UTC ISO 8601.

### Filtering and pagination

```text
GET /students?name=asha
GET /students?course=Python&limit=10&offset=0
GET /students?email=asha.demo%40example.com
GET /students?born_after=2005-12-31&born_before=2007-01-01
```

Filters combine with AND. Name is a literal substring; course and email are exact matches. SQLite's built-in case folding is ASCII-oriented. Date boundaries are exclusive. `born_after=2005-12-31` means born in 2006 or later. Results are ordered by ascending student ID. `limit` defaults to 20 and is restricted to 1-100; `offset` defaults to 0 and cannot be negative.

The collection has the shape `{"total": 5, "limit": 20, "offset": 0, "items": [...]}`. `total` is the full number matching the filters, before pagination. An empty collection returns 200 with `items: []`.

### Update behavior

`PATCH /students/1` with `{"course": "Data Science"}` preserves every omitted field. Explicit `null` clears an optional field, provided at least one valid contact remains. Empty PATCH bodies are rejected. Name, date of birth and enrollment date cannot be cleared.

`PUT /students/1` requires the same full body as creation. Omitted optional fields become null and omitted enrollment date becomes today. IDs and creation timestamps remain unchanged. Neither update route creates a missing student.

### Validation and errors

- Name: trimmed, 2-100 characters.
- Birth date: valid date, not in the future.
- Email or phone: at least one must be supplied. Email is syntax-validated and lowercased; duplicate email is rejected case-insensitively. This is not a deliverability check.
- Phone: 7-15 digits, with optional leading `+`, spaces, hyphens and parentheses; at most 25 characters overall. Phone numbers are not unique.
- Course: up to 100 characters; address: up to 300. Blank optional strings become null.
- Enrollment date defaults to today and cannot precede birth date. Future enrollment is permitted.
- Unknown body fields are rejected to catch spelling errors.
- **404:** missing student. **409:** duplicate email. **422:** invalid input, query or unsupported assistant question. **503:** unavailable database or requested Ollama service.

Errors use a top-level `detail` field. Validation details may be a list; resource errors use a short message. A failed update rolls back and preserves the previous record.

## 5. Storage and architecture

```text
Swagger / HTTP client
        |
        v
FastAPI routes (app/main.py)
        |
        +--> Pydantic input validation (app/schemas.py)
        |
        v
SQLite repository (app/database.py)
        |
        v
data/students.db
```

The schema is created automatically at startup. The database contains one `students` table with a primary key, unique email constraint, contact/date checks and indexes on course and birth date. The default database location is based on the project folder, independent of the terminal's current folder.

Each operation opens and closes its own connection. Writes commit on success and roll back on error. `BEGIN IMMEDIATE` protects the read-merge-write PATCH operation against lost updates; list count and page share one read transaction. WAL mode improves reader/writer concurrency. SQL values use bound placeholders, including filters. No request or model response is executed as SQL.

```text
app/                         API, schemas, database, optional assistant
tests/test_api.py            Automated behavioral tests
scripts/seed.py              Repeatable fictional sample import
scripts/demo.py              Live API walkthrough
scripts/verify_live.py       Isolated HTTP and server-restart verification
examples/                   Fictional JSON, HTTP requests and Postman collection
docs/                       Report source, API schema, evidence and viva notes
output/pdf/                 Printable project report
requirements*.txt           Dependencies and verified version lock
README.md                   Installation, API, tests and submission guide
```

### Configuration

Set environment variables before starting Uvicorn. `.env.example` is documentation and is **not** loaded automatically.

```powershell
$env:STUDENT_DB_PATH = "C:\my-demo-data\students.db"
$env:OLLAMA_ENABLED = "1"
$env:OLLAMA_MODEL = "llama3.2:1b"
```

For Bash, use `export STUDENT_DB_PATH=/your/path/students.db`, and equivalent `export` commands for Ollama. Use a writable path on a local disk. To reset the demo, stop the server and remove the configured SQLite file and any matching `-wal` / `-shm` files. This deletes its records.

## 6. Run tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m scripts.verify_live
```

The automated tests use isolated temporary databases. The live verifier starts four local Uvicorn processes in sequence, checks HTTP CRUD and confirms that creation, update and deletion each survive a process restart. It writes evidence under `docs/` and never opens the normal project database.

The verified run passed **48 tests**. Evidence is recorded in `docs/test-results.txt` and `docs/live-verification.json`. The current Starlette release emits a deprecation warning for its HTTPX-based TestClient; the requests and tests still pass. The optional Ollama success/error paths are tested with an HTTP mock. An actual local model was not run during verification.

## 7. Optional Ollama extension

`POST /ask` works without a model using these documented patterns:

```json
{"question": "How many students are there?", "use_ai": false}
```

Other supported patterns are `List students`, `List students born after 2005`, and `List students in course Python` (or another exact course). The parser accepts `show` instead of `list` and common count variants. Unsupported questions receive 422 rather than an invented answer.

For local generated commentary:

1. Install Ollama from its official site and start it locally (`ollama serve` if it is not already running).
2. Run `ollama pull llama3.2:1b`.
3. Set `OLLAMA_ENABLED=1` before starting or restarting the API.
4. Send `{"question": "List students born after 2005", "use_ai": true}` to `/ask`.

Retrieval uses fixed, parameterized backend queries and returns at most 50 records plus the exact total. Names, IDs, birth dates and courses form the evidence; email, phone and address are excluded from the model prompt. Ollama is contacted only at `127.0.0.1:11434`. It receives the retrieved facts but has no database connection or tool access.

`answer`, `total_matches`, `filters` and `records` are authoritative SQLite results. `ai_explanation` is separate, supplementary model text and may contain mistakes; check it against the evidence. A model failure returns 503 with instructions to use `use_ai=false`. The core CRUD routes never need Ollama.

## 8. Scope and limitations

This is a local internship demonstration using fictional data. It has no authentication or user roles and should remain on loopback for the demo. A production student system would require access control, transport security, audit logging, backup policies and a privacy review. SQLite is appropriate for this small single-host project; large deployments need a different database strategy. No real personal information, password, secret or generated database is included in the submission package.

## 9. Assignment coverage and submission

| Assignment requirement | Delivered evidence |
|---|---|
| Python, FastAPI, SQLite | `app/`, `requirements.txt` |
| Create, read, update, delete | Six documented CRUD operations and live transcript |
| Student ID, name, DOB, contact | Validated schema with database-assigned ID |
| Filtering / individual profiles | Query filters and ID lookup |
| Persistent storage | Application and process-restart tests |
| Input validation / missing records | 422 validation, 404 responses and rollback tests |
| Reproducible README and dependencies | This file, requirements and exact lock |
| Sample requests | HTTP file, Postman collection and recorded responses |
| Optional local AI | Bounded retrieval plus Ollama commentary |

Before submission:

1. Fill the report cover's blank personal-information lines.
2. Follow the quick demonstration and read `docs/VIVA_AND_DEMO.md` so you can explain the code.
3. Create a GitHub repository and upload the project folder's contents, preserving subfolders. The ZIP excludes `.venv`, generated databases, caches and secrets. If using Git locally, `.gitignore` excludes these too.
4. Confirm README, source code, requirements, tests, examples and the report are visible. If the repository is private, grant the trainer access.
5. Submit the repository link through the channel announced by your EWB trainer. This package does not itself publish or submit anything.

## 10. References

- [FastAPI documentation and testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [Python SQLite documentation](https://docs.python.org/3/library/sqlite3.html)
- [Pydantic documentation](https://docs.pydantic.dev/latest/)
- [Ollama chat API](https://docs.ollama.com/api/chat)
- EWB internship assignment supplied with the project brief.
