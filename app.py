from flask import Flask, render_template, request, redirect, url_for, session
from datetime import datetime
import csv
import os
import base64
import gspread
import pandas as pd  # 追加
from google.oauth2.service_account import Credentials

app = Flask(__name__)
app.secret_key = 'your-secret-key'

# ==== Google Sheets 認証設定（環境変数からjson生成） ====
SERVICE_ACCOUNT_FILE = 'credentials.json'
SPREADSHEET_NAME = 'ExperimentLogs'
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# base64から認証ファイル復元（Render環境用）
b64_content = os.getenv('GOOGLE_CREDENTIALS')
if b64_content:
    with open('credentials.json', 'wb') as f:
        f.write(base64.b64decode(b64_content))

creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
client = gspread.authorize(creds)
SHEET = client.open_by_key('1KNZ49or81ECH9EVXYeKjAv-ooSnXMbP3dC10e2gQR3g').sheet1

# ==== specs.csv 読み込み ====
specs_df = pd.read_csv('data/specs.csv')

# ==== ログ記録関数 ====
def log_action(action, product_id='', quantity='', page=''):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    participant_id = session.get('participant_id', 'unknown')
    SHEET.append_row([timestamp, participant_id, action, product_id, quantity, page])

# ==== ID入力ページ ====
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

# ==== 商品データ読み込み ====
def load_products():
    products = []
    with open('data/products.csv', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            products.append(row)
    return products

# ==== 商品一覧ページ ====
@app.route('/index')
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
    if quantity > 0:
        cart[product_id] = quantity
        log_action("数量更新", product_id=product_id, quantity=quantity, page="カート")
    else:
        cart.pop(product_id, None)
        log_action("商品削除", product_id=product_id, quantity=0, page="カート")
    session['cart'] = cart
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
    log_action("購入確認画面へ遷移", page="確認")
    return render_template('confirm.html', cart_items=cart_items, total=total)

# ==== 購入完了ページ ====
@app.route('/thanks', methods=['POST'])
def thanks():
    cart = session.get('cart', {})
    products = load_products()

    product_names = []
    quantities = []
    subtotals = []
    total = 0

    for pid, qty in cart.items():
        product = next((p for p in products if p['id'] == pid), None)
        if product:
            name = product['name']
            price = int(product['price'])
            subtotal = price * qty

            product_names.append(name)
            quantities.append(str(qty))
            subtotals.append(str(subtotal))
            total += subtotal

    # Google Sheets に購入情報を記録
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    participant_id = session.get('participant_id', 'unknown')
    SHEET.append_row([
        timestamp,
        participant_id,
        "購入完了",
        total,
        " / ".join(product_names),
        " / ".join(quantities),
        " / ".join(subtotals),
        "完了ページ"
    ])

    session['cart'] = {}
    return render_template('thanks.html')

# ==== 戻るボタンログ ====
@app.route('/back_to_index', methods=['GET', 'POST'])
def back_to_index():
    log_action("商品一覧へ戻る", page="ボタン操作")
    return redirect(url_for('index'))

# ==== カートに戻るボタンログ ====
@app.route('/back_to_cart', methods=['POST'])
def back_to_cart():
    log_action("カートに戻る", page="確認画面")
    return redirect(url_for('cart'))

# ==== コンテキストプロセッサ（バッジ表示用） ====
@app.context_processor
def inject_cart_count():
    cart = session.get('cart', {})
    count = sum(cart.values())
    return dict(cart_count=count)

# ==== ポート指定して起動（Render向け） ====
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 1000))
    app.run(host='0.0.0.0', port=port)

