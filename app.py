from flask import Flask, render_template, request, redirect, url_for, session
from datetime import datetime
import csv
import os
import base64
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)
app.secret_key = 'your-secret-key'

# ==== Google Sheets 認証設定（環境変数からjson生成） ====
SERVICE_ACCOUNT_FILE = 'credentials.json'
SPREADSHEET_NAME = 'ExperimentLogs'
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# base64から認証ファイル復元（Render環境用）
b64_content = os.getenv('GOOGLE_SERVICE_KEY_BASE64')
if b64_content:
    with open(SERVICE_ACCOUNT_FILE, 'wb') as f:
        f.write(base64.b64decode(b64_content))

creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
client = gspread.authorize(creds)
SHEET = client.open(SPREADSHEET_NAME).sheet1

# ==== ログ記録関数 ====
def log_action(action, product_id='', quantity='', page=''):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    SHEET.append_row([timestamp, action, product_id, quantity, page])

# ==== 商品データ読み込み ====
def load_products():
    products = []
    with open('data/products.csv', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            products.append(row)
    return products

# ==== 商品一覧ページ ====
@app.route('/')
def index():
    products = load_products()
    log_action("商品一覧表示", page="一覧")
    return render_template('index.html', products=products)

# ==== 商品詳細ページ ====
@app.route('/product/<product_id>')
def product_detail(product_id):
    products = load_products()
    product = next((p for p in products if p['id'] == product_id), None)
    if not product:
        return "商品が見つかりません", 404
    log_action("商品詳細表示", product_id=product_id, page="詳細")
    return render_template('product.html', product=product)

# ==== カートに追加 ====
@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    product_id = request.form['product_id']
    quantity = int(request.form['quantity'])
    cart = session.get('cart', {})
    cart[product_id] = cart.get(product_id, 0) + quantity
    session['cart'] = cart
    log_action("カート追加", product_id=product_id, quantity=quantity, page="追加")
    return '', 204

# ==== カート表示 ====
@app.route('/cart')
def cart():
    cart = session.get('cart', {})
    products = load_products()
    cart_items = []
    total = 0
    for pid, qty in cart.items():
        product = next((p for p in products if p['id'] == pid), None)
        if product:
            subtotal = int(product['price']) * qty
            cart_items.append({
                'id': pid,
                'name': product['name'],
                'price': int(product['price']),
                'image': product['image'],
                'quantity': qty,
                'subtotal': subtotal
            })
            total += subtotal
    return render_template('cart.html', cart_items=cart_items, total=total)

# ==== 数量更新 ====
@app.route('/update_quantity', methods=['POST'])
def update_quantity():
    product_id = request.form['product_id']
    quantity = int(request.form['quantity'])
    cart = session.get('cart', {})
    if product_id in cart:
        cart[product_id] = quantity
        session['cart'] = cart
        log_action("数量更新", product_id=product_id, quantity=quantity, page="カート")
    return redirect(url_for('cart'))

# ==== 購入確認ページ ====
@app.route('/confirm')
def confirm():
    cart = session.get('cart', {})
    products = load_products()
    cart_items = []
    total = 0
    for pid, qty in cart.items():
        product = next((p for p in products if p['id'] == pid), None)
        if product:
            subtotal = int(product['price']) * qty
            cart_items.append({
                'id': pid,
                'name': product['name'],
                'price': int(product['price']),
                'image': product['image'],
                'quantity': qty,
                'subtotal': subtotal
            })
            total += subtotal
    return render_template('confirm.html', cart_items=cart_items, total=total)

# ==== 購入完了ページ ====
@app.route('/thanks', methods=['POST'])
def thanks():
    cart = session.get('cart', {})
    session['cart'] = {}
    log_action("購入完了", page="完了ページ")
    return render_template('thanks.html')

# ==== 戻るボタンログ ====
@app.route('/back_to_index')
def back_to_index():
    log_action("商品一覧へ戻る", page="ボタン操作")
    return redirect(url_for('index'))

# ==== ポート指定して起動（Render向け） ====
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 1000))
    app.run(host='0.0.0.0', port=port)
