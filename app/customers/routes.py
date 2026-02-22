from flask import render_template, request, flash, redirect, url_for, jsonify, current_app
from sqlalchemy.exc import IntegrityError
from app import db
from app.customers import customers
from app.customers.models import Customer, GiftCard
from app.auth.decorators import login_required, admin_required

@customers.route('/')
@admin_required
def index():
    """List and manage customers."""
    page = request.args.get('page', 1, type=int)
    q = request.args.get('q', '').strip()
    
    query = Customer.query.filter_by(is_active=True)
    if q:
        query = query.filter(
            (Customer.name.ilike(f'%{q}%')) |
            (Customer.phone.ilike(f'%{q}%')) |
            (Customer.email.ilike(f'%{q}%'))
        )
    
    pagination = query.order_by(Customer.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('customers/index.html', 
                           title='Customers',
                           pagination=pagination,
                           q=q)


@customers.route('/form')
@customers.route('/form/<int:customer_id>')
@login_required
def form(customer_id=None):
    """Render the customer add/edit form (usually for HTMX modal)."""
    customer = None
    if customer_id:
        customer = db.session.get(Customer, customer_id)
    return render_template('customers/form.html', customer=customer)

@customers.route('/search')
@login_required
def search():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])
    
    # Search by phone or name
    results = Customer.query.filter(
        (Customer.phone.ilike(f'%{q}%')) | 
        (Customer.name.ilike(f'%{q}%'))
    ).limit(10).all()
    
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'phone': c.phone,
        'points': c.points
    } for c in results])

@customers.route('/create', methods=['POST'])
@login_required
def create():
    data = request.get_json(silent=True) or request.form
    name = (data.get('name') or '').strip()
    phone = (data.get('phone') or '').strip()
    email = (data.get('email') or '').strip() or None
    
    if not name or not phone:
        return jsonify({'error': 'Name and Phone are required'}), 400
        
    if Customer.query.filter_by(phone=phone).first():
        return jsonify({'error': 'Customer with this phone already exists'}), 400
        
    c = Customer(name=name, phone=phone, email=email)
    try:
        db.session.add(c)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({'error': 'Customer with this phone already exists'}), 400
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception('Customer create failed: %s', exc)
        return jsonify({'error': 'Unable to create customer right now'}), 500
    
    return jsonify({
        'id': c.id,
        'name': c.name,
        'phone': c.phone,
        'points': c.points,
        'message': 'Customer created successfully'
    })


@customers.route('/edit/<int:customer_id>', methods=['POST'])
@login_required
def edit_customer(customer_id):
    """Update customer details."""
    data = request.get_json(silent=True) or request.form
    name = (data.get('name') or '').strip()
    phone = (data.get('phone') or '').strip()
    email = (data.get('email') or '').strip() or None
    
    c = db.session.get(Customer, customer_id)
    if not c:
        return jsonify({'error': 'Customer not found'}), 404
    
    if phone and phone != c.phone:
        if Customer.query.filter_by(phone=phone).first():
            return jsonify({'error': 'Phone number already registered to another customer'}), 400
        c.phone = phone

    if name:
        c.name = name
    c.email = email
    
    db.session.commit()
    return jsonify({'message': 'Customer updated successfully'})


@customers.route('/delete/<int:customer_id>', methods=['POST'])
@admin_required
def delete_customer(customer_id):
    """Deactivate a customer (soft-delete)."""
    c = db.session.get(Customer, customer_id)
    if not c:
        return jsonify({'error': 'Customer not found'}), 404
    
    c.is_active = False
    db.session.commit()
    return jsonify({'message': 'Customer deactivated'})


# ── GIFT CARDS ────────────────────────────────────────────────────

@customers.route('/giftcards')
@admin_required
def gift_cards():
    """List and manage gift cards."""
    page = request.args.get('page', 1, type=int)
    gcs = GiftCard.query.order_by(GiftCard.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    return render_template('customers/gift_cards.html', title='Gift Cards', pagination=gcs)


@customers.route('/giftcards/create', methods=['POST'])
@admin_required
def create_gift_card():
    """Issue a new gift card."""
    import secrets
    import string
    
    try:
        balance = Decimal(request.form.get('balance', '0'))
        if balance <= 0:
            raise ValueError("Balance must be positive.")
        
        # Generate a hard-to-guess 12-char code
        alphabet = string.ascii_uppercase + string.digits
        while True:
            code = "".join(secrets.choice(alphabet) for _ in range(12))
            if not GiftCard.query.filter_by(code=code).first():
                break
        
        gc = GiftCard(code=code, initial_balance=balance, balance=balance)
        db.session.add(gc)
        db.session.commit()
        
        flash(f'Gift Card {code} issued with ₹{balance:,.2f}', 'success')
    except Exception as e:
        flash(f'Failed to issue gift card: {str(e)}', 'error')
        
    return redirect(url_for('customers.gift_cards'))


@customers.route('/giftcards/toggle/<int:gc_id>', methods=['POST'])
@admin_required
def toggle_gift_card(gc_id):
    """Activate/Deactivate a gift card."""
    gc = db.session.get(GiftCard, gc_id)
    if not gc:
        flash('Gift card not found.', 'error')
    else:
        gc.is_active = not gc.is_active
        db.session.commit()
        status = "activated" if gc.is_active else "deactivated"
        flash(f'Gift card {gc.code} {status}.', 'success')
        
    return redirect(url_for('customers.gift_cards'))


@customers.route('/giftcard/check')
@login_required
def check_gift_card():
    code = request.args.get('code', '').strip()
    gc = GiftCard.query.filter_by(code=code, is_active=True).first()
    
    if not gc:
        return jsonify({'valid': False, 'error': 'Invalid or inactive gift card'})
        
    return jsonify({
        'valid': True,
        'code': gc.code,
        'balance': str(gc.balance)
    })
