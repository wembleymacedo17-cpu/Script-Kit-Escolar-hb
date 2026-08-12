


COLABORADOR="""
SELECT 
    a.numcad AS cracha,
    a.nomfun AS nome,
    b.dessit AS descricao_situacao,
    car.codcar AS id_cargo,
    car.titcar AS titulo_reduzido_cargo,
    a.datafa AS data_demissao

FROM r034fun a
LEFT JOIN r010sit b 
    ON a.sitafa = b.codsit
LEFT JOIN r038hca hca
    ON a.numemp = hca.numemp
   AND a.tipcol = hca.tipcol
   AND a.numcad = hca.numcad
   AND hca.datalt = (
       SELECT MAX(hca2.datalt)
       FROM r038hca hca2
       WHERE hca2.numemp = hca.numemp
         AND hca2.tipcol = hca.tipcol
         AND hca2.numcad = hca.numcad
   )
LEFT JOIN r024car car
    ON car.estcar = hca.estcar
   AND car.codcar = hca.codcar

WHERE a.numemp IN (1, 2, 5) 
  AND a.tipcol IN (1, 2)

ORDER BY a.nomfun
"""



busca_suba = """SELECT cracha , nome_funcionario, situacao, descricao_situacao FROM colaboradores  """

