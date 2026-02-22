"""
Admin-only routes for system maintenance, including database backups.
"""
import os
import subprocess
from datetime import datetime
from urllib.parse import urlparse

from flask import abort
from flask import current_app
from flask import flash
from flask import render_template
from flask import redirect
from flask import send_from_directory
from flask import url_for

from app.admin import admin
from app.auth.decorators import admin_required


@admin.route('/backup')
@admin_required
def backup():
    """
    Trigger a manual PostgreSQL backup and store it in the project backups folder.
    """
    if current_app.config.get('CLOUD_DEMO'):
        current_app.logger.warning('ACCESS DENIED: Backup attempted in CLOUD_DEMO mode (IP logged).')
        abort(403)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    backup_dir = os.path.join(current_app.root_path, '..', 'backups')
    os.makedirs(backup_dir, exist_ok=True)

    db_uri = current_app.config['SQLALCHEMY_DATABASE_URI']
    if not db_uri.startswith('postgresql://'):
        raise RuntimeError('Backup requires a PostgreSQL DATABASE_URL starting with postgresql://')

    filename = f'backup_{timestamp}.sql'
    filepath = os.path.join(backup_dir, filename)

    try:
        parsed = urlparse(db_uri)
        dbname = parsed.path.lstrip('/')
        user = parsed.username
        password = parsed.password
        host = parsed.hostname
        port = parsed.port or 5432
    except Exception as e:
        current_app.logger.error(f'Failed to parse DB URI: {e}')
        flash('Configuration error: Cannot parse database URI.', 'error')
        return redirect(url_for('main.index'))

    env = os.environ.copy()
    if password:
        env['PGPASSWORD'] = password

    cmd = [
        'pg_dump',
        '--dbname=' + db_uri,
        '-f', filepath,
    ]

    try:
        current_app.logger.info(f"Starting backup for database: {db_uri.split('/')[-1]}")
        subprocess.run(cmd, check=True, capture_output=True)
        current_app.logger.info(f'Backup successful: {filename}')
        flash(f'Backup created successfully: {filename}', 'success')
        return redirect(url_for('admin.download_backup', filename=filename))
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.decode() if e.stderr else str(e)
        current_app.logger.error(f'Backup failed: {err_msg}')
        flash(f'Backup failed. Check logs. Error: {err_msg}', 'error')
        return redirect(url_for('main.index'))
    except Exception as e:
        current_app.logger.error(f'Backup error: {e}')
        flash('An unexpected error occurred during backup.', 'error')
        return redirect(url_for('main.index'))


@admin.route('/backup/download/<filename>')
@admin_required
def download_backup(filename):
    """Serve the backup file for download."""
    backup_dir = os.path.join(current_app.root_path, '..', 'backups')
    return send_from_directory(
        backup_dir,
        filename,
        as_attachment=True,
    )

@admin.route('/hardware')
@admin_required
def hardware_setup():
    """Instructions and tools for configuring the local POS hardware agent."""
    return render_template(
        'admin/hardware.html', 
        title='Hardware Integration'
    )
