from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db  # Import db from extensions

# Define your models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # customer, professional, admin
    phone = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default='Active')  # Active or Blocked
    block_reason = db.Column(db.Text, nullable=True)  # Reason for blocking

    # Relationships
    customer_profile = db.relationship('CustomerProfile', back_populates='user', uselist=False)
    professional_profile = db.relationship('ProfessionalProfile', uselist=False)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# Define other models like CustomerProfile, ProfessionalProfile, etc.

class CustomerProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    address = db.Column(db.String(200))
    city = db.Column(db.String(100))
    state = db.Column(db.String(100))
    pin_code = db.Column(db.String(20))
    bookings = db.relationship('Booking', backref='customer', lazy=True)
    user = db.relationship('User', back_populates='customer_profile')

class ProfessionalProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    profession = db.Column(db.String(100), nullable=False)
    experience = db.Column(db.Integer)
    bio = db.Column(db.Text)
    hourly_rate = db.Column(db.Float, nullable=False)  # New field
    approval_status = db.Column(db.String(20), default='pending')  # New field: 'pending', 'approved', 'rejected'
    rejection_reason = db.Column(db.Text)  # Reason for rejection (optional)
    documents = db.relationship('ProfessionalDocument', backref='professional', lazy=True)  # Document upload
    user = db.relationship('User', back_populates='professional_profile')

class ProfessionalDocument(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    professional_id = db.Column(db.Integer, db.ForeignKey('professional_profile.id'))
    document_type = db.Column(db.String(50))
    document_path = db.Column(db.String(200))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_verified = db.Column(db.Boolean, default=False)

class Service(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    base_price = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    location = db.Column(db.String(200))  # New field
    pin_code = db.Column(db.String(10))  # New field
    time_required = db.Column(db.String(50))

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer_profile.id'))
    professional_id = db.Column(db.Integer, db.ForeignKey('professional_profile.id'))
    service_id = db.Column(db.Integer, db.ForeignKey('service.id'))
    status = db.Column(db.String(20), default='pending')  # pending, confirmed, completed, cancelled
    booking_date = db.Column(db.DateTime, nullable=False)
    booking_time = db.Column(db.String(20), nullable=False)
    address = db.Column(db.String(200))
    remarks = db.Column(db.Text, nullable=True)  # Optional remarks for the booking
    completion_status = db.Column(db.String(20), nullable=True)  # completed or incomplete
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    service = db.relationship('Service', backref='bookings')
    address = db.Column(db.String(200))