import sqlite3
import json

# Check if validation_status.json is SQLite or JSON
try:
    conn = sqlite3.connect('validation_status.json')
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print("validation_status.json is SQLite database")
    print("Existing tables:")
    for t in tables:
        print(f"  - {t[0]}")
    conn.close()
except:
    print("validation_status.json is not SQLite, checking if it's JSON")
    with open('validation_status.json', 'r') as f:
        data = json.load(f)
        print("validation_status.json is JSON file")
        print("Keys:", list(data.keys()))