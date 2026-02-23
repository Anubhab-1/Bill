import os
import click
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_caching import Cache
from flask_socketio import SocketIO

db = SQLAlchemy()
cache = Cache()
socketio = SocketIO()


def create_app(config_name='default'):
    """Application factory — creates and configures the Flask app."""
    import os
    from config import config
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Enforce strict SECRET_KEY for production
    if config_name == 'production' or app.config.get('FLASK_ENV') == 'production':
        sk = app.config.get('SECRET_KEY')
        if not sk or sk == 'dev-secret-key-change-in-production':
            raise RuntimeError('SECRET_KEY must be set to a secure unique value in production.')

    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise RuntimeError('DATABASE_URL environment variable is not set.')

    if not database_url.startswith('postgresql://'):
        raise RuntimeError('DATABASE_URL must start with postgresql://')

    app.config['SQLALCHEMY_DATABASE_URI'] = database_url

    # Strict PostgreSQL Engine Options
    engine_options = dict(app.config.get('SQLALCHEMY_ENGINE_OPTIONS') or {})
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = engine_options

    app.logger.info(f"Strict PostgreSQL Mode: {app.config['SQLALCHEMY_DATABASE_URI']}")

    # ── Logging ───────────────────────────────────────────────────
    from app.utils.logging import setup_logging
    setup_logging(app)

    # ── Extensions ────────────────────────────────────────────────
    from flask_wtf.csrf import CSRFProtect
    csrf = CSRFProtect()
    csrf.init_app(app)

    db.init_app(app)
    cache.init_app(app)
    
    # Enable Redis message queue for SocketIO if REDIS_URL is present (critical for multi-worker prod)
    redis_url = app.config.get('CACHE_REDIS_URL')
    socketio.init_app(
        app, 
        cors_allowed_origins="*", 
        async_mode='eventlet',
        message_queue=redis_url if config_name == 'production' else None
    )


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

    @app.teardown_request
    def rollback_on_exception(exc):
        if exc is not None:
            db.session.rollback()

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
        """Apply safe schema patches and auto-seed admin on first run."""
        from app.migration import run_auto_migration
        run_auto_migration(app)
        click.echo("Schema patch complete.")

        # Auto-seed a default admin user if the database is empty.
        # This allows the app to self-initialize on a fresh Render deployment
        # without needing shell access (a Pro-only feature).
        from app.auth.models import User, RoleEnum
        reset_password = os.environ.get('ADMIN_PASSWORD_RESET', '').strip()

        if User.query.count() == 0:
            click.echo("No users found. Seeding default admin...")
            new_pw = reset_password or 'Admin@2026'
            admin = User(name='Administrator', username='admin', role=RoleEnum.admin)
            admin.set_password(new_pw)
            db.session.add(admin)
            db.session.commit()
            click.echo(f"✅  Default admin created. Username: admin | Password: {new_pw}")
            click.echo("⚠️   IMPORTANT: Change the admin password after first login!")

        elif reset_password:
            # If ADMIN_PASSWORD_RESET env var is set, forcefully reset the admin's password.
            # This is the safe way to recover access on Render free tier (no shell access).
            admin = User.query.filter_by(username='admin').first()
            if admin:
                admin.set_password(reset_password)
                if not admin.is_active:
                    admin.is_active = True
                db.session.commit()
                click.echo(f"✅  Admin password has been reset via ADMIN_PASSWORD_RESET env var.")
                click.echo(f"⚠️   Remove the ADMIN_PASSWORD_RESET env var from Render after logging in!")
            else:
                click.echo("ℹ️  ADMIN_PASSWORD_RESET set but no 'admin' user found. Creating one...")
                admin = User(name='Administrator', username='admin', role=RoleEnum.admin)
                admin.set_password(reset_password)
                db.session.add(admin)
                db.session.commit()
                click.echo(f"✅  Admin user created with the provided password.")

    from app.seed_history import seed_history
    app.cli.add_command(seed_history)


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
