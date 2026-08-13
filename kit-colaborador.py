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
import time 
# ==================== IMPORTS DO BANCO ====================
from database import SessionLocal, Colaborador, Dependente, EscolhaKit, Retirada
from conector_oracle import OracleConnector
from conector_Postgre import SupabaseConnector

   
load_dotenv()
client_gemini = genai.Client()  

# CONFIGURAÇÃO DE IA: A1  Certidão de Nascimento - Filho(a) Biológico(a)

generation_config_certidao = types.GenerateContentConfig(
    temperature=0,
    response_mime_type="application/json",
    system_instruction=(
        "Você é um assistente especializado em extração de dados. Sua tarefa é analisar o documento fornecido.\n"
        "Regra 1: Verifique se o documento é uma Certidão de Nascimento válida. Se for, classifique 'documento_valido' como true. Se for qualquer outro tipo de documento (RG, CNH, boleto) ou estiver ilegível, classifique como false.\n"
        "Regra 2: Verifique se o documento está totalmente legível. Se estiver borrado, muito escuro, cortado ou ilegível a ponto de não conseguir ler os dados com segurança, classifique 'legivel' como false. Caso contrário, true.\n"
        "Regra 3: Extraia o nome completo do pai e o nome completo da mãe, exatamente como constam no documento. Se um dos nomes não existir (ex: pai ausente), retorne null.\n"
        "Regra 4: Extraia o nome completo da criança registrada na certidão.\n"
        "Regra 5: Extraia a data de nascimento da criança no formato DD/MM/AAAA.\n"
        "Regra 6: Identifique o sexo da criança conforme consta na certidão. Retorne EXATAMENTE 'Masculino' ou 'Feminino', sem abreviações.\n"
        "OBS: NAO DAR RESPOSTA EXPLICATIVA"
    ),
    response_schema={
        "type": "OBJECT",
        "properties": {
            "documento_valido": {"type": "BOOLEAN"},
            "legivel": {"type": "BOOLEAN"},
            "nome_pai": {"type": "STRING", "nullable": True},
            "nome_mae": {"type": "STRING"},
            "nome_crianca": {"type": "STRING"},
            "data_nascimento_crianca": {"type": "STRING"},
            "sexo_crianca": {"type": "STRING", "enum": ["Masculino", "Feminino"]}
        },
        "required": ["documento_valido", "legivel", "nome_pai", "nome_mae", "nome_crianca", "data_nascimento_crianca", "sexo_crianca"]
    }
)
#----------------------------------------------- busca documento  "casamento" ou "divorcio"

# ---------------------------------------------------------------
# CONFIGURAÇÃO DE IA: A2 (CERTIDÃO COM AVERBAÇÃO DE ADOÇÃO)
# ---------------------------------------------------------------
generation_config_adocao_averbacao = types.GenerateContentConfig(
    temperature=0,
    response_mime_type="application/json",
    system_instruction=(
        "Você é um assistente rigoroso de auditoria de documentos civis (Certidão de Nascimento com averbação).\n"
        "Regra 1: Verifique se o documento é uma Certidão de Nascimento válida. Classifique 'documento_valido' como true ou false.\n"
        "Regra 2: Verifique se o documento está totalmente legível. Classifique 'legivel' como true ou false.\n"
        "Regra 3: Verifique se existe explicitamente uma averbação, anotação, carimbo ou texto oficial informando a ADOÇÃO no documento. Classifique 'tem_averbacao_adocao' como true ou false.\n"
        "Regra 4: Extraia o nome completo da criança registrada ('nome_crianca').\n"
        "Regra 5: Extraia a data de nascimento da criança no formato DD/MM/AAAA ('data_nascimento_crianca').\n"
        "Regra 6: Extraia o sexo da criança ('sexo_crianca': 'Masculino' ou 'Feminino').\n"
        "Regra 7: Extraia a lista de nomes dos pais atuais (constantes na certidão ou na averbação de adoção) em uma lista de strings chamada 'nomes_pais_responsaveis'.\n"
        "OBS: NÃO DAR RESPOSTA EXPLICATIVA"
    ),
    response_schema={
        "type": "OBJECT",
        "properties": {
            "documento_valido": {"type": "BOOLEAN"},
            "legivel": {"type": "BOOLEAN"},
            "tem_averbacao_adocao": {"type": "BOOLEAN"},
            "nome_crianca": {"type": "STRING"},
            "data_nascimento_crianca": {"type": "STRING"},
            "sexo_crianca": {"type": "STRING", "enum": ["Masculino", "Feminino"]},
            "nomes_pais_responsaveis": {
                "type": "ARRAY",
                "items": {"type": "STRING"}
            }
        },
        "required": [
            "documento_valido", "legivel", "tem_averbacao_adocao", 
            "nome_crianca", "data_nascimento_crianca", "sexo_crianca", "nomes_pais_responsaveis"
        ]
    }
)

# ---------------------------------------------------------------
# CONFIGURAÇÃO DE IA: A3 (GUARDA JUDICIAL PARA FINS DE ADOÇÃO)
# ---------------------------------------------------------------
generation_config_guarda_adocao = types.GenerateContentConfig(
    temperature=0,
    response_mime_type="application/json",
    system_instruction=(
        "Você é um auditor jurídico rigoroso de documentos judiciais (Termo de Guarda, Sentença ou Decisão Judicial para fins de adoção).\n"
        "Regra 1: Verifique se o documento é de origem judicial válida (Termo de Guarda, Sentença, Decisão). Classifique 'documento_judicial_valido' como true ou false.\n"
        "Regra 2: Verifique se o documento está legível e possui elementos de autenticidade (assinatura do juiz, carimbo oficial ou código de validação digital). Classifique 'legivel_e_autentico' como true ou false.\n"
        "Regra 3: Verifique se o texto cita explicitamente que a guarda foi concedida para **Fins de Adoção** (ou estágio de convivência com finalidade adotiva). Classifique 'guarda_para_fins_de_adocao' como true ou false.\n"
        "Regra 4: Extraia o nome completo da criança ou adolescente ('nome_crianca').\n"
        "Regra 5: Extraia a data de nascimento da criança no formato DD/MM/AAAA, se houver ('data_nascimento_crianca'). Se não constar, retorne string vazia.\n"
        "Regra 6: Extraia o nome completo do guardião/responsável legal nomeado no documento ('nome_guardiao').\n"
        "OBS: NÃO DAR RESPOSTA EXPLICATIVA"
    ),
    response_schema={
        "type": "OBJECT",
        "properties": {
            "documento_judicial_valido": {"type": "BOOLEAN"},
            "legivel_e_autentico": {"type": "BOOLEAN"},
            "guarda_para_fins_de_adocao": {"type": "BOOLEAN"},
            "nome_crianca": {"type": "STRING"},
            "data_nascimento_crianca": {"type": "STRING"},
            "nome_guardiao": {"type": "STRING"}
        },
        "required": [
            "documento_judicial_valido", "legivel_e_autentico", 
            "guarda_para_fins_de_adocao", "nome_crianca", "data_nascimento_crianca", "nome_guardiao"
        ]
    }
)



# CONFIGURAÇÃO DE IA: B1 Declaração de União Estável


#--------------------------------------------------------------- busca documento  "uniao_estavel"
generation_config_uniao_estavel = types.GenerateContentConfig(
    temperature=0,
    response_mime_type="application/json",
    system_instruction=(
        "Você é um assistente rigoroso de auditoria de documentos civis (Declaração de União Estável).\n"
        "Regra 1: Verifique se o documento é uma Declaração ou Escritura Pública de União Estável válida. Classifique 'documento_valido' como true ou false.\n"
        "Regra 2: Verifique se o documento possui carimbo, selo digital, etiqueta ou menção explícita de 'reconhecimento de firma' em cartório. Se não houver, classifique 'firma_reconhecida' como false.\n"
        "Regra 3: Se houver reconhecimento de firma, verifique obrigatoriamente se o cartório emissor ou o selo pertence à cidade de 'São José do Rio Preto' ou 'Rio Preto'. Classifique 'cartorio_rio_preto' como true ou false.\n"
        "Regra 4 (EXTREMA IMPORTÂNCIA): Extraia **APENAS o nome completo** dos dois conviventes/companheiros nos campos 'nome_companheiro_1' e 'nome_companheiro_2'. **NÃO** inclua números, RGs, CPFs, endereços ou termos como 'portador', 'portadora'. Retorne estritamente somente o nome civil das pessoas.\n"
        "OBS: NÃO DAR RESPOSTA EXPLICATIVA"
    ),
    response_schema={
        "type": "OBJECT",
        "properties": {
            "documento_valido": {"type": "BOOLEAN"},
            "firma_reconhecida": {"type": "BOOLEAN"},
            "cartorio_rio_preto": {"type": "BOOLEAN"},
            "nome_companheiro_1": {"type": "STRING"},
            "nome_companheiro_2": {"type": "STRING"}
        },
        "required": ["documento_valido", "firma_reconhecida", "cartorio_rio_preto", "nome_companheiro_1", "nome_companheiro_2"]
    }
)


# CONFIGURAÇÃO DE IA: B2: Certidão de Casamento + Certidão de Nascimento


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

# ---------------------------------------------------------------
# CONFIGURAÇÃO DE IA: C1 (TERMO/CERTIDÃO DE GUARDA JUDICIAL)
# ---------------------------------------------------------------
generation_config_guarda_judicial = types.GenerateContentConfig(
    temperature=0,
    response_mime_type="application/json",
    system_instruction=(
        "Você é um auditor jurídico rigoroso de Termos ou Certidões de Guarda Judicial.\n"
        "Regra 1: Verifique se o documento é um Termo ou Certidão de Guarda válido. Classifique 'documento_valido' como true ou false.\n"
        "Regra 2: Verifique se o documento está totalmente legível. Classifique 'legivel' como true ou false.\n"
        "Regra 3: Verifique se o documento possui assinatura do juiz, carimbo oficial ou código de validação digital. Classifique 'autenticidade_judicial' como true ou false.\n"
        "Regra 4: Extraia o nome completo da criança ou adolescente mencionado no documento ('nome_crianca').\n"
        "Regra 5: Extraia o nome completo do(a) guardião(ã) nomeado(a) no documento ('nome_guardiao').\n"
        "OBS: NÃO DAR RESPOSTA EXPLICATIVA"
    ),
    response_schema={
        "type": "OBJECT",
        "properties": {
            "documento_valido": {"type": "BOOLEAN"},
            "legivel": {"type": "BOOLEAN"},
            "autenticidade_judicial": {"type": "BOOLEAN"},
            "nome_crianca": {"type": "STRING"},
            "nome_guardiao": {"type": "STRING"}
        },
        "required": ["documento_valido", "legivel", "autenticidade_judicial", "nome_crianca", "nome_guardiao"]
    }
)

# ---------------------------------------------------------------
# CONFIGURAÇÃO DE IA: C2 (TERMO DE TUTELA JUDICIAL)
# ---------------------------------------------------------------
generation_config_tutela_judicial = types.GenerateContentConfig(
    temperature=0,
    response_mime_type="application/json",
    system_instruction=(
        "Você é um auditor jurídico rigoroso de Termos de Tutela Judicial.\n"
        "Regra 1: Verifique se o documento é um Termo de Tutela válido. Classifique 'documento_valido' como true ou false.\n"
        "Regra 2: Verifique se o documento está totalmente legível. Classifique 'legivel' como true ou false.\n"
        "Regra 3: Verifique se o documento possui assinatura do juiz, carimbo oficial ou código de validação digital. Classifique 'autenticidade_judicial' como true ou false.\n"
        "Regra 4: Extraia o nome completo da criança ou adolescente mencionado no documento ('nome_crianca').\n"
        "Regra 5: Extraia o nome completo do(a) tutor(a) nomeado(a) no documento ('nome_tutor').\n"
        "OBS: NÃO DAR RESPOSTA EXPLICATIVA"
    ),
    response_schema={
        "type": "OBJECT",
        "properties": {
            "documento_valido": {"type": "BOOLEAN"},
            "legivel": {"type": "BOOLEAN"},
            "autenticidade_judicial": {"type": "BOOLEAN"},
            "nome_crianca": {"type": "STRING"},
            "nome_tutor": {"type": "STRING"}
        },
        "required": ["documento_valido", "legivel", "autenticidade_judicial", "nome_crianca", "nome_tutor"]
    }
)

######################################################################## TRATAMENTO DE ERRO AI STUDIO 
#---------------------------------------------------FUNCOES DE validcao de documento

def tratar_erro_gemini(e, tentativa, tentativas):
    """Função auxiliar interna para tratar o backoff e mensagens de erro do Gemini"""
    erro_str = str(e).lower()
    print(f"🔍 ERRO CAPTURADO NA API: {repr(e)}")
    
    # Identifica se é o erro 503, indisponibilidade ou timeout
    if "503" in erro_str or "unavailable" in erro_str or "high demand" in erro_str or "timeout" in erro_str or "429" in erro_str:
        if tentativa < tentativas:
            time.sleep(tentativa * 2) # Espera progressiva: 2s, 4s, 6s...
            return True, None # True = Deve tentar novamente
        else:
            return False, "⚠️ O sistema de inteligência artificial está processando muitas requisições neste momento. Por favor, clique em 'Validar' novamente em alguns segundos."
            
    # Se for um erro diferente que esgotou as tentativas
    if tentativa == tentativas:
        return False, "❌ Serviço de validação indisponível no momento. Verifique o documento e tente novamente."
        
    return False, "❌ Ocorreu um erro inesperado na leitura do documento."


def analisa_guarda_judicial(arquivo, tentativas=3):
    try:
        arquivo.seek(0)
        arquivo_bytes = arquivo.read()
    except Exception:
        return None, "Documento(s) ausente(s) ou ilegível(is)"
    
    mime_type = arquivo.type
    for tentativa in range(1, tentativas + 1):
        try:
            response = client_gemini.models.generate_content(
                model='gemini-3.1-flash-lite',
                contents=[
                    types.Part.from_bytes(data=arquivo_bytes, mime_type=mime_type),
                    "Analise este termo ou certidão de guarda judicial e extraia os dados conforme as regras."
                ],
                config=generation_config_guarda_judicial,
            )
            return json.loads(response.text.strip()), None
        except Exception as e:
            tentar_novo, msg_erro = tratar_erro_gemini(e, tentativa, tentativas)
            if tentar_novo:
                continue
            return None, msg_erro
            
    return None, "Documento(s) ausente(s) ou ilegível(is)"


def analisa_tutela_judicial(arquivo, tentativas=3):
    try:
        arquivo.seek(0)
        arquivo_bytes = arquivo.read()
    except Exception:
        return None, "Documento(s) ausente(s) ou ilegível(is)"
    
    mime_type = arquivo.type
    for tentativa in range(1, tentativas + 1):
        try:
            response = client_gemini.models.generate_content(
                model='gemini-3.1-flash-lite',
                contents=[
                    types.Part.from_bytes(data=arquivo_bytes, mime_type=mime_type),
                    "Analise este termo de tutela judicial e extraia os dados conforme as regras."
                ],
                config=generation_config_tutela_judicial,
            )
            return json.loads(response.text.strip()), None
        except Exception as e:
            tentar_novo, msg_erro = tratar_erro_gemini(e, tentativa, tentativas)
            if tentar_novo:
                continue
            return None, msg_erro
            
    return None, "Documento(s) ausente(s) ou ilegível(is)"


def analisa_certidao_averbacao(arquivo, tentativas=3):
    try:
        arquivo.seek(0)
        arquivo_bytes = arquivo.read()
    except Exception:
        return None, "⚠️ Erro ao ler o arquivo. Tente novamente."
    
    mime_type = arquivo.type
    for tentativa in range(1, tentativas + 1):
        try:
            response = client_gemini.models.generate_content(
                model='gemini-3.1-flash-lite',
                contents=[
                    types.Part.from_bytes(data=arquivo_bytes, mime_type=mime_type),
                    "Analise esta certidão de nascimento com averbação de adoção e extraia os dados conforme as regras."
                ],
                config=generation_config_adocao_averbacao,
            )
            return json.loads(response.text.strip()), None
        except Exception as e:
            tentar_novo, msg_erro = tratar_erro_gemini(e, tentativa, tentativas)
            if tentar_novo:
                continue
            return None, msg_erro
            
    return None, "Não foi possível validar o documento."


def analisa_guarda_adocao(arquivo, tentativas=3):
    try:
        arquivo.seek(0)
        arquivo_bytes = arquivo.read()
    except Exception:
        return None, "⚠️ Erro ao ler o arquivo. Tente novamente."
    
    mime_type = arquivo.type
    for tentativa in range(1, tentativas + 1):
        try:
            response = client_gemini.models.generate_content(
                model='gemini-3.1-flash-lite',
                contents=[
                    types.Part.from_bytes(data=arquivo_bytes, mime_type=mime_type),
                    "Analise este documento judicial de guarda para fins de adoção e extraia os dados conforme as regras."
                ],
                config=generation_config_guarda_adocao,
            )
            return json.loads(response.text.strip()), None
        except Exception as e:
            tentar_novo, msg_erro = tratar_erro_gemini(e, tentativa, tentativas)
            if tentar_novo:
                continue
            return None, msg_erro
            
    return None, "Não foi possível validar o documento judicial."


def analisa_uniao_estavel(arquivo, tentativas=3):
    try:
        arquivo.seek(0)
        arquivo_bytes = arquivo.read()
    except Exception:
        return None, "⚠️ Erro ao ler o arquivo de união estável. Tente novamente."
    
    mime_type = arquivo.type
    for tentativa in range(1, tentativas + 1):
        try:
            response = client_gemini.models.generate_content(
                model='gemini-3.1-flash-lite',
                contents=[
                    types.Part.from_bytes(data=arquivo_bytes, mime_type=mime_type),
                    "Analise esta declaração de união estável e extraia os dados conforme as regras."
                ],
                config=generation_config_uniao_estavel,
            )
            return json.loads(response.text.strip()), None
        except Exception as e:
            tentar_novo, msg_erro = tratar_erro_gemini(e, tentativa, tentativas)
            if tentar_novo:
                continue
            return None, msg_erro
            
    return None, "⚠️ Não foi possível validar o documento."


def analisa_certidao(arquivo, tentativas=3):
    try:
        arquivo.seek(0)
        arquivo_bytes = arquivo.read()
    except Exception:
        return None, "❌ Erro ao ler o arquivo. Tente fazer o upload novamente."

    mime_type = arquivo.type
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
            texto_limpo = response.text.strip()
            return json.loads(texto_limpo), None

        except json.JSONDecodeError:
            return None, "❌ Resposta da IA em formato inesperado. Tente novamente."
        except Exception as e:
            tentar_novo, msg_erro = tratar_erro_gemini(e, tentativa, tentativas)
            if tentar_novo:
                continue
            return None, msg_erro

    return None, "❌ Não foi possível validar após várias tentativas."


def valida_nome_pais_certidao(dados_certidao: dict, nome_colaborador: str):
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

    return False, None


def analisa_certidao_complementar(arquivo, tentativas=3):
    try:
        arquivo.seek(0)
        arquivo_bytes = arquivo.read()
    except Exception:
        return None, "❌ Erro ao ler o arquivo. Tente fazer o upload novamente."

    mime_type = arquivo.type
    for tentativa in range(1, tentativas + 1):
        try:
            response = client_gemini.models.generate_content(
                model='gemini-3.1-flash-lite',
                contents=[
                    types.Part.from_bytes(data=arquivo_bytes, mime_type=mime_type),
                    "Analise o documento e retorne os dados no formato estruturado."
                ],
                config=generation_config_doc_complementar,
            )
            texto_limpo = response.text.strip()
            return json.loads(texto_limpo), None

        except json.JSONDecodeError:
            return None, "❌ Resposta da IA em formato inesperado. Tente novamente."
        except Exception as e:
            tentar_novo, msg_erro = tratar_erro_gemini(e, tentativa, tentativas)
            if tentar_novo:
                continue
            return None, msg_erro

    return None, "❌ Não foi possível validar após várias tentativas."






#---------------------------------------------------FUNCOES DE SISTEMA



def busca_colaborador(situacoes_invalidas=["Desligado", "Aposentadoria p/Invalidez"]):
    """Busca colaborador diretamente no banco de dados (Supabase)"""
    print("Buscando colaborador no banco...")
    
    with st.form("form_busca"):

        cracha_digitado = st.text_input("Crachá:", placeholder="Digite o número e aperte Enter")
        buscar = st.form_submit_button("🔍 Buscar")
        
    if not buscar:
        return None
        
    if not cracha_digitado.strip() or not cracha_digitado.strip().isdigit():
        st.warning("⚠️ Por favor, digite um número de crachá válido antes de buscar.")
        st.session_state.colaborador = None
        return None
        
    cracha_numero = int(cracha_digitado.strip())
    
    supabase_connector = SupabaseConnector()
    try:
        query = f"""
        SELECT 
            cracha,
            nome,
            descricao_situacao,
            titulo_reduzido_cargo,
            id_cargo,
            data_demissao
        FROM colaboradores
        WHERE cracha = {cracha_numero}
        """
        df = pd.read_sql(query, supabase_connector.engine)
        colaborador = df.to_dict(orient="records")[0] if not df.empty else None
        
        if not colaborador:
            st.error("⚠️ Crachá não encontrado na base de dados.")
            st.session_state.colaborador = None  # Reseta o estado para bloquear a tela seguinte
            return None
            
        if colaborador["descricao_situacao"] in situacoes_invalidas:
            st.error(f"⚠️ Colaborador não elegível. Situação atual: {colaborador['descricao_situacao']}")
            st.session_state.colaborador = None  # Reseta o estado para bloquear a tela seguinte
            return None
            
        # ==================== SALVA NO SESSION_STATE ====================
        st.session_state.colaborador = {
            "id": colaborador["cracha"],
            "Crachá": colaborador["cracha"],
            "Nome": colaborador["nome"],
            "Título Reduzido (Cargo)": colaborador["titulo_reduzido_cargo"],
            "Descrição (Situação)": colaborador["descricao_situacao"],
            # AQUI ESTÁ A CORREÇÃO: Garante que o id_cargo seja salvo como um número inteiro
            "id_cargo": int(colaborador["id_cargo"]) if colaborador.get("id_cargo") else None
        }
        
        st.divider()
        st.subheader("📋 Ficha do Colaborador")
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
        
        email = st.text_input("E-mail", placeholder="exemplo@gmail.com")
        confirmacao_email = st.text_input("Confirme o E-mail", placeholder="exemplo@gmail.com")
            
        telefone = st.text_input("Número de Telefone (WhatsApp)")
        salvar = st.form_submit_button("💾 Salvar Dados de Contato")
        
    if not salvar:
        return None
        
    erros = []
    
    email_digitado = email.strip()
    email_confirmado = confirmacao_email.strip()
    
    if not email_digitado or not email_confirmado:
        erros.append("⚠️ O preenchimento e a confirmação do e-mail são obrigatórios.")
    elif email_digitado.lower() != email_confirmado.lower():
        erros.append("⚠️ Os e-mails não batem. Por favor, digite novamente.")
        
    if not telefone.strip():
        erros.append("⚠️ Telefone é obrigatório.")
    else:
        telefone_valido, mensagem_telefone = valida_telefone(telefone)
        if not telefone_valido:
            erros.append(f"⚠️ {mensagem_telefone}")
            
    if erros:
        for x in erros:
            st.error(f"{x}")
        return None
        
    st.success("✅ Dados de contato salvos com sucesso!")
    
    return {
        "email": email_digitado.lower(), 
        "telefone": formata_telefone(telefone)
    }


def adicionar_dependentes():
    st.subheader("👶 Adicionar Dependente")
    st.write(f"Nome Responsável: {st.session_state.colaborador['Nome']}")

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
    # FORMULÁRIO PRINCIPAL DE ADIÇÃO (DIRETO AO CARRINHO)
    # =========================================================
    with st.form("form_dependente"):
        nome_filho    = st.text_input("Nome Completo da Criança")
        genero        = st.selectbox("Gênero:", ["", "Masculino", "Feminino"],
                                     format_func=lambda x: "Selecione o Gênero..." if x == "" else x)
        data_maxima   = date.today() - timedelta(days=730)
        data_nascimento = st.date_input("Data de Nascimento",
                                        min_value=date(2000, 1, 1), max_value=data_maxima, format="DD/MM/YYYY")
        certidao      = st.file_uploader(
            "Anexar Certidão de Nascimento 📄",
            type=["pdf", "png", "jpg", "jpeg"],
            help="Pode enviar foto, imagem escaneada ou PDF"
        )
        salvar = st.form_submit_button("📁 Adicionar ao Carrinho")

    if not salvar:
        return None

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

    # ===================== CHECAGEM DE DUPLICIDADE (Carrinho + Banco) =====================
    nome_padronizado = padroniza_texto(nome_filho).strip()

    db = SessionLocal()
    try:
        # 1. Verifica se já está no carrinho atual da sessão
        for dep in st.session_state.get("lista_dependentes", []):
            if padroniza_texto(dep["Nome_filho"]) == nome_padronizado and dep["Data_nascimento"] == data_nascimento.strftime("%d/%m/%Y"):
                st.error("❌ Esta criança já está no seu carrinho ou já possui um kit cadastrado.")
                return None

        # 2. Verifica no banco de dados oficial
        duplicado = db.query(Dependente).filter(
            Dependente.nome_filho.ilike(f"%{nome_padronizado}%"),
            Dependente.data_nascimento == data_nascimento
        ).first()

        if duplicado:
            st.error("❌ Esta criança já possui um kit cadastrado.")
            return None

        # Análise da certidão com Gemini
        with st.spinner("🔍 Analisando certidão de nascimento, aguarde..."):
            dados_certidao, erro_api = analisa_certidao(certidao)
       
        if erro_api:
            st.error(erro_api)
            return None

        # TRATAMENTO PARA DOCUMENTO ILEGÍVEL OU INVÁLIDO
        if not dados_certidao.get("legivel", True) or not dados_certidao.get("documento_valido", True):
            st.error("❌ Documento ilegível, mande outro arquivo")
            return None

        # Validações dos dados da criança na certidão
        dados_ok, msg_dados = valida_dados_crianca_certidao(dados_certidao, nome_filho, data_nascimento, genero)
        if not dados_ok:
            st.error(msg_dados)
            return None

        valido, mensagem = valida_nome_pais_certidao(
            dados_certidao, st.session_state.colaborador['Nome']
        )

        if valido:
            st.success(mensagem)
        else:
            st.info("ℹ️ Vínculo requer conferência, mas o item foi adicionado ao carrinho para validação posterior.")

        # Retorna o dicionário para ser inserido puramente no carrinho (Session State)
        nome_final = padroniza_texto(dados_certidao.get("nome_crianca") or nome_filho)
        return {
            "ID_Dependente": None, # Será gerado ao finalizar o carrinho no banco
            "ID_Colaborador": st.session_state.colaborador['Crachá'],
            "Nome_filho": nome_final,
            "Gênero": genero,
            "Data_nascimento": data_nascimento.strftime("%d/%m/%Y"),
            "Escolaridade": st.session_state.escolaridade,
            "Ano_escolar": st.session_state.ano_escolar,
            "Data_Cadastro": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "revisao_rh": "Sim" if not valido else False
        }

    finally:
        db.close()


def ficha_colaborador():
    print("Exibindo ficha do colaborador...")
    # Código para exibir a ficha do colaborador
    # Exemplo: renderização de interface, exibição de dados, etc.
    pass

#---------------------------------------------------FUNCOES DE VALIDACAO input

def verificar_crianca_duplicada(db, nome_filho, data_nascimento):
    if not nome_filho:
        return False
        
    # Padroniza e limpa o nome (tudo minúsculo, sem espaços extras)
    nome_padronizado = padroniza_texto(nome_filho).lower().strip()
    
    # Padroniza a data de nascimento para string DD/MM/YYYY independentemente do formato recebido
    if hasattr(data_nascimento, "strftime"):
        data_str = data_nascimento.strftime("%d/%m/%Y")
    else:
        data_str = str(data_nascimento).strip()
    
    # 1. VERIFICAÇÃO RIGOROSA NO CARRINHO (Session State)
    for dep in st.session_state.get("lista_dependentes", []):
        dep_nome = padroniza_texto(dep.get("Nome_filho", "")).lower().strip()
        dep_data = str(dep.get("Data_nascimento", "")).strip()
        
        # Se o nome bater E a data de nascimento for igual, bloqueia!
        if dep_nome == nome_padronizado and dep_data == data_str:
            return True
            
    # 2. VERIFICAÇÃO NO BANCO DE DADOS OFICIAL
    if hasattr(data_nascimento, "strftime"):
        data_obj_db = data_nascimento
    else:
        try:
            data_obj_db = datetime.strptime(data_str, "%d/%m/%Y").date()
        except:
            data_obj_db = None

    if data_obj_db:
        duplicado = db.query(Dependente).filter(
            Dependente.nome_filho.ilike(f"%{nome_padronizado}%"),
            Dependente.data_nascimento == data_obj_db
        ).first()
        if duplicado:
            return True
            
    return False
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
def avalia_caso_colaborador():
    st.divider()
    st.subheader("📋 Validação de Vínculo do Dependente")
    st.write("Por favor, selecione a situação que melhor se aplica ao registro do seu dependente:")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("A) Filho(a) biológico(a) ou adotivo(a)", width='stretch'):
            st.session_state.tipo_fluxo = "A"
            st.rerun()
            
    with col2:
        if st.button("B) Enteado(a) (Registrado no nome do cônjuge/companheiro)", width='stretch'):
            st.session_state.tipo_fluxo = "B"
            st.rerun()
            
    with col3:
        if st.button("C) Criança/Adolescente sob Guarda ou Tutela", width='stretch'):
            st.session_state.tipo_fluxo = "C"
            st.rerun()

#---------------------------------------------------FUNCOES DE validcao de documento
def analisa_guarda_judicial(arquivo, tentativas=3):
    try:
        arquivo.seek(0)
        arquivo_bytes = arquivo.read()
    except Exception:
        return None, "Documento(s) ausente(s) ou ilegível(is)"
    
    mime_type = arquivo.type
    for tentativa in range(1, tentativas + 1):
        try:
            response = client_gemini.models.generate_content(
                model='gemini-3.1-flash-lite',
                contents=[
                    types.Part.from_bytes(data=arquivo_bytes, mime_type=mime_type),
                    "Analise este termo ou certidão de guarda judicial e extraia os dados conforme as regras."
                ],
                config=generation_config_guarda_judicial,
            )
            return json.loads(response.text.strip()), None
        except Exception:
            if tentativa == tentativas:
                return None, "Documento(s) ausente(s) ou ilegível(is)"
    return None, "Documento(s) ausente(s) ou ilegível(is)"

def analisa_tutela_judicial(arquivo, tentativas=3):
    try:
        arquivo.seek(0)
        arquivo_bytes = arquivo.read()
    except Exception:
        return None, "Documento(s) ausente(s) ou ilegível(is)"
    
    mime_type = arquivo.type
    for tentativa in range(1, tentativas + 1):
        try:
            response = client_gemini.models.generate_content(
                model='gemini-3.1-flash-lite',
                contents=[
                    types.Part.from_bytes(data=arquivo_bytes, mime_type=mime_type),
                    "Analise este termo de tutela judicial e extraia os dados conforme as regras."
                ],
                config=generation_config_tutela_judicial,
            )
            return json.loads(response.text.strip()), None
        except Exception:
            if tentativa == tentativas:
                return None, "Documento(s) ausente(s) ou ilegível(is)"
    return None, "Documento(s) ausente(s) ou ilegível(is)"


def analisa_certidao_averbacao(arquivo, tentativas=3):
    try:
        arquivo.seek(0)
        arquivo_bytes = arquivo.read()
    except Exception:
        return None, "⚠️ Erro ao ler o arquivo. Tente novamente."
    
    mime_type = arquivo.type
    ERROS_COM_RETRY = ("503", "timeout", "timed out", "429")
    
    for tentativa in range(1, tentativas + 1):
        try:
            response = client_gemini.models.generate_content(
                model='gemini-3.1-flash-lite',
                contents=[
                    types.Part.from_bytes(data=arquivo_bytes, mime_type=mime_type),
                    "Analise esta certidão de nascimento com averbação de adoção e extraia os dados conforme as regras."
                ],
                config=generation_config_adocao_averbacao,
            )
            return json.loads(response.text.strip()), None
        except Exception as e:
            if tentativa == tentativas:
                return None, "⚠️ Serviço de validação indisponível no momento."
    return None, "Não foi possível validar o documento."

def analisa_guarda_adocao(arquivo, tentativas=3):
    try:
        arquivo.seek(0)
        arquivo_bytes = arquivo.read()
    except Exception:
        return None, "⚠️ Erro ao ler o arquivo. Tente novamente."
    
    mime_type = arquivo.type
    
    for tentativa in range(1, tentativas + 1):
        try:
            response = client_gemini.models.generate_content(
                model='gemini-3.1-flash-lite',
                contents=[
                    types.Part.from_bytes(data=arquivo_bytes, mime_type=mime_type),
                    "Analise este documento judicial de guarda para fins de adoção e extraia os dados conforme as regras."
                ],
                config=generation_config_guarda_adocao,
            )
            return json.loads(response.text.strip()), None
        except Exception as e:
            if tentativa == tentativas:
                return None, "⚠️ Serviço de validação judicial indisponível no momento."
    return None, "Não foi possível validar o documento judicial."



def analisa_uniao_estavel(arquivo, tentativas=3):
    try:
        arquivo.seek(0)
        arquivo_bytes = arquivo.read()
    except Exception:
        return None, "⚠️ Erro ao ler o arquivo de união estável. Tente novamente."
    
    mime_type = arquivo.type
    ERROS_COM_RETRY = ("503", "timeout", "timed out", "429")
    
    for tentativa in range(1, tentativas + 1):
        try:
            response = client_gemini.models.generate_content(
                model='gemini-3.1-flash-lite',
                contents=[
                    types.Part.from_bytes(data=arquivo_bytes, mime_type=mime_type),
                    "Analise esta declaração de união estável e extraia os dados conforme as regras."
                ],
                config=generation_config_uniao_estavel,
            )
            dados = json.loads(response.text.strip())
            return dados, None
        except Exception as e:
            if tentativa == tentativas:
                return None, "⚠️ Serviço de validação de união estável indisponível no momento."
    return None, "⚠️ Não foi possível validar o documento."


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

    if not dados_certidao.get("documento_valido"):
        return False, "❌ Documento adicionado nao e um certidao de nascimento"

    if dados_certidao.get("legivel") is False:
        return False, "❌ Documento esta inlegivel , carregue outro"

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

def catalogo_kits_por_escolaridade():
    # URL pública do Storage no Supabase
    BASE_URL = "https://shmjscmivtujhrcjeicn.supabase.co/storage/v1/object/public/imagens/"
    
    kits_infantil = ["Dinossauro", "Abelha", "Borboleta", "Unicornio", "Cachorro"]
    kits_efi = [f"EFI-{i}" for i in range(1, 12)]
    kits_efii = [f"EFII-{i}" for i in range(1, 17)]
    kits_em = [f"EM-{i}" for i in range(1, 14)]
    
    return {
        "Educação Infantil": kits_infantil,
        "Ensino Fundamental I": kits_efi,
        "Ensino Fundamental II": kits_efii,
        "Ensino Médio": kits_em,
        "Ensino Superior / Técnico": kits_em
    }, BASE_URL

def escolher_kits_colaborador():
    st.divider()
    st.subheader("🎒 Escolha dos Kits Escolares")
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
            
        catalogo, base_url = catalogo_kits_por_escolaridade()
        escolhas = []
        st.write(f"Você possui {len(dependentes_colaborador)} crédito(s) de kit.")
        
        # INJEÇÃO DO CSS PARA PADRONIZAR A ALTURA DAS IMAGENS
        st.markdown("""
            <style>
            div[data-testid="stColumn"] img {
                height: 180px !important;
                object-fit: contain !important;
            }
            </style>
        """, unsafe_allow_html=True)
        
        with st.form("form_escolha_kits"):
            for dependente in dependentes_colaborador:
                nome_filho = dependente.nome_filho
                escolaridade = dependente.escolaridade
                ano_escolar = dependente.ano_escola
                genero = dependente.genero
                id_dependente = dependente.id_dependente
                
                st.markdown(f"### 👶 {nome_filho}")
                st.write(f"**Escolaridade:** {escolaridade} | **Ano escolar:** {ano_escolar}")
                
                opcoes_kits = catalogo.get(escolaridade, [])
                if not opcoes_kits:
                    st.error(f"Não existem kits cadastrados para a escolaridade: {escolaridade}")
                    continue
                
                # ========================================================
                # VITRINE VISUAL DE KITS (Exibição lado a lado)
                # ========================================================
                st.markdown(f"**Catálogo Disponível:**")
                
                itens_por_linha = 4
                for i in range(0, len(opcoes_kits), itens_por_linha):
                    colunas = st.columns(itens_por_linha)
                    for j in range(itens_por_linha):
                        if i + j < len(opcoes_kits):
                            nome_kit = opcoes_kits[i+j]
                            nome_arquivo = nome_kit.replace(" ", "")
                            url_img = f"{base_url}{nome_arquivo}.png"
                            
                            with colunas[j]:
                                st.image(url_img, caption=nome_kit, width='stretch')
                
                st.write("---")
                # ========================================================

                kit_escolhido = st.selectbox(
                    f"Confirme o kit desejado para {nome_filho}:",
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
        erros = [f"⚠️ Selecione um kit para {e['Nome_filho']}." for e in escolhas if not e["Kit_Escolhido"]]
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
        st.success("🎉 Kits escolhidos com sucesso!")
        return novas_escolhas
    finally:
        db.close()

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
    st.set_page_config(page_title='Funfarme - Kit Escolar', page_icon='🎒', layout="wide")
    st.title('🎒 Funfarme - Kit Escolar')
    
    # ---------------------------------------------------------------
    # Inicializa todos os estados necessários ---
    if 'colaborador' not in st.session_state:
        st.session_state.colaborador = None
    if 'contato' not in st.session_state:
        st.session_state.contato = None
    if 'tipo_fluxo' not in st.session_state:
        st.session_state.tipo_fluxo = None
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

    # ===================== CARRINHO VISUAL NA SIDEBAR =====================
    if st.session_state.contato is not None and not st.session_state.cadastro_finalizado:
        with st.sidebar:
            st.markdown("### 🛒 Carrinho de Dependentes")
            st.caption(f"Colaborador: {st.session_state.colaborador['Nome']}")
            st.divider()
            
            if st.session_state.lista_dependentes:
                for i, dep in enumerate(st.session_state.lista_dependentes, start=1):
                    st.markdown(f"**{i}. {dep['Nome_filho']}**")
                    st.write(f"📚 {dep.get('Escolaridade', '')}")
                    st.caption(f"Ano: {dep.get('Ano_escolar', '')} | Nasc: {dep.get('Data_nascimento', '')}")
                    st.markdown("---")
                
                if st.button("🚀 Finalizar Carrinho e Escolher Kits", type="primary", width='stretch'):
                    # GRAVAÇÃO OFICIAL NO BANCO DE DADOS EM LOTE
                    db = SessionLocal()
                    try:
                        for dep in st.session_state.lista_dependentes:
                            if not dep.get("ID_Dependente"):
                                novo_dep_db = Dependente(
                                    id_colaborador=st.session_state.colaborador.get("id"),
                                    nome_filho=dep["Nome_filho"],
                                    data_nascimento=datetime.strptime(dep["Data_nascimento"], "%d/%m/%Y").date(),
                                    genero=dep.get("Gênero", "Não informado"),
                                    escolaridade=dep["Escolaridade"],
                                    ano_escola=dep["Ano_escolar"],
                                    revisao_rh=dep.get("revisao_rh")
                                )
                                db.add(novo_dep_db)
                                db.commit()
                                db.refresh(novo_dep_db)
                                dep["ID_Dependente"] = novo_dep_db.id_dependente
                    finally:
                        db.close()

                    st.session_state.aguardando_decisao = False
                    st.session_state.escolhendo_kits = True
                    st.rerun()
            else:
                st.info("Seu carrinho está vazio. Adicione os dependentes ao lado.")

    # ===================== FASE 1: BUSCA E CONTATO =====================
    if st.session_state.contato is None:
        st.write('Informe seu crachá e clique em Buscar Colaborador.')
        
        colaborador = busca_colaborador()
        if colaborador is not None:
            st.session_state.colaborador = colaborador

        if st.session_state.colaborador is not None:
            contato = adiciona_dados_contato()
            if contato is not None:
                st.session_state.contato = contato
                st.rerun()  
    
    else:
        # ===================== FASE 2: TRIAGEM DE VÍNCULO =====================
        st.success(f"👤 Colaborador: {st.session_state.colaborador['Nome']} | ✅ Contato salvo.")
        
        # -------------------------------------------------------------------------
        # TELAS DE CONTROLE UNIVERSAL
        # -------------------------------------------------------------------------
        if st.session_state.cadastro_finalizado:
            st.divider()
            st.success("✅ Cadastro finalizado com sucesso! Obrigado.")
            if st.session_state.escolhas_kits:
                exibir_qrcode_final()
            st.balloons()
            return

        if st.session_state.escolhendo_kits:
            escolhas_kits = escolher_kits_colaborador()
            if escolhas_kits is not None:
                st.session_state.escolhas_kits = escolhas_kits
                st.session_state.escolhendo_kits = False
                st.session_state.cadastro_finalizado = True                                
                st.rerun()
            return

        if st.session_state.aguardando_decisao:
            st.divider()
            st.subheader("✅ Item adicionado ao carrinho com sucesso!")
            st.write("Confira os itens no seu **Carrinho (na barra lateral à esquerda)** ou escolha abaixo o que deseja fazer:")
            
            col1, col2 = st.columns([1, 1])
            with col1:
                # Modifiquei o texto do botão para abranger tanto dependente quanto o próprio estagiário
                if st.button("➕ Adicionar outro dependente/kit", type="primary", width='stretch'):
                    st.session_state.aguardando_decisao = False
                    st.session_state.escolaridade = ""
                    st.session_state.ano_escolar = ""
                    st.session_state.aguardando_doc_complementar = False
                    st.session_state.dados_certidao_filho = None
                    st.session_state.dependente_temp = None
                    st.session_state.tipo_fluxo = None # Reseta para a tela inicial
                    if 'sub_opcao_a' in st.session_state: del st.session_state['sub_opcao_a']
                    if 'sub_opcao_b' in st.session_state: del st.session_state['sub_opcao_b']
                    if 'sub_opcao_c' in st.session_state: del st.session_state['sub_opcao_c']
                    st.rerun()
            with col2:
                if st.button("🚀 Finalizar carrinho e escolher kits", width='stretch'):
                    db = SessionLocal()
                    try:
                        for dep in st.session_state.lista_dependentes:
                            if not dep.get("ID_Dependente"):
                                novo_dep_db = Dependente(
                                    id_colaborador=st.session_state.colaborador.get("id"),
                                    nome_filho=dep["Nome_filho"],
                                    data_nascimento=datetime.strptime(dep["Data_nascimento"], "%d/%m/%Y").date(),
                                    genero=dep.get("Gênero", "Não informado"),
                                    escolaridade=dep["Escolaridade"],
                                    ano_escola=dep["Ano_escolar"],
                                    revisao_rh=dep.get("revisao_rh")
                                )
                                db.add(novo_dep_db)
                                db.commit()
                                db.refresh(novo_dep_db)
                                dep["ID_Dependente"] = novo_dep_db.id_dependente
                    finally:
                        db.close()

                    st.session_state.aguardando_decisao = False
                    st.session_state.escolhendo_kits = True
                    st.rerun()
            return

        # -------------------------------------------------------------------------
        # SELEÇÃO DO FLUXO PRINCIPAL COM NOVA REGRA DE NEGÓCIO (ESTAGIÁRIO)
        # -------------------------------------------------------------------------
        if st.session_state.tipo_fluxo is None:
            # Lista de cargos que classificam como estagiário
            cargos_estagiario = [600, 601, 602, 5001]
            id_cargo_colab = st.session_state.colaborador.get('id_cargo')
            
            # Converte para int caso tenha vindo como string do banco
            if id_cargo_colab is not None and int(id_cargo_colab) in cargos_estagiario:
                st.session_state.tipo_fluxo = "ESTAGIARIO"
                st.rerun()
            else:
                # Se não for estagiário, exibe os caminhos A, B e C normalmente
                avalia_caso_colaborador()
                return

        # =========================================================================
        # CAMINHO EXCLUSIVO: ESTAGIÁRIO (KIT PRÓPRIO)
        # =========================================================================
        elif st.session_state.tipo_fluxo == "ESTAGIARIO":
            st.subheader("🎓 Cadastro de Estagiário (Kit Próprio)")
            st.info("Como estagiário, você tem direito ao seu próprio kit escolar. Preencha seus dados acadêmicos e anexe a sua **Certidão de Nascimento** para validação automática.")

            if 'escolaridade' not in st.session_state: st.session_state.escolaridade = ""
            if 'ano_escolar' not in st.session_state: st.session_state.ano_escolar = ""

            # Permite apenas as opções que fazem sentido para a idade de estagiário (Médio pra cima)
            st.selectbox("Sua Escolaridade", ["", "Ensino Médio", "Ensino Superior / Técnico"], format_func=lambda x: "Selecione a Escolaridade..." if x == "" else x, key="escolaridade")
            
            opcoes_ano = {
                "": [],
                "Ensino Médio": ["", "1º Ano", "2º Ano", "3º Ano"],
                "Ensino Superior / Técnico": ["", "1º Semestre", "2º Semestre", "3º Semestre", "4º Semestre", "5º Semestre", "6º Semestre", "7º Semestre", "8º Semestre", "9º Semestre", "10º Semestre"]
            }
            
            if st.session_state.escolaridade:
                st.selectbox("Ano/Semestre em 2026", opcoes_ano[st.session_state.escolaridade], format_func=lambda x: "Selecione o Ano/Semestre..." if x == "" else x, key="ano_escolar")

            with st.form("form_estagiario"):
                genero_est = st.selectbox("Seu Gênero:", ["", "Masculino", "Feminino"], format_func=lambda x: "Selecione o Gênero..." if x == "" else x)
                
                # Range de datas maior (Estagiários são adultos/jovens)
                data_nascimento_est = st.date_input("Sua Data de Nascimento", min_value=date(1950, 1, 1), max_value=date.today(), format="DD/MM/YYYY")
                
                certidao_est = st.file_uploader("Anexe SUA Certidão de Nascimento", type=["pdf", "png", "jpg", "jpeg"])
                
                salvar_est = st.form_submit_button("Validar e Adicionar ao Carrinho")

            if salvar_est:
                erros_est = []
                if not genero_est: erros_est.append("O gênero é obrigatório.")
                if not st.session_state.escolaridade: erros_est.append("A escolaridade é obrigatória.")
                if not st.session_state.ano_escolar: erros_est.append("O ano escolar é obrigatório.")
                if not certidao_est: erros_est.append("A certidão de nascimento é obrigatória.")

                if erros_est:
                    for e in erros_est: st.error(f"⚠️ {e}")
                else:
                    with st.spinner("Analisando certidão via IA... Aguarde"):
                        dados_cert, err_cert = analisa_certidao(certidao_est)
                        
                        if err_cert:
                            st.error(f"⚠️ {err_cert}")
                        elif not dados_cert.get("legivel", True) or not dados_cert.get("documento_valido", True):
                            st.error("❌ Documento ilegível ou não é uma certidão válida, mande outro arquivo.")
                        else:
                            # 1. Comparação rigorosa: Nome do Colaborador (Banco) vs Nome da Criança (na Certidão lida pela IA)
                            nome_colab = padroniza_texto(st.session_state.colaborador['Nome'])
                            nome_cert = padroniza_texto(dados_cert.get("nome_crianca", ""))
                            
                            if nome_colab != nome_cert:
                                st.error(f"⚠️ Vínculo negado: O nome lido na certidão ({dados_cert.get('nome_crianca', 'N/A')}) não corresponde ao seu nome cadastrado ({st.session_state.colaborador['Nome']}).")
                            else:
                                db = SessionLocal()
                                try:
                                    # Usa o mesmo verificador de duplicidade para garantir que o estagiário não peça o próprio kit 2x
                                    if verificar_crianca_duplicada(db, nome_colab, data_nascimento_est):
                                        st.error("❌ Você já adicionou o seu kit ao carrinho ou já finalizou este cadastro.")
                                    else:
                                        # Cadastra o próprio Estagiário como "Filho" na listagem
                                        st.session_state.lista_dependentes.append({
                                            "ID_Dependente": None,
                                            "ID_Colaborador": st.session_state.colaborador['Crachá'],
                                            "Nome_filho": nome_colab, 
                                            "Gênero": genero_est,
                                            "Data_nascimento": data_nascimento_est.strftime("%d/%m/%Y"),
                                            "Escolaridade": st.session_state.escolaridade,
                                            "Ano_escolar": st.session_state.ano_escolar,
                                            "revisao_rh": "Não (Estagiário Validado)"
                                        })
                                        st.success("✅ Certidão validada! Seu Kit de Estagiário foi adicionado ao carrinho.")
                                        st.session_state.aguardando_decisao = True
                                        st.rerun()
                                finally:
                                    db.close()

        # =========================================================================
        # CAMINHO A: FILHO(A) BIOLÓGICO(A) OU ADOTIVO(A)
        # =========================================================================
        elif st.session_state.tipo_fluxo == "A":
            st.subheader("📝 Cadastro - Filho(a) Biológico(a) ou Adotivo(a)")
            
            if st.button("⬅️ Voltar e escolher outra opção", key="voltar_a"):
                st.session_state.tipo_fluxo = None
                if 'sub_opcao_a' in st.session_state:
                    del st.session_state['sub_opcao_a']
                st.rerun()

            st.write("---")
            sub_opcao_a = st.radio(
                "🎯 Selecione a forma de comprovação do vínculo:",
                [
                    "**A1:** Certidão de Nascimento - Filho(a) Biológico(a) ",
                    "**A2:** Certidão de Nascimento com averbação de adoção",
                    "**A3:** Documento judicial que comprove a guarda para fins de adoção"
                ],
                index=None,
                key="sub_opcao_a"
            )

            # Só exibe se o usuário selecionar uma opção
            if sub_opcao_a:
                st.divider()
                
                # --- SUB-FLUXO A1 ---
                if "A1" in sub_opcao_a:
                    dependente = adicionar_dependentes()
                    if dependente is not None:
                        st.session_state.lista_dependentes.append(dependente)
                        st.session_state.aguardando_decisao = True
                        st.rerun()

                # --- SUB-FLUXOS A2 e A3 (Exigem seleção prévia de Escolaridade) ---
                elif "A2" in sub_opcao_a or "A3" in sub_opcao_a:
                    if 'escolaridade' not in st.session_state: st.session_state.escolaridade = ""
                    if 'ano_escolar' not in st.session_state: st.session_state.ano_escolar = ""

                    st.selectbox("Escolaridade", ["", "Educação Infantil", "Ensino Fundamental I", "Ensino Fundamental II", "Ensino Médio"], format_func=lambda x: "Selecione a Escolaridade..." if x == "" else x, key="escolaridade")
                    
                    opcoes_ano = {
                        "": [],
                        "Educação Infantil":    ["", "Maternal I", "Maternal II", "Etapa I", "Etapa II"],
                        "Ensino Fundamental I": ["", "1º Ano", "2º Ano", "3º Ano", "4º Ano", "5º Ano"],
                        "Ensino Fundamental II":["", "6º Ano", "7º Ano", "8º Ano", "9º Ano"],
                        "Ensino Médio":         ["", "1º Ano", "2º Ano", "3º Ano"]
                    }
                    
                    if st.session_state.escolaridade:
                        st.selectbox("Ano Escolar 2026", opcoes_ano[st.session_state.escolaridade], format_func=lambda x: "Selecione o Ano Escolar..." if x == "" else x, key="ano_escolar")

                    st.write("---")

                    # --- SUB-FLUXO A2 FORMULÁRIO ---
                    if "A2" in sub_opcao_a:
                        with st.form("form_fluxo_a2"):
                            st.info("📌 Requisitos (A2): Envie a **Certidão de Nascimento** contendo explicitamente a averbação de adoção.")
                            
                            nome_filho_a2 = st.text_input("Nome Completo da Criança")
                            genero_a2 = st.selectbox("Gênero:", ["", "Masculino", "Feminino"], format_func=lambda x: "Selecione o Gênero..." if x == "" else x)
                            
                            data_maxima_a2 = date.today() - timedelta(days=730)
                            data_nascimento_a2 = st.date_input("Data de Nascimento da Criança", min_value=date(2000, 1, 1), max_value=data_maxima_a2, format="DD/MM/YYYY")
                            
                            certidao_averbada = st.file_uploader("Anexar Certidão com Averbação de Adoção", type=["pdf", "png", "jpg", "jpeg"], key="cert_a2")
                            
                            salvar_a2 = st.form_submit_button("Validar e Adicionar ao Carrinho (A2)")

                        if salvar_a2:
                            erros_a2 = []
                            if not nome_filho_a2.strip(): erros_a2.append("O nome da criança é obrigatório.")
                            if not genero_a2: erros_a2.append("O gênero é obrigatório.")
                            if not st.session_state.escolaridade: erros_a2.append("A escolaridade é obrigatória.")
                            if not st.session_state.ano_escolar: erros_a2.append("O ano escolar é obrigatório.")
                            if not certidao_averbada: erros_a2.append("A certidão com averbação é obrigatória.")
                                
                            if erros_a2:
                                for e in erros_a2: st.error(f"⚠️ {e}")
                            else:
                                with st.spinner("Analisando certidão com averbação via IA... Aguarde"):
                                    dados_a2, err_a2 = analisa_certidao_averbacao(certidao_averbada)
                                    if err_a2:
                                        st.error(f"⚠️ {err_a2}")
                                    else:
                                        if not dados_a2.get("documento_valido"):
                                            st.error("⚠️ Documento adicionado não é uma certidão de nascimento.")
                                        elif not dados_a2.get("legivel"):
                                            st.error("⚠️ Documento está ilegível, carregue outro.")
                                        elif not dados_a2.get("tem_averbacao_adocao"):
                                            st.error("⚠️ O documento não possui a averbação de adoção exigida.")
                                        else:
                                            nome_cert_a2 = padroniza_texto(dados_a2.get("nome_crianca", ""))
                                            nome_form_a2 = padroniza_texto(nome_filho_a2)
                                            sexo_cert_a2 = padroniza_texto(dados_a2.get("sexo_crianca", ""))
                                            sexo_form_a2 = padroniza_texto(genero_a2)
                                            
                                            data_cert_str = (dados_a2.get("data_nascimento_crianca") or "").strip()
                                            
                                            if nome_cert_a2 != nome_form_a2:
                                                st.error(f"⚠️ Nome informado não confere com a certidão. Consta: {dados_a2.get('nome_crianca')}")
                                            elif sexo_cert_a2 != sexo_form_a2:
                                                st.error(f"⚠️ O sexo informado não corresponde ao encontrado na certidão.")
                                            elif data_cert_str:
                                                try:
                                                    data_cert_obj = datetime.strptime(data_cert_str, "%d/%m/%Y").date()
                                                    if data_cert_obj != data_nascimento_a2:
                                                        st.error(f"⚠️ A data de nascimento informada não confere com a certidão ({data_cert_str}).")
                                                        data_cert_obj = None
                                                except ValueError:
                                                    data_cert_obj = data_nascimento_a2
                                            else:
                                                data_cert_obj = data_nascimento_a2

                                            if data_cert_obj:
                                                nome_colab = padroniza_texto(st.session_state.colaborador['Nome'])
                                                pais_responsaveis = [padroniza_texto(p) for p in dados_a2.get("nomes_pais_responsaveis", [])]
                                                
                                                if nome_colab not in pais_responsaveis:
                                                    st.error(f"⚠️ O nome do colaborador ({st.session_state.colaborador['Nome']}) não consta como pai/mãe na certidão ou na averbação de adoção.")
                                                else:
                                                    db = SessionLocal()
                                                    try:
                                                        nome_final_a2 = nome_cert_a2 or nome_form_a2
                                                        if verificar_crianca_duplicada(db, nome_final_a2, data_nascimento_a2):
                                                            st.error("❌ Esta criança já está no seu carrinho ou já possui um kit cadastrado. Cada criança pode receber apenas 1 kit.")
                                                        else:
                                                            st.session_state.lista_dependentes.append({
                                                                "ID_Dependente": None,
                                                                "ID_Colaborador": st.session_state.colaborador['Crachá'],
                                                                "Nome_filho": nome_final_a2,
                                                                "Gênero": genero_a2,
                                                                "Data_nascimento": data_nascimento_a2.strftime("%d/%m/%Y"),
                                                                "Escolaridade": st.session_state.escolaridade,
                                                                "Ano_escolar": st.session_state.ano_escolar,
                                                                "revisao_rh": "Sim (Adoção A2)"
                                                            })
                                                            st.success("✅ Dependente adicionado ao carrinho com sucesso!")
                                                            st.session_state.aguardando_decisao = True
                                                            st.rerun()
                                                    finally:
                                                        db.close()

                    # --- SUB-FLUXO A3 FORMULÁRIO ---
                    elif "A3" in sub_opcao_a:
                        with st.form("form_fluxo_a3"):
                            st.info("📌 Requisitos (A3): Envie o **Termo de Guarda e Responsabilidade ou Decisão Judicial** especificando a guarda para fins de adoção.")
                            
                            nome_filho_a3 = st.text_input("Nome Completo da Criança / Adolescente")
                            
                            data_maxima_a3 = date.today() - timedelta(days=730)
                            data_nascimento_a3 = st.date_input("Data de Nascimento da Criança", min_value=date(2000, 1, 1), max_value=data_maxima_a3, format="DD/MM/YYYY")
                            
                            doc_judicial = st.file_uploader("Anexar Documento Judicial (Guarda para Fins de Adoção)", type=["pdf", "png", "jpg", "jpeg"], key="doc_a3")
                            
                            salvar_a3 = st.form_submit_button("Validar e Adicionar ao Carrinho (A3)")

                        if salvar_a3:
                            erros_a3 = []
                            if not nome_filho_a3.strip(): erros_a3.append("O nome da criança é obrigatório.")
                            if not st.session_state.escolaridade: erros_a3.append("A escolaridade é obrigatória.")
                            if not st.session_state.ano_escolar: erros_a3.append("O ano escolar é obrigatório.")
                            if not doc_judicial: erros_a3.append("O documento judicial é obrigatório.")
                                
                            if erros_a3:
                                for e in erros_a3: st.error(f"⚠️ {e}")
                            else:
                                with st.spinner("Analisando documento judicial via IA... Aguarde"):
                                    dados_a3, err_a3 = analisa_guarda_adocao(doc_judicial)
                                    if err_a3:
                                        st.error(f"⚠️ {err_a3}")
                                    else:
                                        if not dados_a3.get("documento_judicial_valido"):
                                            st.error("⚠️ Documento adicionado não possui validade judicial.")
                                        elif not dados_a3.get("legivel_e_autentico"):
                                            st.error("⚠️ Documento ilegível ou sem comprovação de autenticidade.")
                                        elif not dados_a3.get("guarda_para_fins_de_adocao"):
                                            st.error("⚠️ O documento não especifica que a guarda é provisória/definitiva para fins de adoção.")
                                        else:
                                            nome_doc_a3 = padroniza_texto(dados_a3.get("nome_crianca", ""))
                                            nome_form_a3 = padroniza_texto(nome_filho_a3)
                                            
                                            if nome_doc_a3 and nome_doc_a3 not in nome_form_a3 and nome_form_a3 not in nome_doc_a3:
                                                st.error(f"⚠️ O nome da criança no documento judicial ({dados_a3.get('nome_crianca')}) não confere com o informado.")
                                            else:
                                                nome_colab = padroniza_texto(st.session_state.colaborador['Nome'])
                                                guardiao_doc = padroniza_texto(dados_a3.get("nome_guardiao", ""))
                                                
                                                if nome_colab not in guardiao_doc and guardiao_doc not in nome_colab:
                                                    st.error(f"⚠️ O nome do colaborador ({st.session_state.colaborador['Nome']}) não bate com o nome do guardião nomeado no documento ({dados_a3.get('nome_guardiao')}).")
                                                else:
                                                    db = SessionLocal()
                                                    try:
                                                        nome_final_a3 = nome_doc_a3 or nome_form_a3
                                                        if verificar_crianca_duplicada(db, nome_final_a3, data_nascimento_a3):
                                                            st.error("❌ Esta criança já está no seu carrinho ou já possui um kit cadastrado. Cada criança pode receber apenas 1 kit.")
                                                        else:
                                                            st.session_state.lista_dependentes.append({
                                                                "ID_Dependente": None,
                                                                "ID_Colaborador": st.session_state.colaborador['Crachá'],
                                                                "Nome_filho": nome_final_a3,
                                                                "Gênero": "Não informado",
                                                                "Data_nascimento": data_nascimento_a3.strftime("%d/%m/%Y"),
                                                                "Escolaridade": st.session_state.escolaridade,
                                                                "Ano_escolar": st.session_state.ano_escolar,
                                                                "revisao_rh": "Sim (Guarda para Adoção A3)"
                                                            })
                                                            st.success("✅ Dependente adicionado ao carrinho com sucesso!")
                                                            st.session_state.aguardando_decisao = True
                                                            st.rerun()
                                                    finally:
                                                        db.close()

        # =========================================================================
        # CAMINHO B: ENTEADO(A) (REGISTRADO NO NOME DE OUTRA PESSOA)
        # =========================================================================
        elif st.session_state.tipo_fluxo == "B":
            st.subheader("📝 Cadastro de Enteado(a)")
            
            if st.button("⬅️ Voltar e escolher outra opção", key="voltar_b"):
                st.session_state.tipo_fluxo = None
                if 'sub_opcao_b' in st.session_state:
                    del st.session_state['sub_opcao_b']
                st.rerun()
            
            st.write("---")
            sub_opcao_b = st.radio(
                "🎯 Selecione o documento para comprovação do vínculo com o cônjuge/companheiro(a):",
                [
                    "**B1:** Declaração de União Estável + Certidão de Nascimento Filho(a)",
                    "**B2:** Certidão de Casamento + Certidão de Nascimento Filho(a)"
                ],
                index=None,
                key="sub_opcao_b"
            )

            # Só exibe o formulário e a seleção de escolaridade se o usuário clicar
            if sub_opcao_b:
                st.divider()
                if 'escolaridade' not in st.session_state: st.session_state.escolaridade = ""
                if 'ano_escolar' not in st.session_state: st.session_state.ano_escolar = ""

                st.selectbox("Escolaridade", ["", "Educação Infantil", "Ensino Fundamental I", "Ensino Fundamental II", "Ensino Médio"], format_func=lambda x: "Selecione a Escolaridade..." if x == "" else x, key="escolaridade")
                
                opcoes_ano = {
                    "": [],
                    "Educação Infantil":    ["", "Maternal I", "Maternal II", "Etapa I", "Etapa II"],
                    "Ensino Fundamental I": ["", "1º Ano", "2º Ano", "3º Ano", "4º Ano", "5º Ano"],
                    "Ensino Fundamental II":["", "6º Ano", "7º Ano", "8º Ano", "9º Ano"],
                    "Ensino Médio":         ["", "1º Ano", "2º Ano", "3º Ano"]
                }
                
                if st.session_state.escolaridade:
                    st.selectbox("Ano Escolar 2026", opcoes_ano[st.session_state.escolaridade], format_func=lambda x: "Selecione o Ano Escolar..." if x == "" else x, key="ano_escolar")

                # --- FORMA B1 ---
                if "B1" in sub_opcao_b:
                    with st.form("form_fluxo_b1"):
                        st.info("📌 Requisitos : Envie a **Certidão de Nascimento da Criança** e a **Declaração de União Estável** com firma reconhecida .")
                        nome_filho_b = st.text_input("Nome Completo da Criança")
                        genero_b = st.selectbox("Gênero:", ["", "Masculino", "Feminino"], format_func=lambda x: "Selecione o Gênero..." if x == "" else x)
                        data_nascimento_b = st.date_input("Data de Nascimento da Criança", min_value=date(2000, 1, 1), max_value=date.today() - timedelta(days=730), format="DD/MM/YYYY")
                        certidao_b = st.file_uploader("Anexar Certidão de Nascimento", type=["pdf", "png", "jpg", "jpeg"], key="cert_b1")
                        uniao_b = st.file_uploader("Anexar União Estável (com firma reconhecida em SJ Rio Preto)", type=["pdf", "png", "jpg", "jpeg"], key="doc_b1")
                        salvar_b1 = st.form_submit_button("Validar e Adicionar ao Carrinho (B1)")

                    if salvar_b1:
                        erros_b = []
                        if not nome_filho_b.strip(): erros_b.append("O nome da criança é obrigatório.")
                        if not genero_b: erros_b.append("O gênero é obrigatório.")
                        if not st.session_state.escolaridade: erros_b.append("A escolaridade é obrigatória.")
                        if not st.session_state.ano_escolar: erros_b.append("O ano escolar é obrigatório.")
                        if not certidao_b: erros_b.append("A certidão de nascimento é obrigatória.")
                        if not uniao_b: erros_b.append("A declaração de união estável é obrigatória.")
                            
                        if erros_b:
                            for e in erros_b: st.error(f"⚠️ {e}")
                        else:
                            with st.spinner("Analisando documentos com a IA... Aguarde"):
                                dados_cert, err_cert = analisa_certidao(certidao_b)
                                if err_cert:
                                    st.error(f"⚠️ {err_cert}")
                                else:
                                    dados_uniao, err_uniao = analisa_uniao_estavel(uniao_b)
                                    if err_uniao:
                                        st.error(f"⚠️ {err_uniao}")
                                    else:
                                        if not dados_uniao.get("documento_valido"):
                                            st.error("⚠️ O documento anexado não é uma Declaração de União Estável válida.")
                                        elif not dados_uniao.get("firma_reconhecida"):
                                            st.error("⚠️ É NECESSÁRIO RECONHECER FIRMA")
                                        else:
                                            nome_colab = padroniza_texto(st.session_state.colaborador['Nome'])
                                            comp1 = padroniza_texto(dados_uniao.get("nome_companheiro_1", ""))
                                            comp2 = padroniza_texto(dados_uniao.get("nome_companheiro_2", ""))
                                            
                                            if not (nome_colab == comp1 or nome_colab == comp2):
                                                st.error(f"⚠️ O nome do colaborador ({st.session_state.colaborador['Nome']}) não consta como convivente na União Estável apresentada.")
                                            else:
                                                companheiro = comp2 if nome_colab == comp1 else comp1
                                                mae_cert = padroniza_texto(dados_cert.get("nome_mae", ""))
                                                pai_cert = padroniza_texto(dados_cert.get("nome_pai", ""))
                                                
                                                if nome_colab == mae_cert or nome_colab == pai_cert:
                                                    st.error("⚠️ Consta que você é o pai/mãe registrado nesta certidão. Para este caso, utilize a Opção 'A' (Filho biológico ou adotivo).")
                                                elif not (companheiro == mae_cert or companheiro == pai_cert):
                                                    st.error(f"⚠️ O nome do(a) companheiro(a) na União Estável ({companheiro}) não confere com os pais registrados na Certidão de Nascimento da criança ({mae_cert} / {pai_cert}).")
                                                else:
                                                    db = SessionLocal()
                                                    try:
                                                        nome_final_b1 = padroniza_texto(dados_cert.get("nome_crianca") or nome_filho_b)
                                                        if verificar_crianca_duplicada(db, nome_final_b1, data_nascimento_b):
                                                            st.error("❌ Esta criança já está no seu carrinho ou já possui um kit cadastrado. Cada criança pode receber apenas 1 kit.")
                                                        else:
                                                            st.session_state.lista_dependentes.append({
                                                                "ID_Dependente": None,
                                                                "ID_Colaborador": st.session_state.colaborador['Crachá'],
                                                                "Nome_filho": nome_final_b1,
                                                                "Gênero": genero_b,
                                                                "Data_nascimento": data_nascimento_b.strftime("%d/%m/%Y"),
                                                                "Escolaridade": st.session_state.escolaridade,
                                                                "Ano_escolar": st.session_state.ano_escolar,
                                                                "revisao_rh": "Sim (Enteado - União Estável B1)"
                                                            })
                                                            st.success("✅ Dependente adicionado ao carrinho com sucesso!")
                                                            st.session_state.aguardando_decisao = True
                                                            st.rerun()
                                                    finally:
                                                        db.close()

                # --- FORMA B2 ---
                elif "B2" in sub_opcao_b:
                    with st.form("form_fluxo_b2"):
                        st.info("📌 Requisitos (B2): Envie a **Certidão de Nascimento da Criança** e a **Certidão de Casamento** (sem averbação de divórcio).")
                        nome_filho_b2 = st.text_input("Nome Completo da Criança")
                        genero_b2 = st.selectbox("Gênero:", ["", "Masculino", "Feminino"], format_func=lambda x: "Selecione o Gênero..." if x == "" else x)
                        data_nascimento_b2 = st.date_input("Data de Nascimento da Criança", min_value=date(2000, 1, 1), max_value=date.today() - timedelta(days=730), format="DD/MM/YYYY")
                        certidao_b2 = st.file_uploader("Anexar Certidão de Nascimento da Criança", type=["pdf", "png", "jpg", "jpeg"], key="cert_b2")
                        casamento_b2 = st.file_uploader("Anexar Certidão de Casamento", type=["pdf", "png", "jpg", "jpeg"], key="doc_b2")
                        salvar_b2 = st.form_submit_button("Validar e Adicionar ao Carrinho (B2)")

                    if salvar_b2:
                        erros_b2 = []
                        if not nome_filho_b2.strip(): erros_b2.append("O nome da criança é obrigatório.")
                        if not genero_b2: erros_b2.append("O gênero é obrigatório.")
                        if not st.session_state.escolaridade: erros_b2.append("A escolaridade é obrigatória.")
                        if not st.session_state.ano_escolar: erros_b2.append("O ano escolar é obrigatório.")
                        if not certidao_b2: erros_b2.append("A certidão de nascimento é obrigatória.")
                        if not casamento_b2: erros_b2.append("A certidão de casamento é obrigatória.")
                            
                        if erros_b2:
                            for e in erros_b2: st.error(f"⚠️ {e}")
                        else:
                            with st.spinner("Analisando documentos com a IA... Aguarde"):
                                dados_cert, err_cert = analisa_certidao(certidao_b2)
                                if err_cert:
                                    st.error(f"⚠️ {err_cert}")
                                else:
                                    dados_casam, err_casam = analisa_certidao_complementar(casamento_b2)
                                    if err_casam:
                                        st.error(f"⚠️ {err_casam}")
                                    else:
                                        tipo_doc = str(dados_casam.get("tipo_documento", "")).lower()
                                        if not dados_casam.get("documento_valido"):
                                            st.error("⚠️ O documento anexado não é uma Certidão de Casamento válida.")
                                        elif "divórcio" in tipo_doc or "divorcio" in tipo_doc:
                                            st.error("⚠️ Certidão indica divórcio, vínculo inválido.")
                                        else:
                                            nome_colab = padroniza_texto(st.session_state.colaborador['Nome'])
                                            nome_antes = padroniza_texto(dados_casam.get("nome_antes", ""))
                                            nome_depois = padroniza_texto(dados_casam.get("nome_depois", ""))
                                            
                                            if not (nome_colab == nome_antes or nome_colab == nome_depois):
                                                st.error(f"⚠️ O nome do colaborador ({st.session_state.colaborador['Nome']}) não consta na Certidão de Casamento apresentada.")
                                            else:
                                                conjuge = nome_depois if nome_colab == nome_antes else nome_antes
                                                mae_cert = padroniza_texto(dados_cert.get("nome_mae", ""))
                                                pai_cert = padroniza_texto(dados_cert.get("nome_pai", ""))
                                                
                                                if nome_colab == mae_cert or nome_colab == pai_cert:
                                                    st.error("⚠️ Consta que você é o pai/mãe registrado nesta certidão. Para este caso, utilize a Opção 'A' (Filho biológico ou adotivo).")
                                                elif not (conjuge == mae_cert or conjuge == pai_cert or nome_antes == mae_cert or nome_antes == pai_cert or nome_depois == mae_cert or nome_depois == pai_cert):
                                                    st.error(f"⚠️ O nome do(a) cônjuge na Certidão de Casamento não confere com os pais registrados na Certidão de Nascimento ({mae_cert} / {pai_cert}).")
                                                else:
                                                    db = SessionLocal()
                                                    try:
                                                        nome_final_b2 = padroniza_texto(dados_cert.get("nome_crianca") or nome_filho_b2)
                                                        if verificar_crianca_duplicada(db, nome_final_b2, data_nascimento_b2):
                                                            st.error("❌ Esta criança já está no seu carrinho ou já possui um kit cadastrado. Cada criança pode receber apenas 1 kit.")
                                                        else:
                                                            st.session_state.lista_dependentes.append({
                                                                "ID_Dependente": None,
                                                                "ID_Colaborador": st.session_state.colaborador['Crachá'],
                                                                "Nome_filho": nome_final_b2,
                                                                "Gênero": genero_b2,
                                                                "Data_nascimento": data_nascimento_b2.strftime("%d/%m/%Y"),
                                                                "Escolaridade": st.session_state.escolaridade,
                                                                "Ano_escolar": st.session_state.ano_escolar,
                                                                "revisao_rh": "Sim (Enteado - Casamento B2)"
                                                            })
                                                            st.success("✅ Dependente adicionado ao carrinho com sucesso!")
                                                            st.session_state.aguardando_decisao = True
                                                            st.rerun()
                                                    finally:
                                                        db.close()

        # =========================================================================
        # CAMINHO C: CRIANÇA OU ADOLESCENTE SOB GUARDA OU TUTELA (C1 e C2)
        # =========================================================================
        elif st.session_state.tipo_fluxo == "C":
            st.subheader("📝 Cadastro - Criança ou Adolescente sob Guarda ou Tutela")
            
            if st.button("⬅️ Voltar e escolher outra opção", key="voltar_c"):
                st.session_state.tipo_fluxo = None
                if 'sub_opcao_c' in st.session_state:
                    del st.session_state['sub_opcao_c']
                st.rerun()

            st.write("---")
            sub_opcao_c = st.radio(
                "🎯 Selecione o documento judicial de responsabilidade:",
                [
                    "**C1:** Termo/Certidão de Guarda Judicial + Certidão de Nascimento",
                    "**C2:** Termo de Tutela Judicial + Certidão de Nascimento"
                ],
                index=None,
                key="sub_opcao_c"
            )

            if sub_opcao_c:
                st.divider()
                if 'escolaridade' not in st.session_state: st.session_state.escolaridade = ""
                if 'ano_escolar' not in st.session_state: st.session_state.ano_escolar = ""

                st.selectbox("Escolaridade", ["", "Educação Infantil", "Ensino Fundamental I", "Ensino Fundamental II", "Ensino Médio"], format_func=lambda x: "Selecione a Escolaridade..." if x == "" else x, key="escolaridade")
                
                opcoes_ano = {
                    "": [],
                    "Educação Infantil":    ["", "Maternal I", "Maternal II", "Etapa I", "Etapa II"],
                    "Ensino Fundamental I": ["", "1º Ano", "2º Ano", "3º Ano", "4º Ano", "5º Ano"],
                    "Ensino Fundamental II":["", "6º Ano", "7º Ano", "8º Ano", "9º Ano"],
                    "Ensino Médio":         ["", "1º Ano", "2º Ano", "3º Ano"]
                }
                
                if st.session_state.escolaridade:
                    st.selectbox("Ano Escolar 2026", opcoes_ano[st.session_state.escolaridade], format_func=lambda x: "Selecione o Ano Escolar..." if x == "" else x, key="ano_escolar")

                st.write("---")

                # ==================== SUB-FLUXO C1: GUARDA JUDICIAL ====================
                if "C1" in sub_opcao_c:
                    with st.form("form_fluxo_c1"):
                        st.info("📌 Requisitos (C1): Anexe o **Termo/Certidão de Guarda Judicial** E a **Certidão de Nascimento da Criança**.")
                        
                        nome_filho_c1 = st.text_input("Nome Completo da Criança / Adolescente")
                        genero_c1 = st.selectbox("Gênero:", ["", "Masculino", "Feminino"], format_func=lambda x: "Selecione o Gênero..." if x == "" else x, key="genero_c1")
                        
                        data_maxima_c1 = date.today() - timedelta(days=730)
                        data_nascimento_c1 = st.date_input("Data de Nascimento da Criança", min_value=date(2000, 1, 1), max_value=data_maxima_c1, format="DD/MM/YYYY", key="dt_c1")
                        
                        certidao_c1 = st.file_uploader("Anexar Certidão de Nascimento da Criança", type=["pdf", "png", "jpg", "jpeg"], key="cert_c1")
                        termo_guarda_c1 = st.file_uploader("Anexar Termo/Certidão de Guarda Judicial", type=["pdf", "png", "jpg", "jpeg"], key="termo_guarda_c1")
                        
                        salvar_c1 = st.form_submit_button("Validar e Adicionar ao Carrinho (C1)")

                    if salvar_c1:
                        erros_c1 = []
                        if not nome_filho_c1.strip(): erros_c1.append("O nome da criança é obrigatório.")
                        if not genero_c1: erros_c1.append("O gênero é obrigatório.")
                        if not st.session_state.escolaridade: erros_c1.append("A escolaridade é obrigatória.")
                        if not st.session_state.ano_escolar: erros_c1.append("O ano escolar é obrigatório.")
                        if not certidao_c1 or not termo_guarda_c1: erros_c1.append("Documento(s) ausente(s) ou ilegível(is)")
                            
                        if erros_c1:
                            for e in erros_c1: st.error(f"⚠️ {e}")
                        else:
                            with st.spinner("Analisando documentos com a IA... Aguarde"):
                                dados_cert_c1, err_cert_c1 = analisa_certidao(certidao_c1)
                                if err_cert_c1:
                                    st.error(f"⚠️ {err_cert_c1}")
                                else:
                                    valido_cert, msg_cert = valida_dados_crianca_certidao(dados_cert_c1, nome_filho_c1, data_nascimento_c1, genero_c1)
                                    if not valido_cert:
                                        st.error(f"⚠️ {msg_cert}")
                                    else:
                                        dados_guarda, err_guarda = analisa_guarda_judicial(termo_guarda_c1)
                                        if err_guarda:
                                            st.error(f"⚠️ {err_guarda}")
                                        else:
                                            if not dados_guarda.get("documento_valido") or not dados_guarda.get("legivel"):
                                                st.error("⚠️ Documento(s) ausente(s) ou ilegível(is)")
                                            elif not dados_guarda.get("autenticidade_judicial"):
                                                st.error("⚠️ Documento sem comprovação de autenticidade judicial")
                                            else:
                                                nome_crianca_guarda = padroniza_texto(dados_guarda.get("nome_crianca", ""))
                                                nome_crianca_cert = padroniza_texto(dados_cert_c1.get("nome_crianca", ""))
                                                
                                                if nome_crianca_guarda and nome_crianca_guarda not in nome_crianca_cert and nome_crianca_cert not in nome_crianca_guarda:
                                                    st.error(f"⚠️ O nome da criança/adolescente no Termo de Guarda ({dados_guarda.get('nome_crianca')}) não confere com o da Certidão de Nascimento.")
                                                else:
                                                    nome_colab = padroniza_texto(st.session_state.colaborador['Nome'])
                                                    guardiao_doc = padroniza_texto(dados_guarda.get("nome_guardiao", ""))
                                                    
                                                    if nome_colab not in guardiao_doc and guardiao_doc not in nome_colab:
                                                        st.error(f"⚠️ O nome do colaborador ({st.session_state.colaborador['Nome']}) não consta expressamente como o(a) GUARDIÃO(Ã) nomeado(a) no documento judicial ({dados_guarda.get('nome_guardiao')}).")
                                                    else:
                                                        db = SessionLocal()
                                                        try:
                                                            nome_final_c1 = nome_crianca_cert or padroniza_texto(nome_filho_c1)
                                                            if verificar_crianca_duplicada(db, nome_final_c1, data_nascimento_c1):
                                                                st.error("❌ Esta criança já está no seu carrinho ou já possui um kit cadastrado. Cada criança pode receber apenas 1 kit.")
                                                            else:
                                                                st.session_state.lista_dependentes.append({
                                                                    "ID_Dependente": None,
                                                                    "ID_Colaborador": st.session_state.colaborador['Crachá'],
                                                                    "Nome_filho": nome_final_c1,
                                                                    "Gênero": genero_c1,
                                                                    "Data_nascimento": data_nascimento_c1.strftime("%d/%m/%Y"),
                                                                    "Escolaridade": st.session_state.escolaridade,
                                                                    "Ano_escolar": st.session_state.ano_escolar,
                                                                    "revisao_rh": "Sim (Guarda Judicial C1)"
                                                                })
                                                                st.success("✅ Dependente adicionado ao carrinho com sucesso!")
                                                                st.session_state.aguardando_decisao = True
                                                                st.rerun()
                                                        finally:
                                                            db.close()

                # ==================== SUB-FLUXO C2: TUTELA JUDICIAL ====================
                elif "C2" in sub_opcao_c:
                    with st.form("form_fluxo_c2"):
                        st.info("📌 Requisitos (C2): Anexe o **Termo de Tutela Judicial** E a **Certidão de Nascimento da Criança**.")
                        
                        nome_filho_c2 = st.text_input("Nome Completo da Criança / Adolescente")
                        genero_c2 = st.selectbox("Gênero:", ["", "Masculino", "Feminino"], format_func=lambda x: "Selecione o Gênero..." if x == "" else x, key="genero_c2")
                        
                        data_maxima_c2 = date.today() - timedelta(days=730)
                        data_nascimento_c2 = st.date_input("Data de Nascimento da Criança", min_value=date(2000, 1, 1), max_value=data_maxima_c2, format="DD/MM/YYYY", key="dt_c2")
                        
                        certidao_c2 = st.file_uploader("Anexar Certidão de Nascimento da Criança", type=["pdf", "png", "jpg", "jpeg"], key="cert_c2")
                        termo_tutela_c2 = st.file_uploader("Anexar Termo de Tutela Judicial", type=["pdf", "png", "jpg", "jpeg"], key="termo_tutela_c2")
                        
                        salvar_c2 = st.form_submit_button("Validar e Adicionar ao Carrinho (C2)")

                    if salvar_c2:
                        erros_c2 = []
                        if not nome_filho_c2.strip(): erros_c2.append("O nome da criança é obrigatório.")
                        if not genero_c2: erros_c2.append("O gênero é obrigatório.")
                        if not st.session_state.escolaridade: erros_c2.append("A escolaridade é obrigatória.")
                        if not st.session_state.ano_escolar: erros_c2.append("O ano escolar é obrigatório.")
                        if not certidao_c2 or not termo_tutela_c2: erros_c2.append("Documento(s) ausente(s) ou ilegível(is)")
                            
                        if erros_c2:
                            for e in erros_c2: st.error(f"⚠️ {e}")
                        else:
                            with st.spinner("Analisando documentos com a IA... Aguarde"):
                                dados_cert_c2, err_cert_c2 = analisa_certidao(certidao_c2)
                                if err_cert_c2:
                                    st.error(f"⚠️ {err_cert_c2}")
                                else:
                                    valido_cert_c2, msg_cert_c2 = valida_dados_crianca_certidao(dados_cert_c2, nome_filho_c2, data_nascimento_c2, genero_c2)
                                    if not valido_cert_c2:
                                        st.error(f"⚠️ {msg_cert_c2}")
                                    else:
                                        dados_tutela, err_tutela = analisa_tutela_judicial(termo_tutela_c2)
                                        if err_tutela:
                                            st.error(f"⚠️ {err_tutela}")
                                        else:
                                            if not dados_tutela.get("documento_valido") or not dados_tutela.get("legivel"):
                                                st.error("⚠️ Documento(s) ausente(s) ou ilegível(is)")
                                            elif not dados_tutela.get("autenticidade_judicial"):
                                                st.error("⚠️ Documento sem comprovação de autenticidade judicial")
                                            else:
                                                nome_crianca_tutela = padroniza_texto(dados_tutela.get("nome_crianca", ""))
                                                nome_crianca_cert_c2 = padroniza_texto(dados_cert_c2.get("nome_crianca", ""))
                                                
                                                if nome_crianca_tutela and nome_crianca_tutela not in nome_crianca_cert_c2 and nome_crianca_cert_c2 not in nome_crianca_tutela:
                                                    st.error(f"⚠️ O nome da criança/adolescente no Termo de Tutela ({dados_tutela.get('nome_crianca')}) não confere com o da Certidão de Nascimento.")
                                                else:
                                                    nome_colab = padroniza_texto(st.session_state.colaborador['Nome'])
                                                    tutor_doc = padroniza_texto(dados_tutela.get("nome_tutor", ""))
                                                    
                                                    if nome_colab not in tutor_doc and tutor_doc not in nome_colab:
                                                        st.error(f"⚠️ O nome do colaborador ({st.session_state.colaborador['Nome']}) não consta expressamente como o(a) TUTOR(A) nomeado(a) no documento judicial ({dados_tutela.get('nome_tutor')}).")
                                                    else:
                                                        db = SessionLocal()
                                                        try:
                                                            nome_final_c2 = nome_crianca_cert_c2 or padroniza_texto(nome_filho_c2)
                                                            if verificar_crianca_duplicada(db, nome_final_c2, data_nascimento_c2):
                                                                st.error("❌ Esta criança já está no seu carrinho ou já possui um kit cadastrado. Cada criança pode receber apenas 1 kit.")
                                                            else:
                                                                st.session_state.lista_dependentes.append({
                                                                    "ID_Dependente": None,
                                                                    "ID_Colaborador": st.session_state.colaborador['Crachá'],
                                                                    "Nome_filho": nome_final_c2,
                                                                    "Gênero": genero_c2,
                                                                    "Data_nascimento": data_nascimento_c2.strftime("%d/%m/%Y"),
                                                                    "Escolaridade": st.session_state.escolaridade,
                                                                    "Ano_escolar": st.session_state.ano_escolar,
                                                                    "revisao_rh": "Sim (Tutela Judicial C2)"
                                                                })
                                                                st.success("✅ Dependente adicionado ao carrinho com sucesso!")
                                                                st.session_state.aguardando_decisao = True
                                                                st.rerun()
                                                        finally:
                                                            db.close()
interface()                    