"""Test setup. Tests use their own database and never call the real Claude API.

The environment is changed here, before any app module is imported, so the engine and
settings pick up the test values.
"""

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import anthropic
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from tests.fakes import FakeAnthropic

BACKEND_DIR = Path(__file__).resolve().parents[1]

# The app runs as a limited role. Migrations and test database setup run as the owner.
_app_url = make_url(os.environ.get("DATABASE_URL", "postgresql+psycopg://casedesk_app:casedesk_app@db:5432/casedesk"))
_owner_url = make_url(
    os.environ.get("MIGRATION_DATABASE_URL", "postgresql+psycopg://casedesk:casedesk@db:5432/casedesk")
)
TEST_DATABASE = f"{_app_url.database}_test"
TEST_DATABASE_URL = _app_url.set(database=TEST_DATABASE).render_as_string(hide_password=False)
OWNER_TEST_DATABASE_URL = _owner_url.set(database=TEST_DATABASE).render_as_string(hide_password=False)

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["MIGRATION_DATABASE_URL"] = OWNER_TEST_DATABASE_URL
os.environ["ANTHROPIC_API_KEY"] = "test-key"
os.environ["AUTO_READ"] = "false"
os.environ["HOME_CACHE_SECONDS"] = "0"  # tests write to the database directly, so they read the queue fresh
os.environ["AUDIT_CHECKPOINT_FILE"] = str(Path(tempfile.mkdtemp(prefix="audit_checkpoint_")) / "checkpoint.json")


def _recreate_test_database() -> None:
    admin = create_engine(_owner_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DATABASE}" WITH (FORCE)'))
        connection.execute(text(f'CREATE DATABASE "{TEST_DATABASE}"'))
    admin.dispose()


@pytest.fixture(scope="session", autouse=True)
def test_database() -> str:
    """Start every test run from an empty database migrated to head."""
    _recreate_test_database()
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    command.upgrade(config, "head")
    return TEST_DATABASE


@pytest.fixture(scope="session", autouse=True)
def prompts_seeded(test_database: str) -> None:
    """The prompt registry starts with the YAML seeds, as it does on app start."""
    from app.ai.seed import seed_prompts
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        seed_prompts(session)


@pytest.fixture(scope="session", autouse=True)
def seeded(test_database: str) -> None:
    """Load the starter kit once. Rules such as the review date come from it."""
    from app.cases.loader import load_starter_kit
    from app.core.config import get_settings
    from app.db.session import SessionLocal

    kit = Path(get_settings().starter_kit_dir)
    assert (kit / "01_cases.csv").exists(), f"Tests need the starter kit mounted at {kit}"
    with SessionLocal() as session:
        load_starter_kit(session, kit)


def make_case(
    db: Session,
    case_id: str,
    *,
    ops: str = "OPS-91",
    legal: str = "LEGAL-91",
    status: str = "NEW",
    name: str = "Test Client",
) -> None:
    """Insert a throwaway case owned by test users, so tests never touch the starter kit cases."""
    db.execute(
        text(
            """
            INSERT INTO cases (case_id, web_record_id, client_ref, case_archetype, operational_stage,
                assigned_ops_user, assigned_legal_reviewer, opened_at, matter_visibility, priority)
            VALUES (:case_id, 'WEB-T', :client_ref, 'SYNTH_TEST_CASE', 'INTAKE_REVIEW', :ops, :legal,
                '2026-10-01', 'RESTRICTED', 'NORMAL') ON CONFLICT (case_id) DO NOTHING
            """
        ),
        {"case_id": case_id, "client_ref": f"CLIENT-{case_id[-6:]}", "ops": ops, "legal": legal},
    )
    db.execute(
        text(
            "INSERT INTO case_workflows (case_id, status) VALUES (:case_id, :status) "
            "ON CONFLICT (case_id) DO UPDATE SET status = :status"
        ),
        {"case_id": case_id, "status": status},
    )
    db.execute(
        text(
            "INSERT INTO profile_fields (source_id, case_id, field_name, verified_value, verification_state, "
            "verified_at, verified_by) VALUES (:sid, :case_id, 'full_name', :name, 'HUMAN_VERIFIED', now(), 'OPS-91') "
            "ON CONFLICT (source_id) DO UPDATE SET verified_value = :name"
        ),
        {"sid": f"PROFILE-{case_id}-full_name", "case_id": case_id, "name": name},
    )
    db.commit()


@pytest.fixture(autouse=True)
def fake_claude(monkeypatch: pytest.MonkeyPatch) -> FakeAnthropic:
    """Replace anthropic.Anthropic so no test reaches the network. Script replies with fake.reply(...)."""
    fake = FakeAnthropic()
    monkeypatch.setattr(anthropic, "Anthropic", lambda *args, **kwargs: fake)
    return fake


@pytest.fixture
def db() -> Iterator[Session]:
    """A session as the limited app role. Tests commit what they want to keep."""
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        yield session


@pytest.fixture(scope="session")
def owner_engine() -> Iterator[Engine]:
    """The database owner. Only for tests that tamper with data to prove the ledger notices."""
    engine = create_engine(OWNER_TEST_DATABASE_URL)
    yield engine
    engine.dispose()
