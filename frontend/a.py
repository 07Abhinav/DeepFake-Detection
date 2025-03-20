from flask import Flask, request, render_template, redirect, url_for, session, send_from_directory, flash
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from pymongo import MongoClient
import os
import bcrypt
from datetime import datetime
import re

# Initialize Flask app
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app)
app.secret_key = os.urandom(24)  # More secure secret key

# File upload configuration
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# MongoDB setup
try:
    client = MongoClient("mongodb+srv://abhinav29072003:Legend100@cluster0.t0jdg.mongodb.net/kyc")
    db = client['kyc_database']
    users_collection = db['users']
    kyc_collection = db['kyc_forms']
    # Create indexes for better query performance
    users_collection.create_index('email', unique=True)
    kyc_collection.create_index('pan_no', unique=True)
except Exception as e:
    print(f"MongoDB connection error: {e}")

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def validate_email(email):
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return re.match(pattern, email) is not None

def validate_pan(pan_no):
    pattern = r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$'
    return re.match(pattern, pan_no) is not None

def validate_aadhar(aadhar_no):
    pattern = r'^\d{12}$'
    return re.match(pattern, aadhar_no) is not None

def validate_phone(phone_no):
    pattern = r'^\d{10}$'
    return re.match(pattern, phone_no) is not None

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    if 'user' not in session:
        return redirect(url_for('login'))
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/')
def landing_page():
    return render_template('landing.html')

@app.route('/index')
def index():
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        if not validate_email(email):
            flash('Invalid email format')
            return redirect(url_for('signup'))

        if len(password) < 8:
            flash('Password must be at least 8 characters long')
            return redirect(url_for('signup'))

        try:
            if users_collection.find_one({'email': email}):
                flash('Email already registered')
                return redirect(url_for('signup'))

            hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
            users_collection.insert_one({'email': email, 'password': hashed_pw})
            flash('Registration successful! Please login.')
            return redirect(url_for('login'))
        except Exception as e:
            flash('An error occurred during registration')
            print(f"Registration error: {e}")
            return redirect(url_for('signup'))

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        try:
            user = users_collection.find_one({'email': email})
            if user and bcrypt.checkpw(password.encode('utf-8'), user['password']):
                session['user'] = email
                return redirect(url_for('kyc_form'))
            else:
                flash('Invalid email or password')
        except Exception as e:
            flash('An error occurred during login')
            print(f"Login error: {e}")

    return render_template('login.html')

@app.route('/kyc', methods=['GET', 'POST'])
def kyc_form():
    if 'user' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        try:
            # Validate form inputs
            if not validate_pan(request.form['pan_no']):
                flash('Invalid PAN number format')
                return redirect(url_for('kyc_form'))

            if not validate_aadhar(request.form['aadhar_no']):
                flash('Invalid Aadhar number format')
                return redirect(url_for('kyc_form'))

            if not validate_phone(request.form['phone_no']):
                flash('Invalid phone number format')
                return redirect(url_for('kyc_form'))

            form_data = {
                'user_email': session['user'],
                'name': request.form['name'],
                'father_name': request.form['father_name'],
                'gender': request.form['gender'],
                'dob': request.form['dob'],
                'nationality': request.form['nationality'],
                'pan_no': request.form['pan_no'],
                'aadhar_no': request.form['aadhar_no'],
                'phone_no': request.form['phone_no'],
                'address': request.form['address'],
                'city': request.form['city'],
                'state': request.form['state'],
                'pin_code': request.form['pin_code'],
                'date_signed': request.form['date_signed'],
                'submission_date': datetime.utcnow()
            }

            # Handle file uploads
            files = ['proof_address', 'aadhar_photo', 'e_signature']
            for file_key in files:
                if file_key not in request.files:
                    flash(f'No {file_key.replace("_", " ")} file provided')
                    return redirect(request.url)
                
                file = request.files[file_key]
                if file.filename == '':
                    flash(f'No {file_key.replace("_", " ")} file selected')
                    return redirect(request.url)
                
                if file and allowed_file(file.filename):
                    filename = secure_filename(f"{session['user']}_{file_key}_{file.filename}")
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)
                    form_data[file_key] = filename
                else:
                    flash(f'Invalid file type for {file_key.replace("_", " ")}')
                    return redirect(request.url)

            # Save form data to MongoDB
            kyc_collection.insert_one(form_data)
            
            # Render success template
            return render_template('success.html')

        except Exception as e:
            flash('An error occurred while submitting the form')
            print(f"KYC form submission error: {e}")
            return redirect(url_for('kyc_form'))

    return render_template('kyc.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    flash('You have been logged out')
    return redirect(url_for('index'))

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500

if __name__ == '__main__':
    app.run(debug=False)  # Set to False for production