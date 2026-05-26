from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'super_secret_key_for_local')

# DB Connection & SSL Drop Fix
db_url = os.environ.get('DATABASE_URL', 'sqlite:///portal.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
}
# Auto-Logout Fix (Session lasts 30 days)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

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
    email = db.Column(db.String(100))
    address = db.Column(db.Text)
    experience = db.Column(db.String(50))
    expertise = db.Column(db.String(100))
    wallet_balance = db.Column(db.Integer, default=0)
    per_day_amount = db.Column(db.Integer)
    is_available = db.Column(db.Boolean, default=True)

    # CASCADES: Agar user delete ho, toh uska sab data delete ho jaye (500 error fix)
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

class UnlockedLead(db.Model):
    __tablename__ = 'unlocked_lead'
    id = db.Column(db.Integer, primary_key=True)
    shop_owner_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    requirement_id = db.Column(db.Integer, db.ForeignKey('requirement.id'))

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

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ================= ROUTES =================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        role = request.form.get('role')
        mobile = request.form.get('mobile')
        password = request.form.get('password')
        name = request.form.get('name')
        email = request.form.get('email')
        address = request.form.get('address')
        experience = request.form.get('experience')
        expertise = request.form.get('expertise')
        
        # Safe Integer handling for per_day_amount
        per_day_raw = request.form.get('per_day_amount')
        per_day_amount = int(per_day_raw) if per_day_raw and per_day_raw.strip() else None

        # Check karein ki number pehle se register na ho
        user_exists = User.query.filter_by(mobile=mobile).first()
        if user_exists:
            flash('Mobile number pehle se registered hai!', 'danger')
            return redirect(url_for('signup', role=role))

        hashed_password = generate_password_hash(password, method='scrypt')
        
        new_user = User(
            role=role,
            mobile=mobile,
            password=hashed_password,
            name=name,
            email=email,
            address=address,
            experience=experience,
            expertise=expertise,
            per_day_amount=per_day_amount, # Ab yahan empty string nahi jayegi
            wallet_balance=0,
            is_available=True
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('Account successfully ban gaya hai! Login karein.', 'success')
        return redirect(url_for('login'))
        
    role = request.args.get('role', 'customer')
    return render_template('signup.html', role=role)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        mobile = request.form.get('mobile')
        password = request.form.get('password')
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
    if current_user.role != 'customer': return "Unauthorized", 401
    
    if request.method == 'POST':
        current_user.name = request.form.get('name')
        current_user.email = request.form.get('email')
        current_user.address = request.form.get('address')
        
        new_req = Requirement(
            customer_id=current_user.id,
            category=request.form.get('category'), budget=request.form.get('budget'),
            deadline=request.form.get('deadline'), description=request.form.get('description')
        )
        db.session.add(new_req)
        db.session.commit()
        flash('Requirement published successfully!', 'success')
        return redirect(url_for('customer_dash'))
        
    my_reqs = Requirement.query.filter_by(customer_id=current_user.id).order_by(Requirement.id.desc()).all()
    return render_template('customer_dash.html', my_reqs=my_reqs)

@app.route('/shop/dashboard', methods=['GET', 'POST'])
@login_required
def shop_dash():
    if current_user.role.lower() != 'shop_owner': return redirect(url_for('login'))
    
    if request.method == 'POST':
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
                           my_vacancies=my_vacancies, my_requests=my_requests)

@app.route('/unlock_lead/<int:req_id>', methods=['POST'])
@login_required
def unlock_lead(req_id):
    req = Requirement.query.get_or_404(req_id)
    credit_cost = 50
    if req.budget > 50000: credit_cost = 200
    elif req.budget > 10000: credit_cost = 100
    
    if current_user.wallet_balance >= credit_cost:
        current_user.wallet_balance -= credit_cost
        new_unlock = UnlockedLead(shop_owner_id=current_user.id, requirement_id=req.id)
        db.session.add(new_unlock)
        db.session.commit()
        flash('Lead Unlocked Successfully!', 'success')
    else:
        flash('Not enough credits in Wallet. Please recharge.', 'danger')
    return redirect(url_for('shop_dash'))

@app.route('/buy_credits_page')
@login_required
def buy_credits_page():
    if current_user.role != 'shop_owner': return "Unauthorized", 401
    settings = SiteSettings.query.first()
    upi_id = settings.admin_upi if settings else "admin@upi"
    return render_template('buy_credits.html', upi_id=upi_id)

@app.route('/submit_payment', methods=['POST'])
@login_required
def submit_payment():
    amount = request.form.get('amount')
    trx_id = request.form.get('trx_id')
    new_req = PaymentRequest(shop_owner_id=current_user.id, amount=amount, trx_id=trx_id, status='Pending')
    db.session.add(new_req)
    db.session.commit()
    flash("Request sent to Admin successfully! Credits will be added upon approval.", "success")
    return redirect(url_for('shop_dash'))

@app.route('/worker/dashboard', methods=['GET', 'POST'])
@login_required
def worker_dash():
    if current_user.role != 'worker': return "Unauthorized", 401
    
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
    if current_user.role != 'admin': return "Unauthorized", 401
    
    shop_owners = User.query.filter_by(role='shop_owner').all()
    workers = User.query.filter_by(role='worker').all()
    all_users = User.query.all()
    total_reqs = Requirement.query.count()
    total_vacancies = Vacancy.query.count()
    pending_requests = PaymentRequest.query.filter_by(status='Pending').all()
    
    settings = SiteSettings.query.first()
    admin_upi = settings.admin_upi if settings else "admin@upi"
    
    return render_template('admin_dash.html', shop_owners=shop_owners, workers=workers, 
                           all_users=all_users, total_reqs=total_reqs, 
                           total_vacancies=total_vacancies, pending_requests=pending_requests, admin_upi=admin_upi)

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if current_user.role != 'admin': return "Unauthorized", 401
    user = User.query.get(user_id)
    if user:
        db.session.delete(user)
        db.session.commit()
        flash('User and all related data deleted successfully.', 'success')
    return redirect(url_for('admin_dash'))

@app.route('/admin/edit_user/<int:user_id>', methods=['POST'])
@login_required
def edit_user(user_id):
    if current_user.role != 'admin': return "Unauthorized", 401
    user = User.query.get(user_id)
    if user:
        user.name = request.form.get('name')
        user.mobile = request.form.get('mobile')
        user.address = request.form.get('address')
        if user.role == 'shop_owner':
            user.wallet_balance = request.form.get('wallet_balance', user.wallet_balance)
        db.session.commit()
        flash('User details updated.', 'success')
    return redirect(url_for('admin_dash'))

@app.route('/admin/update_upi', methods=['POST'])
@login_required
def update_upi():
    if current_user.role != 'admin': return "Unauthorized", 401
    settings = SiteSettings.query.first()
    if not settings:
        settings = SiteSettings()
        db.session.add(settings)
    settings.admin_upi = request.form.get('upi_id')
    db.session.commit()
    flash('Admin UPI Updated Successfully.', 'success')
    return redirect(url_for('admin_dash'))

@app.route('/approve_payment/<int:req_id>/<action>', methods=['POST'])
@login_required
def approve_payment(req_id, action):
    if current_user.role != 'admin': return "Unauthorized", 401
    req = PaymentRequest.query.get_or_404(req_id)
    shop_owner = User.query.get(req.shop_owner_id)
    
    if action == 'approve':
        shop_owner.wallet_balance += req.amount
        req.status = 'Approved'
        flash(f'Payment Approved. ₹{req.amount} added to Shop Owner.', 'success')
    else:
        req.status = 'Rejected'
        flash('Payment Request Rejected.', 'danger')
        
    db.session.commit()
    return redirect(url_for('admin_dash'))

# --- HELPER ROUTES ---
@app.route('/create_admin')
def create_admin():
    if not User.query.filter_by(role='admin').first():
        hashed_pw = generate_password_hash('admin123')
        admin = User(role='admin', name='Super Admin', mobile='9999999999', password=hashed_pw, address='Head Office')
        db.session.add(admin)
        db.session.commit()
        return "Admin account created successfully! Mobile: 9999999999, Pass: admin123"
    return "Admin already exists!"

@app.route('/reset_db_danger_123')
def reset_db_safely():
    # CAUTION: Yeh route hit karne par sab delete hoke naya ban jayega!
    db.drop_all()
    db.create_all()
    return "Database Successfull Reset! Pura kachra saaf. URL se /create_admin pe jao abhi."

with app.app_context():
    db.create_all()

# =======================================================
# NAYE ROUTES: EDIT & DELETE FUNCTIONALITIES
# =======================================================

# 1. Customer: Requirement Delete karne ke liye
@app.route('/delete_requirement/<int:req_id>', methods=['POST'])
@login_required
def delete_requirement(req_id):
    if current_user.role != 'customer':
        return "Unauthorized", 403
    req = Requirement.query.filter_by(id=req_id, customer_id=current_user.id).first_or_404()
    db.session.delete(req)
    db.session.commit()
    flash('Aapki requirement successfully delete ho gayi hai!', 'success')
    return redirect(url_for('customer_dash'))

# 2. Customer: Requirement Edit karne ke liye
@app.route('/edit_requirement/<int:req_id>', methods=['POST'])
@login_required
def edit_requirement(req_id):
    if current_user.role != 'customer':
        return "Unauthorized", 403
    req = Requirement.query.filter_by(id=req_id, customer_id=current_user.id).first_or_404()
    
    req.category = request.form.get('category')
    req.budget = request.form.get('budget')
    req.deadline = request.form.get('deadline')
    req.description = request.form.get('description')
    
    db.session.commit()
    flash('Aapki requirement successfully update ho gayi hai!', 'success')
    return redirect(url_for('customer_dash'))

# 3. Shop Owner: Vacancy Delete karne ke liye (Aapke model ka naam Vacancy hai)
@app.route('/delete_vacancy/<int:vac_id>', methods=['POST'])
@login_required
def delete_vacancy(vac_id):
    if current_user.role.lower() != 'shop_owner':
        return "Unauthorized", 403
    vac = Vacancy.query.filter_by(id=vac_id, shop_owner_id=current_user.id).first_or_404()
    db.session.delete(vac)
    db.session.commit()
    flash('Job Vacancy successfully hata di gayi hai!', 'success')
    return redirect(url_for('shop_dash'))

# 4. Worker: Availability Chhipane/Hane ke liye (Jab kaam mil jaye)
@app.route('/worker/hide_profile', methods=['POST'])
@login_required
def worker_hide_profile():
    if current_user.role != 'worker':
        return "Unauthorized", 403
    
    current_user.is_available = False  # Isse worker marketplace se hide ho jayega
    db.session.commit()
    flash('Aapki availability marketplace se hata di gayi hai! Jab aapko fir se kaam chahiye ho, toh profile edit karke save kar dein.', 'success')
    return redirect(url_for('worker_dash'))

@app.route('/update_worker_profile', methods=['POST']) # Is route ka naam aapki app me jo ho wo check kar lena (jaise edit_profile ya update_profile)
@login_required
def update_worker_profile():
    if current_user.role != 'worker':
        return "Unauthorized", 403
        
    current_user.name = request.form.get('name')
    current_user.address = request.form.get('address')
    current_user.experience = request.form.get('experience')
    current_user.expertise = request.form.get('expertise')
    current_user.per_day_amount = request.form.get('per_day_amount')
    
    current_user.is_available = True  # Form save karte hi worker fir se AVAILABLE ho jayega!
    
    db.session.commit()
    flash('Aapka profile successfully update aur activate ho gaya hai.', 'success')
    return redirect(url_for('worker_dash'))


if __name__ == '__main__':
    app.run(debug=True)
