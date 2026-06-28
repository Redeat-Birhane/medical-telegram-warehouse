import psycopg2

try:
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        dbname="medical_warehouse",
        user="postgres",
        password="2018"
    )
    print("SUCCESS — connected to PostgreSQL")
    conn.close()
except Exception as e:
    print(f"FAILED: {e}")