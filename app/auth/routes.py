from flask import render_template, redirect, url_for, request, session, flash, current_app
from app.auth import auth
from app.auth.models import User
from app.auth.decorators import login_required, admin_required


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
@login_required
def logout():
    """Clear the session and redirect to login."""
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))

@auth.route('/users')
@admin_required
def users_list():
    """List all system users."""
    users = User.query.order_by(User.id.asc()).all()
    return render_template('auth/users.html', title='System Users', users=users)


@auth.route('/users/create', methods=['POST'])
@admin_required
def create_user():
    """Create a new system user."""
    from app import db
    username = request.form.get('username', '').strip()
    name = request.form.get('name', '').strip()
    password = request.form.get('password', '')
    role = request.form.get('role', 'cashier')

    if not username or not password or not name:
        flash('Username, Name, and Password are required.', 'error')
        return redirect(url_for('auth.users_list'))

    if User.query.filter_by(username=username).first():
        flash('Username already exists.', 'error')
        return redirect(url_for('auth.users_list'))

    from app.auth.models import RoleEnum
    new_user = User(username=username, name=name, role=RoleEnum(role))
    new_user.set_password(password)
    
    db.session.add(new_user)
    db.session.commit()
    
    flash(f'User {username} created successfully.', 'success')
    return redirect(url_for('auth.users_list'))


@auth.route('/users/toggle/<int:user_id>', methods=['POST'])
@admin_required
def toggle_user_status(user_id):
    """Enable/Disable a user account."""
    from app import db
    user = db.session.get(User, user_id)
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('auth.users_list'))
    
    if user.id == session.get('user_id'):
        flash('Cannot disable your own account.', 'error')
        return redirect(url_for('auth.users_list'))

    user.is_active = not user.is_active
    db.session.commit()
    
    status = "enabled" if user.is_active else "disabled"
    flash(f'User {user.username} has been {status}.', 'success')
    return redirect(url_for('auth.users_list'))
