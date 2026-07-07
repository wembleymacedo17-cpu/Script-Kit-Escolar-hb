ENTRADA: crachá do colaborador
        ↓
1. BUSCA DEPENDENTES CADASTRADOS
   Abre dependentes.xlsx → filtra por ID_Colaborador = crachá
        ↓
2. GERA CRÉDITOS
   Para cada dependente encontrado:
   → 1 crédito na categoria da escolaridade dele
   
   Exemplo:
   João   → Ensino Médio       → 1 crédito Ensino Médio
   Mirella → Ensino Fundamental I → 1 crédito Ensino Fundamental I
        ↓
3. EXIBE SELEÇÃO DE KIT POR CRÉDITO
   Para cada crédito:
   → Mostra nome do dependente
   → Mostra apenas os kits disponíveis para aquela escolaridade
   → Colaborador escolhe 1 kit por crédito
   
   Exemplo:
   [João - Ensino Médio]
     ○ Kit Ensino Médio A
     ○ Kit Ensino Médio B  ← escolheu
     ○ Kit Ensino Médio C

   [Mirella - Ensino Fundamental I]
     ○ Kit Fund. I A  ← escolheu
     ○ Kit Fund. I B
     ○ Kit Fund. I C
        ↓
4. CONFIRMA ESCOLHA
   Exibe resumo das escolhas antes de finalizar
        ↓
5. SALVA
   → Grava escolhas em outra tabela (kits_escolhidos.xlsx)
   → Gera QR code com os dados











   ------------------------------ FLUXO COMPLETO 

1. Colaborador finaliza cadastro
2. Sistema cria Codigo_Retirada
3. Sistema salva retirada no banco com Status = NAO ENTREGUE
4. Sistema gera QR Code com URL /retirada/{codigo}
5. Responsável escaneia QR Code
6. Celular abre a página da retirada
7. Site chama a API buscando o código
8. API consulta o banco
9. Se status = NAO ENTREGUE:
      mostra dados + botão ENTREGAR KIT
10. Se status = ENTREGUE:
      mostra aviso: kit já retirado
11. Responsável clica ENTREGAR KIT
12. Site chama API de baixa
13. API muda status para ENTREGUE
14. QR Code fica inválido para nova retirada
