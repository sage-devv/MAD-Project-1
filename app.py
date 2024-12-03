from flask import Flask, render_template, redirect, url_for, flash, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash
from config import Config
import os
from extensions import db  # Import db
from werkzeug.utils import secure_filename


app = Flask(__name__)
app.config.from_object('config.Config')
db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.errorhandler(401)
def unauthorized_error(error):
    flash('You must be logged in to access this page.', 'error')
    return redirect(url_for('login'))

# Import models after db initialization to avoid circular imports
from models import User, CustomerProfile, ProfessionalProfile, Service, Booking, ProfessionalDocument

UPLOAD_FOLDER = 'uploads/'
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')

        user = User.query.filter_by(email=email, role=role).first()
        
        if user:
            # Check if the user is blocked
            if user.status == 'Blocked':
                flash(f'Your account has been blocked by the Admin. Reason: {user.block_reason or "No reason provided."}', 'error')
                return redirect(url_for('login'))
            
        if user and user.check_password(password):
            if role == 'professional' and user.professional_profile.approval_status == 'pending':
                flash('Your account is pending approval. Please wait for admin review.', 'warning')
                return redirect(url_for('login'))
            elif role == 'professional' and user.professional_profile.approval_status == 'rejected':
                flash('Your account was rejected. Apply again after 6 months.', 'error')
                return redirect(url_for('login'))

            login_user(user)
            flash(f'Welcome, {user.name}!', 'success')
            return redirect(url_for(f'{role}_dashboard'))

        flash('Invalid credentials. Please try again.', 'error')
    return render_template('login.html')

@app.route('/signup/<role>', methods=['GET', 'POST'])
def signup(role):
    if request.method == 'POST':
        # Retrieve common form data
        first_name = request.form.get('firstName')
        last_name = request.form.get('lastName')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Validate required fields
        if not first_name or not last_name or not email or not password:
            flash('All fields are required.', 'error')
            return redirect(url_for('signup', role=role))

        # Check if the email already exists
        if User.query.filter_by(email=email).first():
            flash('Email is already registered.', 'error')
            return redirect(url_for('signup', role=role))

        # Create a new user
        user = User(
            email=email,
            name=f"{first_name} {last_name}",
            role=role
        )
        user.set_password(password)
        db.session.add(user)

        # Role-specific handling
        if role == 'professional':
            # Retrieve professional-specific data
            profession = request.form.get('profession')
            experience = request.form.get('experience')
            hourly_rate = request.form.get('hourlyRate')

            # Handle file uploads
            license_doc = request.files.get('licenseDocument')
            id_proof = request.files.get('idProof')

            if not license_doc or not id_proof:
                flash('License and ID proof documents are required for professionals.', 'error')
                return redirect(url_for('signup', role=role))
            
            if not allowed_file(license_doc.filename) or not allowed_file(id_proof.filename):
                flash('Invalid file format. Only PDF, JPG, JPEG, or PNG files are allowed.', 'error')
                return redirect(url_for('signup', role=role))

            # Save files
            license_filename = secure_filename(license_doc.filename)
            id_proof_filename = secure_filename(id_proof.filename)

            # Ensure upload directory exists
            if not os.path.exists(app.config['UPLOAD_FOLDER']):
                os.makedirs(app.config['UPLOAD_FOLDER'])

            license_doc.save(os.path.join(app.config['UPLOAD_FOLDER'], license_filename))
            id_proof.save(os.path.join(app.config['UPLOAD_FOLDER'], id_proof_filename))

            # Create professional profile
            profile = ProfessionalProfile(
                user=user,
                profession=profession,
                experience=experience,
                bio=request.form.get('bio', 'No bio provided.'),
                hourly_rate=hourly_rate,
                approval_status='pending'
            )
            db.session.add(profile)

            # Save uploaded documents
            db.session.add(ProfessionalDocument(professional=profile, document_type='License', document_path=license_filename))
            db.session.add(ProfessionalDocument(professional=profile, document_type='ID Proof', document_path=id_proof_filename))

        elif role == 'customer':
            # Handle customer-specific data
            profile = CustomerProfile(
                user=user,
                address=request.form.get('address'),
                city=request.form.get('city'),
                state=request.form.get('state'),
                pin_code=request.form.get('pinCode')
            )
            db.session.add(profile)

        elif role == 'admin':
            # Admin-specific data can be handled here if needed
            pass

        # Commit changes to the database
        db.session.commit()
        flash('Account created successfully! For professionals, your profile is under review.', 'success')
        return redirect(url_for('login'))

    return render_template('signup.html', role=role)

@app.route('/customer/dashboard')
@login_required
def customer_dashboard():
    if current_user.role != 'customer':
        flash('Access denied.', 'error')
        return redirect(url_for('login'))

    # Fetch verified professionals to show to the customer
    nearby_professionals = ProfessionalProfile.query.filter_by(approval_status='approved').all()
    service_categories = Service.query.with_entities(Service.category).distinct()
    bookings = current_user.customer_profile.bookings

    return render_template(
        'customer_dashboard.html',
        nearby_professionals=nearby_professionals,
        service_categories=service_categories,
        bookings=bookings
    )

@app.route('/customer/request', methods=['POST'])
@login_required
def create_booking():
    if current_user.role != 'customer':
        return redirect(url_for('login'))
    
    # Retrieve service and professional IDs from the request
    service_id = request.form.get('service_id')
    professional_id = request.form.get('professional_id')
    
    # Validate service ID
    service = Service.query.get(service_id)
    if not service:
        flash('The selected service does not exist.', 'error')
        return redirect(url_for('customer_dashboard'))
    
    # Validate professional ID
    professional = ProfessionalProfile.query.get(professional_id)
    if not professional or professional.profession != service.category:
        flash('The selected professional does not match the service category.', 'error')
        return redirect(url_for('customer_dashboard'))
    
    # Create a new booking
    booking = Booking(
        customer_id=current_user.customer_profile.id,
        professional_id=professional_id,
        service_id=service_id,
        booking_date=request.form.get('date'),
        booking_time=request.form.get('time'),
        address=current_user.customer_profile.address,
        status='requested'
    )
    db.session.add(booking)
    db.session.commit()
    flash('Booking request sent successfully.', 'success')
    return redirect(url_for('customer_dashboard'))


@app.route('/customer/search', methods=['POST'])
@login_required
def customer_search():
    if current_user.role != 'customer':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('login'))

    query = request.form.get('query', '')
    services = Service.query.filter(
        (Service.name.ilike(f"%{query}%")) |
        (Service.location.ilike(f"%{query}%")) |
        (Service.pin_code.ilike(f"%{query}%"))
    ).all()

    return render_template('customer_dashboard.html', services=services)

@app.route('/admin/search_professionals', methods=['GET', 'POST'])
@login_required
def search_professionals():
    if current_user.role != 'admin':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('login'))

    query = request.form.get('query', '')
    professionals = ProfessionalProfile.query.filter(
        (ProfessionalProfile.profession.ilike(f"%{query}%")) |
        (User.name.ilike(f"%{query}%"))
    ).join(User).all()

    return render_template('admin_dashboard.html', professionals=professionals)

@app.route('/professional/service_requests', methods=['GET'])
@login_required
def view_service_requests():
    if current_user.role != 'professional':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('login'))

    service_requests = Booking.query.filter_by(professional_id=current_user.professional_profile.id).all()
    return render_template('professional_service_requests.html', service_requests=service_requests)


@app.route('/professional/dashboard')
@login_required
def professional_dashboard():
    if current_user.role != 'professional':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('login'))
    
    # Fetch professional profile
    professional = current_user.professional_profile

    if not professional:
        flash('Profile not found. Please complete your registration.', 'error')
        return redirect(url_for('login'))

    # Fetch pending service requests
    pending_requests = Booking.query.filter_by(
        status='requested'
    ).all()

    return render_template(
        'professional_dashboard.html',
        professional=professional,
        pending_requests=pending_requests
    )

@app.route('/service-request/accept/<int:request_id>', methods=['POST'])
@login_required
def accept_service_request(request_id):
    if current_user.role != 'professional':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('login'))

    request = Booking.query.get_or_404(request_id)
    if request.professional_id != current_user.professional_profile.id:
        flash('Unauthorized action.', 'error')
        return redirect(url_for('professional_dashboard'))

    request.status = 'accepted'
    db.session.commit()
    flash('Service request accepted.', 'success')
    return redirect(url_for('professional_dashboard'))


@app.route('/service-request/reject/<int:request_id>', methods=['POST'])
@login_required
def reject_service_request(request_id):
    if current_user.role != 'professional':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('login'))

    request = Booking.query.get_or_404(request_id)
    if request.professional_id != current_user.professional_profile.id:
        flash('Unauthorized action.', 'error')
        return redirect(url_for('professional_dashboard'))

    request.status = 'rejected'
    db.session.commit()
    flash('Service request rejected.', 'success')
    return redirect(url_for('professional_dashboard'))


@app.route('/service-request/complete/<int:request_id>', methods=['POST'])
@login_required
def complete_service_request(request_id):
    if current_user.role != 'professional':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('login'))

    request = Booking.query.get_or_404(request_id)
    if request.professional_id != current_user.professional_profile.id:
        flash('Unauthorized action.', 'error')
        return redirect(url_for('professional_dashboard'))

    request.status = 'completed'
    db.session.commit()
    flash('Service request marked as completed.', 'success')
    return redirect(url_for('professional_dashboard'))

@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if current_user.role != 'professional':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('login'))
    
    if 'file' not in request.files:
        flash('No file part', 'error')
        return redirect(url_for('professional_dashboard'))
    
    file = request.files['file']
    if file.filename == '':
        flash('No selected file', 'error')
        return redirect(url_for('professional_dashboard'))
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        flash('File uploaded successfully', 'success')
    else:
        flash('Invalid file format.', 'error')
    return redirect(url_for('professional_dashboard'))

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        return redirect(url_for('login'))
    
    # Query professionals based on approval status
    search_query = request.form.get('query') if request.method == 'POST' else None

    # Fetch professionals based on search query
    if search_query:
        pending_professionals = ProfessionalProfile.query.filter(
            ProfessionalProfile.approval_status == 'pending',
            ProfessionalProfile.user.has(User.name.ilike(f'%{search_query}%'))
        ).all()
        approved_professionals = ProfessionalProfile.query.filter(
            ProfessionalProfile.approval_status == 'approved',
            ProfessionalProfile.user.has(User.name.ilike(f'%{search_query}%'))
        ).all()
        rejected_professionals = ProfessionalProfile.query.filter(
            ProfessionalProfile.approval_status == 'rejected',
            ProfessionalProfile.user.has(User.name.ilike(f'%{search_query}%'))
        ).all()
    else:
        pending_professionals = ProfessionalProfile.query.filter_by(approval_status='pending').all()
        approved_professionals = ProfessionalProfile.query.filter_by(approval_status='approved').all()
        rejected_professionals = ProfessionalProfile.query.filter_by(approval_status='rejected').all()
    
    # Pass services and users if needed
    services = Service.query.all()
    users = User.query.all()
    
    return render_template(
        'admin_dashboard.html',
        pending_professionals=pending_professionals,
        approved_professionals=approved_professionals,
        rejected_professionals=rejected_professionals,
        services=services,
        users=users
    )

@app.route('/admin/approve/<int:professional_id>', methods=['POST'])
@login_required
def approve_professional(professional_id):
    if current_user.role != 'admin':
        return redirect(url_for('login'))
    professional = ProfessionalProfile.query.get(professional_id)
    if professional:
        professional.approval_status = 'approved'
        db.session.commit()
        flash('Professional approved successfully.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/reject/<int:professional_id>', methods=['POST'])
@login_required
def reject_professional(professional_id):
    if current_user.role != 'admin':
        return redirect(url_for('login'))
    professional = ProfessionalProfile.query.get(professional_id)
    if professional:
        professional.approval_status = 'rejected'
        professional.rejection_reason = request.form.get('rejection_reason', 'Not specified')
        db.session.commit()
        flash('Professional rejected successfully.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/professional/update_status/<int:booking_id>', methods=['POST'])
@login_required
def update_booking_status(booking_id):
    if current_user.role != 'professional':
        return redirect(url_for('login'))

    booking = Booking.query.get(booking_id)
    if booking and booking.professional_id == current_user.professional_profile.id:
        new_status = request.form.get('status')
        booking.status = new_status
        db.session.commit()
        flash('Booking status updated successfully.')
    else:
        flash('Booking not found or unauthorized action.')
    return redirect(url_for('professional_dashboard'))

@app.route('/admin/block_user/<int:user_id>', methods=['POST'])
@login_required
def block_user(user_id):
    if current_user.role != 'admin':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('admin_dashboard'))

    user = User.query.get_or_404(user_id)
    block_reason = request.form.get('block_reason')

    # Update user status to 'Blocked'
    user.status = 'Blocked'
    user.block_reason = block_reason
    db.session.commit()

    flash(f'User {user.name} has been blocked.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/unblock_user/<int:user_id>', methods=['POST'])
@login_required
def unblock_user(user_id):
    if current_user.role != 'admin':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('admin_dashboard'))

    user = User.query.get_or_404(user_id)

    # Update user status to 'Active'
    user.status = 'Active'
    user.block_reason = None
    db.session.commit()

    flash(f'User {user.name} has been unblocked.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/create_service', methods=['POST'])
@login_required
def create_service():
    if current_user.role != 'admin':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('admin_dashboard'))
    
    if not request.form.get('category'):
        flash('Category is required.', 'error')
        return redirect(url_for('admin_dashboard'))

    service = Service(
        id=request.form.get('id'),  # Explicitly get Service ID
        name=request.form.get('name'),
        category=request.form.get('category'),
        base_price=request.form.get('base_price'),
        time_required=request.form.get('time_required'),
        description=request.form.get('description'),
    )
    db.session.add(service)
    db.session.commit()
    flash('Service added successfully.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/update_service/<string:service_id>', methods=['POST'])
@login_required
def update_service(service_id):
    if current_user.role != 'admin':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('admin_dashboard'))

    service = Service.query.get_or_404(service_id)
    service.name = request.form.get('name')
    service.base_price = request.form.get('base_price')
    service.time_required = request.form.get('time_required')
    service.description = request.form.get('description')
    db.session.commit()
    flash('Service updated successfully.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_service/<string:service_id>', methods=['POST'])
@login_required
def delete_service(service_id):
    if current_user.role != 'admin':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('admin_dashboard'))

    service = Service.query.get_or_404(service_id)
    db.session.delete(service)
    db.session.commit()
    flash('Service deleted successfully.', 'success')
    return redirect(url_for('admin_dashboard'))


# @app.route('/booking/create', methods=['POST'])
# @login_required
# def create_booking():
#     if current_user.role != 'customer':
#         return redirect(url_for('login'))
    
#     professional_id = request.form.get('professional_id')
#     service_id = request.form.get('service_id')
#     booking_date = request.form.get('date')
#     booking_time = request.form.get('time')
    
#     booking = Booking(
#         customer=current_user.customer_profile,
#         professional_id=professional_id,
#         service_id=service_id,
#         booking_date=booking_date,
#         booking_time=booking_time,
#         address=current_user.customer_profile.address
#     )
    
#     db.session.add(booking)
#     db.session.commit()
#     flash('Booking created successfully')
#     return redirect(url_for('customer_dashboard'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)