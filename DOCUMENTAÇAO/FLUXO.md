[ 1. TELA DE INICIALIZAÇÃO ]
       │
       ├─► Usuário digita o número do Crachá (suporta clique no botão ou tecla "Enter").
       └─► Sistema busca no banco de dados (Supabase) via API/Conector.
              │
              ├─► Se o crachá não existir: Retorna erro ("Crachá não encontrado").
              ├─► Se o colaborador estiver desligado/inativo: Retorna erro de elegibilidade.
              └─► Se OK: Carrega as informações e exibe a Ficha do Colaborador.

[ 2. DADOS DE CONTATO ]
       │
       ├─► O formulário de busca de crachá se oculta automaticamente (mantendo a tela limpa).
       ├─► O usuário preenche:
       │      ├─ E-mail
       │      ├─ Confirmação de E-mail (Devem ser estritamente iguais)
       │      └─ Número de Telefone (WhatsApp com validação de DDD e formato)
       └─► Sistema valida os campos. Se aprovado, os dados de contato são salvos e a tela avança.



       [ 3. ADICIONAR DEPENDENTES & ANÁLISE DE CERTIDÃO ]
       │
       ├─► O usuário preenche os dados do filho(a):
       │      ├─ Nome Completo
       │      ├─ Gênero
       │      ├─ Data de Nascimento
       │      └─ Anexa o documento (PDF ou Imagem da Certidão de Nascimento)
       │
       ├─► O sistema envia a certidão para a inteligência artificial (Gemini) analisar:
       │      │
       │      ├─► Trava 1: O documento é uma Certidão de Nascimento válida? 
       │      │     └─ (Se NÃO, exibe: "Documento adicionado nao e um certidao de nascimento")
       │      │
       │      ├─► Trava 2: O documento está legível?
       │      │     └─ (Se ESTIVER BORRADO/ILEGÍVEL, exibe: "Documento esta inlegivel , carregue outro")
       │      │
       │      ├─► Trava 3: Os dados batem com o formulário (Nome, Data e Gênero)?
       │      │     └─ (Se NÃO bater, exibe o erro correspondente informando a divergência)
       │      │
       │      └─► Trava 4: O nome do pai ou da mãe confere com o colaborador logado?
       │            ├─ Se SIM: Dependente aprovado e cadastrado diretamente no banco.
       │            └─ Se NÃO (ex: mudança de nome por casamento/divórcio): 
       │                  └─► Sistema abre a etapa de envio de documento complementar (Certidão de Casamento/Divórcio) para revisão do RH.
       │
       └─► Após o cadastro do dependente, o sistema pergunta: 
              ├─ "Adicionar outro dependente" (retorna para o passo 3)
              └─ "Finalizar cadastro" (avança para o passo 4)