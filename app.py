from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta, datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'super_secret_key_for_local')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(hours=8)

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
    last_deduction_month = db.Column(db.Integer, default=datetime.now().month)
    is_plan_active = db.Column(db.Boolean, default=True)

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

class Quotation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shop_owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    worker_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) # Agar worker ko bhej rahe hain
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'), nullable=True)       # Agar kisi job post par bhej rahe hain
    
    amount = db.Column(db.Float, nullable=False)         # Estimate Amount
    deadline = db.Column(db.String(100), nullable=False)   # Kam kitne din me hoga (e.g., "3 Days")
    notes = db.Column(db.Text, nullable=True)            # Extra instructions/Notes
    status = db.Column(db.String(20), default='Pending') # Pending, Interested, Not Interested
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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
        
        # Safe Integer handling for per_day_amount (InvalidTextRepresentation Fix)
        per_day_raw = request.form.get('per_day_amount')
        per_day_amount = int(per_day_raw) if per_day_raw and per_day_raw.strip() else None

        # Check karein ki number pehle se register na ho
        user_exists = User.query.filter_by(mobile=mobile).first()
        if user_exists:
            flash('Mobile number pehle se registered hai!', 'danger')
            return redirect(url_for('signup', role=role))

        # Password ko securely hash karein
        hashed_password = generate_password_hash(password, method='scrypt')
        
        # Naya user object create karein (with is_available=True)
        new_user = User(
            role=role,
            mobile=mobile,
            password=hashed_password,
            name=name,
            email=email,
            address=address,
            experience=experience,
            expertise=expertise,
            per_day_amount=per_day_amount,
            wallet_balance=50,           # 🔥 YAHAN 0 KO 50 KAR DIYA HAI
            is_available=True
        )
        
        db.session.add(new_user)
        db.session.commit() # DB me save ho gaya
        
        # 🔥 FIRST TIME AUTO-LOGIN: User ko password bina daale turant login karwayein
        login_user(new_user)

        # 🔥 WELCOME POPUP TRIGGER (Sirf Shop Owner ke liye)
        if new_user.role == 'shop_owner':
            session['show_welcome_popup'] = True
        
        flash('Account successfully ban gaya hai aur aap login ho chuke hain!', 'success')
        
        # Role ke hisab se sahi dashboard par redirect karein
        if new_user.role == 'customer':
            return redirect(url_for('customer_dash'))
        elif new_user.role == 'shop_owner':
            return redirect(url_for('shop_dash'))
        elif new_user.role == 'worker':
            return redirect(url_for('worker_dash'))
            
        return redirect(url_for('index'))
        
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
    if current_user.role.lower() != 'shop_owner': 
        return redirect(url_for('login'))
    
    # =========================================================
    # 🔥 NEW SYSTEM: SUBSCRIPTION AUTO-DEDUCTION LOGIC
    # =========================================================
    current_month = datetime.now().month

    # 1. Mahina badal gaya hai, toh deduction check karo (Auto-Deduct on 1st)
    if current_user.last_deduction_month != current_month:
        if current_user.wallet_balance >= 200:
            current_user.wallet_balance -= 200
            current_user.last_deduction_month = current_month
            current_user.is_plan_active = True
            db.session.commit()
            flash("Naye mahine ka Platform Fee (200 Credits) auto-deduct ho gaya hai. Aapka account active hai!", "success")
        else:
            # Balance nahi hai toh turant account LOCK
            current_user.is_plan_active = False
            db.session.commit()

    # 2. Agar account Blocked tha, aur dukaandar ne ab recharge kar liya (Balance >= 200)
    if not current_user.is_plan_active and current_user.wallet_balance >= 200:
        current_user.wallet_balance -= 200
        current_user.last_deduction_month = current_month
        current_user.is_plan_active = True
        db.session.commit()
        
        # 🔥 YEH NAYI LINE ADD KI HAI (Success popup dikhane ke liye)
        session['show_reactivation_popup'] = True
        
        flash("Recharge successful! Aapka account dobara chalu ho gaya hai.", "success")
    # =========================================================

    if request.method == 'POST':
        # SECURITY CHECK: Agar plan inactive hai, toh vacancy post mat karne do
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

    # Puraana Data Fetching Logic (Same to Same)
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
    
    # 🔥 NEW LOGIC: Budget ko integer me badlein aur exact range cost nikalen
    try:
        budget_num = int(''.join(filter(str.isdigit, str(req.budget)))) if req.budget else 0
    except ValueError:
        budget_num = 0

    # Aapki batayi hui exact ranges backend par lagayi hain:
    if budget_num <= 2000:
        credit_cost = 50
    elif budget_num <= 5000:
        credit_cost = 70
    elif budget_num <= 10000:
        credit_cost = 90
    elif budget_num <= 20000:
        credit_cost = 120
    elif budget_num <= 35000:
        credit_cost = 140
    else:
        credit_cost = 200
        
    # Check karein ki dukanwala isse pehle se unlock toh nahi kar chuka hai
    already_unlocked = UnlockedLead.query.filter_by(shop_owner_id=current_user.id, requirement_id=req.id).first()
    if already_unlocked:
        flash('Yeh lead aapne pehle se hi unlock ki hui hai!', 'info')
        return redirect(url_for('shop_dash'))

    # Wallet Balance verification
    if current_user.wallet_balance >= credit_cost:
        current_user.wallet_balance -= credit_cost
        new_unlock = UnlockedLead(shop_owner_id=current_user.id, requirement_id=req.id)
        
        db.session.add(new_unlock)
        db.session.commit()
        flash(f'Lead successfully unlock ho gayi hai! {credit_cost} Credits deduct hue hain.', 'success')
    else:
        flash('Aapke wallet me sufficiant credits nahi hain. Please recharge karein.', 'danger')
        
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
    
    # 🔥 NAYA CODE: Sirf Customers ka data nikalna
    customers = User.query.filter_by(role='customer').order_by(User.id.desc()).all()
    
    all_users = User.query.all()
    total_reqs = Requirement.query.count()
    total_vacancies = Vacancy.query.count()
    pending_requests = PaymentRequest.query.filter_by(status='Pending').all()
    
    # 🔥 NAYA CODE: Har customer ne kitni requirements daali hain, uska count dictionary me save karna
    customer_req_counts = {}
    for c in customers:
        count = Requirement.query.filter_by(customer_id=c.id).count()
        customer_req_counts[c.id] = count
    
    settings = SiteSettings.query.first()
    admin_upi = settings.admin_upi if settings else "admin@upi"
    
    # render_template me customers aur customer_req_counts variables ko add kar diya
    return render_template('admin_dash.html', 
                           shop_owners=shop_owners, 
                           workers=workers, 
                           customers=customers, 
                           customer_req_counts=customer_req_counts,
                           all_users=all_users, 
                           total_reqs=total_reqs, 
                           total_vacancies=total_vacancies, 
                           pending_requests=pending_requests, 
                           admin_upi=admin_upi)

@app.route('/admin/delete_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
def delete_user(user_id):
    if current_user.role != 'admin': return "Unauthorized", 401
    
    user = User.query.get(user_id)
    
    if user:
        try:
            # Agar delete hone wala user CUSTOMER hai:
            if user.role == 'customer':
                # Uski saari requirements (jobs) nikal lo
                user_reqs = Requirement.query.filter_by(customer_id=user.id).all()
                for req in user_reqs:
                    # synchronize_session=False add kiya hai taaki strict delete ho bina session conflict ke
                    UnlockedLead.query.filter_by(requirement_id=req.id).delete(synchronize_session=False)
                
                # Fir customer ki saari requirements delete karo
                Requirement.query.filter_by(customer_id=user.id).delete(synchronize_session=False)
            
            # Agar delete hone wala user SHOP OWNER hai:
            elif user.role == 'shop_owner':
                # Usne jitni leads unlock ki thi, unka record hatao
                UnlockedLead.query.filter_by(shop_owner_id=user.id).delete(synchronize_session=False)
                
            # Ab aakhir mein safely User ko delete kar do
            db.session.delete(user)
            db.session.commit()
            flash('User aur usse juda saara data successfully delete ho gaya.', 'success')
            
        except Exception as e:
            db.session.rollback() # Error aane par database ko safe rakho
            print(f"Delete Error aaya hai: {e}") # Yeh aapko Render logs mein dikh jayega agar kuch fasa toh
            flash('Error: Data delete nahi ho paya. System Error aaya hai.', 'danger')
            
    return redirect(url_for('admin_dash'))

@app.route('/admin/edit_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    if current_user.role != 'admin': return "Unauthorized", 401
    
    user = User.query.get(user_id)
    
    # Sirf tabhi update chalega jab request POST hogi (Form submit hone par)
    if user and request.method == 'POST':
        # SAFE UPDATE
        if 'name' in request.form:
            user.name = request.form.get('name')
        if 'mobile' in request.form:
            user.mobile = request.form.get('mobile')
        if 'email' in request.form:
            user.email = request.form.get('email')
        if 'address' in request.form:
            user.address = request.form.get('address')
            
        # Shop Owner ke liye special wallet balance handler
        if user.role == 'shop_owner' and 'wallet_balance' in request.form:
            user.wallet_balance = request.form.get('wallet_balance', user.wallet_balance)
            
        db.session.commit()
        flash(f'{user.name} ki details successfully update ho gayi hain.', 'success')
        
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

# =======================================================
# UTILITY FUNCTION: BUDGET KE HISAB SE CREDIT CALCULATE KARNA
# =======================================================
def get_unlock_cost(budget_str):
    try:
        # Budget string se saare comma aur extra space hatakar number me badlein
        if not budget_str:
            return 50  # Minimum cost agar budget khali ho
        
        # Agar budget string me text ho (jaise "₹2,000"), toh sirf digits nikalne ke liye:
        budget = int(''.join(filter(str.isdigit, str(budget_str))))
        
        if budget <= 2000:
            return 50
        elif budget <= 5000:
            return 70
        elif budget <= 10000:
            return 90
        elif budget <= 20000:
            return 120
        elif budget <= 35000:
            return 140
        else:
            return 200
    except:
        return 50  # Kisi bhi error ke case me minimum 50 credits safe rakhna

# 1. Quotation Submit karne ka Route
@app.route('/submit_quotation/<int:worker_id>', methods=['POST'])
@login_required
def submit_quotation(worker_id):
    if current_user.role != 'shop_owner':
        flash("Sirf Shop Owners hi quotation bhej sakte hain.", "danger")
        return redirect(url_for('dashboard'))

    amount = request.form.get('amount')
    deadline = request.form.get('deadline')
    notes = request.form.get('notes')

    # Naya quotation record save karein
    new_quote = Quotation(
        shop_owner_id=current_user.id,
        worker_id=worker_id,
        amount=amount,
        deadline=deadline,
        notes=notes
    )
    db.session.add(new_quote)
    db.session.commit()

    flash("Quotation successfully submit ho gaya hai! User ko notify kar diya gaya hai.", "success")
    return redirect(url_for('dashboard'))


# 2. Status Update karne ka Route (Interested / Not Interested)
@app.route('/update_quote_status/<int:quote_id>/<string:status_value>')
@login_required
def update_quote_status(quote_id, status_value):
    quote = Quotation.query.get_or_404(quote_id)
    
    # Check ki sahi user change kar raha hai
    if status_value in ['Interested', 'Not Interested']:
        quote.status = status_value
        db.session.commit()
        flash(f"Status updated to {status_value}!", "success")
        
    return redirect(url_for('dashboard'))

@app.before_request
def make_session_permanent():
    session.permanent = True


if __name__ == '__main__':
    app.run(debug=True)
