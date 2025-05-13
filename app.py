from flask import Flask, render_template, request, redirect, session
import csv, os
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'experiment_secret'

# 商品データ読み込み
def load_products():
    with open('data/products.csv', encoding='utf-8') as f:
        return list(csv.DictReader(f))

# ログ記録
def log_action(action, product_id=None, quantity=None):
    log_file = 'data/log.csv'
    with open(log_file, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            session.get('participant_id', 'unknown'),
            session.get('group', 'unknown'),
            datetime.now().isoformat(),
            action,
            product_id,
            quantity
        ])

@app.route('/')
def index():
    products = load_products()
    return render_template('index.html', products=products)

@app.route('/product/<product_id>')
def product(product_id):
    group = request.args.get('group', 'ctrl')
    session['group'] = group
    session['participant_id'] = request.args.get('id', 'anon')
    products = load_products()
    product = next((p for p in products if p['id'] == product_id), None)
    log_action('view', product_id)
    return render_template('product.html', product=product, group=group)

@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    product_id = request.form['product_id']
    quantity = int(request.form['quantity'])
    cart = session.get('cart', {})
    cart[product_id] = cart.get(product_id, 0) + quantity
    session['cart'] = cart
    log_action('add_to_cart', product_id, quantity)
    return redirect('/cart')

@app.route('/cart')
def cart():
    products = load_products()
    cart = session.get('cart', {})
    cart_items = []
    for pid, qty in cart.items():
        product = next((p for p in products if p['id'] == pid), None)
        if product:
            product['quantity'] = qty
            product['subtotal'] = int(product['price']) * qty
            cart_items.append(product)
    return render_template('cart.html', cart_items=cart_items)

@app.route('/confirm')
def confirm():
    products = load_products()
    cart = session.get('cart', {})
    cart_items = []
    total_price = 0
    for pid, qty in cart.items():
        product = next((p for p in products if p['id'] == pid), None)
        if product:
            subtotal = int(product['price']) * qty
            total_price += subtotal
            product['quantity'] = qty
            product['subtotal'] = subtotal
            cart_items.append(product)
    return render_template('confirm.html', cart_items=cart_items, total=total_price)

@app.route('/checkout', methods=['POST'])
def checkout():
    log_action('checkout')
    session.clear()
    return render_template('thanks.html')

if __name__ == '__main__':
    app.run(debug=True)
