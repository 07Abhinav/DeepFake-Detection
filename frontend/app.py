import os
import base64
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import re
from datetime import datetime
import cv2
import numpy as np
import tensorflow as tf
from PIL import Image
import glob
from dotenv import load_dotenv  # Import the load_dotenv function

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['MONGO_URI'] = os.getenv('MONGO_URI')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['ALLOWED_EXTENSIONS'] = {'mp4', 'jpg', 'jpeg', 'png', 'pdf'}

mongo = PyMongo(app)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Load your AI model
model = tf.keras.models.load_model("E:/Deepfake detection/DeepFake-Detection/models/vg16.h5")

def validate_input(input_type, value):
    validators = {
        'email': r'^[\w\.-]+@[\w\.-]+\.\w+$',
        'pan': r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$',
        'aadhar': r'^\d{12}$',
        'phone': r'^\d{10}$'
    }
    return re.match(validators.get(input_type, ''), value) is not None

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def extract_frames(video_path, output_folder, num_frames=10):
    os.makedirs(output_folder, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_indices = np.linspace(0, total_frames - 1, num_frames, dtype=int)
    frame_count = 0
    
    for idx in frame_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        success, image = cap.read()
        if success:
            cv2.imwrite(f"{output_folder}/frame_{frame_count}.jpg", image)
            frame_count += 1
    
    cap.release()

def preprocess_image(image_path):
    img = Image.open(image_path).convert("RGB")
    img = img.resize((224, 224))  # Adjust according to model input size
    img_array = np.array(img) / 255.0  # Normalize
    return np.expand_dims(img_array, axis=0)

def predict_frame(image_path):
    img_tensor = preprocess_image(image_path)
    prediction = model.predict(img_tensor)
    return "FAKE" if prediction[0] > 0.05 else "REAL"  # Assuming binary classification

@app.route('/')
def landing():
    return render_template('landing.html')

@app.route('/index')
def index():
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        if not validate_input('email', email):
            flash('Invalid email format')
            return redirect(url_for('signup'))

        if mongo.db.users.find_one({'email': email}):
            flash('Email already registered')
            return redirect(url_for('signup'))

        hashed_pw = generate_password_hash(password)
        mongo.db.users.insert_one({'email': email, 'password': hashed_pw})
        flash('Registration successful!')
        return redirect(url_for('login'))

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        user = mongo.db.users.find_one({'email': email})
        if user and check_password_hash(user['password'], password):
            session['email'] = email
            flash('Login successful!')
            return redirect(url_for('kyc'))
        
        flash('Invalid credentials')
    return render_template('login.html')

@app.route('/kyc', methods=['GET', 'POST'])
def kyc():
    if 'email' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        try:
            # Prepare file uploads
            aadhar_photo = request.files['aadhar_photo']
            e_signature = request.files['e_signature']

            # Secure filenames
            aadhar_filename = secure_filename(aadhar_photo.filename)
            signature_filename = secure_filename(e_signature.filename)

            # Save files
            aadhar_photo.save(os.path.join(app.config['UPLOAD_FOLDER'], aadhar_filename))
            e_signature.save(os.path.join(app.config['UPLOAD_FOLDER'], signature_filename))

            # Prepare KYC data
            kyc_data = {
                'name': request.form['name'],
                'fathers_name': request.form['fathers_name'],
                'gender': request.form['gender'],
                'dob': request.form['dob'],
                'nationality': request.form['nationality'],
                'pan_no': request.form['pan_no'],
                'aadhar_no': request.form['aadhar_no'],
                'phone_no': request.form['phone_no'],
                'email': request.form['email'],
                'address': request.form['address'],
                'city': request.form['city'],
                'state': request.form['state'],
                'pin_code': request.form['pin_code'],
                'proof_address': request.form['proof_address'],
                'date_signed': request.form['date_signed'],
                'aadhar_photo': aadhar_filename,
                'e_signature': signature_filename,
                'submission_date': datetime.utcnow()
            }

            # Insert into MongoDB
            mongo.db.kyc_forms.insert_one(kyc_data)

            # Redirect to video submission page
            return redirect(url_for('video_submit'))

        except Exception as e:
            print(f"Error in KYC submission: {e}")
            flash('An error occurred during submission')
            return redirect(url_for('kyc'))

    return render_template('kyc.html')

@app.route('/video_submit', methods=['GET', 'POST'])
def video_submit():
    if 'email' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Check if "on_camera" is selected
        if request.form.get('on_camera'):
            # Simulate a "REAL" prediction for on-camera verification
            flash("Live verification selected. Status: REAL")
            return redirect(url_for('success'))

        if 'video' not in request.files:
            flash('No video file uploaded')
            return redirect(request.url)
        
        video = request.files['video']
        if video.filename == '':
            flash('No video selected')
            return redirect(request.url)
        
        if video and allowed_file(video.filename):
            # Save the uploaded video
            video_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(video.filename))
            video.save(video_path)
            
            # Extract frames and predict
            output_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'frames')
            extract_frames(video_path, output_folder)
            frame_files = sorted(glob.glob(f"{output_folder}/*.jpg"))
            predictions = [predict_frame(frame) for frame in frame_files]
            
            final_decision = "FAKE" if predictions.count("FAKE") >= 3 else "REAL"

            if final_decision == "REAL":
                return redirect(url_for('success'))
            else:
                return redirect(url_for('failure'))
    
    return render_template('video-submit.html')

@app.route('/success')
def success():
    return render_template('success.html')

@app.route('/failure')
def failure():
    return render_template('failure.html')

# Add these new routes to your existing app.py

@app.route('/acknowledgment', methods=['GET', 'POST'])
def acknowledgment():
    if 'email' not in session:
        return redirect(url_for('login'))
    
    # Get the latest KYC submission for this user
    kyc_data = mongo.db.kyc_forms.find_one({'email': session['email']}, sort=[('submission_date', -1)])
    
    if not kyc_data:
        flash('No KYC submission found')
        return redirect(url_for('kyc'))
    
    return render_template('acknowledgment.html', kyc_data=kyc_data)

@app.route('/verification_complete')
def verification_complete():
    if 'email' not in session:
        return redirect(url_for('login'))
    
    # In a real application, you would update the KYC status in the database here
    # For example:
    # mongo.db.kyc_forms.update_one(
    #     {'email': session['email']},
    #     {'$set': {'status': 'verified', 'verification_date': datetime.utcnow()}}
    # )
    
    return render_template('verification_complete.html')
# # Add these new routes to your existing app.py

# @app.route('/nri_kyc', methods=['GET', 'POST'])
# def nri_kyc():
#     if 'email' not in session:
#         return redirect(url_for('login'))

#     if request.method == 'POST':
#         try:
#             # Save NRI-specific documents
#             passport = request.files['passport']
#             visa = request.files['visa']
#             overseas_address_proof = request.files['overseas_address_proof']

#             # Secure filenames
#             passport_filename = secure_filename(passport.filename)
#             visa_filename = secure_filename(visa.filename)
#             address_proof_filename = secure_filename(overseas_address_proof.filename)

#             # Save files
#             passport.save(os.path.join(app.config['UPLOAD_FOLDER'], passport_filename))
#             visa.save(os.path.join(app.config['UPLOAD_FOLDER'], visa_filename))
#             overseas_address_proof.save(os.path.join(app.config['UPLOAD_FOLDER'], address_proof_filename))

#             # Update KYC data with NRI info
#             nri_data = {
#                 'nri_status': True,
#                 'passport_number': request.form['passport_number'],
#                 'country_of_residence': request.form['country_of_residence'],
#                 'visa_type': request.form['visa_type'],
#                 'passport_doc': passport_filename,
#                 'visa_doc': visa_filename,
#                 'overseas_address_proof': address_proof_filename,
#                 'nri_submission_date': datetime.utcnow()
#             }

#             # Update the existing KYC record
#             mongo.db.kyc_forms.update_one(
#                 {'email': session['email']},
#                 {'$set': nri_data}
#             )

#             return redirect(url_for('nri_processing'))

#         except Exception as e:
#             print(f"Error in NRI KYC submission: {e}")
#             flash('An error occurred during NRI document submission')
#             return redirect(url_for('nri_kyc'))

#     return render_template('nri_kyc.html')

# @app.route('/nri_processing')
# def nri_processing():
#     if 'email' not in session:
#         return redirect(url_for('login'))
#     return render_template('nri_processing.html')

# @app.route('/senior_verification', methods=['GET', 'POST'])
# def senior_verification():
#     if 'email' not in session:
#         return redirect(url_for('login'))

#     if request.method == 'POST':
#         # Update KYC data with senior citizen status
#         mongo.db.kyc_forms.update_one(
#             {'email': session['email']},
#             {'$set': {
#                 'senior_citizen': True,
#                 'manual_verification_requested': True,
#                 'verification_status': 'pending_manual_review'
#             }}
#         )
#         return redirect(url_for('senior_processing'))

#     return render_template('senior_verification.html')

# # @app.route('/senior_processing')
# # def senior_processing():
# #     if 'email' not in session:
# #         return redirect(url_for('login'))
# #     return render_template('senior_processing.html')

# # # Modify the existing success route to handle conditions
# # @app.route('/success')
# # def success():
# #     if 'email' not in session:
# #         return redirect(url_for('login'))
    
# #     # Check if user is NRI or senior citizen
# #     kyc_data = mongo.db.kyc_forms.find_one({'email': session['email']})
    
# #     if kyc_data.get('nri_status'):
# #         return redirect(url_for('nri_kyc'))
# #     elif kyc_data.get('senior_citizen'):
# #         return redirect(url_for('senior_verification'))
    
# #     return render_template('success.html')

@app.route('/logout')
def logout():
    session.pop('email', None)
    flash('Logged out successfully')
    return redirect(url_for('landing'))

if __name__ == '__main__':
    app.run(debug=True)