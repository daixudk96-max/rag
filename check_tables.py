import psycopg

conn = psycopg.connect('postgresql://postgres:postgres@localhost:5432/rag')
cursor = conn.cursor()

cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
tables = cursor.fetchall()

print(f"Tables in database: {len(tables)}")
for t in tables:
    print(f"  - {t[0]}")

cursor.close()
conn.close()