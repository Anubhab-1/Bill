import click
from datetime import date, timedelta, datetime
import random
from decimal import Decimal
from flask.cli import with_appcontext
from app import db
from app.auth.models import User, RoleEnum
from app.inventory.models import Product, ProductBatch, InventoryLog
from app.billing.models import Sale, SaleItem, CashSession, InvoiceSequence
from app.customers.models import Customer
from app.billing.invoice import generate_invoice_number

@click.command('seed-history')
@with_appcontext
def seed_history():
    """Generates 30 days of realistic sales history."""
    click.echo("🌱 Seeding 30 days of history...")
    
    # Ensure users exist
    admin = User.query.filter_by(role=RoleEnum.admin).first()
    cashiers = User.query.filter_by(role=RoleEnum.cashier).all()
    if not cashiers:
        click.echo("❌ No cashiers found. Run 'flask seed-demo' first.")
        return

    # Ensure customers
    if Customer.query.count() < 10:
        names = ["Aarav Patel", "Vihaan Rao", "Aditya Sharma", "Sai Kumar", "Reyansh Gupta", 
                 "Muhammad Khan", "Arjun Singh", "Riaan Verma", "Krishna Das", "Ishaan Nair"]
        for i, name in enumerate(names):
            if not Customer.query.filter_by(phone=f"98765432{i:02d}").first():
                c = Customer(name=name, phone=f"98765432{i:02d}", email=f"cust{i}@example.com")
                db.session.add(c)
        db.session.commit()
    
    customers = Customer.query.all()
    products = Product.query.all()
    
    if not products:
        click.echo("❌ No products found.")
        return

    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    
    # Clear existing sales if you want a clean slate (optional, skip if risky)
    # SaleItem.query.delete()
    # Sale.query.delete()
    # db.session.commit()

    total_sales_generated = 0

    current_date = start_date
    while current_date <= end_date:
        # Weekend multiplier: Fri/Sat/Sun get more sales
        is_weekend = current_date.weekday() >= 4
        num_sales = random.randint(15, 30) if is_weekend else random.randint(5, 12)
        
        click.echo(f"  📅 {current_date}: Generating {num_sales} sales...")

        for _ in range(num_sales):
            cashier = random.choice(cashiers)
            customer = random.choice(customers) if random.random() < 0.3 else None # 30% attach rate
            
            # Create timestamp (9 AM to 9 PM)
            hour = random.randint(9, 20)
            minute = random.randint(0, 59)
            sale_time = datetime.combine(current_date, datetime.min.time()).replace(hour=hour, minute=minute)

            # Generate Invoice Number
            # We manually manage sequence for backdated rows to avoid messing up current live sequence
            # But simpler to just use random string for history
            inv_num = f"{current_date.year}-{random.randint(10000, 99999)}"

            sale = Sale(
                invoice_number=inv_num,
                cashier_id=cashier.id,
                customer_id=customer.id if customer else None,
                created_at=sale_time,
                payment_method=random.choice(['cash', 'card', 'upi', 'cash', 'upi']) # Cash/UPI dominant
            )
            
            # Add Items
            num_items = random.randint(1, 6)
            total_amt = Decimal(0)
            gst_total = Decimal(0)
            
            for _ in range(num_items):
                prod = random.choice(products)
                qty = random.randint(1, 3)
                price = prod.price
                gst_pct = prod.gst_percent
                
                subtotal = price * qty
                gst_amt = (subtotal * Decimal(gst_pct) / 100).quantize(Decimal('0.01'))
                
                item = SaleItem(
                    product=prod,
                    quantity=qty,
                    price_at_sale=price,
                    gst_percent=gst_pct,
                    subtotal=subtotal,
                    weight_kg=None,
                    unit_label=None
                )
                sale.items.append(item)
                
                total_amt += subtotal
                gst_total += gst_amt
                
                # Deduct stock (simulated)
                # We won't actually deduct current stock to avoid negative numbers
                # assuming stock was replenished
            
            sale.total_amount = total_amt
            sale.gst_total = gst_total
            sale.grand_total = total_amt + gst_total
            sale.is_printed = True
            
            db.session.add(sale)
            total_sales_generated += 1
        
        db.session.commit() # Commit daily
        current_date += timedelta(days=1)

    click.echo(f"✅ Generated {total_sales_generated} historical sales.")
