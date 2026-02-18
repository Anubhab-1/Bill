from flask import render_template, redirect, url_for, request, flash, abort, current_app, session
from sqlalchemy.exc import IntegrityError
from app.inventory import inventory
from app.inventory.models import Product, InventoryLog
from app.inventory.validators import validate_product_form, parse_product_form
from app.auth.decorators import login_required, admin_required
from app import db


# ── LIST ──────────────────────────────────────────────────────────────────────

@inventory.route('/')
@login_required
def index():
    """List all products, ordered by name."""
    from app.inventory.models import LOW_STOCK_THRESHOLD
    products = Product.query.order_by(Product.name.asc()).all()
    return render_template(
        'inventory/index.html',
        title='Inventory',
        products=products,
        low_stock_threshold=LOW_STOCK_THRESHOLD,
    )


# ── CREATE ────────────────────────────────────────────────────────────────────

@inventory.route('/new', methods=['GET', 'POST'])
@admin_required
def new():
    """Show add-product form (GET) or create a new product (POST)."""
    errors = {}
    form_data = {}

    if request.method == 'POST':
        form_data = request.form.to_dict()
        errors = validate_product_form(form_data)

        if not errors:
            # Route-level uniqueness check (fast path, avoids unnecessary DB write)
            if Product.query.filter_by(barcode=form_data['barcode'].strip()).first():
                errors['barcode'] = 'A product with this barcode already exists.'

        if not errors:
            data = parse_product_form(form_data)   # returns Decimal price, int stock/gst
            product = Product(**data)
            try:
                db.session.add(product)
                db.session.flush()  # get ID
                
                # Log initial stock (creation)
                if product.stock > 0:
                    log = InventoryLog(
                        product_id=product.id,
                        old_stock=0,
                        new_stock=product.stock,
                        changed_by=session.get('user_id'),
                        reason="Initial Stock (Product Created)"
                    )
                    db.session.add(log)

                db.session.commit()
                current_app.logger.info(f"Admin created product: {product.name} ({product.barcode})")
                flash(f'Product "{product.name}" added successfully.', 'success')
                return redirect(url_for('inventory.index'))
            except IntegrityError:
                # Race condition: another request inserted the same barcode between
                # our check above and this commit.
                db.session.rollback()
                errors['barcode'] = 'A product with this barcode already exists.'

    return render_template(
        'inventory/form.html',
        title='Add Product',
        form_action=url_for('inventory.new'),
        errors=errors,
        form_data=form_data,
        is_edit=False
    )


# ── EDIT ──────────────────────────────────────────────────────────────────────

@inventory.route('/<int:product_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit(product_id):
    """Show edit form (GET) or update an existing product (POST)."""
    product = db.session.get(Product, product_id)
    if product is None:
        abort(404)

    errors = {}

    if request.method == 'POST':
        form_data = request.form.to_dict()
        errors = validate_product_form(form_data)

        if not errors:
            new_barcode = form_data['barcode'].strip()
            # Uniqueness check — only fail if barcode belongs to a DIFFERENT product
            conflict = Product.query.filter(
                Product.barcode == new_barcode,
                Product.id != product_id
            ).first()
            if conflict:
                errors['barcode'] = 'A product with this barcode already exists.'

        if not errors:
            data = parse_product_form(form_data)   # Decimal price, int stock/gst
            for field, value in data.items():
                setattr(product, field, value)
            try:
                # Detect stock change
                # product is attached to session, so 'product.stock' reflects the UPDATE?
                # No, we set attributes via setattr loop above.
                # To get old value, we need to inspect history or query before update.
                # Actually, we modified the object in memory. 
                # SQLAlchemy history tracks changes!
                from sqlalchemy import inspect
                hist = inspect(product).attrs.stock.history
                
                if hist.has_changes():
                    old_s = hist.deleted[0] if hist.deleted else 0
                    new_s = product.stock
                    
                    log = InventoryLog(
                        product_id=product.id,
                        old_stock=old_s,
                        new_stock=new_s,
                        changed_by=session.get('user_id'),
                        reason="Admin Adjustment"
                    )
                    db.session.add(log)

                db.session.commit()
                current_app.logger.info(f"Admin updated product: {product.name} ({product.barcode})")
                flash(f'Product "{product.name}" updated successfully.', 'success')
                return redirect(url_for('inventory.index'))
            except IntegrityError:
                # Race condition: another request claimed the barcode between
                # our conflict check above and this commit.
                db.session.rollback()
                errors['barcode'] = 'A product with this barcode already exists.'

    else:
        # Pre-fill form with current DB values on GET
        form_data = {
            'name':        product.name,
            'barcode':     product.barcode,
            'price':       str(product.price),
            'stock':       str(product.stock),
            'gst_percent': str(product.gst_percent),
        }

    return render_template(
        'inventory/form.html',
        title=f'Edit — {product.name}',
        form_action=url_for('inventory.edit', product_id=product_id),
        errors=errors,
        form_data=form_data,
        is_edit=True,
        product=product
    )


# ── DELETE ────────────────────────────────────────────────────────────────────

@inventory.route('/<int:product_id>/delete', methods=['POST'])
@admin_required
def delete(product_id):
    """Delete a product. Supports both full-page and HTMX requests."""
    product = db.session.get(Product, product_id)
    if product is None:
        abort(404)

    name = product.name
    barcode = product.barcode
    
    # Soft Delete
    product.is_active = False
    
    # Log it
    log = InventoryLog(
        product_id=product.id,
        old_stock=product.stock,
        new_stock=product.stock, # Stock unchanged, but product disabled
        changed_by=session.get('user_id'),
        reason="Product Deleted (Soft Delete)"
    )
    db.session.add(log)
    
    db.session.commit()
    
    current_app.logger.info(f"Admin soft-deleted product: {name} ({barcode})")

    # HTMX request → return empty 200 so HTMX removes the row from the DOM
    if request.headers.get('HX-Request'):
        return '', 200

    flash(f'Product "{name}" deleted.', 'success')
    return redirect(url_for('inventory.index'))


# ── LOGS ──────────────────────────────────────────────────────────────────────

@inventory.route('/<int:product_id>/logs')
@admin_required
def logs(product_id):
    """View inventory logs for a product."""
    product = db.session.get(Product, product_id)
    if product is None:
        abort(404)
        
    logs = InventoryLog.query.filter_by(product_id=product_id).order_by(InventoryLog.timestamp.desc()).all()
    
    return render_template(
        'inventory/logs.html',
        title=f'Logs: {product.name}',
        product=product,
        logs=logs
    )
