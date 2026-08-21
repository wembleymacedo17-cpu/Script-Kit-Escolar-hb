import os
from datetime import datetime, timezone
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Date, DateTime, BigInteger, Text, ForeignKey, UniqueConstraint, CheckConstraint, Boolean, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker, relationship, declarative_base


# ===================== CONFIGURAÇÃO =====================
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(env_path, override=True, encoding='utf-8')

SUPABASE_USER = os.getenv('SUPABASE_USER', '').strip()
SUPABASE_PASSWORD = os.getenv('SUPABASE_PASSWORD', '').strip()
SUPABASE_HOST = os.getenv('SUPABASE_HOST', '').strip()
SUPABASE_PORT = os.getenv('SUPABASE_PORT', '').strip()
SUPABASE_DB = os.getenv('SUPABASE_DB', '').strip()

DATABASE_URL = URL.create(
    drivername="postgresql+psycopg2",
    username=SUPABASE_USER,
    password=SUPABASE_PASSWORD,
    host=SUPABASE_HOST,
    port=SUPABASE_PORT,
    database=SUPABASE_DB
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# ===================== MODELOS =====================

class Colaborador(Base):
    __tablename__ = "colaboradores"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    cracha = Column(BigInteger, unique=True, nullable=False)
    nome = Column(Text, nullable=False)
    descricao_situacao = Column(Text)
    titulo_reduzido_cargo = Column(Text)
    data_demissao = Column(Date)
    criado_em = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    situacao = Column(Integer)

    # 🔒 COLUNAS TOTP
    totp_secret = Column(String(32), nullable=True)
    totp_ativo = Column(Boolean, default=False)

    dependentes = relationship("Dependente", back_populates="colaborador", cascade="all, delete-orphan")


class Dependente(Base):
    __tablename__ = "dependentes"
    id_dependente = Column(Integer, primary_key=True, autoincrement=True)
    id_colaborador = Column(BigInteger, ForeignKey("colaboradores.id", ondelete="CASCADE"), nullable=False)
    nome_filho = Column(Text, nullable=False)
    data_nascimento = Column(Date)
    genero = Column(String(50))
    escolaridade = Column(String(100))
    ano_escola = Column(String(50))
    data_cadastro = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    revisao_rh = Column(String(50))
    motivo_reprova_ia = Column(String, nullable=True)
    url_documento = Column(String, nullable=True)

    # 🔒 COLUNAS DE COMPLIANCE
    aceite_ia = Column(Boolean, default=False)
    aceite_lgpd = Column(Boolean, default=False)
    data_aceite = Column(DateTime, nullable=True)

    # Registro de fluxo e documento
    fluxo_documento = Column(Text, nullable=True)

    colaborador = relationship("Colaborador", back_populates="dependentes")
    escolha = relationship("EscolhaKit", back_populates="dependente", uselist=False)


class EscolhaKit(Base):
    __tablename__ = "escolhas_kits"
    id_escolha = Column(Integer, primary_key=True, autoincrement=True)
    id_colaborador = Column(BigInteger, ForeignKey("colaboradores.id", ondelete="CASCADE"), nullable=False)
    id_dependente = Column(Integer, ForeignKey("dependentes.id_dependente", ondelete="CASCADE"), nullable=False)
    kit_escolhido = Column(String(150), nullable=False)
    data_escolha = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    aceite_variacao_kit = Column(Boolean, default=False)
    data_aceite_variacao = Column(DateTime, nullable=True)

    dependente = relationship("Dependente", back_populates="escolha")

    __table_args__ = (UniqueConstraint('id_dependente', name='uk_dependente_kit'),)


class Retirada(Base):
    __tablename__ = "retiradas"
    id_retirada = Column(Integer, primary_key=True, autoincrement=True)
    codigo_retirada = Column(String(255), unique=True, nullable=False)
    id_colaborador = Column(BigInteger, ForeignKey("colaboradores.id", ondelete="CASCADE"), nullable=False)
    email = Column(String(150))
    telefone = Column(String(20))
    qtd_kits = Column(Integer, nullable=False)
    resumo_kits = Column(Text)
    status = Column(String(20), default='PENDENTE', nullable=False)
    data_geracao = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    data_entrega = Column(DateTime)

    __table_args__ = (CheckConstraint("status IN ('PENDENTE', 'ENTREGUE')", name='chk_status_retirada'),)


# ===================== FUNÇÕES E MÉTODOS =====================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Cria as tabelas no banco de dados"""
    Base.metadata.create_all(bind=engine)
    print("✅ Tabelas criadas ou já existentes.")


def atualizar_colaboradores_merge(engine_db, df_oracle: pd.DataFrame):
    """
    Carrega os dados do Oracle mantendo os campos de TOTP intactos no Postgres.
    """
    try:
        # 1. Carrega dados do Oracle na tabela temporária de Staging
        df_oracle.to_sql(
            name='stg_colaboradores',
            con=engine_db,
            if_exists='replace',
            index=False,
            chunksize=10000,
            method='multi'
        )
        
        # 2. Executa MERGE (UPSERT) da Staging para a Tabela Principal 'colaboradores'
        query_upsert = """
            INSERT INTO colaboradores (
                cracha, 
                nome, 
                descricao_situacao, 
                titulo_reduzido_cargo, 
                data_demissao, 
                situacao, 
                totp_secret, 
                totp_ativo
            )
            SELECT 
                s.cracha, 
                s.nome, 
                s.descricao_situacao, 
                s.titulo_reduzido_cargo, 
                s.data_demissao, 
                s.situacao,
                NULL AS totp_secret,
                FALSE AS totp_ativo
            FROM stg_colaboradores s
            ON CONFLICT (cracha) DO UPDATE SET
                nome = EXCLUDED.nome,
                descricao_situacao = EXCLUDED.descricao_situacao,
                titulo_reduzido_cargo = EXCLUDED.titulo_reduzido_cargo,
                data_demissao = EXCLUDED.data_demissao,
                situacao = EXCLUDED.situacao;
            
            -- Limpa a tabela temporária após a sincronização
            DROP TABLE IF EXISTS stg_colaboradores;
        """
        
        with engine_db.begin() as conn:
            conn.execute(text(query_upsert))
        print("✅ Tabela 'colaboradores' sincronizada com sucesso mantendo os dados de TOTP!")

    except Exception as e:
        print(f"❌ Erro ao realizar o MERGE dos colaboradores: {e}")
        raise e


if __name__ == "__main__":
    init_db()