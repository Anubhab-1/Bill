"""
app/reports/routes.py
──────────────────────
Phase 5: Reporting & Owner Visibility

Routes:
  GET  /reports/                    → paginated sales list with filters
  GET  /reports/<sale_id>           → full sale detail (read-only)
  GET  /reports/export.csv          → filtered CSV download
  GET  /reports/cashier-summary     → sales grouped by cashier
"""
import csv
import io
from datetime import date, datetime, timedelta
from decimal import Decimal

from flask import render_template, request, redirect, url_for, flash, Response
from sqlalchemy import func, cast, Date, desc

from app import db
from app.reports import reports
from app.auth.models import User
from app.billing.models import Sale, SaleItem
from app.inventory.models import Product
from app.auth.decorators import admin_required

# ── Constants ─────────────────────────────────────────────────────
PAGE_SIZE = 20   # rows per page on the sales list


# ── Shared filter helper ──────────────────────────────────────────

def _apply_filters(query, start_str, end_str, cashier_id_str):
    """
    Apply date-range and cashier filters to a Sale query.

    Date filtering uses SQLAlchemy's cast(Sale.created_at, Date) so the
    comparison is purely date-based (ignores time component).

    Returns:
        (filtered_query, start_date, end_date, cashier_id)
        Dates are Python date objects (or None if not supplied).
    """
    start_date  = None
    end_date    = None
    cashier_id  = None

    # ── Date range ────────────────────────────────────────────────
    if start_str:
        try:
            start_date = datetime.strptime(start_str, '%Y-%m-%d').date()
            query = query.filter(cast(Sale.created_at, Date) >= start_date)
        except ValueError:
            pass   # ignore malformed date — don't crash

    if end_str:
        try:
            end_date = datetime.strptime(end_str, '%Y-%m-%d').date()
            query = query.filter(cast(Sale.created_at, Date) <= end_date)
        except ValueError:
            pass

    # ── Cashier filter ────────────────────────────────────────────
    if cashier_id_str:
        try:
            cashier_id = int(cashier_id_str)
            query = query.filter(Sale.cashier_id == cashier_id)
        except (ValueError, TypeError):
            pass

    return query, start_date, end_date, cashier_id


# ═══════════════════════════════════════════════════════════════════
# 1. SALES LIST  —  GET /reports/
# ═══════════════════════════════════════════════════════════════════

@reports.route('/')
@admin_required
def index():
    """
    Paginated, filterable sales list.

    Pagination: manual limit/offset (no Flask-SQLAlchemy paginate needed).
    Aggregation: func.sum for page-level totals.
    """
    # ── Query params ──────────────────────────────────────────────
    start_str      = request.args.get('start', '')
    end_str        = request.args.get('end', '')
    cashier_id_str = request.args.get('cashier', '')
    try:
        page = max(1, int(request.args.get('page', 1)))
    except (ValueError, TypeError):
        page = 1

    # ── Base query — newest first ─────────────────────────────────
    base_q = Sale.query.order_by(desc(Sale.created_at))
    base_q, start_date, end_date, cashier_id = _apply_filters(
        base_q, start_str, end_str, cashier_id_str
    )

    # ── Totals for the ENTIRE filtered result set ─────────────────
    # Re-apply the same filters to a fresh aggregation query.
    # func.coalesce prevents NULL when there are no matching rows.
    agg_q = db.session.query(
        func.count(Sale.id).label('total_count'),
        func.coalesce(func.sum(Sale.total_amount + Sale.gst_total), 0).label('grand_sum'),
        func.coalesce(func.avg(Sale.total_amount + Sale.gst_total), 0).label('avg_bill'),
    )
    agg_q, _, _, _ = _apply_filters(agg_q, start_str, end_str, cashier_id_str)
    agg = agg_q.first()

    total_count = agg.total_count or 0
    grand_sum   = Decimal(str(agg.grand_sum or 0))
    avg_bill    = Decimal(str(agg.avg_bill or 0))

    # ── Paginate ──────────────────────────────────────────────────
    # offset = how many rows to skip
    # limit  = how many rows to return
    total_pages = max(1, -(-total_count // PAGE_SIZE))   # ceiling division
    page        = min(page, total_pages)
    offset      = (page - 1) * PAGE_SIZE

    sales = base_q.offset(offset).limit(PAGE_SIZE).all()

    # ── Cashier list for filter dropdown ─────────────────────────
    cashiers = User.query.order_by(User.name).all()

    return render_template(
        'reports/index.html',
        title='Sales Reports',
        sales=sales,
        # Pagination
        page=page,
        total_pages=total_pages,
        total_count=total_count,
        page_size=PAGE_SIZE,
        # Aggregates
        grand_sum=grand_sum,
        avg_bill=avg_bill,
        # Filter state (passed back so form stays populated)
        start_str=start_str,
        end_str=end_str,
        cashier_id=cashier_id,
        cashiers=cashiers,
    )


# ═══════════════════════════════════════════════════════════════════
# 2. SALE DETAIL  —  GET /reports/<sale_id>
# ═══════════════════════════════════════════════════════════════════

@reports.route('/<int:sale_id>')
@admin_required
def detail(sale_id):
    """Full read-only invoice detail for admin review."""
    sale = db.session.get(Sale, sale_id)
    if sale is None:
        flash('Sale not found.', 'error')
        return redirect(url_for('reports.index'))

    return render_template(
        'reports/detail.html',
        title=f'Sale {sale.invoice_number}',
        sale=sale,
    )


# ═══════════════════════════════════════════════════════════════════
# 3. CASHIER SUMMARY  —  GET /reports/cashier-summary
# ═══════════════════════════════════════════════════════════════════

@reports.route('/cashier-summary')
@admin_required
def cashier_summary():
    """
    Sales grouped by cashier using SQLAlchemy aggregation.

    Query:
        SELECT users.name, COUNT(sales.id), SUM(total_amount + gst_total)
        FROM sales JOIN users ON sales.cashier_id = users.id
        GROUP BY users.id, users.name
        ORDER BY SUM(...) DESC
    """
    start_str      = request.args.get('start', '')
    end_str        = request.args.get('end', '')

    rows_q = db.session.query(
        User.id.label('cashier_id'),
        User.name.label('cashier_name'),
        func.count(Sale.id).label('tx_count'),
        func.coalesce(func.sum(Sale.total_amount + Sale.gst_total), 0).label('total_handled'),
        func.coalesce(func.avg(Sale.total_amount + Sale.gst_total), 0).label('avg_bill'),
    ).join(Sale, Sale.cashier_id == User.id)

    # Date filter on the joined query
    if start_str:
        try:
            start_date = datetime.strptime(start_str, '%Y-%m-%d').date()
            rows_q = rows_q.filter(cast(Sale.created_at, Date) >= start_date)
        except ValueError:
            start_str = ''
    if end_str:
        try:
            end_date = datetime.strptime(end_str, '%Y-%m-%d').date()
            rows_q = rows_q.filter(cast(Sale.created_at, Date) <= end_date)
        except ValueError:
            end_str = ''

    rows = (
        rows_q
        .group_by(User.id, User.name)
        .order_by(desc('total_handled'))
        .all()
    )

    # Convert Decimal-safe
    summary = [
        {
            'cashier_name':  r.cashier_name,
            'tx_count':      r.tx_count,
            'total_handled': Decimal(str(r.total_handled)),
            'avg_bill':      Decimal(str(r.avg_bill)),
        }
        for r in rows
    ]

    return render_template(
        'reports/cashier_summary.html',
        title='Cashier Summary',
        summary=summary,
        start_str=start_str,
        end_str=end_str,
    )


# ═══════════════════════════════════════════════════════════════════
# 4. CSV EXPORT  —  GET /reports/export.csv
# ═══════════════════════════════════════════════════════════════════

@reports.route('/export.csv')
@admin_required
def export_csv():
    """
    Stream a CSV of filtered sales to the browser.

    Uses Python's csv module + io.StringIO — no temp files, no disk I/O.
    The same _apply_filters() helper is reused so the CSV always matches
    what the user sees on the reports page.
    """
    start_str      = request.args.get('start', '')
    end_str        = request.args.get('end', '')
    cashier_id_str = request.args.get('cashier', '')

    # Fetch ALL matching rows (no pagination for export)
    q = Sale.query.order_by(desc(Sale.created_at))
    q, _, _, _ = _apply_filters(q, start_str, end_str, cashier_id_str)
    sales = q.all()

    # ── Build CSV in memory ───────────────────────────────────────
    buf = io.StringIO()
    writer = csv.writer(buf)

    # Header row
    writer.writerow([
        'Invoice Number',
        'Date',
        'Time',
        'Cashier',
        'Subtotal (excl. GST)',
        'GST Total',
        'Grand Total',
    ])

    # Data rows
    for sale in sales:
        writer.writerow([
            sale.invoice_number,
            sale.created_at.strftime('%Y-%m-%d'),
            sale.created_at.strftime('%H:%M:%S'),
            sale.cashier.name,
            f'{sale.total_amount:.2f}',
            f'{sale.gst_total:.2f}',
            f'{sale.grand_total:.2f}',
        ])

    # ── Build filename with date range ────────────────────────────
    today    = date.today().strftime('%Y%m%d')
    filename = f'sales_export_{today}.csv'
    if start_str:
        filename = f'sales_{start_str}_to_{end_str or today}.csv'

    # ── Return as file download ───────────────────────────────────
    return Response(
        buf.getvalue(),
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Type': 'text/csv; charset=utf-8',
        }
    )
