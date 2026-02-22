from decimal import Decimal

from flask import session


CART_KEY = 'cart'


def get_cart() -> dict:
    return session.get(CART_KEY, {})


def add_to_cart(variant) -> None:
    cart = get_cart()
    key = str(variant.id)
    product = variant.product

    if key in cart:
        cart[key]['quantity'] += 1
    else:
        cart[key] = {
            'product_id': product.id,
            'name': product.name,
            'barcode': variant.barcode,
            'price': str(variant.price),
            'gst_percent': product.gst_percent,
            'quantity': 1,
            'is_weighed': False,
            'weight_kg': None,
            'price_per_kg': None,
            'variant_id': variant.id,
            'size': variant.size,
            'color': variant.color,
        }

    session[CART_KEY] = cart
    session.modified = True


def add_weighed_to_cart(variant, weight_kg: Decimal) -> None:
    cart = get_cart()
    key = str(variant.id)
    product = variant.product
    line_price = (Decimal(str(product.price_per_kg)) * weight_kg).quantize(Decimal('0.01'))

    if key in cart and cart[key].get('is_weighed'):
        cart[key]['weight_kg'] = str(weight_kg)
        cart[key]['price'] = str(line_price)
    else:
        cart[key] = {
            'product_id': product.id,
            'name': product.name,
            'barcode': variant.barcode,
            'price': str(line_price),
            'gst_percent': product.gst_percent,
            'quantity': 1,
            'is_weighed': True,
            'weight_kg': str(weight_kg),
            'price_per_kg': str(product.price_per_kg),
            'variant_id': variant.id,
            'size': variant.size,
            'color': variant.color,
        }

    session[CART_KEY] = cart
    session.modified = True


def update_cart_quantity(variant_id: int, quantity: int) -> None:
    cart = get_cart()
    key = str(variant_id)

    if key in cart:
        if quantity <= 0:
            cart.pop(key)
        else:
            cart[key]['quantity'] = quantity

        session[CART_KEY] = cart
        session.modified = True


def remove_from_cart(variant_id: int) -> None:
    cart = get_cart()
    cart.pop(str(variant_id), None)
    session[CART_KEY] = cart
    session.modified = True


def clear_cart() -> None:
    session.pop(CART_KEY, None)
    session.modified = True


def cart_totals(cart: dict) -> dict:
    subtotal = Decimal('0')
    gst_total = Decimal('0')

    for item in cart.values():
        price = Decimal(item['price'])
        qty = Decimal(item['quantity'])
        gst_rate = Decimal(item['gst_percent']) / Decimal('100')

        line_subtotal = (price * qty).quantize(Decimal('0.01'))
        line_gst = (line_subtotal * gst_rate).quantize(Decimal('0.01'))

        subtotal += line_subtotal
        gst_total += line_gst

    return {
        'subtotal': subtotal,
        'gst_total': gst_total,
        'grand_total': subtotal + gst_total,
    }
