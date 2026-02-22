from app import create_app, db
from app.inventory.models import Product, ProductVariant
from decimal import Decimal

app = create_app("development")

with app.app_context():
    for i in range(1, 101):
        barcode = f"TEST{i:05d}"
        existing = Product.query.filter_by(barcode=barcode).first()
        if existing:
            continue

        product = Product(
            name=f"Test Product {i}",
            gst_percent=18
        )
        db.session.add(product)
        db.session.flush()

        variant = ProductVariant(
            product_id=product.id,
            barcode=barcode,
            size="Standard",
            color="Red",
            price=Decimal("100.00"),
            stock=500
        )
        db.session.add(variant)

    db.session.commit()
    print("✅ 100 test products created successfully.")