from conector_oracle import OracleConnector


oracle_connector = OracleConnector()

query = """
SELECT 
	cracha,
	NOME_FUNCIONARIO AS nome,
	descricao_situacao,
	DESCRICAO_CARGO AS titulo_reduzido_cargo,
	data_demissao	
FROM   apl_vetorh.USU_VPB_COLAB uvc
"""

oracle_connector.conectar()  
df = oracle_connector.executar_query(query) 

print(df.head()) 