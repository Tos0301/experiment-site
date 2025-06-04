from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import csv, os
import pandas as pd
import datetime
import gspread
from google.oauth2.service_account import Credentials
import base64
import json

app = Flask(__name__)
app.secret_key = 'secret_key'

scopes = ['https://www.googleapis.com/auth/spreadsheets']
service_account_path = 'encoded.txt'  # base64でエンコードされたサービスアカウントキー
spreadsheet_id = '1KNZ49or81ECH9EVXYeKjAv-ooSnXMbP3dC10e2gQR3g'

with open(service_account_path, 'r') as f:
    encoded = f.read()
decoded_json = base64.b64decode(encoded).decode('utf-8')
service_info = json.loads(decoded_json)

credentials = Credentials.from_service_account_info(service_info, scopes=scopes)
gc = gspread.authorize(credentials)
worksheet = gc.open_by_key(spreadsheet_id).sheet1

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

def load_specs():
    specs = {}
    with open("data/specs.csv", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # IDをゼロ埋めして確実に一致させる
            product_id = row["id"].strip().zfill(3)
            specs[product_id] = row["specs"]
    return specs


@app.route('/')
def input_id():
    return render_template('input_id.html')

@app.route('/set_id', methods=['POST'])
def set_participant_id():
    prefix = request.form.get("prefix", "").upper()
    birthdate = request.form.get("birthdate", "")
    suffix = request.form.get("suffix", "")
    
    if not (prefix and birthdate and suffix):
        return redirect(url_for("input_id"))

    participant_id = f"{prefix}{birthdate}{suffix}"
    session["participant_id"] = participant_id

    # 任意：ログを記録
    log_action("ID入力", page="ID")  # log_action関数があれば

    return redirect(url_for("confirm_id"))

@app.route('/confirm_id', methods=['GET', 'POST'])
def confirm_id():
    participant_id = session.get("participant_id", "")
    if not participant_id:
        return redirect(url_for("input_id"))
    return render_template("confirm_id.html", participant_id=participant_id)

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
    specs_data = load_specs()
    cart_count = sum(session.get("cart", {}).values())

    image_list = []
    if product and "image" in product:
        image_prefix = product["image"].rsplit(".", 1)[0]  # mug01
        image_folder = os.path.join("static", "images")
        image_list = []
        for i in range(1, 6):  # 最大5枚程度
            filename = f"{image_prefix}_{i}.jpg"
            path = os.path.join(image_folder, filename)
            if os.path.exists(path):
                image_list.append(filename)

    if request.method == 'POST':
        log_action(f"商品詳細表示: {product_id}", page="詳細")
    
    return render_template(
        'product.html',
        product=product,
        cart_count=cart_count,
        specs=specs_data.get(product_id, "(商品説明がありません)"),
        image_list=image_list
    )


@app.route('/go_product', methods=['POST'])
def go_product():
    product_id = request.form.get("product_id")
    return redirect(url_for('product_detail', product_id=product_id))

@app.route('/go_cart', methods=['POST'])
def go_cart():
    log_action("カートを見る", page="詳細")
    return redirect(url_for('cart'))


@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    product_id = request.form["product_id"]
    quantity = int(request.form["quantity"])

    products = load_products()
    product = next((p for p in products if p["id"] == product_id), None)

    cart = session.get("cart", {})
    cart[product_id] = cart.get(product_id, 0) + quantity
    session["cart"] = cart

    if product:
        name = product["name"]
        price = int(product["price"])
        subtotal = price * quantity

        log_action("カートに追加", total_price=subtotal,
                   products=[name], quantities=[quantity], subtotals=[subtotal], page="詳細")
    else:
        log_action("カートに追加", page="詳細")

    # ✅ 非同期(fetch)リクエストの場合はJSONで返す
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        cart_count = sum(cart.values())
        return jsonify({"cart_count": cart_count})

    # ✅ 通常遷移のときはリダイレクト（使っていないなら return "", 204 のままでもOK）
    return "", 204



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

@app.route('/back_to_index', methods=['POST'])
def back_to_index():
    log_action("商品一覧に戻る", page="カート")
    return redirect(url_for('index'))


@app.route('/update_cart', methods=['POST'])
def update_cart():
    product_id = request.form.get("product_id")
    try:
        quantity = int(request.form.get("quantity", 1))
    except (ValueError, TypeError):
        quantity = 1  # 万が一無効な値が来たら1に戻す

    cart = session.get("cart", {})

    if quantity > 0:
        cart[product_id] = quantity
    else:
        cart.pop(product_id, None)  # 存在しない場合でもエラーにしない

    session["cart"] = cart
    log_action(f"数量更新: {product_id} → {quantity}", page="カート")
    return redirect(url_for("cart"))

@app.route('/cart_count', methods=['GET'])
def cart_count():
    cart = session.get("cart", {})
    count = sum(cart.values())
    return jsonify({'count': count})



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

@app.route('/confirm', methods=['GET'])
def confirm():
    cart = session.get("cart", {})
    products = load_products()

    cart_items = []
    total = 0
    cart_count = 0

    for product_id, quantity in cart.items():
        product = next((p for p in products if p["id"] == product_id), None)
        if product:
            subtotal = int(product["price"]) * quantity
            cart_items.append({
                "product": product,  # ← ここが重要
                "quantity": quantity,
                "subtotal": subtotal
            })
            total += subtotal
            cart_count += quantity

    log_action("購入確認画面表示", page="確認")
    return render_template("confirm.html", cart_items=cart_items, cart_count=cart_count, total=total)


@app.route('/complete', methods=['POST'])
def complete():
    cart = session.get("cart", {})
    products = load_products()

    product_names = []
    quantities = []
    subtotals = []

    total_price = 0

    for product_id, quantity in cart.items():
        product = next((p for p in products if p["id"] == product_id), None)
        if product:
            name = product["name"]
            price = int(product["price"])
            subtotal = price * quantity

            product_names.append(name)
            quantities.append(quantity)
            subtotals.append(subtotal)
            total_price += subtotal

    log_action("購入確定", total_price=total_price,
               products=product_names, quantities=quantities, subtotals=subtotals, page="確認")

    session["cart"] = {}  # ✅ カートを空にするのはログ記録のあと

    return redirect(url_for("thanks"))



@app.route('/thanks', methods=['GET', 'POST'])
def thanks():
    log_action("購入完了", page="完了")
    return render_template('thanks.html', cart_count=0)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
