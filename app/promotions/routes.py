from datetime import datetime
from decimal import Decimal, InvalidOperation
from flask import abort, flash, redirect, render_template, request, session, url_for
from sqlalchemy import desc

from app import db
from app.auth.decorators import admin_required
from app.promotions import promotions
from app.promotions.models import PROMO_TYPE_CHOICES, Promotion
from app.promotions.engine import evaluate_promotions
from app.inventory.models import Product


def _parse_date_field(raw_value, field_name, errors):
    value = (raw_value or '').strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        errors[field_name] = 'Invalid date. Use YYYY-MM-DD format.'
        return None


def _parse_positive_int_field(raw_value, field_name, errors):
    value = (raw_value or '').strip()
    try:
        parsed = int(value)
        if parsed <= 0:
            raise ValueError
        return parsed
    except (ValueError, TypeError):
        errors[field_name] = 'Must be a positive integer.'
        return None


def _parse_non_negative_decimal_field(raw_value, field_name, errors, allow_zero=False, max_value=None):
    value = (raw_value or '').strip()
    try:
        parsed = Decimal(value)
    except (InvalidOperation, TypeError):
        errors[field_name] = 'Must be a valid number.'
        return None

    min_allowed = Decimal('0.00') if allow_zero else Decimal('0.01')
    if parsed < min_allowed:
        errors[field_name] = f'Must be at least {min_allowed}.'
        return None
    if max_value is not None and parsed > max_value:
        errors[field_name] = f'Must be <= {max_value}.'
        return None
    return parsed


def _parse_product_ids(raw_ids):
    product_ids = []
    for token in (raw_ids or '').split(','):
        token = token.strip()
        if not token:
            continue
        try:
            pid = int(token)
            if pid > 0:
                product_ids.append(pid)
        except ValueError:
            continue
    return sorted(set(product_ids))


def _build_params_from_form(form, promo_type, errors):
    params = {}

    if promo_type in {'percentage_item', 'fixed_item'}:
        product_ids = _parse_product_ids(form.get('param_product_ids', ''))
        if not product_ids:
            errors['param_product_ids'] = 'Provide at least one valid product ID.'
            return {}
        params['product_ids'] = product_ids

        if promo_type == 'percentage_item':
            percent = _parse_non_negative_decimal_field(
                form.get('param_percent'),
                'param_percent',
                errors,
                allow_zero=False,
                max_value=Decimal('100'),
            )
            if percent is not None:
                params['percent'] = float(percent)
        else:
            amount = _parse_non_negative_decimal_field(
                form.get('param_amount'),
                'param_amount',
                errors,
                allow_zero=False,
            )
            if amount is not None:
                params['amount'] = float(amount)

    elif promo_type == 'bill_percentage':
        percent = _parse_non_negative_decimal_field(
            form.get('param_percent'),
            'param_percent',
            errors,
            allow_zero=False,
            max_value=Decimal('100'),
        )
        if percent is not None:
            params['percent'] = float(percent)

    elif promo_type == 'buy_x_get_y':
        product_id = _parse_positive_int_field(form.get('param_product_id'), 'param_product_id', errors)
        buy_qty = _parse_positive_int_field(form.get('param_buy_qty'), 'param_buy_qty', errors)
        free_qty = _parse_positive_int_field(form.get('param_free_qty'), 'param_free_qty', errors)
        if product_id is not None and buy_qty is not None and free_qty is not None:
            params['product_id'] = product_id
            params['buy_qty'] = buy_qty
            params['free_qty'] = free_qty

    return params


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
        start_date = _parse_date_field(request.form.get('start_date'), 'start_date', errors)
        end_date = _parse_date_field(request.form.get('end_date'), 'end_date', errors)
        is_active = bool(request.form.get('is_active'))
        stackable = bool(request.form.get('stackable'))

        if not name:
            errors['name'] = 'Name is required.'
        if promo_type not in PROMO_TYPE_CHOICES:
            errors['promo_type'] = 'Invalid promotion type.'

        max_uses = None
        max_uses_raw = (request.form.get('max_uses') or '').strip()
        if max_uses_raw:
            max_uses = _parse_positive_int_field(max_uses_raw, 'max_uses', errors)

        if start_date and end_date and end_date < start_date:
            errors['end_date'] = 'End date cannot be before start date.'

        params = _build_params_from_form(request.form, promo_type, errors) if promo_type in PROMO_TYPE_CHOICES else {}

        if not errors:
            promo = Promotion(
                name=name,
                promo_type=promo_type,
                start_date=start_date,
                end_date=end_date,
                is_active=is_active,
                stackable=stackable,
                max_uses=max_uses,
                created_by=session.get('user_id'),
            )
            promo.params_dict = params
            db.session.add(promo)
            db.session.commit()
            flash('Promotion created successfully', 'success')
            return redirect(url_for('promotions.index'))

    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()
    return render_template(
        'promotions/form.html',
        title='New Promotion',
        promo=None,
        errors=errors,
        products=products,
    )

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
        start_date = _parse_date_field(request.form.get('start_date'), 'start_date', errors)
        end_date = _parse_date_field(request.form.get('end_date'), 'end_date', errors)
        is_active = bool(request.form.get('is_active'))
        stackable = bool(request.form.get('stackable'))

        if not name:
            errors['name'] = 'Name is required.'
        if promo_type not in PROMO_TYPE_CHOICES:
            errors['promo_type'] = 'Invalid promotion type.'

        max_uses = None
        max_uses_raw = (request.form.get('max_uses') or '').strip()
        if max_uses_raw:
            max_uses = _parse_positive_int_field(max_uses_raw, 'max_uses', errors)

        if start_date and end_date and end_date < start_date:
            errors['end_date'] = 'End date cannot be before start date.'

        params = _build_params_from_form(request.form, promo_type, errors) if promo_type in PROMO_TYPE_CHOICES else {}

        if not errors:
            promo.name = name
            promo.promo_type = promo_type
            promo.start_date = start_date
            promo.end_date = end_date
            promo.is_active = is_active
            promo.stackable = stackable
            promo.max_uses = max_uses
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
    quantities = request.form.getlist('qty[]')
    
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
        key = str(pid)
        if key in mock_cart:
            mock_cart[key]['quantity'] += qty
            continue
        mock_cart[key] = {
            'product_id': pid,
            'name': product.name,
            'price': str(product.price),
            'quantity': qty,
            'gst_percent': product.gst_percent,
        }

    active_promos = get_active_promotions()
    promo_result  = evaluate_promotions(mock_cart, active_promos)

    return render_template('promotions/_preview.html', 
                         mock_cart=mock_cart, promo_result=promo_result)


def get_active_promotions():
    """Return a list of all currently active and valid promotions."""
    all_active = Promotion.query.filter_by(is_active=True).all()
    # Filter by date ranges and usage limits in Python for simplicity
    return [p for p in all_active if p.is_valid_today]
