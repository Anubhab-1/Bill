"""Validation helpers for inventory product and variant forms."""
from decimal import Decimal, InvalidOperation


def validate_product_form(form_data: dict, existing_barcode: str = None) -> dict:
    """Validate create/edit product form payload."""
    del existing_barcode  # Backward-compatible function signature.
    errors = {}

    name = form_data.get('name', '').strip()
    if not name:
        errors['name'] = 'Product name is required.'
    elif len(name) > 200:
        errors['name'] = 'Product name must be 200 characters or fewer.'

    brand = form_data.get('brand', '').strip()
    if len(brand) > 100:
        errors['brand'] = 'Brand must be 100 characters or fewer.'

    category = form_data.get('category', '').strip()
    if len(category) > 100:
        errors['category'] = 'Category must be 100 characters or fewer.'

    description = form_data.get('description', '').strip()
    if len(description) > 5000:
        errors['description'] = 'Description must be 5000 characters or fewer.'

    gst_raw = form_data.get('gst_percent', '0').strip()
    try:
        gst = int(gst_raw)
        if not (0 <= gst <= 28):
            errors['gst_percent'] = 'GST must be between 0 and 28.'
    except ValueError:
        errors['gst_percent'] = 'GST must be a whole number.'

    is_weighed = form_data.get('is_weighed') in ('1', 'true', 'on', 'yes', True)
    ppk_raw = form_data.get('price_per_kg', '').strip()
    if is_weighed:
        if not ppk_raw:
            errors['price_per_kg'] = 'Price per kg is required for weighed items.'
        else:
            try:
                ppk = Decimal(ppk_raw)
                if ppk <= 0:
                    errors['price_per_kg'] = 'Price per kg must be greater than zero.'
            except InvalidOperation:
                errors['price_per_kg'] = 'Price per kg must be a valid number.'
    elif ppk_raw:
        try:
            ppk = Decimal(ppk_raw)
            if ppk <= 0:
                errors['price_per_kg'] = 'Price per kg must be greater than zero.'
        except InvalidOperation:
            errors['price_per_kg'] = 'Price per kg must be a valid number.'

    return errors


def parse_product_form(form_data: dict) -> dict:
    """Convert validated product form strings into model-ready values."""
    is_weighed = form_data.get('is_weighed') in ('1', 'true', 'on', 'yes', True)
    ppk_raw = form_data.get('price_per_kg', '').strip()
    return {
        'name': form_data.get('name', '').strip(),
        'brand': form_data.get('brand', '').strip() or None,
        'category': form_data.get('category', '').strip() or None,
        'description': form_data.get('description', '').strip() or None,
        'gst_percent': int(form_data.get('gst_percent', '0').strip()),
        'is_weighed': is_weighed,
        'price_per_kg': Decimal(ppk_raw) if ppk_raw else None,
    }


def validate_variant_form(form_data: dict) -> dict:
    """Validate create/edit variant form payload."""
    errors = {}

    size = form_data.get('size', '').strip()
    if not size:
        errors['size'] = 'Size is required.'
    elif len(size) > 10:
        errors['size'] = 'Size must be 10 characters or fewer.'

    color = form_data.get('color', '').strip()
    if not color:
        errors['color'] = 'Color is required.'
    elif len(color) > 50:
        errors['color'] = 'Color must be 50 characters or fewer.'

    barcode = form_data.get('barcode', '').strip()
    if not barcode:
        errors['barcode'] = 'Barcode is required.'
    elif len(barcode) > 100:
        errors['barcode'] = 'Barcode must be 100 characters or fewer.'

    price_raw = form_data.get('price', '').strip()
    if not price_raw:
        errors['price'] = 'Price is required.'
    else:
        try:
            price = Decimal(price_raw)
            if price <= 0:
                errors['price'] = 'Price must be greater than zero.'
        except InvalidOperation:
            errors['price'] = 'Price must be a valid number.'

    stock_raw = form_data.get('stock', '').strip()
    if stock_raw == '':
        errors['stock'] = 'Stock is required.'
    else:
        try:
            stock = int(stock_raw)
            if stock < 0:
                errors['stock'] = 'Stock cannot be negative.'
        except ValueError:
            errors['stock'] = 'Stock must be a whole number.'

    sku = form_data.get('sku', '').strip()
    if len(sku) > 100:
        errors['sku'] = 'SKU must be 100 characters or fewer.'

    return errors


def parse_variant_form(form_data: dict) -> dict:
    """Convert validated variant form strings into model-ready values."""
    return {
        'size': form_data.get('size', '').strip(),
        'color': form_data.get('color', '').strip(),
        'sku': form_data.get('sku', '').strip() or None,
        'barcode': form_data.get('barcode', '').strip(),
        'price': Decimal(form_data.get('price', '0').strip()),
        'stock': int(form_data.get('stock', '0').strip()),
        'is_active': True,
    }
