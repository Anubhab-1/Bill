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

@main.route("/fix-db-schema-now")
def fix_db_schema_now():
    """Emergency route to manually trigger DB migration."""
    from app.migration import run_auto_migration
    from flask import current_app
    
    try:
        run_auto_migration(current_app._get_current_object())
        return "✅ Migration triggered. Check logs. If no errors, DB is fixed.", 200
    except Exception as e:
        return f"❌ Migration failed: {str(e)}", 500


@main.route("/health")
def health():
    """Health check for load balancers and monitoring."""
    from datetime import datetime
    import shutil
    import os
    from flask import current_app, request

    status = "ok"
    failures = []
    
    # 1. DB Check
    try:
        from sqlalchemy import text
        db.session.execute(text("SELECT 1"))
    except Exception as e:
        status = "error"
        failures.append(f"DB: {str(e)}")
        current_app.logger.error(f"Health check failed (DB): {e}")

    # 2. Disk Check
    try:
        total, used, free = shutil.disk_usage("/")
        free_gb = free // (2**30)
        total_gb = total // (2**30)
        percent_free = (free / total) * 100
        
        if percent_free < 10:
            msg = f"Low Disk Space: {free_gb}GB free ({percent_free:.1f}%)"
            failures.append(msg)
            current_app.logger.warning(msg)
            # Optional: Email Alert (simple implementation)
            _send_alert_email("Critical: Low Disk Space", msg)
            if status == "ok": status = "warning"
            
    except Exception as e:
        failures.append(f"Disk Check Error: {str(e)}")
        if status == "ok": status = "warning"

    response = {
        "status": status,
        "timestamp": datetime.utcnow().isoformat(),
        "details": {
            "db": "ok" if not any("DB" in f for f in failures) else "error",
            "disk_free_gb": free_gb,
            "disk_free_percent": round(percent_free, 1)
        }
    }
    
    if failures:
        response["failures"] = failures
        
    # HTMX Support for Dashboard Widget
    if request.headers.get("HX-Request"):
        from flask import render_template_string
        
        # Color logic
        db_color = "green" if response["details"]["db"] == "ok" else "red"
        disk_color = "green" if response["details"]["disk_free_percent"] > 20 else ("yellow" if response["details"]["disk_free_percent"] > 10 else "red")
        
        html = f"""
        <div class="flex items-center justify-between py-2.5 border-b border-gray-800">
            <div class="flex items-center gap-3">
                <span class="w-2 h-2 rounded-full bg-{db_color}-400"></span>
                <span class="text-sm text-gray-300">Database</span>
            </div>
            <span class="text-xs px-2.5 py-1 rounded-full font-medium bg-{db_color}-500/10 text-{db_color}-400">
                {response["details"]["db"].upper()}
            </span>
        </div>
        <div class="flex items-center justify-between py-2.5 border-b border-gray-800 last:border-0">
            <div class="flex items-center gap-3">
                <span class="w-2 h-2 rounded-full bg-{disk_color}-400"></span>
                <span class="text-sm text-gray-300">Disk Space</span>
            </div>
            <div class="text-right">
                <span class="text-xs px-2.5 py-1 rounded-full font-medium bg-{disk_color}-500/10 text-{disk_color}-400">
                    {response["details"]["disk_free_percent"]}% Free
                </span>
                <div class="text-[10px] text-gray-500 mt-0.5">{response["details"]["disk_free_gb"]} GB Avail</div>
            </div>
        </div>
        """
        return html, 200

    return response, 200 if status != "error" else 500

def _send_alert_email(subject, body):
    """Simple email alert helper. Logs if mail not configured."""
    from flask import current_app
    # Check if we have mail config
    if not current_app.config.get('MAIL_SERVER'):
        current_app.logger.info(f"Alert (No Mail Config): {subject} - {body}")
        return

    # In a real app, use Flask-Mail or SMTP here
    # For now, we simulate it clearly in logs
    current_app.logger.critical(f"SENDING EMAIL ALERT: {subject} \n {body}")

@main.route('/')
@login_required
def index():
    """Homepage — Mall Billing System dashboard."""
    from app.inventory.models import Product, LOW_STOCK_THRESHOLD, ProductBatch
    from app.billing.models import Sale, SaleItem
    from datetime import timedelta

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

    # ── Expiry alerts ─────────────────────────────────────────────
    alert_cutoff = today + timedelta(days=14)
    expiring_soon = (
        db.session.query(ProductBatch, Product)
        .join(Product, Product.id == ProductBatch.product_id)
        .filter(
            ProductBatch.quantity > 0,
            ProductBatch.expiry_date.isnot(None),
            ProductBatch.expiry_date >= today,
            ProductBatch.expiry_date <= alert_cutoff,
        )
        .order_by(ProductBatch.expiry_date.asc())
        .limit(8)
        .all()
    )
    expired_batches = (
        db.session.query(ProductBatch, Product)
        .join(Product, Product.id == ProductBatch.product_id)
        .filter(
            ProductBatch.quantity > 0,
            ProductBatch.expiry_date.isnot(None),
            ProductBatch.expiry_date < today,
        )
        .order_by(ProductBatch.expiry_date.asc())
        .limit(5)
        .all()
    )

    # ── Pending Purchase Orders ────────────────────────────────────
    try:
        from app.purchasing.models import PurchaseOrder, POStatus
        pending_pos = (
            PurchaseOrder.query
            .filter(PurchaseOrder.status.in_([POStatus.DRAFT, POStatus.SENT, POStatus.PARTIAL]))
            .order_by(PurchaseOrder.expected_date.asc().nulls_last())
            .limit(5)
            .all()
        )
        pending_po_count = (
            PurchaseOrder.query
            .filter(PurchaseOrder.status.in_([POStatus.DRAFT, POStatus.SENT, POStatus.PARTIAL]))
            .count()
        )
    except Exception:
        pending_pos = []
        pending_po_count = 0

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
        # Expiry alerts
        expiring_soon=expiring_soon,
        expired_batches=expired_batches,
        # Purchasing
        pending_pos=pending_pos,
        pending_po_count=pending_po_count,
    )
