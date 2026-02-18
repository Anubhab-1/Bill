"""
app/auth/decorators.py
----------------------
Reusable route-protection decorators.
Usage:
    from app.auth.decorators import login_required, admin_required

    @billing.route('/new')
    @login_required
    def new_bill():
        ...

    @reports.route('/all')
    @admin_required
    def all_reports():
        ...
"""
from functools import wraps
from flask import session, redirect, url_for, flash, abort


def login_required(f):
    """
    Redirect to login page if the user is not authenticated.
    Checks for 'user_id' key in the Flask session.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """
    Allow access only to users with role == 'admin'.
    Implies login_required — unauthenticated users are redirected to login.
    Authenticated non-admins receive a 403 Forbidden response.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        if session.get('role') != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated
