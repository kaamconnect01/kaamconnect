from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta
import os

app = Flask(__name__)

# Security ke liye Secret Key ko environment variable se lenge
app.secret_key = os.environ.get("SECRET_KEY", "kaam_connect_permanent_secret_key_123")

# Neon DB (PostgreSQL) URL setup for Render
db_url = os.environ.get('DATABASE_URL', 'sqlite:///portal.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False


# 🔥 Fix: Isse session browser refresh ya incognito me drop nahi hoga
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30) 

db = SQLAlchemy(app)

# ================= DB MODELS ================= #

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(20), nullable=False) # 'customer', 'shop', 'worker', 'admin'
    mobile = db.Column(db.String(15), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(100), nullable=True)
    address = db.Column(db.String(255), nullable=True)
    password = db.Column(db.String(255), nullable=True) 
    
    experience = db.Column(db.String(50), nullable=True)
    expertise = db.Column(db.String(255), nullable=True)
    wallet_credit = db.Column(db.Integer, default=0)
    
    last_job_amount = db.Column(db.Integer, nullable=True)

class Requirement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    budget = db.Column(db.Integer, nullable=False)
    deadline = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default="Pending")
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    # Cleaned duplicate relationship line
    customer = db.relationship('User', backref='customer_requirements', foreign_keys=[customer_id])

class UnlockedContact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    requirement_id = db.Column(db.Integer, db.ForeignKey('requirement.id'))

class Vacancy(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    address = db.Column(db.String(255))
    work_type = db.Column(db.String(100))
    per_day_salary = db.Column(db.Integer)
    description = db.Column(db.Text)

class AdminSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    upi_id = db.Column(db.String(100), default="admin@upi")

class CreditRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    amount = db.Column(db.Integer, nullable=False) 
    utr_number = db.Column(db.String(100), unique=True, nullable=False) 
    status = db.Column(db.String(20), default="Pending") 
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    shop = db.relationship('User', backref=db.backref('credit_requests', lazy=True))

class JobVacancy(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    work_type = db.Column(db.String(100), nullable=False)
    per_day_salary = db.Column(db.Integer, nullable=False)
    address = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    shop = db.relationship('User', backref='vacancies', foreign_keys=[shop_id])

# ================= ROUTES ================= #

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/signup_login', methods=['GET', 'POST'])
def signup_login():
    if request.method == 'POST':
        action = request.form.get('action')
        
        # ================= LOGIN FLOW =================
        if action == 'login':
            mobile = request.form.get('mobile')
            password = request.form.get('password')
            user = User.query.filter_by(mobile=mobile).first()
            
            if user:
                if user.role == 'customer' or check_password_hash(user.password, password):
                    session.permanent = True # 🔥 Fix: Session Locked
                    session['user_id'] = user.id
                    session['role'] = user.role
                    return redirect(url_for(f'dashboard_{user.role}'))
            flash("Invalid credentials", "danger")
            return redirect(url_for('signup_login'))
            
        # ================= CUSTOMER SIGNUP =================
        elif action == 'signup_customer':
            mobile = request.form.get('mobile')
            if not User.query.filter_by(mobile=mobile).first():
                new_user = User(role='customer', mobile=mobile)
                db.session.add(new_user)
                db.session.commit()
                
                session.permanent = True # 🔥 Fix
                session['user_id'] = new_user.id
                session['role'] = 'customer'
                return redirect(url_for('dashboard_customer'))
            flash("Mobile already registered", "danger")
            
        # ================= SHOP & WORKER SIGNUP =================
        elif action in ['signup_shop', 'signup_worker']:
            role = 'shop' if action == 'signup_shop' else 'worker'
            mobile = request.form.get('mobile')
            
            if not User.query.filter_by(mobile=mobile).first():
                hashed_pw = generate_password_hash(request.form.get('password'))
                new_user = User(
                    role=role,
                    name=request.form.get('name'),
                    mobile=mobile,
                    email=request.form.get('email'),
                    address=request.form.get('address'),
                    password=hashed_pw,
                    experience=request.form.get('experience'),
                    expertise=request.form.get('expertise'),
                    last_job_amount=request.form.get('last_job_amount') if role == 'worker' else None
                )
                db.session.add(new_user)
                db.session.commit()
                
                session.permanent = True # 🔥 Fix
                session['user_id'] = new_user.id
                session['role'] = role
                flash("Account Created & Logged in successfully!", "success")
                return redirect(url_for(f'dashboard_{role}'))
            else:
                flash("Mobile already registered", "danger")
                
    return render_template('signup_login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# --- CUSTOMER ROUTES ---
@app.route('/dashboard/customer', methods=['GET', 'POST'])
def dashboard_customer():
    if session.get('role') != 'customer': return redirect(url_for('index'))
    
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('signup_login'))

    if request.method == 'POST':
        if request.form.get('update_profile'):
            user.name = request.form.get('name')
            user.email = request.form.get('email')
            user.address = request.form.get('address')
            db.session.commit()
            
        elif request.form.get('publish'):
            new_req = Requirement(
                customer_id=user.id,
                category=request.form.get('category'),
                budget=request.form.get('budget'),
                deadline=request.form.get('deadline'),
                description=request.form.get('description')
            )
            db.session.add(new_req)
            db.session.commit()
            flash("Requirement Published!", "success")
            
    my_reqs = Requirement.query.filter_by(customer_id=user.id).all()
    return render_template('dashboard_customer.html', user=user, reqs=my_reqs)

# --- SHOP OWNER ROUTES ---
@app.route('/dashboard/shop', methods=['GET', 'POST'])
def dashboard_shop():
    if session.get('role') != 'shop': 
        return redirect(url_for('index'))
        
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('signup_login'))
    
    if request.method == 'POST' and 'post_vacancy' in request.form:
        work_type = request.form.get('work_type')
        per_day_salary = request.form.get('per_day_salary')
        address = request.form.get('address')
        description = request.form.get('description')
        
        new_job = JobVacancy(shop_id=user.id, work_type=work_type, per_day_salary=per_day_salary, address=address, description=description)
        db.session.add(new_job)
        db.session.commit()
        flash("Job Vacancy successfully live ho gayi hai!", "success")
        return redirect(url_for('dashboard_shop'))
        
    all_reqs = Requirement.query.order_by(Requirement.id.desc()).all()
    workers = User.query.filter_by(role='worker').all()
    admin_settings = AdminSetting.query.first() 
    unlocked_records = UnlockedContact.query.filter_by(shop_id=user.id).all()
    unlocked = [record.requirement_id for record in unlocked_records]
    
    my_vacancies = JobVacancy.query.filter_by(shop_id=user.id).order_by(JobVacancy.id.desc()).all()
    
    return render_template('dashboard_shop.html', user=user, reqs=all_reqs, workers=workers, unlocked=unlocked, admin=admin_settings, my_vacancies=my_vacancies)


# --- WORKER ROUTES ---
@app.route('/dashboard/worker')
def dashboard_worker():
    if session.get('role') != 'worker': 
        return redirect(url_for('index'))
        
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('signup_login'))

    vacancies = JobVacancy.query.order_by(JobVacancy.id.desc()).all() 
    return render_template('dashboard_worker.html', user=user, vacancies=vacancies)

@app.route('/delete_vacancy/<int:vacancy_id>')
def delete_vacancy(vacancy_id):
    if session.get('role') != 'shop':
        return redirect(url_for('index'))
        
    vacancy = JobVacancy.query.get_or_404(vacancy_id)
    
    if vacancy.shop_id == session.get('user_id'):
        db.session.delete(vacancy)
        db.session.commit()
        flash("Vacancy successfully delete kar di gayi!", "success")
    else:
        flash("Unauthorized action!", "danger")
        
    return redirect(url_for('dashboard_shop'))

@app.route('/admin/delete_user/<int:user_id>')
def delete_user(user_id):
    if session.get('role') != 'admin': return redirect(url_for('index'))
    
    user = User.query.get(user_id)
    if user:
        db.session.delete(user)
        db.session.commit()
        flash(f"User {user.name} ko portal se delete kar diya gaya hai.", "success")
    else:
        flash("User nahi mila!", "danger")
        
    return redirect(url_for('dashboard_admin'))

# --- ADMIN ROUTES ---
@app.route('/dashboard/admin')
def dashboard_admin():
    if session.get('role') != 'admin': return redirect(url_for('index'))
    shops = User.query.filter_by(role='shop').all()
    workers = User.query.filter_by(role='worker').all()
    all_users = User.query.all()
    admin_settings = AdminSetting.query.first()
    
    credit_requests = CreditRequest.query.order_by(CreditRequest.id.desc()).all()
    
    return render_template('dashboard_admin.html', shops=shops, workers=workers, all_users=all_users, admin=admin_settings, credit_requests=credit_requests)

def calculate_required_credits(budget):
    try:
        b_val = int(budget)
    except:
        return 50 
        
    if b_val <= 15000:
        return 50
    elif b_val <= 50000:
        return 100
    elif b_val <= 150000:
        return 200
    else:
        return 300

@app.route('/unlock_contact/<int:req_id>')
def unlock_contact(req_id):
    if session.get('role') != 'shop': 
        return redirect(url_for('index'))
    
    user = User.query.get(session['user_id'])
    req = Requirement.query.get(req_id)
    
    credit_needed = calculate_required_credits(req.budget)
    
    if user.wallet_credit >= credit_needed:
        user.wallet_credit -= credit_needed
        new_unlock = UnlockedContact(shop_id=user.id, requirement_id=req.id)
        db.session.add(new_unlock)
        db.session.commit()
        flash(f"Contact Unlocked! {credit_needed} credits deducted.", "success")
    else:
        flash(f"Insufficient credits! Is lead ko unlock karne ke liye {credit_needed} credits chahiye.", "danger")
        
    return redirect(url_for('dashboard_shop'))

@app.route('/buy_credits', methods=['POST'])
def buy_credits():
    if session.get('role') != 'shop': return redirect(url_for('index'))
    
    shop_id = session['user_id']
    amount = request.form.get('amount')
    utr_number = request.form.get('utr_number')
    
    existing = CreditRequest.query.filter_by(utr_number=utr_number).first()
    if existing:
        flash("Ye Transaction ID pehle se submitted hai!", "danger")
        return redirect(url_for('dashboard_shop'))
        
    new_request = CreditRequest(shop_id=shop_id, amount=amount, utr_number=utr_number)
    db.session.add(new_request)
    db.session.commit()
    
    flash("Payment request submit ho gayi hai! Admin verify karke 10-15 mins me credits approve kar dega.", "success")
    return redirect(url_for('dashboard_shop'))

@app.route('/admin/action_credit/<int:req_id>/<string:action>')
def admin_action_credit(req_id, action):
    if session.get('role') != 'admin': return redirect(url_for('index'))
    
    req = CreditRequest.query.get(req_id)
    if not req or req.status != "Pending":
        flash("Invalid request or already processed.", "danger")
        return redirect(url_for('dashboard_admin'))
        
    if action == 'approve':
        shop_user = User.query.get(req.shop_id)
        shop_user.wallet_credit += req.amount
        req.status = "Approved"
        db.session.commit()
        flash(f"💸 {req.amount} Credits approve ho gaye hain user {shop_user.name} ke liye.", "success")
        
    elif action == 'reject':
        req.status = "Rejected"
        db.session.commit()
        flash("Request reject kar di gayi hai.", "warning")
        
    return redirect(url_for('dashboard_admin'))

@app.route('/admin/update_upi', methods=['POST'])
def update_upi():
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    
    new_upi = request.form.get('upi_id')
    
    admin_settings = AdminSetting.query.first()
    
    if not admin_settings:
        admin_settings = AdminSetting(upi_id=new_upi)
        db.session.add(admin_settings)
    else:
        admin_settings.upi_id = new_upi
        
    db.session.commit()
    flash("Admin UPI ID successfully update ho gayi hai!", "success")
    return redirect(url_for('dashboard_admin')) 

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(role='admin').first():
            admin = User(role='admin', mobile='admin', password=generate_password_hash('admin123'))
            db.session.add(admin)
            setting = AdminSetting(upi_id='admin@paytm')
            db.session.add(setting)
            db.session.commit()
    app.run(debug=True)