import click
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from config import config

db = SQLAlchemy()


def create_app(config_name='default'):
    """Application factory — creates and configures the Flask app."""
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # ── Logging ───────────────────────────────────────────────────
    from app.utils.logging import setup_logging
    setup_logging(app)

    # ── Extensions ────────────────────────────────────────────────
    # ── Extensions ────────────────────────────────────────────────
    db.init_app(app)

    # ── Auto-Migration (Critical for Production) ──
    # Runs inline to ensure schema is correct before any request
    from app.migration import run_auto_migration
    run_auto_migration(app)

    # ── Blueprints ────────────────────────────────────────────────
    from app.main import main as main_blueprint
    app.register_blueprint(main_blueprint)

    from app.auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint, url_prefix='/auth')

    from app.billing import billing as billing_blueprint
    app.register_blueprint(billing_blueprint, url_prefix='/billing')

    from app.inventory import inventory as inventory_blueprint
    app.register_blueprint(inventory_blueprint, url_prefix='/inventory')

    from app.reports import reports as reports_blueprint
    app.register_blueprint(reports_blueprint, url_prefix='/reports')
    
    from app.admin import admin as admin_blueprint
    app.register_blueprint(admin_blueprint, url_prefix='/admin')

    from app.purchasing import purchasing as purchasing_blueprint
    app.register_blueprint(purchasing_blueprint, url_prefix='/purchasing')

    from app.promotions import promotions as promotions_blueprint
    app.register_blueprint(promotions_blueprint, url_prefix='/promotions')

    from app.reporting import reporting as reporting_blueprint
    app.register_blueprint(reporting_blueprint, url_prefix='/reporting')

    from app.customers import customers as customers_blueprint
    app.register_blueprint(customers_blueprint, url_prefix='/customers')
    
    # ── Error Handlers ────────────────────────────────────────────
    @app.errorhandler(500)
    def internal_error(e):
        db.session.rollback() # Ensure valid state for next request
        app.logger.error(f"Internal Server Error: {e}", exc_info=True)
        from flask import render_template
        return render_template('errors/500.html', title='Server Error', error=e), 500

    @app.errorhandler(403)
    def forbidden(e):
        from flask import render_template
        return render_template('errors/403.html', title='Access Denied'), 403

    @app.errorhandler(404)
    def not_found(e):
        from flask import render_template
        return render_template('errors/404.html', title='Page Not Found'), 404

    from sqlalchemy.exc import OperationalError
    @app.errorhandler(OperationalError)
    def db_error(e):
        """Handle lost DB connections gracefully."""
        db.session.rollback()
        # Log critical database failure
        app.logger.error(f"Database Connectivity Lost: {e}")
        from flask import render_template
        return render_template('errors/500_db.html', title='Database Error'), 503

    # ── Context Processor ─────────────────────────────────────────
    @app.context_processor
    def inject_config():
        """Make app.config available in templates (e.g. config.CLOUD_DEMO)."""
        return dict(config=app.config)

    @app.context_processor
    def inject_current_user():
        """
        Makes `current_user` available in every Jinja template.
        Fetches the User row from DB using session['user_id'].
        Returns None when not logged in — templates must guard with:
            {% if current_user %}
        """
        from flask import session
        from app.auth.models import User
        user_id = session.get('user_id')
        if user_id:
            user = db.session.get(User, user_id)
        else:
            user = None
        return {'current_user': user}

    # ── CLI Commands ──────────────────────────────────────────────
    register_commands(app)

    return app


def register_commands(app):
    """Register custom Flask CLI commands."""

    @app.cli.command('init-db')
    def init_db():
        """Create all database tables and seed the invoice sequence for this year."""
        from datetime import date
        from app.billing.models import InvoiceSequence

        db.create_all()
        click.echo('✅  Database tables created.')

        # Pre-seed the invoice sequence row for the current year.
        # This avoids an INSERT inside the first sale's transaction,
        # keeping the complete() route simpler and faster.
        year = date.today().year
        if not db.session.get(InvoiceSequence, year):
            db.session.add(InvoiceSequence(year=year, last_seq=0))
            db.session.commit()
            click.echo(f'✅  Invoice sequence seeded for {year} (starts at 0).')
        else:
            click.echo(f'ℹ️   Invoice sequence for {year} already exists.')

    @app.cli.command('show-sequences')
    def show_sequences():
        """Show current invoice sequence counters (diagnostic)."""
        from app.billing.models import InvoiceSequence
        rows = InvoiceSequence.query.order_by(InvoiceSequence.year.desc()).all()
        if not rows:
            click.echo('No sequence rows found. Run flask init-db first.')
            return
        click.echo(f'{"Year":<8} {"Last Seq":<12} {"Next Invoice"}')
        click.echo('─' * 35)
        for row in rows:
            next_inv = f'{row.year}-{row.last_seq + 1:04d}'
            click.echo(f'{row.year:<8} {row.last_seq:<12} {next_inv}')


    @app.cli.command('seed-admin')
    @click.option('--name',     prompt='Full name',  help='Admin full name')
    @click.option('--username', prompt='Username',   help='Admin username')
    @click.option('--password', prompt=True, hide_input=True,
                  confirmation_prompt=True, help='Admin password')
    def seed_admin(name, username, password):
        """Create the initial admin user."""
        from app.auth.models import User, RoleEnum

        if User.query.filter_by(username=username).first():
            click.echo(f'⚠️  User "{username}" already exists.')
            return

        admin = User(name=name, username=username, role=RoleEnum.admin)
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        click.echo(f'✅  Admin user "{username}" created successfully.')

    @app.cli.command('seed-cashier')
    @click.option('--name',     prompt='Full name',  help='Cashier full name')
    @click.option('--username', prompt='Username',   help='Cashier username')
    @click.option('--password', prompt=True, hide_input=True,
                  confirmation_prompt=True, help='Cashier password')
    def seed_cashier(name, username, password):
        """Create a cashier user."""
        from app.auth.models import User, RoleEnum

        if User.query.filter_by(username=username).first():
            click.echo(f'⚠️  User "{username}" already exists.')
            return

        cashier = User(name=name, username=username, role=RoleEnum.cashier)
        cashier.set_password(password)
        db.session.add(cashier)
        db.session.commit()
        click.echo(f'✅  Cashier user "{username}" created successfully.')

    @app.cli.command('patch-db')
    def patch_db():
    # ... (existing patch_db code) ...
        click.echo("✅ Schema patch complete.")

    from app.seed_history import seed_history
    app.cli.add_command(seed_history)

    @app.cli.command('seed-demo')
    def seed_demo():
        """Apply schema updates: new columns and tables."""
        from sqlalchemy import text, inspect
        
        # 0. Compare imports to ensure all models are known to SQLAlchemy
        import app.auth.models
        import app.inventory.models
        import app.billing.models
        import app.promotions.models
        import app.customers.models
        import app.purchasing.models
        
        # 1. Add missing tables (InventoryLog, Promotions, Customers, Returns)
        db.create_all()
        click.echo("✅ Verified all tables.")

        # 2. Add columns to existing tables
        with db.engine.connect() as conn:
            inspector = inspect(conn)
            
            # Helper to check if column exists
            def column_exists(table, column):
                headers = [c['name'] for c in inspector.get_columns(table)]
                return column in headers

            # Helper to check if table exists
            def table_exists(table):
                return inspector.has_table(table)

            # Sales: payment_method
            if not column_exists('sales', 'payment_method'):
                conn.execute(text("ALTER TABLE sales ADD COLUMN payment_method VARCHAR(20) DEFAULT 'cash' NOT NULL"))
                click.echo("✅ Added payment_method to sales.")

            # Sales: is_printed
            if not column_exists('sales', 'is_printed'):
                conn.execute(text("ALTER TABLE sales ADD COLUMN is_printed BOOLEAN DEFAULT FALSE"))
                click.echo("✅ Added is_printed to sales.")
            
            # Sales: customer_id (FK)
            # Critical: Ensure target table exists first
            if table_exists('customers') and not column_exists('sales', 'customer_id'):
                try:
                    conn.execute(text("ALTER TABLE sales ADD COLUMN customer_id INTEGER REFERENCES customers(id)"))
                    click.echo("✅ Added customer_id to sales.")
                except Exception as e:
                    click.echo(f"⚠️ Failed to add customer_id: {e}")

            # Products: is_active
            if not column_exists('products', 'is_active'):
                conn.execute(text("ALTER TABLE products ADD COLUMN is_active BOOLEAN DEFAULT TRUE NOT NULL"))
                click.echo("✅ Added is_active to products.")

            # Products: is_weighed
            if not column_exists('products', 'is_weighed'):
                 conn.execute(text("ALTER TABLE products ADD COLUMN is_weighed BOOLEAN DEFAULT FALSE NOT NULL"))
                 click.echo("✅ Added is_weighed to products.")

            # Products: price_per_kg
            if not column_exists('products', 'price_per_kg'):
                 conn.execute(text("ALTER TABLE products ADD COLUMN price_per_kg NUMERIC(10,2)"))
                 click.echo("✅ Added price_per_kg to products.")

            # SaleItems: weight_kg
            if not column_exists('sale_items', 'weight_kg'):
                 conn.execute(text("ALTER TABLE sale_items ADD COLUMN weight_kg NUMERIC(8,3)"))
                 click.echo("✅ Added weight_kg to sale_items.")

            # SaleItems: unit_label
            if not column_exists('sale_items', 'unit_label'):
                 conn.execute(text("ALTER TABLE sale_items ADD COLUMN unit_label VARCHAR(10)"))
                 click.echo("✅ Added unit_label to sale_items.")

            # 3. Add CHECK constraints (PostgreSQL)
            # These can fail if data violates them, so we wrap comfortably.
            constraints = [
                ("check_stock_non_negative", "ALTER TABLE products ADD CONSTRAINT check_stock_non_negative CHECK (stock >= 0)"),
                ("check_price_positive",     "ALTER TABLE products ADD CONSTRAINT check_price_positive CHECK (price > 0)"),
                ("check_gst_valid",          "ALTER TABLE products ADD CONSTRAINT check_gst_valid CHECK (gst_percent >= 0 AND gst_percent <= 28)"),
            ]
            
            for name, sql in constraints:
                try:
                    conn.execute(text(sql))
                    click.echo(f"✅ Added constraint: {name}")
                except Exception:
                    pass

            conn.commit()

        click.echo("✅ Schema patch complete.")

    @app.cli.command('seed-demo')
    def seed_demo():
        """Populate database with demo data."""
        from app.auth.models import User, RoleEnum
        from app.inventory.models import Product, InventoryLog
        from app.billing.models import Sale, SaleItem, CashSession
        from app.billing.invoice import generate_invoice_number
        import random
        from decimal import Decimal
        from datetime import datetime, timedelta

        click.echo("🌱 Seeding demo data...")
        db.create_all()

        # Users
        if not User.query.filter_by(username='admin').first():
            u = User(name='Admin User', username='admin', role=RoleEnum.admin)
            u.set_password('Admin@2026')
            db.session.add(u)
        
        c1 = User.query.filter_by(username='cashier1').first()
        if not c1:
            u = User(name='Sarah Cashier', username='cashier1', role=RoleEnum.cashier)
            u.set_password('123')
            db.session.add(u)
        
        c2 = User.query.filter_by(username='cashier2').first()
        if not c2:
            u = User(name='John Cashier', username='cashier2', role=RoleEnum.cashier)
            u.set_password('123')
            db.session.add(u)

        db.session.commit()
        click.echo("✅ Users created (admin/demo123, cashier1/123).")

        # Products
        if Product.query.count() < 5:
            names = ['Wireless Mouse', 'Keyboard', 'Monitor 24"', 'USB Cable', 'Laptop Stand', 'Notebook', 'Pen Set', 'Desk Lamp', 'Headphones', 'Speaker']
            for i in range(1, 26):
                name = f"{random.choice(names)} {i}"
                barcode = f"DEMO{i:03d}"
                price = Decimal(random.randint(50, 5000))
                stock = random.randint(10, 100)
                gst = random.choice([0, 5, 12, 18, 28])
                
                p = Product(name=name, barcode=barcode, price=price, stock=stock, gst_percent=gst)
                db.session.add(p)
                db.session.flush()
                
                log = InventoryLog(product_id=p.id, old_stock=0, new_stock=stock, reason="Initial Demo Stock")
                db.session.add(log)
            
            db.session.commit()
            click.echo("✅ Products seeded.")

        # Cash Session for cashier1
        c1 = User.query.filter_by(username='cashier1').first()
        if c1 and not c1.sessions.filter_by(end_time=None).first():
            s = CashSession(cashier_id=c1.id, opening_cash=Decimal('1000.00'), system_total=0)
            db.session.add(s)
            db.session.commit()
            click.echo("✅ Active session created for cashier1.")

        click.echo("✅ Demo seed complete.")

    # ── ProxyFix for Render (HTTPS Termination) ──
    try:
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    except ImportError:
        pass

    return app

# ── Compatibility with Render's default 'gunicorn app:app' ──
# This allows the package to be imported as an application object directly.
import os
try:
    # Only create if not main script and NOT running a flask command (to avoid double seed)
    if __name__ != '__main__' and not os.environ.get('FLASK_RUN_FROM_CLI'):
        env_name = os.environ.get('FLASK_ENV', 'production')
        app = create_app(env_name)
        
        # ── AUTO-SEED (moved from wsgi.py) ──
        # Critical for Render Free Tier where Shell is hard to access
        if env_name == 'production':
            try:
                with app.app_context():
                    db.create_all()
                    from app.auth.models import User
                    if not User.query.first():
                        print("🌱 Database empty. Auto-seeding...")
                        import subprocess
                        # Using subprocess to run the distinct CLI command
                        subprocess.run(["flask", "seed-demo"], check=True)
            except Exception as e:
                print(f"⚠️ Auto-seed failed: {e}")
                
except Exception:
    pass
