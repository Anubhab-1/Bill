from dotenv import load_dotenv
import os

# Load environment variables from .env
load_dotenv()

from app import create_app
from app.migration import run_auto_migration

app = create_app(os.getenv('FLASK_ENV', 'development'))
run_auto_migration(app)
print("✅ Database schema patch completed successfully.")
