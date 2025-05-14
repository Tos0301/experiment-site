from flask import Flask, render_template, request, redirect, session
import csv

app = Flask(__name__)
app.secret_key = 'your-secret-key'

# 商品情報の読み込み
def load_products():
    with open('data/products.csv', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return [row for row in reader]

# トップページ（商品一覧）
@app.route('/')
def index():
    products = load_products()
    return render_template('index.html', products=products)

# 商品詳細ページ（group削除済）
@app.route('/product/<product_id>')
def product_detail(product_id):
    products = load_products()
    product = next((p for p in products if p['id'] == product_id), None)
    return render_template('product.html', product=product)

# カートに追加（POST）
@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    product_id = request.form['product_id']
    quantity = int(request.form['quantity'])

    if 'cart' not in session:
        session['cart'] = {}
    cart = session['cart']
    cart[product_id] = cart.get(product_id, 0) + quantity
    session['cart'] = cart

    return ('', 204)

# カートページ表示
@app.route('/cart')
def cart():
    products = load_products()
    cart = session.get('cart', {})
    cart_items = []
    total = 0

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

# カートの数量更新
@app.route('/update_cart', methods=['POST'])
def update_cart():
    cart = session.get('cart', {})
    for key, value in request.form.items():
        if key.startswith('quantity_'):
            product_id = key.replace('quantity_', '')
            cart[product_id] = int(value)
    session['cart'] = cart
    return redirect('/cart')

# 確認画面
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
    return render_template('confirm.html', cart_items=cart_items, total=total)

# 購入完了
@app.route('/checkout', methods=['POST'])
def checkout():
    session.pop('cart', None)
    return render_template('thanks.html')

# ✅ Render用：ポートとホストの明示的設定
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

