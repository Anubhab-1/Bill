import io
from decimal import Decimal
from datetime import date, timedelta

from flask import abort, current_app, flash, redirect, render_template, request, send_file, session, url_for
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app import db
from app.auth.decorators import admin_required
from app.inventory import inventory
from app.inventory.models import InventoryLog, Product, ProductBatch, ProductVariant
from app.inventory.validators import (
    parse_product_form,
    parse_variant_form,
    validate_product_form,
    validate_variant_form,
)


def _load_product_or_404(product_id: int) -> Product:
    product = db.session.get(Product, product_id)
    if product is None:
        abort(404)
    return product


def _render_variants_page(product: Product, errors=None, form_data=None):
    variants = (
        ProductVariant.query
        .filter_by(product_id=product.id, is_active=True)
        .order_by(ProductVariant.size.asc(), ProductVariant.color.asc(), ProductVariant.id.asc())
        .all()
    )
    return render_template(
        'inventory/variants.html',
        title=f'Variants - {product.name}',
        product=product,
        variants=variants,
        errors=errors or {},
        form_data=form_data or {},
    )


def _find_size_color_conflict(product_id: int, size: str, color: str, exclude_variant_id=None):
    query = ProductVariant.query.filter(
        ProductVariant.product_id == product_id,
        ProductVariant.is_active.is_(True),
        func.lower(ProductVariant.size) == size.lower(),
        func.lower(ProductVariant.color) == color.lower(),
    )
    if exclude_variant_id is not None:
        query = query.filter(ProductVariant.id != exclude_variant_id)
    return query.first()


def _ean13_checksum(payload_12: str) -> int:
    """Compute EAN-13 checksum for the first 12 digits."""
    total = 0
    for idx, ch in enumerate(payload_12):
        digit = int(ch)
        total += digit if idx % 2 == 0 else digit * 3
    return (10 - (total % 10)) % 10


def _generate_variant_barcode_image(raw_barcode: str):
    """
    Generate a barcode image using python-barcode.
    Uses EAN-13 for valid numeric 12/13-digit values, otherwise Code128.
    """
    try:
        from barcode import Code128, EAN13
        from barcode.writer import ImageWriter
    except Exception as exc:
        raise RuntimeError(
            'Barcode libraries are missing. Install python-barcode, Pillow, and reportlab.'
        ) from exc

    barcode_value = (raw_barcode or '').strip()
    if not barcode_value:
        raise ValueError('Barcode value is empty.')

    writer_options = {
        'module_width': 0.22,
        'module_height': 10.0,
        'quiet_zone': 1.0,
        'font_size': 8,
        'text_distance': 1.2,
        'dpi': 300,
        'write_text': True,
    }

    # Prefer EAN-13 when barcode is compatible; otherwise fallback to Code128.
    if barcode_value.isdigit() and len(barcode_value) in (12, 13):
        ean_payload = None
        if len(barcode_value) == 12:
            ean_payload = barcode_value
        else:
            expected_checksum = _ean13_checksum(barcode_value[:12])
            if expected_checksum == int(barcode_value[12]):
                ean_payload = barcode_value[:12]
        if ean_payload is not None:
            image = EAN13(ean_payload, writer=ImageWriter()).render(writer_options=writer_options)
            return image, 'EAN-13'

    image = Code128(barcode_value, writer=ImageWriter()).render(writer_options=writer_options)
    return image, 'Code128'


@inventory.route('/')
@admin_required
def index():
    """List products for admin inventory management."""
    show_archived = request.args.get('archived', '0') == '1'
    
    query = Product.query
    if not show_archived:
        query = query.filter(Product.is_active.is_(True))
    
    products = query.order_by(Product.name.asc()).all()
    return render_template('inventory/index.html', title='Inventory', products=products, show_archived=show_archived)


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
            import uuid
            parsed_data = parse_product_form(form_data)
            parsed_data['barcode'] = f"P-{uuid.uuid4().hex[:8].upper()}"
            product = Product(**parsed_data)
            try:
                db.session.add(product)
                db.session.commit()
                current_app.logger.info("Admin created product: %s", product.name)
                flash(f'Product "{product.name}" added successfully.', 'success')
                return redirect(url_for('inventory.index'))
            except IntegrityError:
                db.session.rollback()
                errors['name'] = 'Unable to create product right now. Please try again.'

    return render_template(
        'inventory/form.html',
        title='Add Product',
        form_action=url_for('inventory.new'),
        errors=errors,
        form_data=form_data,
        is_edit=False,
    )


@inventory.route('/<int:product_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit(product_id):
    """Show edit form (GET) or update an existing product (POST)."""
    product = _load_product_or_404(product_id)
    errors = {}

    if request.method == 'POST':
        form_data = request.form.to_dict()
        errors = validate_product_form(form_data)
        if not errors:
            data = parse_product_form(form_data)
            for field, value in data.items():
                setattr(product, field, value)
            try:
                db.session.commit()
                current_app.logger.info("Admin updated product: %s", product.name)
                flash(f'Product "{product.name}" updated successfully.', 'success')
                return redirect(url_for('inventory.index'))
            except IntegrityError:
                db.session.rollback()
                errors['name'] = 'Unable to update product right now. Please try again.'
    else:
        form_data = {
            'name': product.name,
            'brand': product.brand or '',
            'category': product.category or '',
            'description': product.description or '',
            'gst_percent': str(product.gst_percent),
            'is_weighed': 'on' if product.is_weighed else '',
            'price_per_kg': str(product.price_per_kg) if product.price_per_kg is not None else '',
        }

    return render_template(
        'inventory/form.html',
        title=f'Edit - {product.name}',
        form_action=url_for('inventory.edit', product_id=product_id),
        errors=errors,
        form_data=form_data,
        is_edit=True,
        product=product,
    )


@inventory.route('/<int:product_id>/delete', methods=['POST'])
@admin_required
def delete(product_id):
    """Deactivate a product (soft delete)."""
    product = _load_product_or_404(product_id)
    product.is_active = False
    db.session.commit()
    current_app.logger.info("Admin deactivated product: %s", product.name)
    flash(f'Product "{product.name}" archived.', 'success')
    return redirect(url_for('inventory.index'))


@inventory.route('/<int:product_id>/restore', methods=['POST'])
@admin_required
def restore(product_id):
    """Reactivate an archived product."""
    product = _load_product_or_404(product_id)
    product.is_active = True
    db.session.commit()
    current_app.logger.info("Admin restored product: %s", product.name)
    flash(f'Product "{product.name}" restored successfully.', 'success')
    return redirect(url_for('inventory.index'))


@inventory.route('/<int:product_id>/variants')
@admin_required
def variants(product_id):
    """Show active variants for a product and add-variant form."""
    product = _load_product_or_404(product_id)
    return _render_variants_page(product)


@inventory.route('/variant/<int:variant_id>/print-label')
@admin_required
def print_variant_label(variant_id):
    """
    Generate a small printable PDF label for a variant.
    Includes product name, size, color, price, and barcode image.
    """
    variant = db.session.get(ProductVariant, variant_id)
    if variant is None or variant.product is None:
        abort(404)

    try:
        barcode_image, barcode_type = _generate_variant_barcode_image(variant.barcode)

        from reportlab.lib.units import mm
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas

        label_width = 50 * mm
        label_height = 30 * mm
        margin = 2.5 * mm

        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=(label_width, label_height))
        pdf.setTitle(f'Label {variant.id}')

        name = (variant.product.name or '').strip()
        if len(name) > 30:
            name = f'{name[:27]}...'

        detail = f'{variant.size}/{variant.color}'
        price_text = f'Rs {Decimal(str(variant.price)).quantize(Decimal("0.01"))}'

        pdf.setFont('Helvetica-Bold', 7.5)
        pdf.drawString(margin, label_height - margin - 1.5 * mm, name)
        pdf.setFont('Helvetica', 6.5)
        pdf.drawString(margin, label_height - margin - 5.0 * mm, detail)
        pdf.drawRightString(label_width - margin, label_height - margin - 5.0 * mm, price_text)

        image_reader = ImageReader(barcode_image)
        barcode_x = margin
        barcode_y = margin + 4.0 * mm
        barcode_w = label_width - (2 * margin)
        barcode_h = 14 * mm
        pdf.drawImage(
            image_reader,
            barcode_x,
            barcode_y,
            width=barcode_w,
            height=barcode_h,
            preserveAspectRatio=True,
            mask='auto',
        )

        pdf.setFont('Helvetica', 6)
        pdf.drawCentredString(label_width / 2, margin + 1.2 * mm, f'{variant.barcode} ({barcode_type})')

        pdf.showPage()
        pdf.save()
        buffer.seek(0)

        filename = f'label_variant_{variant.id}.pdf'
        response = send_file(
            buffer,
            mimetype='application/pdf',
            as_attachment=False,
            download_name=filename,
        )
        response.headers['Cache-Control'] = 'no-store'
        return response

    except Exception as exc:
        current_app.logger.exception('Variant label generation failed for variant_id=%s: %s', variant_id, exc)
        flash('Unable to generate barcode label. Check barcode value and installed dependencies.', 'error')
        return redirect(url_for('inventory.variants', product_id=variant.product_id))


@inventory.route('/<int:product_id>/variants/add', methods=['POST'])
@admin_required
def add_variant(product_id):
    """Create a new variant for a product."""
    product = _load_product_or_404(product_id)
    form_data = request.form.to_dict()
    errors = validate_variant_form(form_data)

    if not errors:
        size = form_data.get('size', '').strip()
        color = form_data.get('color', '').strip()
        barcode = form_data.get('barcode', '').strip()

        if _find_size_color_conflict(product.id, size, color):
            errors['size_color'] = 'This product already has that size/color combination.'

        barcode_conflict = ProductVariant.query.filter_by(barcode=barcode).first()
        if barcode_conflict:
            errors['barcode'] = 'A variant with this barcode already exists.'

    if errors:
        return _render_variants_page(product, errors=errors, form_data=form_data), 400

    old_stock = product.total_stock
    variant = ProductVariant(product_id=product.id, **parse_variant_form(form_data))
    try:
        db.session.add(variant)
        db.session.flush()
        db.session.add(
            InventoryLog(
                product_id=product.id,
                old_stock=old_stock,
                new_stock=old_stock + variant.stock,
                changed_by=session.get('user_id'),
                reason=f'Variant Added ({variant.size}/{variant.color})',
            )
        )
        db.session.commit()
        flash('Variant added successfully.', 'success')
        return redirect(url_for('inventory.variants', product_id=product.id))
    except IntegrityError:
        db.session.rollback()
        errors['barcode'] = 'A variant with this barcode already exists.'
        return _render_variants_page(product, errors=errors, form_data=form_data), 400


@inventory.route('/<int:product_id>/variants/<int:variant_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_variant(product_id, variant_id):
    """Edit an existing variant."""
    product = _load_product_or_404(product_id)
    variant = ProductVariant.query.filter_by(id=variant_id, product_id=product.id).first()
    if variant is None:
        abort(404)

    errors = {}
    if request.method == 'POST':
        form_data = request.form.to_dict()
        errors = validate_variant_form(form_data)

        if not errors:
            size = form_data.get('size', '').strip()
            color = form_data.get('color', '').strip()
            barcode = form_data.get('barcode', '').strip()

            if _find_size_color_conflict(product.id, size, color, exclude_variant_id=variant.id):
                errors['size_color'] = 'This product already has that size/color combination.'

            barcode_conflict = ProductVariant.query.filter(
                ProductVariant.barcode == barcode,
                ProductVariant.id != variant.id,
            ).first()
            if barcode_conflict:
                errors['barcode'] = 'A variant with this barcode already exists.'

        if not errors:
            old_stock = product.total_stock
            data = parse_variant_form(form_data)
            data.pop('is_active', None)
            for field, value in data.items():
                setattr(variant, field, value)

            try:
                db.session.flush()
                db.session.add(
                    InventoryLog(
                        product_id=product.id,
                        old_stock=old_stock,
                        new_stock=product.total_stock,
                        changed_by=session.get('user_id'),
                        reason=f'Variant Updated ({variant.size}/{variant.color})',
                    )
                )
                db.session.commit()
                flash('Variant updated successfully.', 'success')
                return redirect(url_for('inventory.variants', product_id=product.id))
            except IntegrityError:
                db.session.rollback()
                errors['barcode'] = 'A variant with this barcode already exists.'
    else:
        form_data = {
            'size': variant.size,
            'color': variant.color,
            'sku': variant.sku or '',
            'barcode': variant.barcode,
            'price': str(variant.price),
            'stock': str(variant.stock),
        }

    return render_template(
        'inventory/variant_form.html',
        title=f'Edit Variant - {product.name}',
        product=product,
        variant=variant,
        errors=errors,
        form_data=form_data,
        form_action=url_for('inventory.edit_variant', product_id=product.id, variant_id=variant.id),
    )


@inventory.route('/<int:product_id>/variants/<int:variant_id>/delete', methods=['POST'])
@admin_required
def delete_variant(product_id, variant_id):
    """Soft-delete a variant from inventory screens."""
    product = _load_product_or_404(product_id)
    variant = ProductVariant.query.filter_by(id=variant_id, product_id=product.id).first()
    if variant is None:
        abort(404)

    if not variant.is_active:
        flash('Variant is already inactive.', 'warning')
        return redirect(url_for('inventory.variants', product_id=product.id))

    old_stock = product.total_stock
    variant.is_active = False

    db.session.add(
        InventoryLog(
            product_id=product.id,
            old_stock=old_stock,
            new_stock=max(0, old_stock - variant.stock),
            changed_by=session.get('user_id'),
            reason=f'Variant Deactivated ({variant.size}/{variant.color})',
        )
    )
    db.session.commit()
    flash('Variant deleted successfully.', 'success')
    return redirect(url_for('inventory.variants', product_id=product.id))


@inventory.route('/<int:product_id>/logs')
@admin_required
def logs(product_id):
    """View inventory logs for a product."""
    product = _load_product_or_404(product_id)
    product_logs = (
        InventoryLog.query
        .filter_by(product_id=product_id)
        .order_by(InventoryLog.timestamp.desc())
        .all()
    )
    return render_template(
        'inventory/logs.html',
        title=f'Logs: {product.name}',
        product=product,
        logs=product_logs,
    )


@inventory.route('/<int:product_id>/batches')
@admin_required
def batches(product_id):
    """View batches for a product."""
    product = _load_product_or_404(product_id)
    today = date.today()
    alert_threshold = today + timedelta(days=14)

    all_batches = (
        ProductBatch.query
        .filter_by(product_id=product_id)
        .filter(ProductBatch.quantity > 0)
        .order_by(
            db.case((ProductBatch.expiry_date.is_(None), 1), else_=0),
            ProductBatch.expiry_date.asc(),
        )
        .all()
    )

    return render_template(
        'inventory/batches.html',
        title=f'Batches - {product.name}',
        product=product,
        batches=all_batches,
        today=today,
        alert_threshold=alert_threshold,
    )


@inventory.route('/<int:product_id>/batches/add', methods=['GET', 'POST'])
@admin_required
def add_batch(product_id):
    """Receive stock into a batch and map quantity to the default variant."""
    product = _load_product_or_404(product_id)
    errors = {}
    form_data = {}

    if request.method == 'POST':
        form_data = request.form.to_dict()
        batch_number = form_data.get('batch_number', '').strip()
        expiry_str = form_data.get('expiry_date', '').strip()
        qty_str = form_data.get('quantity', '').strip()
        cost_str = form_data.get('cost_price', '').strip()

        if not batch_number:
            errors['batch_number'] = 'Batch number is required.'
        if not qty_str.isdigit() or int(qty_str) <= 0:
            errors['quantity'] = 'Quantity must be a positive integer.'

        expiry_date = None
        if expiry_str:
            try:
                from datetime import datetime as _dt
                expiry_date = _dt.strptime(expiry_str, '%Y-%m-%d').date()
                if expiry_date <= date.today():
                    errors['expiry_date'] = 'Expiry date must be in the future.'
            except ValueError:
                errors['expiry_date'] = 'Invalid date format.'

        from decimal import Decimal, InvalidOperation
        cost_price = None
        if cost_str:
            try:
                cost_price = Decimal(cost_str)
                if cost_price < 0:
                    errors['cost_price'] = 'Cost price cannot be negative.'
            except InvalidOperation:
                errors['cost_price'] = 'Invalid cost price.'

        target_variant = product.default_variant
        if target_variant is None:
            errors['quantity'] = 'Add at least one active variant before receiving stock.'

        if not errors:
            qty = int(qty_str)
            old_stock = product.total_stock
            existing = ProductBatch.query.filter_by(
                product_id=product_id,
                batch_number=batch_number,
            ).first()

            if existing:
                existing.quantity += qty
                if cost_price is not None:
                    existing.cost_price = cost_price
                if expiry_date is not None:
                    existing.expiry_date = expiry_date
            else:
                db.session.add(
                    ProductBatch(
                        product_id=product_id,
                        batch_number=batch_number,
                        expiry_date=expiry_date,
                        quantity=qty,
                        cost_price=cost_price,
                    )
                )

            target_variant.stock += qty
            db.session.add(
                InventoryLog(
                    product_id=product.id,
                    old_stock=old_stock,
                    new_stock=old_stock + qty,
                    changed_by=session.get('user_id'),
                    reason=f'Stock received - Batch {batch_number}',
                )
            )
            db.session.commit()

            current_app.logger.info(
                "Batch %r added for %s: +%s units",
                batch_number,
                product.name,
                qty,
            )
            flash(f'Received {qty} units into batch "{batch_number}".', 'success')
            return redirect(url_for('inventory.batches', product_id=product_id))

    return render_template(
        'inventory/add_batch.html',
        title=f'Receive Stock - {product.name}',
        product=product,
        errors=errors,
        form_data=form_data,
    )
