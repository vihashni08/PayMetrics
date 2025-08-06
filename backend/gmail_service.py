import os
import re
import base64
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

class GmailService:
    SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
    
    def __init__(self):
        self.credentials = None
        self.service = None
        self._authenticate()

    def _authenticate(self):
        """Authenticate with Gmail API using OAuth2 - Enhanced error handling"""
        creds = None
        
        # Always start fresh if token.json has issues
        if os.path.exists('token.json'):
            try:
                creds = Credentials.from_authorized_user_file('token.json', self.SCOPES)
                print("📄 Loaded existing token.json")
            except Exception as e:
                print(f"⚠️ Token file corrupted: {e}")
                try:
                    os.remove('token.json')
                    print("🗑️ Removed corrupted token.json")
                except:
                    pass
                creds = None
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    print("✅ Refreshed existing Gmail credentials")
                except Exception as e:
                    print(f"⚠️ Failed to refresh credentials: {e}")
                    # Remove corrupted token and start fresh
                    try:
                        if os.path.exists('token.json'):
                            os.remove('token.json')
                    except:
                        pass
                    creds = None
            
            if not creds:
                if not os.path.exists('credentials.json'):
                    raise Exception("❌ credentials.json not found. Please download from Google Cloud Console.")
                
                try:
                    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', self.SCOPES)
                    # ENHANCED: Better OAuth flow configuration
                    flow.redirect_uri = 'http://localhost:8080/'
                    creds = flow.run_local_server(
                        port=8080, 
                        access_type='offline', 
                        prompt='consent',
                        open_browser=True
                    )
                    print("✅ Obtained new Gmail credentials with refresh token")
                except Exception as e:
                    print(f"❌ Failed to authenticate with Gmail: {e}")
                    raise Exception(f"Gmail authentication failed: {e}")
            
            # Enhanced credential saving with validation
            try:
                token_data = json.loads(creds.to_json())
                
                # Validate required fields
                required_fields = ['token', 'client_id', 'client_secret']
                missing_fields = [field for field in required_fields if field not in token_data]
                
                if missing_fields:
                    print(f"⚠️ Warning: Missing fields in credentials: {missing_fields}")
                
                with open('token.json', 'w') as token_file:
                    json.dump(token_data, token_file, indent=2)
                
                # Verify the saved token has refresh_token
                if 'refresh_token' not in token_data:
                    print("⚠️ Warning: No refresh_token in saved credentials")
                else:
                    print("✅ Refresh token saved successfully")
                    
            except Exception as e:
                print(f"⚠️ Failed to save credentials: {e}")
        
        self.credentials = creds
        
        try:
            self.service = build('gmail', 'v1', credentials=creds)
            # Test the service with a simple call
            self.service.users().getProfile(userId='me').execute()
            print("✅ Successfully authenticated with Gmail API")
        except Exception as e:
            print(f"❌ Failed to build Gmail service: {e}")
            raise Exception(f"Gmail service initialization failed: {e}")

    def get_recent_bank_emails(self, user_email, days=30):
        """Fetch REAL UPI transaction emails from HDFC InstaAlerts - Enhanced"""
        try:
            start_date = datetime.now() - timedelta(days=days)
            date_filter = start_date.strftime('%Y/%m/%d')
            
            # ENHANCED: More comprehensive search queries
            search_queries = [
                # Most specific - UPI transactions
                f'from:alerts@hdfcbank.net AND subject:"UPI txn" AND after:{date_filter}',
                # Backup - general debit transactions
                f'from:alerts@hdfcbank.net AND body:"Dear Customer" AND body:"has been debited" AND after:{date_filter}',
                # Alternative - any HDFC debit with amount
                f'from:hdfcbank AND body:"Rs." AND body:"debited from account" AND after:{date_filter}',
                # Fallback - any HDFC transaction alert
                f'from:alerts@hdfcbank.net AND (body:"transaction" OR body:"debited" OR body:"credited") AND after:{date_filter}',
            ]
            
            all_messages = []
            successful_query = None
            
            for i, query in enumerate(search_queries, 1):
                try:
                    print(f"🔍 Search query {i}: {query[:80]}...")
                    
                    results = self.service.users().messages().list(
                        userId='me',
                        q=query,
                        maxResults=50  # Increased from 25
                    ).execute()
                    
                    messages = results.get('messages', [])
                    
                    if messages:
                        print(f"✅ Query {i} found {len(messages)} emails")
                        all_messages.extend(messages)
                        successful_query = i
                        break  # Stop on first successful query
                    else:
                        print(f"📭 Query {i} found 0 emails")
                    
                except Exception as e:
                    print(f"⚠️ Search query {i} failed: {e}")
                    continue
            
            if not all_messages:
                print("❌ No emails found with any search query")
                print("💡 Suggestions:")
                print("   - Check if HDFC sends alerts to this Gmail account")
                print("   - Verify email address matches your bank account")
                print("   - Try increasing the date range (days parameter)")
                return []
            
            # ENHANCED: Remove duplicates and sort by date
            unique_messages = []
            seen_ids = set()
            
            for msg in all_messages:
                if msg['id'] not in seen_ids:
                    unique_messages.append(msg)
                    seen_ids.add(msg['id'])
            
            print(f"📧 Processing {len(unique_messages)} unique emails (found with query {successful_query})")
            
            emails = []
            processed_count = 0
            
            # Process more emails but limit final results
            for message in unique_messages[:30]:  # Process up to 30 emails
                try:
                    processed_count += 1
                    msg = self.service.users().messages().get(
                        userId='me',
                        id=message['id'],
                        format='full'
                    ).execute()
                    
                    headers = msg['payload'].get('headers', [])
                    sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
                    subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
                    date_header = next((h['value'] for h in headers if h['name'] == 'Date'), '')
                    
                    body = self._extract_email_body(msg['payload'])
                    
                    # Filter for actual transaction emails
                    if self._is_real_transaction_email(body, subject, sender):
                        emails.append({
                            'id': message['id'],
                            'sender': sender,
                            'subject': subject,
                            'body': body,
                            'date': self._parse_email_date(date_header)
                        })
                    
                except Exception as e:
                    print(f"⚠️ Error processing message {processed_count}: {str(e)}")
                    continue
            
            # Sort emails by date (newest first)
            emails.sort(key=lambda x: x['date'], reverse=True)
            
            print(f"✅ Found {len(emails)} valid transaction emails")
            return emails
            
        except Exception as e:
            print(f"❌ Error fetching Gmail emails: {str(e)}")
            return []

    def _is_real_transaction_email(self, body, subject, sender):
        """Enhanced transaction email validation with better logging"""
        sender_lower = sender.lower()
        subject_lower = subject.lower()
        body_lower = body.lower() if body else ""
        
        # Must be from HDFC alerts
        if 'alerts@hdfcbank' not in sender_lower and 'hdfcbank' not in sender_lower:
            return False
        
        # UPI transaction subject is definitive
        if 'upi txn' in subject_lower or 'upi transaction' in subject_lower:
            return True
        
        # Check for transaction content in body
        if body_lower:
            transaction_indicators = [
                'dear customer',
                'has been debited',
                'rs.',
                'inr',
                'account',
                'transaction',
                'debited from',
                'credited to'
            ]
            
            indicator_count = sum(1 for indicator in transaction_indicators if indicator in body_lower)
            
            # Need at least 2 indicators for confidence
            if indicator_count >= 2:
                return True
        
        # Exclude obvious promotional emails
        exclude_keywords = [
            'maintenance', 'downtime', 'newsletter', 'unsubscribe', 
            'app update', 'offer', 'congratulations', 'winner',
            'click here', 'download', 'install'
        ]
        
        if any(keyword in subject_lower or keyword in body_lower for keyword in exclude_keywords):
            return False
        
        # Accept HDFC alerts by default if they contain money-related terms
        money_terms = ['rs.', 'inr', 'amount', 'balance', 'account']
        if any(term in subject_lower or term in body_lower for term in money_terms):
            return True
        
        return False

    def _extract_email_body(self, payload):
        """Enhanced email body extraction with better error handling"""
        plain_text = ""
        html_content = ""
        
        def extract_from_part(part):
            nonlocal plain_text, html_content
            
            mime_type = part.get('mimeType', '')
            body_data = part.get('body', {}).get('data')
            
            if body_data:
                try:
                    decoded = base64.urlsafe_b64decode(body_data).decode('utf-8', errors='ignore')
                    
                    if mime_type == 'text/plain':
                        if len(decoded.strip()) > len(plain_text.strip()):
                            plain_text = decoded
                    elif mime_type == 'text/html':
                        if len(decoded.strip()) > len(html_content.strip()):
                            html_content = decoded
                            
                except Exception as e:
                    print(f"⚠️ Error decoding email part ({mime_type}): {e}")
        
        try:
            # Extract content from email structure
            if 'parts' in payload:
                for part in payload['parts']:
                    if 'parts' in part:
                        for subpart in part['parts']:
                            extract_from_part(subpart)
                    else:
                        extract_from_part(part)
            else:
                extract_from_part(payload)
        except Exception as e:
            print(f"⚠️ Error extracting email structure: {e}")
        
        # Return best available content with preference for plain text
        if plain_text and len(plain_text.strip()) > 20:
            return plain_text.strip()
        elif html_content:
            return self._html_to_text(html_content)
        
        return ""

    def _html_to_text(self, html_content):
        """Enhanced HTML to text conversion"""
        try:
            # Remove script and style elements
            html_content = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
            html_content = re.sub(r'<style[^>]*>.*?</style>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
            
            # Remove HTML tags but preserve line breaks
            text = re.sub(r'<br\s*/?>', '\n', html_content, flags=re.IGNORECASE)
            text = re.sub(r'<p[^>]*>', '\n', text, flags=re.IGNORECASE)
            text = re.sub(r'</p>', '\n', text, flags=re.IGNORECASE)
            text = re.sub(r'<[^>]+>', ' ', text)
            
            # Clean up text
            text = re.sub(r'\s+', ' ', text)
            text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
            text = text.replace('&quot;', '"').replace('&#39;', "'")
            
            # ENHANCED: Better transaction content extraction
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            
            # Look for lines with transaction keywords
            transaction_keywords = ['dear customer', 'rs.', 'inr', 'debited', 'credited', 'account', 'vpa', 'upi', 'transaction']
            relevant_lines = []
            
            for line in lines:
                line_lower = line.lower()
                if any(keyword in line_lower for keyword in transaction_keywords):
                    relevant_lines.append(line)
                # Also include lines with numbers (likely amounts or account numbers)
                elif re.search(r'\d+', line) and len(line) > 10:
                    relevant_lines.append(line)
            
            result = ' '.join(relevant_lines) if relevant_lines else ' '.join(lines)
            return result.strip()
            
        except Exception as e:
            print(f"⚠️ HTML parsing error: {e}")
            return html_content

    def _parse_email_date(self, date_str):
        """Enhanced email date parsing with fallback"""
        try:
            if date_str:
                from email.utils import parsedate_to_datetime
                parsed_date = parsedate_to_datetime(date_str)
                return parsed_date
        except Exception as e:
            print(f"⚠️ Error parsing date '{date_str}': {e}")
        
        return datetime.now()

    def parse_transaction_email(self, email_content: str, sender_email: str, subject: str) -> Optional[Dict]:
        """Enhanced transaction parsing with better error handling and logging"""
        
        if not email_content or not email_content.strip():
            print("❌ Empty email content")
            return None
        
        print(f"🔍 Parsing email: {subject[:50]}...")
        
        # ENHANCED: More comprehensive regex patterns
        patterns = [
            # Pattern 1: Full HDFC format with merchant and date
            r'Dear Customer,?\s*Rs\.?\s?([\d,]+\.?\d*)\s+has been debited from account\s+(\d+)\s+to VPA [^\s]+\s+([A-Z][A-Z\s]+?)(?:\s+on\s+(\d{2}-\d{2}-\d{2}))?',
            
            # Pattern 2: Simplified HDFC format
            r'Rs\.?\s?([\d,]+\.?\d*)\s+has been debited from account\s+(\d+)\s*(?:to VPA [^\s]+\s+([A-Z][A-Z\s]+?))?',
            
            # Pattern 3: Alternative format with INR
            r'INR\s?([\d,]+\.?\d*)\s+(?:has been )?debited from.*?account.*?(\d{4})',
            
            # Pattern 4: Generic debit pattern
            r'(?:Rs\.?|INR)\s?([\d,]+\.?\d*)\s+(?:debited|deducted)\s+from.*?account.*?(\d{4})',
            
            # Pattern 5: UPI transaction pattern
            r'UPI.*?Rs\.?\s?([\d,]+\.?\d*).*?account.*?(\d{4})',
        ]
        
        transaction_data = None
        
        for i, pattern in enumerate(patterns, 1):
            try:
                match = re.search(pattern, email_content, re.IGNORECASE | re.DOTALL)
                if match:
                    amount_str = match.group(1).replace(',', '').replace('Rs', '').replace('INR', '').strip()
                    amount = float(amount_str)
                    
                    # Extract account number (last 4 digits)
                    account_number = match.group(2)
                    account_last_four = account_number[-4:] if len(account_number) >= 4 else account_number
                    
                    # Extract merchant name if available
                    merchant = "Unknown Merchant"
                    if len(match.groups()) >= 3 and match.group(3):
                        merchant = match.group(3).strip().title()
                        # Clean merchant name
                        merchant = re.sub(r'\s+', ' ', merchant).strip()
                        if len(merchant) > 40:
                            merchant = merchant[:40].strip()
                    
                    # Extract transaction date if available
                    transaction_date = datetime.now()
                    if len(match.groups()) >= 4 and match.group(4):
                        try:
                            date_str = match.group(4)
                            day, month, year = map(int, date_str.split('-'))
                            year = 2000 + year if year < 50 else 1900 + year
                            transaction_date = datetime(year, month, day)
                        except Exception as date_error:
                            print(f"⚠️ Error parsing date: {date_error}")
                    
                    transaction_data = {
                        'amount': amount,
                        'account_last_four': account_last_four,
                        'account_type': 'debit_card',  # UPI typically linked to debit card
                        'merchant': merchant,
                        'transaction_date': transaction_date,
                        'bank': 'HDFC',
                        'description': f"UPI Payment to {merchant}",
                        'sender_email': sender_email,
                        'subject': subject,
                        'category': self._categorize_merchant(merchant)
                    }
                    
                    print(f"✅ Parsed with pattern {i}: {merchant} - ₹{amount}")
                    break
                    
            except (ValueError, IndexError) as e:
                print(f"⚠️ Error parsing with pattern {i}: {e}")
                continue
            except Exception as e:
                print(f"⚠️ Unexpected error with pattern {i}: {e}")
                continue
        
        if not transaction_data:
            print(f"❌ No transaction data extracted from: {email_content[:100]}...")
        
        return transaction_data

    def _categorize_merchant(self, merchant):
        """Enhanced merchant categorization with more comprehensive categories"""
        if not merchant or merchant == "Unknown Merchant" or merchant.strip() == "":
            return 'Transfer'
        
        merchant_lower = merchant.lower().strip()
        
        # Person names (UPI P2P transfers) - improved regex
        person_pattern = r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}$'
        if re.match(person_pattern, merchant.strip()):
            return 'Transfer'
        
        # Business categories with comprehensive keywords
        categories = {
            'Food & Dining': [
                'zomato', 'swiggy', 'food', 'restaurant', 'cafe', 'hotel', 'dominos', 'pizza', 
                'kfc', 'mcdonalds', 'starbucks', 'ccd', 'burger', 'kitchen', 'biryani',
                'dining', 'eatery', 'canteen', 'dhaba', 'bakery'
            ],
            'Shopping': [
                'amazon', 'flipkart', 'myntra', 'shopping', 'store', 'mall', 'reliance', 
                'dmart', 'big bazaar', 'lifestyle', 'shoppers', 'mart', 'supermarket',
                'retail', 'fashion', 'clothing', 'electronics', 'mobile', 'laptop'
            ],
            'Transportation': [
                'uber', 'ola', 'metro', 'petrol', 'fuel', 'transport', 'indian oil', 
                'bharat petroleum', 'hp petrol', 'taxi', 'auto', 'bus', 'train',
                'parking', 'toll', 'travel', 'railway'
            ],
            'Entertainment': [
                'netflix', 'spotify', 'prime', 'entertainment', 'movie', 'cinema', 
                'hotstar', 'youtube', 'gaming', 'music', 'subscription', 'ott',
                'theater', 'multiplex', 'concert'
            ],
            'Utilities': [
                'electricity', 'gas', 'water', 'mobile', 'internet', 'airtel', 'jio', 
                'vodafone', 'bsnl', 'broadband', 'wifi', 'recharge', 'bill', 'utility'
            ],
            'Healthcare': [
                'hospital', 'medical', 'pharmacy', 'medicine', 'doctor', 'apollo', 
                'fortis', 'medplus', 'clinic', 'health', 'dental', 'lab', 'diagnostic'
            ],
            'Education': [
                'school', 'college', 'university', 'course', 'exam', 'fees', 'education',
                'tuition', 'coaching', 'learning', 'academy', 'institute'
            ],
            'Financial Services': [
                'bank', 'insurance', 'investment', 'mutual fund', 'sip', 'loan', 'emi',
                'credit card', 'demat', 'trading', 'policy'
            ]
        }
        
        for category, keywords in categories.items():
            if any(keyword in merchant_lower for keyword in keywords):
                return category
        
        # If no category matches, check if it looks like a business name
        if any(word in merchant_lower for word in ['pvt', 'ltd', 'inc', 'corp', 'company', 'services']):
            return 'Services'
        
        return 'Transfer'  # Default for person-to-person payments

    def process_user_emails(self, user_email):
        """Main processing function with enhanced error handling and reporting"""
        try:
            print(f"🔄 Processing emails for: {user_email}")
            print("=" * 50)
            
            emails = self.get_recent_bank_emails(user_email, days=30)
            
            if not emails:
                print("❌ No emails found to process")
                return []
            
            parsed_transactions = []
            processing_errors = 0
            
            for i, email_data in enumerate(emails, 1):
                try:
                    print(f"\n📧 Processing email {i}/{len(emails)}: {email_data['subject'][:50]}...")
                    
                    parsed = self.parse_transaction_email(
                        email_data['body'],
                        email_data['sender'],
                        email_data['subject']
                    )
                    
                    if parsed:
                        parsed['email_id'] = email_data['id']
                        # Use email date instead of parsed date for consistency
                        parsed['transaction_date'] = email_data['date']
                        parsed_transactions.append(parsed)
                        print(f"✅ Success: {parsed['merchant']} - ₹{parsed['amount']:.2f}")
                    else:
                        processing_errors += 1
                        print(f"⚠️ No data extracted from this email")
                        
                except Exception as e:
                    processing_errors += 1
                    print(f"❌ Error processing email {i}: {str(e)}")
                    continue
            
            print("=" * 50)
            print(f"🎉 Processing complete:")
            print(f"   📧 Emails found: {len(emails)}")
            print(f"   ✅ Successfully parsed: {len(parsed_transactions)}")
            print(f"   ⚠️ Processing errors: {processing_errors}")
            
            return parsed_transactions
            
        except Exception as e:
            print(f"❌ Critical error in process_user_emails: {e}")
            return []
