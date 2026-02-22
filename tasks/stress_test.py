#!/usr/bin/env python3
"""
auto_stress_test_suite.py

Automated scenario test harness that imports and reuses stress_test_pos.py logic.
It executes multiple stress scenarios, validates correctness, and exits non-zero
if any scenario fails.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import importlib.util
import os
import random
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from types import ModuleType
from typing import Dict, List, Optional, Tuple


DB_HTTP_ERROR_RE = re.compile(
    r"(deadlock|serializationfailure|could not serialize|integrityerror|traceback)",
    re.IGNORECASE,
)


@dataclass
class ScenarioSpec:
    key: str
    title: str
    overrides: Dict[str, object] = field(default_factory=dict)


@dataclass
class ScenarioResult:
    key: str
    title: str
    passed: bool
    elapsed_sec: float
    total_sales: int
    throughput: float
    avg_complete_ms: float
    p95_complete_ms: float
    memory_before: Optional[int]
    memory_after: Optional[int]
    memory_delta: Optional[int]
    errors: List[str]
    error_counts: Dict[str, int]
    log_samples: List[str] = field(default_factory=list)


def load_stress_module(path: str) -> ModuleType:
    if not os.path.exists(path):
        raise FileNotFoundError(f"stress module not found: {path}")
    module_name = "stress_module"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module spec: {path}")
    module = importlib.util.module_from_spec(spec)
    # Register module before execution for dataclasses (sys.modules lookup).
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def parse_csv(value: str) -> List[str]:
    return [x.strip() for x in value.split(",") if x.strip()]


def clone_namespace(ns: argparse.Namespace) -> argparse.Namespace:
    return argparse.Namespace(**vars(ns))


def calc_unit_total_with_tax(unit_price: Decimal, gst_percent: int) -> Decimal:
    return (unit_price * (Decimal("1") + (Decimal(gst_percent) / Decimal("100")))).quantize(Decimal("0.01"))


def scenario_args(base: argparse.Namespace, spec: ScenarioSpec, seed_offset: int) -> argparse.Namespace:
    args = clone_namespace(base)
    for key, value in spec.overrides.items():
        setattr(args, key, value)
    args.seed = int(base.seed + seed_offset)
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    args.product_prefix = f"{base.product_prefix_base}-{spec.key}-{ts}"
    args.unit_total_with_tax = calc_unit_total_with_tax(args.unit_price, args.gst_percent)
    return args


def run_single_scenario(
    st: ModuleType,
    base_args: argparse.Namespace,
    spec: ScenarioSpec,
    idx: int,
) -> ScenarioResult:
    args = scenario_args(base_args, spec, idx * 1000)

    log_offset = 0
    if args.log_file and os.path.exists(args.log_file):
        log_offset = os.path.getsize(args.log_file)

    rss_before = st.get_rss_bytes()

    if args.setup_mode == "db":
        barcodes, initial_stock = st.setup_products_db(args)
    else:
        st.setup_products_api(args)
        seed_map = st.fetch_final_stocks(args.db_url, args.product_prefix)
        barcodes = sorted(seed_map.keys())
        initial_stock = dict(seed_map)

    if len(barcodes) != args.product_count:
        return ScenarioResult(
            key=spec.key,
            title=spec.title,
            passed=False,
            elapsed_sec=0.0,
            total_sales=0,
            throughput=0.0,
            avg_complete_ms=0.0,
            p95_complete_ms=0.0,
            memory_before=rss_before,
            memory_after=st.get_rss_bytes(),
            memory_delta=None,
            errors=[f"setup count mismatch: expected {args.product_count}, got {len(barcodes)}"],
            error_counts={"setup": 1},
        )

    hot_barcodes = sorted(barcodes)[: min(5, len(barcodes))]
    state = st.StressState()
    sync_barrier = threading.Barrier(args.counters) if args.sync_complete_mode else None

    t0 = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.counters) as pool:
        futures = [
            pool.submit(st.run_counter, i, args, barcodes, hot_barcodes, state, t0, sync_barrier)
            for i in range(args.counters)
        ]
        for future in futures:
            future.result()

    if args.burst_mode:
        st.run_burst_mode(args, barcodes, hot_barcodes, state)

    elapsed = time.monotonic() - t0
    rss_after = st.get_rss_bytes()
    rss_delta = None
    if rss_before is not None and rss_after is not None:
        rss_delta = rss_after - rss_before

    final_stock = st.fetch_final_stocks(args.db_url, args.product_prefix)
    sold_qty_db = st.fetch_sold_quantities(args.db_url, args.product_prefix)

    # Assertions
    errors: List[str] = []
    err_counts: Dict[str, int] = {}

    duplicate_invoices = len(state.invoice_numbers) - len(set(state.invoice_numbers))
    if duplicate_invoices > 0:
        errors.append(f"duplicate invoice numbers: {duplicate_invoices}")
    err_counts["duplicate_invoices"] = duplicate_invoices

    negative_stock_count = sum(1 for stock in final_stock.values() if stock < 0)
    if negative_stock_count > 0:
        errors.append(f"negative stock rows: {negative_stock_count}")
    err_counts["negative_stock"] = negative_stock_count

    expected_total_sold = sum(int(v) for v in sold_qty_db.values())
    actual_total_deducted = 0
    missing_products = 0
    for bc, initial in initial_stock.items():
        current = final_stock.get(bc)
        if current is None:
            missing_products += 1
            continue
        actual_total_deducted += int(initial - current)
    if missing_products > 0:
        errors.append(f"missing products in final snapshot: {missing_products}")
    err_counts["missing_products"] = missing_products

    stock_mismatch = int(expected_total_sold != actual_total_deducted)
    if stock_mismatch:
        errors.append(
            f"stock mismatch expected_sold={expected_total_sold} actual_deducted={actual_total_deducted}"
        )
    err_counts["stock_mismatch"] = stock_mismatch

    non_200 = [m for m in state.request_metrics if m.status_code != 200]
    err_counts["non_200"] = len(non_200)
    if non_200:
        errors.append(f"non-200 responses: {len(non_200)}")

    http_500 = [m for m in state.request_metrics if m.status_code >= 500]
    err_counts["http_500"] = len(http_500)
    if http_500:
        errors.append(f"http 500+ responses: {len(http_500)}")

    db_http_hits = [
        m for m in http_500
        if DB_HTTP_ERROR_RE.search((m.response_excerpt or "").lower() if m.response_excerpt else "")
    ]
    err_counts["db_http_hits"] = len(db_http_hits)
    if db_http_hits:
        errors.append(f"db-related 500 markers in response body: {len(db_http_hits)}")

    pool_hits = [
        m for m in http_500
        if any(marker in (m.response_excerpt or "").lower() for marker in st.POOL_ERROR_MARKERS)
    ]
    err_counts["pool_exhaustion_hits"] = len(pool_hits)
    if pool_hits:
        errors.append(f"queue pool exhaustion markers: {len(pool_hits)}")

    log_hit_count, log_hits = st.scan_logs(args.log_file, log_offset)
    err_counts["log_hits"] = int(log_hit_count)
    if log_hit_count > 0:
        errors.append(f"log error markers: {log_hit_count}")

    if args.sync_complete_mode:
        err_counts["sync_barrier_breaks"] = int(state.sync_barrier_breaks)
        if state.sync_barrier_breaks > 0:
            errors.append(f"sync barrier breaks: {state.sync_barrier_breaks}")
    else:
        err_counts["sync_barrier_breaks"] = int(state.sync_barrier_breaks)

    if args.burst_mode:
        ok_burst, msg = st.assert_burst_sequential(state.burst_invoices)
        err_counts["burst_fail"] = 0 if ok_burst else 1
        if not ok_burst:
            errors.append(f"burst sequentiality: {msg}")
    else:
        err_counts["burst_fail"] = 0

    if args.failure_recovery_rate > 0:
        err_counts["recovery_injections"] = int(state.recovery_injections)
        err_counts["recovery_failures"] = int(state.recovery_failures)
        if state.recovery_injections <= 0:
            errors.append("failure recovery mode enabled but no injections occurred")
        if state.recovery_failures > 0:
            errors.append(f"failure recovery did not recover cleanly: {state.recovery_failures}")
    else:
        err_counts["recovery_injections"] = int(state.recovery_injections)
        err_counts["recovery_failures"] = int(state.recovery_failures)

    complete_lats = list(state.complete_latencies_ms)
    avg_ms = (sum(complete_lats) / len(complete_lats)) if complete_lats else 0.0
    p95_ms = st.percentile(complete_lats, 0.95) if complete_lats else 0.0
    throughput = (state.successful_sales / elapsed) if elapsed > 0 else 0.0

    if args.max_p95_ms > 0 and p95_ms > args.max_p95_ms:
        errors.append(f"p95 complete latency too high: {p95_ms:.2f}ms > {args.max_p95_ms:.2f}ms")
        err_counts["latency_threshold"] = 1
    else:
        err_counts["latency_threshold"] = 0

    passed = len(errors) == 0
    return ScenarioResult(
        key=spec.key,
        title=spec.title,
        passed=passed,
        elapsed_sec=elapsed,
        total_sales=int(state.successful_sales),
        throughput=throughput,
        avg_complete_ms=avg_ms,
        p95_complete_ms=p95_ms,
        memory_before=rss_before,
        memory_after=rss_after,
        memory_delta=rss_delta,
        errors=errors,
        error_counts=err_counts,
        log_samples=log_hits,
    )


def print_result(st: ModuleType, result: ScenarioResult) -> None:
    status = "PASS" if result.passed else "FAIL"
    print(f"\n[{status}] {result.title} ({result.key})")
    print("-" * 78)
    print(f"sales_completed            : {result.total_sales}")
    print(f"elapsed_sec                : {result.elapsed_sec:.2f}")
    print(f"throughput_sales_per_sec   : {result.throughput:.2f}")
    print(f"avg_complete_ms            : {result.avg_complete_ms:.2f}")
    print(f"p95_complete_ms            : {result.p95_complete_ms:.2f}")
    print(f"memory_before              : {st.fmt_bytes(result.memory_before)}")
    print(f"memory_after               : {st.fmt_bytes(result.memory_after)}")
    print(f"memory_delta               : {st.fmt_bytes(result.memory_delta)}")
    print("error_counts               :")
    for key in sorted(result.error_counts.keys()):
        print(f"  - {key}: {result.error_counts[key]}")
    if result.errors:
        print("errors                     :")
        for err in result.errors:
            print(f"  - {err}")
    if result.log_samples:
        print("log_samples                :")
        for line in result.log_samples[:5]:
            print(f"  - {line}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Automated stress scenario suite for stress_test_pos.py"
    )
    parser.add_argument("--stress-module-path", default="stress_test_pos.py", help="Path to stress_test_pos.py")
    parser.add_argument("--base-url", required=True, help="Base app URL, e.g. http://10.0.0.5:5000")
    parser.add_argument("--db-url", default=os.environ.get("DATABASE_URL", ""), help="Database URL")
    parser.add_argument("--setup-mode", choices=["db", "api"], default="db", help="Product setup mode")
    parser.add_argument("--usernames", default="admin", help="Comma-separated usernames")
    parser.add_argument("--passwords", default="admin123", help="Comma-separated passwords")
    parser.add_argument("--counters", type=int, default=4, help="Concurrent counters")
    parser.add_argument("--base-duration", type=int, default=60, help="Scenario duration seconds")
    parser.add_argument("--base-sales-per-counter", type=int, default=50, help="Sales per counter")
    parser.add_argument("--items-min", type=int, default=1, help="Min items/sale")
    parser.add_argument("--items-max", type=int, default=10, help="Max items/sale")
    parser.add_argument("--product-count", type=int, default=100, help="Stress product count")
    parser.add_argument("--initial-stock", type=int, default=500, help="Initial stock/product")
    parser.add_argument("--unit-price", type=Decimal, default=Decimal("100.00"), help="Unit base price")
    parser.add_argument("--gst-percent", type=int, default=5, help="GST percent")
    parser.add_argument("--opening-cash", type=Decimal, default=Decimal("10000.00"), help="Opening cash/session")
    parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout seconds")
    parser.add_argument("--log-file", default="logs/app.log", help="Application log path")
    parser.add_argument("--failure-recovery-rate", type=float, default=0.05, help="Invalid-complete injection probability")
    parser.add_argument("--max-p95-ms", type=float, default=0.0, help="Fail scenario if p95 complete latency exceeds this (0 disables)")
    parser.add_argument(
        "--scenarios",
        default="all",
        help="Comma list: all,baseline,hot,sync,burst,recovery",
    )
    parser.add_argument("--seed", type=int, default=20260220, help="Random seed")
    parser.add_argument("--product-prefix-base", default="SUITE-STRESS", help="Prefix base for generated products")
    return parser.parse_args()


def build_base_namespace(cli: argparse.Namespace) -> argparse.Namespace:
    if not cli.db_url:
        raise SystemExit("db-url is required.")
    if cli.items_min <= 0 or cli.items_max < cli.items_min:
        raise SystemExit("invalid items range")
    if cli.counters <= 0:
        raise SystemExit("counters must be >= 1")
    if cli.failure_recovery_rate < 0 or cli.failure_recovery_rate > 1:
        raise SystemExit("failure-recovery-rate must be between 0 and 1")

    usernames = parse_csv(cli.usernames)
    passwords = parse_csv(cli.passwords)
    if not usernames or not passwords:
        raise SystemExit("provide at least one username and one password")

    ns = argparse.Namespace()
    ns.base_url = cli.base_url.rstrip("/")
    ns.db_url = cli.db_url
    ns.setup_mode = cli.setup_mode
    ns.usernames = usernames
    ns.passwords = passwords
    ns.counters = cli.counters
    ns.duration = cli.base_duration
    ns.sales_per_counter = cli.base_sales_per_counter
    ns.items_min = cli.items_min
    ns.items_max = cli.items_max
    ns.product_count = cli.product_count
    ns.initial_stock = cli.initial_stock
    ns.unit_price = cli.unit_price
    ns.gst_percent = cli.gst_percent
    ns.opening_cash = cli.opening_cash
    ns.timeout = cli.timeout
    ns.log_file = cli.log_file
    ns.seed = cli.seed
    ns.product_prefix_base = cli.product_prefix_base
    ns.failure_recovery_rate = cli.failure_recovery_rate
    ns.max_p95_ms = cli.max_p95_ms

    # Defaults expected by stress_test_pos internals
    ns.hot_product_mode = False
    ns.sync_complete_mode = False
    ns.sync_timeout = 30
    ns.burst_mode = False
    return ns


def select_scenarios(raw: str) -> List[ScenarioSpec]:
    all_specs = [
        ScenarioSpec("baseline", "Baseline Load", {}),
        ScenarioSpec("hot", "Hot Product Contention", {"hot_product_mode": True}),
        ScenarioSpec("sync", "Sync Complete Collision Mode", {"sync_complete_mode": True}),
        ScenarioSpec("burst", "Burst Mode", {"burst_mode": True}),
        ScenarioSpec(
            "recovery",
            "Failure Recovery Injection Mode",
            {"failure_recovery_rate": 0.20},
        ),
    ]
    if raw.strip().lower() == "all":
        return all_specs
    selected = {x.strip().lower() for x in raw.split(",") if x.strip()}
    specs = [s for s in all_specs if s.key in selected]
    if not specs:
        raise SystemExit("No valid scenarios selected.")
    return specs


def main() -> int:
    cli = parse_args()
    st = load_stress_module(cli.stress_module_path)
    base = build_base_namespace(cli)
    scenarios = select_scenarios(cli.scenarios)

    print("=== Auto Stress Test Suite ===")
    print(f"stress_module_path : {cli.stress_module_path}")
    print(f"base_url           : {base.base_url}")
    print(f"db_url             : {base.db_url}")
    print(f"setup_mode         : {base.setup_mode}")
    print(f"counters           : {base.counters}")
    print(f"base_duration_sec  : {base.duration}")
    print(f"sales_per_counter  : {base.sales_per_counter}")
    print(f"scenarios          : {', '.join(s.key for s in scenarios)}")

    results: List[ScenarioResult] = []
    random.seed(base.seed)

    for idx, spec in enumerate(scenarios, start=1):
        result = run_single_scenario(st, base, spec, idx)
        results.append(result)
        print_result(st, result)

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    failed = total - passed

    print("\n=== Suite Summary ===")
    print(f"scenarios_passed : {passed}/{total}")
    for r in results:
        print(f"  - {r.key:<10} {'PASS' if r.passed else 'FAIL'}")

    if failed > 0:
        print("\n[FAIL] One or more scenarios failed.")
        return 1

    print("\n[PASS] All scenarios passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
