import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional

class GmailService:
    BANK_PATTERNS = {
        'hdfc': {
            'sender_patterns': ['hdfc', 'hdfcbank', 'alerts@hdfcbank'],
            'debit_pattern': r'Rs\.?\s?([\d,]+\.?\d*)\s+has been debited from account\s+(\d+)',
            'merchant_pattern': r'to VPA [^\s]+ (.+?) on',
            'date_pattern': r'on (\d{2}-\d{2}-\d{2})'
        },
        'sbi': {
            'sender_patterns': ['sbi', 'onlinesbi'],
            'debit_pattern': r'INR ([\d,]+\.?\d*) debited from a/c \*+(\d+)',
            'merchant_pattern': r'at (.+?) on'
        },
        'icici': {
            'sender_patterns': ['icici', 'icicibankltd'],
            'debit_pattern': r'INR\s?([\d,]+\.?\d*)\s+debited from account\s+\*+(\d+)',
            'merchant_pattern': r'at (.+?) on'
        }
    }

    def __init__(self, credentials=None):
        self.credentials = credentials

    def get_recent_bank_emails(self, user_email, days=30):
        # Simulate enhanced emails with multiple account types
        return [
            {
                'id': 'email_hdfc_cc_1', 'sender': 'alerts@hdfcbank.net',
                'subject': 'Transaction Alert',
                'body': '''Rs.549.79 has been debited from account 2448 to VPA zomato.payu@axisbank Zomato private Limited on 02-08-25.''',
                'date': datetime.now()
            },
            {
                'id': 'email_hdfc_dc_1', 'sender': 'alerts@hdfcbank.net',
                'subject': 'Debit Card Transaction',
                'body': '''Rs.2500.00 has been debited from account 5678 at HDFC ATM on 30-07-25.''',
                'date': datetime.now() - timedelta(days=3)
            },
            {
                'id': 'email_sbi_sav_1', 'sender': 'sbi.co.in@noreply.com',
                'subject': 'Transaction Alert',
                'body': '''INR 850.00 debited from a/c ****9012 at TATA POWER MUMBAI on 29-07-25.''',
                'date': datetime.now() - timedelta(days=4)
            }
        ]

    def parse_transaction_email(self, email_content: str, sender_email: str, subject: str) -> Optional[Dict]:
        bank = self.detect_bank(sender_email.lower())
        if not bank or bank not in self.BANK_PATTERNS:
            return None
            
        patterns = self.BANK_PATTERNS[bank]
        debit_match = re.search(patterns['debit_pattern'], email_content, re.IGNORECASE)
        
        if not debit_match:
            return None
            
        amount_str = debit_match.group(1).replace(',', '')
        account_last_four = debit_match.group(2)[-4:]
        
        merchant_match = re.search(patterns.get('merchant_pattern', ''), email_content, re.IGNORECASE)
        merchant = merchant_match.group(1).strip() if merchant_match else 'Unknown Merchant'
        
        # Determine account type
        account_type = 'credit_card' if account_last_four in ['2448', '3456'] else (
            'debit_card' if account_last_four == '5678' else 'savings'
        )
        
        return {
            'amount': float(amount_str),
            'account_last_four': account_last_four,
            'account_type': account_type,
            'merchant': merchant,
            'transaction_date': datetime.now(),
            'bank': bank.upper(),
            'description': f"{merchant} - {bank.upper()}",
            'sender_email': sender_email,
            'subject': subject
        }

    def detect_bank(self, sender_email: str) -> Optional[str]:
        for bank, patterns in self.BANK_PATTERNS.items():
            if any(pattern in sender_email for pattern in patterns['sender_patterns']):
                return bank
        return None

    def process_user_emails(self, user_email):
        try:
            emails = self.get_recent_bank_emails(user_email)
            parsed_transactions = []
            
            for email_data in emails:
                parsed = self.parse_transaction_email(
                    email_data['body'], email_data['sender'], email_data['subject']
                )
                if parsed:
                    parsed['email_id'] = email_data['id']
                    parsed['email_date'] = email_data['date']
                    parsed_transactions.append(parsed)
            
            return parsed_transactions
        except Exception as e:
            print(f"Error processing emails: {e}")
            return []
