# Demonstration and viva preparation

## Five-minute walkthrough

1. **Purpose (30 seconds):** Explain that the API manages student records and stores them in a local SQLite file.
2. **Create (45 seconds):** Open `/docs`, expand `POST /students`, choose Try it out, enter fictional values, and execute. Explain the 201 status, generated ID and timestamps.
3. **Read and filter (45 seconds):** Retrieve that ID. List students with a course filter. Explain the difference between one object and the paginated collection.
4. **Update (45 seconds):** PATCH only the course. Show that the name and contact remain unchanged. Explain that PUT replaces the full editable record.
5. **Validation (45 seconds):** Try a future birth date, no contact details, and a duplicate email. Explain 422 versus 409.
6. **Persistence and delete (45 seconds):** Restart the server without changing the database path, retrieve the record, delete it, then show the 404 response.
7. **Tests and bonus (45 seconds):** Show the test results and `/ask` count response. Describe Ollama as optional and distinguish deterministic data from generated commentary.

Use a student you created for the demonstration when deleting. The seed script is repeatable, but it skips any sample whose email already exists.

## Questions and answers

**1. What does CRUD mean?** Create inserts a record, Read retrieves it, Update changes it, and Delete removes it. The API maps these to POST, GET, PUT/PATCH and DELETE.

**2. Why FastAPI?** It provides route handling, request parsing, integration with Pydantic validation, response serialization and generated OpenAPI documentation. The Swagger interface makes a separate frontend unnecessary for this backend assignment.

**3. Why SQLite?** It persists relational data in a local file without a database server. Its transactions and constraints suit a small single-host demonstration.

**4. How is the ID unique?** SQLite assigns an integer primary key with AUTOINCREMENT. The request schema excludes student_id, so a caller cannot override it. Deleted IDs are not reused by this schema.

**5. How are contacts validated?** The complete record must have an email or phone. Emails are syntax-checked and lowercased; phone formatting and digit counts are validated. An optional field may be null only if the record still satisfies the contact rule.

**6. What is PUT versus PATCH?** PUT supplies a replacement record; omitted optional values reset. PATCH changes only fields present in the request. PATCH validates the merged record before committing.

**7. How do you prevent SQL injection?** Request values are passed separately as bound parameters. The application constructs only fixed SQL fragments from known filters. Student names and course values are never concatenated into SQL.

**8. Why validate in both Python and SQLite?** Python provides useful errors and rules involving dates and formats. Database constraints preserve key invariants such as uniqueness and contact presence even if an internal operation is incorrect.

**9. What happens on failure?** The connection context rolls back a failed write. Missing IDs return 404, duplicate emails 409 and invalid input 422. Operational database failures return a generic 503 without exposing file paths.

**10. What protects a PATCH from concurrent requests?** A BEGIN IMMEDIATE transaction reserves the writer before reading the old row. The operation merges, validates and updates within that transaction, so unrelated changes are not lost through stale reads.

**11. How did you verify persistence?** Tests recreate the application against the same file. The live verifier additionally stops and starts four separate Uvicorn processes and checks persistence of creation, update and deletion.

**12. How does pagination work?** The API computes the filtered total, then retrieves an ordered slice using LIMIT and OFFSET. Both reads share a transaction so the total and page describe the same snapshot.

**13. Can the model execute SQL?** No. The backend recognizes a small documented set of question patterns and retrieves records with parameterized queries. Ollama receives only selected evidence and has no database tools.

**14. Is every AI sentence guaranteed correct?** No. The main answer and counts are deterministic SQLite facts. The optional ai_explanation is supplementary text that should be checked against the returned evidence.

**15. What would you improve for production?** Add authenticated roles, authorization, auditing, backups, migration management and deployment monitoring; evaluate a server database for heavier concurrency. Keep real data out of demo fixtures.

## Explain the files

- `app/main.py`: application factory, lifecycle, routes and error handling.
- `app/schemas.py`: request/response types and validation rules.
- `app/database.py`: schema, transactions, queries and record persistence.
- `app/assistant.py`: constrained question parsing, retrieval and optional Ollama request.
- `app/config.py`: environment-based configuration.
- `tests/test_api.py`: behavior and failure-case verification with temporary databases.
- `scripts/`: example import, live demonstration and restart verification.

## Honest validation notes

The recorded environment used Python 3.14.6 on Windows. All 48 automated tests passed. The Ollama HTTP contract was mocked in tests; no local model inference was measured. The README documents that limit. Read and run the project before presenting it; do not claim a test or demonstration you have not personally reproduced.
