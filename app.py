from flask import Flask, render_template, request, redirect, url_for, session
from datetime import datetime
import csv
import os
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)
app.secret_key = 'your-secret-key'

# ==== Google Sheets API連携 ====
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SERVICE_ACCOUNT_FILE = 'experimentlogging-90510cddec06.json'
SPREADSHEET_NAME = 'ExperimentLogs'

creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
client = gspread.authorize(creds)
SHEET = client.open(SPREADSHEET_NAME).sheet1

# ==== 商品データの読み込み ====
import csv
PRODUCTS_CSV_PATH = 'data/products.csv'

def load_products():
    with open(PRODUCTS_CSV_PATH, newline='', encoding='utf-8') as csvfile:
        return list(csv.DictReader(csvfile))

# ==== 行動ログ関数 ====
def log_action(action, product_id='', quantity='', page=''):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    SHEET.append_row([timestamp, action, product_id, quantity, page])

# ==== 商品一覧ページ ====
@app.route('/')
def index():
    products = load_products()
    log_action("ページ訪問", page="商品一覧")
    return render_template('index.html', products=products)

# ==== 商品詳細ページ ====
@app.route('/product/<product_id>')
def product_detail(product_id):
    products = load_products()
    product = next((p for p in products if p['id'] == product_id), None)
    if not product:
        return redirect(url_for('index'))
    log_action("ページ訪問", product_id=product_id, page="商品詳細")
    return render_template('product.html', product=product)

# ==== カートに追加 ====
@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    product_id = request.form['product_id']
    quantity = int(request.form['quantity'])
    cart = session.get('cart', {})
    cart[product_id] = cart.get(product_id, 0) + quantity
    session['cart'] = cart
    log_action("カートに追加", product_id=product_id, quantity=quantity, page="商品詳細")
    return redirect(url_for('cart'))

# ==== カートページ ====
@app.route('/cart')
def cart():
    products = load_products()
    cart = session.get('cart', {})
    cart_items = []
    total = 0

    for product_id, quantity in cart.items():
        product = next((p for p in products if p['id'] == product_id), None)
        if product:
            product = product.copy()
            product['quantity'] = quantity
            product['subtotal'] = int(product['price']) * quantity
            cart_items.append(product)
            total += product['subtotal']

    log_action("ページ訪問", page="カート")
    return render_template('cart.html', cart_items=cart_items, total=total)

# ==== 数量更新処理 ====
@app.route('/update_quantity', methods=['POST'])
def update_quantity():
    product_id = request.form.get('product_id')
    quantity = int(request.form.get('quantity', 1))
    cart = session.get('cart', {})
    if product_id in cart:
        cart[product_id] = quantity
        session['cart'] = cart
    log_action("数量更新", product_id=product_id, quantity=quantity, page="カート")
    return redirect(url_for('cart'))

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

# ==== ポート指定と起動 ====
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 1000))
    app.run(host='0.0.0.0', port=port)
