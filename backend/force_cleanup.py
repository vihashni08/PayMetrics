import os
import sqlite3

# Delete all possible database files
db_files = ['paymetrics.db', 'instance/paymetrics.db', 'app.db', 'database.db']
for db_file in db_files:
    if os.path.exists(db_file):
        os.remove(db_file)
        print(f"✅ Deleted {db_file}")

# Also check instance folder
if os.path.exists('instance'):
    for file in os.listdir('instance'):
        if file.endswith('.db'):
            os.remove(f'instance/{file}')
            print(f"✅ Deleted instance/{file}")

# Delete token files
auth_files = ['token.json', 'token.pickle', 'credentials.pickle']
for auth_file in auth_files:
    if os.path.exists(auth_file):
        os.remove(auth_file)
        print(f"✅ Deleted {auth_file}")

print("🧹 Complete cleanup done!")
