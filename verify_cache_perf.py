import time
from app import create_app, db, cache
from app.inventory.models import ProductVariant
from decimal import Decimal

def benchmark_lookup():
    app = create_app('development')
    with app.app_context():
        # ── Setup ──
        # Ensure we have a variant to test
        variant = ProductVariant.query.filter_by(is_active=True).first()
        if not variant:
            print("No active variants found in DB. Please add one first.")
            return
        
        barcode = variant.barcode
        cache_key = f"barcode_lookup_{barcode}"
        
        # 1. Clear Cache to ensure clean start
        cache.delete(cache_key)
        print(f"Testing Barcode: {barcode} ({variant.product.name} - {variant.size}/{variant.color})")
        print("-" * 50)

        # 2. Database Hit (First Lookup)
        start_time = time.time()
        # Simulated lookup logic from billing/routes.py
        cached_val = cache.get(cache_key)
        if cached_val is None:
            v = ProductVariant.query.filter_by(barcode=barcode, is_active=True).first()
            if v:
                cache.set(cache_key, v, timeout=3600)
        db_time = (time.time() - start_time) * 1000
        print(f"1st Lookup (DB Hit):    {db_time:.2f} ms")

        # 3. Cache Hit (Second Lookup)
        start_time = time.time()
        cached_val = cache.get(cache_key)
        if cached_val is None:
            v = ProductVariant.query.filter_by(barcode=barcode, is_active=True).first()
            cache.set(cache_key, v, timeout=3600)
        cache_time = (time.time() - start_time) * 1000
        print(f"2nd Lookup (Cache Hit): {cache_time:.2f} ms")

        # 4. Invalidation Check
        cache.delete(cache_key)
        start_time = time.time()
        cached_val = cache.get(cache_key)
        if cached_val is None:
            v = ProductVariant.query.filter_by(barcode=barcode, is_active=True).first()
        invalidation_time = (time.time() - start_time) * 1000
        print(f"3rd Lookup (After Del): {invalidation_time:.2f} ms")
        
        print("-" * 50)
        improvement = ((db_time - cache_time) / db_time) * 100
        print(f"Performance Gain: {improvement:.1f}%")

if __name__ == "__main__":
    benchmark_lookup()
