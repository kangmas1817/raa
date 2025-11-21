import os
from flask import Flask, jsonify, request, redirect, url_for, session, flash, get_flashed_messages
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import json
import random
from functools import wraps
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from google_auth_oauthlib.flow import Flow
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
import time

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'kang-mas-secret-2025')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URI', 'sqlite:///kang_mas_new.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
app.config['UPLOAD_FOLDER'] = os.getenv('UPLOAD_FOLDER', 'static/uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Ensure upload folders exist
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'products'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'logos'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'assets'), exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ===== GOOGLE OAUTH CONFIG =====
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')

# Allowed file extensions for upload
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_product_image(file, product_name=None):
    """Save product image and return filename"""
    if file and allowed_file(file.filename):
        if product_name:
            safe_name = secure_filename(product_name)
            safe_name = safe_name.replace(' ', '_').lower()
            filename = f"{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{file.filename.rsplit('.', 1)[1].lower()}"
        else:
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
            filename = timestamp + filename
        
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'products', filename)
        file.save(filepath)
        return f'uploads/products/{filename}'
    return None

def save_logo(file):
    """Save logo and return filename"""
    if file and allowed_file(file.filename):
        filename = 'logo.png'
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'logos', filename)
        file.save(filepath)
        return f'uploads/logos/{filename}'
    return None

# ===== OAuth flow configuration =====
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

def get_google_flow():
    flow = Flow.from_client_config(
        client_config={
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [
                    "http://localhost:5000/google-callback",
                    "http://127.0.0.1:5000/google-callback"
                ]
            }
        },
        scopes=[
            "https://www.googleapis.com/auth/userinfo.profile",
            "https://www.googleapis.com/auth/userinfo.email",
            "openid"
        ]
    )
    return flow

# ===== GOLDEN OCEAN COLOR PALETTE =====
COLORS = {
    'primary': '#B55123',    # DARK MANGO - Gold/Orange tua sebagai primary
    'secondary': '#E47A24',  # APRICOT - Gold/Orange medium
    'accent': '#7A6B5E',     # PINEAPPLE - Brown Gold 
    'success': '#38a169',    # Kembali ke hijau untuk success (kontras lebih baik)
    'warning': '#d69e2e',    # Golden yellow untuk warning
    'error': '#BF2020',      # BLOOD ORANGE - Red
    'dark': '#2d3748',       
    'light': '#fef6eb',      # Light golden tint
    'white': '#ffffff',
    'teal': '#E47A24',       # APRICOT - Gold/Orange
    'navy': '#B55123',       # DARK MANGO - Gold tua
    'ocean-light': '#fef6eb', # Light golden cream
    'ocean-medium': '#E47A24', # APRICOT - Gold medium
    'ocean-deep': '#B55123',   # DARK MANGO - Gold tua
    'gold-light': '#fef6eb',
    'gold-medium': '#E47A24',
    'gold-deep': '#B55123',
    'gold-dark': '#7A6B5E'
}

# ===== DATABASE MODELS =====
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    full_name = db.Column(db.String(100), nullable=False)
    user_type = db.Column(db.String(20), nullable=False)
    phone = db.Column(db.String(20))
    address = db.Column(db.Text)
    avatar = db.Column(db.String(200), default='👤')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    google_id = db.Column(db.String(100), unique=True)
    email_verified = db.Column(db.Boolean, default=False)
    verification_code = db.Column(db.String(6))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_verification_code(self):
        self.verification_code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        return self.verification_code

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    cost_price = db.Column(db.Float, default=1000)
    stock = db.Column(db.Integer, nullable=False)
    size_cm = db.Column(db.Float)
    weight_kg = db.Column(db.Float)
    category = db.Column(db.String(50), default='ikan_mas')
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    is_featured = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    image_url = db.Column(db.String(500))

class CartItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(20), unique=True, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending')
    payment_method = db.Column(db.String(50))
    payment_status = db.Column(db.String(20), default='unpaid')
    shipping_address = db.Column(db.Text, nullable=False)
    shipping_method = db.Column(db.String(50))
    order_date = db.Column(db.DateTime, default=datetime.utcnow)
    completed_date = db.Column(db.DateTime)
    tracking_info = db.Column(db.Text)

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    cost_price = db.Column(db.Float)

class Account(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    category = db.Column(db.String(20), nullable=False)
    balance = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class JournalEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    transaction_number = db.Column(db.String(20), unique=True, nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    description = db.Column(db.Text, nullable=False)
    journal_type = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    journal_details = db.relationship('JournalDetail', backref='journal_entry', lazy=True)

class JournalDetail(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    journal_id = db.Column(db.Integer, db.ForeignKey('journal_entry.id'), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    debit = db.Column(db.Float, default=0)
    credit = db.Column(db.Float, default=0)
    description = db.Column(db.Text)
    account = db.relationship('Account', backref='journal_details')

class CashFlow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    type = db.Column(db.String(10), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AppSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ===== DATABASE MIGRATION =====
def reset_database_safe():
    """Safely reset database by creating new one"""
    try:
        # Drop all tables and create new ones
        db.drop_all()
        db.create_all()
        print("New database created successfully!")
        return True
    except Exception as e:
        print(f"Cannot reset database: {e}")
        print("Trying to continue with existing database...")
        return False

# ===== TEMPLATE TRANSAKSI OTOMATIS LENGKAP =====
TRANSACTION_TEMPLATES = {
    'saldo_awal': {
        'name': 'Saldo Awal Usaha',
        'description': 'Pencatatan saldo awal usaha Kang-Mas Shop',
        'entries': [
            {'account_type': 'kas', 'side': 'debit', 'description': 'Saldo awal kas'},
            {'account_type': 'persediaan', 'side': 'debit', 'description': 'Saldo awal persediaan barang dagang'},
            {'account_type': 'peralatan', 'side': 'debit', 'description': 'Saldo awal peralatan toko'},
            {'account_type': 'perlengkapan', 'side': 'debit', 'description': 'Saldo awal perlengkapan toko'},
            {'account_type': 'pendapatan', 'side': 'credit', 'description': 'Saldo awal penjualan'},
            {'account_type': 'hutang', 'side': 'credit', 'description': 'Saldo awal utang dagang'}
        ]
    },
    'setoran_modal': {
        'name': 'Setoran Modal Awal',
        'description': 'Kas diterima dari pemilik sebagai modal awal',
        'entries': [
            {'account_type': 'kas', 'side': 'debit', 'description': 'Setoran modal pemilik'},
            {'account_type': 'modal', 'side': 'credit', 'description': 'Modal pemilik'}
        ]
    },
    'pembelian_peralatan_kredit': {
        'name': 'Pembelian Peralatan Kredit',
        'description': 'Dibeli beberapa peralatan untuk budidaya ikan secara kredit',
        'entries': [
            {'account_type': 'peralatan', 'side': 'debit', 'description': 'Peralatan budidaya'},
            {'account_type': 'hutang', 'side': 'credit', 'description': 'Utang dagang'}
        ]
    },
    'pembelian_perlengkapan_tunai': {
        'name': 'Pembelian Perlengkapan Tunai',
        'description': 'Dibeli kebutuhan perlengkapan budidaya ikan mas secara tunai',
        'entries': [
            {'account_type': 'perlengkapan', 'side': 'debit', 'description': 'Perlengkapan budidaya'},
            {'account_type': 'kas', 'side': 'credit', 'description': 'Pembayaran tunai'}
        ]
    },
    'pembelian_bibit_campur': {
        'name': 'Pembelian Bibit Ikan Mas (Tunai + Kredit)',
        'description': 'Dibeli 2.000 ekor bibit ikan mas (1.500 tunai, 500 kredit)',
        'entries': [
            {'account_type': 'persediaan', 'side': 'debit', 'description': 'Bibit ikan mas 2000 ekor'},
            {'account_type': 'kas', 'side': 'credit', 'description': 'Pembayaran tunai 1500 ekor'},
            {'account_type': 'hutang', 'side': 'credit', 'description': 'Utang 500 ekor'}
        ]
    },
    'pelunasan_utang_peralatan': {
        'name': 'Pelunasan Utang Peralatan',
        'description': 'Membayar faktur pembelian dari Toko Abc',
        'entries': [
            {'account_type': 'hutang', 'side': 'debit', 'description': 'Pelunasan utang peralatan'},
            {'account_type': 'kas', 'side': 'credit', 'description': 'Pembayaran kas'}
        ]
    },
    'pelunasan_utang_bibit': {
        'name': 'Pelunasan Utang Pembelian Bibit',
        'description': 'Membayar faktur pembelian bibit dari pengepul',
        'entries': [
            {'account_type': 'hutang', 'side': 'debit', 'description': 'Pelunasan utang bibit'},
            {'account_type': 'kas', 'side': 'credit', 'description': 'Pembayaran kas'}
        ]
    },
    'pembelian_peralatan_tunai': {
        'name': 'Pembelian Peralatan Tunai',
        'description': 'Pembelian baskom, sortir, serokan secara tunai',
        'entries': [
            {'account_type': 'peralatan', 'side': 'debit', 'description': 'Peralatan tambahan'},
            {'account_type': 'kas', 'side': 'credit', 'description': 'Pembayaran tunai'}
        ]
    },
    'pembelian_obat_ikan': {
        'name': 'Pembelian Obat Ikan Tunai',
        'description': 'Pembelian obat pencegah penyakit ikan',
        'entries': [
            {'account_type': 'perlengkapan', 'side': 'debit', 'description': 'Obat ikan'},
            {'account_type': 'kas', 'side': 'credit', 'description': 'Pembayaran tunai'}
        ]
    },
    'biaya_listrik': {
        'name': 'Pembayaran Biaya Listrik',
        'description': 'Pembayaran biaya listrik bulanan',
        'entries': [
            {'account_type': 'beban_listrik', 'side': 'debit', 'description': 'Biaya listrik'},
            {'account_type': 'kas', 'side': 'credit', 'description': 'Pembayaran tunai'}
        ]
    },
    'penjualan_bibit_kredit': {
        'name': 'Penjualan Bibit Ikan Secara Kredit',
        'description': 'Penjualan bibit ikan secara kredit',
        'entries': [
            {'account_type': 'piutang', 'side': 'debit', 'description': 'Piutang penjualan'},
            {'account_type': 'pendapatan', 'side': 'credit', 'description': 'Pendapatan penjualan'}
        ]
    },
    'penerimaan_piutang': {
        'name': 'Penerimaan Kas dari Piutang',
        'description': 'Penerimaan pembayaran piutang dagang',
        'entries': [
            {'account_type': 'kas', 'side': 'debit', 'description': 'Penerimaan kas'},
            {'account_type': 'piutang', 'side': 'credit', 'description': 'Piutang dilunasi'}
        ]
    },
    'penjualan_ikan_tunai': {
        'name': 'Penjualan Ikan Mas Tunai',
        'description': 'Penjualan ikan mas konsumsi secara tunai',
        'entries': [
            {'account_type': 'kas', 'side': 'debit', 'description': 'Penerimaan penjualan'},
            {'account_type': 'pendapatan', 'side': 'credit', 'description': 'Pendapatan penjualan'}
        ]
    },
    'biaya_air': {
        'name': 'Pembayaran Biaya Air',
        'description': 'Pembayaran biaya air bulanan',
        'entries': [
            {'account_type': 'beban_listrik', 'side': 'debit', 'description': 'Biaya air'},
            {'account_type': 'kas', 'side': 'credit', 'description': 'Pembayaran tunai'}
        ]
    },
    'kerugian_ikan_mati': {
        'name': 'Kerugian Akibat Ikan Mati',
        'description': 'Kerugian akibat ikan mati tidak bisa dijual',
        'entries': [
            {'account_type': 'beban_kerugian', 'side': 'debit', 'description': 'Beban kerugian ikan mati'},
            {'account_type': 'persediaan', 'side': 'credit', 'description': 'Pengurangan persediaan'}
        ]
    },
    'biaya_reparasi': {
        'name': 'Biaya Reparasi Kendaraan',
        'description': 'Biaya reparasi kendaraan operasional',
        'entries': [
            {'account_type': 'beban_lain', 'side': 'debit', 'description': 'Biaya reparasi'},
            {'account_type': 'kas', 'side': 'credit', 'description': 'Pembayaran tunai'}
        ]
    },
    'penjualan_bibit_tunai': {
        'name': 'Penjualan Bibit Ikan Mas Tunai',
        'description': 'Penjualan bibit ikan mas secara tunai',
        'entries': [
            {'account_type': 'kas', 'side': 'debit', 'description': 'Penerimaan penjualan'},
            {'account_type': 'pendapatan', 'side': 'credit', 'description': 'Pendapatan penjualan'}
        ]
    },
    'penjualan_dengan_pengiriman': {
        'name': 'Penjualan + Beban Pengiriman',
        'description': 'Penjualan bibit dengan biaya pengiriman ditanggung penjual',
        'entries': [
            {'account_type': 'kas', 'side': 'debit', 'description': 'Penerimaan penjualan'},
            {'account_type': 'pendapatan', 'side': 'credit', 'description': 'Pendapatan penjualan'},
            {'account_type': 'beban_transport', 'side': 'debit', 'description': 'Biaya pengiriman'},
            {'account_type': 'kas', 'side': 'credit', 'description': 'Pembayaran biaya pengiriman'}
        ]
    },
    'pembelian_bibit_tunai': {
        'name': 'Pembelian Bibit Ikan Mas Tunai',
        'description': 'Pembelian bibit ikan mas tambahan secara tunai',
        'entries': [
            {'account_type': 'persediaan', 'side': 'debit', 'description': 'Bibit ikan tambahan'},
            {'account_type': 'kas', 'side': 'credit', 'description': 'Pembayaran tunai'}
        ]
    },
    'penjualan_ikan_ongkir': {
        'name': 'Penjualan Ikan + Ongkir Pembeli',
        'description': 'Penjualan ikan mas tunai dengan ongkir ditanggung pembeli',
        'entries': [
            {'account_type': 'kas', 'side': 'debit', 'description': 'Penerimaan penjualan termasuk ongkir'},
            {'account_type': 'pendapatan', 'side': 'credit', 'description': 'Pendapatan penjualan'}
        ]
    },
    'kerugian_hibah': {
        'name': 'Kerugian Hibah Bibit',
        'description': 'Kerugian akibat pemberian bibit ke saudara',
        'entries': [
            {'account_type': 'beban_kerugian', 'side': 'debit', 'description': 'Kerugian hibah bibit'},
            {'account_type': 'persediaan', 'side': 'credit', 'description': 'Pengurangan persediaan'}
        ]
    },
    'pembelian_perlengkapan_peralatan': {
        'name': 'Pembelian Perlengkapan & Peralatan',
        'description': 'Pembelian perlengkapan dan peralatan secara tunai',
        'entries': [
            {'account_type': 'perlengkapan', 'side': 'debit', 'description': 'Pembelian perlengkapan'},
            {'account_type': 'peralatan', 'side': 'debit', 'description': 'Pembelian peralatan'},
            {'account_type': 'kas', 'side': 'credit', 'description': 'Pembayaran tunai'}
        ]
    },
    'penyusutan_peralatan': {
        'name': 'Penyusutan Peralatan',
        'description': 'Penyusutan peralatan bulanan',
        'entries': [
            {'account_type': 'beban_penyusutan', 'side': 'debit', 'description': 'Beban penyusutan'},
            {'account_type': 'akumulasi_penyusutan', 'side': 'credit', 'description': 'Akumulasi penyusutan'}
        ]
    },
    'pemakaian_perlengkapan': {
        'name': 'Pemakaian Perlengkapan',
        'description': 'Pemakaian perlengkapan bulanan',
        'entries': [
            {'account_type': 'beban_perlengkapan', 'side': 'debit', 'description': 'Beban perlengkapan'},
            {'account_type': 'perlengkapan', 'side': 'credit', 'description': 'Pengurangan perlengkapan'}
        ]
    }
}

# ===== GOOGLE OAUTH ROUTES =====
@app.route('/google-login')
def google_login():
    flow = get_google_flow()
    flow.redirect_uri = url_for('google_callback', _external=True)
    
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='select_account'
    )
    
    session['state'] = state
    return redirect(authorization_url)

@app.route('/google-callback')
def google_callback():
    try:
        flow = get_google_flow()
        flow.redirect_uri = url_for('google_callback', _external=True)
        flow.fetch_token(authorization_response=request.url)
        
        credentials = flow.credentials
        id_info = id_token.verify_oauth2_token(
            credentials.id_token, 
            google_requests.Request(), 
            GOOGLE_CLIENT_ID
        )
        
        google_id = id_info.get('sub')
        email = id_info.get('email')
        name = id_info.get('name')
        
        user = User.query.filter_by(email=email).first()
        
        if not user:
            user = User(
                email=email,
                full_name=name,
                user_type='customer',
                google_id=google_id,
                email_verified=True,
                avatar='👤'
            )
            db.session.add(user)
            db.session.commit()
            flash('Akun berhasil dibuat dengan Google!', 'success')
        else:
            if not user.google_id:
                user.google_id = google_id
                db.session.commit()
        
        login_user(user)
        flash(f'Berhasil login dengan Google! Selamat datang {name}', 'success')
        return redirect('/')
        
    except Exception as e:
        print(f"Google OAuth error: {e}")
        flash('Error saat login dengan Google. Silakan coba lagi.', 'error')
        return redirect('/login')

# ===== EMAIL CONFIG =====
EMAIL_CONFIG = {
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587,
    'sender_email': 'kang.mas1817@gmail.com',
    'sender_password': 'TugasSiaKangMas'
}

def send_verification_email(email, verification_code):
    try:
        subject = "Kode Verifikasi Kang-Mas Shop"
        body = f"""
        Halo!
        
        Terima kasih telah mendaftar di Kang-Mas Shop.
        
        Kode verifikasi Anda adalah: {verification_code}
        
        Masukkan kode ini di halaman verifikasi untuk mengaktifkan akun Anda.
        
        Kode ini berlaku selama 10 menit.
        
        Salam,
        Tim Kang-Mas Shop
        """
        
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = EMAIL_CONFIG['sender_email']
        msg['To'] = email
        
        with smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port']) as server:
            server.starttls()
            server.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['sender_password'])
            server.send_message(msg)
        
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

# ===== DECORATORS =====
def seller_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Silakan login terlebih dahulu.', 'error')
            return redirect('/login')
        if current_user.user_type != 'seller':
            flash('Akses ditolak. Hanya untuk seller.', 'error')
            return redirect('/')
        return f(*args, **kwargs)
    return decorated_function

def customer_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Silakan login terlebih dahulu.', 'error')
            return redirect('/login')
        if current_user.user_type != 'customer':
            flash('Akses ditolak. Hanya untuk customer.', 'error')
            return redirect('/')
        return f(*args, **kwargs)
    return decorated_function

# ===== AKUNTANSI FUNCTIONS =====
def generate_unique_transaction_number(prefix='TRX'):
    """Generate unique transaction number dengan timestamp dan random number"""
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    random_num = random.randint(100, 999)
    return f"{prefix}{timestamp}{random_num}"

def create_journal_entry(transaction_number, date, description, journal_type, entries):
    try:
        # Cek apakah transaction number sudah ada
        existing_journal = JournalEntry.query.filter_by(transaction_number=transaction_number).first()
        if existing_journal:
            # Jika sudah ada, generate yang baru
            transaction_number = generate_unique_transaction_number()
        
        journal = JournalEntry(
            transaction_number=transaction_number,
            date=date,
            description=description,
            journal_type=journal_type
        )
        db.session.add(journal)
        db.session.flush()
        
        for entry in entries:
            detail = JournalDetail(
                journal_id=journal.id,
                account_id=entry['account_id'],
                debit=entry.get('debit', 0),
                credit=entry.get('credit', 0),
                description=entry.get('description', '')
            )
            db.session.add(detail)
            
            # Update account balance
            account = db.session.get(Account, entry['account_id'])
            if account:
                if account.category in ['asset', 'expense']:
                    account.balance += entry.get('debit', 0) - entry.get('credit', 0)
                else:
                    account.balance += entry.get('credit', 0) - entry.get('debit', 0)
        
        db.session.commit()
        return journal
    except Exception as e:
        db.session.rollback()
        print(f"Error creating journal entry: {e}")
        raise e

def create_journal_from_template(template_key, date, amounts):
    """Membuat jurnal dari template dengan amount yang diberikan"""
    try:
        template = TRANSACTION_TEMPLATES[template_key]
        accounts_map = {}
        
        # Build accounts mapping
        for account in Account.query.all():
            accounts_map[account.type] = account.id
        
        entries = []
        amount_index = 0
        amount_keys = list(amounts.keys())
        
        for template_entry in template['entries']:
            account_type = template_entry['account_type']
            # Handle duplicate account types (like kas2)
            if amount_index < len(amount_keys):
                current_amount_key = amount_keys[amount_index]
                if current_amount_key.startswith(account_type):
                    amount = amounts[current_amount_key]
                    amount_index += 1
                else:
                    amount = amounts.get(account_type, 0)
            else:
                amount = amounts.get(account_type, 0)
            
            if account_type in accounts_map:
                entry = {
                    'account_id': accounts_map[account_type],
                    'description': template_entry['description']
                }
                if template_entry['side'] == 'debit':
                    entry['debit'] = amount
                    entry['credit'] = 0
                else:
                    entry['debit'] = 0
                    entry['credit'] = amount
                
                entries.append(entry)
        
        # Create journal entry dengan transaction number yang unique
        journal = create_journal_entry(
            generate_unique_transaction_number(),
            date,
            template['description'],
            'general',
            entries
        )
        
        return journal
        
    except Exception as e:
        print(f"Error creating journal from template {template_key}: {e}")
        return None

def generate_transaction_number(prefix='TRX'):
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    return f"{prefix}{timestamp}"

def create_cash_flow_entry(date, description, category, amount, flow_type):
    cash_flow = CashFlow(
        date=date,
        description=description,
        category=category,
        amount=amount,
        type=flow_type
    )
    db.session.add(cash_flow)
    db.session.commit()
    return cash_flow

# ===== FUNGSI UNTUK MEMBUAT JURNAL UMUM OTOMATIS =====
def create_initial_journals():
    """Membuat jurnal umum awal berdasarkan saldo awal yang diberikan"""
    try:
        # Cek apakah sudah ada jurnal
        if JournalEntry.query.count() > 0:
            print("Jurnal sudah ada, skip pembuatan initial journals")
            return
        
        print("Membuat jurnal umum awal berdasarkan saldo awal...")
        
        # Get accounts mapping
        accounts_map = {}
        for account in Account.query.all():
            accounts_map[account.type] = account.id
        
        # Jurnal untuk mencatat saldo awal
        # Tanggal 1 Januari 2025 - Pencatatan saldo awal usaha
        journal_entries = [
            {
                'transaction_number': generate_unique_transaction_number('SALDO'),
                'date': datetime(2025, 1, 1),
                'description': 'Pencatatan saldo awal usaha Kang-Mas Shop',
                'journal_type': 'opening_balance',
                'entries': [
                    {'account_type': 'kas', 'debit': 10000000, 'credit': 0, 'description': 'Saldo awal kas'},
                    {'account_type': 'persediaan', 'debit': 5000000, 'credit': 0, 'description': 'Saldo awal persediaan barang dagang'},
                    {'account_type': 'peralatan', 'debit': 5000000, 'credit': 0, 'description': 'Saldo awal peralatan toko'},
                    {'account_type': 'perlengkapan', 'debit': 6500000, 'credit': 0, 'description': 'Saldo awal perlengkapan toko'},
                    {'account_type': 'pendapatan', 'debit': 0, 'credit': 6500000, 'description': 'Saldo awal penjualan'},
                    {'account_type': 'hutang', 'debit': 0, 'credit': 20000000, 'description': 'Saldo awal utang dagang'}
                ]
            }
        ]
        
        for journal_data in journal_entries:
            entries = []
            for entry_data in journal_data['entries']:
                if entry_data['account_type'] in accounts_map:
                    entries.append({
                        'account_id': accounts_map[entry_data['account_type']],
                        'debit': entry_data['debit'],
                        'credit': entry_data['credit'],
                        'description': entry_data['description']
                    })
            
            if entries:
                create_journal_entry(
                    journal_data['transaction_number'],
                    journal_data['date'],
                    journal_data['description'],
                    journal_data['journal_type'],
                    entries
                )
        
        print("Jurnal umum saldo awal berhasil dibuat!")
        
    except Exception as e:
        print(f"Error creating initial journals: {e}")

# ===== INITIAL DATA =====
def create_initial_data():
    # Create seller account
    seller = User.query.filter_by(email='kang.mas1817@gmail.com').first()
    if not seller:
        seller = User(
            email='kang.mas1817@gmail.com',
            full_name='Pemilik Kang-Mas Shop',
            user_type='seller',
            phone='+6289654733875',
            address='Magelang, Jawa Tengah',
            avatar='👑',
            email_verified=True
        )
        seller.set_password('TugasSiaKangMas')
        db.session.add(seller)
        print("Seller account created successfully")

    # Create demo customer
    if not User.query.filter_by(email='customer@example.com').first():
        customer = User(
            email='customer@example.com',
            full_name='Budi Santoso',
            user_type='customer',
            phone='087654321098',
            address='Jl. Contoh No. 123, Jakarta',
            avatar='👨',
            email_verified=True
        )
        customer.set_password('customer123')
        db.session.add(customer)

    # Create accounts dengan saldo awal
    if Account.query.count() == 0:
        accounts = [
            # Asset Accounts
            {'code': '101', 'name': 'Kas', 'type': 'kas', 'category': 'asset', 'balance': 10000000},
            {'code': '102', 'name': 'Piutang Usaha', 'type': 'piutang', 'category': 'asset', 'balance': 0},
            {'code': '103', 'name': 'Persediaan Barang Dagang', 'type': 'persediaan', 'category': 'asset', 'balance': 5000000},
            {'code': '104', 'name': 'Perlengkapan Toko', 'type': 'perlengkapan', 'category': 'asset', 'balance': 6500000},
            {'code': '105', 'name': 'Peralatan Toko', 'type': 'peralatan', 'category': 'asset', 'balance': 5000000},
            {'code': '106', 'name': 'Akumulasi Penyusutan', 'type': 'akumulasi_penyusutan', 'category': 'asset', 'balance': 0},
            
            # Liability Accounts
            {'code': '201', 'name': 'Utang Dagang', 'type': 'hutang', 'category': 'liability', 'balance': 20000000},
            
            # Equity Accounts
            {'code': '301', 'name': 'Modal', 'type': 'modal', 'category': 'equity', 'balance': 0},
            {'code': '302', 'name': 'Prive', 'type': 'prive', 'category': 'equity', 'balance': 0},
            
            # Revenue Accounts
            {'code': '401', 'name': 'Pendapatan Penjualan', 'type': 'pendapatan', 'category': 'revenue', 'balance': 6500000},
            
            # Expense Accounts
            {'code': '501', 'name': 'Harga Pokok Penjualan', 'type': 'hpp', 'category': 'expense', 'balance': 0},
            {'code': '502', 'name': 'Beban Gaji', 'type': 'beban_gaji', 'category': 'expense', 'balance': 0},
            {'code': '503', 'name': 'Beban Listrik dan Air', 'type': 'beban_listrik', 'category': 'expense', 'balance': 0},
            {'code': '504', 'name': 'Beban Perlengkapan', 'type': 'beban_perlengkapan', 'category': 'expense', 'balance': 0},
            {'code': '505', 'name': 'Beban Penyusutan', 'type': 'beban_penyusutan', 'category': 'expense', 'balance': 0},
            {'code': '506', 'name': 'Beban Transportasi', 'type': 'beban_transport', 'category': 'expense', 'balance': 0},
            {'code': '507', 'name': 'Beban Operasional', 'type': 'beban_operasional', 'category': 'expense', 'balance': 0},
            {'code': '520', 'name': 'Beban Kerugian', 'type': 'beban_kerugian', 'category': 'expense', 'balance': 0},
            {'code': '529', 'name': 'Beban Lain-lain', 'type': 'beban_lain', 'category': 'expense', 'balance': 0},
        ]
        
        for acc_data in accounts:
            account = Account(**acc_data)
            db.session.add(account)

    # Create products
    if Product.query.count() == 0:
        seller_id = User.query.filter_by(user_type='seller').first().id
        products = [
            {
                'name': 'Bibit Ikan Mas',
                'description': 'Bibit ikan mas segar ukuran 8cm, kualitas terbaik untuk pembesaran',
                'price': 2000,
                'cost_price': 1000,
                'stock': 1000,
                'size_cm': 8,
                'seller_id': seller_id,
                'category': 'bibit',
                'image_url': '/static/uploads/products/bibit_ikan_mas.jpg'
            },
            {
                'name': 'Ikan Mas Konsumsi',
                'description': 'Ikan mas segar siap konsumsi, berat 1kg',
                'price': 30000,
                'cost_price': 20000,
                'stock': 50,
                'weight_kg': 1,
                'seller_id': seller_id,
                'category': 'konsumsi',
                'is_featured': True,
                'image_url': '/static/uploads/products/ikan_mas_konsumsi.jpg'
            }
        ]
        
        for prod_data in products:
            product = Product(**prod_data)
            db.session.add(product)

    # Create settings
    if AppSetting.query.count() == 0:
        settings = [
            {'key': 'app_name', 'value': 'Kang-Mas Shop'},
            {'key': 'app_logo', 'value': '/static/uploads/logos/logo.png'},
            {'key': 'app_description', 'value': 'Toko Ikan Mas Segar sejak 2017'},
            {'key': 'contact_phone', 'value': '+6289654733875'},
            {'key': 'contact_address', 'value': 'Magelang, Jawa Tengah'}
        ]
        
        for setting_data in settings:
            setting = AppSetting(**setting_data)
            db.session.add(setting)

    db.session.commit()
    print("Initial data created successfully")
    
    # Buat jurnal umum setelah data initial dibuat
    create_initial_journals()

# ===== FUNGSI STOK MANAGEMENT =====
def update_stock_from_journal(journal_entry):
    """Update stok produk berdasarkan jurnal pembelian"""
    try:
        # Cek apakah ini jurnal pembelian persediaan
        for detail in journal_entry.journal_details:
            if detail.account.type == 'persediaan' and detail.debit > 0:
                # Ini adalah pembelian bibit/ikan - tambah stok
                product_name = journal_entry.description
                
                # Cari produk berdasarkan nama atau deskripsi
                product = Product.query.filter(
                    (Product.name.ilike(f"%{product_name}%")) | 
                    (Product.description.ilike(f"%{product_name}%"))
                ).first()
                
                if product:
                    # Hitung quantity berdasarkan harga (asumsi harga per item)
                    quantity = int(detail.debit / product.cost_price)
                    product.stock += quantity
                    print(f"✅ Stok {product.name} bertambah {quantity} menjadi {product.stock}")
                    
        db.session.commit()
    except Exception as e:
        print(f"Error updating stock from journal: {e}")

def create_sales_journal(order):
    """Buat jurnal penjualan otomatis saat order completed"""
    try:
        # Hitung total harga produk saja (tanpa ongkir)
        product_total = 0
        for item in OrderItem.query.filter_by(order_id=order.id).all():
            product_total += item.price * item.quantity
        
        # Buat jurnal penjualan
        transaction_number = generate_unique_transaction_number('SALES')
        description = f"Penjualan Order #{order.order_number}"
        
        # Get accounts
        kas_account = Account.query.filter_by(type='kas').first()
        pendapatan_account = Account.query.filter_by(type='pendapatan').first()
        
        if kas_account and pendapatan_account:
            entries = [
                {
                    'account_id': kas_account.id,
                    'debit': product_total,
                    'credit': 0,
                    'description': f'Penerimaan penjualan order #{order.order_number}'
                },
                {
                    'account_id': pendapatan_account.id,
                    'debit': 0,
                    'credit': product_total,
                    'description': f'Pendapatan penjualan order #{order.order_number}'
                }
            ]
            
            journal = create_journal_entry(
                transaction_number,
                order.completed_date or datetime.now(),
                description,
                'sales',
                entries
            )
            
            print(f"✅ Jurnal penjualan dibuat untuk order #{order.order_number}: Rp {product_total:,.0f}")
            return journal
        
    except Exception as e:
        print(f"Error creating sales journal: {e}")
    return None

# ===== FUNGSI BUKU BESAR =====
def get_ledger_data():
    """Ambil data untuk buku besar - hanya akun yang punya transaksi"""
    try:
        # Dapatkan semua akun yang punya transaksi di journal_details
        accounts_with_transactions = db.session.query(Account).join(JournalDetail).distinct().order_by(Account.code).all()
        
        ledger_html = ""
        
        for account in accounts_with_transactions:
            # Dapatkan semua transaksi untuk akun ini
            journal_details = JournalDetail.query.filter_by(account_id=account.id).order_by(JournalDetail.journal_id).all()
            
            account_html = f'''
            <div class="card" style="margin-bottom: 2rem;">
                <h4 style="color: var(--primary); margin-bottom: 1rem;">
                    {account.code} - {account.name}
                </h4>
                <div style="margin-bottom: 1rem;">
                    <strong>Saldo Awal:</strong> Rp 0
                    <strong style="margin-left: 2rem;">Saldo Akhir:</strong> 
                    <span class="{'debit' if account.balance >= 0 else 'credit'}">
                        Rp {abs(account.balance):,.0f}
                    </span>
                </div>
                
                <div style="overflow-x: auto;">
                    <table class="table">
                        <thead>
                            <tr>
                                <th>Tanggal</th>
                                <th>Keterangan</th>
                                <th>Debit</th>
                                <th>Kredit</th>
                                <th>Saldo</th>
                            </tr>
                        </thead>
                        <tbody>
            '''
            
            running_balance = 0
            
            for detail in journal_details:
                journal = detail.journal_entry
                
                if account.category in ['asset', 'expense']:
                    running_balance += detail.debit - detail.credit
                else:
                    running_balance += detail.credit - detail.debit
                
                account_html += f'''
                <tr>
                    <td>{journal.date.strftime('%d/%m/%Y')}</td>
                    <td>{journal.description}</td>
                    <td class="debit">{"Rp {0:,.0f}".format(detail.debit) if detail.debit > 0 else ""}</td>
                    <td class="credit">{"Rp {0:,.0f}".format(detail.credit) if detail.credit > 0 else ""}</td>
                    <td class="{'debit' if running_balance >= 0 else 'credit'}">Rp {abs(running_balance):,.0f}</td>
                </tr>
                '''
            
            account_html += f'''
                        </tbody>
                    </table>
                </div>
            </div>
            '''
            
            ledger_html += account_html
        
        return ledger_html if ledger_html else '<div class="card"><p>Belum ada transaksi untuk ditampilkan di buku besar.</p></div>'
        
    except Exception as e:
        print(f"Error generating ledger data: {e}")
        return '<div class="card"><p>Error loading ledger data.</p></div>'

def get_balance_sheet():
    """Generate balance sheet HTML"""
    try:
        # Get asset accounts
        asset_accounts = Account.query.filter_by(category='asset').all()
        total_assets = sum(acc.balance for acc in asset_accounts if acc.balance > 0)
        
        # Get liability accounts
        liability_accounts = Account.query.filter_by(category='liability').all()
        total_liabilities = sum(acc.balance for acc in liability_accounts if acc.balance > 0)
        
        # Get equity accounts
        equity_accounts = Account.query.filter_by(category='equity').all()
        total_equity = sum(acc.balance for acc in equity_accounts if acc.balance > 0)
        
        # Calculate net income
        revenue_accounts = Account.query.filter_by(category='revenue').all()
        expense_accounts = Account.query.filter_by(category='expense').all()
        total_revenue = sum(acc.balance for acc in revenue_accounts)
        total_expenses = sum(acc.balance for acc in expense_accounts)
        net_income = total_revenue - total_expenses
        
        total_equity += net_income
        
        assets_html = ""
        for acc in asset_accounts:
            if acc.balance > 0:
                assets_html += f'''
                <tr>
                    <td>{acc.name}</td>
                    <td class="debit">Rp {acc.balance:,.0f}</td>
                </tr>
                '''
        
        liabilities_html = ""
        for acc in liability_accounts:
            if acc.balance > 0:
                liabilities_html += f'''
                <tr>
                    <td>{acc.name}</td>
                    <td class="credit">Rp {acc.balance:,.0f}</td>
                </tr>
                '''
        
        equity_html = ""
        for acc in equity_accounts:
            if acc.balance > 0:
                equity_html += f'''
                <tr>
                    <td>{acc.name}</td>
                    <td class="credit">Rp {acc.balance:,.0f}</td>
                </tr>
                '''
        
        return f'''
        <div class="grid grid-2">
            <div>
                <h4>Aset</h4>
                <table class="table">
                    <tbody>
                        {assets_html}
                        <tr style="font-weight: bold; border-top: 2px solid var(--primary);">
                            <td>Total Aset</td>
                            <td class="debit">Rp {total_assets:,.0f}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
            
            <div>
                <h4>Kewajiban & Ekuitas</h4>
                <table class="table">
                    <tbody>
                        {liabilities_html}
                        <tr style="font-weight: bold;">
                            <td>Total Kewajiban</td>
                            <td class="credit">Rp {total_liabilities:,.0f}</td>
                        </tr>
                        {equity_html}
                        <tr>
                            <td>Laba Bersih</td>
                            <td class="credit">Rp {net_income:,.0f}</td>
                        </tr>
                        <tr style="font-weight: bold; border-top: 2px solid var(--primary);">
                            <td>Total Kewajiban & Ekuitas</td>
                            <td class="credit">Rp {total_liabilities + total_equity + net_income:,.0f}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
        
        <div style="margin-top: 2rem; padding: 1.5rem; background: {'rgba(56, 161, 105, 0.1)' if total_assets == (total_liabilities + total_equity + net_income) else 'rgba(229, 62, 62, 0.1)'}; border-radius: var(--border-radius);">
            <h4 style="color: {'var(--success)' if total_assets == (total_liabilities + total_equity + net_income) else 'var(--error)'};">
                {'✅ Neraca Seimbang' if total_assets == (total_liabilities + total_equity + net_income) else '❌ Neraca Tidak Seimbang'}
            </h4>
            <p>Aset = Kewajiban + Ekuitas</p>
            <p>Rp {total_assets:,.0f} = Rp {total_liabilities + total_equity + net_income:,.0f}</p>
        </div>
        '''
    except Exception as e:
        print(f"Error generating balance sheet: {e}")
        return '<p>Error loading balance sheet</p>'

def get_cash_flow_statement():
    """Generate cash flow statement HTML"""
    try:
        # Get cash account
        cash_account = Account.query.filter_by(type='kas').first()
        cash_balance = cash_account.balance if cash_account else 0
        
        # Get operating activities (simplified)
        revenue_accounts = Account.query.filter_by(category='revenue').all()
        operating_inflows = sum(acc.balance for acc in revenue_accounts)
        
        expense_accounts = Account.query.filter_by(category='expense').all()
        operating_outflows = sum(acc.balance for acc in expense_accounts)
        
        net_cash_operating = operating_inflows - operating_outflows
        
        return f'''
        <table class="table">
            <thead>
                <tr>
                    <th>Aktivitas Operasi</th>
                    <th>Jumlah</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>Penerimaan dari Penjualan</td>
                    <td class="debit">Rp {operating_inflows:,.0f}</td>
                </tr>
                <tr>
                    <td>Pengeluaran Operasional</td>
                    <td class="credit">Rp {operating_outflows:,.0f}</td>
                </tr>
                <tr style="font-weight: bold; border-top: 2px solid var(--primary);">
                    <td>Arus Kas Bersih dari Operasi</td>
                    <td class="{'debit' if net_cash_operating >= 0 else 'credit'}">Rp {abs(net_cash_operating):,.0f}</td>
                </tr>
            </tbody>
        </table>
        
        <div style="margin-top: 2rem; padding: 1.5rem; background: rgba(49, 130, 206, 0.1); border-radius: var(--border-radius);">
            <h4 style="color: var(--primary);">Saldo Kas Akhir</h4>
            <p class="price">Rp {cash_balance:,.0f}</p>
        </div>
        '''
    except Exception as e:
        print(f"Error generating cash flow statement: {e}")
        return '<p>Error loading cash flow statement</p>'

# ===== DEEP OCEAN HTML TEMPLATES =====
def base_html(title, content, additional_css="", additional_js=""):
    settings = {s.key: s.value for s in AppSetting.query.all()}
    app_name = settings.get('app_name', 'Kang-Mas Shop')
    app_logo = settings.get('app_logo', '/static/uploads/logos/logo.png')
    
    return f'''
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - {app_name}</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Poppins:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link rel="icon" href="{app_logo}" type="image/x-icon">
    <style>
        :root {{
            --primary: {COLORS['primary']};
            --secondary: {COLORS['secondary']};
            --accent: {COLORS['accent']};
            --success: {COLORS['success']};
            --warning: {COLORS['warning']};
            --error: {COLORS['error']};
            --dark: {COLORS['dark']};
            --light: {COLORS['light']};
            --white: {COLORS['white']};
            --teal: {COLORS['teal']};
            --navy: {COLORS['navy']};
            --ocean-light: {COLORS['ocean-light']};
            --ocean-medium: {COLORS['ocean-medium']};
            --ocean-deep: {COLORS['ocean-deep']};
            --shadow-sm: 0 2px 4px rgba(0,0,0,0.1);
            --shadow-md: 0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.06);
            --shadow-lg: 0 10px 15px -3px rgba(0,0,0,0.1), 0 4px 6px -2px rgba(0,0,0,0.05);
            --shadow-xl: 0 20px 25px -5px rgba(0,0,0,0.1), 0 10px 10px -5px rgba(0,0,0,0.04);
            --border-radius: 12px;
            --border-radius-lg: 16px;
            --border-radius-xl: 20px;
        }}
        
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Inter', sans-serif;
            background: linear-gradient(135deg, #f0f9ff 0%, #e6f3ff 100%);
            color: var(--dark);
            min-height: 100vh;
            line-height: 1.6;
        }}
        
        /* Ocean Navbar */
        .navbar {{
            background: linear-gradient(135deg, var(--primary) 0%, var(--ocean-deep) 100%);
            padding: 1rem 2rem;
            position: sticky;
            top: 0;
            z-index: 1000;
            box-shadow: var(--shadow-lg);
        }}
        
        .nav-container {{
            max-width: 1400px;
            margin: 0 auto;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .nav-brand {{
            font-family: 'Poppins', sans-serif;
            font-size: 1.8rem;
            font-weight: 800;
            color: var(--white);
            text-decoration: none;
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }}
        
        .nav-links {{
            display: flex;
            align-items: center;
            gap: 1rem;
        }}
        
        .nav-link {{
            color: var(--white);
            text-decoration: none;
            padding: 0.75rem 1.5rem;
            border-radius: var(--border-radius);
            transition: all 0.3s ease;
            font-weight: 500;
        }}
        
        .nav-link:hover {{
            background: rgba(255, 255, 255, 0.2);
            transform: translateY(-2px);
        }}
        
        .user-menu {{
            display: flex;
            align-items: center;
            gap: 1rem;
            background: rgba(255, 255, 255, 0.2);
            padding: 0.75rem 1.5rem;
            border-radius: var(--border-radius);
            backdrop-filter: blur(10px);
        }}
        
        .avatar {{
            width: 45px;
            height: 45px;
            border-radius: 50%;
            background: var(--ocean-medium);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.3rem;
            color: var(--white);
            box-shadow: var(--shadow-md);
        }}
        
        .badge {{
            padding: 0.4rem 1rem;
            border-radius: 25px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            background: var(--ocean-medium);
            color: var(--white);
            box-shadow: var(--shadow-sm);
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 2rem;
        }}
        
        /* Ocean Cards */
        .card {{
            background: rgba(255, 255, 255, 0.9);
            backdrop-filter: blur(10px);
            border-radius: var(--border-radius-lg);
            padding: 2rem;
            box-shadow: var(--shadow-lg);
            margin-bottom: 2rem;
            border: 1px solid rgba(255, 255, 255, 0.3);
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }}
        
        .card::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--ocean-deep) 100%);
        }}
        
        .card:hover {{
            transform: translateY(-5px);
            box-shadow: var(--shadow-xl);
        }}
        
        /* Ocean Buttons */
        .btn {{
            padding: 0.875rem 2rem;
            border: none;
            border-radius: var(--border-radius);
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 0.75rem;
            cursor: pointer;
            transition: all 0.3s ease;
            font-weight: 600;
            font-size: 0.95rem;
        }}
        
        .btn-primary {{
            background: linear-gradient(135deg, var(--primary) 0%, var(--ocean-deep) 100%);
            color: var(--white);
            box-shadow: var(--shadow-md);
        }}
        
        .btn-primary:hover {{
            transform: translateY(-2px);
            box-shadow: var(--shadow-lg);
        }}
        
        .btn-success {{ 
            background: linear-gradient(135deg, var(--success) 0%, var(--teal) 100%);
            color: var(--white);
            box-shadow: var(--shadow-md);
        }}
        
        .btn-warning {{ 
            background: linear-gradient(135deg, var(--warning) 0%, #b7791f 100%);
            color: var(--white);
            box-shadow: var(--shadow-md);
        }}
        
        .btn-danger {{ 
            background: linear-gradient(135deg, var(--error) 0%, #c53030 100%);
            color: var(--white);
            box-shadow: var(--shadow-md);
        }}
        
        .btn-info {{ 
            background: linear-gradient(135deg, var(--ocean-medium) 0%, var(--teal) 100%);
            color: var(--white);
            box-shadow: var(--shadow-md);
        }}
        
        .grid {{
            display: grid;
            gap: 2rem;
        }}
        
        .grid-2 {{ grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); }}
        .grid-3 {{ grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }}
        .grid-4 {{ grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); }}
        
        /* Ocean Hero Section */
        .hero {{
            text-align: center;
            padding: 5rem 2rem;
            background: linear-gradient(135deg, var(--primary) 0%, var(--ocean-deep) 100%);
            border-radius: var(--border-radius-xl);
            margin-bottom: 3rem;
            color: var(--white);
            position: relative;
            overflow: hidden;
        }}
        
        .hero::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000"><polygon fill="rgba(255,255,255,0.05)" points="0,1000 1000,0 1000,1000"/></svg>');
        }}
        
        .hero h1 {{
            font-size: 3.5rem;
            margin-bottom: 1.5rem;
            font-family: 'Poppins', sans-serif;
            font-weight: 800;
        }}
        
        .hero p {{
            font-size: 1.25rem;
            margin-bottom: 2rem;
            opacity: 0.9;
        }}
        
        /* Ocean Stats */
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 1.5rem;
            margin: 3rem 0;
        }}
        
        .stat-card {{
            background: linear-gradient(135deg, var(--white) 0%, var(--ocean-light) 100%);
            padding: 2.5rem 2rem;
            border-radius: var(--border-radius-lg);
            text-align: center;
            box-shadow: var(--shadow-lg);
            border: 1px solid rgba(255, 255, 255, 0.5);
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }}
        
        .stat-card::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--ocean-deep) 100%);
        }}
        
        .stat-card:hover {{
            transform: translateY(-5px);
            box-shadow: var(--shadow-xl);
        }}
        
        .stat-number {{
            font-family: 'Poppins', sans-serif;
            font-size: 2.5rem;
            font-weight: 800;
            color: var(--primary);
            margin-bottom: 0.5rem;
        }}
        
        .price {{
            font-family: 'Poppins', sans-serif;
            font-size: 2rem;
            font-weight: 700;
            color: var(--primary);
        }}
        
        /* Ocean Tables */
        .table {{
            width: 100%;
            border-collapse: collapse;
            background: var(--white);
            border-radius: var(--border-radius);
            overflow: hidden;
            box-shadow: var(--shadow-lg);
        }}
        
        .table th, .table td {{
            padding: 1.25rem;
            text-align: left;
            border-bottom: 1px solid rgba(0,0,0,0.05);
        }}
        
        .table th {{
            background: linear-gradient(135deg, var(--primary) 0%, var(--ocean-deep) 100%);
            color: var(--white);
            font-weight: 600;
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .table tr:hover {{
            background: rgba(49, 130, 206, 0.05);
        }}
        
        /* Ocean Forms */
        .form-group {{
            margin-bottom: 1.75rem;
        }}
        
        .form-label {{
            display: block;
            margin-bottom: 0.75rem;
            font-weight: 600;
            color: var(--dark);
            font-size: 0.95rem;
        }}
        
        .form-control {{
            width: 100%;
            padding: 1rem 1.25rem;
            border: 2px solid rgba(0,0,0,0.1);
            border-radius: var(--border-radius);
            font-size: 1rem;
            transition: all 0.3s ease;
            background: rgba(255, 255, 255, 0.8);
            font-family: 'Inter', sans-serif;
        }}
        
        .form-control:focus {{
            outline: none;
            border-color: var(--ocean-medium);
            box-shadow: 0 0 0 3px rgba(49, 130, 206, 0.1);
            background: var(--white);
        }}
        
        /* Ocean Tabs */
        .accounting-tabs {{
            display: flex;
            gap: 0.5rem;
            margin-bottom: 2rem;
            background: rgba(255, 255, 255, 0.6);
            padding: 0.5rem;
            border-radius: var(--border-radius);
            backdrop-filter: blur(10px);
        }}
        
        .tab {{
            padding: 1rem 2rem;
            background: transparent;
            border: none;
            border-radius: var(--border-radius);
            cursor: pointer;
            font-weight: 600;
            color: var(--dark);
            transition: all 0.3s ease;
            position: relative;
        }}
        
        .tab.active {{
            background: linear-gradient(135deg, var(--primary) 0%, var(--ocean-deep) 100%);
            color: var(--white);
            box-shadow: var(--shadow-md);
        }}
        
        .tab-content {{
            display: none;
        }}
        
        .tab-content.active {{
            display: block;
            animation: fadeIn 0.5s ease;
        }}
        
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        
        .debit {{ 
            color: var(--success); 
            font-weight: 600;
            background: rgba(56, 161, 105, 0.1);
            padding: 0.5rem 1rem;
            border-radius: var(--border-radius);
        }}
        
        .credit {{ 
            color: var(--error); 
            font-weight: 600;
            background: rgba(229, 62, 62, 0.1);
            padding: 0.5rem 1rem;
            border-radius: var(--border-radius);
        }}
        
        /* Product Cards */
        .product-image {{
            width: 100%;
            height: 220px;
            object-fit: cover;
            border-radius: var(--border-radius);
            margin-bottom: 1.5rem;
            transition: transform 0.3s ease;
            box-shadow: var(--shadow-md);
        }}
        
        .product-card:hover .product-image {{
            transform: scale(1.05);
        }}
        
        /* Tracking Steps */
        .tracking-steps {{
            display: flex;
            justify-content: space-between;
            margin: 2rem 0;
            position: relative;
        }}
        
        .tracking-steps::before {{
            content: '';
            position: absolute;
            top: 25px;
            left: 0;
            right: 0;
            height: 3px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--ocean-deep) 100%);
            z-index: 1;
            border-radius: 10px;
        }}
        
        .tracking-step {{
            text-align: center;
            position: relative;
            z-index: 2;
            flex: 1;
        }}
        
        .step-icon {{
            width: 50px;
            height: 50px;
            border-radius: 50%;
            background: var(--ocean-light);
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 0.75rem;
            transition: all 0.3s ease;
            font-size: 1.25rem;
            box-shadow: var(--shadow-md);
            border: 3px solid var(--white);
        }}
        
        .step-active {{
            background: linear-gradient(135deg, var(--primary) 0%, var(--ocean-deep) 100%);
            color: var(--white);
            transform: scale(1.1);
        }}
        
        .step-completed {{
            background: linear-gradient(135deg, var(--success) 0%, var(--teal) 100%);
            color: var(--white);
        }}
        
        /* Google Button */
        .google-btn {{
            background: #4285F4;
            color: white;
            width: 100%;
            justify-content: center;
            margin-top: 1rem;
            box-shadow: var(--shadow-md);
        }}
        
        .google-btn:hover {{
            background: #357ae8;
            transform: translateY(-2px);
            box-shadow: var(--shadow-lg);
        }}
        
        /* Divider */
        .divider {{
            text-align: center;
            margin: 1.5rem 0;
            position: relative;
        }}
        
        .divider::before {{
            content: '';
            position: absolute;
            top: 50%;
            left: 0;
            right: 0;
            height: 1px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--ocean-deep) 100%);
        }}
        
        .divider span {{
            background: var(--white);
            padding: 0 1.5rem;
            position: relative;
            color: var(--dark);
            font-weight: 500;
        }}
        
        /* Flash Messages */
        .flash-messages {{
            position: fixed;
            top: 100px;
            right: 20px;
            z-index: 10000;
        }}
        
        .flash-message {{
            padding: 1.25rem 1.75rem;
            border-radius: var(--border-radius);
            margin-bottom: 0.75rem;
            font-weight: 500;
            box-shadow: var(--shadow-xl);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.2);
            animation: slideInRight 0.5s ease;
        }}
        
        @keyframes slideInRight {{
            from {{ transform: translateX(100%); opacity: 0; }}
            to {{ transform: translateX(0); opacity: 1; }}
        }}
        
        .flash-success {{ 
            background: linear-gradient(135deg, var(--success) 0%, var(--teal) 100%);
            color: white;
        }}
        
        .flash-error {{ 
            background: linear-gradient(135deg, var(--error) 0%, #c53030 100%);
            color: white;
        }}
        
        .flash-warning {{ 
            background: linear-gradient(135deg, var(--warning) 0%, #b7791f 100%);
            color: white;
        }}
        
        /* Logo Styling */
        .navbar-logo {{
            width: 45px;
            height: 45px;
            border-radius: 12px;
            object-fit: cover;
            margin-right: 12px;
            box-shadow: var(--shadow-md);
            border: 2px solid rgba(255, 255, 255, 0.3);
        }}

        /* Ocean Modal Styles */
        .modal {{
            display: none;
            position: fixed;
            z-index: 10000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.5);
            backdrop-filter: blur(10px);
        }}

        .modal-content {{
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(20px);
            margin: 10% auto;
            padding: 2.5rem;
            border-radius: var(--border-radius-xl);
            width: 90%;
            max-width: 500px;
            box-shadow: var(--shadow-xl);
            border: 1px solid rgba(255, 255, 255, 0.3);
            position: relative;
            animation: modalSlideIn 0.3s ease;
        }}
        
        @keyframes modalSlideIn {{
            from {{ transform: translateY(-50px); opacity: 0; }}
            to {{ transform: translateY(0); opacity: 1; }}
        }}

        .close {{
            color: #aaa;
            float: right;
            font-size: 28px;
            font-weight: bold;
            cursor: pointer;
            position: absolute;
            right: 1.5rem;
            top: 1.5rem;
            transition: color 0.3s ease;
        }}

        .close:hover {{
            color: var(--error);
        }}

        .modal-buttons {{
            display: flex;
            gap: 1rem;
            margin-top: 2rem;
        }}

        .modal-buttons .btn {{
            flex: 1;
        }}

        /* Status Badges */
        .status-text {{
            padding: 0.5rem 1rem;
            border-radius: 25px;
            font-weight: 600;
            display: inline-block;
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            box-shadow: var(--shadow-sm);
        }}

        .status-pending {{ 
            background: linear-gradient(135deg, var(--warning) 0%, #b7791f 100%);
            color: white;
        }}
        
        .status-processing {{ 
            background: linear-gradient(135deg, var(--ocean-medium) 0%, var(--ocean-deep) 100%);
            color: white;
        }}
        
        .status-completed {{ 
            background: linear-gradient(135deg, var(--success) 0%, var(--teal) 100%);
            color: white;
        }}
        
        .status-cancelled {{ 
            background: linear-gradient(135deg, var(--error) 0%, #c53030 100%);
            color: white;
        }}
        
        .status-paid {{ 
            background: linear-gradient(135deg, var(--success) 0%, var(--teal) 100%);
            color: white;
        }}
        
        .status-unpaid {{ 
            background: linear-gradient(135deg, var(--error) 0%, #c53030 100%);
            color: white;
        }}
        
        /* Floating Action Button */
        .fab {{
            position: fixed;
            bottom: 2rem;
            right: 2rem;
            width: 60px;
            height: 60px;
            border-radius: 50%;
            background: linear-gradient(135deg, var(--primary) 0%, var(--ocean-deep) 100%);
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5rem;
            box-shadow: var(--shadow-xl);
            cursor: pointer;
            z-index: 1000;
            transition: all 0.3s ease;
            text-decoration: none;
        }}
        
        .fab:hover {{
            transform: scale(1.1);
        }}
        
        /* Loading Animation */
        .loading {{
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(255,255,255,.3);
            border-radius: 50%;
            border-top-color: #fff;
            animation: spin 1s ease-in-out infinite;
        }}
        
        @keyframes spin {{
            to {{ transform: rotate(360deg); }}
        }}
        
        /* Responsive Design */
        @media (max-width: 768px) {{
            .nav-links {{
                flex-direction: column;
                gap: 0.5rem;
            }}
            
            .hero h1 {{
                font-size: 2.5rem;
            }}
            
            .grid-2, .grid-3, .grid-4 {{
                grid-template-columns: 1fr;
            }}
            
            .container {{
                padding: 1rem;
            }}
            
            .stats {{
                grid-template-columns: 1fr;
            }}
        }}
        
        {additional_css}
    </style>
</head>
<body>
    <!-- Floating Cart Button -->
    {current_user.is_authenticated and current_user.user_type == 'customer' and '''
    <a href="/cart" class="fab">
        <i class="fas fa-shopping-cart"></i>
        <span id="cart-count-fab" style="position: absolute; top: -5px; right: -5px; background: var(--error); color: white; border-radius: 50%; width: 20px; height: 20px; display: none; align-items: center; justify-content: center; font-size: 0.7rem; font-weight: bold;">0</span>
    </a>
    ''' or ''}

    <nav class="navbar">
        <div class="nav-container">
            <a href="/" class="nav-brand">
                <img src="{app_logo}" alt="{app_name}" class="navbar-logo" onerror="this.style.display='none'">
                <span>{app_name}</span>
            </a>
            
            <div class="nav-links">
                {get_navigation()}
            </div>
        </div>
    </nav>
    
    <div class="flash-messages">
        {get_flash_messages()}
    </div>
    
    <div class="container">
        {content}
    </div>

    <!-- Ocean Payment Modal -->
    <div id="paymentModal" class="modal">
        <div class="modal-content">
            <span class="close" onclick="closeModal('paymentModal')">&times;</span>
            <div style="text-align: center; margin-bottom: 1.5rem;">
                <div style="width: 60px; height: 60px; background: linear-gradient(135deg, var(--success) 0%, var(--teal) 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1rem;">
                    <i class="fas fa-credit-card" style="color: white; font-size: 1.5rem;"></i>
                </div>
                <h2 style="margin-bottom: 0.5rem; color: var(--primary);">Pembayaran</h2>
                <p style="color: var(--dark); opacity: 0.7;">Selesaikan pembayaran untuk melanjutkan</p>
            </div>
            
            <div id="paymentInstructions" style="background: rgba(49, 130, 206, 0.05); padding: 1.5rem; border-radius: var(--border-radius); margin-bottom: 1.5rem;">
                <!-- Instructions will be loaded here -->
            </div>
            
            <div class="modal-buttons">
                <button class="btn btn-success" onclick="showSuccessModal()" style="width: 100%;">
                    <i class="fas fa-check-circle"></i>
                    Sudah Bayar
                </button>
            </div>
        </div>
    </div>

    <!-- Ocean Success Modal -->
    <div id="successModal" class="modal">
        <div class="modal-content">
            <span class="close" onclick="closeModal('successModal')">&times;</span>
            <div style="text-align: center;">
                <div style="width: 80px; height: 80px; background: linear-gradient(135deg, var(--success) 0%, var(--teal) 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1.5rem;">
                    <i class="fas fa-check" style="color: white; font-size: 2rem;"></i>
                </div>
                <h2 style="margin-bottom: 1rem; color: var(--success);">Sukses!</h2>
                <p style="margin-bottom: 1rem; color: var(--dark);">Pembayaran berhasil dikonfirmasi</p>
                <p style="color: var(--dark); opacity: 0.7; font-size: 0.9rem; margin-bottom: 2rem;">
                    Pesanan Anda sedang diproses dan akan segera dikirim
                </p>
            </div>
            
            <div class="modal-buttons">
                <button class="btn btn-success" onclick="closeModal('successModal'); window.location.href='/orders';" style="width: 100%;">
                    <i class="fas fa-list"></i>
                    Lihat Pesanan Saya
                </button>
                <button class="btn btn-primary" onclick="contactSeller()" style="width: 100%;">
                    <i class="fab fa-whatsapp"></i>
                    Hubungi Penjual
                </button>
            </div>
        </div>
    </div>
    
    <script>
        // Ocean JavaScript Functions
        function addToCart(productId) {{
            console.log('🛒 Adding product to cart:', productId);
            
            if (!productId) {{
                showNotification('Product ID tidak valid', 'error');
                return;
            }}
            
            const button = event.target;
            const originalText = button.innerHTML;
            
            // Show loading state
            button.innerHTML = '<div class="loading"></div> Menambahkan...';
            button.disabled = true;
            
            const cartData = {{
                product_id: parseInt(productId),
                quantity: 1
            }};
            
            fetch('/api/cart/add', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                }},
                body: JSON.stringify(cartData)
            }})
            .then(response => {{
                if (!response.ok) {{
                    return response.json().then(errorData => {{
                        throw new Error(errorData.message || `HTTP error! status: ${{response.status}}`);
                    }});
                }}
                return response.json();
            }})
            .then(data => {{
                if (data.success) {{
                    showNotification('✅ ' + data.message, 'success');
                    updateCartCount();
                }} else {{
                    showNotification('❌ ' + data.message, 'error');
                }}
            }})
            .catch(error => {{
                console.error('Fetch error:', error);
                let errorMessage = 'Gagal menambahkan ke keranjang';
                
                if (error.message.includes('HTTP error! status: 403')) {{
                    errorMessage = 'Hanya customer yang bisa menambah ke keranjang';
                }} else if (error.message.includes('HTTP error! status: 404')) {{
                    errorMessage = 'Produk tidak ditemukan';
                }} else if (error.message.includes('HTTP error! status: 400')) {{
                    errorMessage = 'Stock tidak mencukupi';
                }}
                
                showNotification('❌ ' + errorMessage, 'error');
            }})
            .finally(() => {{
                setTimeout(() => {{
                    button.innerHTML = originalText;
                    button.disabled = false;
                }}, 1000);
            }});
        }}
        
        function showTab(tabName, element) {{
            document.querySelectorAll('.tab-content').forEach(tab => {{
                tab.classList.remove('active');
            }});
            document.querySelectorAll('.tab').forEach(tab => {{
                tab.classList.remove('active');
            }});
            document.getElementById(tabName).classList.add('active');
            element.classList.add('active');
        }}
        
        function showNotification(message, type) {{
            const notification = document.createElement('div');
            notification.className = `flash-message flash-${{type}}`;
            notification.innerHTML = `
                <div style="display: flex; align-items: center; gap: 0.75rem;">
                    <i class="fas fa-${{type === 'success' ? 'check-circle' : 'exclamation-circle'}}"></i>
                    <span>${{message}}</span>
                </div>
            `;
            
            const flashContainer = document.querySelector('.flash-messages');
            flashContainer.appendChild(notification);
            
            setTimeout(() => {{
                notification.style.animation = 'slideInRight 0.5s ease reverse';
                setTimeout(() => {{
                    flashContainer.removeChild(notification);
                }}, 500);
            }}, 4000);
        }}
        
        function checkout() {{
            window.location.href = '/checkout';
        }}
        
        function processCheckout() {{
            const shippingAddress = document.getElementById('shipping_address').value;
            const shippingMethod = document.getElementById('shipping_method').value;
            const paymentMethod = document.getElementById('payment_method').value;
            
            if (!shippingAddress) {{
                showNotification('Harap isi alamat pengiriman!', 'error');
                return;
            }}
            
            if (!shippingMethod) {{
                showNotification('Harap pilih metode pengiriman!', 'error');
                return;
            }}
            
            if (!paymentMethod) {{
                showNotification('Harap pilih metode pembayaran!', 'error');
                return;
            }}
            
            const formData = new FormData();
            formData.append('shipping_address', shippingAddress);
            formData.append('shipping_method', shippingMethod);
            formData.append('payment_method', paymentMethod);
            
            fetch('/process_checkout', {{
                method: 'POST',
                body: formData
            }})
            .then(response => response.json())
            .then(data => {{
                if (data.success) {{
                    showPaymentModal(data.order_number, data.payment_method, data.total_amount);
                }} else {{
                    showNotification('❌ ' + data.message, 'error');
                }}
            }});
        }}

        function showPaymentModal(orderNumber, paymentMethod, totalAmount) {{
            const paymentInstructions = {{
                'bri': `
                    <h4 style="margin-bottom: 1rem; color: var(--primary);"><i class="fas fa-university"></i> Transfer Bank BRI</h4>
                    <div style="background: white; padding: 1rem; border-radius: var(--border-radius); border-left: 4px solid var(--primary);">
                        <p style="margin: 0.5rem 0;"><strong>No. Rekening:</strong> 1234567890</p>
                        <p style="margin: 0.5rem 0;"><strong>Atas Nama:</strong> Kang-Mas Shop</p>
                        <p style="margin: 0.5rem 0;"><strong>Total:</strong> <span style="color: var(--success); font-weight: bold;">Rp ${{totalAmount.toLocaleString()}}</span></p>
                    </div>
                `,
                'bca': `
                    <h4 style="margin-bottom: 1rem; color: var(--primary);"><i class="fas fa-university"></i> Transfer Bank BCA</h4>
                    <div style="background: white; padding: 1rem; border-radius: var(--border-radius); border-left: 4px solid var(--primary);">
                        <p style="margin: 0.5rem 0;"><strong>No. Rekening:</strong> 0987654321</p>
                        <p style="margin: 0.5rem 0;"><strong>Atas Nama:</strong> Kang-Mas Shop</p>
                        <p style="margin: 0.5rem 0;"><strong>Total:</strong> <span style="color: var(--success); font-weight: bold;">Rp ${{totalAmount.toLocaleString()}}</span></p>
                    </div>
                `,
                'mandiri': `
                    <h4 style="margin-bottom: 1rem; color: var(--primary);"><i class="fas fa-university"></i> Transfer Bank Mandiri</h4>
                    <div style="background: white; padding: 1rem; border-radius: var(--border-radius); border-left: 4px solid var(--primary);">
                        <p style="margin: 0.5rem 0;"><strong>No. Rekening:</strong> 1122334455</p>
                        <p style="margin: 0.5rem 0;"><strong>Atas Nama:</strong> Kang-Mas Shop</p>
                        <p style="margin: 0.5rem 0;"><strong>Total:</strong> <span style="color: var(--success); font-weight: bold;">Rp ${{totalAmount.toLocaleString()}}</span></p>
                    </div>
                `,
                'qris': `
                    <h4 style="margin-bottom: 1rem; color: var(--primary);"><i class="fas fa-qrcode"></i> QRIS</h4>
                    <div style="text-align: center; margin: 1rem 0;">
                        <div style="background: white; padding: 1.5rem; border-radius: var(--border-radius); display: inline-block;">
                            <div style="width: 200px; height: 200px; background: linear-gradient(45deg, var(--primary), var(--ocean-deep)); border-radius: var(--border-radius); display: flex; align-items: center; justify-content: center; color: white; font-size: 3rem;">
                                <i class="fas fa-qrcode"></i>
                            </div>
                        </div>
                    </div>
                    <p style="text-align: center; color: var(--success); font-weight: bold; font-size: 1.1rem;">Total: Rp ${{totalAmount.toLocaleString()}}</p>
                `,
                'gopay': `
                    <h4 style="margin-bottom: 1rem; color: var(--primary);"><i class="fas fa-mobile-alt"></i> Gopay</h4>
                    <div style="background: white; padding: 1rem; border-radius: var(--border-radius); border-left: 4px solid #00AA13;">
                        <p style="margin: 0.5rem 0;"><strong>No. HP:</strong> +6289654733875</p>
                        <p style="margin: 0.5rem 0;"><strong>Atas Nama:</strong> Kang-Mas Shop</p>
                        <p style="margin: 0.5rem 0;"><strong>Total:</strong> <span style="color: var(--success); font-weight: bold;">Rp ${{totalAmount.toLocaleString()}}</span></p>
                    </div>
                `,
                'dana': `
                    <h4 style="margin-bottom: 1rem; color: var(--primary);"><i class="fas fa-wallet"></i> Dana</h4>
                    <div style="background: white; padding: 1rem; border-radius: var(--border-radius); border-left: 4px solid #00B2FF;">
                        <p style="margin: 0.5rem 0;"><strong>No. HP:</strong> +6289654733875</p>
                        <p style="margin: 0.5rem 0;"><strong>Atas Nama:</strong> Kang-Mas Shop</p>
                        <p style="margin: 0.5rem 0;"><strong>Total:</strong> <span style="color: var(--success); font-weight: bold;">Rp ${{totalAmount.toLocaleString()}}</span></p>
                    </div>
                `,
                'cod': `
                    <h4 style="margin-bottom: 1rem; color: var(--primary);"><i class="fas fa-money-bill-wave"></i> Cash on Delivery</h4>
                    <div style="background: white; padding: 1rem; border-radius: var(--border-radius); border-left: 4px solid var(--success);">
                        <p style="margin: 0.5rem 0;">Bayar ketika pesanan diterima</p>
                        <p style="margin: 0.5rem 0;"><strong>Total:</strong> <span style="color: var(--success); font-weight: bold;">Rp ${{totalAmount.toLocaleString()}}</span></p>
                    </div>
                `
            }};

            document.getElementById('paymentInstructions').innerHTML = paymentInstructions[paymentMethod] || '<p>Silakan selesaikan pembayaran</p>';
            document.getElementById('paymentModal').style.display = 'block';
            window.currentOrderNumber = orderNumber;
            window.currentPaymentMethod = paymentMethod;
            window.currentTotalAmount = totalAmount;
        }}

        function showSuccessModal() {{
            closeModal('paymentModal');
            document.getElementById('successModal').style.display = 'block';
            confirmPayment();
        }}

        function closeModal(modalId) {{
            document.getElementById(modalId).style.display = 'none';
        }}

        function contactSeller() {{
            const orderNumber = window.currentOrderNumber;
            const totalAmount = window.currentTotalAmount;
            
            const message = `Hai Kak, saya telah melakukan pembayaran untuk:

🛍️ Order #: ${{orderNumber}}
💰 Total: Rp ${{totalAmount.toLocaleString()}}

Mohon konfirmasi pembayaran saya ya. Terima kasih! 😊`;
            
            const phone = '+6285876127696';
            const url = 'https://wa.me/' + phone + '?text=' + encodeURIComponent(message);
            window.open(url, '_blank');
            
            // Konfirmasi pembayaran di sistem
            confirmPayment();
            
            // Tutup modal
            closeModal('paymentModal');
            closeModal('successModal');
            
            showNotification('✅ Pembayaran dikonfirmasi! Pesanan sedang diproses.', 'success');
            
            setTimeout(() => {{
                window.location.href = '/orders';
            }}, 2000);
        }}

        function confirmPayment() {{
            fetch('/confirm_payment/' + window.currentOrderNumber, {{
                method: 'POST'
            }})
            .then(response => response.json())
            .then(data => {{
                if (data.success) {{
                    console.log('Payment confirmed successfully');
                }}
            }});
        }}
        
        function updateCartCount() {{
            fetch('/api/cart/count')
                .then(response => response.json())
                .then(data => {{
                    const cartBadge = document.getElementById('cart-count');
                    const cartFab = document.getElementById('cart-count-fab');
                    
                    if (cartBadge) {{
                        cartBadge.textContent = data.count;
                        cartBadge.style.display = data.count > 0 ? 'flex' : 'none';
                    }}
                    
                    if (cartFab) {{
                        cartFab.textContent = data.count;
                        cartFab.style.display = data.count > 0 ? 'flex' : 'none';
                    }}
                }});
        }}
        
        function updateTracking(orderId, status) {{
            fetch('/update_tracking/' + orderId, {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                }},
                body: JSON.stringify({{
                    status: status,
                    tracking_info: document.getElementById('tracking-info-' + orderId).value
                }})
            }})
            .then(response => response.json())
            .then(data => {{
                if (data.success) {{
                    showNotification('✅ Status pengiriman diperbarui!', 'success');
                    setTimeout(() => location.reload(), 1000);
                }} else {{
                    showNotification('❌ ' + data.message, 'error');
                }}
            }});
        }}
        
        function loadTransactionTemplate() {{
            const templateKey = document.getElementById('transaction_template').value;
            if (!templateKey) return;
            
            fetch('/api/get_transaction_template/' + templateKey)
                .then(response => response.json())
                .then(data => {{
                    if (data.success) {{
                        const formContainer = document.getElementById('templateFormContainer');
                        formContainer.innerHTML = data.form_html;
                    }} else {{
                        showNotification('❌ ' + data.message, 'error');
                    }}
                }});
        }}
        
        function submitTemplateJournal() {{
            const formData = new FormData(document.getElementById('templateJournalForm'));
            const data = {{
                template_key: formData.get('template_key'),
                date: formData.get('date'),
                amounts: {{}}
            }};
            
            // Collect amounts from form
            document.querySelectorAll('[id^="amount_"]').forEach(input => {{
                const accountType = input.id.replace('amount_', '');
                data.amounts[accountType] = parseFloat(input.value) || 0;
            }});
            
            fetch('/seller/add_template_journal', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                }},
                body: JSON.stringify(data)
            }})
            .then(response => response.json())
            .then(data => {{
                if (data.success) {{
                    showNotification('✅ ' + data.message, 'success');
                    setTimeout(() => location.reload(), 1000);
                }} else {{
                    showNotification('❌ ' + data.message, 'error');
                }}
            }});
        }}
        
        // Initialize when DOM is loaded
        document.addEventListener('DOMContentLoaded', function() {{
            updateCartCount();
            
            // Activate first tab by default
            const firstTab = document.querySelector('.tab');
            const firstTabContent = document.querySelector('.tab-content');
            if (firstTab && firstTabContent) {{
                firstTab.classList.add('active');
                firstTabContent.classList.add('active');
            }}
            
            // Auto-hide flash messages after 5 seconds
            setTimeout(() => {{
                const flashMessages = document.querySelector('.flash-messages');
                if (flashMessages) {{
                    flashMessages.style.display = 'none';
                }}
            }}, 5000);

            // Close modal when clicking outside
            window.onclick = function(event) {{
                const modals = document.getElementsByClassName('modal');
                for (let modal of modals) {{
                    if (event.target == modal) {{
                        modal.style.display = 'none';
                    }}
                }}
            }}
            
            // Add smooth scrolling
            document.querySelectorAll('a[href^="#"]').forEach(anchor => {{
                anchor.addEventListener('click', function (e) {{
                    e.preventDefault();
                    document.querySelector(this.getAttribute('href')).scrollIntoView({{
                        behavior: 'smooth'
                    }});
                }});
            }});
        }});
    </script>
    {additional_js}
</body>
</html>
'''

def get_navigation():
    if current_user.is_authenticated:
        user_badge = f"""
            <div class="user-menu">
                <div class="avatar">{current_user.avatar}</div>
                <div>
                    <div style="font-weight: 600; font-size: 0.95rem;">{current_user.full_name}</div>
                    <div class="badge">
                        {current_user.user_type.upper()}
                    </div>
                </div>
            </div>
        """
        
        nav_links = []
        
        if current_user.user_type == 'customer':
            nav_links.extend([
                '<a href="/products" class="nav-link"><i class="fas fa-store"></i> Produk</a>',
                f'<a href="/cart" class="nav-link"><i class="fas fa-shopping-cart"></i> Keranjang <span id="cart-count" style="background: var(--error); color: white; border-radius: 50%; width: 20px; height: 20px; display: none; align-items: center; justify-content: center; font-size: 0.8rem; margin-left: 5px;">0</span></a>',
                '<a href="/orders" class="nav-link"><i class="fas fa-box"></i> Pesanan Saya</a>',
                '<a href="/profile" class="nav-link"><i class="fas fa-user"></i> Profile</a>'
            ])
        else:  # seller
            nav_links.extend([
                '<a href="/seller/dashboard" class="nav-link"><i class="fas fa-chart-line"></i> Dashboard</a>',
                '<a href="/seller/orders" class="nav-link"><i class="fas fa-boxes"></i> Pesanan</a>',
                '<a href="/seller/accounting" class="nav-link"><i class="fas fa-chart-bar"></i> Akuntansi</a>',
                '<a href="/seller/products" class="nav-link"><i class="fas fa-fish"></i> Produk</a>'
            ])
        
        nav_links.append('<a href="/logout" class="nav-link"><i class="fas fa-sign-out-alt"></i> Logout</a>')
        
        return user_badge + ''.join(nav_links)
    else:
        return '''
            <a href="/login" class="nav-link"><i class="fas fa-sign-in-alt"></i> Login</a>
            <a href="/register" class="nav-link"><i class="fas fa-user-plus"></i> Register</a>
        '''

def get_flash_messages():
    messages = ""
    for category, message in get_flashed_messages(with_categories=True):
        messages += f'<div class="flash-message flash-{category}">{message}</div>'
    return messages

def get_account_options():
    accounts = Account.query.all()
    options = ""
    for account in accounts:
        options += f'<option value="{account.id}">{account.code} - {account.name}</option>'
    return options

def get_trial_balance():
    try:
        accounts = Account.query.all()
        trial_balance_html = ""
        total_debit = total_credit = 0
        
        for account in accounts:
            if account.balance >= 0:
                debit = account.balance
                credit = 0
            else:
                debit = 0
                credit = abs(account.balance)
            
            total_debit += debit
            total_credit += credit
            
            trial_balance_html += f'''
            <tr>
                <td>{account.code}</td>
                <td>{account.name}</td>
                <td class="debit">{"Rp {0:,.0f}".format(debit) if debit > 0 else ""}</td>
                <td class="credit">{"Rp {0:,.0f}".format(credit) if credit > 0 else ""}</td>
            </tr>
            '''
        
        # Add total row
        trial_balance_html += f'''
        <tr style="font-weight: bold; border-top: 2px solid var(--primary);">
            <td colspan="2">TOTAL</td>
            <td class="debit">Rp {total_debit:,.0f}</td>
            <td class="credit">Rp {total_credit:,.0f}</td>
        </tr>
        '''
        
        return trial_balance_html
    except:
        return '<tr><td colspan="4">Error loading trial balance</td></tr>'

def get_journal_entries_table():
    """Generate single table for all journal entries"""
    try:
        # Get all journal entries ordered by date
        journal_entries = JournalEntry.query.order_by(JournalEntry.date).all()
        
        if not journal_entries:
            return '''
            <div class="card">
                <h4 style="color: var(--primary);">Belum Ada Transaksi</h4>
                <p>Gunakan form Input Jurnal Otomatis di atas untuk menambahkan transaksi pertama.</p>
            </div>
            '''
        
        table_html = '''
        <div class="card">
            <h4 style="color: var(--primary); margin-bottom: 1.5rem;"><i class="fas fa-list"></i> Daftar Semua Jurnal</h4>
            <div style="overflow-x: auto;">
                <table class="table">
                    <thead>
                        <tr>
                            <th>Tanggal</th>
                            <th>No. Transaksi</th>
                            <th>Keterangan</th>
                            <th>Akun</th>
                            <th>Debit</th>
                            <th>Kredit</th>
                        </tr>
                    </thead>
                    <tbody>
        '''
        
        for journal in journal_entries:
            # Add transaction header
            table_html += f'''
            <tr style="background: rgba(49, 130, 206, 0.05);">
                <td><strong>{journal.date.strftime('%d/%m/%Y')}</strong></td>
                <td><strong>{journal.transaction_number}</strong></td>
                <td colspan="4"><strong>{journal.description}</strong></td>
            </tr>
            '''
            
            # Add account details
            for detail in journal.journal_details:
                table_html += f'''
                <tr>
                    <td></td>
                    <td></td>
                    <td></td>
                    <td>{detail.account.code} - {detail.account.name}</td>
                    <td class="debit">{"Rp {0:,.0f}".format(detail.debit) if detail.debit > 0 else ""}</td>
                    <td class="credit">{"Rp {0:,.0f}".format(detail.credit) if detail.credit > 0 else ""}</td>
                </tr>
                '''
        
        table_html += '''
                    </tbody>
                </table>
            </div>
        </div>
        '''
        
        return table_html
    except Exception as e:
        print(f"Error generating journal table: {e}")
        return '<div class="card"><p>Error loading journal entries</p></div>'

def get_income_statement():
    """Generate income statement HTML"""
    try:
        # Get revenue accounts
        revenue_accounts = Account.query.filter_by(category='revenue').all()
        total_revenue = sum(acc.balance for acc in revenue_accounts)
        
        # Get expense accounts
        expense_accounts = Account.query.filter_by(category='expense').all()
        total_expenses = sum(acc.balance for acc in expense_accounts)
        
        net_income = total_revenue - total_expenses
        
        revenue_html = ""
        for acc in revenue_accounts:
            if acc.balance > 0:
                revenue_html += f'''
                <tr>
                    <td>{acc.name}</td>
                    <td class="debit">Rp {acc.balance:,.0f}</td>
                </tr>
                '''
        
        expense_html = ""
        for acc in expense_accounts:
            if acc.balance > 0:
                expense_html += f'''
                <tr>
                    <td>{acc.name}</td>
                    <td class="credit">Rp {acc.balance:,.0f}</td>
                </tr>
                '''
        
        return f'''
        <table class="table">
            <thead>
                <tr>
                    <th>Pendapatan</th>
                    <th>Jumlah</th>
                </tr>
            </thead>
            <tbody>
                {revenue_html}
                <tr style="font-weight: bold; border-top: 2px solid var(--primary);">
                    <td>Total Pendapatan</td>
                    <td class="debit">Rp {total_revenue:,.0f}</td>
                </tr>
            </tbody>
        </table>
        
        <table class="table" style="margin-top: 2rem;">
            <thead>
                <tr>
                    <th>Beban</th>
                    <th>Jumlah</th>
                </tr>
            </thead>
            <tbody>
                {expense_html}
                <tr style="font-weight: bold; border-top: 2px solid var(--primary);">
                    <td>Total Beban</td>
                    <td class="credit">Rp {total_expenses:,.0f}</td>
                </tr>
            </tbody>
        </table>
        
        <div style="margin-top: 2rem; padding: 1.5rem; background: {'rgba(56, 161, 105, 0.1)' if net_income >= 0 else 'rgba(229, 62, 62, 0.1)'}; border-radius: var(--border-radius);">
            <h4 style="color: {'var(--success)' if net_income >= 0 else 'var(--error)'};">
                {'Laba Bersih' if net_income >= 0 else 'Rugi Bersih'}: 
                <span style="{'debit' if net_income >= 0 else 'credit'}">Rp {abs(net_income):,.0f}</span>
            </h4>
        </div>
        '''
    except Exception as e:
        print(f"Error generating income statement: {e}")
        return '<p>Error loading income statement</p>'

# ===== ROUTES UTAMA =====
@app.route('/')
def index():
    if not current_user.is_authenticated:
        return redirect('/login')
    
    try:
        settings = {s.key: s.value for s in AppSetting.query.all()}
        featured_products = Product.query.filter_by(is_featured=True).limit(3).all()
        
        featured_html = ""
        for product in featured_products:
            weight_info = f"{product.weight_kg}kg" if product.weight_kg else f"{product.size_cm}cm"
            add_to_cart_btn = ''
            if current_user.user_type == 'customer':
                add_to_cart_btn = f'''
                <button class="btn btn-primary" onclick="addToCart({product.id})" style="margin-top: 1rem;">
                    <i class="fas fa-cart-plus"></i> Tambah ke Keranjang
                </button>
                '''
            
            featured_html += f'''
                <div class="card product-card">
                    <img src="{product.image_url}" alt="{product.name}" class="product-image" onerror="this.style.display='none'">
                    <h3 style="margin-bottom: 0.5rem; color: var(--dark);">{product.name}</h3>
                    <p style="color: #6B7280; margin-bottom: 1rem;">{product.description}</p>
                    <div class="price" style="margin-bottom: 0.5rem;">Rp {product.price:,.0f}</div>
                    <p style="color: #6B7280; font-size: 0.9rem;">Stock: {product.stock} | {weight_info}</p>
                    {add_to_cart_btn}
                </div>
            '''
        
        content = f'''
        <div class="hero">
            <h1>{settings.get('app_name', 'Kang-Mas Shop')}</h1>
            <p>{settings.get('app_description', 'Sejak 2017 - Melayani dengan Kualitas Terbaik')}</p>
            <p><em>Ikan mas segar langsung dari kolam Magelang</em></p>
            
            <div style="margin-top: 2rem;">
                <p style="font-size: 1.2rem;">
                    Selamat datang kembali, <strong>{current_user.full_name}</strong>!
                </p>
                {current_user.user_type == 'customer' and '''
                <a href="/products" class="btn btn-primary" style="margin-top: 1rem;">
                    <i class="fas fa-store"></i> Lihat Semua Produk
                </a>
                ''' or '''
                <a href="/seller/dashboard" class="btn btn-primary" style="margin-top: 1rem;">
                    <i class="fas fa-chart-line"></i> Seller Dashboard
                </a>
                '''}
            </div>
        </div>

        <h2 style="margin-bottom: 2rem; text-align: center; color: var(--primary);">
            <i class="fas fa-star"></i> Produk Unggulan
        </h2>
        <div class="grid grid-3">
            {featured_html}
        </div>

        <div class="stats">
            <div class="stat-card">
                <div class="stat-number">7+</div>
                <div class="stat-label">Tahun Pengalaman</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">1000+</div>
                <div class="stat-label">Pelanggan Puas</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">100%</div>
                <div class="stat-label">Ikan Segar</div>
            </div>
        </div>
        '''
        
        return base_html('Home', content)
    except Exception as e:
        print(f"Error in index route: {e}")
        return base_html('Home', '<div class="card"><h2>Welcome to Kang-Mas Shop</h2><p>Error loading content. Please try again.</p></div>')

# ===== ROUTES AUTH =====
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect('/')
    
    if request.method == 'POST':
        email = request.form.get('email')
        full_name = request.form.get('full_name')
        password = request.form.get('password')
        phone = request.form.get('phone')
        address = request.form.get('address')
        
        if User.query.filter_by(email=email).first():
            flash('Email sudah terdaftar!', 'error')
        else:
            user = User(
                email=email,
                full_name=full_name,
                user_type='customer',
                phone=phone,
                address=address
            )
            user.set_password(password)
            
            verification_code = user.generate_verification_code()
            db.session.add(user)
            db.session.commit()
            
            if send_verification_email(email, verification_code):
                session['pending_verification'] = user.id
                flash('Kode verifikasi telah dikirim ke email Anda!', 'success')
                return redirect('/verify_email')
            else:
                db.session.delete(user)
                db.session.commit()
                flash('Gagal mengirim email verifikasi. Silakan coba lagi.', 'error')
    
    content = '''
    <div style="max-width: 500px; margin: 0 auto;">
        <div class="card">
            <div style="text-align: center; margin-bottom: 2rem;">
                <div style="width: 80px; height: 80px; background: linear-gradient(135deg, var(--primary) 0%, var(--ocean-deep) 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1rem;">
                    <i class="fas fa-user-plus" style="color: white; font-size: 2rem;"></i>
                </div>
                <h2 style="color: var(--primary);">Daftar Akun Baru</h2>
            </div>
            
            <form method="POST">
                <div class="form-group">
                    <label class="form-label"><i class="fas fa-envelope"></i> Email</label>
                    <input type="email" name="email" class="form-control" required>
                </div>
                <div class="form-group">
                    <label class="form-label"><i class="fas fa-user"></i> Nama Lengkap</label>
                    <input type="text" name="full_name" class="form-control" required>
                </div>
                <div class="form-group">
                    <label class="form-label"><i class="fas fa-lock"></i> Password</label>
                    <input type="password" name="password" class="form-control" required>
                </div>
                <div class="form-group">
                    <label class="form-label"><i class="fas fa-phone"></i> No. Telepon</label>
                    <input type="text" name="phone" class="form-control" required>
                </div>
                <div class="form-group">
                    <label class="form-label"><i class="fas fa-map-marker-alt"></i> Alamat</label>
                    <textarea name="address" class="form-control" required></textarea>
                </div>
                <button type="submit" class="btn btn-primary" style="width: 100%;">
                    <i class="fas fa-user-plus"></i> Daftar dengan Email
                </button>
            </form>
            
            <div class="divider">
                <span>atau</span>
            </div>
            
            <div style="text-align: center;">
                <a href="/google-login" class="btn google-btn">
                    <img src="https://developers.google.com/identity/images/g-logo.png" 
                         style="width: 20px; height: 20px; margin-right: 10px; background: white; padding: 2px; border-radius: 2px;">
                    Daftar dengan Google
                </a>
            </div>
            
            <p style="text-align: center; margin-top: 1rem;">
                Sudah punya akun? <a href="/login" style="color: var(--primary); text-decoration: none; font-weight: 600;">Login di sini</a>
            </p>
        </div>
    </div>
    '''
    return base_html('Register', content)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect('/')
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            if not user.email_verified and not user.google_id:
                flash('Email belum diverifikasi! Silakan cek email Anda.', 'warning')
                return redirect('/verify_email')
            
            login_user(user, remember=True)
            flash(f'Berhasil login! Selamat datang {user.full_name}', 'success')
            return redirect('/')
        else:
            flash('Email atau password salah!', 'error')
    
    settings = {s.key: s.value for s in AppSetting.query.all()}
    app_logo = settings.get('app_logo', '/static/uploads/logos/logo.png')
    
    content = f'''
    <div style="max-width: 400px; margin: 0 auto;">
        <div class="card">
            <div style="display: flex; align-items: center; gap: 1rem; margin-bottom: 2rem;">
                <img src="{app_logo}" alt="Kang-Mas Shop" style="width: 50px; height: 50px; border-radius: 12px; box-shadow: var(--shadow-md);" onerror="this.style.display='none'">
                <h2 style="margin: 0; color: var(--primary);">Masuk ke Akun</h2>
            </div>
            
            <form method="POST">
                <div class="form-group">
                    <label class="form-label"><i class="fas fa-envelope"></i> Email</label>
                    <input type="email" name="email" class="form-control" required>
                </div>
                <div class="form-group">
                    <label class="form-label"><i class="fas fa-lock"></i> Password</label>
                    <input type="password" name="password" class="form-control" required>
                </div>
                <button type="submit" class="btn btn-primary" style="width: 100%;">
                    <i class="fas fa-sign-in-alt"></i> Login
                </button>
            </form>
            
            <div class="divider">
                <span>atau</span>
            </div>
            
            <div style="text-align: center;">
                <a href="/google-login" class="btn google-btn">
                    <img src="https://developers.google.com/identity/images/g-logo.png" 
                         style="width: 20px; height: 20px; margin-right: 10px; background: white; padding: 2px; border-radius: 2px;">
                    Login dengan Google
                </a>
            </div>
            
            <div style="margin-top: 1rem; padding: 1rem; background: rgba(49, 130, 206, 0.1); border-radius: var(--border-radius);">
                <h4 style="margin-bottom: 0.5rem; color: var(--primary);"><i class="fas fa-info-circle"></i> Demo Accounts:</h4>
                <p style="margin: 0.25rem 0; font-size: 0.9rem;"><strong>Customer:</strong> customer@example.com / customer123</p>
                <p style="margin: 0.25rem 0; font-size: 0.9rem;"><strong>Seller:</strong> kang.mas1817@gmail.com / TugasSiaKangMas</p>
            </div>
            
            <p style="text-align: center; margin-top: 1rem;">
                Belum punya akun? <a href="/register" style="color: var(--primary); text-decoration: none; font-weight: 600;">Daftar sebagai Customer</a>
            </p>
        </div>
    </div>
    '''
    return base_html('Login', content)

@app.route('/verify_email', methods=['GET', 'POST'])
def verify_email():
    user_id = session.get('pending_verification')
    if not user_id:
        return redirect('/register')
    
    user = User.query.get(user_id)
    if not user:
        return redirect('/register')
    
    if request.method == 'POST':
        verification_code = request.form.get('verification_code')
        
        if user.verification_code == verification_code:
            user.email_verified = True
            user.verification_code = None
            db.session.commit()
            session.pop('pending_verification', None)
            
            login_user(user)
            flash('Email berhasil diverifikasi! Selamat datang.', 'success')
            return redirect('/')
        else:
            flash('Kode verifikasi salah! Silakan coba lagi.', 'error')
    
    content = f'''
    <div style="max-width: 400px; margin: 0 auto;">
        <div class="card">
            <h2 style="color: var(--primary);"><i class="fas fa-envelope"></i> Verifikasi Email</h2>
            <p>Kami telah mengirim kode verifikasi ke <strong>{user.email}</strong></p>
            <form method="POST">
                <div class="form-group">
                    <label class="form-label">Kode Verifikasi (6 digit)</label>
                    <input type="text" name="verification_code" class="form-control" maxlength="6" required>
                </div>
                <button type="submit" class="btn btn-primary" style="width: 100%;">Verifikasi</button>
            </form>
            <p style="text-align: center; margin-top: 1rem;">
                Tidak menerima kode? <a href="/resend_verification">Kirim ulang</a>
            </p>
        </div>
    </div>
    '''
    return base_html('Verifikasi Email', content)

@app.route('/resend_verification')
def resend_verification():
    user_id = session.get('pending_verification')
    if user_id:
        user = User.query.get(user_id)
        if user:
            verification_code = user.generate_verification_code()
            db.session.commit()
            
            if send_verification_email(user.email, verification_code):
                flash('Kode verifikasi baru telah dikirim!', 'success')
            else:
                flash('Gagal mengirim email verifikasi. Silakan coba lagi.', 'error')
    
    return redirect('/verify_email')

@app.route('/logout')
def logout():
    logout_user()
    return redirect('/login')

# ===== ROUTES CUSTOMER =====
@app.route('/profile')
@login_required
def profile():
    try:
        if current_user.user_type == 'customer':
            total_orders = Order.query.filter_by(customer_id=current_user.id).count()
            total_spent_result = db.session.query(db.func.sum(Order.total_amount)).filter_by(customer_id=current_user.id).scalar()
            total_spent = total_spent_result if total_spent_result else 0
        else:
            total_orders = 0
            total_spent = 0
        
        content = f'''
        <div class="card">
            <h2 style="color: var(--primary);"><i class="fas fa-user"></i> Profile {current_user.user_type.title()}</h2>
            <div class="grid grid-2">
                <div>
                    <h4>Informasi Pribadi</h4>
                    <p><strong>Nama:</strong> {current_user.full_name}</p>
                    <p><strong>Email:</strong> {current_user.email}</p>
                    <p><strong>Alamat:</strong> {current_user.address or '-'}</p>
                    <p><strong>Tipe Akun:</strong> <span class="badge">{current_user.user_type.upper()}</span></p>
                </div>
                <div>
                    <h4>Statistik</h4>
                    {current_user.user_type == 'customer' and f'''
                    <p><strong>Total Order:</strong> {total_orders}</p>
                    <p><strong>Total Belanja:</strong> Rp {total_spent:,.0f}</p>
                    ''' or '''
                    <p><strong>Role:</strong> Penjual/Pemilik Toko</p>
                    <p><strong>Akses:</strong> Manajemen Penuh</p>
                    '''}
                    <p><strong>Member sejak:</strong> {current_user.created_at.strftime('%d/%m/%Y')}</p>
                    <p><strong>Status Verifikasi:</strong> {'✅ Terverifikasi' if current_user.email_verified else '❌ Belum diverifikasi'}</p>
                </div>
            </div>
        </div>
        '''
        return base_html('Profile', content)
    except Exception as e:
        print(f"Error in profile route: {e}")
        flash('Terjadi error saat memuat profile.', 'error')
        return redirect('/')

@app.route('/products')
@login_required
def products():
    try:
        products_list = Product.query.filter_by(is_active=True).all()
        
        products_html = ""
        for product in products_list:
            weight_info = f"{product.weight_kg}kg" if product.weight_kg else f"{product.size_cm}cm"
            add_to_cart_btn = ''
            if current_user.user_type == 'customer':
                add_to_cart_btn = f'''
                <button class="btn btn-primary" onclick="addToCart({product.id})" style="margin-top: 1rem;">
                    <i class="fas fa-cart-plus"></i> Tambah ke Keranjang
                </button>
                '''
            
            products_html += f'''
            <div class="card">
                <img src="{product.image_url}" alt="{product.name}" class="product-image" onerror="this.style.display='none'">
                <h3>{product.name}</h3>
                <p>{product.description}</p>
                <div class="price">Rp {product.price:,.0f}</div>
                <p>Stock: {product.stock} | {weight_info}</p>
                {add_to_cart_btn}
            </div>
            '''
        
        content = f'''
        <h1 style="color: var(--primary);"><i class="fas fa-store"></i> Semua Produk</h1>
        <div class="grid grid-3">
            {products_html}
        </div>
        '''
        return base_html('Produk', content)
    except Exception as e:
        print(f"Error in products route: {e}")
        flash('Terjadi error saat memuat produk.', 'error')
        return redirect('/')

@app.route('/cart')
@login_required
def cart():
    try:
        # Hanya customer yang bisa akses cart
        if current_user.user_type != 'customer':
            flash('Hanya customer yang bisa mengakses keranjang belanja.', 'error')
            return redirect('/')
        
        cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
        
        if not cart_items:
            content = '''
            <div class="card">
                <h2 style="color: var(--primary);"><i class="fas fa-shopping-cart"></i> Keranjang Belanja</h2>
                <p>Keranjang belanja Anda kosong.</p>
                <a href="/products" class="btn btn-primary">Belanja Sekarang</a>
            </div>
            '''
        else:
            cart_html = ""
            total = 0
            
            for item in cart_items:
                product = Product.query.get(item.product_id)
                if product:  # Pastikan product exists
                    subtotal = product.price * item.quantity
                    total += subtotal
                    
                    cart_html += f'''
                    <div class="card" style="display: flex; justify-content: space-between; align-items: center;">
                        <div style="flex: 1;">
                            <h4>{product.name}</h4>
                            <p>Rp {product.price:,.0f} x {item.quantity}</p>
                            <p>Subtotal: Rp {subtotal:,.0f}</p>
                        </div>
                        <div>
                            <form action="/remove_from_cart/{item.id}" method="POST" style="display: inline;">
                                <button type="submit" class="btn btn-danger">Hapus</button>
                            </form>
                        </div>
                    </div>
                    '''
            
            content = f'''
            <h1 style="color: var(--primary);"><i class="fas fa-shopping-cart"></i> Keranjang Belanja</h1>
            {cart_html}
            <div class="card">
                <h3>Total: Rp {total:,.0f}</h3>
                <button class="btn btn-success" onclick="checkout()">
                    <i class="fas fa-credit-card"></i> Checkout Sekarang
                </button>
            </div>
            '''
        
        return base_html('Keranjang', content)
    except Exception as e:
        print(f"Error in cart route: {e}")
        flash('Terjadi error saat memuat keranjang.', 'error')
        return redirect('/')

@app.route('/remove_from_cart/<int:cart_item_id>', methods=['POST'])
@login_required
def remove_from_cart(cart_item_id):
    try:
        if current_user.user_type != 'customer':
            flash('Akses ditolak.', 'error')
            return redirect('/')
        
        cart_item = CartItem.query.get(cart_item_id)
        if cart_item and cart_item.user_id == current_user.id:
            db.session.delete(cart_item)
            db.session.commit()
            flash('Produk dihapus dari keranjang', 'success')
        return redirect('/cart')
    except Exception as e:
        print(f"Error removing from cart: {e}")
        flash('Terjadi error saat menghapus dari keranjang.', 'error')
        return redirect('/cart')

@app.route('/checkout')
@login_required
def checkout_page():
    try:
        if current_user.user_type != 'customer':
            flash('Hanya customer yang bisa checkout.', 'error')
            return redirect('/')
        
        cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
        
        if not cart_items:
            flash('Keranjang belanja Anda kosong', 'error')
            return redirect('/cart')
        
        total = 0
        for item in cart_items:
            product = Product.query.get(item.product_id)
            if product:
                total += product.price * item.quantity
        
        content = f'''
        <div style="max-width: 600px; margin: 0 auto;">
            <div class="card">
                <h2 style="color: var(--primary);"><i class="fas fa-credit-card"></i> Checkout</h2>
                
                <div class="form-group">
                    <label class="form-label">Alamat Pengiriman</label>
                    <textarea id="shipping_address" class="form-control" required placeholder="Masukkan alamat lengkap pengiriman">{current_user.address or ''}</textarea>
                </div>
                
                <div class="form-group">
                    <label class="form-label">Metode Pengiriman</label>
                    <select id="shipping_method" class="form-control" required>
                        <option value="">Pilih metode pengiriman</option>
                        <option value="jne">JNE Reguler - Rp 15,000</option>
                        <option value="jnt">JNT Express - Rp 12,000</option>
                        <option value="pos">POS Indonesia - Rp 10,000</option>
                        <option value="grab">Grab Express - Rp 20,000</option>
                    </select>
                </div>
                
                <div class="form-group">
                    <label class="form-label">Metode Pembayaran</label>
                    <select id="payment_method" class="form-control" required>
                        <option value="">Pilih metode pembayaran</option>
                        <option value="bri">BRI (123456)</option>
                        <option value="bca">BCA (789012)</option>
                        <option value="mandiri">Mandiri (345678)</option>
                        <option value="qris">QRIS</option>
                        <option value="gopay">Gopay +6289654733875</option>
                        <option value="dana">Dana +6289654733875</option>
                        <option value="cod">Cash on Delivery (COD)</option>
                    </select>
                </div>
                
                <div class="card" style="background: var(--ocean-light);">
                    <h4>Ringkasan Pesanan</h4>
                    <p><strong>Total Belanja:</strong> Rp {total:,.0f}</p>
                    <p><strong>Ongkos Kirim:</strong> Rp 15,000</p>
                    <p><strong>Total Pembayaran:</strong> Rp {total + 15000:,.0f}</p>
                </div>
                
                <button class="btn btn-success" style="width: 100%; margin-top: 1rem;" onclick="processCheckout()">
                    <i class="fas fa-credit-card"></i> Proses Pembayaran
                </button>
            </div>
        </div>
        '''
        return base_html('Checkout', content)
    except Exception as e:
        print(f"Error in checkout route: {e}")
        flash('Terjadi error saat memuat halaman checkout.', 'error')
        return redirect('/cart')

@app.route('/process_checkout', methods=['POST'])
@login_required
def process_checkout():
    try:
        if current_user.user_type != 'customer':
            return jsonify({'success': False, 'message': 'Akses ditolak'})
        
        cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
        
        if not cart_items:
            return jsonify({'success': False, 'message': 'Keranjang kosong'})
        
        shipping_address = request.form.get('shipping_address')
        shipping_method = request.form.get('shipping_method')
        payment_method = request.form.get('payment_method')
        
        if not shipping_address or not shipping_method or not payment_method:
            return jsonify({'success': False, 'message': 'Harap lengkapi semua data pengiriman dan pembayaran'})
        
        order_number = f"ORD{datetime.now().strftime('%Y%m%d%H%M%S')}"
        total_amount = 0
        
        # Cek stok sebelum checkout
        for cart_item in cart_items:
            product = Product.query.get(cart_item.product_id)
            if not product or product.stock < cart_item.quantity:
                product_name = product.name if product else 'Produk'
                return jsonify({'success': False, 'message': f'Stock {product_name} tidak mencukupi'})
        
        order = Order(
            order_number=order_number,
            customer_id=current_user.id,
            total_amount=0,
            shipping_address=shipping_address,
            shipping_method=shipping_method,
            payment_method=payment_method,
            payment_status='unpaid',  # Status awal belum bayar
            status='pending'
        )
        db.session.add(order)
        db.session.flush()
        
        # Kurangi stok dan buat order items
        for cart_item in cart_items:
            product = Product.query.get(cart_item.product_id)
            if product:
                product.stock -= cart_item.quantity  # Kurangi stok
                print(f"✅ Stok {product.name} berkurang {cart_item.quantity} menjadi {product.stock}")
                
                order_item = OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    quantity=cart_item.quantity,
                    price=product.price,
                    cost_price=product.cost_price
                )
                db.session.add(order_item)
                total_amount += product.price * cart_item.quantity
        
        # Tambahkan ongkos kirim
        shipping_cost = 15000
        total_amount += shipping_cost
        
        order.total_amount = total_amount
        db.session.commit()
        
        # Hapus cart items
        CartItem.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Checkout berhasil!', 
            'order_number': order_number,
            'payment_method': payment_method,
            'total_amount': total_amount
        })
    except Exception as e:
        print(f"Error processing checkout: {e}")
        return jsonify({'success': False, 'message': 'Terjadi error saat proses checkout'})

@app.route('/confirm_payment/<order_number>', methods=['POST'])
@login_required
def confirm_payment(order_number):
    try:
        order = Order.query.filter_by(order_number=order_number, customer_id=current_user.id).first_or_404()
        
        # Update status pembayaran dan order
        order.payment_status = 'paid'
        order.status = 'processing'  # Status berubah dari pending ke processing
        
        db.session.commit()
        
        flash('Pembayaran berhasil dikonfirmasi! Pesanan sedang diproses.', 'success')
        return jsonify({'success': True, 'message': 'Pembayaran berhasil dikonfirmasi'})
    except Exception as e:
        print(f"Error confirming payment: {e}")
        return jsonify({'success': False, 'message': 'Terjadi error saat konfirmasi pembayaran'})

@app.route('/orders')
@login_required
def orders():
    try:
        if current_user.user_type == 'customer':
            orders_list = Order.query.filter_by(customer_id=current_user.id).order_by(Order.order_date.desc()).all()
            title = 'Pesanan Saya'
        else:
            orders_list = Order.query.order_by(Order.order_date.desc()).all()
            title = 'Semua Pesanan'
        
        if not orders_list:
            content = f'''
            <div class="card">
                <h2 style="color: var(--primary);"><i class="fas fa-box"></i> {title}</h2>
                <p>Belum ada pesanan.</p>
                {current_user.user_type == 'customer' and '<a href="/products" class="btn btn-primary">Belanja Sekarang</a>' or ''}
            </div>
            '''
        else:
            orders_html = ""
            for order in orders_list:
                customer = User.query.get(order.customer_id) if current_user.user_type != 'customer' else current_user
                
                # Status dengan style text normal
                status_display = f"<span class='status-text status-{order.status}'>{order.status.upper()}</span>"
                payment_status_display = f"<span class='status-text status-{order.payment_status}'>{order.payment_status.upper()}</span>"
                
                customer_info = f"<p><strong>Customer:</strong> {customer.full_name}</p>" if current_user.user_type != 'customer' else ""
                
                orders_html += f'''
                <div class="card">
                    <h4>Order #{order.order_number}</h4>
                    {customer_info}
                    <p><strong>Total:</strong> Rp {order.total_amount:,.0f}</p>
                    <p><strong>Status:</strong> {status_display}</p>
                    <p><strong>Pembayaran:</strong> {payment_status_display}</p>
                    <p><strong>Metode:</strong> {order.payment_method} | <strong>Pengiriman:</strong> {order.shipping_method}</p>
                    <p><strong>Tanggal:</strong> {order.order_date.strftime('%d/%m/%Y %H:%M')}</p>
                    <p><strong>Alamat:</strong> {order.shipping_address}</p>
                    {order.tracking_info and f'<p><strong>Tracking:</strong> {order.tracking_info}</p>' or ''}
                    
                    {current_user.user_type == 'seller' and order.payment_status == 'unpaid' and '''
                    <div style="margin-top: 1rem; padding: 1rem; background: rgba(229, 62, 62, 0.1); border-radius: 8px;">
                        <p style="color: var(--error); margin: 0;">
                            <strong>⚠️ Menunggu Pembayaran:</strong> Pesanan belum dapat diproses karena pembayaran belum diterima.
                        </p>
                    </div>
                    ''' or ''}
                    
                    {current_user.user_type == 'seller' and order.payment_status == 'paid' and order.status == 'processing' and f'''
                    <form action="/seller/update_order_status/{order.id}" method="POST" style="margin-top: 1rem;">
                        <input type="hidden" name="status" value="completed">
                        <button type="submit" class="btn btn-success">Selesaikan Order</button>
                    </form>
                    ''' or ''}
                </div>
                '''
            
            content = f'''
            <h1 style="color: var(--primary);"><i class="fas fa-box"></i> {title}</h1>
            {orders_html}
            '''
        
        return base_html('Pesanan', content)
    except Exception as e:
        print(f"Error in orders route: {e}")
        flash('Terjadi error saat memuat pesanan.', 'error')
        return redirect('/')

# ===== ROUTES SELLER =====
@app.route('/seller/dashboard')
@login_required
@seller_required
def seller_dashboard():
    try:
        total_products = Product.query.filter_by(seller_id=current_user.id).count()
        total_orders = Order.query.count()
        total_sales_result = db.session.query(db.func.sum(Order.total_amount)).scalar()
        total_sales = total_sales_result if total_sales_result else 0
        total_customers = User.query.filter_by(user_type='customer').count()
        
        # Recent orders
        recent_orders = Order.query.order_by(Order.order_date.desc()).limit(5).all()
        recent_orders_html = ""
        for order in recent_orders:
            customer = User.query.get(order.customer_id)
            status_display = f"<span class='status-text status-{order.status}'>{order.status.upper()}</span>"
            recent_orders_html += f'''
            <div style="padding: 1rem; border-bottom: 1px solid rgba(0,0,0,0.1);">
                <div style="display: flex; justify-content: between; align-items: center;">
                    <div style="flex: 1;">
                        <strong>#{order.order_number}</strong>
                        <br><small>{customer.full_name if customer else 'Unknown'}</small>
                    </div>
                    <div>
                        {status_display}
                        <br><small>Rp {order.total_amount:,.0f}</small>
                    </div>
                </div>
            </div>
            '''
        
        content = f'''
        <h1 style="color: var(--primary);"><i class="fas fa-chart-line"></i> Seller Dashboard</h1>
        
        <div class="stats">
            <div class="stat-card">
                <div class="stat-number">{total_products}</div>
                <div class="stat-label">Total Produk</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{total_orders}</div>
                <div class="stat-label">Total Pesanan</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">Rp {total_sales:,.0f}</div>
                <div class="stat-label">Total Penjualan</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{total_customers}</div>
                <div class="stat-label">Total Customer</div>
            </div>
        </div>
        
        <div class="grid grid-2">
            <div class="card">
                <h3 style="color: var(--primary);"><i class="fas fa-bolt"></i> Quick Actions</h3>
                <div style="display: flex; flex-direction: column; gap: 1rem;">
                    <a href="/seller/orders" class="btn btn-primary"><i class="fas fa-boxes"></i> Kelola Pesanan</a>
                    <a href="/seller/accounting" class="btn btn-success"><i class="fas fa-chart-bar"></i> Lihat Akuntansi</a>
                    <a href="/seller/products" class="btn btn-info"><i class="fas fa-fish"></i> Kelola Produk</a>
                </div>
            </div>
            
            <div class="card">
                <h3 style="color: var(--primary);"><i class="fas fa-list"></i> Pesanan Terbaru</h3>
                <div style="max-height: 300px; overflow-y: auto;">
                    {recent_orders_html or '<p style="text-align: center; padding: 2rem;">Belum ada pesanan</p>'}
                </div>
            </div>
        </div>
        
        <div class="grid grid-2">
            <div class="card">
                <h3 style="color: var(--primary);"><i class="fas fa-money-bill-wave"></i> Ringkasan Keuangan</h3>
                <p><strong>Kas:</strong> Rp {Account.query.filter_by(type='kas').first().balance if Account.query.filter_by(type='kas').first() else 0:,.0f}</p>
                <p><strong>Pendapatan:</strong> Rp {Account.query.filter_by(type='pendapatan').first().balance if Account.query.filter_by(type='pendapatan').first() else 0:,.0f}</p>
                <p><strong>Laba Bersih:</strong> Rp {calculate_net_income():,.0f}</p>
            </div>
            
            <div class="card">
                <h3 style="color: var(--primary);"><i class="fas fa-chart-pie"></i> Status Pesanan</h3>
                <p><strong>Pending:</strong> {Order.query.filter_by(status='pending').count()} pesanan</p>
                <p><strong>Processing:</strong> {Order.query.filter_by(status='processing').count()} pesanan</p>
                <p><strong>Completed:</strong> {Order.query.filter_by(status='completed').count()} pesanan</p>
            </div>
        </div>
        '''
        
        return base_html('Seller Dashboard', content)
    except Exception as e:
        print(f"Error in seller dashboard: {e}")
        flash('Terjadi error saat memuat dashboard.', 'error')
        return redirect('/')

def calculate_net_income():
    try:
        revenue_account = Account.query.filter_by(type='pendapatan').first()
        revenue = revenue_account.balance if revenue_account else 0
        
        expense_accounts = Account.query.filter(Account.category=='expense').all()
        expenses = sum(acc.balance for acc in expense_accounts)
        
        return revenue - expenses
    except Exception as e:
        print(f"Error calculating net income: {e}")
        return 0

@app.route('/seller/orders')
@login_required
@seller_required
def seller_orders():
    try:
        orders = Order.query.order_by(Order.order_date.desc()).all()
        
        orders_html = ""
        for order in orders:
            customer = User.query.get(order.customer_id)
            status_display = f"<span class='status-text status-{order.status}'>{order.status.upper()}</span>"
            payment_status_display = f"<span class='status-text status-{order.payment_status}'>{order.payment_status.upper()}</span>"
            
            tracking_steps = get_tracking_steps(order.status, order.tracking_info)
            
            orders_html += f'''
            <div class="card">
                <div style="display: flex; justify-content: space-between; align-items: start;">
                    <div style="flex: 1;">
                        <h4>Order #{order.order_number}</h4>
                        <p><strong>Customer:</strong> {customer.full_name if customer else 'Unknown'}</p>
                        <p><strong>Total:</strong> Rp {order.total_amount:,.0f}</p>
                        <p><strong>Status:</strong> {status_display}</p>
                        <p><strong>Pembayaran:</strong> {payment_status_display}</p>
                        <p><strong>Metode:</strong> {order.payment_method} | <strong>Pengiriman:</strong> {order.shipping_method}</p>
                        <p><strong>Tanggal:</strong> {order.order_date.strftime('%d/%m/%Y %H:%M')}</p>
                        
                        <div class="tracking-steps">
                            {tracking_steps}
                        </div>
                        
                        {order.payment_status == 'paid' and f'''
                        <div class="form-group">
                            <label class="form-label">Update Status Pengiriman:</label>
                            <select id="tracking-info-{order.id}" class="form-control">
                                <option value="Pesanan diproses" {'selected' if order.tracking_info == 'Pesanan diproses' else ''}>Pesanan diproses</option>
                                <option value="Pesanan dikemas" {'selected' if order.tracking_info == 'Pesanan dikemas' else ''}>Pesanan dikemas</option>
                                <option value="Pesanan dikirim" {'selected' if order.tracking_info == 'Pesanan dikirim' else ''}>Pesanan dikirim</option>
                                <option value="Dalam perjalanan" {'selected' if order.tracking_info == 'Dalam perjalanan' else ''}>Dalam perjalanan</option>
                                <option value="Tiba di tujuan" {'selected' if order.tracking_info == 'Tiba di tujuan' else ''}>Tiba di tujuan</option>
                                <option value="Pesanan selesai" {'selected' if order.tracking_info == 'Pesanan selesai' else ''}>Pesanan selesai</option>
                            </select>
                        </div>
                        ''' or '''
                        <div style="margin-top: 1rem; padding: 1rem; background: rgba(229, 62, 62, 0.1); border-radius: 8px;">
                            <p style="color: var(--error); margin: 0;">
                                <strong>⚠️ Menunggu Pembayaran:</strong> Pesanan belum dapat diproses karena pembayaran belum diterima.
                            </p>
                        </div>
                        '''}
                    </div>
                    <div>
                        {get_order_actions(order)}
                        {order.payment_status == 'paid' and f'''
                        <button class="btn btn-info" onclick="updateTracking({order.id}, 'processing')">
                            <i class="fas fa-map-marker-alt"></i> Update Tracking
                        </button>
                        ''' or ''}
                    </div>
                </div>
            </div>
            '''
        
        content = f'''
        <h1 style="color: var(--primary);"><i class="fas fa-boxes"></i> Manajemen Pesanan</h1>
        <div class="stats">
            <div class="stat-card">
                <div class="stat-number">{Order.query.filter_by(status='pending').count()}</div>
                <div class="stat-label">Pending</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{Order.query.filter_by(status='processing').count()}</div>
                <div class="stat-label">Diproses</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{Order.query.filter_by(status='completed').count()}</div>
                <div class="stat-label">Selesai</div>
            </div>
        </div>
        
        {orders_html}
        '''
        
        return base_html('Pesanan Seller', content)
    except Exception as e:
        print(f"Error in seller orders: {e}")
        flash('Terjadi error saat memuat pesanan.', 'error')
        return redirect('/seller/dashboard')

def get_tracking_steps(status, tracking_info):
    steps = [
        {'id': 'pending', 'label': 'Pesanan Diterima', 'icon': '📥'},
        {'id': 'processing', 'label': 'Diproses', 'icon': '⚙️'},
        {'id': 'packed', 'label': 'Dikemas', 'icon': '📦'},
        {'id': 'shipped', 'label': 'Dikirim', 'icon': '🚚'},
        {'id': 'delivered', 'label': 'Tiba', 'icon': '🏠'},
        {'id': 'completed', 'label': 'Selesai', 'icon': '✅'}
    ]
    
    status_order = ['pending', 'processing', 'packed', 'shipped', 'delivered', 'completed']
    current_index = status_order.index(status) if status in status_order else 0
    
    steps_html = ""
    for i, step in enumerate(steps):
        step_class = ""
        if i < current_index:
            step_class = "step-completed"
        elif i == current_index:
            step_class = "step-active"
        
        steps_html += f'''
        <div class="tracking-step">
            <div class="step-icon {step_class}">{step['icon']}</div>
            <div style="font-size: 0.8rem;">{step['label']}</div>
        </div>
        '''
    
    return steps_html

def get_order_actions(order):
    if order.payment_status != 'paid':
        return '<span class="status-text status-unpaid">MENUNGGU PEMBAYARAN</span>'
    
    if order.status == 'processing':
        return f'''
        <form action="/seller/update_order_status/{order.id}" method="POST" style="display: inline;">
            <input type="hidden" name="status" value="completed">
            <button type="submit" class="btn btn-success">Selesaikan Order</button>
        </form>
        '''
    elif order.status == 'completed':
        return '<span class="status-text status-completed">SELESAI</span>'
    else:
        return '<span class="status-text status-pending">MENUNGGU PROSES</span>'

@app.route('/seller/update_order_status/<int:order_id>', methods=['POST'])
@login_required
@seller_required
def update_order_status(order_id):
    try:
        order = Order.query.get(order_id)
        new_status = request.form.get('status')
        
        if order and order.payment_status == 'paid':  # Hanya proses jika sudah bayar
            old_status = order.status
            order.status = new_status
            
            if new_status == 'completed':
                order.completed_date = datetime.now()
                # Buat jurnal penjualan otomatis
                create_sales_journal(order)
                flash('Order diselesaikan! Jurnal penjualan otomatis dibuat.', 'success')
            else:
                flash('Status order berhasil diupdate!', 'success')
            
            db.session.commit()
        else:
            flash('Order tidak dapat diproses karena pembayaran belum diterima!', 'error')
        
        return redirect('/seller/orders')
    except Exception as e:
        print(f"Error updating order status: {e}")
        flash('Terjadi error saat mengupdate status order.', 'error')
        return redirect('/seller/orders')

@app.route('/update_tracking/<int:order_id>', methods=['POST'])
@login_required
@seller_required
def update_tracking(order_id):
    try:
        order = Order.query.get(order_id)
        if order and order.payment_status == 'paid':
            data = request.get_json()
            order.tracking_info = data.get('tracking_info')
            
            tracking_mapping = {
                'Pesanan diproses': 'processing',
                'Pesanan dikemas': 'processing',
                'Pesanan dikirim': 'processing',
                'Dalam perjalanan': 'processing',
                'Tiba di tujuan': 'completed',
                'Pesanan selesai': 'completed'
            }
            
            new_status = tracking_mapping.get(order.tracking_info, order.status)
            if new_status != order.status:
                order.status = new_status
                if new_status == 'completed':
                    order.completed_date = datetime.now()
                    # Buat jurnal penjualan otomatis
                    create_sales_journal(order)
            
            db.session.commit()
            return jsonify({'success': True, 'message': 'Status pengiriman diperbarui'})
        
        return jsonify({'success': False, 'message': 'Order tidak ditemukan atau belum dibayar'})
    except Exception as e:
        print(f"Error updating tracking: {e}")
        return jsonify({'success': False, 'message': 'Terjadi error'})

@app.route('/seller/products')
@login_required
@seller_required
def seller_products():
    try:
        products = Product.query.filter_by(seller_id=current_user.id).all()
        
        products_html = ""
        for product in products:
            weight_info = f"{product.weight_kg}kg" if product.weight_kg else f"{product.size_cm}cm"
            products_html += f'''
            <div class="card">
                <div style="display: flex; justify-content: space-between; align-items: start;">
                    <div style="flex: 1;">
                        <img src="{product.image_url}" alt="{product.name}" class="product-image" style="max-width: 200px;" onerror="this.style.display='none'">
                        <h4>{product.name}</h4>
                        <p>{product.description}</p>
                        <div class="price">Rp {product.price:,.0f}</div>
                        <p>Stock: {product.stock} | {weight_info} | Kategori: {product.category}</p>
                        <p>Harga Cost: Rp {product.cost_price:,.0f}</p>
                    </div>
                    <div>
                        <a href="/seller/edit_product/{product.id}" class="btn btn-warning"><i class="fas fa-edit"></i> Edit</a>
                    </div>
                </div>
            </div>
            '''
        
        content = f'''
        <h1 style="color: var(--primary);"><i class="fas fa-fish"></i> Manajemen Produk</h1>
        <a href="/seller/add_product" class="btn btn-primary"><i class="fas fa-plus"></i> Tambah Produk Baru</a>
        {products_html}
        '''
        
        return base_html('Produk Seller', content)
    except Exception as e:
        print(f"Error in seller products: {e}")
        flash('Terjadi error saat memuat produk.', 'error')
        return redirect('/seller/dashboard')

@app.route('/seller/add_product', methods=['GET', 'POST'])
@login_required
@seller_required
def add_product():
    try:
        if request.method == 'POST':
            name = request.form.get('name')
            description = request.form.get('description')
            price = float(request.form.get('price'))
            cost_price = float(request.form.get('cost_price'))
            stock = int(request.form.get('stock'))
            size_cm = request.form.get('size_cm')
            weight_kg = request.form.get('weight_kg')
            category = request.form.get('category')
            
            product = Product(
                name=name,
                description=description,
                price=price,
                cost_price=cost_price,
                stock=stock,
                size_cm=float(size_cm) if size_cm else None,
                weight_kg=float(weight_kg) if weight_kg else None,
                category=category,
                seller_id=current_user.id
            )
            
            # Handle image upload
            if 'image' in request.files:
                file = request.files['image']
                if file and file.filename != '':
                    filename = save_product_image(file, product.name)
                    if filename:
                        product.image_url = f'/static/{filename}'
            
            db.session.add(product)
            db.session.commit()
            
            flash('Produk berhasil ditambahkan!', 'success')
            return redirect('/seller/products')
        
        content = '''
        <div style="max-width: 600px; margin: 0 auto;">
            <div class="card">
                <h2 style="color: var(--primary);"><i class="fas fa-plus"></i> Tambah Produk Baru</h2>
                <form method="POST" enctype="multipart/form-data">
                    <div class="form-group">
                        <label class="form-label">Gambar Produk</label>
                        <input type="file" name="image" class="form-control" accept="image/*">
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">Nama Produk</label>
                        <input type="text" name="name" class="form-control" required>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Deskripsi</label>
                        <textarea name="description" class="form-control" required></textarea>
                    </div>
                    <div class="grid grid-2">
                        <div class="form-group">
                            <label class="form-label">Harga Jual</label>
                            <input type="number" name="price" class="form-control" step="0.01" required>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Harga Cost</label>
                            <input type="number" name="cost_price" class="form-control" step="0.01" required>
                        </div>
                    </div>
                    <div class="grid grid-3">
                        <div class="form-group">
                            <label class="form-label">Stock</label>
                            <input type="number" name="stock" class="form-control" required>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Kategori</label>
                            <select name="category" class="form-control" required>
                                <option value="bibit">Bibit</option>
                                <option value="konsumsi">Konsumsi</option>
                                <option value="ikan_mas">Ikan Mas</option>
                            </select>
                        </div>
                    </div>
                    <div class="grid grid-2">
                        <div class="form-group">
                            <label class="form-label">Ukuran (cm)</label>
                            <input type="number" name="size_cm" class="form-control" step="0.1">
                        </div>
                        <div class="form-group">
                            <label class="form-label">Berat (kg)</label>
                            <input type="number" name="weight_kg" class="form-control" step="0.1">
                        </div>
                    </div>
                    <button type="submit" class="btn btn-primary"><i class="fas fa-save"></i> Simpan Produk</button>
                </form>
            </div>
        </div>
        '''
        return base_html('Tambah Produk', content)
    except Exception as e:
        print(f"Error in add product: {e}")
        flash('Terjadi error saat menambah produk.', 'error')
        return redirect('/seller/products')

@app.route('/seller/edit_product/<int:product_id>', methods=['GET', 'POST'])
@login_required
@seller_required
def edit_product(product_id):
    try:
        product = Product.query.get_or_404(product_id)
        
        if request.method == 'POST':
            product.name = request.form.get('name')
            product.description = request.form.get('description')
            product.price = float(request.form.get('price'))
            product.cost_price = float(request.form.get('cost_price'))
            product.stock = int(request.form.get('stock'))
            product.size_cm = float(request.form.get('size_cm')) if request.form.get('size_cm') else None
            product.weight_kg = float(request.form.get('weight_kg')) if request.form.get('weight_kg') else None
            product.category = request.form.get('category')
            
            # Handle image upload
            if 'image' in request.files:
                file = request.files['image']
                if file and file.filename != '':
                    filename = save_product_image(file, product.name)
                    if filename:
                        product.image_url = f'/static/{filename}'
            
            db.session.commit()
            flash('Produk berhasil diperbarui!', 'success')
            return redirect('/seller/products')
        
        content = f'''
        <div style="max-width: 600px; margin: 0 auto;">
            <div class="card">
                <h2 style="color: var(--primary);"><i class="fas fa-edit"></i> Edit Produk</h2>
                
                <form method="POST" enctype="multipart/form-data">
                    <div class="form-group">
                        <label class="form-label">Gambar Produk</label>
                        <input type="file" name="image" class="form-control" accept="image/*">
                        <small>Upload gambar baru untuk mengganti gambar saat ini</small>
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">Nama Produk</label>
                        <input type="text" name="name" class="form-control" value="{product.name}" required>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Deskripsi</label>
                        <textarea name="description" class="form-control" required>{product.description}</textarea>
                    </div>
                    <div class="grid grid-2">
                        <div class="form-group">
                            <label class="form-label">Harga Jual</label>
                            <input type="number" name="price" class="form-control" step="0.01" value="{product.price}" required>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Harga Cost</label>
                            <input type="number" name="cost_price" class="form-control" step="0.01" value="{product.cost_price}" required>
                        </div>
                    </div>
                    <div class="grid grid-3">
                        <div class="form-group">
                            <label class="form-label">Stock</label>
                            <input type="number" name="stock" class="form-control" value="{product.stock}" required>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Kategori</label>
                            <select name="category" class="form-control" required>
                                <option value="bibit" {'selected' if product.category == 'bibit' else ''}>Bibit</option>
                                <option value="konsumsi" {'selected' if product.category == 'konsumsi' else ''}>Konsumsi</option>
                                <option value="ikan_mas" {'selected' if product.category == 'ikan_mas' else ''}>Ikan Mas</option>
                            </select>
                        </div>
                    </div>
                    <div class="grid grid-2">
                        <div class="form-group">
                            <label class="form-label">Ukuran (cm)</label>
                            <input type="number" name="size_cm" class="form-control" step="0.1" value="{product.size_cm or ''}">
                        </div>
                        <div class="form-group">
                            <label class="form-label">Berat (kg)</label>
                            <input type="number" name="weight_kg" class="form-control" step="0.1" value="{product.weight_kg or ''}">
                        </div>
                    </div>
                    <button type="submit" class="btn btn-primary"><i class="fas fa-save"></i> Update Produk</button>
                </form>
                
                <div style="margin-top: 2rem;">
                    <h4>Gambar Saat Ini:</h4>
                    <img src="{product.image_url}" alt="{product.name}" 
                         style="max-width: 200px; height: auto; border-radius: 8px; margin-top: 1rem;"
                         onerror="this.style.display='none'">
                </div>
            </div>
        </div>
        '''
        return base_html('Edit Produk', content)
    except Exception as e:
        print(f"Error editing product: {e}")
        flash('Terjadi error saat mengupdate produk.', 'error')
        return redirect('/seller/products')

# ===== ROUTES AKUNTANSI =====
@app.route('/seller/accounting')
@login_required
@seller_required
def seller_accounting():
    try:
        # Get template options for dropdown
        template_options = ""
        for key, template in TRANSACTION_TEMPLATES.items():
            template_options += f'<option value="{key}">{template["name"]}</option>'
        
        # Generate input form for template transactions
        template_form = f'''
        <div class="card">
            <h3 style="color: var(--primary);"><i class="fas fa-plus-circle"></i> Input Jurnal Otomatis</h3>
            <p>Pilih jenis transaksi dan sistem akan menampilkan form yang sesuai</p>
            
            <div class="form-group">
                <label class="form-label">Jenis Transaksi</label>
                <select id="transaction_template" class="form-control" onchange="loadTransactionTemplate()">
                    <option value="">Pilih Jenis Transaksi</option>
                    {template_options}
                </select>
            </div>
            
            <div id="templateFormContainer">
                <!-- Form will be loaded here based on template selection -->
            </div>
        </div>
        '''
        
        content = f'''
        <h1 style="color: var(--primary);"><i class="fas fa-chart-bar"></i> Sistem Akuntansi Kang-Mas Shop</h1>
        <p>Sistem akuntansi lengkap dengan siklus akuntansi terintegrasi</p>
        
        <div class="accounting-tabs">
            <button class="tab active" onclick="showTab('saldo-awal', this)">Saldo Awal</button>
            <button class="tab" onclick="showTab('jurnal-umum', this)">Jurnal Umum</button>
            <button class="tab" onclick="showTab('buku-besar', this)">Buku Besar</button>
            <button class="tab" onclick="showTab('neraca-saldo', this)">Neraca Saldo</button>
            <button class="tab" onclick="showTab('laporan-keuangan', this)">Laporan Keuangan</button>
        </div>
        
        <div id="saldo-awal" class="tab-content active">
            <div class="card">
                <h3 style="color: var(--primary);"><i class="fas fa-file-invoice-dollar"></i> Saldo Awal</h3>
                <p>Pencatatan saldo awal usaha Kang-Mas Shop per 1 Januari 2025</p>
                
                <div style="background: var(--ocean-light); padding: 1.5rem; border-radius: var(--border-radius); margin: 1.5rem 0;">
                    <h4 style="color: var(--primary); margin-bottom: 1rem;">Ringkasan Saldo Awal:</h4>
                    <div class="grid grid-2">
                        <div>
                            <h5>Aset:</h5>
                            <p>Kas: Rp 10,000,000</p>
                            <p>Persediaan Barang Dagang: Rp 5,000,000</p>
                            <p>Peralatan Toko: Rp 5,000,000</p>
                            <p>Perlengkapan Toko: Rp 6,500,000</p>
                            <p><strong>Total Aset: Rp 26,500,000</strong></p>
                        </div>
                        <div>
                            <h5>Kewajiban & Ekuitas:</h5>
                            <p>Utang Dagang: Rp 20,000,000</p>
                            <p>Pendapatan Penjualan: Rp 6,500,000</p>
                            <p><strong>Total Kewajiban & Ekuitas: Rp 26,500,000</strong></p>
                        </div>
                    </div>
                </div>
                
                <table class="table">
                    <thead>
                        <tr>
                            <th>Akun</th>
                            <th>Kode</th>
                            <th>Debit</th>
                            <th>Kredit</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td>Kas</td>
                            <td>101</td>
                            <td class="debit">Rp 10,000,000</td>
                            <td></td>
                        </tr>
                        <tr>
                            <td>Persediaan Barang Dagang</td>
                            <td>103</td>
                            <td class="debit">Rp 5,000,000</td>
                            <td></td>
                        </tr>
                        <tr>
                            <td>Peralatan Toko</td>
                            <td>105</td>
                            <td class="debit">Rp 5,000,000</td>
                            <td></td>
                        </tr>
                        <tr>
                            <td>Perlengkapan Toko</td>
                            <td>104</td>
                            <td class="debit">Rp 6,500,000</td>
                            <td></td>
                        </tr>
                        <tr>
                            <td>Pendapatan Penjualan</td>
                            <td>401</td>
                            <td></td>
                            <td class="credit">Rp 6,500,000</td>
                        </tr>
                        <tr>
                            <td>Utang Dagang</td>
                            <td>201</td>
                            <td></td>
                            <td class="credit">Rp 20,000,000</td>
                        </tr>
                        <tr style="font-weight: bold; border-top: 2px solid var(--primary);">
                            <td colspan="2">TOTAL</td>
                            <td class="debit">Rp 26,500,000</td>
                            <td class="credit">Rp 26,500,000</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
        
        <div id="jurnal-umum" class="tab-content">
            <div class="card">
                <h3 style="color: var(--primary);"><i class="fas fa-book"></i> Jurnal Umum</h3>
                <p>Pencatatan semua transaksi usaha dalam periode akuntansi</p>
            </div>
            
            {template_form}
            
            {get_journal_entries_table()}
        </div>

        <div id="buku-besar" class="tab-content">
            <div class="card">
                <h3 style="color: var(--primary);"><i class="fas fa-book-open"></i> Buku Besar</h3>
                <p>Ringkasan semua transaksi per akun dalam periode akuntansi</p>
                {get_ledger_data()}
            </div>
        </div>
        
        <div id="neraca-saldo" class="tab-content">
            <div class="card">
                <h3 style="color: var(--primary);"><i class="fas fa-balance-scale"></i> Neraca Saldo</h3>
                <p>Daftar saldo semua akun buku besar sebelum penyesuaian</p>
                <table class="table">
                    <thead>
                        <tr>
                            <th>Kode</th>
                            <th>Nama Akun</th>
                            <th>Debit</th>
                            <th>Kredit</th>
                        </tr>
                    </thead>
                    <tbody>
                        {get_trial_balance()}
                    </tbody>
                </table>
            </div>
        </div>
        
        <div id="laporan-keuangan" class="tab-content">
            <div class="card">
                <h3 style="color: var(--primary);"><i class="fas fa-chart-line"></i> Laporan Laba Rugi</h3>
                {get_income_statement()}
            </div>
            
            <div class="card">
                <h3 style="color: var(--primary);"><i class="fas fa-balance-scale-left"></i> Laporan Posisi Keuangan (Neraca)</h3>
                {get_balance_sheet()}
            </div>
            
            <div class="card">
                <h3 style="color: var(--primary);"><i class="fas fa-money-bill-wave"></i> Laporan Arus Kas</h3>
                {get_cash_flow_statement()}
            </div>
        </div>
        '''
        
        return base_html('Akuntansi', content)
    except Exception as e:
        print(f"Error in accounting: {e}")
        flash('Terjadi error saat memuat data akuntansi.', 'error')
        return redirect('/seller/dashboard')

@app.route('/api/get_transaction_template/<template_key>')
@login_required
@seller_required
def get_transaction_template(template_key):
    try:
        if template_key not in TRANSACTION_TEMPLATES:
            return jsonify({'success': False, 'message': 'Template tidak ditemukan'})
        
        template = TRANSACTION_TEMPLATES[template_key]
        accounts_map = {}
        
        # Build accounts mapping
        for account in Account.query.all():
            accounts_map[account.type] = account
        
        form_html = f'''
        <form id="templateJournalForm">
            <input type="hidden" name="template_key" value="{template_key}">
            
            <div class="form-group">
                <label class="form-label">Tanggal Transaksi</label>
                <input type="date" name="date" class="form-control" required value="{datetime.now().strftime('%Y-%m-%d')}">
            </div>
            
            <div class="form-group">
                <label class="form-label">Keterangan</label>
                <input type="text" name="description" class="form-control" value="{template['description']}" required>
            </div>
            
            <h4 style="margin: 1.5rem 0 1rem 0; color: var(--primary);">Detail Akun:</h4>
        '''
        
        for entry in template['entries']:
            account = accounts_map.get(entry['account_type'])
            if account:
                form_html += f'''
                <div class="form-group">
                    <label class="form-label">
                        {account.code} - {account.name} 
                        <span style="color: {'var(--success)' if entry['side'] == 'debit' else 'var(--error)'}; font-weight: 600;">
                            ({'Debit' if entry['side'] == 'debit' else 'Kredit'})
                        </span>
                    </label>
                    <input type="number" id="amount_{entry['account_type']}" name="amount_{entry['account_type']}" 
                           class="form-control" step="0.01" min="0" required 
                           placeholder="Masukkan nominal {entry['description']}">
                </div>
                '''
        
        form_html += '''
            <button type="button" class="btn btn-primary" onclick="submitTemplateJournal()">
                <i class="fas fa-save"></i> Simpan Jurnal
            </button>
        </form>
        '''
        
        return jsonify({'success': True, 'form_html': form_html})
        
    except Exception as e:
        print(f"Error getting transaction template: {e}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/seller/add_template_journal', methods=['POST'])
@login_required
@seller_required
def add_template_journal():
    try:
        data = request.get_json()
        template_key = data['template_key']
        date = datetime.strptime(data['date'], '%Y-%m-%d')
        amounts = data['amounts']
        
        if template_key not in TRANSACTION_TEMPLATES:
            return jsonify({'success': False, 'message': 'Template tidak ditemukan'})
        
        # Create journal from template
        journal = create_journal_from_template(template_key, date, amounts)
        
        # Update stok jika ini adalah jurnal pembelian persediaan
        if journal:
            update_stock_from_journal(journal)
        
        return jsonify({'success': True, 'message': 'Jurnal berhasil disimpan'})
    except Exception as e:
        print(f"Error adding template journal: {e}")
        return jsonify({'success': False, 'message': str(e)})

# ===== API ROUTES =====
@app.route('/api/cart/add', methods=['POST'])
@login_required
def api_cart_add():
    try:
        print("=== API CART ADD CALLED ===")
        print("Current User:", current_user.id, current_user.email, current_user.user_type)
        
        # Check if user is customer
        if current_user.user_type != 'customer':
            print("❌ User is not customer")
            return jsonify({'success': False, 'message': 'Hanya customer yang bisa menambah ke keranjang'})
        
        # Check content type
        if not request.is_json:
            print("❌ Request is not JSON")
            return jsonify({'success': False, 'message': 'Request harus berupa JSON'})
        
        data = request.get_json()
        print("📦 Received data:", data)
        
        if not data:
            print("❌ No data received")
            return jsonify({'success': False, 'message': 'Data tidak valid'})
            
        product_id = data.get('product_id')
        quantity = data.get('quantity', 1)
        
        if not product_id:
            print("❌ No product_id provided")
            return jsonify({'success': False, 'message': 'Product ID tidak ditemukan'})
        
        # Convert to integer
        try:
            product_id = int(product_id)
            quantity = int(quantity)
        except (ValueError, TypeError):
            print("❌ Invalid product_id or quantity")
            return jsonify({'success': False, 'message': 'Product ID atau quantity tidak valid'})
        
        product = Product.query.get(product_id)
        if not product:
            print("❌ Product not found with ID:", product_id)
            return jsonify({'success': False, 'message': 'Produk tidak ditemukan'})
        
        print(f"✅ Product found: {product.name}, Stock: {product.stock}")
        
        # Check stock
        if product.stock < quantity:
            print(f"❌ Insufficient stock: {product.stock} < {quantity}")
            return jsonify({'success': False, 'message': f'Stock {product.name} tidak mencukupi. Stok tersedia: {product.stock}'})
        
        # Check if item already in cart
        existing_item = CartItem.query.filter_by(
            user_id=current_user.id, 
            product_id=product_id
        ).first()
        
        if existing_item:
            # Check if adding more would exceed stock
            if product.stock < (existing_item.quantity + quantity):
                print(f"❌ Would exceed stock: {existing_item.quantity} + {quantity} > {product.stock}")
                return jsonify({'success': False, 'message': f'Stock tidak mencukupi untuk jumlah yang diminta. Stok tersedia: {product.stock}'})
            
            existing_item.quantity += quantity
            print(f"✅ Updated existing item: {existing_item.quantity}")
        else:
            cart_item = CartItem(
                user_id=current_user.id,
                product_id=product_id,
                quantity=quantity
            )
            db.session.add(cart_item)
            print("✅ Created new cart item")
        
        db.session.commit()
        print("✅ Cart updated successfully")
        
        # Get updated cart count
        cart_count = CartItem.query.filter_by(user_id=current_user.id).count()
        print(f"🛒 Cart count: {cart_count}")
        
        return jsonify({
            'success': True, 
            'message': f'{product.name} berhasil ditambahkan ke keranjang!',
            'cart_count': cart_count
        })
        
    except Exception as e:
        print(f"💥 ERROR in api_cart_add: {str(e)}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Terjadi error sistem: {str(e)}'})

@app.route('/api/cart/count')
@login_required
def api_cart_count():
    try:
        if current_user.user_type != 'customer':
            return jsonify({'count': 0})
        
        count = CartItem.query.filter_by(user_id=current_user.id).count()
        print(f"🛒 Cart count requested: {count}")
        return jsonify({'count': count})
    except Exception as e:
        print(f"Error getting cart count: {e}")
        return jsonify({'count': 0})

# ===== JALANKAN APLIKASI =====
if __name__ == '__main__':
    with app.app_context():
        # Reset database untuk memastikan skema terbaru
        reset_database_safe()
        create_initial_data()
    app.run(debug=True, port=5000)