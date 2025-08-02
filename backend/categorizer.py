import re
from typing import Dict, List, Optional


class TransactionCategorizer:
    # Comprehensive categorization rules for Indian context
    CATEGORY_RULES = {
        'Food & Dining': {
            'keywords': ['zomato', 'swiggy', 'uber eats', 'dominos', 'pizza', 'restaurant', 'cafe', 'food', 'dining', 'mcdonald', 'kfc', 'subway', 'starbucks'],
            'merchants': ['zomato', 'swiggy', 'dominos', 'pizza hut', 'kfc', 'mcdonald'],
        },
        'Transportation': {
            'keywords': ['uber', 'ola', 'metro', 'bus', 'taxi', 'fuel', 'petrol', 'diesel', 'parking', 'toll', 'transport'],
            'merchants': ['uber', 'ola', 'rapido', 'indian oil', 'bharat petroleum', 'hp petrol'],
        },
        'Shopping': {
            'keywords': ['amazon', 'flipkart', 'myntra', 'ajio', 'shopping', 'purchase', 'retail', 'store'],
            'merchants': ['amazon', 'flipkart', 'myntra', 'ajio', 'nykaa', 'big bazaar'],
        },
        'Groceries': {
            'keywords': ['grocery', 'supermarket', 'vegetables', 'fruits', 'bigbasket', 'grofers', 'dunzo'],
            'merchants': ['bigbasket', 'grofers', 'dunzo', 'more', 'reliance fresh', 'dmart'],
        },
        'Entertainment': {
            'keywords': ['movie', 'cinema', 'netflix', 'amazon prime', 'hotstar', 'spotify', 'entertainment', 'gaming'],
            'merchants': ['netflix', 'amazon prime', 'hotstar', 'spotify', 'bookmyshow', 'paytm movies'],
        },
        'Utilities': {
            'keywords': ['electricity', 'gas', 'water', 'internet', 'mobile', 'phone', 'recharge', 'postpaid', 'broadband'],
            'merchants': ['bsnl', 'airtel', 'jio', 'vodafone', 'tata power', 'adani gas'],
        },
        'Healthcare': {
            'keywords': ['pharmacy', 'medicine', 'doctor', 'hospital', 'health', 'medical', 'apollo', '1mg', 'pharmeasy'],
            'merchants': ['apollo pharmacy', '1mg', 'pharmeasy', 'netmeds', 'apollo hospital'],
        },
        'Education': {
            'keywords': ['course', 'training', 'education', 'fees', 'tuition', 'book', 'udemy', 'coursera'],
            'merchants': ['udemy', 'coursera', 'byju', 'unacademy', 'vedantu'],
        },
        'Travel': {
            'keywords': ['flight', 'hotel', 'booking', 'travel', 'makemytrip', 'goibibo', 'oyo', 'irctc'],
            'merchants': ['makemytrip', 'goibibo', 'cleartrip', 'oyo', 'irctc', 'redbus'],
        },
        'Investment': {
            'keywords': ['mutual fund', 'sip', 'stock', 'trading', 'investment', 'zerodha', 'groww', 'paytm money'],
            'merchants': ['zerodha', 'groww', 'paytm money', 'upstox', 'angel broking'],
        },
        'Insurance': {
            'keywords': ['insurance', 'premium', 'policy', 'lic', 'health insurance', 'car insurance'],
            'merchants': ['lic', 'icici prudential', 'hdfc life', 'bajaj allianz'],
        },
        'Personal Care': {
            'keywords': ['salon', 'spa', 'cosmetics', 'beauty', 'personal care', 'nykaa', 'urban company'],
            'merchants': ['nykaa', 'urban company', 'lakme', 'looks salon'],
        }
    }
    
    def __init__(self, user_categories: List[Dict] = None):
        self.user_categories = user_categories or []
    
    def categorize_transaction(self, transaction_data: Dict) -> Optional[int]:
        """Categorize transaction and return category ID"""
        merchant = (transaction_data.get('merchant', '') or '').lower()
        description = (transaction_data.get('description', '') or '').lower()
        
        combined_text = f"{merchant} {description}".lower()
        
        # First, check user's custom categories
        for user_cat in self.user_categories:
            if user_cat.get('keywords'):
                for keyword in user_cat['keywords']:
                    if keyword.lower() in combined_text:
                        return user_cat['id']
        
        # Then check default categories
        for category_name, rules in self.CATEGORY_RULES.items():
            # Check keywords
            for keyword in rules['keywords']:
                if keyword in combined_text:
                    # Find matching default category ID
                    for user_cat in self.user_categories:
                        if user_cat['name'] == category_name and user_cat.get('is_default'):
                            return user_cat['id']
            
            # Check merchant names
            if 'merchants' in rules:
                for merchant_name in rules['merchants']:
                    if merchant_name in merchant:
                        for user_cat in self.user_categories:
                            if user_cat['name'] == category_name and user_cat.get('is_default'):
                                return user_cat['id']
        
        # Return 'Uncategorized' category ID if no match found
        uncategorized = next((cat for cat in self.user_categories if cat['name'] == 'Uncategorized'), None)
        return uncategorized['id'] if uncategorized else None

    @staticmethod
    def create_default_categories(user_id: int) -> List[Dict]:
        """Create default categories for a new user"""
        default_categories = [
            {'name': 'Food & Dining', 'color': '#FF5722', 'is_default': True},
            {'name': 'Transportation', 'color': '#2196F3', 'is_default': True},
            {'name': 'Shopping', 'color': '#E91E63', 'is_default': True},
            {'name': 'Groceries', 'color': '#4CAF50', 'is_default': True},
            {'name': 'Entertainment', 'color': '#9C27B0', 'is_default': True},
            {'name': 'Utilities', 'color': '#FF9800', 'is_default': True},
            {'name': 'Healthcare', 'color': '#F44336', 'is_default': True},
            {'name': 'Education', 'color': '#3F51B5', 'is_default': True},
            {'name': 'Travel', 'color': '#00BCD4', 'is_default': True},
            {'name': 'Investment', 'color': '#795548', 'is_default': True},
            {'name': 'Insurance', 'color': '#607D8B', 'is_default': True},
            {'name': 'Personal Care', 'color': '#FFC107', 'is_default': True},
            {'name': 'Uncategorized', 'color': '#9E9E9E', 'is_default': True},
        ]
        
        return [{'user_id': user_id, **cat} for cat in default_categories]
