"""
app/purchasing/routes.py
All routes for the Supplier and Purchase Order system.
"""
from datetime import date
from decimal import Decimal, InvalidOperation

from flask import (
    render_template, redirect, url_for, request,
    flash, abort, session, current_app
)
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import db
from app.auth.decorators import login_required, admin_required
from app.purchasing import purchasing
from app.purchasing.models import (
    Supplier, PurchaseOrder, PurchaseOrderItem,
    GoodsReceipt, GoodsReceiptItem, POStatus
)
from app.inventory.models import Product, ProductBatch, InventoryLog


# Supplier routes
@purchasing.route('/suppliers')
@admin_required
def suppliers():
    """List all active suppliers."""
    all_suppliers = Supplier.query.order_by(Supplier.name.asc()).all()
    return render_template(
        'purchasing/suppliers/index.html',
        title='Suppliers',
        suppliers=all_suppliers,
    )


@purchasing.route('/suppliers/new', methods=['GET', 'POST'])
@admin_required
def new_supplier():
    """Create a new supplier."""
    errors = {}
    form_data = {}

    if request.method == 'POST':
        form_data = request.form.to_dict()
        name = form_data.get('name', '').strip()
        if not name:
            errors['name'] = 'Supplier name is required.'

        if not errors:
            supplier = Supplier(
                name=name,
                contact=form_data.get('contact', '').strip() or None,
                gst_no=form_data.get('gst_no', '').strip() or None,
                address=form_data.get('address', '').strip() or None,
            )
            db.session.add(supplier)
            db.session.commit()
            flash(f'Supplier "{supplier.name}" created.', 'success')
            return redirect(url_for('purchasing.suppliers'))

    return render_template(
        'purchasing/suppliers/form.html',
        title='New Supplier',
        form_action=url_for('purchasing.new_supplier'),
        errors=errors,
        form_data=form_data,
        is_edit=False,
    )


@purchasing.route('/suppliers/<int:supplier_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_supplier(supplier_id):
    """Edit an existing supplier."""
    supplier = db.session.get(Supplier, supplier_id)
    if not supplier:
        abort(404)

    errors = {}

    if request.method == 'POST':
        form_data = request.form.to_dict()
        name = form_data.get('name', '').strip()
        if not name:
            errors['name'] = 'Supplier name is required.'

        if not errors:
            supplier.name = name
            supplier.contact = form_data.get('contact', '').strip() or None
            supplier.gst_no = form_data.get('gst_no', '').strip() or None
            supplier.address = form_data.get('address', '').strip() or None
            db.session.commit()
            flash(f'Supplier "{supplier.name}" updated.', 'success')
            return redirect(url_for('purchasing.suppliers'))
    else:
        form_data = {
            'name': supplier.name,
            'contact': supplier.contact or '',
            'gst_no': supplier.gst_no or '',
            'address': supplier.address or '',
        }

    return render_template(
        'purchasing/suppliers/form.html',
        title=f'Edit - {supplier.name}',
        form_action=url_for('purchasing.edit_supplier', supplier_id=supplier_id),
        errors=errors,
        form_data=form_data,
        is_edit=True,
        supplier=supplier,
    )


# Purchase order routes
@purchasing.route('/')
@login_required
def index():
    """List all purchase orders, newest first. Filter by status."""
    status_filter = request.args.get('status', '')
    query = PurchaseOrder.query.order_by(PurchaseOrder.created_at.desc())
    if status_filter and status_filter in POStatus.__members__:
        query = query.filter(PurchaseOrder.status == POStatus[status_filter])
    pos = query.all()
    return render_template(
        'purchasing/index.html',
        title='Purchase Orders',
        pos=pos,
        POStatus=POStatus,
        status_filter=status_filter,
    )


@purchasing.route('/new', methods=['GET', 'POST'])
@admin_required
def new_po():
    """Create a new Purchase Order with line items."""
    suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()
    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()
    errors = {}
    form_data = {}

    if request.method == 'POST':
        form_data = request.form.to_dict(flat=False)
        supplier_id = request.form.get('supplier_id', '').strip()
        expected_date = request.form.get('expected_date', '').strip()
        notes = request.form.get('notes', '').strip()

        if not supplier_id:
            errors['supplier_id'] = 'Please select a supplier.'
        elif not db.session.get(Supplier, int(supplier_id)):
            errors['supplier_id'] = 'Invalid supplier.'

        product_ids = request.form.getlist('product_id[]')
        ordered_qtys = request.form.getlist('ordered_qty[]')
        unit_costs = request.form.getlist('unit_cost[]')

        line_items = []
        for i, (pid, qty, cost) in enumerate(zip(product_ids, ordered_qtys, unit_costs)):
            pid = pid.strip()
            qty = qty.strip()
            cost = cost.strip()
            if not pid:
                continue
            try:
                qty_int = int(qty)
                if qty_int <= 0:
                    raise ValueError
            except (ValueError, TypeError):
                errors[f'line_{i}'] = f'Row {i + 1}: quantity must be a positive integer.'
                continue
            try:
                cost_dec = Decimal(cost) if cost else None
            except InvalidOperation:
                errors[f'line_{i}_cost'] = f'Row {i + 1}: invalid unit cost.'
                continue
            line_items.append({'product_id': int(pid), 'qty': qty_int, 'cost': cost_dec})

        if not line_items:
            errors['items'] = 'Add at least one product line.'

        if not errors:
            exp_date = None
            if expected_date:
                try:
                    exp_date = date.fromisoformat(expected_date)
                except ValueError:
                    errors['expected_date'] = 'Invalid date format.'

        if not errors:
            po = PurchaseOrder(
                supplier_id=int(supplier_id),
                status=POStatus.DRAFT,
                created_by=session.get('user_id'),
                expected_date=exp_date,
                notes=notes or None,
            )
            db.session.add(po)
            db.session.flush()

            for li in line_items:
                db.session.add(PurchaseOrderItem(
                    po_id=po.id,
                    product_id=li['product_id'],
                    ordered_qty=li['qty'],
                    unit_cost=li['cost'],
                ))

            db.session.commit()
            flash(f'Purchase Order #{po.id} created.', 'success')
            return redirect(url_for('purchasing.po_detail', po_id=po.id))

    return render_template(
        'purchasing/new.html',
        title='New Purchase Order',
        suppliers=suppliers,
        products=products,
        errors=errors,
        form_data=form_data,
    )


@purchasing.route('/<int:po_id>')
@login_required
def po_detail(po_id):
    """View a single PO with all items and receipts."""
    po = db.session.get(PurchaseOrder, po_id)
    if not po:
        abort(404)
    return render_template(
        'purchasing/detail.html',
        title=f'PO #{po.id}',
        po=po,
        POStatus=POStatus,
    )


@purchasing.route('/<int:po_id>/send', methods=['POST'])
@admin_required
def send_po(po_id):
    """Mark a DRAFT PO as SENT."""
    po = db.session.get(PurchaseOrder, po_id)
    if not po:
        abort(404)
    if po.status != POStatus.DRAFT:
        flash('Only DRAFT orders can be marked as SENT.', 'warning')
        return redirect(url_for('purchasing.po_detail', po_id=po_id))
    po.status = POStatus.SENT
    db.session.commit()
    flash(f'PO #{po.id} marked as SENT.', 'success')
    return redirect(url_for('purchasing.po_detail', po_id=po_id))


@purchasing.route('/<int:po_id>/cancel', methods=['POST'])
@admin_required
def cancel_po(po_id):
    """Cancel a PO (DRAFT or SENT only)."""
    po = db.session.get(PurchaseOrder, po_id)
    if not po:
        abort(404)
    if po.status not in (POStatus.DRAFT, POStatus.SENT):
        flash('Only DRAFT or SENT orders can be cancelled.', 'warning')
        return redirect(url_for('purchasing.po_detail', po_id=po_id))
    po.status = POStatus.CANCELLED
    db.session.commit()
    flash(f'PO #{po.id} cancelled.', 'success')
    return redirect(url_for('purchasing.index'))


# GRN routes
@purchasing.route('/<int:po_id>/receive', methods=['GET', 'POST'])
@admin_required
def receive_po(po_id):
    """Create a Goods Receipt Note (GRN) for a PO."""
    po = db.session.get(PurchaseOrder, po_id)
    if not po:
        abort(404)
    if request.method == 'GET' and po.status not in (POStatus.SENT, POStatus.PARTIAL):
        flash('Only SENT or PARTIAL orders can receive a GRN.', 'warning')
        return redirect(url_for('purchasing.po_detail', po_id=po_id))

    errors = {}

    if request.method == 'POST':
        notes = request.form.get('notes', '').strip()

        grn_items = []
        for item in po.items:
            qty_str = request.form.get(f'qty_{item.id}', '0').strip()
            batch = request.form.get(f'batch_{item.id}', '').strip() or None
            expiry = request.form.get(f'expiry_{item.id}', '').strip()

            try:
                qty = int(qty_str)
            except (ValueError, TypeError):
                qty = 0

            if qty < 0:
                errors[f'qty_{item.id}'] = 'Quantity cannot be negative.'
                continue

            expiry_date = None
            if expiry:
                try:
                    expiry_date = date.fromisoformat(expiry)
                except ValueError:
                    errors[f'expiry_{item.id}'] = 'Invalid expiry date.'
                    continue

            if qty > 0:
                grn_items.append({
                    'po_item': item,
                    'qty': qty,
                    'batch': batch,
                    'expiry': expiry_date,
                })

        if not grn_items:
            errors['items'] = 'Enter at least one received quantity.'

        if not errors:
            try:
                po_locked = (
                    db.session.query(PurchaseOrder)
                    .filter(PurchaseOrder.id == po_id)
                    .with_for_update()
                    .first()
                )
                if not po_locked:
                    raise ValueError('Purchase order not found.')
                if po_locked.status in (POStatus.RECEIVED, POStatus.CANCELLED):
                    raise ValueError('Cannot receive against a closed PO.')
                if po_locked.status not in (POStatus.SENT, POStatus.PARTIAL):
                    raise ValueError('Only SENT or PARTIAL orders can receive a GRN.')

                requested_map = {entry['po_item'].id: entry for entry in grn_items}
                requested_item_ids = sorted(requested_map.keys())

                locked_items = (
                    db.session.query(PurchaseOrderItem)
                    .filter(
                        PurchaseOrderItem.po_id == po_locked.id,
                        PurchaseOrderItem.id.in_(requested_item_ids),
                    )
                    .order_by(PurchaseOrderItem.id.asc())
                    .with_for_update()
                    .all()
                )
                if len(locked_items) != len(requested_item_ids):
                    raise ValueError('Some PO lines are no longer available.')

                existing_receipts = (
                    db.session.query(GoodsReceiptItem)
                    .join(GoodsReceipt, GoodsReceiptItem.grn_id == GoodsReceipt.id)
                    .filter(
                        GoodsReceipt.po_id == po_locked.id,
                        GoodsReceiptItem.po_item_id.in_(requested_item_ids),
                    )
                    .with_for_update()
                    .all()
                )
                received_map = {}
                for receipt_item in existing_receipts:
                    received_map[receipt_item.po_item_id] = (
                        received_map.get(receipt_item.po_item_id, 0) + receipt_item.received_qty
                    )

                for po_item in locked_items:
                    qty_to_receive = requested_map[po_item.id]['qty']
                    already_received = received_map.get(po_item.id, 0)
                    remaining_qty = po_item.ordered_qty - already_received
                    if qty_to_receive > remaining_qty:
                        raise ValueError(
                            f'Over-receipt blocked for "{po_item.product.name}". '
                            f'Remaining: {remaining_qty}, requested: {qty_to_receive}.'
                        )

                grn = GoodsReceipt(
                    po_id=po_locked.id,
                    received_by=session.get('user_id'),
                    received_date=date.today(),
                    notes=notes or None,
                )
                db.session.add(grn)
                db.session.flush()

                for po_item in locked_items:
                    entry = requested_map[po_item.id]
                    qty = entry['qty']

                    db.session.add(GoodsReceiptItem(
                        grn_id=grn.id,
                        po_item_id=po_item.id,
                        received_qty=qty,
                        batch_number=entry['batch'],
                        expiry_date=entry['expiry'],
                    ))

                    product = (
                        db.session.query(Product)
                        .filter(Product.id == po_item.product_id)
                        .with_for_update()
                        .first()
                    )
                    if not product:
                        raise ValueError(f'Product {po_item.product_id} not found.')

                    old_stock = product.total_stock
                    target_variant = product.default_variant
                    if not target_variant:
                        raise ValueError(f'Product "{product.name}" has no active variants to receive stock into.')
                    target_variant.stock += qty

                    batch_num = entry['batch'] or f'GRN-{grn.id}'
                    matching_batches = (
                        db.session.query(ProductBatch)
                        .filter(
                            ProductBatch.product_id == product.id,
                            ProductBatch.batch_number == batch_num,
                        )
                        .order_by(ProductBatch.id.asc())
                        .with_for_update()
                        .all()
                    )

                    if matching_batches:
                        target_batch = matching_batches[0]
                        if len(matching_batches) > 1:
                            for duplicate_batch in matching_batches[1:]:
                                target_batch.quantity += duplicate_batch.quantity
                                if target_batch.expiry_date is None and duplicate_batch.expiry_date is not None:
                                    target_batch.expiry_date = duplicate_batch.expiry_date
                                if target_batch.cost_price is None and duplicate_batch.cost_price is not None:
                                    target_batch.cost_price = duplicate_batch.cost_price
                                db.session.delete(duplicate_batch)
                        target_batch.quantity += qty
                        if target_batch.expiry_date is None and entry['expiry'] is not None:
                            target_batch.expiry_date = entry['expiry']
                        if target_batch.cost_price is None and po_item.unit_cost is not None:
                            target_batch.cost_price = po_item.unit_cost
                    else:
                        db.session.add(ProductBatch(
                            product_id=product.id,
                            batch_number=batch_num,
                            quantity=qty,
                            expiry_date=entry['expiry'],
                            cost_price=po_item.unit_cost,
                        ))

                    db.session.add(InventoryLog(
                        product_id=product.id,
                        old_stock=old_stock,
                        new_stock=product.total_stock,
                        changed_by=session.get('user_id'),
                        reason='PO_RECEIVE',
                        reference=po_locked.id,
                    ))

                _update_po_status(po_locked)
                db.session.commit()
                flash(f'GRN #{grn.id} recorded. Stock updated.', 'success')
                return redirect(url_for('purchasing.grn_detail', po_id=po_locked.id, grn_id=grn.id))

            except ValueError as exc:
                db.session.rollback()
                errors['items'] = str(exc)
                flash(str(exc), 'error')
            except IntegrityError as exc:
                db.session.rollback()
                current_app.logger.error(f'GRN integrity error for PO {po_id}: {exc}')
                errors['items'] = 'Database constraint blocked this GRN. Please retry.'
                flash(errors['items'], 'error')
            except Exception as exc:
                db.session.rollback()
                current_app.logger.exception(f'GRN processing failed for PO {po_id}: {exc}')
                errors['items'] = 'Unexpected error while receiving GRN.'
                flash(errors['items'], 'error')

    return render_template(
        'purchasing/receive.html',
        title=f'Receive - PO #{po.id}',
        po=po,
        errors=errors,
    )


@purchasing.route('/<int:po_id>/grn/<int:grn_id>')
@login_required
def grn_detail(po_id, grn_id):
    """View a single GRN."""
    po = db.session.get(PurchaseOrder, po_id)
    grn = db.session.get(GoodsReceipt, grn_id)
    if not po or not grn or grn.po_id != po.id:
        abort(404)
    return render_template(
        'purchasing/grn_detail.html',
        title=f'GRN #{grn.id}',
        po=po,
        grn=grn,
    )


def _update_po_status(po: PurchaseOrder) -> None:
    """
    Recalculate PO status after a GRN.
    - All items fully received -> RECEIVED
    - Some items received -> PARTIAL
    """
    all_full = all(
        sum(
            receipt_item.received_qty
            for grn in po.receipts
            for receipt_item in grn.items
            if receipt_item.po_item_id == item.id
        ) >= item.ordered_qty
        for item in po.items
    )
    po.status = POStatus.RECEIVED if all_full else POStatus.PARTIAL
