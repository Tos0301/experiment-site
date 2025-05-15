from flask import Flask, render_template, request, redirect, url_for, session
import csv
import os
import io
import base64
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)
app.secret_key = 'your-secret-key'

# ==== Google Sheets 連携設定 ====
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SPREADSHEET_NAME = 'ExperimentLogs'

encoded_credentials = os.environ.get("GOOGLE_CREDENTIALS_BASE64")
if encoded_credentials:
    decoded = base64.b64decode(encoded_credentials).decode('utf-8')
    credentials_json = io.StringIO(decoded)
    creds = Credentials.from_service_account_info(eval(credentials_json.read()), scopes=SCOPES)
    client = gspread.authorize(creds)
    SHEET = client.open(SPREADSHEET_NAME).sheet1
else:
    SHEET = None  # デプロイエラー回避のため

# ==== ログ記録関数 ====
def log_action(action, product_id="", quantity="", page=""):
    if SHEET:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        SHEET.append_row([timestamp, action, product_id, quantity, page])

# ==== CSV読込 ====
def load_products():
    with open('data/products.csv', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return list(reader)

# ==== 商品一覧 ====
@app.route('/')
def index():
    products = load_products()
    log_action("アクセス", page="商品一覧")
    return render_template('index.html', products=products)

# ==== 商品詳細 ====
@app.route('/product/<product_id>')
def product_detail(product_id):
    products = load_products()
    product = next((p for p in products if p['id'] == product_id), None)
    if not product:
        return "商品が見つかりません", 404
    log_action("アクセス", product_id=product_id, page="商品詳細")
    return render_template('product.html', product=product)

# ==== カートに追加 ====
@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    product_id = request.form['product_id']
    quantity = int(request.form['quantity'])

    cart = session.get('cart', {})
    cart[product_id] = cart.get(product_id, 0) + quantity
    session['cart'] = cart

    log_action("カート追加", product_id=product_id, quantity=quantity, page="カート")

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
            cart_items.append({'product': product, 'quantity': qty, 'subtotal': subtotal})
            total += subtotal

    log_action("アクセス", page="カート")
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

# ==== カート → 確認画面 ====
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
            cart_items.append({'product': product, 'quantity': qty, 'subtotal': subtotal})
            total += subtotal

    log_action("アクセス", page="確認画面")
    return render_template('confirm.html', cart_items=cart_items, total=total)

# ==== 購入完了 ====
@app.route('/thanks', methods=['POST'])
def thanks():
    cart = session.get('cart', {})
    session['cart'] = {}
    log_action("購入完了", page="完了ページ")
    return render_template('thanks.html')

# ==== 商品一覧に戻る（ログ用） ====
@app.route('/back_to_index')
def back_to_index():
    log_action("商品一覧に戻る", page="ボタン操作")
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
