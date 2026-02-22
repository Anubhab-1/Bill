#!/usr/bin/env python3
"""
stress_test_pos.py

Realistic concurrent stress test for Mall POS over HTTP.

What it validates:
- 4+ concurrent counters running end-to-end sales flow
- invoice uniqueness (and burst sequentiality check)
- no negative stock for stress products
- stock deductions match quantities sold
- no HTTP 500 responses
- no deadlock/IntegrityError markers in app logs (if log file available)
- response-time metrics (avg / p95 / throughput)

This script does NOT modify application code.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import os
import random
import re
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Tuple

import requests
from sqlalchemy import create_engine, text


INVOICE_RE = re.compile(r"Invoice\s*#\s*([0-9]{4}-[0-9]{4,})", re.IGNORECASE)
FALLBACK_INVOICE_RE = re.compile(r"\b([0-9]{4}-[0-9]{4,})\b")
ADD_ITEM_ERROR_MARKERS = (
    "no product found",
    "out of stock",
    "insufficient stock",
    "limit reached",
    "please enter a barcode",
)
LOG_ERROR_RE = re.compile(
    r"(deadlock|serializationfailure|could not serialize|integrityerror|traceback)",
    re.IGNORECASE,
)
POOL_ERROR_MARKERS = ("queuepool limit", "timeouterror")


@dataclass
class RequestMetric:
    route: str
    status_code: int
    latency_ms: float
    ok: bool
    error: str = ""
    response_excerpt: str = ""


@dataclass
class StressState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    request_metrics: List[RequestMetric] = field(default_factory=list)
    complete_latencies_ms: List[float] = field(default_factory=list)
    invoice_numbers: List[str] = field(default_factory=list)
    expected_sold_by_barcode: Counter = field(default_factory=Counter)
    successful_sales: int = 0
    failed_sales: int = 0
    non_200_count: int = 0
    exception_count: int = 0
    burst_invoices: List[str] = field(default_factory=list)
    recovery_injections: int = 0
    recovery_successes: int = 0
    recovery_failures: int = 0
    sync_barrier_breaks: int = 0

    def add_metric(self, metric: RequestMetric) -> None:
        with self.lock:
            self.request_metrics.append(metric)
            if not metric.ok or metric.status_code != 200:
                self.non_200_count += 1
            if metric.route == "/billing/complete":
                self.complete_latencies_ms.append(metric.latency_ms)

    def add_sale_success(self, invoice_number: str, sold_counter: Counter, burst: bool = False) -> None:
        with self.lock:
            self.successful_sales += 1
            self.invoice_numbers.append(invoice_number)
            self.expected_sold_by_barcode.update(sold_counter)
            if burst:
                self.burst_invoices.append(invoice_number)

    def add_sale_failure(self) -> None:
        with self.lock:
            self.failed_sales += 1

    def add_exception(self) -> None:
        with self.lock:
            self.exception_count += 1

    def add_recovery_injection(self) -> None:
        with self.lock:
            self.recovery_injections += 1

    def add_recovery_success(self) -> None:
        with self.lock:
            self.recovery_successes += 1

    def add_recovery_failure(self) -> None:
        with self.lock:
            self.recovery_failures += 1

    def add_sync_barrier_break(self) -> None:
        with self.lock:
            self.sync_barrier_breaks += 1


def percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct
    low = int(k)
    high = min(low + 1, len(ordered) - 1)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (k - low)


def get_rss_bytes() -> Optional[int]:
    try:
        import psutil  # type: ignore

        return int(psutil.Process(os.getpid()).memory_info().rss)
    except Exception:
        return None


def fmt_bytes(num_bytes: Optional[int]) -> str:
    if num_bytes is None:
        return "N/A"
    value = float(num_bytes)
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_idx = 0
    while value >= 1024.0 and unit_idx < len(units) - 1:
        value /= 1024.0
        unit_idx += 1
    return f"{value:.2f} {units[unit_idx]}"


def parse_invoice_number(html: str) -> Optional[str]:
    m = INVOICE_RE.search(html)
    if m:
        return m.group(1)
    m = FALLBACK_INVOICE_RE.search(html)
    if m:
        return m.group(1)
    return None


def to_money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def build_payment_payload(total_due: Decimal, rng: random.Random) -> Dict[str, str]:
    mode = rng.choice(["cash", "card", "upi", "mixed"])
    payload = {
        "payment_cash": "0",
        "payment_card": "0",
        "payment_upi": "0",
        "payment_loyalty": "0",
        "payment_gift": "0",
    }
    if mode == "cash":
        payload["payment_cash"] = to_money(total_due)
    elif mode == "card":
        payload["payment_card"] = to_money(total_due)
    elif mode == "upi":
        payload["payment_upi"] = to_money(total_due)
    else:
        cash_part = (total_due * Decimal(str(rng.uniform(0.3, 0.7)))).quantize(Decimal("0.01"))
        rest = total_due - cash_part
        payload["payment_cash"] = to_money(cash_part)
        payload["payment_card"] = to_money(rest)
    return payload


def request_with_metrics(
    sess: requests.Session,
    method: str,
    url: str,
    route: str,
    state: StressState,
    timeout: int,
    **kwargs,
) -> requests.Response:
    start = time.perf_counter()
    try:
        resp = sess.request(method, url, timeout=timeout, allow_redirects=True, **kwargs)
        latency_ms = (time.perf_counter() - start) * 1000.0
        excerpt = ""
        if resp.status_code >= 500:
            try:
                excerpt = (resp.text or "")[:500]
            except Exception:
                excerpt = ""
        state.add_metric(
            RequestMetric(
                route=route,
                status_code=resp.status_code,
                latency_ms=latency_ms,
                ok=True,
                response_excerpt=excerpt,
            )
        )
        return resp
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000.0
        state.add_metric(RequestMetric(route=route, status_code=0, latency_ms=latency_ms, ok=False, error=str(exc)))
        raise


def ensure_login_and_open_session(
    sess: requests.Session,
    base_url: str,
    username: str,
    password: str,
    opening_cash: Decimal,
    state: StressState,
    timeout: int,
) -> bool:
    login_resp = request_with_metrics(
        sess,
        "POST",
        f"{base_url}/auth/login",
        "/auth/login",
        state,
        timeout,
        data={"username": username, "password": password},
    )
    if login_resp.status_code != 200:
        return False

    billing_resp = request_with_metrics(
        sess,
        "GET",
        f"{base_url}/billing/",
        "/billing",
        state,
        timeout,
    )
    if billing_resp.status_code != 200:
        return False

    on_open_session_page = (
        "/billing/session/open" in billing_resp.url
        or "Start Your Shift" in billing_resp.text
        or "Opening Cash" in billing_resp.text
    )
    if on_open_session_page:
        open_resp = request_with_metrics(
            sess,
            "POST",
            f"{base_url}/billing/session/open",
            "/billing/session/open",
            state,
            timeout,
            data={"opening_cash": to_money(opening_cash)},
        )
        if open_resp.status_code != 200:
            return False

        billing_resp = request_with_metrics(
            sess,
            "GET",
            f"{base_url}/billing/",
            "/billing",
            state,
            timeout,
        )
        if billing_resp.status_code != 200:
            return False

    return True


def add_items_to_cart(
    sess: requests.Session,
    base_url: str,
    barcodes: List[str],
    item_count: int,
    state: StressState,
    timeout: int,
    rng: random.Random,
    preferred_pool: Optional[List[str]] = None,
) -> Counter:
    sold = Counter()
    candidate_pool = preferred_pool if preferred_pool else barcodes
    for _ in range(item_count):
        bc = rng.choice(candidate_pool)
        resp = request_with_metrics(
            sess,
            "POST",
            f"{base_url}/billing/add-item",
            "/billing/add-item",
            state,
            timeout,
            data={"barcode": bc},
        )
        if resp.status_code != 200:
            continue
        body_lc = resp.text.lower()
        if any(marker in body_lc for marker in ADD_ITEM_ERROR_MARKERS):
            continue
        sold[bc] += 1
    return sold


def inject_invalid_completion(
    sess: requests.Session,
    base_url: str,
    state: StressState,
    timeout: int,
) -> None:
    # Empty-cart completion attempt validates recovery path.
    request_with_metrics(
        sess,
        "POST",
        f"{base_url}/billing/complete",
        "/billing/complete-invalid",
        state,
        timeout,
        data={
            "payment_cash": "0",
            "payment_card": "0",
            "payment_upi": "0",
            "payment_loyalty": "0",
            "payment_gift": "0",
        },
    )


def complete_sale(
    sess: requests.Session,
    base_url: str,
    sold: Counter,
    unit_total_with_tax: Decimal,
    state: StressState,
    timeout: int,
    rng: random.Random,
    burst: bool = False,
) -> Tuple[bool, Optional[str]]:
    qty_total = sum(sold.values())
    if qty_total <= 0:
        return False, None

    total_due = unit_total_with_tax * Decimal(qty_total)
    payment_payload = build_payment_payload(total_due, rng)

    resp = request_with_metrics(
        sess,
        "POST",
        f"{base_url}/billing/complete",
        "/billing/complete",
        state,
        timeout,
        data=payment_payload,
    )
    if resp.status_code != 200:
        return False, None

    invoice_number = parse_invoice_number(resp.text)
    if not invoice_number:
        return False, None

    state.add_sale_success(invoice_number, sold, burst=burst)
    return True, invoice_number


def run_counter(
    counter_id: int,
    args: argparse.Namespace,
    barcodes: List[str],
    hot_barcodes: List[str],
    state: StressState,
    start_monotonic: float,
    sync_barrier: Optional[threading.Barrier] = None,
) -> None:
    rng = random.Random(args.seed + counter_id)
    username = args.usernames[counter_id % len(args.usernames)]
    password = args.passwords[counter_id % len(args.passwords)]

    attempts = 0
    while True:
        elapsed = time.monotonic() - start_monotonic
        if args.duration > 0 and elapsed >= args.duration:
            break
        if args.sales_per_counter > 0 and attempts >= args.sales_per_counter:
            break
        attempts += 1

        try:
            with requests.Session() as sess:
                if not ensure_login_and_open_session(
                    sess=sess,
                    base_url=args.base_url,
                    username=username,
                    password=password,
                    opening_cash=args.opening_cash,
                    state=state,
                    timeout=args.timeout,
                ):
                    state.add_sale_failure()
                    continue

                recovery_injected = False
                if args.failure_recovery_rate > 0:
                    should_inject = (
                        rng.random() < args.failure_recovery_rate
                        or (counter_id == 0 and attempts == 1)
                    )
                    if should_inject:
                        recovery_injected = True
                        state.add_recovery_injection()
                        inject_invalid_completion(
                            sess=sess,
                            base_url=args.base_url,
                            state=state,
                            timeout=args.timeout,
                        )

                item_count = rng.randint(args.items_min, args.items_max)
                preferred_pool = None
                if args.hot_product_mode and hot_barcodes and rng.random() < 0.5:
                    preferred_pool = hot_barcodes
                sold = add_items_to_cart(
                    sess=sess,
                    base_url=args.base_url,
                    barcodes=barcodes,
                    item_count=item_count,
                    state=state,
                    timeout=args.timeout,
                    rng=rng,
                    preferred_pool=preferred_pool,
                )

                if sync_barrier is not None and not sync_barrier.broken:
                    try:
                        sync_barrier.wait(timeout=args.sync_timeout)
                    except threading.BrokenBarrierError:
                        state.add_sync_barrier_break()

                ok, _ = complete_sale(
                    sess=sess,
                    base_url=args.base_url,
                    sold=sold,
                    unit_total_with_tax=args.unit_total_with_tax,
                    state=state,
                    timeout=args.timeout,
                    rng=rng,
                    burst=False,
                )
                if not ok:
                    state.add_sale_failure()
                    if recovery_injected:
                        state.add_recovery_failure()
                elif recovery_injected:
                    state.add_recovery_success()
        except Exception:
            state.add_exception()
            state.add_sale_failure()


def run_burst_mode(
    args: argparse.Namespace,
    barcodes: List[str],
    hot_barcodes: List[str],
    state: StressState,
) -> None:
    print("\n[BURST] Running synchronized completion burst...")
    barrier = threading.Barrier(args.counters)
    invoices = []
    lock = threading.Lock()

    def burst_worker(counter_id: int) -> None:
        rng = random.Random(args.seed + 10000 + counter_id)
        username = args.usernames[counter_id % len(args.usernames)]
        password = args.passwords[counter_id % len(args.passwords)]
        try:
            with requests.Session() as sess:
                if not ensure_login_and_open_session(
                    sess=sess,
                    base_url=args.base_url,
                    username=username,
                    password=password,
                    opening_cash=args.opening_cash,
                    state=state,
                    timeout=args.timeout,
                ):
                    state.add_sale_failure()
                    return

                sold = add_items_to_cart(
                    sess=sess,
                    base_url=args.base_url,
                    barcodes=barcodes,
                    item_count=rng.randint(max(1, args.items_min), min(3, args.items_max)),
                    state=state,
                    timeout=args.timeout,
                    rng=rng,
                    preferred_pool=(hot_barcodes if args.hot_product_mode and hot_barcodes else None),
                )

                barrier.wait(timeout=10)
                ok, inv = complete_sale(
                    sess=sess,
                    base_url=args.base_url,
                    sold=sold,
                    unit_total_with_tax=args.unit_total_with_tax,
                    state=state,
                    timeout=args.timeout,
                    rng=rng,
                    burst=True,
                )
                if not ok:
                    state.add_sale_failure()
                    return
                with lock:
                    invoices.append(inv)
        except Exception:
            state.add_exception()
            state.add_sale_failure()

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.counters) as ex:
        futs = [ex.submit(burst_worker, c) for c in range(args.counters)]
        for fut in futs:
            fut.result()

    print(f"[BURST] completed invoices: {len(invoices)}/{args.counters}")


def setup_products_db(args: argparse.Namespace) -> Tuple[List[str], Dict[str, int]]:
    engine = create_engine(args.db_url, future=True, pool_pre_ping=True)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    prefix = args.product_prefix

    rows = []
    for i in range(args.product_count):
        barcode = f"{prefix}-{i:04d}"
        rows.append({
            "name": f"Stress Product {i:03d}",
            "barcode": barcode,
            "price": args.unit_price,
            "stock": args.initial_stock,
            "gst_percent": args.gst_percent,
            "is_active": True,
            "is_weighed": False,
            "price_per_kg": None,
            "created_at": now,
            "updated_at": now,
        })

    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO products (
                name, barcode, price, stock, gst_percent,
                is_active, is_weighed, price_per_kg, created_at, updated_at
            ) VALUES (
                :name, :barcode, :price, :stock, :gst_percent,
                :is_active, :is_weighed, :price_per_kg, :created_at, :updated_at
            )
        """), rows)

        product_rows = conn.execute(text("""
            SELECT barcode, stock
            FROM products
            WHERE barcode LIKE :prefix
        """), {"prefix": f"{prefix}%"}).fetchall()

    barcodes = [r.barcode for r in product_rows]
    initial_stock = {r.barcode: int(r.stock) for r in product_rows}
    return barcodes, initial_stock


def setup_products_api(args: argparse.Namespace) -> None:
    # API setup requires admin credentials; used only if explicitly selected.
    admin_user = args.usernames[0]
    admin_pass = args.passwords[0]
    with requests.Session() as sess:
        login = sess.post(
            f"{args.base_url}/auth/login",
            data={"username": admin_user, "password": admin_pass},
            timeout=args.timeout,
            allow_redirects=True,
        )
        if login.status_code != 200:
            raise RuntimeError(f"API setup login failed: status={login.status_code}")

        for i in range(args.product_count):
            barcode = f"{args.product_prefix}-{i:04d}"
            payload = {
                "name": f"Stress Product {i:03d}",
                "barcode": barcode,
                "price": str(args.unit_price),
                "stock": str(args.initial_stock),
                "gst_percent": str(args.gst_percent),
            }
            resp = sess.post(
                f"{args.base_url}/inventory/new",
                data=payload,
                timeout=args.timeout,
                allow_redirects=True,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"API setup failed at product {barcode}: status={resp.status_code}")


def fetch_final_stocks(db_url: str, prefix: str) -> Dict[str, int]:
    engine = create_engine(db_url, future=True, pool_pre_ping=True)
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT barcode, stock
            FROM products
            WHERE barcode LIKE :prefix
        """), {"prefix": f"{prefix}%"}).fetchall()
    return {r.barcode: int(r.stock) for r in rows}


def fetch_sold_quantities(db_url: str, prefix: str) -> Dict[str, int]:
    engine = create_engine(db_url, future=True, pool_pre_ping=True)
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT p.barcode, COALESCE(SUM(si.quantity), 0) AS sold_qty
            FROM products p
            LEFT JOIN sale_items si ON si.product_id = p.id
            WHERE p.barcode LIKE :prefix
            GROUP BY p.barcode
        """), {"prefix": f"{prefix}%"}).fetchall()
    return {r.barcode: int(r.sold_qty or 0) for r in rows}


def scan_logs(log_file: Optional[str], start_offset: int) -> Tuple[int, List[str]]:
    if not log_file or not os.path.exists(log_file):
        return 0, []
    with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
        f.seek(start_offset)
        chunk = f.read()
    hits = []
    for line in chunk.splitlines():
        if LOG_ERROR_RE.search(line):
            hits.append(line.strip())
    return len(hits), hits[:10]


def assert_burst_sequential(burst_invoices: List[str]) -> Tuple[bool, str]:
    if not burst_invoices:
        return False, "No burst invoices captured."
    unique = sorted(set(burst_invoices))
    if len(unique) != len(burst_invoices):
        return False, "Duplicate invoice numbers in burst mode."

    years = {inv.split("-")[0] for inv in unique}
    if len(years) != 1:
        return False, "Burst invoices span multiple years unexpectedly."

    seqs = sorted(int(inv.split("-")[1]) for inv in unique)
    for i in range(1, len(seqs)):
        if seqs[i] != seqs[i - 1] + 1:
            return False, "Burst invoice numbers are not contiguous."
    return True, "Burst invoices are sequential and contiguous."


def format_summary_row(label: str, value: str, width: int = 38) -> str:
    return f"{label:<{width}} {value}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Concurrent POS supermarket stress test.")
    parser.add_argument("--base-url", required=True, help="Base URL, e.g. http://10.0.0.5:5000")
    parser.add_argument("--duration", type=int, default=60, help="Test duration in seconds (0 = no duration limit).")
    parser.add_argument("--counters", type=int, default=4, help="Number of concurrent billing counters.")
    parser.add_argument("--sales-per-counter", type=int, default=50, help="Sales attempts per counter (0 = unlimited until duration).")
    parser.add_argument("--items-min", type=int, default=1, help="Minimum items per sale.")
    parser.add_argument("--items-max", type=int, default=10, help="Maximum items per sale.")
    parser.add_argument("--product-count", type=int, default=100, help="How many stress products to create.")
    parser.add_argument("--initial-stock", type=int, default=500, help="Initial stock per stress product.")
    parser.add_argument("--unit-price", type=Decimal, default=Decimal("100.00"), help="Unit base price for stress products.")
    parser.add_argument("--gst-percent", type=int, default=5, help="GST percent for stress products.")
    parser.add_argument("--opening-cash", type=Decimal, default=Decimal("10000.00"), help="Opening cash for session-open flow.")
    parser.add_argument("--db-url", default=os.environ.get("DATABASE_URL", ""), help="Database URL for setup/assertions.")
    parser.add_argument("--setup-mode", choices=["db", "api"], default="db", help="Product setup mode.")
    parser.add_argument("--usernames", default="admin", help="Comma-separated usernames for counters.")
    parser.add_argument("--passwords", default="admin123", help="Comma-separated passwords (cycled if fewer than counters).")
    parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout seconds.")
    parser.add_argument("--log-file", default="logs/app.log", help="App log file path for deadlock/integrity scan.")
    parser.add_argument("--burst-mode", action="store_true", help="Run synchronized completion burst after normal run.")
    parser.add_argument("--hot-product-mode", action="store_true", help="Route 50%% of sales to same 5 products.")
    parser.add_argument("--sync-complete-mode", action="store_true", help="Synchronize /billing/complete across counters with barrier.")
    parser.add_argument("--sync-timeout", type=int, default=30, help="Barrier wait timeout seconds for sync-complete mode.")
    parser.add_argument("--failure-recovery-rate", type=float, default=0.05, help="Probability of invalid completion injection before a sale.")
    parser.add_argument("--seed", type=int, default=20260220, help="Random seed.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.items_min <= 0 or args.items_max < args.items_min:
        raise SystemExit("Invalid items range.")
    if args.counters <= 0:
        raise SystemExit("counters must be >= 1.")
    if not args.db_url:
        raise SystemExit("db-url is required for stock/integrity assertions.")
    if args.failure_recovery_rate < 0 or args.failure_recovery_rate > 1:
        raise SystemExit("failure-recovery-rate must be between 0 and 1.")

    args.base_url = args.base_url.rstrip("/")
    args.usernames = [u.strip() for u in args.usernames.split(",") if u.strip()]
    args.passwords = [p.strip() for p in args.passwords.split(",") if p.strip()]
    if not args.usernames or not args.passwords:
        raise SystemExit("Provide at least one username and one password.")

    args.product_prefix = f"STRESS-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    args.unit_total_with_tax = (
        args.unit_price * (Decimal("1") + (Decimal(args.gst_percent) / Decimal("100")))
    ).quantize(Decimal("0.01"))

    print("=== POS Stress Test: Setup ===")
    print(format_summary_row("Base URL:", args.base_url))
    print(format_summary_row("Counters:", str(args.counters)))
    print(format_summary_row("Duration (s):", str(args.duration)))
    print(format_summary_row("Sales per counter:", str(args.sales_per_counter)))
    print(format_summary_row("Setup mode:", args.setup_mode))
    print(format_summary_row("Product prefix:", args.product_prefix))
    print(format_summary_row("Hot product mode:", str(args.hot_product_mode)))
    print(format_summary_row("Sync complete mode:", str(args.sync_complete_mode)))
    print(format_summary_row("Failure recovery rate:", f"{args.failure_recovery_rate:.2f}"))

    log_offset = 0
    if args.log_file and os.path.exists(args.log_file):
        log_offset = os.path.getsize(args.log_file)

    rss_before = get_rss_bytes()

    if args.setup_mode == "db":
        barcodes, initial_stock = setup_products_db(args)
    else:
        setup_products_api(args)
        # For API mode, still use DB to fetch products for assertions.
        final_seed = fetch_final_stocks(args.db_url, args.product_prefix)
        barcodes = sorted(final_seed.keys())
        initial_stock = dict(final_seed)

    if len(barcodes) != args.product_count:
        raise SystemExit(f"Setup did not create expected products. expected={args.product_count}, got={len(barcodes)}")

    hot_barcodes = sorted(barcodes)[: min(5, len(barcodes))]
    state = StressState()
    start = time.monotonic()
    sync_barrier = threading.Barrier(args.counters) if args.sync_complete_mode else None

    print("\n=== Running Concurrent Counter Load ===")
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.counters) as ex:
        futures = [
            ex.submit(run_counter, i, args, barcodes, hot_barcodes, state, start, sync_barrier)
            for i in range(args.counters)
        ]
        for fut in futures:
            fut.result()

    if args.burst_mode:
        run_burst_mode(args, barcodes, hot_barcodes, state)

    elapsed = time.monotonic() - start
    rss_after = get_rss_bytes()
    rss_delta = (rss_after - rss_before) if (rss_before is not None and rss_after is not None) else None
    final_stock = fetch_final_stocks(args.db_url, args.product_prefix)
    sold_qty_db = fetch_sold_quantities(args.db_url, args.product_prefix)

    # Assertions
    errors = []
    duplicate_invoices = len(state.invoice_numbers) - len(set(state.invoice_numbers))
    if duplicate_invoices > 0:
        errors.append(f"Duplicate invoice numbers detected: {duplicate_invoices}")

    if any(stock < 0 for stock in final_stock.values()):
        errors.append("Negative stock detected in stress products.")

    expected_total_sold = sum(sold_qty_db.values())
    actual_total_deducted = 0
    for bc, initial in initial_stock.items():
        current = final_stock.get(bc)
        if current is None:
            errors.append(f"Missing product in final stock snapshot: {bc}")
            continue
        actual_total_deducted += (initial - current)
    if expected_total_sold != actual_total_deducted:
        errors.append(
            f"Stock deduction mismatch. expected_sold={expected_total_sold}, "
            f"actual_deducted={actual_total_deducted}"
        )

    server_500s = [m for m in state.request_metrics if m.status_code >= 500]
    if server_500s:
        errors.append(f"HTTP 500+ responses detected: {len(server_500s)}")
    pool_exhaustion_500s = [
        m for m in server_500s
        if any(marker in (m.response_excerpt or "").lower() for marker in POOL_ERROR_MARKERS)
    ]
    if pool_exhaustion_500s:
        errors.append(f"Pool exhaustion/timeout 500 responses detected: {len(pool_exhaustion_500s)}")

    non_200 = [m for m in state.request_metrics if m.status_code != 200]
    if non_200:
        errors.append(f"Non-200 responses detected: {len(non_200)}")

    log_hit_count, log_hits = scan_logs(args.log_file, log_offset)
    if log_hit_count > 0:
        errors.append(f"Error markers found in logs: {log_hit_count}")

    if state.recovery_injections > 0 and state.recovery_failures > 0:
        errors.append(
            f"Failure recovery check failed: {state.recovery_failures} injected-invalid cycles did not recover."
        )

    if args.burst_mode:
        ok_burst, msg_burst = assert_burst_sequential(state.burst_invoices)
        if not ok_burst:
            errors.append(f"Burst sequentiality failed: {msg_burst}")

    # Metrics
    complete_lats = state.complete_latencies_ms
    avg_ms = (sum(complete_lats) / len(complete_lats)) if complete_lats else 0.0
    p95_ms = percentile(complete_lats, 0.95) if complete_lats else 0.0
    throughput = (state.successful_sales / elapsed) if elapsed > 0 else 0.0

    print("\n=== Final Summary ===")
    print(format_summary_row("Total sales completed:", str(state.successful_sales)))
    print(format_summary_row("Failed sales:", str(state.failed_sales)))
    print(format_summary_row("Total HTTP requests:", str(len(state.request_metrics))))
    print(format_summary_row("Failed requests (non-200/exception):", str(state.non_200_count)))
    print(format_summary_row("Avg /billing/complete latency:", f"{avg_ms:.2f} ms"))
    print(format_summary_row("P95 /billing/complete latency:", f"{p95_ms:.2f} ms"))
    print(format_summary_row("Throughput:", f"{throughput:.2f} sales/sec"))
    print(format_summary_row("Duplicate invoices:", str(duplicate_invoices)))
    print(format_summary_row("Expected qty sold:", str(expected_total_sold)))
    print(format_summary_row("Actual stock deducted:", str(actual_total_deducted)))
    print(format_summary_row("HTTP 500 count:", str(len(server_500s))))
    print(format_summary_row("Pool exhaustion 500 count:", str(len(pool_exhaustion_500s))))
    print(format_summary_row("Log error marker hits:", str(log_hit_count)))
    print(format_summary_row("Recovery injections:", str(state.recovery_injections)))
    print(format_summary_row("Recovery successes:", str(state.recovery_successes)))
    print(format_summary_row("Recovery failures:", str(state.recovery_failures)))
    print(format_summary_row("Sync barrier breaks:", str(state.sync_barrier_breaks)))
    print(format_summary_row("RSS before:", fmt_bytes(rss_before)))
    print(format_summary_row("RSS after:", fmt_bytes(rss_after)))
    print(format_summary_row("RSS delta:", fmt_bytes(rss_delta)))
    if args.burst_mode:
        print(format_summary_row("Burst invoices captured:", str(len(state.burst_invoices))))

    if log_hits:
        print("\nLog error samples:")
        for line in log_hits:
            print(f"  - {line}")

    if errors:
        print("\n[FAIL] Assertions failed:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("\n[PASS] All assertions satisfied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
