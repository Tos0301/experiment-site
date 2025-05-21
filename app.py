from flask import Flask, render_template, request, redirect, url_for, session
from datetime import datetime
import csv
import os
import pandas as pd
import base64
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)
app.secret_key = 'your-secret-key'

# ==== Google Sheets 認証設定 ====
SERVICE_ACCOUNT_FILE = 'credentials.json'
SPREADSHEET_ID = '1KNZ49or81ECH9EVXYeKjAv-ooSnXMbP3dC10e2gQR3g'
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

b64_content = os.getenv('GOOGLE_CREDENTIALS')
if b64_content:
    with open('credentials.json', 'wb') as f:
        f.write(base64.b64decode(b64_content))

creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
client = gspread.authorize(creds)
SHEET = client.open_by_key(SPREADSHEET_ID).sheet1  # ← 修正済み

# ==== ログ記録 ====
def log_action(action, total_price='', products='', quantities='', subtotals='', page=''):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    participant_id = session.get('participant_id', 'unknown')
    SHEET.append_row([
        timestamp, participant_id, action, total_price, products, quantities, subtotals, page
    ])

# ==== 商品読み込み ====
def load_products():
    df = pd.read_csv('data/products.csv', dtype=str)
    return df.to_dict(orient='records')

def load_specs():
    return pd.read_csv('data/specs.csv', dtype=str)

specs_df = load_specs()

# ==== ルート ====
@app.route('/')
def root():
    return redirect(url_for('input_id'))

@app.route('/input_id')
def input_id():
    return render_template('input_id.html')

@app.route('/set_id', methods=['POST'])
def set_participant_id():
    participant_id = request.form.get('participant_id')
    session['participant_id'] = participant_id
    log_action("ID登録", page="ID入力")
    return redirect(url_for('index'))

@app.route('/index')
def index():
    products = load_products()
    log_action("商品一覧表示", page="一覧")
    return render_template('index.html', products=products)

@app.route('/product/<product_id>')
def product_detail(product_id):
    products = load_products()
    product = next((p for p in products if p['id'] == product_id), None)
    if not product:
        return "商品が見つかりません", 404
    spec_row = specs_df[specs_df['id'] == product_id]
    specs = spec_row['specs'].values[0] if not spec_row.empty else ""
    log_action("商品詳細表示", products=product_id, page="詳細")
    return render_template('product.html', product=product, specs=specs)

@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    product_id = request.form['product_id']
    quantity = int(request.form['quantity'])
    cart = session.get('cart', {})
    cart[product_id] = cart.get(product_id, 0) + quantity
    session['cart'] = cart
    log_action("カート追加", products=product_id, quantities=quantity, page="詳細")
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
                'id': pid,
                'name': product['name'],
                'image': product['image'],
                'price': product['price'],
                'quantity': quantity,
                'subtotal': subtotal
            })
            total += subtotal
            total_count += quantity
    log_action("カート表示", page="カート")
    return render_template('cart.html', cart_items=cart_items, total=total, cart_count=total_count)

@app.route('/update_quantity', methods=['POST'])
def update_quantity():
    product_id = request.form['product_id']
    quantity = int(request.form['quantity'])
    cart = session.get('cart', {})
    if quantity > 0:
        cart[product_id] = quantity
        log_action("数量更新", products=product_id, quantities=quantity, page="カート")
    else:
        cart.pop(product_id, None)
        log_action("商品削除", products=product_id, quantities=0, page="カート")
    session['cart'] = cart
    return redirect(url_for('cart'))

@app.route('/confirm')
def confirm():
    products = load_products()
    cart = session.get('cart', {})
    cart_items = []
    total = 0
    product_ids, quantities, subtotals = [], [], []
    for pid, qty in cart.items():
        product = next((p for p in products if p['id'] == pid), None)
        if product:
            subtotal = int(product['price']) * qty
            cart_items.append({
                'name': product['name'],
                'quantity': qty,
                'subtotal': subtotal
            })
            total += subtotal
            product_ids.append(pid)
            quantities.append(str(qty))
            subtotals.append(str(subtotal))
    log_action("購入確認へ進む", total_price=total,
               products=' / '.join(product_ids),
               quantities=' / '.join(quantities),
               subtotals=' / '.join(subtotals),
               page="確認")
    return render_template('confirm.html', cart_items=cart_items, total=total, cart_count=sum(cart.values()))

@app.route('/complete', methods=['POST'])
def complete():
    cart = session.get('cart', {})
    products = load_products()
    product_ids, quantities, subtotals = [], [], []
    total = 0
    for pid, qty in cart.items():
        product = next((p for p in products if p['id'] == pid), None)
        if product:
            subtotal = int(product['price']) * qty
            total += subtotal
            product_ids.append(pid)
            quantities.append(str(qty))
            subtotals.append(str(subtotal))
    log_action("注文確定", total_price=total,
               products=' / '.join(product_ids),
               quantities=' / '.join(quantities),
               subtotals=' / '.join(subtotals),
               page="完了")
    session.pop('cart', None)
    return render_template('thanks.html')

# ==== POST 遷移系 ====
@app.route('/go_product', methods=['POST'])
def go_product():
    pid = request.form.get('product_id')
    log_action("商品詳細へ", products=pid, page="一覧")
    return redirect(url_for('product_detail', product_id=pid))

@app.route('/go_cart', methods=['POST'])
def go_cart():
    log_action("カートへ", page="詳細")
    return redirect(url_for('cart'))

@app.route('/go_index', methods=['POST'])
def go_index():
    log_action("商品一覧へ戻る", page="戻る")
    return redirect(url_for('index'))

@app.route('/back_to_cart', methods=['POST'])
def back_to_cart():
    log_action("カートに戻る", page="確認")
    return redirect(url_for('cart'))

# ==== 実行設定 ====
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
