import os
import pytest
from urllib.parse import urlsplit, urlunsplit

from dotenv import load_dotenv

load_dotenv()


def _derive_test_database_url() -> str:
    explicit_test_url = os.environ.get("TEST_DATABASE_URL")
    if explicit_test_url:
        if not explicit_test_url.startswith("postgresql://"):
            raise RuntimeError("TEST_DATABASE_URL must start with postgresql://")
        return explicit_test_url

    base_url = os.environ.get("DATABASE_URL")
    if not base_url:
        raise RuntimeError("DATABASE_URL environment variable is not set.")
    if not base_url.startswith("postgresql://"):
        raise RuntimeError("DATABASE_URL must start with postgresql://")

    parts = urlsplit(base_url)
    # Preserve credentials/host/port/query and force dedicated test DB name.
    return urlunsplit((parts.scheme, parts.netloc, "/mall_test", parts.query, parts.fragment))


# ---- Force PostgreSQL test database ----
TEST_DATABASE_URL = _derive_test_database_url()

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["TEST_DATABASE_URL"] = TEST_DATABASE_URL


# ---- App + DB setup ----
from app import create_app
from app import db

# Ensure all models are imported at the session level so db.create_all() 
# always knows about them regardless of which test file is currently executing.
import app.auth.models
import app.inventory.models
import app.billing.models
import app.promotions.models
import app.customers.models
import app.purchasing.models


@pytest.fixture(scope="session")
def app():
    app = create_app("testing")
    return app


@pytest.fixture(scope="function", autouse=True)
def app_context(app):
    """Push application context automatically for every test."""
    with app.app_context():
        yield


@pytest.fixture(scope="function", autouse=True)
def setup_database(app):
    """Clean database before each test for isolation."""
    with app.app_context():
        db.session.remove()
        db.drop_all()
        db.create_all()
        yield
        db.session.remove()
