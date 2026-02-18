"""
app/admin/routes.py
──────────────────
Admin-only routes for system maintenance, including database backups.
"""
import os
import shutil
import subprocess
import logging
from datetime import datetime
from urllib.parse import urlparse

from flask import current_app, send_from_directory, flash, redirect, url_for, render_template, abort
from app.admin import admin
from app.auth.decorators import admin_required

@admin.route('/backup')
@admin_required
def backup():
    """
    Triggers a manual database backup.
    Supports PostgreSQL (pg_dump) and SQLite (file copy).
    Saves to /backups folder in the project root.
    """
    # ── CLOUD DEMO RESTRICTION ────────────────────────────────────
    if current_app.config.get('CLOUD_DEMO'):
        current_app.logger.warning("ACCESS DENIED: Backup attempted in CLOUD_DEMO mode (IP logged).")
        abort(403)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    
    # Ensure backup directory exists
    backup_dir = os.path.join(current_app.root_path, '..', 'backups')
    os.makedirs(backup_dir, exist_ok=True)
    
    db_uri = current_app.config['SQLALCHEMY_DATABASE_URI']

    # ── SQLite Strategy ───────────────────────────────────────────
    if db_uri.startswith('sqlite:'):
        filename = f'backup_{timestamp}.db'
        filepath = os.path.join(backup_dir, filename)
        
        # Extract path from URI
        # e.g. sqlite:///C:\Users\...\mall.db
        # or   sqlite:///mall.db (relative)
        src_path = db_uri.replace('sqlite:///', '')
        
        # Handle relative path: Flask-SQLAlchemy defaults to instance_path
        if not os.path.isabs(src_path):
             # 1. Try instance folder (standard Flask location)
             candidate = os.path.join(current_app.instance_path, src_path)
             if os.path.exists(candidate):
                 src_path = candidate
             else:
                 # 2. Try project root (fallback)
                 src_path = os.path.join(current_app.root_path, '..', src_path)

        try:
            shutil.copy2(src_path, filepath)
            current_app.logger.info(f"Backup successful (SQLite copy): {filename}")
            flash(f"Backup created successfully: {filename}", "success")
            return redirect(url_for('admin.download_backup', filename=filename))
        except Exception as e:
            current_app.logger.error(f"SQLite backup failed: {e}")
            flash(f"Backup failed: {str(e)}", "error")
            return redirect(url_for('main.index'))

    # ── PostgreSQL Strategy ───────────────────────────────────────
    filename = f'backup_{timestamp}.sql'
    filepath = os.path.join(backup_dir, filename)

    # Parse DB URI to get credentials
    # Format: postgresql://user:password@host:port/dbname
    try:
        parsed = urlparse(db_uri)
        dbname = parsed.path.lstrip('/')
        user   = parsed.username
        password = parsed.password
        host   = parsed.hostname
        port   = parsed.port or 5432
    except Exception as e:
        current_app.logger.error(f"Failed to parse DB URI: {e}")
        flash("Configuration error: Cannot parse database URI.", "error")
        return redirect(url_for('main.index'))

    # Prepare environment for pg_dump
    env = os.environ.copy()
    if password:
        env['PGPASSWORD'] = password

    cmd = [
        'pg_dump',
        '-h', str(host),
        '-p', str(port),
        '-U', str(user),
        '-f', filepath,
        dbname
    ]

    try:
        current_app.logger.info(f"Starting backup: {' '.join(cmd[:-1])} [dbname hidden]")
        subprocess.run(cmd, env=env, check=True, capture_output=True)
        
        current_app.logger.info(f"Backup successful: {filename}")
        flash(f"Backup created successfully: {filename}", "success")
        return redirect(url_for('admin.download_backup', filename=filename))

    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.decode() if e.stderr else str(e)
        current_app.logger.error(f"Backup failed: {err_msg}")
        flash(f"Backup failed. Check logs. Error: {err_msg}", "error")
        return redirect(url_for('main.index'))
    except Exception as e:
        current_app.logger.error(f"Backup error: {str(e)}")
        flash(f"An unexpected error occurred during backup.", "error")
        return redirect(url_for('main.index'))


@admin.route('/backup/download/<filename>')
@admin_required
def download_backup(filename):
    """Serve the backup file for download."""
    backup_dir = os.path.join(current_app.root_path, '..', 'backups')
    return send_from_directory(
        backup_dir, 
        filename, 
        as_attachment=True
    )
