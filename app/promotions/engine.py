"""
app/promotions/engine.py
------------------------
Pure-Python promotion evaluation engine.

Evaluate active promotions against a cart and return a PromoResult
with applied discounts, descriptions, and the updated grand total.

No DB writes happen here — only reads. The caller (billing route or
admin tester) decides how to act on the result.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import List


Q = Decimal('0.01')   # quantize target


@dataclass
class AppliedEntry:
    """One applied promo discount."""
    promo_id:        int | None
    promo_name:      str
    discount_amount: Decimal
    description:     str
    stackable:       bool


@dataclass
class PromoResult:
    """Result of evaluating all promotions against the cart."""
    applied:          List[AppliedEntry] = field(default_factory=list)
    total_discount:   Decimal = Decimal('0')
    original_total:   Decimal = Decimal('0')
    discounted_total: Decimal = Decimal('0')


# ── Individual handlers ───────────────────────────────────────────

def _handle_percentage_item(promo, cart: dict) -> Decimal:
    """Apply a percentage discount to specific product(s) in cart."""
    params      = promo.params_dict
    product_ids = {str(p) for p in params.get('product_ids', [])}
    percent     = Decimal(str(params.get('percent', 0)))

    discount = Decimal('0')
    for pid, item in cart.items():
        if pid in product_ids:
            price = Decimal(item['price'])
            qty   = Decimal(item['quantity'])
            line  = (price * qty).quantize(Q)
            discount += (line * percent / Decimal('100')).quantize(Q)
    return discount


def _handle_fixed_item(promo, cart: dict) -> Decimal:
    """Apply a fixed ₹ discount to specific product(s) in cart (capped at line total)."""
    params      = promo.params_dict
    product_ids = {str(p) for p in params.get('product_ids', [])}
    amount      = Decimal(str(params.get('amount', 0)))

    discount = Decimal('0')
    for pid, item in cart.items():
        if pid in product_ids:
            price    = Decimal(item['price'])
            qty      = Decimal(item['quantity'])
            line     = (price * qty).quantize(Q)
            discount += min(amount, line)   # cap at line total
    return discount


def _handle_bill_percentage(promo, cart: dict, cart_subtotal: Decimal) -> Decimal:
    """Apply a percentage off the entire bill subtotal."""
    percent = Decimal(str(promo.params_dict.get('percent', 0)))
    return (cart_subtotal * percent / Decimal('100')).quantize(Q)


def _handle_buy_x_get_y(promo, cart: dict) -> Decimal:
    """
    Buy X, Get Y free for a specific product.
    Example: buy 2, get 1 free → for every (buy+free) units, free_qty units are discounted.
    """
    params     = promo.params_dict
    product_id = str(params.get('product_id', ''))
    buy_qty    = int(params.get('buy_qty', 1))
    free_qty   = int(params.get('free_qty', 1))

    item = cart.get(product_id)
    if not item:
        return Decimal('0')

    total_qty  = int(item['quantity'])
    unit_price = Decimal(item['price'])   # for regular items this is unit price

    # Number of full cycles: e.g. buy 2 get 1 → cycle = 3 units
    cycle       = buy_qty + free_qty
    full_cycles = total_qty // cycle
    free_units  = full_cycles * free_qty

    return (unit_price * Decimal(free_units)).quantize(Q)


# ── Cart subtotal helper ──────────────────────────────────────────

def _cart_subtotal(cart: dict) -> Decimal:
    """Sum of price × qty for all items (pre-GST)."""
    total = Decimal('0')
    for item in cart.values():
        total += (Decimal(item['price']) * Decimal(item['quantity'])).quantize(Q)
    return total


# ── Main public function ──────────────────────────────────────────

def evaluate_promotions(cart: dict, promotions: list) -> PromoResult:
    """
    Evaluate a list of Promotion objects against the current cart.

    Stacking rules:
    1. Evaluate all promotions individually first.
    2. Stackable promos are all applied (summed).
    3. Non-stackable promos compete; only the single best one is kept.
    4. If the best non-stackable discount > total stackable discount,
       use only the non-stackable. Otherwise, use stacked discounts.

    Returns a PromoResult. All amounts are positive (discounts subtract).
    """
    if not cart or not promotions:
        subtotal = _cart_subtotal(cart) if cart else Decimal('0')
        result = PromoResult(original_total=subtotal, discounted_total=subtotal)
        return result

    subtotal = _cart_subtotal(cart)

    # Evaluate each promotion individually
    stackable_entries: List[AppliedEntry]     = []
    non_stackable_entries: List[AppliedEntry] = []

    for promo in promotions:
        if not promo.is_valid_today:
            continue

        disc = Decimal('0')

        if promo.promo_type == 'percentage_item':
            disc = _handle_percentage_item(promo, cart)
            params = promo.params_dict
            desc = f"{params.get('percent')}% off selected item(s)"

        elif promo.promo_type == 'fixed_item':
            disc = _handle_fixed_item(promo, cart)
            params = promo.params_dict
            desc = f"₹{params.get('amount')} off selected item(s)"

        elif promo.promo_type == 'bill_percentage':
            disc = _handle_bill_percentage(promo, cart, subtotal)
            params = promo.params_dict
            desc = f"{params.get('percent')}% off entire bill"

        elif promo.promo_type == 'buy_x_get_y':
            disc = _handle_buy_x_get_y(promo, cart)
            params = promo.params_dict
            desc = f"Buy {params.get('buy_qty')} Get {params.get('free_qty')} Free"

        else:
            continue   # unknown type — skip

        if disc <= Decimal('0'):
            continue   # no discount applicable

        entry = AppliedEntry(
            promo_id=promo.id,
            promo_name=promo.name,
            discount_amount=disc.quantize(Q),
            description=desc,
            stackable=promo.stackable,
        )

        if promo.stackable:
            stackable_entries.append(entry)
        else:
            non_stackable_entries.append(entry)

    # ── Determine final set of applied discounts ──────────────────
    stackable_total = sum((e.discount_amount for e in stackable_entries), start=Decimal('0'))

    best_non_stack: AppliedEntry | None = None
    if non_stackable_entries:
        best_non_stack = max(non_stackable_entries, key=lambda e: e.discount_amount)

    final_entries: List[AppliedEntry] = []

    if best_non_stack and best_non_stack.discount_amount > stackable_total:
        # Non-stackable beats everything — use only it
        final_entries = [best_non_stack]
    else:
        # Use all stackable promos
        final_entries = list(stackable_entries)
        # Add the best non-stackable if it further increases the discount
        if best_non_stack and best_non_stack.discount_amount > Decimal('0'):
            # Only add if stackable_total > 0 (i.e., non-stack beat standalone, so skip)
            # Actually in this branch stackable >= non-stack, so we already won with stackable
            pass

    total_discount   = sum((e.discount_amount for e in final_entries), start=Decimal('0')).quantize(Q)
    # Cap discount at subtotal to never produce negative totals
    total_discount   = min(total_discount, subtotal)
    discounted_total = (subtotal - total_discount).quantize(Q)

    return PromoResult(
        applied=final_entries,
        total_discount=total_discount,
        original_total=subtotal,
        discounted_total=discounted_total,
    )
