import os
import json
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta, datetime
from zoneinfo import ZoneInfo
from pywebpush import webpush, WebPushException
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
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

# ================= DATABASE MODELS =================
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    mobile = db.Column(db.String(15), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(100), nullable=True)
    address = db.Column(db.Text, nullable=True)
    experience = db.Column(db.String(50), nullable=True)
    expertise = db.Column(db.String(100), nullable=True)
    wallet_balance = db.Column(db.Integer, default=0)
    per_day_amount = db.Column(db.Integer, nullable=True)
    is_available = db.Column(db.Boolean, default=True)
    last_deduction_month = db.Column(db.Integer, default=datetime.now().month)
    is_plan_active = db.Column(db.Boolean, default=True)
    shop_name = db.Column(db.String(150), nullable=True)
    created_at = db.Column(db.DateTime, nullable=True)

    requirements = db.relationship('Requirement', backref='customer_user', cascade='all, delete-orphan')
    vacancies = db.relationship('Vacancy', backref='shop_owner_user', cascade='all, delete-orphan')
    unlocked_leads = db.relationship('UnlockedLead', backref='shop_owner_user', cascade='all, delete-orphan')
    payment_requests = db.relationship('PaymentRequest', backref='shop_owner_user', cascade='all, delete-orphan')
    push_subscriptions = db.relationship('PushSubscription', backref='user', cascade='all, delete-orphan')

class PushSubscription(db.Model):
    __tablename__ = 'push_subscriptions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    subscription_info = db.Column(db.Text, nullable=False)

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

# ================= PUSH & EMAIL NOTIFICATION HELPERS =================
def send_web_push(user_id, title, body, url="/"):
    """Browser Push Notification Bhejne ke liye Helper Function"""
    try:
        vapid_private_key = os.environ.get("VAPID_PRIVATE_KEY")
        vapid_claim_email = os.environ.get("VAPID_CLAIM_EMAIL", "mailto:admin@kaamconnect.com")
        
        if not vapid_private_key:
            return

        subscriptions = PushSubscription.query.filter_by(user_id=user_id).all()
        for sub in subscriptions:
            sub_info = json.loads(sub.subscription_info)
            payload = json.dumps({"title": title, "body": body, "url": url})
            try:
                webpush(
                    subscription_info=sub_info,
                    data=payload,
                    vapid_private_key=vapid_private_key,
                    vapid_claims={"sub": vapid_claim_email}
                )
            except WebPushException as ex:
                print(f"Web push failed: {ex}")
                if "404" in str(ex) or "410" in str(ex):
                    db.session.delete(sub)
                    db.session.commit()
    except Exception as e:
        print(f"Push notification error: {e}")

def notify_admin_new_user(user):
    try:
        api_key = os.environ.get('BREVO_API_KEY')
        admin_email = os.environ.get('ADMIN_EMAIL') or os.environ.get('MAIL_USERNAME')
        sender_email = os.environ.get('MAIL_USERNAME', 'no-reply@kaamconnect.com')
        
        if api_key and admin_email:
            import urllib.request
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
                <html><body>
                    <div style="font-family: Arial, sans-serif; padding: 20px;">
                        <h2>🎉 Naya User Register Hua Hai!</h2>
                        <ul>
                            <li><b>Role:</b> {user.role}</li>
                            <li><b>Name:</b> {user.name}</li>
                            <li><b>Mobile:</b> {user.mobile}</li>
                            {extra_info}
                        </ul>
                    </div>
                </body></html>
                """
            }
            headers = {"accept": "application/json", "api-key": api_key, "content-type": "application/json"}
            req_data = json.dumps(payload).encode('utf-8')
            req_obj = urllib.request.Request(url, data=req_data, headers=headers, method='POST')
            with urllib.request.urlopen(req_obj, timeout=5):
                pass
    except Exception as e:
        print(f"Admin notification mail error: {e}")

def send_email_notification(to_emails, subject, html_content):
    try:
        api_key = os.environ.get('BREVO_API_KEY')
        sender_email = os.environ.get('MAIL_USERNAME', 'no-reply@kaamconnect.com')
        
        if not api_key or not sender_email or not to_emails:
            return

        if isinstance(to_emails, str):
            to_emails = [to_emails]
            
        valid_emails = [{"email": email} for email in to_emails if email]
        if not valid_emails:
            return

        import urllib.request
        url = "https://api.brevo.com/v3/smtp/email"
        payload = {
            "sender": {"name": "Kaamconnect System", "email": sender_email},
            "to": valid_emails,
            "subject": subject,
            "htmlContent": html_content
        }
        headers = {"accept": "application/json", "api-key": api_key, "content-type": "application/json"}
        req_data = json.dumps(payload).encode('utf-8')
        req_obj = urllib.request.Request(url, data=req_data, headers=headers, method='POST')
        with urllib.request.urlopen(req_obj, timeout=5):
            pass
    except Exception as e:
        print(f"General Notification mail error: {e}")

# ================= PUSH NOTIFICATION ROUTES =================
@app.route('/sw.js')
def sw():
    return send_from_directory('static', 'sw.js', mimetype='application/javascript')

@app.route('/save-token', methods=['POST'])
@login_required
def save_token():
    sub_data = request.json
    if not sub_data:
        return jsonify({"error": "Invalid data"}), 400
    
    sub_json_str = json.dumps(sub_data)
    existing = PushSubscription.query.filter_by(user_id=current_user.id).first()
    if existing:
        existing.subscription_info = sub_json_str
    else:
        new_sub = PushSubscription(user_id=current_user.id, subscription_info=sub_json_str)
        db.session.add(new_sub)
    db.session.commit()
    return jsonify({"message": "Token Saved Successfully"})

# ================= ROUTES =================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        role = request.form.get('role', 'customer').strip()
        mobile = request.form.get('mobile', '').strip()
        password = request.form.get('password', '').strip()
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        address = request.form.get('address', '').strip()
        experience = request.form.get('experience', '').strip()
        expertise = request.form.get('expertise', '').strip()
        shop_name = request.form.get('shop_name', '').strip()
        
        per_day_raw = request.form.get('per_day_amount')
        per_day_amount = int(per_day_raw) if per_day_raw and per_day_raw.strip().isdigit() else None

        if not mobile or not password or not name:
            flash('Please fill all mandatory fields.', 'danger')
            return redirect(url_for('signup', role=role))

        user_exists = User.query.filter_by(mobile=mobile).first()
        if user_exists:
            flash('Mobile number pehle se registered hai!', 'danger')
            return redirect(url_for('signup', role=role))

        hashed_password = generate_password_hash(password, method='scrypt')
        ist_time = datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)
        
        new_user = User(
            role=role, mobile=mobile, password=hashed_password, name=name,
            email=email, address=address, experience=experience, expertise=expertise,
            shop_name=shop_name, per_day_amount=per_day_amount,
            wallet_balance=50, is_available=True, created_at=ist_time
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        notify_admin_new_user(new_user)
        login_user(new_user)

        if new_user.role == 'shop_owner':
            session['show_welcome_popup'] = True
        
        flash('Account successfully ban gaya hai aur aap login ho chuke hain!', 'success')
        
        if new_user.role == 'customer': return redirect(url_for('customer_dash'))
        elif new_user.role == 'shop_owner': return redirect(url_for('shop_dash'))
        elif new_user.role == 'worker': return redirect(url_for('worker_dash'))
        return redirect(url_for('index'))
        
    role = request.args.get('role', 'customer')
    return render_template('signup.html', role=role)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        mobile = request.form.get('mobile', '').strip()
        password = request.form.get('password', '').strip()
        user = User.query.filter_by(mobile=mobile).first()
        
        if user and check_password_hash(user.password, password):
            session.permanent = True
            login_user(user)
            if user.role == 'customer': return redirect(url_for('customer_dash'))
            elif user.role == 'shop_owner': return redirect(url_for('shop_dash'))
            elif user.role == 'worker': return redirect(url_for('worker_dash'))
            elif user.role == 'admin': return redirect(url_for('admin_dash'))
        flash('Invalid Mobile Number or Password', 'danger')
    return render_template('login.html')

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

        # Email notification to shop owners
        try:
            shop_owners = User.query.filter_by(role='shop_owner', is_available=True).all()
            recipient_emails = [shop.email for shop in shop_owners if shop.email]
            if recipient_emails:
                send_email_notification(recipient_emails, "📢 Naya Kaam Aaya Hai! (Urgent)", f"Category: {new_req.category}, Budget: ₹{new_req.budget}")
        except Exception as e:
            print(f"Email error: {e}")

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

    pub_key = os.environ.get("VAPID_PUBLIC_KEY")
    return render_template('customer_dash.html', my_reqs=my_reqs, public_key=pub_key)

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
            flash("Naye mahine ka Platform Fee (200 Credits) auto-deduct ho gaya hai.", "success")
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
            
            # Email & Push notification to workers
            workers = User.query.filter_by(role='worker', is_available=True).all()
            worker_emails = [w.email for w in workers if w.email]
            if worker_emails:
                send_email_notification(worker_emails, "📢 Nayi Job Vacancy Aayi Hai!", f"Task: {request.form.get('task_type')} | Pay: ₹{request.form.get('per_day_pay')}")
            
            for worker in workers:
                send_web_push(worker.id, "📢 नई जॉब वैकेंसी!", f"{current_user.shop_name or current_user.name} ने नई जॉब डाली है।", url="/worker/dashboard")
            
            flash('Job Vacancy Published Successfully!', 'success')
        return redirect(url_for('shop_dash'))

    requirements = Requirement.query.order_by(Requirement.id.desc()).all()
    customers = {u.id: u for u in User.query.filter_by(role='customer').all()} 
    unlocked_leads = [lead.requirement_id for lead in UnlockedLead.query.filter_by(shop_owner_id=current_user.id).all()]
    workers = User.query.filter_by(role='worker', is_available=True).all()
    my_vacancies = Vacancy.query.filter_by(shop_owner_id=current_user.id).order_by(Vacancy.id.desc()).all()
    my_requests = PaymentRequest.query.filter_by(shop_owner_id=current_user.id).order_by(PaymentRequest.id.desc()).all()
    
    pub_key = os.environ.get("VAPID_PUBLIC_KEY")
    return render_template('shop_dash.html', requirements=requirements, customers=customers, 
                           unlocked_leads=unlocked_leads, workers=workers, 
                           get_unlock_cost=lambda b: 50, # fallback
                           my_vacancies=my_vacancies, my_requests=my_requests, public_key=pub_key)

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
        flash('Yeh lead aapne pehle se hi unlock ki hui hai!', 'info')
        return redirect(url_for('shop_dash'))

    if current_user.wallet_balance >= credit_cost:
        current_user.wallet_balance -= credit_cost
        amount = request.form.get('amount')
        deadline = request.form.get('deadline')
        notes = request.form.get('notes')
        
        new_unlock = UnlockedLead(
            shop_owner_id=current_user.id, requirement_id=req.id,
            amount=amount, deadline=deadline, notes=notes, status='Pending'
        )
        db.session.add(new_unlock)
        db.session.commit()
        
        # Notify Customer via Email & Push
        customer = User.query.get(req.customer_id)
        if customer:
            if customer.email:
                send_email_notification(customer.email, "🎉 Kisi ne aapki requirement accept ki hai!", f"Shop: {current_user.shop_name or current_user.name} | Mobile: {current_user.mobile}")
            send_web_push(customer.id, "🎉 रिक्वायरमेंट अपडेट!", f"{current_user.shop_name or current_user.name} ने आपकी रिक्वायरमेंट स्वीकार कर ली है।", url="/customer/dashboard")
            
        flash(f'Lead successfully unlock ho gayi hai! {credit_cost} Credits deduct hue hain.', 'success')
    else:
        flash('Aapke wallet me sufficient credits nahi hain.', 'danger')
        
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
    new_req = PaymentRequest(shop_owner_id=current_user.id, amount=amount, trx_id=trx_id, status='Pending')
    db.session.add(new_req)
    db.session.commit()
    flash("Request sent to Admin successfully!", "success")
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
    pub_key = os.environ.get("VAPID_PUBLIC_KEY")
    return render_template('worker_dash.html', vacancies=vacancies, shop_owners=shop_owners, public_key=pub_key)

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
    
    customer_req_counts = {c.id: Requirement.query.filter_by(customer_id=c.id).count() for c in customers}
    settings = SiteSettings.query.first()
    admin_upi = settings.admin_upi if settings else "admin@upi"
    
    return render_template('admin_dash.html', shop_owners=shop_owners, workers=workers, customers=customers, 
                           customer_req_counts=customer_req_counts, all_users=all_users, total_reqs=total_reqs, 
                           total_vacancies=total_vacancies, pending_requests=pending_requests, admin_upi=admin_upi)

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
            flash('User successfully delete ho gaya.', 'success')
        except Exception as e:
            db.session.rollback() 
            flash('Error deleting user.', 'danger')
            
    return redirect(url_for('admin_dash'))

@app.route('/admin/edit_user/<int:user_id>', methods=['POST'])
@login_required
def edit_user(user_id):
    if current_user.role != 'admin': return "Unauthorized", 403
    user = User.query.get(user_id)
    if user and request.method == 'POST':
        if request.form.get('name'): user.name = request.form.get('name').strip()
        if request.form.get('mobile'): user.mobile = request.form.get('mobile').strip()
        if request.form.get('email'): user.email = request.form.get('email').strip()
        if request.form.get('address'): user.address = request.form.get('address').strip()
        new_password = request.form.get('password')
        if new_password and new_password.strip():
            user.password = generate_password_hash(new_password.strip(), method='scrypt')
        if user.role == 'shop_owner' and 'wallet_balance' in request.form:
            try: user.wallet_balance = int(request.form.get('wallet_balance', user.wallet_balance))
            except ValueError: pass
        db.session.commit()
        flash('Details updated successfully.', 'success')
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
        
        if shop_owner:
            if shop_owner.email:
                send_email_notification(shop_owner.email, "✅ Wallet Recharge Successful!", f"Aapki ₹{req.amount} ki payment request approve ho gayi hai.")
            send_web_push(shop_owner.id, "✅ वॉलेट रिचार्ज सफल!", f"आपके वॉलेट में ₹{req.amount} क्रेडिट कर दिए गए हैं।", url="/shop/dashboard")
            
        flash(f'Payment Approved. ₹{req.amount} added.', 'success')
    else:
        req.status = 'Rejected'
        flash('Payment Request Rejected.', 'danger')
        
    db.session.commit()
    return redirect(url_for('admin_dash'))

@app.route('/delete_requirement/<int:req_id>', methods=['POST'])
@login_required
def delete_requirement(req_id):
    if current_user.role != 'customer': return "Unauthorized", 403
    req = Requirement.query.filter_by(id=req_id, customer_id=current_user.id).first_or_404()
    db.session.delete(req)
    db.session.commit()
    flash('Requirement deleted successfully!', 'success')
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
    flash('Requirement updated successfully!', 'success')
    return redirect(url_for('customer_dash'))

@app.route('/delete_vacancy/<int:vac_id>', methods=['POST'])
@login_required
def delete_vacancy(vac_id):
    if current_user.role.lower() != 'shop_owner': return "Unauthorized", 403
    vac = Vacancy.query.filter_by(id=vac_id, shop_owner_id=current_user.id).first_or_404()
    db.session.delete(vac)
    db.session.commit()
    flash('Job vacancy deleted!', 'success')
    return redirect(url_for('shop_dash'))

@app.route('/worker/hide_profile', methods=['POST'])
@login_required
def worker_hide_profile():
    if current_user.role != 'worker': return "Unauthorized", 403
    current_user.is_available = False
    db.session.commit()
    flash('Profile hidden from marketplace!', 'success')
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
    flash('Profile updated successfully.', 'success')
    return redirect(url_for('worker_dash'))

@app.route('/submit_quotation/<int:worker_id>', methods=['POST'])
@login_required
def submit_quotation(worker_id):
    if current_user.role != 'shop_owner':
        flash("Unauthorized", "danger")
        return redirect(url_for('shop_dash'))

    try: amount = float(request.form.get('amount', 0))
    except ValueError: amount = 0.0

    deadline = request.form.get('deadline')
    notes = request.form.get('notes')

    new_quote = Quotation(shop_owner_id=current_user.id, worker_id=worker_id, amount=amount, deadline=deadline, notes=notes)
    db.session.add(new_quote)
    db.session.commit()
    
    worker = User.query.get(worker_id)
    if worker:
        if worker.email:
            send_email_notification(worker.email, "💼 Naya Kaam Ka Quotation Aaya Hai!", f"Amount: ₹{amount}")
        send_web_push(worker.id, "💼 नया जॉब ऑफर!", f"{current_user.shop_name or current_user.name} ने आपको ₹{amount} का कोटेशन भेजा है।", url="/worker/dashboard")

    flash("Quotation successfully submit ho gaya hai!", "success")
    return redirect(url_for('shop_dash'))

@app.route('/update_quote_status/<int:req_id>/<string:status_value>', methods=['POST', 'GET'])
@login_required
def update_quote_status(req_id, status_value):
    if current_user.role.lower() != 'shop_owner': return "Unauthorized", 403
    unlocked_lead = UnlockedLead.query.filter_by(requirement_id=req_id, shop_owner_id=current_user.id).first()
    if unlocked_lead:
        if status_value in ['Interested', 'Not Interested']:
            unlocked_lead.status = status_value
            db.session.commit()
            flash(f"Status updated to {status_value}", "success")
    return redirect(url_for('shop_dash'))

@app.route('/admin/send_broadcast', methods=['POST'])
@login_required
def admin_send_broadcast():
    if current_user.role != 'admin': return "Unauthorized", 403
    target_role = request.form.get('target_role')
    subject = request.form.get('subject')
    message_body = request.form.get('message')
    
    users = User.query.filter(User.email != None).all() if target_role == 'all' else User.query.filter_by(role=target_role).filter(User.email != None).all()
    recipient_emails = [u.email for u in users if u.email]
    
    if recipient_emails:
        try:
            send_email_notification(recipient_emails, subject, message_body.replace(chr(10), '<br>'))
            flash('Broadcast email sent successfully!', 'success')
        except Exception as e:
            flash(f'Error: {e}', 'danger')
    return redirect(url_for('admin_dash'))

@app.route('/terms')
def terms(): return render_template('terms.html')

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
    # Create default admin if missing
    if not User.query.filter_by(role='admin').first():
        hashed_pw = generate_password_hash('admin123', method='scrypt')
        admin = User(role='admin', name='Super Admin', mobile='9999999999', password=hashed_pw, address='Head Office')
        db.session.add(admin)
        db.session.commit()

if __name__ == '__main__':
    app.run(debug=False)
