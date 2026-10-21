"""FastAPI entry point: python -m uvicorn app.main:app --reload."""

import sqlite3
from contextlib import asynccontextmanager
from datetime import date
from typing import Annotated

from fastapi import FastAPI, HTTPException, Path, Query, Response
from fastapi.responses import JSONResponse
from pydantic import EmailStr, ValidationError

from .assistant import add_ollama_commentary, retrieve
from .config import Settings
from .database import Database, DuplicateEmail, StudentNotFound
from .schemas import AskRequest, AskResponse, StudentCreate, StudentOut, StudentPage, StudentPatch

StudentId = Annotated[int, Path(ge=1, le=9223372036854775807, description="Database-assigned positive student ID")]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    db = Database(settings.database_path)

    @asynccontextmanager
    async def lifespan(application):
        db.initialize()
        yield

    application = FastAPI(
        title="EWB Student Records API", version="1.0.0",
        description="Student CRUD with persistent SQLite storage. Use fictional data for this local internship demo. "
                    "POST creates, GET retrieves, PUT replaces, PATCH partially updates, and DELETE removes a record.",
        lifespan=lifespan,
    )
    application.state.db = db

    @application.exception_handler(StudentNotFound)
    async def not_found(request, exc):
        return JSONResponse(status_code=404, content={"detail": "Student not found."})

    @application.exception_handler(DuplicateEmail)
    async def duplicate(request, exc):
        return JSONResponse(status_code=409, content={"detail": "A student with this email already exists."})

    @application.exception_handler(sqlite3.OperationalError)
    async def database_error(request, exc):
        return JSONResponse(status_code=503, content={"detail": "Database temporarily unavailable. Please retry."})

    @application.get("/", tags=["Service"])
    def index():
        return {"service": "EWB Student Records API", "version": "1.0.0", "docs": "/docs", "health": "/health"}

    @application.get("/health", tags=["Service"])
    def health():
        db.health()
        return {"status": "ok", "database": "sqlite"}

    @application.post("/students", response_model=StudentOut, status_code=201, tags=["Students"],
                      responses={409: {"description": "Duplicate email"}})
    def create_student(student: StudentCreate, response: Response):
        saved = db.create(student)
        response.headers["Location"] = f"/students/{saved['student_id']}"
        return saved

    @application.get("/students", response_model=StudentPage, tags=["Students"])
    def list_students(
        name: Annotated[str | None, Query(min_length=1, max_length=100, description="Literal name substring; ASCII case-insensitive")] = None,
        course: Annotated[str | None, Query(min_length=1, max_length=100, description="Exact course; ASCII case-insensitive")] = None,
        email: EmailStr | None = None,
        born_after: Annotated[date | None, Query(description="Exclusive lower date-of-birth boundary")] = None,
        born_before: Annotated[date | None, Query(description="Exclusive upper date-of-birth boundary")] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0, le=9223372036854775807)] = 0,
    ):
        if born_after and born_before and born_after >= born_before:
            raise HTTPException(422, "born_after must be earlier than born_before.")
        return db.list(name=name, course=course, email=email, born_after=born_after,
                       born_before=born_before, limit=limit, offset=offset)

    @application.get("/students/{student_id}", response_model=StudentOut, tags=["Students"],
                     responses={404: {"description": "Student not found"}})
    def get_student(student_id: StudentId):
        return db.get(student_id)

    @application.put("/students/{student_id}", response_model=StudentOut, tags=["Students"],
                     summary="Replace a student", description="Replace all editable fields. Omitted optional fields reset to defaults. "
                     "Student ID and creation timestamp are retained.")
    def replace_student(student_id: StudentId, student: StudentCreate):
        return db.update(student_id, student.model_dump(mode="json"), replace=True)

    @application.patch("/students/{student_id}", response_model=StudentOut, tags=["Students"],
                       summary="Partially update a student")
    def patch_student(student_id: StudentId, student: StudentPatch):
        try:
            return db.update(student_id, student.model_dump(mode="json", exclude_unset=True))
        except ValidationError as exc:
            # A field can be individually valid but violate a merged-record rule.
            raise HTTPException(422, detail=exc.errors(include_context=False, include_url=False)) from exc

    @application.delete("/students/{student_id}", status_code=204, tags=["Students"],
                        responses={404: {"description": "Student not found"}})
    def delete_student(student_id: StudentId):
        db.delete(student_id)
        return Response(status_code=204)

    @application.post("/ask", response_model=AskResponse, tags=["Optional assistant"],
                      description="Read-only questions using documented patterns. The answer is computed from SQLite. "
                      "With use_ai=true, optional Ollama commentary appears separately in ai_explanation; it may be inaccurate.")
    def ask(request: AskRequest):
        evidence = retrieve(db, request.question)
        return add_ollama_commentary(evidence, settings) if request.use_ai else evidence

    return application


app = create_app()
