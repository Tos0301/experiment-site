from flask import Flask, render_template, request, redirect, url_for, session
import csv, os
import pandas as pd
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import base64
import json

app = Flask(__name__)
app.secret_key = 'secret_key'

# Google Sheets連携設定
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
key_b64 = os.environ.get("GSHEET_SERVICE_KEY")
key_dict = json.loads(base64.b64decode(key_b64).decode("utf-8"))
credentials = ServiceAccountCredentials.from_json_keyfile_dict(key_dict, scope)
gc = gspread.authorize(credentials)
worksheet = gc.open_by_url("https://docs.google.com/spreadsheets/d/1KNZ49or81ECH9EVXYeKjAv-ooSnXMbP3dC10e2gQR3g/edit#gid=0").sheet1

def log_action(action, page="", total_price=0, products=None, quantities=None, subtotals=None):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    participant_id = session.get("participant_id", "")
    products = products or []
    quantities = quantities or []
    subtotals = subtotals or []
    worksheet.append_row([
        now, participant_id, action, total_price,
        ",".join(products), ",".join(map(str, quantities)), ",".join(map(str, subtotals)),
        page
    ])

def load_products():
    df = pd.read_csv("data/products.csv", dtype=str)
    return df.to_dict(orient="records")

@app.route('/')
def input_id():
    return render_template('input_id.html')

@app.route('/set_id', methods=['POST'])
def set_id():
    participant_id = request.form.get("participant_id")
    if participant_id:
        session["participant_id"] = participant_id
        log_action("ID入力", page="ID")
        return redirect(url_for("index"))
    return redirect(url_for("input_id"))

@app.route('/index', methods=['GET', 'POST'])
def index():
    products = load_products()
    cart_count = sum(session.get("cart", {}).values())
    if request.method == 'POST':
        log_action("商品一覧表示", page="一覧")
    return render_template('index.html', products=products, cart_count=cart_count)

@app.route('/product/<product_id>', methods=['GET', 'POST'])
def product_detail(product_id):
    products = load_products()
    product = next((p for p in products if p["id"] == product_id), None)
    cart_count = sum(session.get("cart", {}).values())
    if request.method == 'POST':
        log_action(f"商品詳細表示: {product_id}", page="詳細")
    return render_template('product.html', product=product, cart_count=cart_count)

@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    product_id = request.form["product_id"]
    quantity = int(request.form["quantity"])
    cart = session.get("cart", {})
    cart[product_id] = cart.get(product_id, 0) + quantity
    session["cart"] = cart
    log_action("カートに追加", page="詳細")
    return redirect(url_for("cart"))

@app.route('/cart', methods=['GET', 'POST'])
def cart():
    products = load_products()
    cart = session.get("cart", {})
    cart_items = []
    total = 0
    for product_id, quantity in cart.items():
        product = next((p for p in products if p["id"] == product_id), None)
        if product:
            subtotal = int(product["price"]) * quantity
            total += subtotal
            cart_items.append({
                "product": product,
                "quantity": quantity,
                "subtotal": subtotal
            })
    cart_count = sum(cart.values())
    if request.method == 'POST':
        log_action("カート表示", page="カート", total_price=total,
                   products=[item["product"]["name"] for item in cart_items],
                   quantities=[item["quantity"] for item in cart_items],
                   subtotals=[item["subtotal"] for item in cart_items])
    return render_template('cart.html', cart_items=cart_items, total=total, cart_count=cart_count)

@app.route('/update_cart', methods=['POST'])
def update_cart():
    cart = {}
    for key in request.form:
        if key.startswith("quantity_"):
            product_id = key.split("_")[1]
            quantity = int(request.form[key])
            if quantity > 0:
                cart[product_id] = quantity
    session["cart"] = cart
    log_action("カート更新", page="カート")
    return redirect(url_for('cart'))

@app.route('/go_confirm', methods=['POST'])
def go_confirm():
    log_action("確認画面へ進む", page="カート")
    return redirect(url_for('confirm'))

@app.route('/back_to_index', methods=['POST'])
def go_index():
    return redirect(url_for('index'))

@app.route('/back_to_cart', methods=['POST'])
def back_to_cart():
    log_action("カートに戻る", page="確認")
    return redirect(url_for('cart'))

@app.route('/confirm', methods=['GET', 'POST'])
def confirm():
    cart = session.get("cart", {})
    products = load_products()
    cart_items = []
    total = 0
    for product_id, quantity in cart.items():
        product = next((p for p in products if p["id"] == product_id), None)
        if product:
            subtotal = int(product["price"]) * quantity
            total += subtotal
            cart_items.append({
                "product": product,
                "quantity": quantity,
                "subtotal": subtotal
            })
    cart_count = sum(cart.values())
    if request.method == 'POST':
        log_action("購入確認画面表示", page="確認", total_price=total,
                   products=[item["product"]["name"] for item in cart_items],
                   quantities=[item["quantity"] for item in cart_items],
                   subtotals=[item["subtotal"] for item in cart_items])
    return render_template("confirm.html", cart_items=cart_items, total=total, cart_count=cart_count)

@app.route('/thanks', methods=['POST'])
def thanks():
    log_action("購入完了", page="完了")
    session["cart"] = {}
    return render_template('thanks.html', cart_count=0)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
