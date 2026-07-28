import pandas as pd
import os
import streamlit as st  
from datetime import date, datetime, timedelta
import time
import qrcode
import re
import unicodedata
import json
from google import genai
from google.genai import types
from dotenv import load_dotenv
from io import BytesIO
import uuid
from datetime import datetime

# ==================== IMPORTS DO BANCO ====================
from database import SessionLocal, Colaborador, Dependente, EscolhaKit, Retirada
from conector_oracle import OracleConnector

load_dotenv()
client_gemini = genai.Client()  

generation_config_certidao = types.GenerateContentConfig(
    temperature=0,
    response_mime_type="application/json",
    system_instruction=(
        "Você é um assistente especializado em extração de dados. Sua tarefa é analisar o documento fornecido.\n"
        "Regra 1: Verifique se o documento é uma Certidão de Nascimento válida. Se for, classifique 'documento_valido' como true. Se for qualquer outro tipo de documento (RG, CNH, boleto) ou estiver ilegível, classifique como false.\n"
        "Regra 2: Extraia o nome completo do pai e o nome completo da mãe, exatamente como constam no documento. Se um dos nomes não existir (ex: pai ausente), retorne null.\n"
        "Regra 3: Extraia o nome completo da criança registrada na certidão.\n"
        "Regra 4: Extraia a data de nascimento da criança no formato DD/MM/AAAA.\n"
        "Regra 5: Identifique o sexo da criança conforme consta na certidão. Retorne EXATAMENTE 'Masculino' ou 'Feminino', sem abreviações.\n"
        "OBS: NAO DAR RESPOSTA EXPLICATIVA"
    ),
    response_schema={
        "type": "OBJECT",
        "properties": {
            "documento_valido": {"type": "BOOLEAN"},
            "nome_pai": {"type": "STRING", "nullable": True},
            "nome_mae": {"type": "STRING",},
            "nome_crianca": {"type": "STRING"},
            "data_nascimento_crianca": {"type": "STRING"},
            "sexo_crianca": {"type": "STRING","enum": ["Masculino","Feminino"]
}   
        },
        "required": ["documento_valido", "nome_pai", "nome_mae", "nome_crianca", "data_nascimento_crianca", "sexo_crianca"]
    }
)
#----------------------------------------------- busca documento  "casamento" ou "divorcio"
generation_config_doc_complementar = types.GenerateContentConfig(
    temperature=0,
    response_mime_type="application/json",
    system_instruction=(
        "Você é um assistente especializado em extração de dados de documentos civis brasileiros.\n"
        "Sua tarefa: analisar uma certidão de casamento ou divórcio.\n"
        "Regra 1: Classifique 'documento_valido' como true se for certidão de casamento ou divórcio. Caso contrário, false.\n"
        "Regra 2: Extraia o nome da pessoa ANTES e DEPOIS da mudança de nome.\n"
        "Se for divórcio, o nome 'antes' é o nome de casada, 'depois' é o nome retomado.\n"
        "Se for casamento, o nome 'antes' é o solteiro, 'depois' é o de casada.\n"
        "OBS: NAO DAR RESPOSTA EXPLICATIVA"
    ),
    response_schema={
        "type": "OBJECT",
        "properties": {
            "documento_valido":  {"type": "BOOLEAN"},
            "tipo_documento":    {"type": "STRING"},   
            "nome_antes":        {"type": "STRING"},
            "nome_depois":       {"type": "STRING"}
        },
        "required": ["documento_valido", "tipo_documento", "nome_antes", "nome_depois"]
    }
)






#---------------------------------------------------FUNCOES DE SISTEMA


from conector_Postgre import SupabaseConnector

def busca_colaborador(situacoes_invalidas=["Desligado", "Aposentadoria p/Invalidez"]):
    """Busca colaborador diretamente no banco de dados (Supabase)"""
    print("Buscando colaborador no banco...")

    with st.form("form_busca"):
        cracha_digitado = st.number_input("Crachá :", min_value=0, max_value=9999999999, step=1)
        buscar = st.form_submit_button("🔍 Buscar")

    if not buscar:
        return None

    supabase_connector = SupabaseConnector()
    try:
        query = f"""
        SELECT 
            cracha,
            nome,
            descricao_situacao,
            titulo_reduzido_cargo,
            data_demissao
        FROM colaboradores
        WHERE cracha = {cracha_digitado}
        """
        df = pd.read_sql(query, supabase_connector.engine)
        colaborador = df.to_dict(orient="records")[0] if not df.empty else None

        if not colaborador:
            st.error("❌ Crachá não encontrado na base de dados.")
            return None

        if colaborador["descricao_situacao"] in situacoes_invalidas:
            st.error(f"❌ Colaborador não elegível. Situação atual: {colaborador['descricao_situacao']}")
            return None

        # ==================== SALVA NO SESSION_STATE ====================
        st.session_state.colaborador = {
            "id": colaborador["cracha"],  # ← usando cracha como identificador, já que não há id
            "Crachá": colaborador["cracha"],
            "Nome": colaborador["nome"],
            "Título Reduzido (Cargo)": colaborador["titulo_reduzido_cargo"],
            "Descrição (Situação)": colaborador["descricao_situacao"]
        }

        st.divider()
        st.subheader("👤 Ficha do Colaborador")
        st.text_input("Nome Completo", value=colaborador['nome'], disabled=True)
        st.text_input("Cargo", value=colaborador['titulo_reduzido_cargo'] or "", disabled=True)
        st.text_input("Situação", value=colaborador['descricao_situacao'] or "", disabled=True)

        return st.session_state.colaborador

    finally:
        supabase_connector.fechar_conexao()

def adiciona_dados_contato():
    print("Adicionando dados de contato...")

    with st.form("form_contato"):
        st.subheader("📞 Dados de Contato")

        col_email, col_dominio = st.columns([2, 1])
        with col_email:
            nome_email = st.text_input("E-mail", placeholder="seu.nome")
            nome_email_confirmacao = st.text_input("Confirme o E-mail", placeholder="seu.nome")  # ← campo de confirmação
        with col_dominio:
            dominios = ["", "@gmail.com", "@outlook.com", "@hotmail.com", "@hcmripreto.com.br", "@yahoo.com.br", "@hospitaldebase.com.br"]
            dominio_escolhido = st.selectbox(
                "Domínio",
                dominios,
                format_func=lambda x: "Selecione..." if x == "" else x
            )
            dominio_escolhido_confirmção = st.selectbox(
                "Confirme o Domínio:",
                dominios,
                format_func=lambda x: "Selecione..." if x == "" else x
            )

        telefone = st.text_input("Número de Telefone (WhatsApp)")
        salvar = st.form_submit_button("📁 Salvar Dados de Contato")

    if not salvar:
        return None

    erros = []

    email_completo = f"{nome_email.strip()}{dominio_escolhido}"
    email_confirmacao_completo = f"{nome_email_confirmacao.strip()}{dominio_escolhido_confirmção}"
#-------------------------------------------validações dos campos email
    if not nome_email.strip():
        erros.append("❌ E-mail é obrigatório.")
    elif not dominio_escolhido:
        erros.append("❌ Selecione um domínio.")
    elif not validar_email(email_completo):
        erros.append("❌ E-mail inválido.")
    elif not nome_email_confirmacao.strip():
        erros.append("❌ Confirmação de e-mail é obrigatória.")
    elif email_completo != email_confirmacao_completo: 
        erros.append("❌ Os e-mails não coincidem.")
#-------------------------------------------validações dos campos telefone  

    if not telefone.strip():
        erros.append("❌ Telefone é obrigatório.")
    else:
        telefone_valido, mensagem_telefone = valida_telefone(telefone)
        if not telefone_valido:
            erros.append(f"❌ {mensagem_telefone}")    

    if erros:
        for x in erros:
            st.error(f"{x}")
        return None  

    st.success("✅ Dados de contato salvos com sucesso!")  
    return {
        "email": email_completo,
        "telefone": formata_telefone(telefone)
    }


def adicionar_dependentes():
    st.subheader("👶 Adicionar Dependente")
    st.write(f"Nome Responsável: {st.session_state.colaborador['Nome']}")

    # --- Inicializa estados de controle do fluxo (mantido igual) ---
    if 'aguardando_doc_complementar' not in st.session_state:
        st.session_state.aguardando_doc_complementar = False
    if 'dados_certidao_filho' not in st.session_state:
        st.session_state.dados_certidao_filho = None
    if 'dependente_temp' not in st.session_state:
        st.session_state.dependente_temp = None

    if 'escolaridade' not in st.session_state:
        st.session_state.escolaridade = ""
    if 'ano_escolar' not in st.session_state:
        st.session_state.ano_escolar = ""

    st.selectbox(
        "Escolaridade",
        ["", "Educação Infantil", "Ensino Fundamental I", "Ensino Fundamental II", "Ensino Médio"],
        format_func=lambda x: "Selecione a Escolaridade..." if x == "" else x,
        key="escolaridade",
        on_change=lambda: None
    )

    opcoes_ano = {
        "": [],
        "Educação Infantil":    ["", "Maternal I", "Maternal II", "Etapa I", "Etapa II"],
        "Ensino Fundamental I": ["", "1º Ano", "2º Ano", "3º Ano", "4º Ano", "5º Ano"],
        "Ensino Fundamental II":["", "6º Ano", "7º Ano", "8º Ano", "9º Ano"],
        "Ensino Médio":         ["", "1º Ano", "2º Ano", "3º Ano"]
    }

    if st.session_state.escolaridade:
        st.selectbox(
            "Ano Escolar 2026",
            opcoes_ano[st.session_state.escolaridade],
            format_func=lambda x: "Selecione o Ano Escolar..." if x == "" else x,
            key="ano_escolar"
        )

    # =========================================================
    # FASE 2 — Documento complementar
    # =========================================================
    if st.session_state.aguardando_doc_complementar:
        st.warning(
            "⚠️ Seu nome atual não foi encontrado na certidão. "
            "Isso pode ocorrer por mudança de nome (casamento/divórcio)."
        )
        st.divider()

        doc_complementar = st.file_uploader(
            "📄 Anexe sua Certidão de Casamento ou Divórcio para confirmar seu vínculo",
            type=["pdf", "png", "jpg", "jpeg"],
            key="doc_complementar"
        )

        col1, col2 = st.columns([1, 1])

        with col1:
            confirmar = st.button("✅ Confirmar com documento complementar", type="primary")
        with col2:
            cancelar = st.button("↩️ Cancelar e tentar outra certidão")

        if cancelar:
            st.session_state.aguardando_doc_complementar = False
            st.session_state.dados_certidao_filho = None
            st.session_state.dependente_temp = None
            st.rerun()

        if confirmar:
            if not doc_complementar:
                st.error("❌ Anexe o documento complementar antes de confirmar.")
                return None

            dados_complementar, erro = analisa_certidao_complementar(doc_complementar)

            if erro:
                st.error(erro)
                return None

            nome_na_certidao_filho = (
                st.session_state.dados_certidao_filho.get("nome_mae") or
                st.session_state.dados_certidao_filho.get("nome_pai") or ""
            )

            ok, mensagem, revisao_rh = valida_com_doc_complementar(
                dados_complementar, 
                st.session_state.colaborador['Nome'], 
                nome_na_certidao_filho
            )

            if ok:
                st.success(mensagem)
                if revisao_rh:
                    st.info("ℹ️ Este cadastro será encaminhado para revisão do RH.")

                # ==================== MUDANÇA: SALVAR NO BANCO ====================
                resultado = st.session_state.dependente_temp
                resultado["revisao_rh"] = revisao_rh
                resultado["Data_Cadastro"] = datetime.now().strftime("%d/%m/%Y %H:%M")

                db = SessionLocal()          # Abre conexão com o banco
                try:
                    novo_dependente = Dependente(
                        id_colaborador=st.session_state.colaborador.get("id"),   # ID real do colaborador no banco
                        nome_filho=resultado["Nome_filho"],
                        data_nascimento=datetime.strptime(resultado["Data_nascimento"], "%d/%m/%Y").date(),
                        genero=resultado.get("Gênero"),
                        escolaridade=resultado["Escolaridade"],
                        ano_escola=resultado["Ano_escolar"],
                        revisao_rh="Sim" if resultado["revisao_rh"] else None
                    )
                    db.add(novo_dependente)
                    db.commit()
                    db.refresh(novo_dependente)

                    st.success(f"✅ Dependente cadastrado com sucesso! ID: {novo_dependente.id_dependente}")
                finally:
                    db.close()               # Sempre fecha a conexão

                # Limpa os estados
                st.session_state.aguardando_doc_complementar = False
                st.session_state.dados_certidao_filho = None
                st.session_state.dependente_temp = None
                return resultado
            else:
                st.error(mensagem)
                return None

        return None

    # =========================================================
    # FASE 1 — Formulário principal
    # =========================================================
    with st.form("form_dependente"):
        nome_filho    = st.text_input("Nome Completo da Criança")
        genero        = st.selectbox("Gênero:", ["", "Masculino", "Feminino"],
                                     format_func=lambda x: "Selecione o Gênero..." if x == "" else x)
        data_maxima   = date.today() - timedelta(days=730)
        data_nascimento = st.date_input("Data de Nascimento",
                                        min_value=date(2000, 1, 1), max_value=data_maxima)
        certidao      = st.file_uploader(
            "Anexar Certidão de Nascimento 📄",
            type=["pdf", "png", "jpg", "jpeg"],
            help="Pode enviar foto, imagem escaneada ou PDF"
        )
        salvar = st.form_submit_button("📁 Adicionar Dependente")

    if not salvar:
        return None

    # Validações dos campos (mantidas iguais)
    erros = []
    if not nome_filho.strip():
        erros.append("❌ Nome da criança é obrigatório.")
    elif len(nome_filho.strip()) < 3:
        erros.append("❌ Nome muito curto.")
    elif re.search(r'[^a-zA-ZÀ-ÿ\s]', nome_filho):
        erros.append("❌ Nome não pode conter números ou caracteres especiais.")

    if not genero:
        erros.append("❌ Gênero é obrigatório.")
    if not st.session_state.escolaridade:
        erros.append("❌ Escolaridade é obrigatória.")
    if not st.session_state.ano_escolar:
        erros.append("❌ Ano Escolar é obrigatório.")
    if not certidao:
        erros.append("❌ Certidão de nascimento é obrigatória.")

    if erros:
        for x in erros:
            st.error(x)
        return None

    # ===================== CHECAGEM DE DUPLICIDADE NO BANCO =====================
    nome_padronizado = padroniza_texto(nome_filho).strip()
    data_nascimento.strftime("%d/%m/%Y")

    db = SessionLocal()
    try:
        # Substitui a busca no DataFrame por busca no banco
        duplicado = db.query(Dependente).filter(
            Dependente.nome_filho.ilike(f"%{nome_padronizado}%"),
            Dependente.data_nascimento == data_nascimento
        ).first()

        if duplicado:
            st.error("❌ Esta criança já possui um kit cadastrado.")
            return None

        # Análise da certidão com Gemini (mantida igual)
        with st.spinner("🔍 Analisando certidão de nascimento, aguarde..."):
            dados_certidao, erro_api = analisa_certidao(certidao)
       
        if erro_api:
            st.error(erro_api)
            return None

        # Validações (mantidas)
        dados_ok, msg_dados = valida_dados_crianca_certidao(dados_certidao, nome_filho, data_nascimento, genero)
        if not dados_ok:
            st.error(msg_dados)
            return None

        valido, mensagem = valida_nome_pais_certidao(
            dados_certidao, st.session_state.colaborador['Nome']
        )

        if valido:
            st.success(mensagem)

            # ==================== SALVAMENTO NO BANCO ====================
            novo_dependente_db = Dependente(
                id_colaborador = st.session_state.colaborador.get("id"),   # ID do colaborador no banco
                nome_filho = padroniza_texto(dados_certidao.get("nome_crianca") or nome_filho),
                data_nascimento = data_nascimento,
                genero = genero,
                escolaridade = st.session_state.escolaridade,
                ano_escola = st.session_state.ano_escolar
            )

            db.add(novo_dependente_db)
            db.commit()
            db.refresh(novo_dependente_db)

            # Retorna dicionário compatível com o resto do seu código
            return {
                "ID_Dependente": novo_dependente_db.id_dependente,
                "ID_Colaborador": st.session_state.colaborador['Crachá'],
                "Nome_filho": novo_dependente_db.nome_filho,
                "Gênero": novo_dependente_db.genero,
                "Data_nascimento": novo_dependente_db.data_nascimento.strftime("%d/%m/%Y"),
                "Escolaridade": novo_dependente_db.escolaridade,
                "Ano_escolar": novo_dependente_db.ano_escola,
                "Data_Cadastro": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "revisao_rh": False
            }

        else:
            # Fase 2 - documento complementar
            st.session_state.aguardando_doc_complementar = True
            st.session_state.dados_certidao_filho = dados_certidao
            st.session_state.dependente_temp = {
                "ID_Dependente": None,   # será gerado pelo banco
                "ID_Colaborador": st.session_state.colaborador['Crachá'],
                "Nome_filho": padroniza_texto(dados_certidao.get("nome_crianca") or ""),
                "Gênero": genero,
                "Data_nascimento": data_nascimento.strftime("%d/%m/%Y"),
                "Escolaridade": st.session_state.escolaridade,
                "Ano_escolar": st.session_state.ano_escolar,
            }
            st.rerun()

    finally:
        db.close()



def ficha_colaborador():
    print("Exibindo ficha do colaborador...")
    # Código para exibir a ficha do colaborador
    # Exemplo: renderização de interface, exibição de dados, etc.
    pass

#---------------------------------------------------FUNCOES DE VALIDACAO input

def validar_email(email):
    """
    Valida se o formato do e-mail é válido.
    Aceita letras, números, pontos, traços e underscores.
    """
    if not email:
        return False
        
    # Padrão Regex para e-mails válidos (ex: nome.sobrenome@dominio.com.br)
    padrao_email = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    
    # re.fullmatch garante que a string inteira obedeça à regra, sem sobras
    return bool(re.fullmatch(padrao_email, email.strip()))
def padroniza_texto(texto):
    # Remove espaços extras, converte para maiúsculo e remove acentos
    texto = texto.strip().upper()
    texto = unicodedata.normalize('NFKD', texto)
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r'[^A-Z\s]', '', texto)  # Remove alfanuméricos e caracteres especiais
    texto = re.sub(r'\s+', ' ', texto)       # Remove espaços duplos
    return texto
def valida_telefone(telefone):
    """
    Valida telefone brasileiro (celular ou fixo).
    Aceita formatos: (17) 99706-0067, 17997060067, 17 99706 0067, etc.
    """
    # Remove tudo que não é número
    numero = re.sub(r'\D', '', telefone)

    # Rejeita se tiver letras misturadas no original (alfanumérico)
    if re.search(r'[a-zA-Z]', telefone):
        return False, "Telefone não pode conter letras."

    # Valida quantidade de dígitos celular (11)
    if len(numero) != 11:
        return False, "Telefone deve ter 11 dígitos (com DDD)."

    # Valida DDD — lista de DDDs válidos no Brasil
    ddds_validos = {
        11,12,13,14,15,16,17,18,19,21,22,24,27,28,
        31,32,33,34,35,37,38,41,42,43,44,45,46,47,48,49,
        51,53,54,55,61,62,63,64,65,66,67,68,69,
        71,73,74,75,77,79,81,82,83,84,85,86,87,88,89,
        91,92,93,94,95,96,97,98,99
    }
    ddd = int(numero[:2])
    if ddd not in ddds_validos:
        return False, "DDD inválido."

    # Celular (11 dígitos) precisa começar com 9 após o DDD
    if len(numero) == 11 and numero[2] != '9':
        return False, "Celular deve começar com 9 após o DDD."

    return True, "Telefone válido."
def formata_telefone(telefone):
    numero = re.sub(r'\D', '', telefone)
    if len(numero) == 11:
        return f"({numero[:2]}) {numero[2:7]}-{numero[7:]}"
    return numero



#---------------------------------------------------FUNCOES DE validcao de documento
def analisa_certidao(arquivo, tentativas=3):
    """
    Versão corrigida: trata timeout, 503 e retorna dict (não string).
    """
    try:
        arquivo.seek(0)
        arquivo_bytes = arquivo.read()
    except Exception:
        return None, "❌ Erro ao ler o arquivo. Tente fazer o upload novamente."

    mime_type = arquivo.type
    ERROS_COM_RETRY = ("503", "timeout", "timed out", "429")  # ← amplia os retries

    for tentativa in range(1, tentativas + 1):
        try:
            response = client_gemini.models.generate_content(
                model='gemini-3.1-flash-lite',
                contents=[
                    types.Part.from_bytes(data=arquivo_bytes, mime_type=mime_type),
                    "Analise o documento e retorne os dados no formato estruturado."
                ],
                config=generation_config_certidao,
            )

            # Sanitiza antes de parsear (remove possível lixo extra)
            texto_limpo = response.text.strip()
            dados = json.loads(texto_limpo)      # ← parse único aqui
            return dados, None                   # ← retorna dict, não string

        except json.JSONDecodeError:
            return None, "❌ Resposta da IA em formato inesperado. Tente novamente."

        except Exception as e:
            print(f"🔍 ERRO REAL CAPTURADO: {repr(e)}")  
            erro_str = str(e).lower()
            tem_retry = any(cod in erro_str for cod in ERROS_COM_RETRY)
            if tem_retry and tentativa < tentativas:
                time.sleep(2 * tentativa)
                continue
            return None, "❌ Serviço de validação indisponível. Tente em alguns instantes."

    return None, "❌ Não foi possível validar após várias tentativas."
def valida_nome_pais_certidao(dados_certidao: dict, nome_colaborador: str):

    """
    Versão corrigida: recebe dict já parseado, não string.
    """
    nome_pai = dados_certidao.get("nome_pai") or ""
    nome_mae = dados_certidao.get("nome_mae") or ""

    if not nome_pai and not nome_mae:
        return False, "❌ Não foi possível identificar os nomes dos pais na certidão."

    nome_db   = padroniza_texto(nome_colaborador)
    pai_cert  = padroniza_texto(nome_pai)
    mae_cert  = padroniza_texto(nome_mae)

    if nome_db == pai_cert:
        return True, f"✅ Nome confere com o pai: {nome_pai}"
    if nome_db == mae_cert:
        return True, f"✅ Nome confere com a mãe: {nome_mae}"

    return False, None   # ← None sinaliza "não bateu, mas não é erro técnico"
def analisa_certidao_complementar(arquivo, tentativas=3):
    """
    Envia a certidão de casamento ou divórcio ao Gemini.
    Retorna (dict, None) se sucesso ou (None, "mensagem de erro") se falhar.
    """
    try:
        arquivo.seek(0)
        arquivo_bytes = arquivo.read()
    except Exception:
        return None, "❌ Erro ao ler o arquivo. Tente fazer o upload novamente."

    mime_type = arquivo.type
    ERROS_COM_RETRY = ("503", "timeout", "timed out", "429")

    for tentativa in range(1, tentativas + 1):
        try:
            response = client_gemini.models.generate_content(
                model='gemini-3.1-flash-lite',
                contents=[
                    types.Part.from_bytes(data=arquivo_bytes, mime_type=mime_type),
                    "Analise o documento e retorne os dados no formato estruturado."
                ],
                config=generation_config_doc_complementar,   # ← config específica para casamento/divórcio
            )

            texto_limpo = response.text.strip()
            dados = json.loads(texto_limpo)
            return dados, None

        except json.JSONDecodeError:
            return None, "❌ Resposta da IA em formato inesperado. Tente novamente."

        except Exception as e:
            erro_str = str(e).lower()
            tem_retry = any(cod in erro_str for cod in ERROS_COM_RETRY)
            if tem_retry and tentativa < tentativas:
                time.sleep(2 * tentativa)   # espera progressiva: 2s, 4s
                continue
            return None, "❌ Serviço de validação indisponível. Tente em alguns instantes."

    return None, "❌ Não foi possível validar após várias tentativas."

def valida_com_doc_complementar(dados: dict, nome_banco: str, nome_certidao_filho: str):
    """
    Valida se o colaborador é o mesmo por meio de certidão de casamento/divórcio.
    Recebe os dados já extraídos pelo Gemini.
    Retorna (True/False, mensagem, flag_revisao_rh)
    """
    if not dados.get("documento_valido"):
        return False, "❌ Documento não reconhecido. Envie uma certidão de casamento ou divórcio.", False

    nome_antes  = padroniza_texto(dados.get("nome_antes") or "")
    nome_depois = padroniza_texto(dados.get("nome_depois") or "")
    nome_db     = padroniza_texto(nome_banco)
    nome_cert   = padroniza_texto(nome_certidao_filho)

    banco_no_doc = nome_db in (nome_antes, nome_depois)
    cert_no_doc = nome_cert in (nome_antes, nome_depois)

    if banco_no_doc and cert_no_doc:
        return True, "✅ Vínculo confirmado via documento complementar. Cadastro aprovado com revisão do RH.", True

    return False, (
        "❌ Não foi possível confirmar o vínculo entre os documentos. "
        "Entre em contato com o RH para regularizar manualmente."
    ), False
   
def crianca_ja_cadastrada(nome_crianca_padronizado, data_nascimento_str, df_dependentes):
    """
    Verifica se essa criança (nome + data de nascimento) já está cadastrada
    por QUALQUER colaborador — inclusive o mesmo. 1 criança = 1 kit, sempre.
    Retorna (True/False, mensagem).
    """
    if df_dependentes.empty:
        return False, None

    encontrados = df_dependentes[
        (df_dependentes["Nome_filho"] == nome_crianca_padronizado) &
        (df_dependentes["Data_nascimento"] == data_nascimento_str)           ##############################BUSCA NO BANCO DE DADOS #########################
    ]

    if encontrados.empty:
        return False, None

    return True, "❌ Esta criança já possui um kit cadastrado. Cada criança pode receber apenas 1 kit. Entre em contato com o RH em caso de divergência."   
def valida_dados_crianca_certidao(dados_certidao: dict, nome_informado: str, data_informada: date,genero_informado: str):
    """
    Compara nome e data de nascimento da criança, informados pelo colaborador
    no formulário, com os dados extraídos da certidão pelo Gemini.
    Retorna (True/False, mensagem).
    """
#---------------------------------------------------------------------------------------------------------nome_crianca
    nome_cert = padroniza_texto(dados_certidao.get("nome_crianca") or "")  ##############################BUSCA NO BANCO DE DADOS #########################
    nome_form = padroniza_texto(nome_informado)

    if not nome_cert:
        return False, "❌ Não foi possível identificar o nome da criança na certidão."

    if nome_cert != nome_form:
        return False, f"❌ Nome informado não confere com a certidão. Certidão mostra: {dados_certidao.get('nome_crianca')}"
#---------------------------------------------------------------------------------------------------------data_nascimento_crianca
    data_cert_str = (dados_certidao.get("data_nascimento_crianca") or "").strip()       ##############################BUSCA NO BANCO DE DADOS #########################

    if not data_cert_str:
        return False, "❌ Não foi possível identificar a data de nascimento na certidão."

    try:
        data_cert = datetime.strptime(data_cert_str, "%d/%m/%Y").date()
    except ValueError:
        return False, "❌ Não foi possível interpretar a data de nascimento extraída da certidão."

    if data_cert != data_informada:
        return False, f"❌ Data de nascimento informada ({data_informada.strftime('%d/%m/%Y')}) não confere com a certidão ({data_cert_str})."

    # ------------------------------------------------------------------------------------------------------------- sexo 
    sexo_cert = padroniza_texto(dados_certidao.get("sexo_crianca") or "")
    sexo_form = padroniza_texto(genero_informado)
    if sexo_cert != sexo_form:
        return (
        False,
        f"❌ O sexo informado ({genero_informado}) "
        f"não corresponde ao sexo encontrado na certidão "
        f"({dados_certidao.get('sexo_crianca')}).")

    return True, "✅ Nome, data de nascimento e sexo conferem com a certidão."


#---------------------------------------------------------------------------------------------------Funcoes de catalogo de kits
def catalogo_kits_por_escolaridade():
    return {
        "Educação Infantil": [
            "Kit Educação Infantil A",
            "Kit Educação Infantil B",
            "Kit Educação Infantil C"
        ],
        "Ensino Fundamental I": [
            "Kit Fundamental I A",
            "Kit Fundamental I B",
            "Kit Fundamental I C"
        ],
        "Ensino Fundamental II": [
            "Kit Fundamental II A",
            "Kit Fundamental II B",
            "Kit Fundamental II C"
        ],
        "Ensino Médio": [
            "Kit Ensino Médio A",
            "Kit Ensino Médio B",
            "Kit Ensino Médio C"
        ]
    }

# ===================== FUNÇÕES DE QRCODE =====================
def monta_conteudo_qrcode():
    """Gera o conteúdo que vai dentro do QR Code"""
    if "codigo_retirada" not in st.session_state:
        criar_registro_retirada_qrcode()

    codigo_retirada = st.session_state.codigo_retirada
    return f"RETIRADA_KIT:{codigo_retirada}"
def gerar_qrcode(conteudo_qrcode):
    """Gera a imagem do QR Code"""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4
    )

    qr.add_data(conteudo_qrcode)
    qr.make(fit=True)

    imagem_qrcode = qr.make_image(fill_color="black", back_color="white")

    buffer = BytesIO()
    imagem_qrcode.save(buffer, format="PNG")
    buffer.seek(0)

    return buffer
#---------------------------------------------------------------------------------------------------QRCODE 
def monta_resumo_kits(escolhas_kits):
    linhas_resumo = []
    for escolha in escolhas_kits:
        linha = f"{escolha.get('Nome_filho')} - {escolha.get('Escolaridade')} - {escolha.get('Kit_Escolhido')}"
        linhas_resumo.append(linha)
    return " | ".join(linhas_resumo)
def criar_registro_retirada_qrcode():
    colaborador = st.session_state.colaborador
    contato = st.session_state.contato
    escolhas_kits = st.session_state.escolhas_kits

    db = SessionLocal()
    try:
        codigo_retirada = str(uuid.uuid4())
        resumo_kits = monta_resumo_kits(escolhas_kits)

        nova_retirada = Retirada(
            codigo_retirada=codigo_retirada,
            id_colaborador=colaborador["id"],
            email=contato["email"],
            telefone=contato["telefone"],
            qtd_kits=len(escolhas_kits),
            resumo_kits=resumo_kits,
            status="PENDENTE"
        )

        db.add(nova_retirada)
        db.commit()
        db.refresh(nova_retirada)

        st.session_state.codigo_retirada = codigo_retirada
        st.session_state.retirada_qrcode = {
            "Codigo_Retirada": codigo_retirada,
            "Nome_Colaborador": colaborador["Nome"],
            "ID_Colaborador": colaborador["Crachá"],
            "Email": contato["email"],
            "Telefone": contato["telefone"],
            "Qtd_Kits": len(escolhas_kits),
            "Resumo_Kits": resumo_kits,
            "Status": "PENDENTE"
        }

        return nova_retirada

    finally:
        db.close()
def escolher_kits_colaborador():
    st.divider()
    st.subheader("🎒 Escolha dos Kits Escolares")

    cracha_colaborador = st.session_state.colaborador["Crachá"]
    id_colaborador = st.session_state.colaborador["id"]   # ID real do banco

    db = SessionLocal()
    try:
        # Busca dependentes deste colaborador diretamente do banco
        dependentes_colaborador = db.query(Dependente).filter(
            Dependente.id_colaborador == id_colaborador
        ).all()

        if not dependentes_colaborador:
            st.warning("Nenhum dependente encontrado para este colaborador.")
            return None

        catalogo = catalogo_kits_por_escolaridade()
        escolhas = []

        st.write(f"Você possui {len(dependentes_colaborador)} crédito(s) de kit.")

        with st.form("form_escolha_kits"):
            for dependente in dependentes_colaborador:
                nome_filho = dependente.nome_filho
                escolaridade = dependente.escolaridade
                ano_escolar = dependente.ano_escola
                genero = dependente.genero
                id_dependente = dependente.id_dependente

                st.markdown(f"### {nome_filho}")
                st.write(f"Escolaridade: {escolaridade}")
                st.write(f"Ano escolar: {ano_escolar}")

                opcoes_kits = catalogo.get(escolaridade, [])

                if not opcoes_kits:
                    st.error(f"Não existem kits cadastrados para a escolaridade: {escolaridade}")
                    continue

                kit_escolhido = st.selectbox(
                    f"Escolha o kit de {nome_filho}",
                    [""] + opcoes_kits,
                    format_func=lambda x: "Selecione um kit..." if x == "" else x,
                    key=f"kit_dependente_{id_dependente}"
                )

                escolhas.append({
                    "ID_Dependente": id_dependente,
                    "ID_Colaborador": id_colaborador,
                    "Nome_filho": nome_filho,
                    "Gênero": genero,
                    "Escolaridade": escolaridade,
                    "Ano_escolar": ano_escolar,
                    "Kit_Escolhido": kit_escolhido
                })

            salvar_escolhas = st.form_submit_button("✅ Confirmar escolha dos kits")

        if not salvar_escolhas:
            return None

        # Validação de seleção
        erros = [f"❌ Selecione um kit para {e['Nome_filho']}." for e in escolhas if not e["Kit_Escolhido"]]
        if erros:
            for erro in erros:
                st.error(erro)
            return None

        # ==================== SALVAR ESCOLHAS NO BANCO ====================
        novas_escolhas = []
        for escolha in escolhas:
            nova_escolha = EscolhaKit(
                id_colaborador=escolha["ID_Colaborador"],
                id_dependente=escolha["ID_Dependente"],
                kit_escolhido=escolha["Kit_Escolhido"]
            )
            db.add(nova_escolha)
            db.commit()
            db.refresh(nova_escolha)

            novas_escolhas.append({
                "ID_Escolha": nova_escolha.id_escolha,
                "ID_Dependente": nova_escolha.id_dependente,
                "Kit_Escolhido": nova_escolha.kit_escolhido,
                "Nome_filho": escolha["Nome_filho"],
                "Escolaridade": escolha["Escolaridade"],
                "Ano_escolar": escolha["Ano_escolar"]
            })

        st.session_state.escolhas_kits = novas_escolhas
        st.success("✅ Kits escolhidos com sucesso!")

        return novas_escolhas

    finally:
        db.close()
def exibir_qrcode_final():
    st.divider()
    st.subheader("🎟️ QR Code para Retirada")

    if "retirada_qrcode" not in st.session_state:
        criar_registro_retirada_qrcode()

    retirada = st.session_state.retirada_qrcode

    st.write(f"Colaborador: {retirada['Nome_Colaborador']}")
    st.write(f"Crachá: {retirada['ID_Colaborador']}")
    st.write(f"Quantidade de kits: {retirada['Qtd_Kits']}")
    st.write(f"Status: {retirada['Status']}")

    st.info(retirada["Resumo_Kits"])

    conteudo_qrcode = monta_conteudo_qrcode()
    imagem_qrcode = gerar_qrcode(conteudo_qrcode)

    st.image(
        imagem_qrcode,
        caption="Apresente este QR Code para retirada do kit.",
        width=300
    )

    st.download_button(
        label="⬇️ Baixar QR Code",
        data=imagem_qrcode,
        file_name=f"qrcode_retirada_{retirada['Codigo_Retirada']}.png",
        mime="image/png"
    )

    return imagem_qrcode

#------------------------------------------------------------PAINEL DE CONTROLE------------------------------------------------------------------------
def interface():
    st.set_page_config(page_title='Funfarme - Kit Escolar', page_icon='🎒')
    st.title('🏥Funfarme - Kit Escolar')
    st.write('Informe seu crachá e clique em Buscar Colaborador.')

    # --------------------------------------------------------------- Inicializa todos os estados necessários ---
    if 'colaborador' not in st.session_state:
        st.session_state.colaborador = None
    if 'contato' not in st.session_state:
        st.session_state.contato = None
    if 'lista_dependentes' not in st.session_state:
        st.session_state.lista_dependentes = []
    if 'aguardando_decisao' not in st.session_state:
        st.session_state.aguardando_decisao = False
    if 'cadastro_finalizado' not in st.session_state:
        st.session_state.cadastro_finalizado = False
    if 'escolhendo_kits' not in st.session_state:
        st.session_state.escolhendo_kits = False
    if 'escolhas_kits' not in st.session_state:
        st.session_state.escolhas_kits = []    

    # ===================== BUSCA DO COLABORADOR =====================
    colaborador = busca_colaborador()   # ← sem passar df (agora usa banco)

    if colaborador is not None:
        st.session_state.colaborador = colaborador

    if st.session_state.colaborador is not None:

        if st.session_state.contato is None:
            contato = adiciona_dados_contato()

            if contato is not None:
                st.session_state.contato = contato
                st.rerun()
        else:
            st.success("✅ Dados de contato salvos.")

        if st.session_state.contato is not None:

            # ✅ Cadastro já finalizado
            if st.session_state.cadastro_finalizado:
                st.divider()
                st.success("✅ Cadastro finalizado com sucesso! Obrigado.")

                if st.session_state.escolhas_kits:
                    exibir_qrcode_final()

                st.balloons()
                return

            # Escolha dos kits
            if st.session_state.escolhendo_kits:
                escolhas_kits = escolher_kits_colaborador()

                if escolhas_kits is not None:
                    st.session_state.escolhas_kits = escolhas_kits
                    st.session_state.escolhendo_kits = False
                    st.session_state.cadastro_finalizado = True           
                    st.rerun()
                return

            # Aguardando decisão após adicionar dependente
            if st.session_state.aguardando_decisao:
                st.divider()
                st.subheader("👶 Dependente adicionado com sucesso!")

                for i, dep in enumerate(st.session_state.lista_dependentes, start=1):
                    st.success(f"✅ {i}º dependente: {dep['Nome_filho']}")

                col1, col2 = st.columns([1, 1])
                with col1:
                    if st.button("➕ Adicionar outro dependente", type="primary"):
                        st.session_state.aguardando_decisao = False
                        st.session_state.escolaridade = ""
                        st.session_state.ano_escolar = ""
                        st.session_state.aguardando_doc_complementar = False
                        st.session_state.dados_certidao_filho = None
                        st.session_state.dependente_temp = None
                        st.rerun()

                with col2:
                    if st.button("✅ Finalizar cadastro"):
                        st.session_state.aguardando_decisao = False
                        st.session_state.escolhendo_kits = True
                        st.rerun()
                return

            # Fluxo normal — adicionar dependente
            dependente = adicionar_dependentes()

            if dependente is not None:
                st.session_state.lista_dependentes.append(dependente)
                st.session_state.aguardando_decisao = True
                st.rerun()



interface()