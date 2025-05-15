from flask import Flask, render_template, request, redirect, session, url_for
import csv
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)
app.secret_key = 'your-secret-key'

# ✅ Google Sheets API 連携設定
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SERVICE_ACCOUNT_FILE = 'experimentlogging-90510cddec06.json'  # ← 必要に応じてファイル名変更
SPREADSHEET_NAME = 'ExperimentLogs'        # ← Sheetsの実名に合わせて変更

creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
client = gspread.authorize(creds)
SHEET = client.open(SPREADSHEET_NAME).sheet1

# ✅ ログ記録関数（Google Sheets に送信）
def log_action(action, product_id='', quantity='', page=''):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    SHEET.append_row([timestamp, action, product_id, quantity, page])

# ✅ 商品情報の読み込み
def load_products():
    with open('data/products.csv', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return [row for row in reader]

# ✅ 商品一覧ページ
@app.route('/')
def index():
    products = load_products()
    log_action('view_index', page='index')
    return render_template('index.html', products=products)

# ✅ 商品詳細ページ
@app.route('/product/<product_id>')
def product_detail(product_id):
    products = load_products()
    product = next((p for p in products if p['id'] == product_id), None)
    log_action('view_product', product_id=product_id, page='product')
    return render_template('product.html', product=product)

# ✅ カートに追加
@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    product_id = request.form['product_id']
    quantity = int(request.form['quantity'])

    log_action('add_to_cart', product_id, quantity, page='product')

    if 'cart' not in session:
        session['cart'] = {}
    cart = session['cart']
    cart[product_id] = cart.get(product_id, 0) + quantity
    session['cart'] = cart

    return ('', 204)

# ✅ カートページ
@app.route('/cart')
def cart():
    products = load_products()
    cart = session.get('cart', {})
    cart_items = []
    total = 0

    log_action('view_cart', page='cart')

    for p in products:
        pid = p['id']
        if pid in cart:
            quantity = cart[pid]
            subtotal = int(p['price']) * quantity
            total += subtotal
            cart_items.append({
                'id': pid,
                'name': p['name'],
                'price': int(p['price']),
                'image': p['image'],
                'quantity': quantity,
                'subtotal': subtotal
            })

    return render_template('cart.html', cart_items=cart_items, total=total)

# ✅ カート数量更新
@app.route('/update_cart', methods=['POST'])
def update_cart():
    cart = session.get('cart', {})
    for key, value in request.form.items():
        if key.startswith('quantity_'):
            product_id = key.replace('quantity_', '')
            cart[product_id] = int(value)
            log_action('update_quantity', product_id, value, page='cart')
    session['cart'] = cart
    return redirect('/cart')

# ✅ 確認画面
@app.route('/confirm')
def confirm():
    cart = session.get('cart', {})
    products = load_products()
    cart_items = []
    total = 0
    for p in products:
        if p['id'] in cart:
            quantity = cart[p['id']]
            subtotal = int(p['price']) * quantity
            total += subtotal
            cart_items.append({
                'name': p['name'],
                'quantity': quantity,
                'subtotal': subtotal
            })
    log_action('proceed_to_confirm', page='cart')
    return render_template('confirm.html', cart_items=cart_items, total=total)

# ✅ 購入完了
@app.route('/checkout', methods=['POST'])
def checkout():
    log_action('checkout_complete', page='confirm')
    session.pop('cart', None)
    return render_template('thanks.html')

# ✅ ローカル実行用
if __name__ == '__main__':
    app.run(debug=True)
