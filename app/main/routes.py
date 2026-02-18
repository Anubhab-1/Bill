"""
app/main/routes.py
──────────────────
Dashboard — aggregates today's KPIs and top-selling products.
"""
from datetime import date
from decimal import Decimal

from flask import render_template
from sqlalchemy import func, cast, Date, desc

from app import db
from app.main import main
from app.auth.decorators import login_required


@main.route('/')
@login_required
def index():
    """Homepage — Mall Billing System dashboard."""
    from app.inventory.models import Product, LOW_STOCK_THRESHOLD
    from app.billing.models import Sale, SaleItem

    today = date.today()

    # ── Inventory stats ───────────────────────────────────────────
    product_count   = Product.query.count()
    low_stock_count = Product.query.filter(
        Product.stock <= LOW_STOCK_THRESHOLD
    ).count()

    # ── Today's billing KPIs ──────────────────────────────────────
    # Single query: count + sum + avg for today's sales
    today_agg = db.session.query(
        func.count(Sale.id).label('tx_count'),
        func.coalesce(func.sum(Sale.total_amount + Sale.gst_total), 0).label('revenue'),
        func.coalesce(func.avg(Sale.total_amount + Sale.gst_total), 0).label('avg_bill'),
    ).filter(
        cast(Sale.created_at, Date) == today
    ).first()

    todays_count   = today_agg.tx_count  if today_agg else 0
    todays_revenue = Decimal(str(today_agg.revenue  or 0))
    todays_avg     = Decimal(str(today_agg.avg_bill or 0))

    # ── Top 5 selling products today ─────────────────────────────
    # JOIN sale_items → sales (filtered to today) → products
    # GROUP BY product, ORDER BY total qty sold DESC, LIMIT 5
    top_products = db.session.query(
        Product.name.label('name'),
        func.sum(SaleItem.quantity).label('qty_sold'),
        func.sum(SaleItem.subtotal).label('revenue'),
    ).join(
        SaleItem, SaleItem.product_id == Product.id
    ).join(
        Sale, Sale.id == SaleItem.sale_id
    ).filter(
        cast(Sale.created_at, Date) == today
    ).group_by(
        Product.id, Product.name
    ).order_by(
        desc('qty_sold')
    ).limit(5).all()

    top_products_list = [
        {
            'name':    r.name,
            'qty':     r.qty_sold,
            'revenue': Decimal(str(r.revenue or 0)),
        }
        for r in top_products
    ]

    return render_template(
        'main/index.html',
        title='Dashboard',
        # Inventory
        product_count=product_count,
        low_stock_count=low_stock_count,
        low_stock_threshold=LOW_STOCK_THRESHOLD,
        # Billing KPIs
        todays_count=todays_count,
        todays_revenue=todays_revenue,
        todays_avg=todays_avg,
        # Top products
        top_products=top_products_list,
    )
