[ 1. BUSCA DE CRACHÁ ]
       │
       ├─► Colaborador digita o número do crachá e pressiona "Enter" ou clica em "Buscar".
       ├─► Sistema consulta o banco de dados Supabase e valida a elegibilidade (descarta desligados/inativos).
       └─► Se válido: Exibe os dados do colaborador (Nome, Cargo, Situação).

       [ 2. DADOS DE CONTATO ]
       │
       ├─► Formulário simples sem seletores de domínio complexos:
       │      ├─ Campo E-mail + Campo Confirme o E-mail
       │      └─ Número de Telefone (WhatsApp)
       │
       ├─► Validação de E-mail: Aceita o cadastro se `email_1.lower() == email_2.lower()`.
       └─► Após salvar o contato com sucesso: As caixas de Busca e de Contato somem da tela, 
           mantendo apenas um resumo no topo e deixando a interface limpa.


           [ 3. TRIAGEM DE VÍNCULO (AVALIA CASO COLABORADOR) ]
       │
       ├─► O colaborador escolhe umas das opcoes de vinclo:

       │
       ├──► OPÇÃO A:Filho(a) biológico(a) ou adotivo(a):
                   OPCOES DE VALIDAÇOES 
                   A1:Filho(a) biológico(a) ou adotivo(a):  
       │           Anexa Certidão de Nascimento da criança.
       │            IA Gemini valida:
       │            ├─ Documento é certidão válida? (Se não: "Documento adicionado nao e um certidao de nascimento")
       │            ├─ Documento está legível? (Se não: "Documento esta inlegivel , carregue outro")
       │            ├─ Dados batem com formulário (Nome, Data e Sexo)?
       │            └─ Nome do colaborador bate com Pai ou Mãe na certidão?
       │            
                    A2:Certidão de nascimento com averbação de adoção
                    A2: Certidão de nascimento com averbação de adoção
                     Anexa Certidão de Nascimento constando a averbação.
                     IA Gemini valida:
                     ├─ Documento é uma certidão de nascimento válida? (Se não: "Documento adicionado não é uma certidão de nascimento")
                     ├─ Documento está legível? (Se não: "Documento está ilegível, carregue outro")
                     ├─ Existe a averbação (carimbo/texto oficial) informando a adoção no documento? (Se não: "O documento não possui a averbação de adoção exigida")
                     ├─ Dados da criança batem com formulário (Nome, Data de nascimento e Sexo)?
                     └─ Nome do colaborador consta como pai/mãe na certidão ou na averbação? 

                    A3:Documento judicial que comprove a guarda para fins de adoção
                    Anexa Termo de Guarda e Responsabilidade ou Decisão Judicial.
                     IA Gemini valida:
                     ├─ Documento é de origem judicial (Termo de Guarda, Sentença, etc.)? (Se não: "Documento adicionado não possui validade judicial")
                     ├─ Documento está legível e possui assinatura/validação do juiz (ou código de validação digital)? (Se não: "Documento ilegível ou sem comprovação de autenticidade")
                     ├─ O documento cita explicitamente que a guarda é "para fins de adoção"? (Se não: "O documento não especifica que a guarda é provisória/definitiva para fins de adoção")
                     ├─ Dados da criança batem com formulário (Nome e Data de nascimento)?
                     └─ Nome do colaborador bate com o nome do guardião nomeado no documento?


       ├──► OPÇÃO B: "Filho registrado no nome de outra pessoa Enteado(a)"
                     FORMAS DE VALIDACAO

              **B1: Declaração de União Estável + Certidão de Nascimento**
          Anexa Declaração de União Estável E Certidão de Nascimento da Criança.
│            IA Gemini + Regras de Negócio validam:
│            ├─ Os dois documentos foram enviados e estão legíveis? (Se não: "Documento(s) ausente(s) ou ilegível(is)")
│            ├─ Documento é uma Declaração de União Estável válida?
│            ├─ A União Estável possui firma reconhecida? (Se não: "É NECESSÁRIO RECONHECER FIRMA")
│            ├─ Dados da criança na Certidão de Nascimento batem com o formulário (Nome, Data e Sexo)?
│            ├─ Nome do colaborador consta na União Estável?
│            ├─ O(a) companheiro(a) da União Estável é a MÃE ou PAI na Certidão de Nascimento?
│            └─ Colaborador NÃO é o pai ou mãe na certidão da criança? (Garante que é o caso B e não o A)
             	
              **B2: Certidão de Casamento + Certidão de Nascimento**
          Anexa Certidão de Casamento E Certidão de Nascimento da Criança.
│            IA Gemini + Regras de Negócio validam:
│            ├─ Os dois documentos foram enviados e estão legíveis? (Se não: "Documento(s) ausente(s) ou ilegível(is)")
│            ├─ Documento é uma Certidão de Casamento válida?
│            ├─ A Certidão de Casamento está sem averbação de divórcio? (Se sim: "Certidão indica divórcio, vínculo inválido")
│            ├─ Dados da criança na Certidão de Nascimento batem com o formulário (Nome, Data e Sexo)?
│            ├─ Nome do colaborador consta na Certidão de Casamento?
│            ├─ O(a) cônjuge na Certidão de Casamento é a MÃE ou PAI na Certidão de Nascimento?
│            └─ Colaborador NÃO é o pai ou mãe na certidão da criança? (Garante que é o caso B e não o A) 

             ──► OPÇÃO C: "Criança ou adolescente sob guarda ou tutela"
FORMAS DE VALIDAÇÃO

          **C1: Termo/Certidão de Guarda Judicial + Certidão de Nascimento**
          Anexa Termo/Certidão de Guarda Judicial E Certidão de Nascimento da Criança.
│            IA Gemini + Regras de Negócio validam:
│            ├─ Os dois documentos foram enviados e estão legíveis? (Se não: "Documento(s) ausente(s) ou ilegível(is)")
│            ├─ O documento judicial é um Termo ou Certidão de Guarda válido?
│            ├─ O documento judicial possui assinatura do juiz, carimbo oficial ou código de validação digital? (Se não: "Documento sem comprovação de autenticidade judicial")
│            ├─ Dados da criança na Certidão de Nascimento batem com o formulário (Nome, Data e Sexo)?
│            ├─ O nome da criança/adolescente no Termo de Guarda é exatamente o mesmo da Certidão de Nascimento?
│            └─ O nome do colaborador consta expressamente como o(a) GUARDIÃO(Ã) nomeado(a) no documento judicial?

          **C2: Termo de Tutela Judicial + Certidão de Nascimento**
          Anexa Termo de Tutela Judicial E Certidão de Nascimento da Criança.
│            IA Gemini + Regras de Negócio validam:
│            ├─ Os dois documentos foram enviados e estão legíveis? (Se não: "Documento(s) ausente(s) ou ilegível(is)")
│            ├─ O documento judicial é um Termo de Tutela válido?
│            ├─ O documento judicial possui assinatura do juiz, carimbo oficial ou código de validação digital? (Se não: "Documento sem comprovação de autenticidade judicial")
│            ├─ Dados da criança na Certidão de Nascimento batem com o formulário (Nome, Data e Sexo)?
│            ├─ O nome da criança/adolescente no Termo de Tutela é exatamente o mesmo da Certidão de Nascimento?
│            └─ O nome do colaborador consta expressamente como o(a) TUTOR(A) nomeado(a) no documento judicial?

Detalhe importante para a IA neste fluxo:
Documentos judiciais muitas vezes possuem uma linguagem complexa. É importante que o prompt da IA seja instruído a procurar especificamente pelas palavras "concedo a guarda a...", "nomeio como tutor..." ou o campo específico de "Guardião/Tutor" para garantir que o colaborador é quem detém a responsabilidade legal, e não apenas uma parte citada no processo. 



       [ 4. DECISÃO DE DEPENDENTES ]
       │
       ├─► Após o salvamento do dependente no banco de dados, o sistema pergunta:
       │      ├─ "Adicionar outro dependente" ──► Retorna ao início da inclusão.
       │      └─ "Finalizar cadastro" ──────────► Avança para a escolha de kits.        




       [ 5. ESCOLHA DOS KITS ESCOLARES ]
       │
       ├─► Sistema carrega os dependentes salvos no banco para aquele colaborador.
       ├─► Apresenta o catálogo de kits correspondente à escolaridade de cada filho (Educação Infantil, Fundamental I/II, Médio).
       └─► Registra as escolhas na tabela `escolhas_kits` no PostgreSQL/Supabase.



       [ 6. GERAÇÃO DO QR CODE ]
       │
       ├─► Sistema gera um `codigo_retirada` único (UUID) com status `PENDENTE`.
       ├─► Consolida o resumo de todos os kits e dependentes associados.
       ├─► Renderiza a imagem do QR Code na tela.
       └─► Disponibiliza o botão de download do QR Code para o colaborador apresentar no dia da entrega.