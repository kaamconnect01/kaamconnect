from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os  # <--- YEH IMPORT HONA ZAROORI HAI

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'super_secret_key_for_local')

# Render/Neon ka Database URL lena
db_url = os.environ.get('DATABASE_URL', 'sqlite:///portal.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
db = SQLAlchemy(app)

with app.app_context():
    db.create_all()
    print("Database tables created successfully!")

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# ================= DATABASE MODELS =================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(20), nullable=False) # 'customer', 'shop_owner', 'worker', 'admin'
    name = db.Column(db.String(100), nullable=False)
    mobile = db.Column(db.String(15), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(100))
    address = db.Column(db.Text)
    
    # Shop Owner & Worker Specific
    experience = db.Column(db.String(50))
    expertise = db.Column(db.String(100))
    
    # Shop Owner Specific
    wallet_balance = db.Column(db.Integer, default=0)
    
    # Worker Specific
    per_day_amount = db.Column(db.Integer)

class Requirement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    category = db.Column(db.String(50)) # Flat furniture, bed, sofa, etc.
    budget = db.Column(db.Integer)
    deadline = db.Column(db.String(50))
    description = db.Column(db.Text)
    
class UnlockedLead(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shop_owner_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    requirement_id = db.Column(db.Integer, db.ForeignKey('requirement.id'))

class Vacancy(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shop_owner_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    person_need = db.Column(db.String(100))
    address = db.Column(db.Text)
    task_type = db.Column(db.String(100))
    per_day_pay = db.Column(db.Integer)
    description = db.Column(db.Text)

class SiteSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    admin_upi = db.Column(db.String(100), default='admin@upi')

class PaymentRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shop_owner_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    amount = db.Column(db.Integer, nullable=False)
    trx_id = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default='Pending') # Pending, Approved, Rejected

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ================= ROUTES =================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/signup/<role>', methods=['GET', 'POST'])
def signup(role):
    if request.method == 'POST':
        mobile = request.form.get('mobile')
        password = generate_password_hash(request.form.get('password'))
        
        if User.query.filter_by(mobile=mobile).first():
            flash('Mobile number already registered!')
            return redirect(url_for('signup', role=role))
            
        # Role ke hisaab se form fields save honge
        new_user = User(
            role=role,
            mobile=mobile,
            password=password,
            name=request.form.get('name', 'Customer'),
            email=request.form.get('email'),
            address=request.form.get('address'),
            experience=request.form.get('experience'),
            expertise=request.form.get('expertise'),
            per_day_amount=request.form.get('per_day_amount')
        )
        
        db.session.add(new_user)
        db.session.commit()

        login_user(new_user)  # User ko auto-login kar do
        flash('Signup Successful! Welcome.')

        # Role ke hisaab se sahi dashboard par bhej do
        if role == 'shop_owner':
            return redirect(url_for('shop_dash'))
        elif role == 'customer':
            return redirect(url_for('customer_dash'))
        else:
            return redirect(url_for('index'))
        # --------------------------
        
    return render_template('signup.html', role=role)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        mobile = request.form.get('mobile')
        password = request.form.get('password')
        user = User.query.filter_by(mobile=mobile).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            # Role ke hisab se dashboard par bhejo
            if user.role == 'customer': return redirect(url_for('customer_dash'))
            elif user.role == 'shop_owner': return redirect(url_for('shop_dash'))
            elif user.role == 'worker': return redirect(url_for('worker_dash'))
            elif user.role == 'admin': return redirect(url_for('admin_dash'))
        flash('Invalid Credentials')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# --- Dashboards (Aapki Requirements ke hisaab se) ---

@app.route('/customer/dashboard', methods=['GET', 'POST'])
@login_required
def customer_dash():
    if current_user.role != 'customer': return "Unauthorized"
    
    if request.method == 'POST':
        # Customer jab requirement form bharega, toh uski contact details bhi update ho jayengi
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
        flash('Aapki requirement successfully publish ho gayi hai!')
        return redirect(url_for('customer_dash'))
        
    # Purani publish ki hui requirements dikhane ke liye
    my_reqs = Requirement.query.filter_by(customer_id=current_user.id).all()
    return render_template('customer_dash.html', my_reqs=my_reqs)

@app.route('/shop/dashboard', methods=['GET', 'POST'])
@login_required
def shop_dash():
    # Role check ko safe banaya taaki Unauthorized error na aaye
    if current_user.role.lower() != 'shop_owner': 
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        # Vacancy publish logic (Ab error nahi aayega)
        person_need = request.form.get('person_need')
        if person_need: 
            new_vacancy = Vacancy(
                shop_owner_id=current_user.id,
                person_need=person_need,
                address=request.form.get('address'),
                task_type=request.form.get('task_type'),
                per_day_pay=request.form.get('per_day_pay'),
                description=request.form.get('description')
            )
            db.session.add(new_vacancy)
            db.session.commit()
            flash('Job Vacancy Published Successfully!')
        return redirect(url_for('shop_dash'))

    # Saari details fetch karna
    requirements = Requirement.query.all()
    customers = {u.id: u for u in User.query.filter_by(role='customer').all()} 
    unlocked_leads = [lead.requirement_id for lead in UnlockedLead.query.filter_by(shop_owner_id=current_user.id).all()]
    workers = User.query.filter_by(role='worker').all()
    my_vacancies = Vacancy.query.filter_by(shop_owner_id=current_user.id).all()
    
    # Admin ki UPI ID nikalna
    settings = SiteSettings.query.first()
    if not settings:
        settings = SiteSettings(admin_upi='admin@upi')
        db.session.add(settings)
        db.session.commit()

    # Shop owner ki payment history
    my_requests = PaymentRequest.query.filter_by(shop_owner_id=current_user.id).order_by(PaymentRequest.id.desc()).all()
    
    return render_template('shop_dash.html', 
                           requirements=requirements, 
                           customers=customers, 
                           unlocked_leads=unlocked_leads,
                           workers=workers,
                           my_vacancies=my_vacancies,
                           settings=settings,
                           my_requests=my_requests)

@app.route('/unlock_lead/<int:req_id>', methods=['POST'])
@login_required
def unlock_lead(req_id):
    req = Requirement.query.get(req_id)
    
    # Credit deduction logic budget k hisaab se
    credit_cost = 50
    if req.budget > 50000: credit_cost = 200
    elif req.budget > 10000: credit_cost = 100
    
    if current_user.wallet_balance >= credit_cost:
        current_user.wallet_balance -= credit_cost
        new_unlock = UnlockedLead(shop_owner_id=current_user.id, requirement_id=req.id)
        db.session.add(new_unlock)
        db.session.commit()
        flash('Lead Unlocked Successfully! Customer details aapko dikh rahi hain.')
    else:
        flash('Not enough credits. Please buy credits from your wallet!')
    return redirect(url_for('shop_dash'))

@app.route('/submit_payment', methods=['POST'])
@login_required
def submit_payment():
    amount = request.form.get('amount')
    trx_id = request.form.get('trx_id')
    
    # 1. New request create karo
    new_req = PaymentRequest(shop_owner_id=current_user.id, amount=amount, trx_id=trx_id, status='Pending')
    
    # 2. Database mein add aur commit zaroor karo!
    db.session.add(new_req)
    db.session.commit() 
    
    flash("Request sent to Admin!")
    return redirect(url_for('shop_dash'))

@app.route('/buy_credits', methods=['POST'])
@login_required
def buy_credits():
    # Abhi ke liye hum dummy recharge bana rahe hain. 
    # Real me yahan UPI/Razorpay API lagti hai.
    amount = int(request.form.get('amount', 0))
    current_user.wallet_balance += amount
    db.session.commit()
    flash(f'Success: {amount} Credits aapke wallet me add ho gaye hain!')
    return redirect(url_for('shop_dash'))

@app.route('/worker/dashboard', methods=['GET', 'POST'])
@login_required
def worker_dash():
    if current_user.role != 'worker': return "Unauthorized"
    
    if request.method == 'POST':
        # Worker Edit Profile Logic
        current_user.name = request.form.get('name')
        current_user.address = request.form.get('address')
        current_user.experience = request.form.get('experience')
        current_user.expertise = request.form.get('expertise')
        current_user.per_day_amount = request.form.get('per_day_amount')
        
        db.session.commit()
        flash('Profile Updated Successfully!')
        return redirect(url_for('worker_dash'))

    # Job tab k liye sari vacancies laani hai
    vacancies = Vacancy.query.all()
    # Jis shop owner ne vacancy dali hai, uski details dikhane k liye
    shop_owners = {u.id: u for u in User.query.filter_by(role='shop_owner').all()}
    
    return render_template('worker_dash.html', vacancies=vacancies, shop_owners=shop_owners)

# ================= ADMIN ROUTES =================

# Yeh route sirf ek baar chalana hai Admin account banane ke liye
@app.route('/create_admin')
def create_admin():
    if not User.query.filter_by(role='admin').first():
        hashed_pw = generate_password_hash('admin123')
        admin = User(role='admin', name='Super Admin', mobile='9999999999', password=hashed_pw, address='Head Office')
        db.session.add(admin)
        db.session.commit()
        return "Admin account created successfully! Mobile: 9999999999 | Password: admin123 . Ab /login par jakar login karein."
    return "Admin already exists!"

@app.route('/admin/dashboard')
@login_required
def admin_dash():
    if current_user.role != 'admin': return "Unauthorized"
    
    # Dashboard ke statistics aur lists
    shop_owners = User.query.filter_by(role='shop_owner').all()
    workers = User.query.filter_by(role='worker').all()
    all_users = User.query.all()
    
    total_reqs = Requirement.query.count()
    total_vacancies = Vacancy.query.count()
    
    return render_template('admin_dash.html', 
                           shop_owners=shop_owners, 
                           workers=workers, 
                           all_users=all_users,
                           total_reqs=total_reqs,
                           total_vacancies=total_vacancies)

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if current_user.role != 'admin': return "Unauthorized"
    user = User.query.get(user_id)
    if user:
        db.session.delete(user)
        db.session.commit()
        flash(f'User {user.name} deleted successfully!')
    return redirect(url_for('admin_dash'))

@app.route('/admin/edit_user/<int:user_id>', methods=['POST'])
@login_required
def edit_user(user_id):
    if current_user.role != 'admin': return "Unauthorized"
    user = User.query.get(user_id)
    if user:
        user.name = request.form.get('name')
        user.mobile = request.form.get('mobile')
        user.address = request.form.get('address')
        if user.role == 'shop_owner':
            user.wallet_balance = request.form.get('wallet_balance', user.wallet_balance)
        db.session.commit()
        flash('User details updated successfully!')
    return redirect(url_for('admin_dash'))

# ==========================================
# ADMIN PAYMENT CONTROLS
# ==========================================
@app.route('/admin/update_upi', methods=['POST'])
@login_required
def update_upi():
    if current_user.role != 'admin': return "Unauthorized"
    settings = SiteSettings.query.first()
    if not settings:
        settings = SiteSettings()
        db.session.add(settings)
    settings.admin_upi = request.form.get('upi_id')
    db.session.commit()
    flash('Admin UPI ID Updated Successfully!')
    return redirect(url_for('admin_dash'))

@app.route('/approve_payment/<int:req_id>/<action>', methods=['POST'])
@login_required
def approve_payment(req_id, action):
    if current_user.role != 'admin': return "Unauthorized"
    
    req = PaymentRequest.query.get_or_404(req_id)
    shop_owner = User.query.get(req.shop_owner_id)
    
    if action == 'approve':
        # Wallet update karo
        shop_owner.wallet_balance += req.amount
        req.status = 'Approved'
        flash(f'Request Approved! ₹{req.amount} added to Shop Owner.')
    else:
        req.status = 'Rejected'
        flash('Request Rejected.')
        
    db.session.commit()
    return redirect(url_for('admin_dash'))

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)
