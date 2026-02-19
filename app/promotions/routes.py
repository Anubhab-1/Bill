"""
app/promotions/routes.py
------------------------
Admin routes for managing promotions and testing them against sample carts.
"""
import json
from datetime import date
from decimal import Decimal

from flask import (
    render_template, redirect, url_for,
    request, flash, session, jsonify
)

from app.promotions import promotions
from app.promotions.models import Promotion, AppliedPromotion, PROMO_TYPES
from app.promotions.engine import evaluate_promotions
from app.inventory.models import Product
from app.auth.decorators import admin_required
from app import db


# ── Helper ────────────────────────────────────────────────────────

def _parse_params_from_form(promo_type: str) -> dict:
    """Extract and structure promotion params from the submitted form."""
    if promo_type == 'percentage_item':
        raw_ids = request.form.get('param_product_ids', '')
        pids = [int(x.strip()) for x in raw_ids.split(',') if x.strip().isdigit()]
        return {'product_ids': pids, 'percent': float(request.form.get('param_percent', 0))}

    elif promo_type == 'fixed_item':
        raw_ids = request.form.get('param_product_ids', '')
        pids = [int(x.strip()) for x in raw_ids.split(',') if x.strip().isdigit()]
        return {'product_ids': pids, 'amount': float(request.form.get('param_amount', 0))}

    elif promo_type == 'bill_percentage':
        return {'percent': float(request.form.get('param_percent', 0))}

    elif promo_type == 'buy_x_get_y':
        return {
            'product_id': int(request.form.get('param_product_id', 0)),
            'buy_qty':    int(request.form.get('param_buy_qty', 1)),
            'free_qty':   int(request.form.get('param_free_qty', 1)),
        }

    return {}


# ── List ──────────────────────────────────────────────────────────

@promotions.route('/')
@admin_required
def index():
    all_promos = Promotion.query.order_by(Promotion.is_active.desc(), Promotion.id.desc()).all()
    return render_template('promotions/index.html',
                           title='Promotions', promos=all_promos, promo_types=dict(PROMO_TYPES))


# ── Create ────────────────────────────────────────────────────────

@promotions.route('/new', methods=['GET', 'POST'])
@admin_required
def new_promo():
    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()
    if request.method == 'POST':
        promo_type = request.form.get('promo_type', '')
        if promo_type not in [p[0] for p in PROMO_TYPES]:
            flash('Invalid promotion type.', 'error')
            return render_template('promotions/form.html', title='New Promotion',
                                   promo=None, promo_types=PROMO_TYPES, products=products)

        try:
            start = request.form.get('start_date') or None
            end   = request.form.get('end_date')   or None
            promo = Promotion(
                name        = request.form.get('name', '').strip(),
                promo_type  = promo_type,
                params      = json.dumps(_parse_params_from_form(promo_type)),
                start_date  = date.fromisoformat(start) if start else None,
                end_date    = date.fromisoformat(end)   if end   else None,
                is_active   = bool(request.form.get('is_active')),
                max_uses    = int(request.form.get('max_uses')) if request.form.get('max_uses') else None,
                stackable   = bool(request.form.get('stackable')),
                created_by  = session.get('user_id'),
            )
            db.session.add(promo)
            db.session.commit()
            flash(f'Promotion "{promo.name}" created.', 'success')
            return redirect(url_for('promotions.index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {e}', 'error')

    return render_template('promotions/form.html', title='New Promotion',
                           promo=None, promo_types=PROMO_TYPES, products=products)


# ── Edit ──────────────────────────────────────────────────────────

@promotions.route('/<int:promo_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_promo(promo_id):
    promo    = db.session.get(Promotion, promo_id) or (None, __import__('flask').abort(404))[0]
    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()

    if request.method == 'POST':
        promo_type = request.form.get('promo_type', promo.promo_type)
        try:
            start = request.form.get('start_date') or None
            end   = request.form.get('end_date')   or None
            promo.name       = request.form.get('name', '').strip()
            promo.promo_type = promo_type
            promo.params     = json.dumps(_parse_params_from_form(promo_type))
            promo.start_date = date.fromisoformat(start) if start else None
            promo.end_date   = date.fromisoformat(end)   if end   else None
            promo.is_active  = bool(request.form.get('is_active'))
            promo.max_uses   = int(request.form.get('max_uses')) if request.form.get('max_uses') else None
            promo.stackable  = bool(request.form.get('stackable'))
            db.session.commit()
            flash(f'Promotion "{promo.name}" updated.', 'success')
            return redirect(url_for('promotions.index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {e}', 'error')

    return render_template('promotions/form.html', title='Edit Promotion',
                           promo=promo, promo_types=PROMO_TYPES, products=products)


# ── Toggle active ─────────────────────────────────────────────────

@promotions.route('/<int:promo_id>/toggle', methods=['POST'])
@admin_required
def toggle_promo(promo_id):
    promo = db.session.get(Promotion, promo_id)
    if promo:
        promo.is_active = not promo.is_active
        db.session.commit()
        status = 'Active' if promo.is_active else 'Inactive'
        flash(f'"{promo.name}" is now {status}.', 'success')
    return redirect(url_for('promotions.index'))


# ── Delete ────────────────────────────────────────────────────────

@promotions.route('/<int:promo_id>/delete', methods=['POST'])
@admin_required
def delete_promo(promo_id):
    promo = db.session.get(Promotion, promo_id)
    if promo:
        name = promo.name
        db.session.delete(promo)
        db.session.commit()
        flash(f'Promotion "{name}" deleted.', 'success')
    return redirect(url_for('promotions.index'))


# ── Tester ────────────────────────────────────────────────────────

@promotions.route('/tester')
@admin_required
def tester():
    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()
    return render_template('promotions/tester.html', title='Promo Tester',
                           products=products, promo_result=None)


@promotions.route('/tester/preview', methods=['POST'])
@admin_required
def tester_preview():
    """
    HTMX endpoint: receives a sample cart as form data,
    evaluates all active promotions, and returns an HTML partial.
    """
    # Build a mock cart from form inputs
    # Form fields: product_id[] and qty[]
    product_ids = request.form.getlist('product_id[]')
    quantities  = request.form.getlist('qty[]')

    mock_cart = {}
    for pid_s, qty_s in zip(product_ids, quantities):
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
            'name':        product.name,
            'price':       str(product.price),
            'quantity':    qty,
            'gst_percent': product.gst_percent,
        }

    active_promos = Promotion.query.filter_by(is_active=True).all()
    promo_result  = evaluate_promotions(mock_cart, active_promos)

    return render_template('promotions/_preview.html',
                           mock_cart=mock_cart, promo_result=promo_result)


# ── API: active promotions (used by billing cart route) ──────────

def get_active_promotions():
    """Return all currently date-valid active promotions. Used by billing."""
    today = date.today()
    return Promotion.query.filter(
        Promotion.is_active == True,
        db.or_(Promotion.start_date.is_(None), Promotion.start_date <= today),
        db.or_(Promotion.end_date.is_(None),   Promotion.end_date   >= today),
    ).all()
