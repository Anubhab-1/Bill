from app import create_app
import os

config_name = os.environ.get('FLASK_ENV', 'production')
app = create_app(config_name)

# ── AUTO-SEED for Render (No Shell Access) ──
# Ensures tables and demo users exist on startup
with app.app_context():
    try:
        from app.auth.models import User
        # Check if basic tables exist/are populated to avoid expensive subprocess call
        # If User table doesn't exist, this might raise ProgrammingError, which db.create_all catches?
        # No, db.create_all() is safe.
        db.create_all() 
        
        if not User.query.first():
            print("🌱 Database empty. Auto methods running: flask seed-demo")
            import subprocess
            # Run the flask command in a subprocess
            subprocess.run(["flask", "seed-demo"], check=True)
    except Exception as e:
        print(f"⚠️ Auto-seed check failed (ignoring): {e}")

if __name__ == "__main__":
    app.run()
