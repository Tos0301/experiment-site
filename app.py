from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from urllib.parse import urlencode
import csv, os
import pandas as pd
import datetime
import gspread
from google.oauth2.service_account import Credentials
import base64
import json
import random
import re
import unicodedata
import time

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "12characterPSKey")
GOOGLE_FORM_BASE_URL = os.getenv("GOOGLE_FORM_BASE_URL", "")  # 例: https://docs.google.com/forms/d/e/.../viewform
DEST_ROUTE_AFTER_FORM = os.getenv("DEST_ROUTE_AFTER_FORM", "finish")  # 回答後に進めたいルート名
COUNTERPART_BASE_URL = os.getenv("COUNTERPART_BASE_URL", "https://control-site.onrender.com")
FORM1_CODE = os.getenv("FORM1_CODE", "F1_SECRET_CODE")
FORM2_CODE = os.getenv("FORM2_CODE", "F2_SECRET_CODE")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "12characterPSKey")

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

ID_PATTERN = re.compile(r"^[A-Za-z0-9\-_.]{12}$")

PROTECTED_ENDPOINTS = {
    "index", "product_detail", "go_product", "go_cart",
    "add_to_cart", "cart", "update_cart", "go_confirm",
    "confirm", "complete", "thanks", "form_embed",
    "back_to_index", "back_to_cart", "cart_count"
}

form_status = {}

def mark_form_done(pid: str, form_id: str):
    rec = form_status.setdefault(pid, {"form1": False, "form2": False})
    if form_id in ("form1", "form2"):
        rec[form_id] = True

def is_form_done(pid: str, form_id: str) -> bool:
    return bool(form_status.get(pid, {}).get(form_id))


def is_form_submitted(pid: str) -> bool:
    """互換用: どちらか1つでも完了していればTrue"""
    rec = form_status.get(pid, {})
    return rec.get("form1", False) or rec.get("form2", False)

def normalize_id(s: str) -> str:
    if not s:
        return ""
    # 前後空白除去 & 全角→半角（英数・記号）
    s = unicodedata.normalize("NFKC", s.strip())
    return s

def log_action(action, page="", total_price=0, products=None, quantities=None, subtotals=None, colors=None, sizes=None):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    participant_id = session.get("participant_id", "")
    condition = session.get("condition", "")
    products = products or []
    quantities = quantities or []
    subtotals = subtotals or []
    colors = colors or []
    sizes = sizes or []
    
    worksheet.append_row([
        now, participant_id, condition, action, total_price,
        ",".join(products),
        ",".join(map(str, quantities)),
        ",".join(map(str, subtotals)),
        ",".join(colors),
        ",".join(sizes),
        page
    ])

def load_products():
    df = pd.read_csv("data/products.csv", dtype=str).fillna("")  # 欠損を空文字で埋める
    products = df.to_dict(orient="records")
    
    for product in products:
        product['colors'] = product['colors'].split('|') if product['colors'] else []
        product['sizes'] = product['sizes'].split('|') if product['sizes'] else []
    
    return products


def load_specs():
    specs = {}
    with open("data/specs.csv", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # IDをゼロ埋めして確実に一致させる
            product_id = row["id"].strip().zfill(3)
            specs[product_id] = row["specs"]
    return specs

@app.route('/reset_session')
def reset_session():
    session.clear()
    return "セッションを初期化しました"

@app.route('/', methods=['GET', 'POST'])
def start():
    from_previous = request.args.get('from_previous', '0')  # ← typo修正済み
    session["from_previous"] = from_previous

    if from_previous == '1':
        session["participant_id"] = request.args.get('participant_id', '')
        session["condition"] = request.args.get('condition', '')  # ← ここも修正

    if from_previous == '1' and session.get("participant_id") and session.get("condition"):
        log_action("前サイトからのスキップ", page="start")
        return redirect(url_for("confirm_id"))

    if request.method == 'POST':
        log_action("実験開始", page="start")
        return redirect(url_for("input_id"))
    
    return render_template("start.html", from_previous=from_previous)



@app.route('/input_id')
def input_id():
    return render_template('input_id.html')


#@app.route('/set_id', methods=['POST'])
#def set_participant_id():
#    prefix = request.form.get("prefix", "").upper()
#    birthdate = request.form.get("birthdate", "")
#    suffix = request.form.get("suffix", "")
    
    # if not (prefix and birthdate and suffix):
    #     return redirect(url_for("input_id"))

    # participant_id = f"{prefix}{birthdate}{suffix}"
    # session["participant_id"] = participant_id

    # # 任意：ログを記録
    # log_action("ID入力", page="ID")  # log_action関数があれば

    # return redirect(url_for("confirm_id"))

@app.before_request
def require_participant_id():
    # ID入力や開始画面、静的ファイルは除外
    if request.endpoint in { "start", "input_id", "set_participant_id", "reset_session", "static", "confirm_id", "notify_form_submit", "form_status_api" }:
        return
    # 前サイトスキップ経路（start→confirm_id）も考慮して、confirm_idまでは許容
    if request.endpoint in PROTECTED_ENDPOINTS and not session.get("participant_id"):
        return redirect(url_for("input_id"))
    
@app.route('/set_id', methods=['POST'])
def set_participant_id():
    raw = request.form.get("participant_id", "")
    participant_id = normalize_id(raw)

    # 空欄チェック
    if not participant_id:
        # 必要に応じて flash メッセージを出すならここで
        return redirect(url_for("input_id"))

    # 形式チェック（必要なければ外してOK）
    if not ID_PATTERN.fullmatch(participant_id):
        flash("参加者IDの文字数または形式が正しくありません。（12文字・半角英数字のみ使用可能です）", "danger")
        return redirect(url_for("input_id"))

    session["participant_id"] = participant_id

    # ログ（従来どおり）
    log_action("ID入力", page="ID")

    return redirect(url_for("confirm_id"))


@app.route('/confirm_id', methods=['GET', 'POST'])
def confirm_id():
    participant_id = session.get("participant_id", "")
    condition = request.args.get("condition", "")
    if participant_id and condition:
        session["participant_id"] = participant_id
        session["condition"] = condition
   
    if not participant_id:
        return redirect(url_for("input_id"))
    
    return render_template("confirm_id.html", participant_id=participant_id)



@app.route('/index', methods=['GET', 'POST'])
def index():
    if 'condition' not in session:
        session['condition'] = random.choice(['control', 'experiment'])
        log_action("条件決定", page="index")    
        print(f"🎯 Assigned new condition: {session['condition']}")

    print(f"🧭 Current session condition: {session['condition']}")

    products = load_products()

    for product in products:
        image = product["image"]
        colors = product.get("colors", [])

        if image.endswith(".jpg"):
            base_prefix = image[:-4]  # ".jpg" を除去
        else:
            base_prefix = image

        # カラーがあればランダムなカラーバリエーション画像を指定
        if colors:
            selected_color = random.choice(colors)
            product["random_color_image"] = f"{base_prefix}_{selected_color}_1.jpg"
        else:
            product["random_color_image"] = image

    cart = session.get("cart", [])
    cart_count = sum(item['quantity'] for item in cart if isinstance(item, dict) and 'quantity' in item)

    if request.method == 'POST':
        log_action("商品一覧表示", page="一覧", products=[], quantities=[], subtotals=[])

    if session["condition"] == "control":
        return render_template('control_index.html', products=products, cart_count=cart_count)
    else:
        return render_template('index.html', products=products, cart_count=cart_count)


@app.route('/product/<product_id>', methods=['GET', 'POST'])
def product_detail(product_id):
    products = load_products()
    product = next((p for p in products if p["id"] == product_id), None)
    if not product:
        return "商品が見つかりませんでした", 404
    
    specs_data = load_specs()
    cart = session.get("cart", [])
    cart_count = sum(item['quantity'] for item in cart if isinstance(item, dict) and 'quantity' in item)

    base_prefix = "noimage"
    image_list = []

    if product and product.get("image"):
        base_prefix = product["image"].rsplit(".", 1)[0]  # 例: towel_b
        color_list = product.get("colors", [])
        default_color = color_list[0] if color_list else ""

        # 1枚目：カラーバリエーション画像（towel_b_sand-beige_1.jpg）
        first_image = f"{base_prefix}_{default_color}_1.jpg"
        image_folder = os.path.join("static", "images")
        if os.path.exists(os.path.join(image_folder, first_image)):
            image_list.append(first_image)

        # 2枚目以降：共通画像（towel_b_2.jpg, towel_b_3.jpg, ...）
        for i in range(2, 6):  # 2〜5枚目まで
            filename = f"{base_prefix}_{i}.jpg"
            if os.path.exists(os.path.join(image_folder, filename)):
                image_list.append(filename)

    if request.method == 'POST':
        log_action(f"商品詳細表示: {product_id}", page="詳細")

    template_name = 'control_product.html' if session.get("condition") == 'control' else 'product.html' 

    return render_template(
        template_name,
        product=product,
        cart_count=cart_count,
        specs=specs_data.get(product_id, "(商品説明がありません)"),
        image_list=image_list,
        base_prefix=base_prefix,  # JSに渡す
        image_source=product.get("image_source", "")  # ← 追加

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

    cart = session.get("cart", [])

    # 新しく追加するアイテム
    new_item = {
        "product_id": product_id,
        "quantity": quantity,
        "color": request.form.get("color", ""),
        "size": request.form.get("size", "")
    }

    # 同じ商品・色・サイズの組み合わせがあれば統合
    found = False
    for item in cart:
        if isinstance(item, dict) and \
            item.get("product_id") == new_item["product_id"] and \
            item.get("color") == new_item["color"] and \
            item.get("size") == new_item["size"]:
            item["quantity"] += quantity
            found = True
            break


    if not found:
        cart.append(new_item)

    session["cart"] = [item for item in cart if isinstance(item, dict) and 'product_id' in item]



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
        cart_count = sum(item['quantity'] for item in cart if isinstance(item, dict) and 'quantity' in item)
        return jsonify({"cart_count": cart_count})

    # ✅ 通常遷移のときはリダイレクト（使っていないなら return "", 204 のままでもOK）
    return "", 204



@app.route('/cart', methods=['GET', 'POST'])
def cart():
    products = load_products()
    cart = session.get("cart", [])
    cart_items = []
    total = 0

    for item in cart:
        if not isinstance(item, dict):
            continue

        product = next((p for p in products if p["id"] == item["product_id"]), None)
        if product:
            subtotal = int(product["price"]) * item["quantity"]
            total += subtotal

            # ✅ color に基づく画像ファイル名を構築
            color = item.get("color", "").strip().lower()
            image_base = product["image"].rsplit(".", 1)[0]  # "mag_c" を取得
            
            if color:
                filename = f"{image_base}_{color}_1.jpg"
            else:
                filename = f"{image_base}_1.jpg"
            image_path = f"images/{image_base}_{color}_1.jpg"

            cart_items.append({
                "product": product,
                "quantity": item["quantity"],
                "subtotal": subtotal,
                "color": color,
                "size": item.get("size", ""),
                "image_path": image_path  # ✅ ここが cart.html で参照される
            })

    
    cart_count = sum(item['quantity'] for item in cart if isinstance(item, dict) and 'quantity' in item)
    
    if request.method == 'POST':
        log_action("カート表示", page="カート", total_price=total,
                   products=[item["product"]["name"] for item in cart_items],
                   quantities=[item["quantity"] for item in cart_items],
                   subtotals=[item["subtotal"] for item in cart_items])
    
    template_name = 'control_cart.html' if session.get("condition") == 'control' else 'cart.html'

    return render_template(
        template_name, 
        cart_items=cart_items, 
        total=total, 
        cart_count=cart_count,
    )

@app.route('/back_to_index', methods=['POST'])
def back_to_index():
    log_action("商品一覧に戻る", page="カート")
    return redirect(url_for('index'))


@app.route('/update_cart', methods=['POST'])
def update_cart():
    product_id = request.form.get("product_id")
    color = request.form.get("color", "")
    size = request.form.get("size", "")
    try:
        quantity = int(request.form.get("quantity", 1))
    except (ValueError, TypeError):
        quantity = 1  # 万が一無効な値が来たら1に戻す

    cart = session.get("cart", [])
    new_cart = []
    for item in cart:
        
        if not isinstance(item, dict):
            continue  # 不正なデータはスキップ

        if item["product_id"] == product_id and item["color"] == color and item["size"] == size:
            if quantity > 0:
                item["quantity"] = quantity
                new_cart.append(item)

        else:
            new_cart.append(item)  # 存在しない場合でもエラーにしない

    session["cart"] = new_cart
    log_action(f"数量更新: {product_id} → {quantity}", page="カート")
    return redirect(url_for("cart"))

@app.route('/cart_count', methods=['GET'])
def cart_count():
    cart = session.get("cart", [])
    count = sum(item['quantity'] for item in cart if isinstance(item, dict) and 'quantity' in item)
    return jsonify({'count': count})




@app.route('/go_confirm', methods=['POST'])
def go_confirm():
    log_action("確認画面へ進む", page="カート")
    return redirect(url_for('confirm'))

#@app.route('/back_to_index', methods=['POST'])
#def go_index():
    #return redirect(url_for('index'))

@app.route('/back_to_cart', methods=['POST'])
def back_to_cart():
    log_action("カートに戻る", page="確認")
    return redirect(url_for('cart'))

@app.route('/confirm', methods=['GET'])
def confirm():
    cart = session.get("cart", [])
    products = load_products()

    cart_items = []
    total = 0
    cart_count = 0

    for item in cart:
        if not isinstance(item, dict):
            continue  # 不正なデータはスキップ

        product_id = item['product_id']
        quantity = item['quantity']
        product = next((p for p in products if p["id"] == product_id), None)

        if product:
            subtotal = int(product["price"]) * quantity
            cart_items.append({
                "product": product,
                "quantity": quantity,
                "subtotal": subtotal,
                "color": item.get("color", ""),
                "size": item.get("size", "")
            })
            total += subtotal
            cart_count += quantity

    log_action("購入確認画面表示", page="確認")

    template_name = 'control_confirm.html' if session.get("condition") == 'control' else 'confirm.html'

    return render_template(template_name, cart_items=cart_items, cart_count=cart_count, total=total)


@app.route('/complete', methods=['POST'])
def complete():
    
    cart = session.get("cart", [])
    products = load_products()

    product_names = []
    quantities = []
    subtotals = []

    total_price = 0

    for item in cart:
        if not isinstance(item, dict):
            continue  # 不正なデータはスキップ
        
        product_id = item['product_id']
        quantity = item['quantity']
        product = next((p for p in products if p["id"] == product_id), None)

        if product:
            name = product["name"]
            price = int(product["price"])
            subtotal = price * quantity

            product_names.append(name)
            quantities.append(quantity)
            subtotals.append(subtotal)
            total_price += subtotal

    colors = [item.get("color", "") for item in cart]
    sizes = [item.get("size", "") for item in cart]

    log_action("購入確定", total_price=total_price,
            products=product_names,
            quantities=quantities,
            subtotals=subtotals,
            colors=colors,
            sizes=sizes,
            page="確認")


    session["cart"] = []  # ✅ カートを空にするのはログ記録のあと

    return redirect(url_for("thanks"))



@app.route('/thanks', methods=['GET', 'POST'])
def thanks():
    condition = session.get('condition', 'experiment')
    template_name = 'control_thanks.html'  if condition == 'control' else 'thanks.html'
    log_action("購入完了", page="完了")
    return render_template(template_name, cart_count=0)


@app.route('/form_embed')
def form_embed():
    participant_id = session.get("participant_id", "")
    from_previous  = request.args.get("from_previous", session.get("from_previous", "0"))
    # 入場順で期待フォームを決める（常に F1 → F2 の順）
    expect_form = "form2" if from_previous == "1" else "form1"

    log_action('Googleフォーム埋め込み表示', page=f'/form_embed:{expect_form}')
    return render_template(
        'googleform.html',
        participant_id=participant_id,
        from_previous=from_previous,
        expect_form=expect_form,   # ★ これをテンプレに渡す
        # 既存：
        google_form_url=GOOGLE_FORM_BASE_URL,
    )


@app.post("/notify_form_submit")
def notify_form_submit():
    # Secret
    if request.headers.get("X-Webhook-Secret") != WEBHOOK_SECRET:
        return "forbidden", 403

    # 受領
    pid    = request.form.get("pid")
    form_id= request.form.get("form_id")    # "form1" or "form2"
    code   = request.form.get("code")       # フォーム別の完了コード

    if not pid or not form_id or not code:
        data = request.get_json(silent=True) or {}
        pid     = pid     or data.get("pid")
        form_id = form_id or data.get("form_id")
        code    = code    or data.get("code")

    if not pid or not form_id or not code:
        return "bad request", 400

    # コード検証（フォーム別）
    expected = FORM1_CODE if form_id == "form1" else FORM2_CODE if form_id == "form2" else None
    if expected is None or code != expected:
        return "ignored: bad form_id or code", 202

    # 正しい完了 ⇒ 該当フォームだけ完了扱い
    mark_form_done(pid, form_id)
    return "ok", 200


@app.get("/form_status/<pid>")
def form_status_api(pid):
    expect = request.args.get("expect")  # "form1" または "form2"
    if expect in ("form1", "form2"):
        return jsonify({"done": is_form_done(pid, expect)})
    # 後方互換：未指定なら“どちらか片方でも完了”を返す（使わない運用推奨）
    done_any = is_form_done(pid, "form1") or is_form_done(pid, "form2")
    return jsonify({"done": done_any})


@app.get("/guard_to_next")
def guard_to_next():
    """
    提出済みか最終確認 → 行き先を分岐
      - まだ相手サイトに入っていない（from_previous != "1"）: 相手サイトに必要情報を付けてリダイレクト
      - すでに相手サイトから来ている（from_previous == "1"）: ローカルの finish へ
    """
    # 1) 提出済みチェック
    pid = session.get("participant_id") or request.args.get("pid")
    if not pid:
        return "no participant_id", 400
    if not is_form_submitted(pid):
        return "form not submitted", 403

    # 2) どちらから来たか（このサイトが1サイト目か2サイト目か）
    from_previous = session.get("from_previous", "0")

    # 3) 2サイト目（前サイトから渡ってきた後）ならローカルの次ステップへ
    if from_previous == "1":
        # 例: finish
        return redirect(url_for(DEST_ROUTE_AFTER_FORM))

    # 4) まだ 1サイト目：相手サイトに ID/条件/フラグ を付けて送る
    if COUNTERPART_BASE_URL:
        qs = urlencode({
            "from_previous": "1",
            "participant_id": session.get("participant_id", ""),
            "condition": session.get("condition", "")
        })
        # トップ（/）に流し、相手サイトの start() がパラメータをセッションへ入れる想定
        target_url = COUNTERPART_BASE_URL.rstrip("/") + "/?" + qs
        # 任意: デバッグログ
        print(f"[GUARD] redirect to counterpart: {target_url}")
        return redirect(target_url)

    # 5) 相手サイトURLが未設定ならフォールバック（ローカルの finish へ）
    return redirect(url_for(DEST_ROUTE_AFTER_FORM))
# ---- 追加ここまで ----


@app.route("/finish")
def finish():
    log_action("実験終了", page="finish")
    return render_template("finish.html")

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
