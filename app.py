from flask import Flask, render_template, request, redirect, url_for, flash, session, render_template_string
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix   # <--- 1. Yeh import add karein
from datetime import timedelta, datetime
from zoneinfo import ZoneInfo
import os
import re
import random

# IMPORT OAUTH FOR GOOGLE LOGIN
from authlib.integrations.flask_client import OAuth

app = Flask(__name__)

# --- 2. RENDER PROXY FIX & URL SCHEME CONFIGURATION ---
app.wsgi_app = ProxyFix(
    app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
)
app.config['PREFERRED_URL_SCHEME'] = 'https'

# --- 3. SECURE SECRET KEY ---
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'super_secret_key_for_local_kaamconnect')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=30)

# DB Connection & SSL Fix
db_url = os.environ.get('DATABASE_URL', 'sqlite:///portal.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
}

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# ================= 4. OAUTH CONFIGURATION (GOOGLE) =================
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.environ.get('GOOGLE_CLIENT_ID', 'YOUR_GOOGLE_CLIENT_ID'),
    client_secret=os.environ.get('GOOGLE_CLIENT_SECRET', 'YOUR_GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# ================= DATABASE MODELS =================
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    mobile = db.Column(db.String(30), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    address = db.Column(db.Text, nullable=True)
    experience = db.Column(db.String(50), nullable=True)
    expertise = db.Column(db.String(100), nullable=True)
    wallet_balance = db.Column(db.Integer, default=0)
    per_day_amount = db.Column(db.Integer, nullable=True)
    is_available = db.Column(db.Boolean, default=True)
    last_deduction_month = db.Column(db.Integer, default=datetime.now().month)
    is_plan_active = db.Column(db.Boolean, default=True)
    is_blocked = db.Column(db.Boolean, default=False)  # Added to prevent missing column error
    shop_name = db.Column(db.String(150), nullable=True)
    created_at = db.Column(db.DateTime, nullable=True)

    requirements = db.relationship('Requirement', backref='customer_user', cascade='all, delete-orphan')
    vacancies = db.relationship('Vacancy', backref='shop_owner_user', cascade='all, delete-orphan')
    unlocked_leads = db.relationship('UnlockedLead', backref='shop_owner_user', cascade='all, delete-orphan')
    payment_requests = db.relationship('PaymentRequest', backref='shop_owner_user', cascade='all, delete-orphan')

class Requirement(db.Model):
    __tablename__ = 'requirement'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    category = db.Column(db.String(50))
    budget = db.Column(db.Integer)
    deadline = db.Column(db.String(50))
    description = db.Column(db.Text)
    unlocked_by_shops = db.relationship('UnlockedLead', backref='requirement', cascade='all, delete-orphan', lazy=True)

class UnlockedLead(db.Model):
    __tablename__ = 'unlocked_lead'
    id = db.Column(db.Integer, primary_key=True)
    shop_owner_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    requirement_id = db.Column(db.Integer, db.ForeignKey('requirement.id'))
    
    amount = db.Column(db.String(100), nullable=True)
    deadline = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(50), default='Pending')

class SiteSettings(db.Model):
    __tablename__ = 'site_settings'
    id = db.Column(db.Integer, primary_key=True)
    maintenance_mode = db.Column(db.Boolean, default=False)
    admin_upi = db.Column(db.String(100), default='admin@upi')

class LeadReport(db.Model):
    __tablename__ = 'lead_report'
    id = db.Column(db.Integer, primary_key=True)
    shop_owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    requirement_id = db.Column(db.Integer, db.ForeignKey('requirement.id'), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='Pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    shop_owner = db.relationship('User', backref='lead_reports')
    requirement = db.relationship('Requirement', backref='reports')

class Vacancy(db.Model):
    __tablename__ = 'vacancy'
    id = db.Column(db.Integer, primary_key=True)
    shop_owner_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    person_need = db.Column(db.String(100))
    address = db.Column(db.Text)
    task_type = db.Column(db.String(100))
    per_day_pay = db.Column(db.Integer)
    description = db.Column(db.Text)

class PaymentRequest(db.Model):
    __tablename__ = 'payment_request'
    id = db.Column(db.Integer, primary_key=True)
    shop_owner_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    amount = db.Column(db.Integer, nullable=False)
    trx_id = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default='Pending')

class Quotation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shop_owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    worker_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    requirement_id = db.Column(db.Integer, db.ForeignKey('requirement.id'), nullable=True)
    
    amount = db.Column(db.Float, nullable=False)
    deadline = db.Column(db.String(100), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='Pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- HELPER FUNCTIONS ---
def get_unlock_cost(budget_str):
    try:
        if not budget_str: return 50 
        budget = int(''.join(filter(str.isdigit, str(budget_str))))
        
        if budget <= 2000: return 50
        elif budget <= 5000: return 70
        elif budget <= 10000: return 90
        elif budget <= 20000: return 120
        elif budget <= 35000: return 140
        else: return 200
    except Exception:
        return 50

def send_otp_email(target_email, otp, context="Security Verification"):
    if not target_email:
        print("OTP Email Error: Target email is empty or None.")
        return
    try:
        api_key = os.environ.get('BREVO_API_KEY')
        sender_email = os.environ.get('MAIL_USERNAME', 'no-reply@kaamconnect.com')
        if api_key and sender_email:
            import urllib.request
            import json
            url = "https://api.brevo.com/v3/smtp/email"
            payload = {
                "sender": {"name": "Kaamconnect System", "email": sender_email},
                "to": [{"email": target_email}],
                "subject": f"Your OTP for Kaamconnect {context}",
                "htmlContent": f"""
                <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #ddd; border-radius: 8px; text-align: center;">
                    <h2 style="color: #667eea;">Kaamconnect {context}</h2>
                    <p style="font-size: 16px;">Apna account verify karne ke liye niche diya gaya OTP enter karein:</p>
                    <h1 style="color: #333; letter-spacing: 5px; padding: 10px; background: #f4f4f4; border-radius: 5px; display: inline-block;">{otp}</h1>
                    <p style="color: #e74c3c; font-size: 12px; margin-top: 20px;">Kripya yeh OTP kisi ke sath share na karein.</p>
                </div>
                """
            }
            headers = {
                "accept": "application/json",
                "api-key": api_key,
                "content-type": "application/json"
            }
            req_data = json.dumps(payload).encode('utf-8')
            req_obj = urllib.request.Request(url, data=req_data, headers=headers, method='POST')
            with urllib.request.urlopen(req_obj, timeout=5) as response:
                pass
    except Exception as e:
        print(f"OTP Email Error: {e}")

# ================= ADMIN NOTIFICATION FUNCTION =================
def notify_admin_new_user(user):
    try:
        api_key = os.environ.get('BREVO_API_KEY')
        admin_email = os.environ.get('ADMIN_EMAIL') or os.environ.get('MAIL_USERNAME')
        sender_email = os.environ.get('MAIL_USERNAME', 'no-reply@kaamconnect.com')
        
        if api_key and admin_email:
            import urllib.request
            import json
            url = "https://api.brevo.com/v3/smtp/email"
            extra_info = ""
            if user.role == 'shop_owner':
                extra_info = f"<li><b>Shop Name:</b> {getattr(user, 'shop_name', 'N/A')}</li>"
            elif user.role == 'worker':
                extra_info = f"<li><b>Expertise/Skills:</b> {getattr(user, 'expertise', 'N/A')}</li>"
            payload = {
                "sender": {"name": "Kaamconnect System", "email": sender_email},
                "to": [{"email": admin_email}],
                "subject": f"🚀 Naya User Signup Hua Hai! ({user.role.upper()})",
                "htmlContent": f"""
                <html>
                    <body>
                        <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #ddd; border-radius: 5px;">
                            <h2 style="color: #28a745;">✨ Naya User Register Hua Hai!</h2>
                            <p>Kaamconnect par ek naya user judaa hai. Details niche di gayi hain:</p>
                            <ul>
                                <li><b>Role:</b> <span style="color: #007bff; text-transform: uppercase;">{user.role}</span></li>
                                <li><b>Name:</b> {user.name}</li>
                                <li><b>Mobile Number:</b> {user.mobile}</li>
                                <li><b>Email Address:</b> {user.email or 'N/A'}</li>
                                <li><b>Address:</b> {getattr(user, 'address', 'N/A')}</li>
                                {extra_info}
                            </ul>
                            <p style="font-size: 12px; color: #777; margin-top: 20px;">Yeh Kaamconnect automated notification system hai.</p>
                        </div>
                    </body>
                </html>
                """
            }
            headers = {
                "accept": "application/json",
                "api-key": api_key,
                "content-type": "application/json"
            }
            req_data = json.dumps(payload).encode('utf-8')
            req_obj = urllib.request.Request(url, data=req_data, headers=headers, method='POST')
            with urllib.request.urlopen(req_obj, timeout=5) as response:
                print("Admin notification mail sent.")
    except Exception as e:
        print(f"Admin notification mail error: {e}")

# ================= GOOGLE AUTH ROUTES =================
@app.route('/login/google')
def login_google():
    redirect_uri = url_for('authorize_google', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/authorize/google')
def authorize_google():
    token = google.authorize_access_token()
    resp = google.get('https://www.googleapis.com/oauth2/v1/userinfo')
    user_info = resp.json()
    
    email = user_info.get('email')
    name = user_info.get('name')
    
    user = User.query.filter_by(email=email).first()
    if user:
        if user.role == 'admin':
            otp = str(random.randint(100000, 999999))
            session['admin_login_id'] = user.id
            session['admin_login_otp'] = otp
            send_otp_email(user.email, otp, context="Admin Login")
            flash(f'Admin Security Alert: Ek OTP aapke registered email ({user.email}) par bheja gaya hai.', 'info')
            return redirect(url_for('verify_admin_otp'))
        
        session.permanent = True
        login_user(user)
        flash('Google se successfully login ho gaye hain!', 'success')
        if user.role == 'customer': return redirect(url_for('customer_dash'))
        elif user.role == 'shop_owner': return redirect(url_for('shop_dash'))
        elif user.role == 'worker': return redirect(url_for('worker_dash'))
        return redirect(url_for('index'))
    else:
        session['google_signup'] = {'email': email, 'name': name}
        flash('Google Email Verify ho gaya hai. Kripya apna Role aur baki details confirm karein.', 'info')
        return redirect(url_for('google_step2'))

def notify_admin_reported_lead(shop_owner, req, reason):
    try:
        api_key = os.environ.get('BREVO_API_KEY')
        admin_email = os.environ.get('ADMIN_EMAIL') or os.environ.get('MAIL_USERNAME')
        sender_email = os.environ.get('MAIL_USERNAME', 'no-reply@kaamconnect.com')
        
        if api_key and admin_email:
            import urllib.request
            import json
            url = "https://api.brevo.com/v3/smtp/email"
            payload = {
                "sender": {"name": "Kaamconnect System", "email": sender_email},
                "to": [{"email": admin_email}],
                "subject": f"⚠️ Lead Reported by Shop Owner ({shop_owner.name})",
                "htmlContent": f"""
                <html>
                    <body>
                        <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #ddd; border-radius: 5px;">
                            <h2 style="color: #dc3545;">⚠️ Ek Lead Report Ki Gayi Hai!</h2>
                            <p>Shop owner ne ek requirement/lead ke khilaf report darj ki hai. Details niche hain:</p>
                            <ul>
                                <li><b>Shop Owner Name:</b> {shop_owner.name}</li>
                                <li><b>Shop Mobile:</b> {shop_owner.mobile}</li>
                                <li><b>Requirement ID:</b> #{req.id}</li>
                                <li><b>Category:</b> {req.category}</li>
                                <li><b>Reason / Issue:</b> {reason}</li>
                            </ul>
                            <p>Kripya Admin Dashboard par jakar ise check karein.</p>
                        </div>
                    </body>
                </html>
                """
            }
            headers = {
                "accept": "application/json",
                "api-key": api_key,
                "content-type": "application/json"
            }
            req_data = json.dumps(payload).encode('utf-8')
            req_obj = urllib.request.Request(url, data=req_data, headers=headers, method='POST')
            with urllib.request.urlopen(req_obj, timeout=5) as response:
                print("Admin report notification email sent.")
    except Exception as e:
        print(f"Admin report notification error: {e}")

@app.route('/google_step2', methods=['GET', 'POST'])
def google_step2():
    if 'google_signup' not in session:
        return redirect(url_for('signup'))
        
    if request.method == 'POST':
        role = request.form.get('role', 'customer').strip()
        country_code = request.form.get('country_code', '+91').strip()
        raw_mobile = request.form.get('mobile', '').strip()
        mobile = f"{country_code} {raw_mobile}"
        password = request.form.get('password', '').strip()
        address = request.form.get('address', '').strip()
        experience = request.form.get('experience', '').strip()
        expertise = request.form.get('expertise', '').strip()
        shop_name = request.form.get('shop_name', '').strip()
        
        per_day_raw = request.form.get('per_day_amount')
        per_day_amount = int(per_day_raw) if per_day_raw and per_day_raw.strip().isdigit() else None
        
        restricted_numbers = ["9999999999", "+91 9999999999"]
        admin_users = User.query.filter_by(role='admin').all()
        for admin in admin_users:
            restricted_numbers.append(admin.mobile)
            if ' ' in admin.mobile:
                restricted_numbers.append(admin.mobile.split(' ', 1)[1])
                
        if raw_mobile in restricted_numbers or mobile in restricted_numbers:
            flash('Kripya apna valid mobile number use karein. System admin ka number allowed nahi hai.', 'danger')
            return redirect(url_for('google_step2'))
            
        user_exists = User.query.filter_by(mobile=mobile).first()
        if user_exists:
            flash('Mobile number pehle se hi kisi aur account se registered hai!', 'danger')
            return redirect(url_for('google_step2'))
            
        hashed_password = generate_password_hash(password, method='scrypt')
        ist_time = datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)
        
        new_user = User(
            role=role, mobile=mobile, password=hashed_password, 
            name=session['google_signup']['name'],
            email=session['google_signup']['email'], 
            address=address, experience=experience, expertise=expertise,
            shop_name=shop_name, per_day_amount=per_day_amount,
            wallet_balance=50, is_available=True, created_at=ist_time
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        notify_admin_new_user(new_user)
        login_user(new_user)
        session.pop('google_signup', None)
        
        if new_user.role == 'shop_owner':
            session['show_welcome_popup'] = True
        
        flash('Account setup complete! Aap securely login ho gaye hain.', 'success')
        if new_user.role == 'customer': return redirect(url_for('customer_dash'))
        elif new_user.role == 'shop_owner': return redirect(url_for('shop_dash'))
        elif new_user.role == 'worker': return redirect(url_for('worker_dash'))
        return redirect(url_for('index'))
        
    return render_template('signup.html', show_google_step2=True, google_data=session['google_signup'])

# ================= ROUTES =================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/report_lead/<int:req_id>', methods=['POST'])
@login_required
def report_lead(req_id):
    if current_user.role.lower() != 'shop_owner':
        return "Unauthorized", 403
        
    reason = request.form.get('reason', 'No reason provided').strip()
    req = Requirement.query.get_or_404(req_id)
    
    # Save report to database
    new_report = LeadReport(
        shop_owner_id=current_user.id,
        requirement_id=req.id,
        reason=reason,
        status='Pending'
    )
    db.session.add(new_report)
    db.session.commit()
    
    # Send email notification to admin
    notify_admin_reported_lead(current_user, req, reason)
    
    flash('Lead successfully report ho gayi hai aur Admin ko email bhej diya gaya hai.', 'success')
    return redirect(url_for('shop_dash'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        role = request.form.get('role', 'customer').strip()
        country_code = request.form.get('country_code', '+91').strip()
        raw_mobile = request.form.get('mobile', '').strip()
        password = request.form.get('password', '').strip()
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        address = request.form.get('address', '').strip()
        experience = request.form.get('experience', '').strip()
        expertise = request.form.get('expertise', '').strip()
        shop_name = request.form.get('shop_name', '').strip()
        
        per_day_raw = request.form.get('per_day_amount')
        per_day_amount = int(per_day_raw) if per_day_raw and per_day_raw.strip().isdigit() else None

        if not raw_mobile or not password or not name or not email:
            flash('Please fill all mandatory fields including Email.', 'danger')
            return redirect(url_for('signup', role=role))

        email_regex = r'^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$'
        if not re.match(email_regex, email, re.IGNORECASE):
            flash('Kripya ek valid Email address dalein (jaise name@example.com).', 'danger')
            return redirect(url_for('signup', role=role))

        restricted_numbers = ["9999999999", "+91 9999999999"]
        admin_users = User.query.filter_by(role='admin').all()
        for admin in admin_users:
            restricted_numbers.append(admin.mobile)
            if ' ' in admin.mobile:
                restricted_numbers.append(admin.mobile.split(' ', 1)[1])
                
        if raw_mobile in restricted_numbers or f"{country_code} {raw_mobile}" in restricted_numbers:
            flash('Kripya apna valid mobile number use karein. System admin ka number allowed nahi hai.', 'danger')
            return redirect(url_for('signup', role=role))

        mobile = f"{country_code} {raw_mobile}"

        user_exists = User.query.filter_by(mobile=mobile).first()
        if user_exists:
            flash('Mobile number pehle se registered hai!', 'danger')
            return redirect(url_for('signup', role=role))

        hashed_password = generate_password_hash(password, method='scrypt')
        
        otp = str(random.randint(100000, 999999))
        session['signup_data'] = {
            'role': role, 'mobile': mobile, 'password': hashed_password,
            'name': name, 'email': email, 'address': address,
            'experience': experience, 'expertise': expertise,
            'shop_name': shop_name, 'per_day_amount': per_day_amount
        }
        session['signup_otp'] = otp
        
        send_otp_email(email, otp, context="Signup")
        flash(f'Verification OTP aapke email ({email}) par bhej diya gaya hai.', 'info')
        
        return render_template('signup.html', role=role, show_otp=True, email=email)
        
    role = request.args.get('role', 'customer')
    return render_template('signup.html', role=role, show_otp=False, show_google_step2=False)

@app.route('/verify_signup_otp', methods=['POST'])
def verify_signup_otp():
    entered_otp = request.form.get('otp', '').strip()
    
    if 'signup_otp' in session and entered_otp == session['signup_otp']:
        data = session.get('signup_data')
        ist_time = datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)
        
        new_user = User(
            role=data['role'], mobile=data['mobile'], password=data['password'], name=data['name'],
            email=data['email'], address=data['address'], experience=data['experience'], expertise=data['expertise'],
            shop_name=data['shop_name'], per_day_amount=data['per_day_amount'],
            wallet_balance=50, is_available=True, created_at=ist_time
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        notify_admin_new_user(new_user)
        login_user(new_user)
        
        session.pop('signup_otp', None)
        session.pop('signup_data', None)

        if new_user.role == 'shop_owner':
            session['show_welcome_popup'] = True
        
        flash('Email verified! Account successfully ban gaya hai aur aap login ho chuke hain!', 'success')
        
        if new_user.role == 'customer': return redirect(url_for('customer_dash'))
        elif new_user.role == 'shop_owner': return redirect(url_for('shop_dash'))
        elif new_user.role == 'worker': return redirect(url_for('worker_dash'))
        return redirect(url_for('index'))
    else:
        flash('Invalid OTP. Kripya sahi OTP dalein.', 'danger')
        return render_template('signup.html', show_otp=True, email=session.get('signup_data', {}).get('email', ''))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        country_code = request.form.get('country_code', '+91').strip()
        raw_mobile = request.form.get('mobile', '').strip()
        password = request.form.get('password', '').strip()
        
        user = User.query.filter_by(mobile=f"{country_code} {raw_mobile}").first()
        if not user:
            user = User.query.filter_by(mobile=raw_mobile).first()
        
        if user and check_password_hash(user.password, password):
            if user.role == 'admin':
                if not user.email:
                    user.email = os.environ.get('ADMIN_EMAIL') or os.environ.get('MAIL_USERNAME') or 'kaamconnect7@gmail.com'
                    db.session.commit()
                
                otp = str(random.randint(100000, 999999))
                session['admin_login_id'] = user.id
                session['admin_login_otp'] = otp
                send_otp_email(user.email, otp, context="Admin Login")
                flash(f'Admin Security Alert: Ek OTP aapke registered email ({user.email}) par bheja gaya hai.', 'info')
                return redirect(url_for('verify_admin_otp'))
            
            session.permanent = True
            login_user(user)
            if user.role == 'customer': return redirect(url_for('customer_dash'))
            elif user.role == 'shop_owner': return redirect(url_for('shop_dash'))
            elif user.role == 'worker': return redirect(url_for('worker_dash'))
        flash('Invalid Mobile Number or Password', 'danger')
    return render_template('login.html')

@app.route('/verify_admin_otp', methods=['GET', 'POST'])
def verify_admin_otp():
    if 'admin_login_id' not in session:
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        entered_otp = request.form.get('otp', '').strip()
        if entered_otp == session.get('admin_login_otp'):
            user = User.query.get(session['admin_login_id'])
            session.permanent = True
            login_user(user)
            session.pop('admin_login_otp', None)
            session.pop('admin_login_id', None)
            flash('Admin authentication successful.', 'success')
            return redirect(url_for('admin_dash'))
        else:
            flash('Invalid OTP entered. Please try again.', 'danger')
            
    html = """
    {% extends 'base.html' %}
    {% block content %}
    <div class="container py-5 mt-5">
        <div class="row justify-content-center">
            <div class="col-md-5">
                <div class="card shadow-lg border-0 p-5 text-center" style="border-radius: 20px; background: rgba(255, 255, 255, 0.9); backdrop-filter: blur(10px);">
                    <i class="fa-solid fa-shield-halved fa-3x text-primary mb-3"></i>
                    <h3 class="fw-bold mb-2 text-dark">Admin Verification</h3>
                    <p class="text-muted small mb-4">Please enter the 6-digit OTP sent to your registered admin email.</p>
                    <form method="POST" onsubmit="document.getElementById('adminOtpBtn').disabled = true; document.getElementById('adminOtpBtn').innerText = 'Please wait...';">
                        <input type="text" name="otp" class="form-control text-center fw-bold fs-4 mb-4 shadow-sm" placeholder="• • • • • •" required maxlength="6" style="letter-spacing: 5px; border-radius: 12px; height: 60px;">
                        <button type="submit" id="adminOtpBtn" class="btn btn-primary w-100 py-3 fw-bold shadow" style="border-radius: 12px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border: none;">
                            Verify & Login Securely
                        </button>
                    </form>
                </div>
            </div>
        </div>
    </div>
    {% endblock %}
    """
    return render_template_string(html)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('index'))

@app.route('/customer/dashboard', methods=['GET', 'POST'])
@login_required
def customer_dash():
    if current_user.role != 'customer': return "Unauthorized", 403
    
    if request.method == 'POST':
        current_user.name = request.form.get('name')
        current_user.email = request.form.get('email')
        current_user.address = request.form.get('address')
        
        new_req = Requirement(
            customer_id=current_user.id,
            category=request.form.get('category'), 
            budget=request.form.get('budget'),
            deadline=request.form.get('deadline'), 
            description=request.form.get('description')
        )
        db.session.add(new_req)
        db.session.commit()

        try:
            shop_owners = User.query.filter_by(role='shop_owner', is_available=True).all()
            recipient_emails = [shop.email for shop in shop_owners if shop.email]

            if recipient_emails:
                api_key = os.environ.get('BREVO_API_KEY')
                sender_email = os.environ.get('MAIL_USERNAME', 'no-reply@kaamconnect.com')
                
                if api_key and sender_email:
                    import urllib.request
                    import json

                    url = "https://api.brevo.com/v3/smtp/email"
                    payload = {
                        "sender": {"name": "Kaamconnect", "email": sender_email},
                        "to": [{"email": email} for email in recipient_emails],
                        "subject": "🎯 Naya Kaam Aaya Hai! (Urgent)",
                        "htmlContent": f"""
                        <html>
                            <body>
                                <h2 style="color: #d9534f;">Nayi Requirement Aayi Hai!</h2>
                                <p>Kaamconnect par ek naya customer kaam lekar aaya hai.</p>
                                <ul>
                                    <li><b>Category:</b> {new_req.category}</li>
                                    <li><b>Budget:</b> ₹{new_req.budget}</li>
                                </ul>
                                <p><b>Note:</b> Sirf pehle 3-4 log hi ise unlock kar sakte hain. Jaldi se apna dashboard check karein!</p>
                            </body>
                        </html>
                        """
                    }
                    headers = {
                        "accept": "application/json",
                        "api-key": api_key,
                        "content-type": "application/json"
                    }
                    
                    req_data = json.dumps(payload).encode('utf-8')
                    req_obj = urllib.request.Request(url, data=req_data, headers=headers, method='POST')
                    with urllib.request.urlopen(req_obj, timeout=5) as response:
                        print("Email sent successfully via Brevo HTTP API")
        except Exception as e:
            print(f"Email bhejne me error: {e}")

        flash('Requirement published successfully!', 'success')
        return redirect(url_for('customer_dash'))
        
    my_reqs = Requirement.query.filter_by(customer_id=current_user.id).order_by(Requirement.id.desc()).all()
    
    for req in my_reqs:
        if hasattr(req, 'unlocked_by_shops') and req.unlocked_by_shops:
            for quote in req.unlocked_by_shops:
                shop_user = User.query.get(quote.shop_owner_id)
                if shop_user:
                    quote.shop_name = getattr(shop_user, 'shop_name', None) or getattr(shop_user, 'name', 'Shop Owner')
                    quote.shop_mobile = getattr(shop_user, 'mobile', 'N/A')
                else:
                    quote.shop_name = "Shop Owner"
                    quote.shop_mobile = "N/A"

    return render_template('customer_dash.html', my_reqs=my_reqs)

@app.route('/shop/dashboard', methods=['GET', 'POST'])
@login_required
def shop_dash():
    if current_user.role.lower() != 'shop_owner': 
        return redirect(url_for('login'))
    
    current_month = datetime.now().month
    if current_user.last_deduction_month != current_month:
        if current_user.wallet_balance >= 200:
            current_user.wallet_balance -= 200
            current_user.last_deduction_month = current_month
            current_user.is_plan_active = True
            db.session.commit()
            flash("Naye mahine ka Platform Fee (200 Credits) auto-deduct ho gaya hai. Aapka account active hai!", "success")
        else:
            current_user.is_plan_active = False
            db.session.commit()

    if not current_user.is_plan_active and current_user.wallet_balance >= 200:
        current_user.wallet_balance -= 200
        current_user.last_deduction_month = current_month
        current_user.is_plan_active = True
        db.session.commit()
        session['show_reactivation_popup'] = True
        flash("Recharge successful! Aapka account dobara chalu ho gaya hai.", "success")

    if request.method == 'POST':
        if not current_user.is_plan_active:
            flash("Aapka plan inactive hai. Nayi vacancy dalne ke liye pehle recharge karein.", "danger")
            return redirect(url_for('shop_dash'))

        person_need = request.form.get('person_need')
        if person_need: 
            new_vacancy = Vacancy(
                shop_owner_id=current_user.id, person_need=person_need,
                address=request.form.get('address'), task_type=request.form.get('task_type'),
                per_day_pay=request.form.get('per_day_pay'), description=request.form.get('description')
            )
            db.session.add(new_vacancy)
            db.session.commit()
            flash('Job Vacancy Published Successfully!', 'success')
        return redirect(url_for('shop_dash'))

    requirements = Requirement.query.order_by(Requirement.id.desc()).all()
    customers = {u.id: u for u in User.query.filter_by(role='customer').all()} 
    unlocked_leads = [lead.requirement_id for lead in UnlockedLead.query.filter_by(shop_owner_id=current_user.id).all()]
    workers = User.query.filter_by(role='worker', is_available=True).all()
    my_vacancies = Vacancy.query.filter_by(shop_owner_id=current_user.id).order_by(Vacancy.id.desc()).all()
    my_requests = PaymentRequest.query.filter_by(shop_owner_id=current_user.id).order_by(PaymentRequest.id.desc()).all()
    
    return render_template('shop_dash.html', requirements=requirements, customers=customers, 
                           unlocked_leads=unlocked_leads, workers=workers, 
                           get_unlock_cost=get_unlock_cost,
                           my_vacancies=my_vacancies, my_requests=my_requests)

@app.route('/unlock_lead/<int:req_id>', methods=['POST'])
@login_required
def unlock_lead(req_id):
    if current_user.role.lower() != 'shop_owner':
        return "Unauthorized", 403
        
    req = Requirement.query.get_or_404(req_id)
    
    try:
        budget_num = int(''.join(filter(str.isdigit, str(req.budget)))) if req.budget else 0
    except ValueError:
        budget_num = 0

    if budget_num <= 2000: credit_cost = 50
    elif budget_num <= 5000: credit_cost = 70
    elif budget_num <= 10000: credit_cost = 90
    elif budget_num <= 20000: credit_cost = 120
    elif budget_num <= 35000: credit_cost = 140
    else: credit_cost = 200
        
    already_unlocked = UnlockedLead.query.filter_by(shop_owner_id=current_user.id, requirement_id=req.id).first()
    if already_unlocked:
        flash('Yeh lead aapne pehle से hi unlock ki hui hai!', 'info')
        return redirect(url_for('shop_dash'))

    if current_user.wallet_balance >= credit_cost:
        current_user.wallet_balance -= credit_cost
        
        amount = request.form.get('amount')
        deadline = request.form.get('deadline')
        notes = request.form.get('notes')
        
        new_unlock = UnlockedLead(
            shop_owner_id=current_user.id, 
            requirement_id=req.id,
            amount=amount,       
            deadline=deadline,   
            notes=notes,          
            status='Pending'      
        )
        
        db.session.add(new_unlock)
        db.session.commit()
        flash(f'Lead successfully unlock ho gayi hai aur Quotation bhej diya gaya hai! {credit_cost} Credits deduct hue hain.', 'success')
    else:
        flash('Aapke wallet me sufficient credits nahi hain. Please recharge karein.', 'danger')
        
    return redirect(url_for('shop_dash'))

@app.route('/buy_credits_page')
@login_required
def buy_credits_page():
    if current_user.role != 'shop_owner': return "Unauthorized", 403
    settings = SiteSettings.query.first()
    upi_id = settings.admin_upi if settings else "admin@upi"
    return render_template('buy_credits.html', upi_id=upi_id)

@app.route('/submit_payment', methods=['POST'])
@login_required
def submit_payment():
    if current_user.role != 'shop_owner': return "Unauthorized", 403
    
    amount_raw = request.form.get('amount', '').strip()
    trx_id = request.form.get('trx_id', '').strip()

    if not amount_raw.isdigit() or not trx_id:
        flash("Please enter a valid amount and transaction ID.", "danger")
        return redirect(url_for('buy_credits_page'))

    amount = int(amount_raw)
    if amount <= 0:
        flash("Amount must be greater than zero.", "danger")
        return redirect(url_for('buy_credits_page'))

    new_req = PaymentRequest(shop_owner_id=current_user.id, amount=amount, trx_id=trx_id, status='Pending')
    db.session.add(new_req)
    db.session.commit()
    flash("Request sent to Admin successfully! Credits will be added upon approval.", "success")
    return redirect(url_for('shop_dash'))

@app.route('/worker/dashboard', methods=['GET', 'POST'])
@login_required
def worker_dash():
    if current_user.role != 'worker': return "Unauthorized", 403
    
    if request.method == 'POST':
        current_user.name = request.form.get('name')
        current_user.address = request.form.get('address')
        current_user.experience = request.form.get('experience')
        current_user.expertise = request.form.get('expertise')
        current_user.per_day_amount = request.form.get('per_day_amount')
        db.session.commit()
        flash('Profile Updated Successfully!', 'success')
        return redirect(url_for('worker_dash'))

    vacancies = Vacancy.query.order_by(Vacancy.id.desc()).all()
    shop_owners = {u.id: u for u in User.query.filter_by(role='shop_owner').all()}
    return render_template('worker_dash.html', vacancies=vacancies, shop_owners=shop_owners)

@app.route('/admin/dashboard')
@login_required
def admin_dash():
    if current_user.role != 'admin': return "Unauthorized", 403
    
    shop_owners = User.query.filter_by(role='shop_owner').all()
    workers = User.query.filter_by(role='worker').all()
    customers = User.query.filter_by(role='customer').order_by(User.id.desc()).all()
    
    all_users = User.query.all()
    total_reqs = Requirement.query.count()
    total_vacancies = Vacancy.query.count()
    pending_requests = PaymentRequest.query.filter_by(status='Pending').all()
    
    # NEW: Fetch reported leads for admin
    reported_leads = LeadReport.query.order_by(LeadReport.id.desc()).all()
    
    customer_req_counts = {}
    for c in customers:
        count = Requirement.query.filter_by(customer_id=c.id).count()
        customer_req_counts[c.id] = count
    
    settings = SiteSettings.query.first()
    admin_upi = settings.admin_upi if settings else "admin@upi"
    
    return render_template('admin_dash.html', 
                           shop_owners=shop_owners, 
                           workers=workers, 
                           customers=customers, 
                           customer_req_counts=customer_req_counts,
                           all_users=all_users, 
                           total_reqs=total_reqs, 
                           total_vacancies=total_vacancies, 
                           pending_requests=pending_requests, 
                           reported_leads=reported_leads,   # <--- Pass here
                           admin_upi=admin_upi)

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if current_user.role != 'admin': return "Unauthorized", 403
    
    if user_id == current_user.id:
        flash('Aap apne khud ke Admin account ko delete nahi kar sakte!', 'danger')
        return redirect(url_for('admin_dash'))

    user = User.query.get(user_id)
    
    if user:
        try:
            Quotation.query.filter(Quotation.shop_owner_id == user.id).delete(synchronize_session=False)

            if user.role == 'customer':
                user_reqs = Requirement.query.filter_by(customer_id=user.id).all()
                for req in user_reqs:
                    UnlockedLead.query.filter_by(requirement_id=req.id).delete(synchronize_session=False)
                    Quotation.query.filter_by(requirement_id=req.id).delete(synchronize_session=False)
                Requirement.query.filter_by(customer_id=user.id).delete(synchronize_session=False)
            
            elif user.role == 'shop_owner':
                UnlockedLead.query.filter_by(shop_owner_id=user.id).delete(synchronize_session=False)
                Vacancy.query.filter_by(shop_owner_id=user.id).delete(synchronize_session=False)
                PaymentRequest.query.filter_by(shop_owner_id=user.id).delete(synchronize_session=False)
                
            db.session.delete(user)
            db.session.commit()
            flash('User aur usse juda saara data successfully delete ho gaya.', 'success')
            
        except Exception as e:
            db.session.rollback() 
            print(f"Delete Error aaya hai: {e}") 
            flash('Error: Data delete nahi ho paya. System Error aaya hai.', 'danger')
            
    return redirect(url_for('admin_dash'))

@app.route('/admin/edit_user/<int:user_id>', methods=['POST'])
@login_required
def edit_user(user_id):
    if current_user.role != 'admin': return "Unauthorized", 403
    
    user = User.query.get(user_id)
    
    if user and request.method == 'POST':
        if request.form.get('name'):
            user.name = request.form.get('name').strip()
        if request.form.get('mobile'):
            user.mobile = request.form.get('mobile').strip()
        if request.form.get('email'):
            user.email = request.form.get('email').strip()
        if request.form.get('address'):
            user.address = request.form.get('address').strip()
            
        new_password = request.form.get('password')
        if new_password and new_password.strip():
            user.password = generate_password_hash(new_password.strip(), method='scrypt')
            
        if user.role == 'shop_owner' and 'wallet_balance' in request.form:
            try:
                user.wallet_balance = int(request.form.get('wallet_balance', user.wallet_balance))
            except ValueError:
                pass
            
        db.session.commit()
        flash(f'{user.name} ki details successfully update ho gayi hain.', 'success')
        
    return redirect(url_for('admin_dash'))

@app.route('/admin/update_upi', methods=['POST'])
@login_required
def update_upi():
    if current_user.role != 'admin': return "Unauthorized", 403
    settings = SiteSettings.query.first()
    if not settings:
        settings = SiteSettings()
        db.session.add(settings)
    settings.admin_upi = request.form.get('upi_id', 'admin@upi').strip()
    db.session.commit()
    flash('Admin UPI Updated Successfully.', 'success')
    return redirect(url_for('admin_dash'))

@app.route('/approve_payment/<int:req_id>/<action>', methods=['POST'])
@login_required
def approve_payment(req_id, action):
    if current_user.role != 'admin': return "Unauthorized", 403
    req = PaymentRequest.query.get_or_404(req_id)
    
    if req.status != 'Pending':
        flash('Yeh payment request pehle hi process ho chuki hai.', 'warning')
        return redirect(url_for('admin_dash'))

    shop_owner = User.query.get(req.shop_owner_id)
    
    if action == 'approve':
        if shop_owner:
            shop_owner.wallet_balance += req.amount
        req.status = 'Approved'
        flash(f'Payment Approved. ₹{req.amount} added to Shop Owner.', 'success')
    else:
        req.status = 'Rejected'
        flash('Payment Request Rejected.', 'danger')
        
    db.session.commit()
    return redirect(url_for('admin_dash'))

# --- HELPER & SYSTEM ROUTES ---
@app.route('/create_admin')
def create_admin():
    admin = User.query.filter_by(role='admin').first()
    admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')
    admin_email = os.environ.get('ADMIN_EMAIL') or os.environ.get('MAIL_USERNAME') or 'admin@kaamconnect.com'
    
    if not admin:
        hashed_pw = generate_password_hash(admin_password, method='scrypt')
        admin = User(role='admin', name='Super Admin', mobile='9999999999', email=admin_email, password=hashed_pw, address='Head Office')
        db.session.add(admin)
        db.session.commit()
        return f"Admin account created successfully! Mobile: 9999999999, Pass: {admin_password}"
    else:
        admin.email = admin_email
        admin.password = generate_password_hash(admin_password, method='scrypt')
        db.session.commit()
        return "Admin account already exists! Password & Email updated from environment variables successfully."

@app.route('/reset_db_danger_123')
def reset_db_safely():
    return "Database reset feature is locked for production security.", 403

# ================= EDIT & DELETE FUNCTIONALITIES =================
@app.route('/delete_requirement/<int:req_id>', methods=['POST'])
@login_required
def delete_requirement(req_id):
    if current_user.role != 'customer': return "Unauthorized", 403
    req = Requirement.query.filter_by(id=req_id, customer_id=current_user.id).first_or_404()
    db.session.delete(req)
    db.session.commit()
    flash('Aapki requirement successfully delete ho gayi hai!', 'success')
    return redirect(url_for('customer_dash'))

@app.route('/edit_requirement/<int:req_id>', methods=['POST'])
@login_required
def edit_requirement(req_id):
    if current_user.role != 'customer': return "Unauthorized", 403
    req = Requirement.query.filter_by(id=req_id, customer_id=current_user.id).first_or_404()
    
    req.category = request.form.get('category')
    req.budget = request.form.get('budget')
    req.deadline = request.form.get('deadline')
    req.description = request.form.get('description')
    
    db.session.commit()
    flash('Aapki requirement successfully update ho gayi hai!', 'success')
    return redirect(url_for('customer_dash'))

@app.route('/delete_vacancy/<int:vac_id>', methods=['POST'])
@login_required
def delete_vacancy(vac_id):
    if current_user.role.lower() != 'shop_owner': return "Unauthorized", 403
    vac = Vacancy.query.filter_by(id=vac_id, shop_owner_id=current_user.id).first_or_404()
    db.session.delete(vac)
    db.session.commit()
    flash('Job Vacancy successfully hata di gayi hai!', 'success')
    return redirect(url_for('shop_dash'))

@app.route('/worker/hide_profile', methods=['POST'])
@login_required
def worker_hide_profile():
    if current_user.role != 'worker': return "Unauthorized", 403
    
    current_user.is_available = False
    db.session.commit()
    flash('Aapki availability marketplace se hata di gayi hai!', 'success')
    return redirect(url_for('worker_dash'))

@app.route('/update_worker_profile', methods=['POST']) 
@login_required
def update_worker_profile():
    if current_user.role != 'worker': return "Unauthorized", 403
        
    current_user.name = request.form.get('name')
    current_user.address = request.form.get('address')
    current_user.experience = request.form.get('experience')
    current_user.expertise = request.form.get('expertise')
    current_user.per_day_amount = request.form.get('per_day_amount')
    current_user.is_available = True 
    
    db.session.commit()
    flash('Aapka profile successfully update aur activate ho gaya hai.', 'success')
    return redirect(url_for('worker_dash'))

@app.route('/submit_quotation/<int:worker_id>', methods=['POST'])
@login_required
def submit_quotation(worker_id):
    if current_user.role != 'shop_owner':
        flash("Sirf Shop Owners hi quotation bhej sakte hain.", "danger")
        return redirect(url_for('shop_dash'))

    try:
        amount = float(request.form.get('amount', 0))
    except ValueError:
        amount = 0.0

    deadline = request.form.get('deadline')
    notes = request.form.get('notes')

    new_quote = Quotation(
        shop_owner_id=current_user.id,
        worker_id=worker_id,
        amount=amount,
        deadline=deadline,
        notes=notes
    )
    db.session.add(new_quote)
    db.session.commit()

    flash("Quotation successfully submit ho gaya hai!", "success")
    return redirect(url_for('shop_dash'))

@app.route('/update_quote_status/<int:req_id>/<string:status_value>', methods=['POST', 'GET'])
@login_required
def update_quote_status(req_id, status_value):
    if current_user.role.lower() != 'shop_owner':
        return "Unauthorized", 403

    unlocked_lead = UnlockedLead.query.filter_by(requirement_id=req_id, shop_owner_id=current_user.id).first()
    
    if unlocked_lead:
        if status_value in ['Interested', 'Not Interested']:
            unlocked_lead.status = status_value
            db.session.commit()
            flash(f"Response successfully updated to: {status_value}!", "success")
    else:
        flash("Lead ka koi record nahi mila!", "danger")
        
    return redirect(url_for('shop_dash'))

@app.route('/admin/send_broadcast', methods=['POST'])
@login_required
def admin_send_broadcast():
    if current_user.role != 'admin':
        return "Unauthorized", 403
        
    target_role = request.form.get('target_role')
    subject = request.form.get('subject')
    message_body = request.form.get('message')
    
    import base64
    attachments_list = []
    uploaded_file = request.files.get('attachment')
    if uploaded_file and uploaded_file.filename:
        file_bytes = uploaded_file.read()
        encoded_file = base64.b64encode(file_bytes).decode('utf-8')
        attachments_list.append({
            "content": encoded_file,
            "name": uploaded_file.filename
        })

    if target_role == 'all':
        users = User.query.filter(User.email != None).all()
    else:
        users = User.query.filter_by(role=target_role).filter(User.email != None).all()
        
    recipient_emails = [u.email for u in users if u.email]
    
    if recipient_emails:
        try:
            api_key = os.environ.get('BREVO_API_KEY')
            sender_email = os.environ.get('MAIL_USERNAME', 'no-reply@kaamconnect.com')
            
            if api_key and sender_email:
                import urllib.request
                import json

                url = "https://api.brevo.com/v3/smtp/email"
                payload = {
                    "sender": {"name": "Kaamconnect Admin", "email": sender_email},
                    "to": [{"email": email} for email in recipient_emails],
                    "subject": subject,
                    "htmlContent": f"""
                    <html>
                        <body>
                            <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #ddd; border-radius: 5px;">
                                <h2 style="color: #0275d8;">🎯 Important Notice from Kaamconnect</h2>
                                <p>{message_body.replace(chr(10), '<br>')}</p>
                                <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
                                <p style="font-size: 12px; color: #777;">Aapko yeh email Kaamconnect Admin ki taraf se bheja gaya hai.</p>
                            </div>
                        </body>
                    </html>
                    """
                }
                
                if attachments_list:
                    payload["attachment"] = attachments_list

                headers = {
                    "accept": "application/json",
                    "api-key": api_key,
                    "content-type": "application/json"
                }
                
                req_data = json.dumps(payload).encode('utf-8')
                req_obj = urllib.request.Request(url, data=req_data, headers=headers, method='POST')
                
                with urllib.request.urlopen(req_obj, timeout=15) as response:
                    flash(f'Broadcast email successfully {len(recipient_emails)} logo ko bhej di gayi hai!', 'success')
        except Exception as e:
            flash(f'Email bhejne mein error aaya: {e}', 'danger')
    else:
        flash('Is category mein koi valid email address nahi mila.', 'warning')
        
    return redirect(url_for('admin_dash'))

@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/shops')
def registered_shops():
    shops = User.query.filter_by(role='shop_owner').all() 
    return render_template('shops.html', shops=shops)

@app.route('/shop/<int:shop_id>')
def shop_detail(shop_id):
    shop = User.query.get_or_404(shop_id)
    return render_template('shop_detail.html', shop=shop)

@app.before_request
def make_session_permanent():
    session.permanent = True

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=False)
