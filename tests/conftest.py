import os
import tempfile
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp()) / "test.sqlite3"
os.environ["CIVIC_COMPASS_DB"] = str(TMP)

# Freeze the world. The seed data is anchored to a fixed date and the clock is pinned to match it,
# so every assertion about freshness, staleness and days-until-election is decided by the dataset
# rather than by the day the suite happens to run. Without this the suite rots: tests covering
# expiry start failing weeks later for reasons that have nothing to do with the code.
os.environ["CIVIC_COMPASS_SEED_OFFSET_DAYS"] = "0"
os.environ["CIVIC_COMPASS_NOW"] = "2026-08-16T12:00:00+00:00"

from app.db import connect, init_schema  # noqa: E402
from app.seed import seed  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _build_db():
    conn = connect()
    init_schema(conn)
    seed(conn)
    conn.close()


@pytest.fixture()
def conn():
    c = connect()
    yield c
    c.close()


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)
