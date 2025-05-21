from flask import Flask, render_template, request, redirect, url_for, session
import pandas as pd
import csv
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# 商品情報を読み込む
def load_products():
    df = pd.read_csv('data/products.csv', dtype={'id': str})
    return df.to_dict(orient='records')

# 商品スペックを読み込む（id列を文字列として処理）
specs_df = pd.read_csv('data/specs.csv', dtype={'id': str})

# ログ出力
def log_action(action, **kwargs):
    if 'user_id' not in session:
        return
    log_path = 'data/logs.csv'
    file_exists = os.path.isfile(log_path)
    with open(log_path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['timestamp', 'user_id', 'action', 'details'])
        details = ', '.join([f'{k}={v}' for k, v in kwargs.items()])
        writer.writerow([datetime.now(), session['user_id'], action, details])

# ==== ID入力画面 ====
@app.route('/', methods=['GET', 'POST'])
def input_id():
    if request.method == 'POST':
        session['user_id'] = request.form['user_id']
        log_action("ID入力", page="input_id")
        return redirect(url_for('index'))
    return render_template('input_id.html')

# ==== 商品一覧 ====
@app.route('/index')
def index():
    products = load_products()
    log_action("商品一覧表示", page="index")
    return render_template('index.html', products=products)

# ==== 商品詳細ページ ====
@app.route('/product/<product_id>')
def product_detail(product_id):
    products = load_products()
    product = next((p for p in products if p['id'] == product_id), None)
    if not product:
        return "商品が見つかりません", 404

    # specs.csv からスペック取得
    spec_row = specs_df[specs_df['id'] == product_id]
    specs = spec_row['specs'].values[0] if not spec_row.empty else ""

    log_action("商品詳細表示", product_id=product_id, page="詳細")
    return render_template('product.html', product=product, specs=specs)

# ==== カートに追加 ====
@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    product_id = request.form['product_id']
    quantity = int(request.form['quantity'])

    cart = session.get('cart', {})
    cart[product_id] = cart.get(product_id, 0) + quantity
    session['cart'] = cart
    session['recently_added'] = quantity

    log_action("カート追加", product_id=product_id, quantity=quantity, page="add_to_cart")
    return redirect(url_for('product_detail', product_id=product_id))

# ==== カート表示 ====
@app.route('/cart')
def cart():
    products = load_products()
    cart = session.get('cart', {})
    cart_items = []
    total = 0
    total_quantity = 0

    for product_id, quantity in cart.items():
        product = next((p for p in products if p['id'] == product_id), None)
        if product:
            subtotal = int(product['price']) * quantity
            cart_items.append({
                'id': product_id,
                'name': product['name'],
                'image': product['image'],
                'price': product['price'],
                'quantity': quantity,
                'subtotal': subtotal
            })
            total += subtotal
            total_quantity += quantity

    log_action("カート表示", page="cart")
    return render_template('cart.html', cart_items=cart_items, total=total, total_quantity=total_quantity)

# ==== 数量更新 ====
@app.route('/update_cart', methods=['POST'])
def update_cart():
    cart = session.get('cart', {})
    for product_id in cart.keys():
        quantity = int(request.form.get(f'quantity_{product_id}', 1))
        cart[product_id] = quantity
    session['cart'] = cart
    log_action("カート更新", cart=session['cart'], page="update_cart")
    return redirect(url_for('cart'))

# ==== 購入確認画面 ====
@app.route('/confirm')
def confirm():
    products = load_products()
    cart = session.get('cart', {})
    cart_items = []
    total = 0

    for product_id, quantity in cart.items():
        product = next((p for p in products if p['id'] == product_id), None)
        if product:
            subtotal = int(product['price']) * quantity
            cart_items.append({
                'id': product_id,
                'name': product['name'],
                'price': product['price'],
                'quantity': quantity,
                'subtotal': subtotal
            })
            total += subtotal

    log_action("購入確認", page="confirm")
    return render_template('confirm.html', cart_items=cart_items, total=total)

# ==== 購入完了画面 ====
@app.route('/complete', methods=['POST'])
def complete():
    log_action("購入完了", page="thanks")
    session.pop('cart', None)
    session.pop('recently_added', None)
    return render_template('thanks.html')
