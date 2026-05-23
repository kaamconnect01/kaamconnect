from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta
import os

app = Flask(__name__)

# Security ke liye Secret Key
app.secret_key = os.environ.get("SECRET_KEY", "kaam_connect_permanent_secret_key_123")

# Neon DB (PostgreSQL) URL setup
db_url = os.environ.get('DATABASE_URL', 'sqlite:///portal.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Session config
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30) 

db = SQLAlchemy(app)

# ================= DB MODELS ================= #

class User(db.Model):
    __tablename__ = 'users' # Name change to 'users'
    user_id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(20), nullable=False) 
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
    customer_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False) # Updated reference
    category = db.Column(db.String(100), nullable=False)
    budget = db.Column(db.Integer, nullable=False)
    deadline = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default="Pending")
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    customer = db.relationship('User', backref='customer_requirements', foreign_keys=[customer_id])

class UnlockedContact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('users.user_id')) # Updated reference
    requirement_id = db.Column(db.Integer, db.ForeignKey('requirement.id'))

class AdminSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    upi_id = db.Column(db.String(100), default="admin@upi")

class CreditRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('users.user_id')) # Updated reference
    amount = db.Column(db.Integer, nullable=False) 
    utr_number = db.Column(db.String(100), unique=True, nullable=False) 
    status = db.Column(db.String(20), default="Pending") 
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    shop = db.relationship('User', backref=db.backref('credit_requests', lazy=True))

class JobVacancy(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False) # Updated reference
    work_type = db.Column(db.String(100), nullable=False)
    per_day_salary = db.Column(db.Integer, nullable=False)
    address = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    shop = db.relationship('User', backref='vacancies', foreign_keys=[shop_id])

# ================= INITIALIZE DB ON STARTUP ================= #
with app.app_context():
    db.create_all()
    # Admin create check
    if not User.query.filter_by(role='admin').first():
        admin = User(role='admin', mobile='admin', password=generate_password_hash('admin123'))
        db.session.add(admin)
        if not AdminSetting.query.first():
            setting = AdminSetting(upi_id='admin@paytm')
            db.session.add(setting)
        db.session.commit()

# ================= ROUTES ================= #
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/signup_login', methods=['GET', 'POST'])
def signup_login():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'login':
            mobile = request.form.get('mobile')
            password = request.form.get('password')
            user = User.query.filter_by(mobile=mobile).first()
            if user:
                if user.role == 'customer' or check_password_hash(user.password, password):
                    session.permanent = True
                    session['user_id'] = user.user_id
                    session['role'] = user.role
                    return redirect(url_for(f'dashboard_{user.role}'))
            flash("Invalid credentials", "danger")
            return redirect(url_for('signup_login'))
            
        elif action == 'signup_customer':
            mobile = request.form.get('mobile')
            if not User.query.filter_by(mobile=mobile).first():
                new_user = User(role='customer', mobile=mobile)
                db.session.add(new_user)
                db.session.commit()
                session.permanent = True
                session['user_id'] = new_user.user_id
                session['role'] = 'customer'
                return redirect(url_for('dashboard_customer'))
            flash("Mobile already registered", "danger")
            
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
                session.permanent = True
                session['user_id'] = new_user.user_id
                session['role'] = role
                flash("Account Created & Logged in successfully!", "success")
                return redirect(url_for(f'dashboard_{role}'))
    return render_template('signup_login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

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
            new_req = Requirement(customer_id=user.user_id, category=request.form.get('category'), budget=request.form.get('budget'), deadline=request.form.get('deadline'), description=request.form.get('description'))
            db.session.add(new_req)
            db.session.commit()
            flash("Requirement Published!", "success")
    my_reqs = Requirement.query.filter_by(customer_id=user.user_id).all()
    return render_template('dashboard_customer.html', user=user, reqs=my_reqs)

@app.route('/dashboard/shop', methods=['GET', 'POST'])
def dashboard_shop():
    if session.get('role') != 'shop': return redirect(url_for('index'))
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('signup_login'))
    if request.method == 'POST' and 'post_vacancy' in request.form:
        new_job = JobVacancy(shop_id=user.user_id, work_type=request.form.get('work_type'), per_day_salary=request.form.get('per_day_salary'), address=request.form.get('address'), description=request.form.get('description'))
        db.session.add(new_job)
        db.session.commit()
        flash("Job Vacancy live ho gayi hai!", "success")
        return redirect(url_for('dashboard_shop'))
    
    all_reqs = Requirement.query.order_by(Requirement.id.desc()).all()
    admin_settings = AdminSetting.query.first() 
    unlocked_records = UnlockedContact.query.filter_by(shop_id=user.user_id).all()
    unlocked = [record.requirement_id for record in unlocked_records]
    my_vacancies = JobVacancy.query.filter_by(shop_id=user.user_id).order_by(JobVacancy.id.desc()).all()
    return render_template('dashboard_shop.html', user=user, reqs=all_reqs, unlocked=unlocked, admin=admin_settings, my_vacancies=my_vacancies)

@app.route('/dashboard/worker')
def dashboard_worker():
    if session.get('role') != 'worker': return redirect(url_for('index'))
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('signup_login'))
    vacancies = JobVacancy.query.order_by(JobVacancy.id.desc()).all() 
    return render_template('dashboard_worker.html', user=user, vacancies=vacancies)

@app.route('/dashboard/admin')
def dashboard_admin():
    if session.get('role') != 'admin': return redirect(url_for('index'))
    all_users = User.query.all()
    admin_settings = AdminSetting.query.first()
    credit_requests = CreditRequest.query.order_by(CreditRequest.id.desc()).all()
    return render_template('dashboard_admin.html', all_users=all_users, admin=admin_settings, credit_requests=credit_requests)

@app.route('/unlock_contact/<int:req_id>')
def unlock_contact(req_id):
    if session.get('role') != 'shop': return redirect(url_for('index'))
    user = User.query.get(session['user_id'])
    req = Requirement.query.get(req_id)
    # Simple logic for credits
    credit_needed = 50
    if user.wallet_credit >= credit_needed:
        user.wallet_credit -= credit_needed
        new_unlock = UnlockedContact(shop_id=user.user_id, requirement_id=req.id)
        db.session.add(new_unlock)
        db.session.commit()
        flash("Contact Unlocked!", "success")
    else:
        flash("Insufficient credits!", "danger")
    return redirect(url_for('dashboard_shop'))

@app.route('/admin/action_credit/<int:req_id>/<string:action>')
def admin_action_credit(req_id, action):
    if session.get('role') != 'admin': return redirect(url_for('index'))
    req = CreditRequest.query.get(req_id)
    if action == 'approve':
        shop_user = User.query.get(req.shop_id)
        shop_user.wallet_credit += req.amount
        req.status = "Approved"
        db.session.commit()
    return redirect(url_for('dashboard_admin'))

if __name__ == '__main__':
    app.run(debug=True)
