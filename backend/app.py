import os
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity, verify_jwt_in_request
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from datetime import datetime, timedelta

load_dotenv()

from models import db, User, Category, Transaction
from gmail_service import GmailService
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

# Enhanced JWT error handlers
@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    return jsonify({'error': 'Token has expired', 'code': 'TOKEN_EXPIRED'}), 401

@jwt.invalid_token_loader
def invalid_token_callback(error):
    return jsonify({'error': 'Invalid token', 'code': 'INVALID_TOKEN'}), 401

@jwt.unauthorized_loader
def missing_token_callback(error):
    return jsonify({'error': 'Authorization token is required', 'code': 'MISSING_TOKEN'}), 401

def create_user_with_categories(google_id, email, name):
    """Helper function to create user with default categories"""
    try:
        user = User(google_id=google_id, email=email, name=name)
        db.session.add(user)
        db.session.flush()
        
        # Create default categories for the user
        for cat_data in TransactionCategorizer.create_default_categories(user.id):
            db.session.add(Category(**cat_data))
        db.session.commit()
        print(f"✅ Created user {email} with categories")
        return user
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error creating user: {e}")
        raise e

def create_access_token_for_user(user):
    """Helper function to create JWT token"""
    return create_access_token(
        identity=str(user.id),
        expires_delta=timedelta(days=30),
        additional_claims={'sub': str(user.id), 'email': user.email, 'name': user.name}
    )

def safe_get_user():
    """Safely get current user with proper error handling"""
    try:
        verify_jwt_in_request()
        user_id = get_jwt_identity()
        if not user_id:
            return None, jsonify({'error': 'Invalid token'}), 401
            
        user = db.session.get(User, user_id)
        if not user:
            return None, jsonify({'error': 'User not found'}), 404
            
        return user, None, None
    except Exception as e:
        print(f"❌ JWT Error: {str(e)}")
        return None, jsonify({'error': 'Authentication failed', 'details': str(e)}), 401

@app.route('/api/auth/demo', methods=['POST'])
def demo_auth():
    """Demo authentication for testing purposes"""
    try:
        user = User.query.filter_by(email='demo@paymetrics.com').first()
        if not user:
            user = create_user_with_categories('demo_user_123', 'demo@paymetrics.com', 'Demo User')
        
        return jsonify({
            'access_token': create_access_token_for_user(user),
            'user': {'id': user.id, 'name': user.name, 'email': user.email}
        })
    except Exception as e:
        print(f"❌ Demo auth error: {str(e)}")
        return jsonify({'error': str(e)}), 400

@app.route('/api/auth/google', methods=['POST'])
def google_auth():
    """Google OAuth authentication - Clean login, no auto sample data"""
    try:
        token = request.json.get('token')
        if not token:
            return jsonify({'error': 'No token provided'}), 400
        
        # Verify Google token
        idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), app.config['GOOGLE_CLIENT_ID'])
        
        user = User.query.filter_by(google_id=idinfo['sub']).first()
        is_new_user = False
        
        if not user:
            user = create_user_with_categories(idinfo['sub'], idinfo['email'], idinfo['name'])
            is_new_user = True
            print(f"✅ Created new user: {user.email}")
        
        return jsonify({
            'access_token': create_access_token_for_user(user),
            'user': {'id': user.id, 'name': user.name, 'email': user.email},
            'is_new_user': is_new_user,
            'message': 'Login successful. Click "Sync Transactions" to load your Gmail data.'
        })
        
    except Exception as e:
        print(f"❌ Google auth error: {str(e)}")
        return jsonify({'error': str(e)}), 400

def save_parsed_transactions(user_id, parsed_transactions):
    """Save parsed transactions to database with proper categorization"""
    if not parsed_transactions:
        return 0
        
    # Get user's categories
    categories = Category.query.filter_by(user_id=user_id).all()
    if not categories:
        print("❌ No categories found for user")
        return 0
    
    # Create category mapping
    category_map = {cat.name: cat.id for cat in categories}
    print(f"📋 Available categories: {list(category_map.keys())}")
    
    saved_count = 0
    for trans_data in parsed_transactions:
        try:
            # Skip duplicates by Gmail message ID
            existing = Transaction.query.filter_by(
                user_id=user_id,
                gmail_message_id=trans_data.get('email_id')
            ).first()
            
            if existing:
                print(f"⚠️ Duplicate transaction skipped: {trans_data.get('merchant')} - ₹{trans_data.get('amount')}")
                continue
            
            # Get category ID with fallback
            category_name = trans_data.get('category', 'Transfer')
            category_id = category_map.get(category_name)
            
            # If category doesn't exist, use first available category as fallback
            if not category_id:
                print(f"⚠️ Category '{category_name}' not found, using fallback")
                category_id = categories[0].id
                category_name = categories[0].name
            
            # Create transaction
            transaction = Transaction(
                user_id=user_id,
                gmail_account_id=1,  # Default Gmail account ID
                category_id=category_id,
                amount=trans_data.get('amount', 0),
                description=trans_data.get('description', ''),
                merchant=trans_data.get('merchant', ''),
                transaction_date=trans_data.get('transaction_date', datetime.now()),
                gmail_message_id=trans_data.get('email_id'),
                sender_email=trans_data.get('sender_email', ''),
                subject=trans_data.get('subject', ''),
                account_type=trans_data.get('account_type', 'debit_card'),
                account_last_four=trans_data.get('account_last_four', '0000'),
                is_verified=True
            )
            
            db.session.add(transaction)
            saved_count += 1
            print(f"✅ Saved: {transaction.merchant} - ₹{transaction.amount} ({category_name})")
            
        except Exception as e:
            print(f"❌ Error saving transaction: {e}")
            continue
    
    try:
        db.session.commit()
        print(f"✅ Committed {saved_count} transactions")
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error committing transactions: {e}")
        return 0
        
    return saved_count

@app.route('/api/transactions/process', methods=['POST'])
@jwt_required()
def process_transactions():
    """Process ONLY real Gmail transactions - ENHANCED ERROR HANDLING"""
    try:
        user, error_response, status_code = safe_get_user()
        if error_response:
            return error_response, status_code
        
        if user.google_id == 'demo_user_123':
            return jsonify({'message': 'Demo user: No Gmail integration available', 'processed_count': 0})
        
        print(f"🔄 Starting Gmail sync for user: {user.email}")
        
        # Check required files
        if not os.path.exists('credentials.json'):
            return jsonify({
                'error': 'Missing credentials.json. Please set up Gmail API credentials first.',
                'processed_count': 0,
                'setup_required': True
            }), 400
        
        try:
            gmail_service = GmailService()
            real_transactions = gmail_service.process_user_emails(user.email)
            
            if not real_transactions:
                return jsonify({
                    'message': 'No transaction emails found in your Gmail. Make sure you have HDFC UPI transaction emails.',
                    'processed_count': 0,
                    'suggestion': 'Check if HDFC sends transaction alerts to this Gmail account.'
                })
            
            # Save real transactions with proper categorization
            processed_count = save_parsed_transactions(user.id, real_transactions)
            
            return jsonify({
                'message': f'Successfully synced {processed_count} real transactions from your Gmail!',
                'processed_count': processed_count
            })
            
        except Exception as gmail_error:
            print(f"❌ Gmail API Error: {str(gmail_error)}")
            return jsonify({
                'error': f'Gmail API Error: {str(gmail_error)}',
                'processed_count': 0,
                'gmail_error': True
            }), 400
        
    except Exception as e:
        print(f"❌ Process transactions error: {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/api/accounts', methods=['GET'])
@jwt_required()
def get_user_accounts():
    """Get user's account summary"""
    try:
        user, error_response, status_code = safe_get_user()
        if error_response:
            return error_response, status_code
        
        accounts = db.session.query(
            Transaction.account_last_four,
            Transaction.account_type,
            db.func.count(Transaction.id).label('transaction_count'),
            db.func.sum(Transaction.amount).label('total_amount')
        ).filter_by(user_id=user.id).group_by(
            Transaction.account_last_four, Transaction.account_type
        ).all()
        
        account_list = []
        for acc in accounts:
            account_data = {
                'id': f"{acc.account_type}_{acc.account_last_four}",
                'name': f"{acc.account_type.replace('_', ' ').title()} ****{acc.account_last_four}",
                'account_last_four': acc.account_last_four,
                'account_type': acc.account_type,
                'transaction_count': acc.transaction_count,
                'total_amount': float(acc.total_amount)
            }
            account_list.append(account_data)
        
        return jsonify({'accounts': account_list})
    except Exception as e:
        print(f"❌ Accounts error: {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500

def apply_filters(query, user_id):
    """Apply account, category, and search filters to query"""
    account_filter = request.args.get('account')
    if account_filter and account_filter != 'all':
        if '_' in account_filter:
            parts = account_filter.split('_', 1)
            if len(parts) >= 2:
                account_type = parts[0]
                account_last_four = parts[1]
                
                query = query.filter(
                    Transaction.account_type == account_type,
                    Transaction.account_last_four == account_last_four
                )
        else:
            query = query.filter(Transaction.account_last_four == account_filter)
    
    category_filter = request.args.get('category')
    if category_filter and category_filter != 'all':
        query = query.join(Category).filter(
            db.func.lower(Category.name) == category_filter.lower()
        )
    
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
            'total_spent': 0,
            'transaction_count': 0,
            'categories': {},
            'period': f"{datetime.now().year}-{datetime.now().month:02d}"
        }
    
    total_spent = sum(float(t.amount) for t in transactions)
    categories = {}
    
    for transaction in transactions:
        cat_name = transaction.category.name
        if cat_name not in categories:
            categories[cat_name] = {
                'amount': 0,
                'count': 0,
                'color': transaction.category.color
            }
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
    """Get monthly spending summary"""
    try:
        user, error_response, status_code = safe_get_user()
        if error_response:
            return error_response, status_code
        
        # Demo data ONLY for demo user
        if user.google_id == 'demo_user_123' and user.email == 'demo@paymetrics.com':
            return jsonify({
                'total_spent': 15750.50,
                'transaction_count': 23,
                'categories': {
                    'Food & Dining': {'amount': 4250.25, 'count': 8, 'color': '#FF5722'},
                    'Transportation': {'amount': 2100.00, 'count': 5, 'color': '#2196F3'},
                    'Shopping': {'amount': 6800.75, 'count': 6, 'color': '#E91E63'},
                    'Groceries': {'amount': 1850.50, 'count': 3, 'color': '#4CAF50'},
                    'Entertainment': {'amount': 749.00, 'count': 1, 'color': '#9C27B0'}
                },
                'period': f"{datetime.now().year}-{datetime.now().month:02d}"
            })
        
        # For real users, use actual transaction data
        query = Transaction.query.filter_by(user_id=user.id)
        query = apply_filters(query, user.id)
        query = apply_date_filter(query)
        
        transactions = query.all()
        return jsonify(calculate_analytics(transactions))
        
    except Exception as e:
        print(f"❌ Monthly summary error: {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/api/transactions', methods=['GET'])
@jwt_required()
def get_transactions():
    """Get paginated list of transactions"""
    try:
        user, error_response, status_code = safe_get_user()
        if error_response:
            return error_response, status_code
            
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        
        query = Transaction.query.filter_by(user_id=user.id)
        query = apply_filters(query, user.id)
        
        pagination = query.order_by(Transaction.transaction_date.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        transactions = [{
            'id': t.id,
            'amount': float(t.amount),
            'description': t.description,
            'merchant': t.merchant,
            'date': t.transaction_date.isoformat(),
            'category': {'id': t.category.id, 'name': t.category.name, 'color': t.category.color},
            'account': f"{t.account_type.replace('_', ' ').title()} ****{t.account_last_four}"
        } for t in pagination.items]
        
        return jsonify({
            'transactions': transactions,
            'pagination': {
                'page': page,
                'pages': pagination.pages,
                'per_page': per_page,
                'total': pagination.total
            }
        })
    except Exception as e:
        print(f"❌ Get transactions error: {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/api/categories', methods=['GET'])
@jwt_required()
def get_categories():
    """Get user's categories"""
    try:
        user, error_response, status_code = safe_get_user()
        if error_response:
            return error_response, status_code
            
        categories = Category.query.filter_by(user_id=user.id).all()
        return jsonify([{
            'id': cat.id,
            'name': cat.name,
            'color': cat.color,
            'is_default': cat.is_default
        } for cat in categories])
    except Exception as e:
        print(f"❌ Categories error: {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'message': 'PayMetrics API is running'})

# Debug route to check registered routes
@app.route('/api/debug/routes', methods=['GET'])
def debug_routes():
    """Debug endpoint to see all registered routes"""
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append({
            'endpoint': rule.endpoint,
            'methods': list(rule.methods),
            'rule': rule.rule
        })
    return jsonify({'routes': routes})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("✅ Database tables created successfully!")
        
        # Print all registered routes for debugging
        print("\n🔍 Registered API routes:")
        for rule in app.url_map.iter_rules():
            if rule.rule.startswith('/api/'):
                print(f"   {rule.rule} -> {list(rule.methods)}")
    
    print("🚀 Starting PayMetrics Flask API...")
    app.run(debug=True, host='0.0.0.0', port=5000)
