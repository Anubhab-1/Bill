import os
import pytest
from sqlalchemy import text
from app import create_app, db

# Force testing configuration
os.environ['TEST_MODE'] = 'True'
os.environ['DATABASE_URL'] = 'postgresql://postgres:Galaxy%402006@localhost:5432/mall_test'

@pytest.fixture(scope='session')
def app():
    """Create a Flask app context for the session."""
    app = create_app('testing')
    print(f"\nDEBUG: App DB URI: {app.config['SQLALCHEMY_DATABASE_URI']}")
    
    with app.app_context():
        # Make sure the testing database is clean before any tests run
        db.drop_all()
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture(scope='session')
def _db(app):
    """Provide the SQLAlchemy db instance."""
    return db

@pytest.fixture(scope='function')
def client(app):
    """A test client for the app."""
    return app.test_client()

@pytest.fixture(scope='function', autouse=True)
def cleanup_db(_db, app):
    """
    Ensures each test starts with a clean database.
    Deletes all records from all tables.
    """
    yield
    with app.app_context():
        # Using reversed(metadata.sorted_tables) to respect foreign key constraints
        for table in reversed(_db.metadata.sorted_tables):
            _db.session.execute(table.delete())
        _db.session.commit()
        _db.session.remove()

@pytest.fixture(scope='function')
def db_session(_db, app):
    """Provides a database session for the test."""
    with app.app_context():
        yield _db.session
        _db.session.remove()

@pytest.fixture(scope='function')
def admin_user(db_session):
    """Create a default admin user."""
    from app.auth.models import User, RoleEnum
    admin = User(
        username='testadmin',
        name='Test Admin',
        role=RoleEnum.admin
    )
    admin.set_password('Admin123')
    db_session.add(admin)
    db_session.commit() # Commit so external requests (app client) see it
    return admin

@pytest.fixture(scope='function')
def cashier_user(db_session):
    """Create a default cashier user."""
    from app.auth.models import User, RoleEnum
    cashier = User(
        username='testcashier',
        name='Test Cashier',
        role=RoleEnum.cashier
    )
    cashier.set_password('Cashier123')
    db_session.add(cashier)
    db_session.commit()
    return cashier
