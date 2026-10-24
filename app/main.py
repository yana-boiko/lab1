"""CRUD-сервіс для результатів лабораторних аналізів"""
import os
from contextlib import asynccontextmanager
from datetime import date
from typing import Annotated
from decimal import Decimal

from fastapi import FastAPI, Path, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationInfo, field_validator

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "labdb")
DB_USER = os.environ.get("DB_USER", "lab")
DB_PASSWORD = os.environ["DB_PASSWORD"]

CONNINFO = (
    f"host={DB_HOST} port={DB_PORT} dbname={DB_NAME} "
    f"user={DB_USER} password={DB_PASSWORD} connect_timeout=3"
)

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


pool = ConnectionPool(CONNINFO, min_size=1, max_size=10, open=False, kwargs={"row_factory": dict_row})


@asynccontextmanager
async def lifespan(_app: FastAPI):
    pool.open(wait=False)
    yield
    pool.close()


app = FastAPI(title="Lab results service", lifespan=lifespan)

# Замість float тепер Decimal, узгоджений з колонкою NUMERIC(14, 4).
# Значення з більш ніж 4 знаками після коми або більш ніж 10 цілими цифрами
# отримують 400 з назвою поля, а не 500 від бази.
def _reject_strings(v):
    if isinstance(v, str):
        raise ValueError("must be a number, not a string")
    return v
Number = Annotated[Decimal, BeforeValidator(_reject_strings), Field(max_digits=14, decimal_places=4)]

Code = Annotated[str, Field(min_length=1, max_length=32)]
ItemId = Annotated[int, Path(ge=1, le=2**63 - 1)]  # діапазон BIGINT


class LabResultIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_code: Code
    test_code: Code
    value: Number
    unit: Annotated[str, Field(min_length=1, max_length=20)]
    ref_low: Number
    ref_high: Number
    sample_date: date

    @field_validator("ref_high")
    @classmethod
    def check_reference_range(cls, ref_high, info: ValidationInfo):
        ref_low = info.data.get("ref_low")
        if ref_low is not None and ref_low >= ref_high:
            raise ValueError(f"ref_low ({ref_low}) must be less than ref_high ({ref_high})")
        return ref_high


class LabResultOut(BaseModel):
    id: int
    patient_code: str
    test_code: str
    value: float
    unit: str
    ref_low: float
    ref_high: float
    sample_date: date


class LabResultList(BaseModel):
    items: list[LabResultOut]
    total: int
    limit: int
    offset: int

@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError):
    errors = []
    for err in exc.errors():
        loc = [str(p) for p in err["loc"] if p not in ("body", "query", "path")]
        field = ".".join(loc) if loc and err["type"] != "json_invalid" else "body"
        msg = err["msg"].removeprefix("Value error, ")
        errors.append({"field": field, "error": msg})
    return JSONResponse(status_code=400, content={"detail": "validation error", "errors": errors})


def not_found(item_id: int) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": f"lab result {item_id} not found"})


COLUMNS = "id, patient_code, test_code, value, unit, ref_low, ref_high, sample_date"


@app.post("/lab-results", status_code=201, response_model=LabResultOut)
def create_lab_result(body: LabResultIn):
    with pool.connection() as conn:
        row = conn.execute(
            f"""INSERT INTO lab_results (patient_code, test_code, value, unit, ref_low, ref_high, sample_date)
                VALUES (%(patient_code)s, %(test_code)s, %(value)s, %(unit)s, %(ref_low)s, %(ref_high)s, %(sample_date)s)
                RETURNING {COLUMNS}""",
            body.model_dump(),
        ).fetchone()
    return row


@app.get("/lab-results", response_model=LabResultList)
def list_lab_results(
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
    test_code: Annotated[str | None, Query(min_length=1, max_length=32)] = None,
):
    where, params = "", {"limit": limit, "offset": offset}
    if test_code is not None:
        where = "WHERE test_code = %(test_code)s"
        params["test_code"] = test_code
    with pool.connection() as conn:
        total = conn.execute(f"SELECT count(*) AS n FROM lab_results {where}", params).fetchone()["n"]
        items = conn.execute(
            f"SELECT {COLUMNS} FROM lab_results {where} ORDER BY id LIMIT %(limit)s OFFSET %(offset)s",
            params,
        ).fetchall()
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@app.get("/lab-results/{item_id}", response_model=LabResultOut)
def get_lab_result(item_id: ItemId):
    with pool.connection() as conn:
        row = conn.execute(f"SELECT {COLUMNS} FROM lab_results WHERE id = %s", (item_id,)).fetchone()
    return row if row else not_found(item_id)


@app.put("/lab-results/{item_id}", response_model=LabResultOut)
def replace_lab_result(item_id: ItemId, body: LabResultIn):
    with pool.connection() as conn:
        row = conn.execute(
            f"""UPDATE lab_results SET patient_code = %(patient_code)s, test_code = %(test_code)s,
                    value = %(value)s, unit = %(unit)s, ref_low = %(ref_low)s, ref_high = %(ref_high)s,
                    sample_date = %(sample_date)s
                WHERE id = %(id)s RETURNING {COLUMNS}""",
            {**body.model_dump(), "id": item_id},
        ).fetchone()
    return row if row else not_found(item_id)


@app.delete("/lab-results/{item_id}", status_code=204)
def delete_lab_result(item_id: ItemId):
    with pool.connection() as conn:
        deleted = conn.execute("DELETE FROM lab_results WHERE id = %s", (item_id,)).rowcount
    return Response(status_code=204) if deleted else not_found(item_id)


@app.get("/healthz")
def healthz():
    try:
        with pool.connection(timeout=2) as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "db": "up"}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unavailable", "db": "down"})