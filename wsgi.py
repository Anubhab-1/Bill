from app import create_app
import os

config_name = os.environ.get('FLASK_ENV', 'production')
app = create_app(config_name)

# ── AUTO-SEED for Render (No Shell Access) ──
# Ensures tables and demo users exist on startup
with app.app_context():
        # ── AUTO-MIGRATION ──
        # Always run migrations on startup to catch schema changes (e.g. is_weighed)
        print("🔄 Running schema migrations (flask patch-db)...")
        import subprocess
        try:
            subprocess.run(["flask", "patch-db"], check=True)
            print("✅ Schema migrations checked/applied.")
        except subprocess.CalledProcessError as e:
            print(f"❌ Migration failed: {e}")

        # ── AUTO-SEED ──
        db.create_all() 
        from app.auth.models import User
        if not User.query.first():
            print("🌱 Database empty. Auto methods running: flask seed-demo")
            subprocess.run(["flask", "seed-demo"], check=True)
    except Exception as e:
        print(f"⚠️ Startup sequence failed: {e}")

if __name__ == "__main__":
    app.run()
