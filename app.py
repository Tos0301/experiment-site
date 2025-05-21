from flask import Flask, render_template, request, redirect, url_for, session
import csv
import os
import pandas as pd
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# === 商品情報読み込み ===
def load_products():
    with open('data/products.csv', newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        return list(reader)

# === 商品スペック読み込み ===
def load_specs():
    return pd.read_csv('data/specs.csv', dtype=str)

specs_df = load_specs()

# === ログ記録 ===
def log_action(action, **kwargs):
    log_data = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        **kwargs
    }
    log_file = 'data/logs.csv'
    file_exists = os.path.isfile(log_file)
    with open(log_file, 'a', newline='', encoding='utf-8') as csvfile:
        fieldnames = log_data.keys()
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(log_data)

# === ID入力画面 ===
@app.route('/')
def input_id():
    return render_template('input_id.html')

@app.route('/set_id', methods=['POST'])
def set_participant_id():
    participant_id = request.form.get('participant_id')
    if participant_id:
        session['participant_id'] = participant_id
        log_action(f"ID入力: {participant_id}", participant_id)
        return redirect(url_for('index'))
    return redirect(url_for('input_id'))


# === 商品一覧ページ ===
@app.route('/index')
def index():
    products = load_products()
    log_action("商品一覧表示", user_id=session.get('user_id', '不明'))
    return render_template('index.html', products=products)

# === 商品詳細ページ ===
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

# === カート操作 ===
@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    product_id = request.form['product_id']
    quantity = int(request.form['quantity'])
    cart = session.get('cart', {})
    cart[product_id] = cart.get(product_id, 0) + quantity
    session['cart'] = cart
    log_action("カートに追加", product_id=product_id, quantity=quantity, user_id=session.get('user_id', '不明'))
    return redirect(url_for('product_detail', product_id=product_id))

@app.route('/cart')
def cart():
    products = load_products()
    cart = session.get('cart', {})
    cart_items = []
    total = 0
    total_count = 0
    for product in products:
        pid = product['id']
        if pid in cart:
            quantity = cart[pid]
            subtotal = int(product['price']) * quantity
            cart_items.append({
                'product': product,
                'quantity': quantity,
                'subtotal': subtotal
            })
            total += subtotal
            total_count += quantity
    return render_template('cart.html', cart_items=cart_items, total=total, total_count=total_count)

# === 注文確認ページ ===
@app.route('/confirm')
def confirm():
    products = load_products()
    cart = session.get('cart', {})
    cart_items = []
    total = 0
    for product in products:
        pid = product['id']
        if pid in cart:
            quantity = cart[pid]
            subtotal = int(product['price']) * quantity
            cart_items.append({
                'product': product,
                'quantity': quantity,
                'subtotal': subtotal
            })
            total += subtotal
    return render_template('confirm.html', cart_items=cart_items, total=total)

# === 注文完了処理 ===
@app.route('/complete', methods=['POST'])
def complete():
    log_action("注文確定", user_id=session.get('user_id', '不明'), cart=session.get('cart', {}))
    session.pop('cart', None)
    return render_template('thanks.html')

# === 実行設定（Render対応） ===
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
