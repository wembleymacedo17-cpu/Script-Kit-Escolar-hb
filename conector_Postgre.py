import os
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL



class SupabaseConnector:
    def __init__(self, env_path: str = None):
        if env_path is None:
            env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
        load_dotenv(env_path, override=True, encoding='utf-8')
        self.user = os.getenv('SUPABASE_USER', '').strip()
        self.password = os.getenv('SUPABASE_PASSWORD', '').strip()
        self.host = os.getenv('SUPABASE_HOST', '').strip()
        self.port = os.getenv('SUPABASE_PORT', '').strip()
        self.db = os.getenv('SUPABASE_DB', '').strip()

        self.engine = self._create_engine()

    def _create_engine(self):
        """Cria a engine do Postgres via SQLAlchemy com segurança."""
        # URL.create lida com caracteres especiais (como **) automaticamente
        connection_url = URL.create(
            drivername="postgresql+psycopg2",
            username=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
            database=self.db
        )
        return create_engine(connection_url)

    def load_dataframe(self, df: pd.DataFrame, table_name: str, if_exists: str = 'replace', chunksize: int = 10000):
        """
        Carrega o DataFrame para o Supabase.
        if_exists: 'replace' (apaga e cria nova) ou 'append' (adiciona)
        """
        try:
            print(f"Iniciando carga da tabela '{table_name}'...")
            
            df.to_sql(
                name=table_name,
                con=self.engine,
                if_exists=if_exists,
                index=False,
                chunksize=chunksize,
                method='multi'
            )
            print(f"✅ Carga concluída com sucesso para '{table_name}'!")
            
        except Exception as e:
            print(f"❌ Erro ao subir dados para o Supabase: {e}")
            raise
    def fechar_conexao(self):
         """Fecha a conexão (boa prática)"""
         if self.engine:
             self.engine.dispose()
             print("🔌 Conexão encerrada.")     