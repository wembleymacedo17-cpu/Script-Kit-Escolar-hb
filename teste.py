# teste.py
from database import engine, init_db
from sqlalchemy import text

print("Testando conexão...")

try:
    init_db()
    with engine.connect() as conn:
        result = conn.execute(text("SELECT version();"))
        print("✅ Conexão com PostgreSQL OK!")
        print("Versão:", result.scalar())
except Exception as e:
    print("❌ Erro na conexão:", e)
