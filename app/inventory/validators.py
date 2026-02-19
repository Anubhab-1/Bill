"""
app/inventory/validators.py
----------------------------
Pure-Python validation for product form data.
Returns a dict of field -> error_message.
An empty dict means all fields are valid.
"""
from decimal import Decimal, InvalidOperation


def validate_product_form(form_data: dict, existing_barcode: str = None) -> dict:
    """
    Validate raw form data for create / edit product.

    Args:
        form_data:        dict of raw string values from request.form
        existing_barcode: current barcode of the product being edited
                          (used to allow the same barcode on edit without
                          triggering the uniqueness check against itself)

    Returns:
        dict of {field_name: error_message} — empty if all valid.
    """
    errors = {}

    # ── name ─────────────────────────────────────────────────────
    name = form_data.get('name', '').strip()
    if not name:
        errors['name'] = 'Product name is required.'
    elif len(name) > 200:
        errors['name'] = 'Product name must be 200 characters or fewer.'

    # ── barcode ───────────────────────────────────────────────────
    barcode = form_data.get('barcode', '').strip()
    if not barcode:
        errors['barcode'] = 'Barcode is required.'
    elif len(barcode) > 100:
        errors['barcode'] = 'Barcode must be 100 characters or fewer.'

    # ── price ─────────────────────────────────────────────────────
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

    # ── stock ─────────────────────────────────────────────────────
    stock_raw = form_data.get('stock', '0').strip()
    try:
        stock = int(stock_raw)
        if stock < 0:
            errors['stock'] = 'Stock cannot be negative.'
    except ValueError:
        errors['stock'] = 'Stock must be a whole number.'

    # ── gst_percent ───────────────────────────────────────────────
    gst_raw = form_data.get('gst_percent', '0').strip()
    try:
        gst = int(gst_raw)
        if not (0 <= gst <= 28):
            errors['gst_percent'] = 'GST must be between 0 and 28.'
    except ValueError:
        errors['gst_percent'] = 'GST must be a whole number.'

    # ── is_weighed / price_per_kg ───────────────────────────────────
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

    return errors


def parse_product_form(form_data: dict) -> dict:
    """
    Convert validated raw form strings to correct Python types.
    Call only after validate_product_form returns no errors.
    """
    from decimal import Decimal
    is_weighed = form_data.get('is_weighed') in ('1', 'true', 'on', 'yes', True)
    ppk_raw = form_data.get('price_per_kg', '').strip()
    return {
        'name':         form_data.get('name', '').strip(),
        'barcode':      form_data.get('barcode', '').strip(),
        'price':        Decimal(form_data.get('price', '0').strip()),
        'stock':        int(form_data.get('stock', '0').strip()),
        'gst_percent':  int(form_data.get('gst_percent', '0').strip()),
        'is_weighed':   is_weighed,
        'price_per_kg': Decimal(ppk_raw) if ppk_raw else None,
    }
