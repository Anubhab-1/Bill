"""
app/reporting/routes.py
-----------------------
Reporting & Analytics routes.
"""
import csv
import io
from datetime import datetime, date, timedelta
from decimal import Decimal

from flask import (
    render_template, request, Response, stream_with_context,
    current_app, url_for
)
from sqlalchemy import func, case, desc, Date, cast

from app.reporting import reporting
from app.auth.decorators import admin_required
from app import db
from app.billing.models import Sale, SaleItem, SalePayment
from app.inventory.models import Product, ProductBatch, ProductVariant
from app.purchasing.models import PurchaseOrder, PurchaseOrderItem, POStatus


# ── Helpers ───────────────────────────────────────────────────────

def _get_date_range():
    """Parse start/end dates from query params, default to current month."""
    today = date.today()
    start_str = request.args.get('start_date')
    end_str   = request.args.get('end_date')

    if start_str:
        start_date = date.fromisoformat(start_str)
    else:
        # Default to 1st of this month
        start_date = today.replace(day=1)

    if end_str:
        end_date = date.fromisoformat(end_str)
    else:
        end_date = today

    return start_date, end_date


def _get_datetime_bounds():
    """
    Build an index-friendly datetime range:
      created_at >= start_dt AND created_at < end_dt_exclusive
    """
    start_date, end_date = _get_date_range()
    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt_exclusive = datetime.combine(end_date + timedelta(days=1), datetime.min.time())
    return start_date, end_date, start_dt, end_dt_exclusive


# ── Dashboard ─────────────────────────────────────────────────────

@reporting.route('/')
@admin_required
def index():
    today = date.today()
    
    # 1. Today's Sales
    today_sales_total = db.session.query(
        func.sum(func.coalesce(Sale.grand_total, Sale.total_amount + Sale.gst_total))
    )\
        .filter(cast(Sale.created_at, Date) == today).scalar() or Decimal('0')
    
    today_sales_count = db.session.query(func.count(Sale.id))\
        .filter(cast(Sale.created_at, Date) == today).scalar() or 0

    # 2. This Month's Sales
    month_start = today.replace(day=1)
    month_sales_total = db.session.query(
        func.sum(func.coalesce(Sale.grand_total, Sale.total_amount + Sale.gst_total))
    )\
        .filter(cast(Sale.created_at, Date) >= month_start).scalar() or Decimal('0')

    # 3. Inventory Value (Cost vs Selling)
    # Estimate cost using weighted average if available, else 0 (simplified)
    # Actually we have batches. Best is to sum(batch.qty * batch.cost) + sum(product.stock * product.price)
    # For speed, let's just use Product.price (Sales Value)
    total_stock_value_sales = db.session.query(
        func.sum(Product.stock * Product.price)
    ).filter(Product.is_active == True).scalar() or Decimal('0')

    # 4. Low Stock Items count
    low_stock_count = Product.query.filter(
        Product.is_active == True,
        Product.stock <= 5  # arbitrary threshold or use reorder_level if we had one
    ).count()

    return render_template('reporting/dashboard.html',
                           today_sales_total=today_sales_total,
                           today_sales_count=today_sales_count,
                           month_sales_total=month_sales_total,
                           stock_value=total_stock_value_sales,
                           low_stock_count=low_stock_count)


# ── Sales Report ──────────────────────────────────────────────────

@reporting.route('/sales')
@admin_required
def sales_report():
    start_date, end_date = _get_date_range()
    
    # Query sales in range
    # Join with User to show cashier name? Not strictly needed if just IDs
    sales = Sale.query.filter(
        cast(Sale.created_at, Date) >= start_date,
        cast(Sale.created_at, Date) <= end_date
    ).order_by(Sale.created_at.desc()).all()

    # Summaries
    total_revenue = sum(s.computed_grand_total for s in sales)
    total_gst     = sum(s.gst_total for s in sales)
    
    # Payment mode breakdown (approximate if mixed payments, 
    # but strictly we should query SalePayment table)
    # Let's aggregate SalePayment for these sales
    payment_stats = db.session.query(
        SalePayment.payment_method, func.sum(SalePayment.amount)
    ).join(Sale).filter(
        cast(Sale.created_at, Date) >= start_date,
        cast(Sale.created_at, Date) <= end_date
    ).group_by(SalePayment.payment_method).all()
    
    payment_summary = {mode: amt for mode, amt in payment_stats}

    return render_template('reporting/sales_report.html',
                           sales=sales,
                           start_date=start_date,
                           end_date=end_date,
                           total_revenue=total_revenue,
                           total_gst=total_gst,
                           payment_summary=payment_summary)


@reporting.route('/apparel')
@admin_required
def apparel_report():
    """
    Apparel analytics:
      1) Top selling sizes
      2) Top selling colors
      3) Sales by brand
      4) Sales by category
    All metrics are computed in SQL aggregation queries.
    """
    start_date, end_date, start_dt, end_dt_exclusive = _get_datetime_bounds()

    gross_sales_expr = SaleItem.subtotal + ((SaleItem.subtotal * SaleItem.gst_percent) / 100)
    brand_label = func.coalesce(func.nullif(Product.brand, ''), 'Unbranded')
    category_label = func.coalesce(func.nullif(Product.category, ''), 'Uncategorized')

    top_sizes = (
        db.session.query(
            SaleItem.snapshot_size.label('size'),
            func.sum(SaleItem.quantity).label('units_sold'),
            func.sum(gross_sales_expr).label('gross_sales'),
        )
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(
            Sale.created_at >= start_dt,
            Sale.created_at < end_dt_exclusive,
            SaleItem.snapshot_size.isnot(None),
            SaleItem.snapshot_size != '',
        )
        .group_by(SaleItem.snapshot_size)
        .order_by(desc('units_sold'), desc('gross_sales'))
        .limit(10)
        .all()
    )

    top_colors = (
        db.session.query(
            SaleItem.snapshot_color.label('color'),
            func.sum(SaleItem.quantity).label('units_sold'),
            func.sum(gross_sales_expr).label('gross_sales'),
        )
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(
            Sale.created_at >= start_dt,
            Sale.created_at < end_dt_exclusive,
            SaleItem.snapshot_color.isnot(None),
            SaleItem.snapshot_color != '',
        )
        .group_by(SaleItem.snapshot_color)
        .order_by(desc('units_sold'), desc('gross_sales'))
        .limit(10)
        .all()
    )

    sales_by_brand = (
        db.session.query(
            brand_label.label('brand'),
            func.sum(SaleItem.quantity).label('units_sold'),
            func.sum(gross_sales_expr).label('gross_sales'),
        )
        .join(ProductVariant, ProductVariant.id == SaleItem.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(
            Sale.created_at >= start_dt,
            Sale.created_at < end_dt_exclusive,
        )
        .group_by(brand_label)
        .order_by(desc('gross_sales'))
        .all()
    )

    sales_by_category = (
        db.session.query(
            category_label.label('category'),
            func.sum(SaleItem.quantity).label('units_sold'),
            func.sum(gross_sales_expr).label('gross_sales'),
        )
        .join(ProductVariant, ProductVariant.id == SaleItem.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(
            Sale.created_at >= start_dt,
            Sale.created_at < end_dt_exclusive,
        )
        .group_by(category_label)
        .order_by(desc('gross_sales'))
        .all()
    )

    return render_template(
        'reporting/apparel_report.html',
        start_date=start_date,
        end_date=end_date,
        top_sizes=top_sizes,
        top_colors=top_colors,
        sales_by_brand=sales_by_brand,
        sales_by_category=sales_by_category,
    )


# ── GST Report ────────────────────────────────────────────────────

@reporting.route('/gst')
@admin_required
def gst_report():
    start_date, end_date = _get_date_range()

    # Output Tax (Sales) - Grouped by GST %
    # Need to join SaleItem -> Product to get % info, or store it on SaleItem snapshot
    # SaleItem has 'price' (unit price at sale), but likely we didn't store gst_percent on SaleItem
    # We should have... let's check model. SaleItem has `date`? No.
    # We must rely on Product.gst_percent (current) which is a limitation if it changed.
    # PRO-TIP: Real systems snapshot tax rates. We'll use Product.gst_percent for now.
    
    output_tax_data = db.session.query(
        SaleItem.gst_percent,
        func.sum(SaleItem.subtotal)
    ).join(Sale, SaleItem.sale_id == Sale.id)\
     .filter(
         cast(Sale.created_at, Date) >= start_date,
         cast(Sale.created_at, Date) <= end_date
     ).group_by(SaleItem.gst_percent).all()

    # Calc tax amounts
    gst_summary = []
    total_output_tax = Decimal('0')
    total_taxable_value = Decimal('0')

    for gst_pct, taxable_val in output_tax_data:
        if not taxable_val: continue
        tax_amt = (taxable_val * gst_pct / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        gst_summary.append({
            'rate': gst_pct,
            'taxable': taxable_val,
            'tax': tax_amt
        })
        total_output_tax += tax_amt
        total_taxable_value += taxable_val

    # Input Tax (Purchases) - from POs marked RECEIVED
    # Similar limitation: need historical tax rate. We'll use Product.gst_percent
    input_tax_data = db.session.query(
        Product.gst_percent,
        func.sum(PurchaseOrderItem.ordered_qty * PurchaseOrderItem.unit_cost)
    ).join(Product, PurchaseOrderItem.product_id == Product.id)\
     .join(PurchaseOrder, PurchaseOrderItem.po_id == PurchaseOrder.id)\
     .filter(
         PurchaseOrder.status == POStatus.RECEIVED,
         # Filter by expected_date or updated_at? Let's use updated_at as proxy for receipt
         cast(PurchaseOrder.updated_at, Date) >= start_date,
         cast(PurchaseOrder.updated_at, Date) <= end_date
     ).group_by(Product.gst_percent).all()

    input_summary = []
    total_input_tax = Decimal('0')

    for gst_pct, purch_val in input_tax_data:
        if not purch_val: continue
        # PurchaseOrderItem.unit_cost is typically ex-tax? Or user entered incl-tax?
        # Let's assume ex-tax for calculation
        tax_amt = (purch_val * gst_pct / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        input_summary.append({
            'rate': gst_pct,
            'purchase_val': purch_val,
            'tax': tax_amt
        })
        total_input_tax += tax_amt

    return render_template('reporting/gst_report.html',
                           start_date=start_date,
                           end_date=end_date,
                           output_summary=gst_summary,
                           total_output_tax=total_output_tax,
                           total_taxable_value=total_taxable_value,
                           input_summary=input_summary,
                           total_input_tax=total_input_tax)


# ── Inventory Report ──────────────────────────────────────────────

@reporting.route('/inventory')
@admin_required
def inventory_report():
    # List all products with stock value
    products = Product.query.filter(Product.is_active == True).order_by(Product.name).all()
    
    inventory_data = []
    total_valuation = Decimal('0')
    
    for p in products:
        value = p.stock * p.price
        inventory_data.append({
            'name': p.name,
            'barcode': p.barcode,
            'stock': p.stock,
            'price': p.price,
            'value': value,
            'gst': p.gst_percent
        })
        total_valuation += value

    # Sort checks: Low stock first
    inventory_data.sort(key=lambda x: x['stock'])

    return render_template('reporting/inventory_report.html',
                           inventory=inventory_data,
                           total_valuation=total_valuation)


# ── CSV Export ────────────────────────────────────────────────────

@reporting.route('/export/<report_type>')
@admin_required
def export_csv(report_type):
    start_date, end_date = _get_date_range()
    
    def generate():
        data = io.StringIO()
        w = csv.writer(data)

        if report_type == 'sales':
            w.writerow(['Date', 'Invoice #', 'Cashier ID', 'Total Amount', 'GST Total', 'Items'])
            yield data.getvalue()
            data.seek(0)
            data.truncate(0)

            sales = Sale.query.filter(
                cast(Sale.created_at, Date) >= start_date,
                cast(Sale.created_at, Date) <= end_date
            ).order_by(Sale.created_at.desc()).all()

            for s in sales:
                item_count = sum(i.quantity for i in s.items)
                w.writerow([
                    s.created_at.strftime('%Y-%m-%d %H:%M'),
                    s.invoice_number,
                    s.cashier_id,
                    s.computed_grand_total,
                    s.gst_total,
                    item_count
                ])
                yield data.getvalue()
                data.seek(0)
                data.truncate(0)

        elif report_type == 'inventory':
            w.writerow(['Barcode', 'Product Name', 'Stock', 'Price', 'GST %', 'Value'])
            yield data.getvalue()
            data.seek(0)
            data.truncate(0)

            products = Product.query.filter(Product.is_active == True).order_by(Product.name).all()
            for p in products:
                w.writerow([
                    p.barcode,
                    p.name,
                    p.stock,
                    p.price,
                    p.gst_percent,
                    p.stock * p.price
                ])
                yield data.getvalue()
                data.seek(0)
                data.truncate(0)
        
        # Add GST export if needed

    headers = {
        'Content-Disposition': f'attachment; filename={report_type}_report_{date.today()}.csv',
        'Content-Type': 'text/csv'
    }
    return Response(stream_with_context(generate()), headers=headers)
