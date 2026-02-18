from flask import render_template, redirect, url_for, request, session, flash, current_app
from app.auth import auth
from app.auth.models import User


@auth.route('/login', methods=['GET', 'POST'])
def login():
    """
    GET  → render login form.
    POST → validate credentials, populate session, redirect to dashboard.
    """
    # Already logged in → go straight to dashboard
    if 'user_id' in session:
        return redirect(url_for('main.index'))

    error = None

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        # Basic presence validation
        if not username or not password:
            error = 'Username and password are required.'
        else:
            user = User.query.filter_by(username=username).first()

            if user is None or not user.check_password(password):
                # Deliberately vague — don't reveal which field was wrong
                current_app.logger.warning(f"Failed login attempt for username: {username}")
                error = 'Invalid username or password.'
            else:
                # ── Populate session (minimal — only what's needed) ──
                session.clear()
                session['user_id'] = user.id
                session['role']    = user.role.value  # 'admin' or 'cashier'
                session.permanent  = True             # respect PERMANENT_SESSION_LIFETIME
                
                current_app.logger.info(f"User {user.username} logged in successfully.")
                # ────────────────────────────────────────────────────
                flash(f'Welcome back, {user.name}!', 'success')
                return redirect(url_for('main.index'))

    return render_template('auth/login.html', title='Login', error=error)


@auth.route('/logout')
def logout():
    """Clear the session and redirect to login."""
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))
