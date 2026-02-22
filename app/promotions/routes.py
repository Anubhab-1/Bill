import io
from datetime import datetime
from flask import abort, flash, redirect, render_template, request, url_for, current_app
from sqlalchemy import desc

from app import db
from app.auth.decorators import admin_required, login_required
from app.promotions import promotions
from app.promotions.models import Promotion
from app.promotions.engine import evaluate_promotions
from app.inventory.models import Product

@promotions.route('/')
@admin_required
def index():
    """List all promotions."""
    promos = Promotion.query.order_by(desc(Promotion.is_active), desc(Promotion.id)).all()
    return render_template('promotions/index.html', title='Promotions', promos=promos)

@promotions.route('/new', methods=['GET', 'POST'])
@admin_required
def create():
    """Create a new promotion."""
    errors = {}
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        promo_type = request.form.get('promo_type', '').strip()
        start_date_s = request.form.get('start_date', '').strip()
        end_date_s = request.form.get('end_date', '').strip()
        is_active = request.form.get('is_active') == 'on'
        
        # Simple validation
        if not name: errors['name'] = 'Name is required'
        if not promo_type: errors['promo_type'] = 'Type is required'
        
        # Parse dates
        start_date = datetime.strptime(start_date_s, '%Y-%m-%d') if start_date_s else None
        end_date = datetime.strptime(end_date_s, '%Y-%m-%d') if end_date_s else None

        # Build parameters
        params = {}
        if promo_type == 'buy_x_get_y':
            params['product_id'] = int(request.form.get('product_id', 0))
            params['buy_qty']    = int(request.form.get('buy_qty', 1))
            params['free_qty']   = int(request.form.get('free_qty', 1))
        elif promo_type == 'flat_off':
            params['min_spend'] = float(request.form.get('min_spend', 0))
            params['discount_amount'] = float(request.form.get('discount_amount', 0))
        elif promo_type == 'percent_off':
            params['min_spend'] = float(request.form.get('min_spend', 0))
            params['discount_percent'] = float(request.form.get('discount_percent', 0))

        if not errors:
            promo = Promotion(
                name=name,
                promo_type=promo_type,
                start_date=start_date,
                end_date=end_date,
                is_active=is_active
            )
            promo.params_dict = params
            db.session.add(promo)
            db.session.commit()
            flash('Promotion created successfully', 'success')
            return redirect(url_for('promotions.index'))

    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()
    return render_template('promotions/form.html', title='New Promotion', promo=None, errors=errors, products=products)

@promotions.route('/<int:promo_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit(promo_id):
    """Edit an existing promotion."""
    promo = db.session.get(Promotion, promo_id)
    if not promo:
        abort(404)
    
    errors = {}
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        promo_type = request.form.get('promo_type', '').strip()
        start_date_s = request.form.get('start_date', '').strip()
        end_date_s = request.form.get('end_date', '').strip()
        is_active = request.form.get('is_active') == 'on'
        
        if not name: errors['name'] = 'Name is required'
        
        params = {}
        if promo_type == 'buy_x_get_y':
            params['product_id'] = int(request.form.get('product_id', 0))
            params['buy_qty']    = int(request.form.get('buy_qty', 1))
            params['free_qty']   = int(request.form.get('free_qty', 1))
        elif promo_type == 'flat_off':
            params['min_spend'] = float(request.form.get('min_spend', 0))
            params['discount_amount'] = float(request.form.get('discount_amount', 0))
        elif promo_type == 'percent_off':
            params['min_spend'] = float(request.form.get('min_spend', 0))
            params['discount_percent'] = float(request.form.get('discount_percent', 0))

        if not errors:
            promo.name = name
            promo.promo_type = promo_type
            promo.start_date = datetime.strptime(start_date_s, '%Y-%m-%d') if start_date_s else None
            promo.end_date = datetime.strptime(end_date_s, '%Y-%m-%d') if end_date_s else None
            promo.is_active = is_active
            promo.params_dict = params
            db.session.commit()
            flash('Promotion updated successfully', 'success')
            return redirect(url_for('promotions.index'))

    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()
    return render_template('promotions/form.html', title='Edit Promotion', promo=promo, errors=errors, products=products)

@promotions.route('/<int:promo_id>/delete', methods=['POST'])
@admin_required
def delete(promo_id):
    """Delete a promotion."""
    promo = db.session.get(Promotion, promo_id)
    if not promo:
        abort(404)
    db.session.delete(promo)
    db.session.commit()
    flash('Promotion deleted', 'success')
    return redirect(url_for('promotions.index'))

@promotions.route('/<int:promo_id>/toggle', methods=['POST'])
@admin_required
def toggle(promo_id):
    """Enable or disable a promotion."""
    promo = db.session.get(Promotion, promo_id)
    if not promo:
        abort(404)
    promo.is_active = not promo.is_active
    db.session.commit()
    flash(f'Promotion {"enabled" if promo.is_active else "disabled"}', 'success')
    return redirect(url_for('promotions.index'))

@promotions.route('/tester', methods=['GET'])
@admin_required
def tester():
    """Interactive tool to test promotion logic."""
    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()
    return render_template('promotions/tester.html', title='Promotion Tester', products=products)

@promotions.route('/tester/preview', methods=['POST'])
@admin_required
def tester_preview():
    """HTMX endpoint for promotion tester."""
    cart_data = request.form.getlist('product_id[]')
    quantities = request.form.getlist('quantity[]')
    
    mock_cart = {}
    for pid_s, qty_s in zip(cart_data, quantities):
        try:
            pid = int(pid_s)
            qty = int(qty_s)
        except (ValueError, TypeError):
            continue
        if qty <= 0:
            continue
        product = db.session.get(Product, pid)
        if not product:
            continue
        mock_cart[str(pid)] = {
            'product_id':  pid,
            'name':        product.name,
            'price':       str(product.price),
            'quantity':    qty,
            'gst_percent': product.gst_percent,
        }

    active_promos = Promotion.query.filter_by(is_active=True).all()
    promo_result  = evaluate_promotions(mock_cart, active_promos)

    return render_template('promotions/_preview.html', 
                         mock_cart=mock_cart, promo_result=promo_result)


def get_active_promotions():
    """Return a list of all currently active and valid promotions."""
    all_active = Promotion.query.filter_by(is_active=True).all()
    # Filter by date ranges and usage limits in Python for simplicity
    return [p for p in all_active if p.is_valid_today]
