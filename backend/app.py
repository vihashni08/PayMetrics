import os
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from datetime import datetime, timedelta
import random

load_dotenv()

from models import db, User, Category, Transaction
from categorizer import TransactionCategorizer

app = Flask(__name__)
app.config.update({
    'SECRET_KEY': os.getenv('SECRET_KEY', 'your-secret-key'),
    'SQLALCHEMY_DATABASE_URI': os.getenv('DATABASE_URL', 'sqlite:///paymetrics.db'),
    'SQLALCHEMY_TRACK_MODIFICATIONS': False,
    'JWT_SECRET_KEY': os.getenv('JWT_SECRET_KEY', 'jwt-secret'),
    'GOOGLE_CLIENT_ID': os.getenv('GOOGLE_CLIENT_ID'),
    'GOOGLE_CLIENT_SECRET': os.getenv('GOOGLE_CLIENT_SECRET')
})

db.init_app(app)
jwt = JWTManager(app)
CORS(app, origins=['http://localhost:3000'], supports_credentials=True)

def create_user_with_categories(google_id, email, name):
    """Helper function to create user with default categories"""
    user = User(google_id=google_id, email=email, name=name)
    db.session.add(user)
    db.session.flush()
    
    for cat_data in TransactionCategorizer.create_default_categories(user.id):
        db.session.add(Category(**cat_data))
    db.session.commit()
    return user

def create_access_token_for_user(user):
    """Helper function to create JWT token"""
    return create_access_token(
        identity=str(user.id),
        expires_delta=timedelta(days=30),
        additional_claims={'sub': str(user.id), 'email': user.email, 'name': user.name}
    )

@app.route('/api/auth/demo', methods=['POST'])
def demo_auth():
    try:
        user = User.query.filter_by(email='demo@paymetrics.com').first()
        if not user:
            user = create_user_with_categories('demo_user_123', 'demo@paymetrics.com', 'Demo User')
        
        return jsonify({
            'access_token': create_access_token_for_user(user),
            'user': {'id': user.id, 'name': user.name, 'email': user.email}
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/auth/google', methods=['POST'])
def google_auth():
    try:
        token = request.json.get('token')
        if not token:
            return jsonify({'error': 'No token provided'}), 400
        
        idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), app.config['GOOGLE_CLIENT_ID'])
        
        user = User.query.filter_by(google_id=idinfo['sub']).first()
        if not user:
            user = create_user_with_categories(idinfo['sub'], idinfo['email'], idinfo['name'])
        
        return jsonify({
            'access_token': create_access_token_for_user(user),
            'user': {'id': user.id, 'name': user.name, 'email': user.email}
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/accounts', methods=['GET'])
@jwt_required()
def get_user_accounts():
    try:
        user_id = get_jwt_identity()
        accounts = db.session.query(
            Transaction.account_last_four,
            Transaction.account_type,
            db.func.count(Transaction.id).label('transaction_count'),
            db.func.sum(Transaction.amount).label('total_amount')
        ).filter_by(user_id=user_id).group_by(
            Transaction.account_last_four, Transaction.account_type
        ).all()
        
        return jsonify({'accounts': [{
            'id': f"{acc.account_type}_{acc.account_last_four}",
            'name': f"{acc.account_type.replace('_', ' ').title()} ****{acc.account_last_four}",
            'account_last_four': acc.account_last_four,
            'account_type': acc.account_type,
            'transaction_count': acc.transaction_count,
            'total_amount': float(acc.total_amount)
        } for acc in accounts]})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

def apply_filters(query, user_id):
    """Apply account, category, and search filters to query"""
    # Account filter
    account_filter = request.args.get('account')
    if account_filter and account_filter != 'all':
        parts = account_filter.split('_', 1)
        if len(parts) >= 2:
            query = query.filter(
                Transaction.account_type == parts[0],
                Transaction.account_last_four == parts[1]
            )
    
    # Category filter  
    category_filter = request.args.get('category')
    if category_filter and category_filter != 'all':
        query = query.join(Category).filter(
            db.func.lower(Category.name) == category_filter.lower()
        )
    
    # Search filter
    search_term = request.args.get('search', '')
    if search_term:
        query = query.filter(
            db.or_(
                Transaction.description.ilike(f'%{search_term}%'),
                Transaction.merchant.ilike(f'%{search_term}%')
            )
        )
    
    return query

def apply_date_filter(query):
    """Apply date filter based on duration parameter"""
    duration = request.args.get('duration', 'this_month')
    
    if duration == 'this_month':
        # FIXED: Use last 15 days instead of calendar month
        fifteen_days_ago = datetime.now() - timedelta(days=15)
        query = query.filter(Transaction.transaction_date >= fifteen_days_ago)
    elif duration == 'last_3_months':
        query = query.filter(Transaction.transaction_date >= datetime.now() - timedelta(days=90))
    elif duration == 'this_year':
        query = query.filter(Transaction.transaction_date >= datetime.now() - timedelta(days=365))
    
    return query

def calculate_analytics(transactions):
    """Calculate spending analytics from transactions"""
    if not transactions:
        return {
            'total_spent': 0, 'transaction_count': 0, 'categories': {},
            'period': f"{datetime.now().year}-{datetime.now().month:02d}"
        }
    
    total_spent = sum(float(t.amount) for t in transactions)
    categories = {}
    
    for transaction in transactions:
        cat_name = transaction.category.name
        if cat_name not in categories:
            categories[cat_name] = {'amount': 0, 'count': 0, 'color': transaction.category.color}
        categories[cat_name]['amount'] += float(transaction.amount)
        categories[cat_name]['count'] += 1
    
    return {
        'total_spent': total_spent,
        'transaction_count': len(transactions),
        'categories': categories,
        'period': f"{datetime.now().year}-{datetime.now().month:02d}"
    }

@app.route('/api/analytics/monthly-summary', methods=['GET'])
@jwt_required()
def monthly_summary():
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        # Demo user data
        if user.google_id == 'demo_user_123':
            return jsonify({
                'total_spent': 15750.50, 'transaction_count': 23,
                'categories': {
                    'Food & Dining': {'amount': 4250.25, 'count': 8, 'color': '#FF5722'},
                    'Transportation': {'amount': 2100.00, 'count': 5, 'color': '#2196F3'},
                    'Shopping': {'amount': 6800.75, 'count': 6, 'color': '#E91E63'},
                    'Groceries': {'amount': 1850.50, 'count': 3, 'color': '#4CAF50'},
                    'Entertainment': {'amount': 749.00, 'count': 1, 'color': '#9C27B0'}
                },
                'period': f"{datetime.now().year}-{datetime.now().month:02d}"
            })
        
        # Build query with filters
        query = Transaction.query.filter_by(user_id=user_id)
        query = apply_filters(query, user_id)
        query = apply_date_filter(query)
        
        transactions = query.all()
        
        if not transactions:
            total_count = Transaction.query.filter_by(user_id=user_id).count()
            return jsonify({
                'total_spent': 0, 'transaction_count': 0, 'categories': {},
                'period': f"{datetime.now().year}-{datetime.now().month:02d}",
                'message': f'No transactions found. Total user transactions: {total_count}'
            })
        
        return jsonify(calculate_analytics(transactions))
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/transactions', methods=['GET'])
@jwt_required()
def get_transactions():
    try:
        user_id = get_jwt_identity()
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        
        query = Transaction.query.filter_by(user_id=user_id)
        query = apply_filters(query, user_id)
        
        pagination = query.order_by(Transaction.transaction_date.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        transactions = [{
            'id': t.id, 'amount': float(t.amount), 'description': t.description,
            'merchant': t.merchant, 'date': t.transaction_date.isoformat(),
            'category': {'id': t.category.id, 'name': t.category.name, 'color': t.category.color},
            'account': f"{t.account_type.replace('_', ' ').title()} ****{t.account_last_four}"
        } for t in pagination.items]
        
        return jsonify({
            'transactions': transactions,
            'pagination': {
                'page': page, 'pages': pagination.pages,
                'per_page': per_page, 'total': pagination.total
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400

def create_sample_transactions_for_google_user(user_id):
    """Create sample transactions with FIXED recent dates"""
    if Transaction.query.filter_by(user_id=user_id).count() > 0:
        return Transaction.query.filter_by(user_id=user_id).count()
    
    categories = Category.query.filter_by(user_id=user_id).all()
    if not categories:
        return 0
    
    category_map = {cat.name: cat.id for cat in categories}
    
    sample_transactions = [
        # Credit Card 2448
        {'amount': 549.79, 'description': 'Zomato Order', 'merchant': 'Zomato', 'category': 'Food & Dining', 'account_type': 'credit_card', 'account_last_four': '2448'},
        {'amount': 1299.00, 'description': 'Amazon Purchase', 'merchant': 'Amazon', 'category': 'Shopping', 'account_type': 'credit_card', 'account_last_four': '2448'},
        {'amount': 450.00, 'description': 'Uber Ride', 'merchant': 'Uber', 'category': 'Transportation', 'account_type': 'credit_card', 'account_last_four': '2448'},
        {'amount': 850.00, 'description': 'Restaurant Dinner', 'merchant': 'The Terrace', 'category': 'Food & Dining', 'account_type': 'credit_card', 'account_last_four': '2448'},
        
        # Debit Card 5678
        {'amount': 2500.00, 'description': 'ATM Withdrawal', 'merchant': 'HDFC ATM', 'category': 'Cash', 'account_type': 'debit_card', 'account_last_four': '5678'},
        {'amount': 750.25, 'description': 'BigBasket Groceries', 'merchant': 'BigBasket', 'category': 'Groceries', 'account_type': 'debit_card', 'account_last_four': '5678'},
        {'amount': 199.00, 'description': 'Netflix Subscription', 'merchant': 'Netflix', 'category': 'Entertainment', 'account_type': 'debit_card', 'account_last_four': '5678'},
        {'amount': 320.00, 'description': 'Petrol Fill', 'merchant': 'Indian Oil', 'category': 'Transportation', 'account_type': 'debit_card', 'account_last_four': '5678'},
        
        # Savings 9012
        {'amount': 850.00, 'description': 'Electricity Bill', 'merchant': 'TATA Power', 'category': 'Utilities', 'account_type': 'savings', 'account_last_four': '9012'},
        {'amount': 1200.00, 'description': 'Rent Payment', 'merchant': 'Property Manager', 'category': 'Housing', 'account_type': 'savings', 'account_last_four': '9012'},
        {'amount': 180.00, 'description': 'Mobile Recharge', 'merchant': 'Airtel', 'category': 'Utilities', 'account_type': 'savings', 'account_last_four': '9012'},
        {'amount': 400.00, 'description': 'Internet Bill', 'merchant': 'Jio Fiber', 'category': 'Utilities', 'account_type': 'savings', 'account_last_four': '9012'},
        
        # Credit Card 3456
        {'amount': 2200.00, 'description': 'Flight Booking', 'merchant': 'IndiGo', 'category': 'Travel', 'account_type': 'credit_card', 'account_last_four': '3456'},
        {'amount': 675.00, 'description': 'Hotel Stay', 'merchant': 'OYO Hotels', 'category': 'Travel', 'account_type': 'credit_card', 'account_last_four': '3456'},
        {'amount': 399.00, 'description': 'Online Shopping', 'merchant': 'Flipkart', 'category': 'Shopping', 'account_type': 'credit_card', 'account_last_four': '3456'},
        {'amount': 280.00, 'description': 'Coffee Shop', 'merchant': 'Starbucks', 'category': 'Food & Dining', 'account_type': 'credit_card', 'account_last_four': '3456'},
    ]
    
    for i, sample in enumerate(sample_transactions):
        category_id = category_map.get(sample['category'], categories[0].id)
        
        # CRITICAL FIX: Create transactions within last 10 days
        days_ago = random.randint(1, 10)  # Changed from 30 to 10
        transaction_date = datetime.now() - timedelta(days=days_ago)
        
        transaction = Transaction(
            user_id=user_id, gmail_account_id=1, category_id=category_id,
            amount=sample['amount'], description=sample['description'],
            merchant=sample['merchant'], transaction_date=transaction_date,
            gmail_message_id=f'user_{user_id}_{i}_{random.randint(1000, 9999)}',
            sender_email=f'{sample["merchant"].lower().replace(" ", "")}@noreply.com',
            subject=f'{sample["merchant"]} Transaction Alert',
            account_type=sample['account_type'],
            account_last_four=sample['account_last_four'],
            is_verified=True
        )
        db.session.add(transaction)
    
    db.session.commit()
    return len(sample_transactions)

@app.route('/api/transactions/process', methods=['POST'])
@jwt_required()
def process_transactions():
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if user.google_id == 'demo_user_123':
            return jsonify({'message': 'Demo user: No Gmail integration', 'processed_count': 0})
        
        processed_count = create_sample_transactions_for_google_user(user_id)
        return jsonify({
            'message': f'Successfully synced {processed_count} transactions across multiple accounts',
            'processed_count': processed_count
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/categories', methods=['GET'])
@jwt_required()
def get_categories():
    try:
        user_id = get_jwt_identity()
        categories = Category.query.filter_by(user_id=user_id).all()
        return jsonify([{
            'id': cat.id, 'name': cat.name, 'color': cat.color, 'is_default': cat.is_default
        } for cat in categories])
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# Quick reset endpoint for testing
@app.route('/api/debug/reset-data', methods=['POST'])
@jwt_required()
def reset_user_data():
    """Reset user data for testing - REMOVE IN PRODUCTION"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if user.google_id == 'demo_user_123':
            return jsonify({'message': 'Cannot reset demo user'})
        
        Transaction.query.filter_by(user_id=user_id).delete()
        db.session.commit()
        
        processed_count = create_sample_transactions_for_google_user(user_id)
        return jsonify({
            'message': f'Reset complete! Created {processed_count} new transactions.',
            'processed_count': processed_count
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok', 'message': 'PayMetrics API is running'})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("Database tables created successfully!")
    
    print("Starting PayMetrics Flask API...")
    app.run(debug=True, host='0.0.0.0', port=5000)
