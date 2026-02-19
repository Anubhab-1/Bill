from flask import render_template, request, flash, redirect, url_for, jsonify
from app import db
from app.customers import customers
from app.customers.models import Customer, GiftCard
from app.auth.decorators import login_required, admin_required

@customers.route('/search')
@login_required
def search():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])
    
    # Search by phone or name
    results = Customer.query.filter(
        (Customer.phone.ilike(f'%{q}%')) | 
        (Customer.name.ilike(f'%{q}%'))
    ).limit(10).all()
    
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'phone': c.phone,
        'points': c.points
    } for c in results])

@customers.route('/create', methods=['POST'])
@login_required
def create():
    data = request.get_json()
    name = data.get('name')
    phone = data.get('phone')
    email = data.get('email')
    
    if not name or not phone:
        return jsonify({'error': 'Name and Phone are required'}), 400
        
    if Customer.query.filter_by(phone=phone).first():
        return jsonify({'error': 'Customer with this phone already exists'}), 400
        
    c = Customer(name=name, phone=phone, email=email)
    db.session.add(c)
    db.session.commit()
    
    return jsonify({
        'id': c.id,
        'name': c.name,
        'phone': c.phone,
        'points': c.points,
        'message': 'Customer created successfully'
    })

@customers.route('/giftcard/check')
@login_required
def check_gift_card():
    code = request.args.get('code', '').strip()
    gc = GiftCard.query.filter_by(code=code, is_active=True).first()
    
    if not gc:
        return jsonify({'valid': False, 'error': 'Invalid or inactive gift card'})
        
    return jsonify({
        'valid': True,
        'code': gc.code,
        'balance': str(gc.balance)
    })
