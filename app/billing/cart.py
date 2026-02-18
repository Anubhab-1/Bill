"""
app/billing/cart.py
--------------------
Stateless helpers for the session-based shopping cart.

Cart structure stored in Flask session under key 'cart':
{
    "<product_id_str>": {
        "name":        str,
        "barcode":     str,
        "price":       str,   ← stored as string to survive JSON serialisation
        "gst_percent": int,
        "quantity":    int
    },
    ...
}

All money values are kept as strings in the session and converted
to Decimal only when computing totals — avoids float contamination.
"""
from decimal import Decimal
from flask import session


CART_KEY = 'cart'


# ── Read ──────────────────────────────────────────────────────────

def get_cart() -> dict:
    """Return the current cart dict (may be empty)."""
    return session.get(CART_KEY, {})


# ── Write ─────────────────────────────────────────────────────────

def add_to_cart(product) -> None:
    """
    Add one unit of `product` to the cart.
    If already present, increments quantity by 1.
    """
    cart = get_cart()
    key  = str(product.id)

    if key in cart:
        cart[key]['quantity'] += 1
    else:
        cart[key] = {
            'name':        product.name,
            'barcode':     product.barcode,
            'price':       str(product.price),   # Decimal → str for JSON safety
            'gst_percent': product.gst_percent,
            'quantity':    1,
        }

    session[CART_KEY] = cart
    session.modified   = True


def remove_from_cart(product_id: int) -> None:
    """Remove a product entirely from the cart."""
    cart = get_cart()
    cart.pop(str(product_id), None)
    session[CART_KEY] = cart
    session.modified   = True


def clear_cart() -> None:
    """Empty the cart after a completed sale."""
    session.pop(CART_KEY, None)
    session.modified = True


# ── Totals ────────────────────────────────────────────────────────

def cart_totals(cart: dict) -> dict:
    """
    Compute subtotal, gst_total, and grand_total for the cart.
    All arithmetic uses Decimal — no float.

    Returns:
        {
            'subtotal':    Decimal,   ← sum of (price × qty) before GST
            'gst_total':   Decimal,   ← sum of GST amounts
            'grand_total': Decimal,   ← subtotal + gst_total
        }
    """
    subtotal  = Decimal('0')
    gst_total = Decimal('0')

    for item in cart.values():
        price    = Decimal(item['price'])
        qty      = Decimal(item['quantity'])
        gst_rate = Decimal(item['gst_percent']) / Decimal('100')

        line_subtotal = (price * qty).quantize(Decimal('0.01'))
        line_gst      = (line_subtotal * gst_rate).quantize(Decimal('0.01'))

        subtotal  += line_subtotal
        gst_total += line_gst

    return {
        'subtotal':    subtotal,
        'gst_total':   gst_total,
        'grand_total': subtotal + gst_total,
    }
