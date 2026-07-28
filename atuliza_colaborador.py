from conector_Postgre import SupabaseConnector
from conector_oracle import OracleConnector
from query import COLABORADOR
import pandas as pd  

oracle = OracleConnector()

oracle.conectar()

df = oracle.executar_query(COLABORADOR)
oracle.fechar_conexao()

postgre = SupabaseConnector()
postgre._create_engine()
postgre.load_dataframe(df,'colaboradores')
postgre.fechar_conexao()
