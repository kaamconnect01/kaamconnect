from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta
import os

app = Flask(__name__)

# Config
app.secret_key = os.environ.get("SECRET_KEY", "kaam_connect_secret_123")
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30) 

db_url = os.environ.get('DATABASE_URL', 'sqlite:///portal.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ================= DB MODELS ================= #

class User(db.Model):
    __tablename__ = 'users' 
    id = db.Column(db.Integer, primary_key=True) # Changed from user_id to id
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
    customer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    budget = db.Column(db.Integer, nullable=False)
    deadline = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default="Pending")
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

class UnlockedContact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    requirement_id = db.Column(db.Integer, db.ForeignKey('requirement.id'))

class JobVacancy(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    work_type = db.Column(db.String(100), nullable=False)
    per_day_salary = db.Column(db.Integer, nullable=False)
    address = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

class AdminSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    upi_id = db.Column(db.String(100), default="admin@upi")

class CreditRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    amount = db.Column(db.Integer, nullable=False) 
    utr_number = db.Column(db.String(100), unique=True, nullable=False) 
    status = db.Column(db.String(20), default="Pending") 
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

# ================= ROUTES ================= #

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/signup_login', methods=['GET', 'POST'])
def signup_login():
    if request.method == 'POST':
        action = request.form.get('action')
        mobile = request.form.get('mobile')
        
        if action == 'login':
            user = User.query.filter_by(mobile=mobile).first()
            if user:
                if user.role == 'customer' or check_password_hash(user.password, request.form.get('password')):
                    session.permanent = True
                    session['user_id'] = user.id
                    session['role'] = user.role
                    return redirect(url_for(f'dashboard_{user.role}'))
            flash("Invalid credentials", "danger")
        
        elif action and action.startswith('signup'):
            role = action.split('_')[1]
            if not User.query.filter_by(mobile=mobile).first():
                new_user = User(role=role, mobile=mobile, password=generate_password_hash(request.form.get('password', '')))
                db.session.add(new_user)
                db.session.commit()
                session['user_id'] = new_user.id
                session['role'] = role
                return redirect(url_for(f'dashboard_{role}'))
    return render_template('signup_login.html')

@app.route('/dashboard/customer')
def dashboard_customer():
    if session.get('role') != 'customer': return redirect(url_for('index'))
    return render_template('dashboard_customer.html', user=User.query.get(session['user_id']))

@app.route('/dashboard/shop')
def dashboard_shop():
    if session.get('role') != 'shop': return redirect(url_for('index'))
    return render_template('dashboard_shop.html', user=User.query.get(session['user_id']))

@app.route('/dashboard/worker')
def dashboard_worker():
    if session.get('role') != 'worker': return redirect(url_for('index'))
    return render_template('dashboard_worker.html', user=User.query.get(session['user_id']))

@app.route('/dashboard/admin')
def dashboard_admin():
    if session.get('role') != 'admin': return redirect(url_for('index'))
    return render_template('dashboard_admin.html', all_users=User.query.all(), credit_requests=CreditRequest.query.all(), admin=AdminSetting.query.first())

@app.route('/admin/update_upi', methods=['POST'])
def update_upi():
    if session.get('role') != 'admin': return redirect(url_for('index'))
    setting = AdminSetting.query.first() or AdminSetting()
    setting.upi_id = request.form.get('upi_id')
    db.session.add(setting)
    db.session.commit()
    return redirect(url_for('dashboard_admin'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Admin setup
        if not User.query.filter_by(role='admin').first():
            db.session.add(User(role='admin', mobile='admin', password=generate_password_hash('admin123')))
            db.session.add(AdminSetting(upi_id='admin@paytm'))
            db.session.commit()
    app.run(debug=True)
