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
from supabase import create_client
from notificador_email import NotificadorEmail, SMTP_SERVER, SMTP_PORT, LOGIN_SMTP, SENHA_KEY, EMAIL_REMETENTE
from query import CARGOS_REJEIATO, DOMINIOS_PESSOAIS_PERMITIDOS

MODELOS_GEMINI = [
    "gemini-2.5-flash",        # 1ª Opção: Principal (Rápido e alta performance)
    "gemini-1.5-flash",        # 2ª Opção: Backup super estável
    "gemini-3.1-flash-lite",   # 3ª Opção: Terceira alternativa
]
   
load_dotenv()
client_gemini = genai.Client()

# ==================== SUPABASE STORAGE (QR CODES) ====================


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
# ---------------------------------------------------------------
# CONFIGURAÇÃO DE IA: DECLARAÇÃO ESCOLAR / MATRÍCULA
# ---------------------------------------------------------------
generation_config_declaracao_escolar = types.GenerateContentConfig(
    temperature=0,
    response_mime_type="application/json",
    system_instruction=(
        "Você é um assistente rigoroso de auditoria de documentos escolares brasileiros.\n"
        "Regra 1: Verifique se o documento é uma Declaração de Matrícula, Declaração Escolar de Matrícula ou documento escolar equivalente que comprove que o aluno está matriculado. Retorne 'eh_declaracao_matricula' como true somente quando houver evidência clara de matrícula.\n"
        "Regra 2: Verifique se o documento está legível. Se estiver borrado, cortado, muito escuro ou ilegível a ponto de não permitir uma extração segura, retorne 'legivel' como false.\n"
        "Regra 3: Extraia SOMENTE o nome do aluno exatamente como aparece no documento, sem inventar ou completar informações. O nome pode estar abreviado, conter iniciais ou nomes intermediários abreviados.\n"
        "Regra 4: NÃO extraia data, ano letivo ou qualquer outra informação que não seja necessária para confirmar que o documento é uma declaração de matrícula e identificar o nome do aluno.\n"
        "OBS: NÃO DAR RESPOSTA EXPLICATIVA"
    ),
    response_schema={
        "type": "OBJECT",
        "properties": {
            "legivel": {"type": "BOOLEAN"},
            "eh_declaracao_matricula": {"type": "BOOLEAN"},
            "nome_aluno": {"type": "STRING"}
        },
        "required": ["legivel", "eh_declaracao_matricula", "nome_aluno"]
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
generation_config_uniao_estavel = types.GenerateContentConfig(
    temperature=0,
    response_mime_type="application/json",
    system_instruction=(
        "Você é um assistente rigoroso de auditoria de documentos civis (Declaração de União Estável).\n"
        "Regra 1: Verifique se o documento é uma Declaração ou Escritura Pública de União Estável válida. Classifique 'documento_valido' como true ou false.\n"
        "Regra 2: Verifique se o documento possui carimbo, selo digital, etiqueta ou menção explícita de 'reconhecimento de firma' em cartório. Se não houver, classifique 'firma_reconhecida' como false.\n"
        "Regra 3: O reconhecimento de firma pode ser de QUALQUER cartório do Brasil (sem restrição de cidade). Classifique 'cartorio_valido' como true se possuir validação de cartório.\n"
        "Regra 4 (EXTREMA IMPORTÂNCIA): Extraia **APENAS o nome completo** dos dois conviventes/companheiros nos campos 'nome_companheiro_1' e 'nome_companheiro_2'. NÃO inclua números, RGs, CPFs, endereços. DICA CRUCIAL: Caso os nomes preenchidos à mão no corpo do texto estejam ilegíveis, procure obrigatoriamente no carimbo/selo do cartório (geralmente na parte inferior), pois o selo de reconhecimento de firma por semelhança sempre contém os nomes impressos de forma perfeitamente legível.\n"
        "OBS: NÃO DAR RESPOSTA EXPLICATIVA"
    ),
    response_schema={
        "type": "OBJECT",
        "properties": {
            "documento_valido": {"type": "BOOLEAN"},
            "firma_reconhecida": {"type": "BOOLEAN"},
            "cartorio_valido": {"type": "BOOLEAN"},
            "nome_companheiro_1": {"type": "STRING"},
            "nome_companheiro_2": {"type": "STRING"}
        },
        "required": ["documento_valido", "firma_reconhecida", "cartorio_valido", "nome_companheiro_1", "nome_companheiro_2"]
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

def nomes_correspondem_com_abreviacao(nome_a: str, nome_b: str) -> bool:
    """Compara nomes aceitando iniciais/abreviações e nomes intermediários omitidos."""
    def tokens(nome):
        nome = padroniza_texto(nome or "")
        return [t for t in nome.split() if t]

    a = tokens(nome_a)
    b = tokens(nome_b)
    if not a or not b:
        return False

    # O primeiro e o último nome precisam corresponder; isso reduz falsos positivos.
    def token_compativel(x, y):
        if x == y:
            return True
        if len(x) == 1:
            return y.startswith(x)
        if len(y) == 1:
            return x.startswith(y)
        # Abreviações como "FERNAN." / "FERNANDA" também são aceitas.
        return x.startswith(y) or y.startswith(x)

    if not token_compativel(a[0], b[0]) or not token_compativel(a[-1], b[-1]):
        return False

    # Faz correspondência em ordem. Assim "JOAO P SILVA" bate com
    # "JOAO PEDRO SILVA", mas nomes de pessoas diferentes não passam apenas
    # por terem uma palavra em comum.
    i = 0
    for token_a in a:
        encontrado = False
        while i < len(b):
            if token_compativel(token_a, b[i]):
                encontrado = True
                i += 1
                break
            i += 1
        if not encontrado:
            return False
    return True


def valida_declaracao_escolar(dados_declaracao: dict, nome_certidao: str):
    """Valida se o documento é uma declaração de matrícula e se o nome confere com a certidão."""
    if not dados_declaracao:
        return False, "❌ Não foi possível analisar a declaração escolar."

    if dados_declaracao.get("legivel") is False:
        return False, "❌ A declaração escolar está ilegível. Envie outro arquivo."

    if not dados_declaracao.get("eh_declaracao_matricula"):
        return False, "❌ O documento não comprova que o aluno está matriculado."

    nome_declaracao = (dados_declaracao.get("nome_aluno") or "").strip()
    if not nome_declaracao:
        return False, "❌ Não foi possível identificar o nome do aluno na declaração escolar."

    if not nomes_correspondem_com_abreviacao(nome_declaracao, nome_certidao):
        return False, (
            f"❌ O nome da declaração escolar ({nome_declaracao}) não corresponde ao nome da certidão "
            f"({nome_certidao})."
        )

    return True, f"✅ Declaração de matrícula válida: o nome ({nome_declaracao}) corresponde ao nome da certidão."


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

# =========================================================================
# CONFIGURAÇÃO DE MODELOS E RESILIÊNCIA DA IA (3 MODELOS EM FALLBACK)
# =========================================================================
MODELOS_GEMINI = [
    "gemini-2.5-flash",        # 1ª Opção: Principal (Rápido e alta performance)
    "gemini-1.5-flash",        # 2ª Opção: Backup super estável
    "gemini-3.1-flash-lite",   # 3ª Opção: Terceira alternativa
]

# =========================================================================
# CONFIGURAÇÃO DE MODELOS E RESILIÊNCIA DA IA (3 MODELOS EM FALLBACK)
# =========================================================================
MODELOS_GEMINI = [
    "gemini-2.5-flash",        # 1ª Opção: Principal (Rápido e alta performance)
    "gemini-1.5-flash",        # 2ª Opção: Backup super estável
    "gemini-3.1-flash-lite",   # 3ª Opção: Terceira alternativa
]

def executar_gemini_com_fallback(contents_data, config_schema, tentativas_por_modelo=2):
    """
    Executa chamadas à API alternando sequencialmente por até 3 modelos.
    Se o 1º falhar 2x -> tenta o 2º. Se o 2º falhar 2x -> tenta o 3º.
    """
    ERROS_RETRY = ("503", "unavailable", "timeout", "timed out", "429", "high demand", "disconnected", "remoteprotocolerror", "reset")

    for modelo in MODELOS_GEMINI:
        for tentativa in range(1, tentativas_por_modelo + 1):
            try:
                print(f"🤖 [IA Studio] Testando modelo '{modelo}' (Tentativa {tentativa}/{tentativas_por_modelo})...")
                
                response = client_gemini.models.generate_content(
                    model=modelo,
                    contents=contents_data,
                    config=config_schema,
                )
                
                texto_limpo = response.text.strip()
                dados_json = json.loads(texto_limpo)
                
                print(f"✅ Sucesso na leitura usando o modelo '{modelo}'!")
                return dados_json, None

            except json.JSONDecodeError:
                return None, "⚠️ Resposta da IA em formato inesperado. Tente novamente."

            except Exception as e:
                erro_str = str(e).lower()
                print(f"🔍 ERRO CAPTURADO [{modelo}]: {repr(e)}")

                tem_retry = any(cod in erro_str for cod in ERROS_RETRY)
                if tem_retry and tentativa < tentativas_por_modelo:
                    tempo_espera = tentativa * 3  # Espera 3 segundos no retry
                    print(f"⏳ Servidor ocupado. Aguardando {tempo_espera}s...")
                    time.sleep(tempo_espera)
                    continue
                elif tem_retry:
                    print(f"🚨 Modelo '{modelo}' indisponível. Alternando para a próxima opção da lista...")
                    break  # Pula imediatamente para o próximo modelo de MODELOS_GEMINI
                else:
                    return None, "⚠️ Erro inesperado no processamento do documento."

    # Se passar por TODOS os 3 modelos e nenhum responder:
    return None, "⚠️ Todos os serviços de IA estão com alta demanda momentânea. Por favor, tente novamente em alguns instantes."


def analisa_certidao(arquivo):
    try:
        arquivo.seek(0)
        arquivo_bytes = arquivo.read()
        mime_type = arquivo.type
        contents = [
            types.Part.from_bytes(data=arquivo_bytes, mime_type=mime_type),
            "Analise o documento e retorne os dados no formato estruturado."
        ]
        return executar_gemini_com_fallback(contents, generation_config_certidao)
    except Exception:
        return None, "Erro ao ler o arquivo. Tente fazer o upload novamente."

def analisa_declaracao_escolar(arquivo):
    try:
        arquivo.seek(0)
        arquivo_bytes = arquivo.read()
        mime_type = arquivo.type
        contents = [
            types.Part.from_bytes(data=arquivo_bytes, mime_type=mime_type),
            "Analise esta declaração escolar e extraia os dados conforme as regras."
        ]
        return executar_gemini_com_fallback(contents, generation_config_declaracao_escolar)
    except Exception:
        return None, "Erro ao ler a declaração escolar. Tente fazer o upload novamente."


def analisa_uniao_estavel(arquivo):
    try:
        arquivo.seek(0)
        arquivo_bytes = arquivo.read()
        mime_type = arquivo.type
        contents = [
            types.Part.from_bytes(data=arquivo_bytes, mime_type=mime_type),
            "Analise esta declaração de união estável e extraia os dados conforme as regras."
        ]
        return executar_gemini_com_fallback(contents, generation_config_uniao_estavel)
    except Exception:
        return None, "Erro ao ler o arquivo de união estável."

def analisa_guarda_adocao(arquivo):
    try:
        arquivo.seek(0)
        arquivo_bytes = arquivo.read()
        mime_type = arquivo.type
        contents = [
            types.Part.from_bytes(data=arquivo_bytes, mime_type=mime_type),
            "Analise este documento judicial de guarda para fins de adoção e extraia os dados conforme as regras."
        ]
        return executar_gemini_com_fallback(contents, generation_config_guarda_adocao)
    except Exception:
        return None, "Erro ao ler o arquivo de guarda para adoção."

def analisa_certidao_averbacao(arquivo):
    try:
        arquivo.seek(0)
        arquivo_bytes = arquivo.read()
        mime_type = arquivo.type
        contents = [
            types.Part.from_bytes(data=arquivo_bytes, mime_type=mime_type),
            "Analise esta certidão de nascimento com averbação de adoção e extraia os dados conforme as regras."
        ]
        return executar_gemini_com_fallback(contents, generation_config_adocao_averbacao)
    except Exception:
        return None, "Erro ao ler a certidão averbada."
def analisa_guarda_judicial(arquivo):
    try:
        arquivo.seek(0)
        arquivo_bytes = arquivo.read()
        mime_type = arquivo.type
        contents = [
            types.Part.from_bytes(data=arquivo_bytes, mime_type=mime_type),
            "Analise este termo ou certidão de guarda judicial e extraia os dados conforme as regras."
        ]
        return executar_gemini_com_fallback(contents, generation_config_guarda_judicial)
    except Exception:
        return None, "Documento(s) ausente(s) ou ilegível(is)"

def analisa_tutela_judicial(arquivo):
    try:
        arquivo.seek(0)
        arquivo_bytes = arquivo.read()
        mime_type = arquivo.type
        contents = [
            types.Part.from_bytes(data=arquivo_bytes, mime_type=mime_type),
            "Analise este termo de tutela judicial e extraia os dados conforme as regras."
        ]
        return executar_gemini_com_fallback(contents, generation_config_tutela_judicial)
    except Exception:
        return None, "Documento(s) ausente(s) ou ilegível(is)"

def analisa_certidao_complementar(arquivo):
    try:
        arquivo.seek(0)
        arquivo_bytes = arquivo.read()
        mime_type = arquivo.type
        contents = [
            types.Part.from_bytes(data=arquivo_bytes, mime_type=mime_type),
            "Analise o documento e retorne os dados no formato estruturado."
        ]
        return executar_gemini_com_fallback(contents, generation_config_doc_complementar)
    except Exception:
        return None, "Erro ao ler o arquivo de casamento/divórcio."


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
        if colaborador:
            print(f"DEBUG -> id_cargo bruto: {repr(colaborador['id_cargo'])} | tipo: {type(colaborador['id_cargo'])}")
        
        if not colaborador:
            st.error("⚠️ Crachá não encontrado na base de dados.")
            st.session_state.colaborador = None  # Reseta o estado para bloquear a tela seguinte
            return None
            
        if colaborador["descricao_situacao"] in situacoes_invalidas:
            st.error(f"⚠️ Colaborador não elegível. Situação atual: {colaborador['descricao_situacao']}")
            st.session_state.colaborador = None  # Reseta o estado para bloquear a tela seguinte
            return None

        # ==================== NOVA VALIDAÇÃO DE CARGOS REJEITADOS ====================
        if str(colaborador["id_cargo"]) in CARGOS_REJEIATO:
            st.error(
                "🎁 O Kit Escolar é uma iniciativa de apoio social direcionada a categorias específicas "
                "da nossa instituição e, por isso, não está disponível para o seu cargo. "
                "Agradecemos muito pela compreensão!"
            )
            st.session_state.colaborador = None  # Reseta o estado para bloquear a tela seguinte
            return None
            
        # ==================== SALVA NO SESSION_STATE ====================
        st.session_state.colaborador = {
            "id": colaborador["cracha"],
            "Crachá": colaborador["cracha"],
            "Nome": colaborador["nome"],
            "Título Reduzido (Cargo)": colaborador["titulo_reduzido_cargo"],
            "Descrição (Situação)": colaborador["descricao_situacao"],
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


def eh_email_pessoal(email: str) -> bool:
    """Retorna True se o domínio do e-mail estiver na lista de provedores pessoais aceitos."""
    partes = email.strip().lower().split("@")
    if len(partes) != 2:
        return False
    return partes[1] in DOMINIOS_PESSOAIS_PERMITIDOS


def adiciona_dados_contato():
    print("Adicionando dados de contato...")
    with st.form("form_contato"):
        st.subheader("📞 Dados de Contato")
        
        email = st.text_input("E-mail", placeholder="rh_4.0-@gmail.com")
        confirmacao_email = st.text_input("Confirme o E-mail", placeholder="rh_4.0-@gmail.com")
            
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
    elif not eh_email_pessoal(email_digitado):
        erros.append(
            "⚠️ Utilize um e-mail pessoal (Gmail, Hotmail, Outlook, Yahoo, iCloud, etc). "
            "Não é possível enviar o QR Code para e-mails corporativos."
        )

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
        declaracao_escolar = st.file_uploader(
            "Anexar Declaração Escolar de Matrícula 📚",
            type=["pdf", "png", "jpg", "jpeg"],
            key="declaracao_escolar_a1",
            help="A declaração deve comprovar a matrícula e informar o nome do aluno."
        )
        
        st.divider()
        # 🔒  CHECKBOXES DE COMPLIANCE 
        aceite_ia = st.checkbox("Estou ciente de que os documentos enviados serão processados e analisados automaticamente por inteligência artificial para fins de validação cadastral.", key="ia_dep")
        aceite_lgpd = st.checkbox("Concordo com o tratamento, armazenamento e uso dos dados para a concessão do Kit Escolar, em conformidade com a LGPD e as normas de compliance da instituição.", key="lgpd_dep")
        
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
    if not declaracao_escolar:
        erros.append("❌ Declaração escolar de matrícula é obrigatória.")
    if not aceite_ia or not aceite_lgpd:
        erros.append("❌ Você deve aceitar os termos de uso de IA e a política de privacidade (LGPD) para prosseguir.")

    if erros:
        for x in erros:
            st.error(x)
        return None

    db = SessionLocal()
    try:
        # 1. Validação cruzada de duplicidade (Carrinho + Banco)
        if verificar_crianca_duplicada(db, nome_filho, data_nascimento):
            st.error("❌ Esta criança já está no seu carrinho ou já possui um kit cadastrado.")
            return None

        # 2. Análise da certidão com Gemini
        with st.spinner("🔍 Analisando certidão de nascimento, aguarde..."):
            dados_certidao, erro_api = analisa_certidao(certidao)
        
        if erro_api:
            st.error(erro_api)
            return None

        # 3. Tratamento para documento ilegível ou inválido
        if not dados_certidao.get("legivel", True) or not dados_certidao.get("documento_valido", True):
            st.error("❌ Documento ilegível, mande outro arquivo")
            return None

        # 4. Validações dos dados da criança na certidão
        dados_ok, msg_dados = valida_dados_crianca_certidao(dados_certidao, nome_filho, data_nascimento, genero)
        if not dados_ok:
            st.error(msg_dados)
            return None

        # 5. VALIDAÇÃO DA DECLARAÇÃO ESCOLAR
        with st.spinner("📚 Validando declaração escolar e correspondência do nome... Aguarde"):
            dados_declaracao, erro_declaracao = analisa_declaracao_escolar(declaracao_escolar)

        if erro_declaracao:
            st.error(erro_declaracao)
            return None

        declaracao_ok, msg_declaracao = valida_declaracao_escolar(
            dados_declaracao, dados_certidao.get("nome_crianca") or nome_filho
        )
        if not declaracao_ok:
            st.error(msg_declaracao)
            return None
        st.success(msg_declaracao)

        # 6. VALIDAÇÃO RÍGIDA DO NOME DOS PAIS (BLOQUEIO OBRIGATÓRIO SE NÃO BATER)
        valido, mensagem = valida_nome_pais_certidao(
            dados_certidao, st.session_state.colaborador['Nome']
        )

        if not valido:
            st.error(f"⚠️ O nome do colaborador ({st.session_state.colaborador['Nome']}) não consta como pai/mãe na certidão de nascimento enviada.")
            return None
        else:
            st.success(mensagem)

        # Retorna o dicionário para ser inserido puramente no carrinho (Session State)
        nome_final = padroniza_texto(dados_certidao.get("nome_crianca") or nome_filho)
        return {
            "ID_Dependente": None,
            "ID_Colaborador": st.session_state.colaborador['Crachá'],
            "Nome_filho": nome_final,
            "Gênero": genero,
            "Data_nascimento": data_nascimento.strftime("%d/%m/%Y"),
            "Escolaridade": st.session_state.escolaridade,
            "Ano_escolar": st.session_state.ano_escolar,
            "revisao_rh": "Não",
            "Fluxo_Documento": "A1 - Certidão de Nascimento + Declaração Escolar de Matrícula (Filho Biológico)",
            "aceite_ia": aceite_ia,
            "aceite_lgpd": aceite_lgpd,
            "data_aceite": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    finally:
        db.close()


def ficha_colaborador():
    print("Exibindo ficha do colaborador...")
    # Código para exibir a ficha do colaborador
    # Exemplo: renderização de interface, exibição de dados, etc.
    pass

#---------------------------------------------------FUNCOES DE VALIDACAO input
def editar_kits_existentes(id_colaborador):
    st.subheader("🎒 Seus Dependentes e Kits Cadastrados")
    st.write("Caso queira, você pode alterar o modelo do kit escolhido abaixo:")

    db = SessionLocal()
    try:
        dependentes = db.query(Dependente).filter(Dependente.id_colaborador == id_colaborador).all()
        catalogo, base_url = catalogo_kits_por_escolaridade()
        
        # Injeção de CSS para padronizar altura das imagens do catálogo
        st.markdown("""
            <style>
            div[data-testid="stColumn"] img {
                height: 180px !important;
                object-fit: contain !important;
            }
            </style>
        """, unsafe_allow_html=True)

        info_dependentes = []
        with st.form("form_edicao_kits"):
            for dep in dependentes:
                st.markdown(f"### 👦/👧 {dep.nome_filho}")
                st.write(f"**Escolaridade:** {dep.escolaridade} | **Ano escolar:** {dep.ano_escola} | **Nasc:** {dep.data_nascimento.strftime('%d/%m/%Y')}")

                escolha_atual = db.query(EscolhaKit).filter(EscolhaKit.id_dependente == dep.id_dependente).first()
                kit_atual = escolha_atual.kit_escolhido if escolha_atual else ""

                opcoes_kits = catalogo.get(dep.escolaridade, [])

                # Vitrine visual de kits — 1 checkbox por imagem
                if opcoes_kits:
                    st.markdown("**Catálogo Disponível — marque o kit desejado:**")
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
                                    st.checkbox(
                                        nome_kit,
                                        value=(nome_kit == kit_atual),
                                        key=f"edit_chk_kit_{dep.id_dependente}_{nome_kit}"
                                    )

                st.write("---")

                info_dependentes.append({
                    "id_dependente": dep.id_dependente,
                    "nome_filho": dep.nome_filho,
                    "escolaridade": dep.escolaridade,
                    "opcoes_kits": opcoes_kits
                })

            salvar_edicao = st.form_submit_button("💾 Salvar Alterações de Kit")

        if salvar_edicao:
            # Apura, para cada dependente, qual(is) checkbox(es) ficaram marcados
            erros = []
            selecoes = {}
            for info in info_dependentes:
                id_dependente = info["id_dependente"]
                marcados = [
                    nome_kit for nome_kit in info["opcoes_kits"]
                    if st.session_state.get(f"edit_chk_kit_{id_dependente}_{nome_kit}")
                ]

                if len(marcados) == 0:
                    erros.append(f"⚠️ Selecione um kit para {info['nome_filho']}.")
                    continue
                if len(marcados) > 1:
                    erros.append(f"⚠️ Selecione apenas um kit para {info['nome_filho']} (mais de um foi marcado).")
                    continue

                selecoes[id_dependente] = marcados[0]

            if erros:
                for erro in erros:
                    st.error(erro)
                return

            houve_alteracao = False
            resumo_novos_kits = []

            for dep in dependentes:
                novo_kit_selecionado = selecoes[dep.id_dependente]
                escolha_db = db.query(EscolhaKit).filter(EscolhaKit.id_dependente == dep.id_dependente).first()
                
                if escolha_db:
                    if escolha_db.kit_escolhido != novo_kit_selecionado:
                        escolha_db.kit_escolhido = novo_kit_selecionado
                        houve_alteracao = True
                    resumo_novos_kits.append(f"{dep.nome_filho} - {dep.escolaridade} - {novo_kit_selecionado}")

            if houve_alteracao:
                # Atualiza o resumo na tabela retiradas
                novo_resumo_str = " | ".join(resumo_novos_kits)
                retirada_db = db.query(Retirada).filter(Retirada.id_colaborador == id_colaborador).first()
                if retirada_db:
                    retirada_db.resumo_kits = novo_resumo_str
                
                db.commit()
                
                # Armazena a mensagem de sucesso na sessão para exibir na tela inicial
                st.session_state.mensagem_sucesso = "✅ Kit atualizado com sucesso!"
                
                # Reseta a sessão para voltar ao estado inicial (Busca por crachá)
                st.session_state.colaborador = None
                st.session_state.contato = None
                st.session_state.tipo_fluxo = None
                st.session_state.lista_dependentes = []
                st.session_state.aguardando_decisao = False
                st.session_state.cadastro_finalizado = False
                st.session_state.escolhendo_kits = False
                st.session_state.escolhas_kits = []
                
                st.rerun()
            else:
                st.info("Nenhuma alteração de kit foi detectada.")
    finally:
        db.close()

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
        if st.button("A) Filho(a)", width='stretch'):
            st.session_state.tipo_fluxo = "A"
            st.rerun()
            
    with col2:
        if st.button("B) Enteado(a) (Registrado no nome do cônjuge/companheiro)", width='stretch'):
            st.session_state.tipo_fluxo = "B"
            st.rerun()
            
    with col3:
        if st.button("C) Criança ou Adolescente sob Guarda ou Tutela", width='stretch'):
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

    # ===================== ETAPA 2: CIÊNCIA SOBRE VARIAÇÃO DE MODELO/ESTOQUE =====================
    if st.session_state.aguardando_ciencia_kits:
        st.warning(
            "⚠️As mochilas apresentadas possuem variações de cores e, em alguns casos, "
            "diferentes opções de acabamento.\n\n"
            "A distribuição estará condicionada ao estoque disponível na data de entrega. "
            "Caso o modelo escolhido não esteja disponível, será fornecida outra opção disponível."
        )

        ciente = st.checkbox("Estou ciente", key="chk_ciencia_variacao_kit")
        confirmar_ciencia = st.button("✅ Confirmar Ciência e Finalizar Escolha", key="btn_confirma_ciencia_kit")

        if confirmar_ciencia:
            if not ciente:
                st.error("⚠️ Você precisa marcar 'Estou ciente' para prosseguir.")
                return None

            db = SessionLocal()
            try:
                data_aceite = datetime.now()
                novas_escolhas = []
                for escolha in st.session_state.escolhas_pendentes_kits:
                    nova_escolha = EscolhaKit(
                        id_colaborador=escolha["ID_Colaborador"],
                        id_dependente=escolha["ID_Dependente"],
                        kit_escolhido=escolha["Kit_Escolhido"],
                        aceite_variacao_kit=True,          # 🚨 requer coluna nova em EscolhaKit
                        data_aceite_variacao=data_aceite    # 🚨 requer coluna nova em EscolhaKit
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
                st.session_state.aguardando_ciencia_kits = False
                st.session_state.escolhas_pendentes_kits = []
                st.success("🎉 Kits escolhidos com sucesso!")
                return novas_escolhas
            finally:
                db.close()

        return None

    # ===================== ETAPA 1: SELEÇÃO DOS KITS (CHECKBOX POR IMAGEM) =====================
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

        info_dependentes = []
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
                # VITRINE VISUAL DE KITS — 1 CHECKBOX POR IMAGEM
                # ========================================================
                st.markdown("**Catálogo Disponível — marque o kit desejado:**")
                
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
                                st.checkbox(nome_kit, key=f"chk_kit_{id_dependente}_{nome_kit}")
                
                st.write("---")
                # ========================================================

                info_dependentes.append({
                    "ID_Dependente": id_dependente,
                    "ID_Colaborador": id_colaborador,
                    "Nome_filho": nome_filho,
                    "Gênero": genero,
                    "Escolaridade": escolaridade,
                    "Ano_escolar": ano_escolar,
                    "Opcoes_kits": opcoes_kits
                })
                
            salvar_escolhas = st.form_submit_button("✅ Confirmar escolha dos kits")
            
        if not salvar_escolhas:
            return None

        # Apura, para cada dependente, qual(is) checkbox(es) ficaram marcados
        escolhas = []
        erros = []
        for info in info_dependentes:
            id_dependente = info["ID_Dependente"]
            marcados = [
                nome_kit for nome_kit in info["Opcoes_kits"]
                if st.session_state.get(f"chk_kit_{id_dependente}_{nome_kit}")
            ]

            if len(marcados) == 0:
                erros.append(f"⚠️ Selecione um kit para {info['Nome_filho']}.")
                continue
            if len(marcados) > 1:
                erros.append(f"⚠️ Selecione apenas um kit para {info['Nome_filho']} (mais de um foi marcado).")
                continue

            escolhas.append({
                "ID_Dependente": id_dependente,
                "ID_Colaborador": info["ID_Colaborador"],
                "Nome_filho": info["Nome_filho"],
                "Gênero": info["Gênero"],
                "Escolaridade": info["Escolaridade"],
                "Ano_escolar": info["Ano_escolar"],
                "Kit_Escolhido": marcados[0]
            })

        if erros:
            for erro in erros:
                st.error(erro)
            return None

        # Guarda as escolhas e avança para a etapa de ciência (Etapa 2)
        st.session_state.escolhas_pendentes_kits = escolhas
        st.session_state.aguardando_ciencia_kits = True
        st.rerun()

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


def salvar_qrcode_bucket(buffer_qrcode: BytesIO, cracha: str) -> str | None:
    """Faz upload do QR Code para o bucket do Supabase, usando o crachá como nome do arquivo."""

    SUPABASE_URL = os.getenv("SUPABASE_URL") 
    SUPABASE_KEY = os.getenv("SUPABASE_KEY") 
    BASE_URL_QRCODE = os.getenv("BASE_URL_QRCODE") 

    
    supabase_storage = create_client(SUPABASE_URL, SUPABASE_KEY)
    BUCKET_QRCODES = "QRCODE"

    nome_arquivo = f"{cracha}.png"
    buffer_qrcode.seek(0)
    
    try:
        supabase_storage.storage.from_(BUCKET_QRCODES).upload(
            path=nome_arquivo,
            file=buffer_qrcode.read(),
            file_options={"content-type": "image/png", "upsert": "true"}
        )
        # Monta o link perfeitamente: url_pasta + nome_do_arquivo
        return f"{BASE_URL_QRCODE}{nome_arquivo}"
        
    except Exception as e:
        print(f"❌ Erro ao salvar QR Code no bucket do Supabase: {e}")
        return None
    finally:
        buffer_qrcode.seek(0)


def enviar_qrcode_por_email(email_destino: str, buffer_qrcode: BytesIO, cracha: str) -> bool:
    """Envia o QR Code de retirada por e-mail ao colaborador."""
    notificador = NotificadorEmail(SMTP_SERVER, SMTP_PORT, LOGIN_SMTP, SENHA_KEY)
    remetente = EMAIL_REMETENTE if EMAIL_REMETENTE else LOGIN_SMTP
    sucesso = notificador.disparar(
        remetente=remetente,
        destinatarios=email_destino,
        assunto="Seu QR Code - Retirada do Kit Escolar Funfarme",
        corpo="Olá! Segue em anexo o QR Code para retirada do seu Kit Escolar.",
        anexo=buffer_qrcode,
        nome_anexo=f"qrcode_retirada_{cracha}.png"
    )
    buffer_qrcode.seek(0)
    return sucesso
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
        resumo_kits = monta_resumo_kits(escolhas_kits)
        
        # BUSCA SE JÁ EXISTE REGISTRO DE RETIRADA PARA ESTE COLABORADOR
        retirada_existente = db.query(Retirada).filter(Retirada.id_colaborador == colaborador["id"]).first()

        if retirada_existente:
            retirada_existente.resumo_kits = resumo_kits
            retirada_existente.qtd_kits = len(escolhas_kits)
            retirada_existente.email = contato["email"]
            retirada_existente.telefone = contato["telefone"]
            db.commit()
            db.refresh(retirada_existente)
            nova_retirada = retirada_existente
        else:
            codigo_retirada = str(uuid.uuid4())
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

        st.session_state.codigo_retirada = nova_retirada.codigo_retirada
        st.session_state.retirada_qrcode = {
            "Codigo_Retirada": nova_retirada.codigo_retirada,
            "Nome_Colaborador": colaborador["Nome"],
            "ID_Colaborador": colaborador["Crachá"],
            "Email": contato["email"],
            "Telefone": contato["telefone"],
            "Qtd_Kits": len(escolhas_kits),
            "Resumo_Kits": resumo_kits,
            "Status": nova_retirada.status
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

    # 1. MOSTRA O QR CODE NA TELA PRIMEIRO
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

    # 2. DEPOIS FAZ UPLOAD E EMAIL (COM AVISO VISUAL DE PROCESSAMENTO)
    if not st.session_state.get("qrcode_processado", False):
        cracha = str(retirada["ID_Colaborador"])
        
        with st.spinner("☁️ Salvando e enviando cópia por e-mail..."):
            # Envia pro Supabase
            salvar_qrcode_bucket(imagem_qrcode, cracha)
            
            # Dispara o Email
            sucesso_email = enviar_qrcode_por_email(retirada["Email"], imagem_qrcode, cracha)
            
            if sucesso_email:
                st.success("✅ Cópia enviada para o seu e-mail!")
            else:
                st.warning("⚠️ O QR Code está gerado acima, mas houve falha ao enviar a cópia por e-mail.")
                
        st.session_state.qrcode_processado = True

    return imagem_qrcode




#------------------------------------------------------------PAINEL DE CONTROLE------------------------------------------------------------------------
def interface():
    st.set_page_config(page_title='Funfarme - Kit Escolar', page_icon='🎒', layout="wide")
    st.title('🎒 Funfarme - Kit Escolar')

    # 🌟 EXIBE A MENSAGEM DE SUCESSO VINDA DA ATUALIZAÇÃO DO KIT
    if "mensagem_sucesso" in st.session_state and st.session_state.mensagem_sucesso:
        st.success(st.session_state.mensagem_sucesso)
        del st.session_state.mensagem_sucesso
    
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
    if 'aguardando_ciencia_kits' not in st.session_state:
        st.session_state.aguardando_ciencia_kits = False
    if 'escolhas_pendentes_kits' not in st.session_state:
        st.session_state.escolhas_pendentes_kits = []

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
                
                if st.button("🚀 Finalizar Carrinho e Escolher Kits", type="primary", width='stretch', key="btn_fin_sidebar"):
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
                                    revisao_rh=dep.get("revisao_rh"),
                                    # 🚨 SALVANDO O FLUXO E DOCUMENTO NO BANCO DE DADOS
                                    fluxo_documento=dep.get("Fluxo_Documento", "Não identificado"),
                                    # 🔒 GRAVANDO COMPLIANCE NO BANCO
                                    aceite_ia=dep.get("aceite_ia", False),
                                    aceite_lgpd=dep.get("aceite_lgpd", False),
                                    data_aceite=datetime.strptime(dep["data_aceite"], "%Y-%m-%d %H:%M:%S") if dep.get("data_aceite") else None
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
            
            # 🚨 TRAVA INTELIGENTE (BYPASS PARA QUEM ESTÁ CADASTRANDO) 🚨
            if not st.session_state.escolhendo_kits and not st.session_state.cadastro_finalizado:
                db = SessionLocal()
                try:
                    dependentes_existentes = db.query(Dependente).filter(
                        Dependente.id_colaborador == st.session_state.colaborador['id']
                    ).all()
                    
                    if dependentes_existentes and len(st.session_state.lista_dependentes) == 0:
                        st.warning("⚠️ Teu crachá já tem dependentes atrelados a ele.")
                        editar_kits_existentes(st.session_state.colaborador['id'])
                        return  
                finally:
                    db.close()

            contato = adiciona_dados_contato()
            if contato is not None:
                st.session_state.contato = contato
                st.rerun()
    
    else:
        # ===================== FASE 2: TRIAGEM DE VÍNCULO =====================
        st.success(f"👤 Colaborador: {st.session_state.colaborador['Nome']} | ✅ Contato salvo.")

        # 🚨 TRAVA DE VERIFICAÇÃO DE CADASTRO EXISTENTE 🚨
        if not st.session_state.escolhendo_kits and not st.session_state.cadastro_finalizado:
            db = SessionLocal()
            try:
                dependentes_existentes = db.query(Dependente).filter(Dependente.id_colaborador == st.session_state.colaborador['id']).all()
                if dependentes_existentes:
                    st.warning("⚠️ O seu crachá já tem dependentes atrelados a ele!")
                    editar_kits_existentes(st.session_state.colaborador['id'])
                    return  
            finally:
                db.close()

        if st.session_state.lista_dependentes:
            qtd_itens = len(st.session_state.lista_dependentes)
            st.warning(
                f"🛒 **Atenção:** Você tem **{qtd_itens}** item(ns) no seu carrinho! "
                f"Toque nas setas **( >> )** no canto superior esquerdo da tela para abrir o menu lateral e **Finalizar o Pedido**."
            )
        
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
                if st.button("➕ Adicionar outro dependente/kit", type="primary", width='stretch'):
                    st.session_state.aguardando_decisao = False
                    st.session_state.escolaridade = ""
                    st.session_state.ano_escolar = ""
                    st.session_state.aguardando_doc_complementar = False
                    st.session_state.dados_certidao_filho = None
                    st.session_state.dependente_temp = None
                    st.session_state.tipo_fluxo = None 
                    if 'sub_opcao_a' in st.session_state: del st.session_state['sub_opcao_a']
                    if 'sub_opcao_b' in st.session_state: del st.session_state['sub_opcao_b']
                    if 'sub_opcao_c' in st.session_state: del st.session_state['sub_opcao_c']
                    st.rerun()
            with col2:
                if st.button("🚀 Finalizar carrinho e escolher kits", width='stretch', key="btn_fin_main"):
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
                                    revisao_rh=dep.get("revisao_rh"),
                                    # 🚨 SALVANDO O FLUXO E DOCUMENTO NO BANCO DE DADOS
                                    fluxo_documento=dep.get("Fluxo_Documento", "Não identificado"),
                                    # 🔒 GRAVANDO COMPLIANCE NO BANCO
                                    aceite_ia=dep.get("aceite_ia", False),
                                    aceite_lgpd=dep.get("aceite_lgpd", False),
                                    data_aceite=datetime.strptime(dep["data_aceite"], "%Y-%m-%d %H:%M:%S") if dep.get("data_aceite") else None
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
        # SELEÇÃO DO FLUXO PRINCIPAL
        # -------------------------------------------------------------------------
        if st.session_state.tipo_fluxo is None:
            cargos_estagiario = [600, 601, 602, 5001]
            id_cargo_colab = st.session_state.colaborador.get('id_cargo')
            
            if id_cargo_colab is not None and int(id_cargo_colab) in cargos_estagiario:
                st.session_state.tipo_fluxo = "ESTAGIARIO"
                st.rerun()
            else:
                avalia_caso_colaborador()
                return

        # 🚨 ================= MARCADOR: FLUXO ESTAGIÁRIO ================= 🚨
        elif st.session_state.tipo_fluxo == "ESTAGIARIO":
            st.subheader("🎓 Cadastro de Estagiário (Kit Próprio)")
            st.info("Como estagiário, você tem direito ao seu próprio kit escolar. Preencha seus dados acadêmicos e anexe a sua **Certidão de Nascimento** para validação automática.")

            if 'escolaridade' not in st.session_state: st.session_state.escolaridade = ""
            if 'ano_escolar' not in st.session_state: st.session_state.ano_escolar = ""

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
                data_nascimento_est = st.date_input("Sua Data de Nascimento", min_value=date(1950, 1, 1), max_value=date.today(), format="DD/MM/YYYY")
                certidao_est = st.file_uploader("Anexe SUA Certidão de Nascimento", type=["pdf", "png", "jpg", "jpeg"])
                
                st.divider()
                aceite_ia = st.checkbox("Estou ciente de que os documentos enviados serão processados e analisados automaticamente por inteligência artificial para fins de validação cadastral.", key="ia_est")
                aceite_lgpd = st.checkbox("Concordo com o tratamento, armazenamento e uso dos dados para a concessão do Kit Escolar, em conformidade com a LGPD e as normas de compliance da instituição.", key="lgpd_est")
                salvar_est = st.form_submit_button("Validar e Adicionar ao Carrinho")

            if salvar_est:
                erros_est = []
                if not genero_est: erros_est.append("O gênero é obrigatório.")
                if not st.session_state.escolaridade: erros_est.append("A escolaridade é obrigatória.")
                if not st.session_state.ano_escolar: erros_est.append("O ano escolar é obrigatório.")
                if not certidao_est: erros_est.append("A certidão de nascimento é obrigatória.")
                if not aceite_ia or not aceite_lgpd: erros_est.append("Você deve aceitar os termos de uso de IA e a política de privacidade (LGPD) para prosseguir.")

                if erros_est:
                    for e in erros_est: st.error(f"⚠️ {e}")
                else:
                    with st.spinner("Analisando certidão via IA... Aguarde"):
                        dados_cert, err_cert = analisa_certidao(certidao_est)
                        
                        if err_cert:
                            st.error(f"⚠️ {err_cert}")
                        else:
                            dados_ok, msg_dados = valida_dados_crianca_certidao(
                                dados_cert, st.session_state.colaborador['Nome'], data_nascimento_est, genero_est
                            )
                            
                            if not dados_ok:
                                st.error(msg_dados)
                            else:
                                db = SessionLocal()
                                try:
                                    nome_colab = padroniza_texto(st.session_state.colaborador['Nome'])
                                    if verificar_crianca_duplicada(db, nome_colab, data_nascimento_est):
                                        st.error("❌ Você já adicionou o seu kit ao carrinho ou já finalizou este cadastro.")
                                    else:
                                        st.session_state.lista_dependentes.append({
                                            "ID_Dependente": None,
                                            "ID_Colaborador": st.session_state.colaborador['Crachá'],
                                            "Nome_filho": nome_colab, 
                                            "Gênero": genero_est,
                                            "Data_nascimento": data_nascimento_est.strftime("%d/%m/%Y"),
                                            "Escolaridade": st.session_state.escolaridade,
                                            "Ano_escolar": st.session_state.ano_escolar,
                                            "revisao_rh": "Não (Estagiário Validado)",
                                            "Fluxo_Documento": "Estagiário - Certidão de Nascimento", # 🚨
                                            "aceite_ia": aceite_ia,
                                            "aceite_lgpd": aceite_lgpd,
                                            "data_aceite": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                        })
                                        st.success("✅ Certidão validada! Seu Kit foi adicionado ao carrinho.")
                                        st.session_state.aguardando_decisao = True
                                        st.rerun()
                                finally:
                                    db.close()

        # 🚨 ================= MARCADOR: CAMINHO A ================= 🚨
        elif st.session_state.tipo_fluxo == "A":
            st.subheader("🍼 Cadastro - Filho(a) Biológico(a) ou Adotivo(a)")
            
            if st.button("⬅️ Voltar e escolher outra opção", key="voltar_a"):
                st.session_state.tipo_fluxo = None
                if 'sub_opcao_a' in st.session_state:
                    del st.session_state['sub_opcao_a']
                st.rerun()
            st.write("---")
            sub_opcao_a = st.radio(
                "🎯 Selecione a forma de comprovação do vínculo:",
                ["**A1:** Certidão de Nascimento - Filho(a) Biológico(a) ", "**A2:** Certidão de Nascimento com averbação de adoção", "**A3:** Documento judicial que comprove a guarda para fins de adoção"],
                index=None, key="sub_opcao_a"
            )

            if sub_opcao_a:
                st.divider()
                
                # --- SUB-FLUXO A1 ---
                if "A1" in sub_opcao_a:
                    dependente = adicionar_dependentes()
                    if dependente is not None:
                        st.session_state.lista_dependentes.append(dependente)
                        st.session_state.aguardando_decisao = True
                        st.rerun()

                # --- SUB-FLUXOS A2 e A3 ---
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
                            declaracao_escolar_a2 = st.file_uploader("Anexar Declaração Escolar de Matrícula 📚", type=["pdf", "png", "jpg", "jpeg"], key="declaracao_escolar_a2")
                            
                            st.divider()
                            aceite_ia = st.checkbox("Estou ciente de que os documentos enviados serão processados e analisados automaticamente por inteligência artificial para fins de validação cadastral.", key="ia_a2")
                            aceite_lgpd = st.checkbox("Concordo com o tratamento, armazenamento e uso dos dados para a concessão do Kit Escolar, em conformidade com a LGPD e as normas de compliance da instituição.", key="lgpd_a2")
                            salvar_a2 = st.form_submit_button("Validar e Adicionar ao Carrinho (A2)")

                        if salvar_a2:
                            erros_a2 = []
                            if not nome_filho_a2.strip(): erros_a2.append("O nome da criança é obrigatório.")
                            if not genero_a2: erros_a2.append("O gênero é obrigatório.")
                            if not st.session_state.escolaridade: erros_a2.append("A escolaridade é obrigatória.")
                            if not st.session_state.ano_escolar: erros_a2.append("O ano escolar é obrigatório.")
                            if not certidao_averbada: erros_a2.append("A certidão com averbação é obrigatória.")
                            if not declaracao_escolar_a2: erros_a2.append("A declaração escolar de matrícula é obrigatória.")
                            if not aceite_ia or not aceite_lgpd: erros_a2.append("Você deve aceitar os termos de uso de IA e a política de privacidade (LGPD) para prosseguir.")

                            if erros_a2:
                                for e in erros_a2: st.error(f"⚠️ {e}")
                            else:
                                with st.spinner("Analisando certidão com averbação via IA... Aguarde"):
                                    dados_a2, err_a2 = analisa_certidao_averbacao(certidao_averbada)
                                    
                                    if err_a2:
                                        st.error(f"⚠️ {err_a2}")
                                    elif not dados_a2.get("tem_averbacao_adocao"):
                                        st.error("⚠️ O documento não possui a averbação de adoção exigida.")
                                    else:
                                        dados_ok, msg_dados = valida_dados_crianca_certidao(
                                            dados_a2, nome_filho_a2, data_nascimento_a2, genero_a2
                                        )
                                        
                                        if not dados_ok:
                                            st.error(msg_dados)
                                        else:
                                            dados_decl_a2, err_decl_a2 = analisa_declaracao_escolar(declaracao_escolar_a2)
                                            decl_ok_a2 = False
                                            if err_decl_a2:
                                                st.error(err_decl_a2)
                                            else:
                                                decl_ok_a2, msg_decl_a2 = valida_declaracao_escolar(
                                                    dados_decl_a2, dados_a2.get("nome_crianca") or nome_filho_a2
                                                )
                                                if decl_ok_a2:
                                                    st.success(msg_decl_a2)
                                                else:
                                                    st.error(msg_decl_a2)

                                            if decl_ok_a2:
                                                nome_colab = padroniza_texto(st.session_state.colaborador['Nome'])
                                                pais_responsaveis = [padroniza_texto(p) for p in dados_a2.get("nomes_pais_responsaveis", [])]

                                                if nome_colab not in pais_responsaveis:
                                                    st.error(f"⚠️ O nome do colaborador ({st.session_state.colaborador['Nome']}) não consta como pai/mãe na certidão ou na averbação de adoção.")
                                                else:
                                                    db = SessionLocal()
                                                    try:
                                                        nome_cert_a2 = padroniza_texto(dados_a2.get("nome_crianca", "")) or padroniza_texto(nome_filho_a2)
                                                        if verificar_crianca_duplicada(db, nome_cert_a2, data_nascimento_a2):
                                                            st.error("⚠️ Esta criança está no seu carrinho ou já possui um kit cadastrado.")
                                                        else:
                                                            st.session_state.lista_dependentes.append({
                                                                "ID_Dependente": None,
                                                                "ID_Colaborador": st.session_state.colaborador['Crachá'],
                                                                "Nome_filho": nome_cert_a2,
                                                                "Gênero": genero_a2,
                                                                "Data_nascimento": data_nascimento_a2.strftime("%d/%m/%Y"),
                                                                "Escolaridade": st.session_state.escolaridade,
                                                                "Ano_escolar": st.session_state.ano_escolar,
                                                                "revisao_rh": "Sim (Adoção A2)",
                                                                "Fluxo_Documento": "A2 - Certidão de Nascimento com Averbação de Adoção", # 🚨
                                                                "aceite_ia": aceite_ia,
                                                                "aceite_lgpd": aceite_lgpd,
                                                                "data_aceite": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
                            
                            st.divider()
                            aceite_ia = st.checkbox("Estou ciente de que os documentos enviados serão processados e analisados automaticamente por inteligência artificial para fins de validação cadastral.", key="ia_a3")
                            aceite_lgpd = st.checkbox("Concordo com o tratamento, armazenamento e uso dos dados para a concessão do Kit Escolar, em conformidade com a LGPD e as normas de compliance da instituição.", key="lgpd_a3")
                            salvar_a3 = st.form_submit_button("Validar e Adicionar ao Carrinho (A3)")

                        if salvar_a3:
                            erros_a3 = []
                            if not nome_filho_a3.strip(): erros_a3.append("O nome da criança é obrigatório.")
                            if not st.session_state.escolaridade: erros_a3.append("A escolaridade é obrigatória.")
                            if not st.session_state.ano_escolar: erros_a3.append("O ano escolar é obrigatório.")
                            if not doc_judicial: erros_a3.append("O documento judicial é obrigatório.")
                            if not aceite_ia or not aceite_lgpd: erros_a3.append("Você deve aceitar os termos de uso de IA e a política de privacidade (LGPD) para prosseguir.")

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
                                        else:
                                            db = SessionLocal()
                                            try:
                                                nome_final_a3 = padroniza_texto(dados_a3.get("nome_crianca", "")) or padroniza_texto(nome_filho_a3)
                                                if verificar_crianca_duplicada(db, nome_final_a3, data_nascimento_a3):
                                                    st.error("⚠️ Esta criança está no seu carrinho ou já possui um kit cadastrado.")
                                                else:
                                                    st.session_state.lista_dependentes.append({
                                                        "ID_Dependente": None,
                                                        "ID_Colaborador": st.session_state.colaborador['Crachá'],
                                                        "Nome_filho": nome_final_a3,
                                                        "Gênero": "Não informado",
                                                        "Data_nascimento": data_nascimento_a3.strftime("%d/%m/%Y"),
                                                        "Escolaridade": st.session_state.escolaridade,
                                                        "Ano_escolar": st.session_state.ano_escolar,
                                                        "revisao_rh": "Sim (Guarda para Adoção A3)",
                                                        "Fluxo_Documento": "A3 - Termo de Guarda para Fins de Adoção", # 🚨
                                                        "aceite_ia": aceite_ia,
                                                        "aceite_lgpd": aceite_lgpd,
                                                        "data_aceite": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                                    })
                                                    st.success("✅ Dependente adicionado ao carrinho com sucesso!")
                                                    st.session_state.aguardando_decisao = True
                                                    st.rerun()
                                            finally:
                                                db.close()

        # 🚨 ================= MARCADOR: CAMINHO B ================= 🚨
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
                ["**B1:** Documento comprobatório de união estável + Certidão de Nascimento Filho(a)", "**B2:** Certidão de Casamento + Certidão de Nascimento Filho(a)"],
                index=None, key="sub_opcao_b"
            )

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
                        st.info("📌 Requisitos : Envie a **Certidão de Nascimento da Criança** e a **Declaração de União Estável** com firma reconhecida.")
                        nome_filho_b = st.text_input("Nome Completo da Criança")
                        genero_b = st.selectbox("Gênero:", ["", "Masculino", "Feminino"], format_func=lambda x: "Selecione o Gênero..." if x == "" else x)
                        data_nascimento_b = st.date_input("Data de Nascimento da Criança", min_value=date(2000, 1, 1), max_value=date.today() - timedelta(days=730), format="DD/MM/YYYY")
                        certidao_b = st.file_uploader("Anexar Certidão de Nascimento", type=["pdf", "png", "jpg", "jpeg"], key="cert_b1")
                        uniao_b = st.file_uploader("Anexar União Estável (com firma reconhecida e Selo do Carto)", type=["pdf", "png", "jpg", "jpeg"], key="doc_b1")
                        declaracao_escolar_b1 = st.file_uploader("Anexar Declaração Escolar de Matrícula 📚", type=["pdf", "png", "jpg", "jpeg"], key="declaracao_escolar_b1")
                        
                        st.divider()
                        aceite_ia = st.checkbox("Estou ciente de que os documentos enviados serão processados e analisados automaticamente por inteligência artificial para fins de validação cadastral.", key="ia_b1")
                        aceite_lgpd = st.checkbox("Concordo com o tratamento, armazenamento e uso dos dados para a concessão do Kit Escolar, em conformidade com a LGPD e as normas de compliance da instituição.", key="lgpd_b1")
                        salvar_b1 = st.form_submit_button("Validar e Adicionar ao Carrinho (B1)")

                    if salvar_b1:
                        erros_b = []
                        if not nome_filho_b.strip(): erros_b.append("O nome da criança é obrigatório.")
                        if not genero_b: erros_b.append("O gênero é obrigatório.")
                        if not st.session_state.escolaridade: erros_b.append("A escolaridade é obrigatória.")
                        if not st.session_state.ano_escolar: erros_b.append("O ano escolar é obrigatório.")
                        if not certidao_b: erros_b.append("A certidão de nascimento é obrigatória.")
                        if not uniao_b: erros_b.append("A declaração de união estável é obrigatória.")
                        if not declaracao_escolar_b1: erros_b.append("A declaração escolar de matrícula é obrigatória.")
                        if not declaracao_escolar_b1: erros_b.append("A declaração escolar de matrícula é obrigatória.")
                        if not aceite_ia or not aceite_lgpd: erros_b.append("Você deve aceitar os termos de uso de IA e a política de privacidade (LGPD) para prosseguir.")
                            
                        if erros_b:
                            for e in erros_b: st.error(f"⚠️ {e}")
                        else:
                            with st.spinner("Analisando documentos com a IA... Aguarde"):
                                dados_cert, err_cert = analisa_certidao(certidao_b)
                                
                                if err_cert:
                                    st.error(f"⚠️ {err_cert}")
                                else:
                                    dados_ok, msg_dados = valida_dados_crianca_certidao(
                                        dados_cert, nome_filho_b, data_nascimento_b, genero_b
                                    )
                                    
                                    if not dados_ok:
                                        st.error(msg_dados)
                                    else:
                                        dados_decl_b1, err_decl_b1 = analisa_declaracao_escolar(declaracao_escolar_b1)
                                        decl_ok_b1 = False
                                        if err_decl_b1:
                                            st.error(err_decl_b1)
                                        else:
                                            decl_ok_b1, msg_decl_b1 = valida_declaracao_escolar(
                                                dados_decl_b1, dados_cert.get("nome_crianca") or nome_filho_b
                                            )
                                            if decl_ok_b1:
                                                st.success(msg_decl_b1)
                                            else:
                                                st.error(msg_decl_b1)

                                        if decl_ok_b1:
                                            dados_uniao, err_uniao = analisa_uniao_estavel(uniao_b)
                                        else:
                                            dados_uniao, err_uniao = None, "Declaração escolar inválida."
                                        
                                        if err_uniao:
                                            st.error(f"⚠️ {err_uniao}")
                                        elif not dados_uniao.get("firma_reconhecida"):
                                            st.error("⚠️ A Declaração de União Estável precisa ter firma reconhecida em cartório.")
                                        else:
                                            db = SessionLocal()
                                            try:
                                                nome_final_b1 = padroniza_texto(dados_cert.get("nome_crianca") or nome_filho_b)
                                                if verificar_crianca_duplicada(db, nome_final_b1, data_nascimento_b):
                                                    st.error("⚠️ Esta criança está no seu carrinho ou já possui um kit cadastrado.")
                                                else:
                                                    st.session_state.lista_dependentes.append({
                                                        "ID_Dependente": None,
                                                        "ID_Colaborador": st.session_state.colaborador['Crachá'],
                                                        "Nome_filho": nome_final_b1,
                                                        "Gênero": genero_b,
                                                        "Data_nascimento": data_nascimento_b.strftime("%d/%m/%Y"),
                                                        "Escolaridade": st.session_state.escolaridade,
                                                        "Ano_escolar": st.session_state.ano_escolar,
                                                        "revisao_rh": "Sim (Enteado - União Estável B1)",
                                                        "Fluxo_Documento": "B1 - Certidão de Nascimento + União Estável (Firma Reconhecida)", # 🚨
                                                        "aceite_ia": aceite_ia,
                                                        "aceite_lgpd": aceite_lgpd,
                                                        "data_aceite": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
                        declaracao_escolar_b2 = st.file_uploader("Anexar Declaração Escolar de Matrícula 📚", type=["pdf", "png", "jpg", "jpeg"], key="declaracao_escolar_b2")
                        
                        st.divider()
                        aceite_ia = st.checkbox("Estou ciente de que os documentos enviados serão processados e analisados automaticamente por inteligência artificial para fins de validação cadastral.", key="ia_b2")
                        aceite_lgpd = st.checkbox("Concordo com o tratamento, armazenamento e uso dos dados para a concessão do Kit Escolar, em conformidade com a LGPD e as normas de compliance da instituição.", key="lgpd_b2")
                        salvar_b2 = st.form_submit_button("Validar e Adicionar ao Carrinho (B2)")

                    if salvar_b2:
                        erros_b2 = []
                        if not nome_filho_b2.strip(): erros_b2.append("O nome da criança é obrigatório.")
                        if not genero_b2: erros_b2.append("O gênero é obrigatório.")
                        if not st.session_state.escolaridade: erros_b2.append("A escolaridade é obrigatória.")
                        if not st.session_state.ano_escolar: erros_b2.append("O ano escolar é obrigatório.")
                        if not certidao_b2: erros_b2.append("A certidão de nascimento é obrigatória.")
                        if not casamento_b2: erros_b2.append("A certidão de casamento é obrigatória.")
                        if not declaracao_escolar_b2: erros_b2.append("A declaração escolar de matrícula é obrigatória.")
                        if not declaracao_escolar_b2: erros_b2.append("A declaração escolar de matrícula é obrigatória.")
                        if not aceite_ia or not aceite_lgpd: erros_b2.append("Você deve aceitar os termos de uso de IA e a política de privacidade (LGPD) para prosseguir.")

                        if erros_b2:
                            for e in erros_b2: st.error(f"⚠️ {e}")
                        else:
                            with st.spinner("Analisando documentos com a IA... Aguarde"):
                                dados_cert, err_cert = analisa_certidao(certidao_b2)
                                
                                if err_cert:
                                    st.error(f"⚠️ {err_cert}")
                                else:
                                    dados_ok, msg_dados = valida_dados_crianca_certidao(
                                        dados_cert, nome_filho_b2, data_nascimento_b2, genero_b2
                                    )
                                    if not dados_ok:
                                        st.error(msg_dados)
                                    else:
                                        dados_decl_b2, err_decl_b2 = analisa_declaracao_escolar(declaracao_escolar_b2)
                                        decl_ok_b2 = False
                                        if err_decl_b2:
                                            st.error(err_decl_b2)
                                        else:
                                            decl_ok_b2, msg_decl_b2 = valida_declaracao_escolar(dados_decl_b2, dados_cert.get("nome_crianca") or nome_filho_b2)
                                            if decl_ok_b2:
                                                st.success(msg_decl_b2)
                                            else:
                                                st.error(msg_decl_b2)

                                        if decl_ok_b2:
                                            dados_casam, err_casam = analisa_certidao_complementar(casamento_b2)
                                        else:
                                            dados_casam, err_casam = None, "Declaração escolar inválida."
                                        if err_casam:
                                            if decl_ok_b2:
                                                st.error(f"⚠️ {err_casam}")
                                        elif not dados_casam.get("documento_valido"):
                                            st.error("⚠️ A Certidão de Casamento é inválida ou não pôde ser lida.")
                                        else:
                                            db = SessionLocal()
                                            try:
                                                nome_final_b2 = padroniza_texto(dados_cert.get("nome_crianca") or nome_filho_b2)
                                                if verificar_crianca_duplicada(db, nome_final_b2, data_nascimento_b2):
                                                    st.error("⚠️ Esta criança está no seu carrinho ou já possui um kit cadastrado.")
                                                else:
                                                    st.session_state.lista_dependentes.append({
                                                        "ID_Dependente": None,
                                                        "ID_Colaborador": st.session_state.colaborador['Crachá'],
                                                        "Nome_filho": nome_final_b2,
                                                        "Gênero": genero_b2,
                                                        "Data_nascimento": data_nascimento_b2.strftime("%d/%m/%Y"),
                                                        "Escolaridade": st.session_state.escolaridade,
                                                        "Ano_escolar": st.session_state.ano_escolar,
                                                        "revisao_rh": "Sim (Enteado - Casamento B2)",
                                                        "Fluxo_Documento": "B2 - Certidão de Nascimento + Certidão de Casamento", # 🚨
                                                        "aceite_ia": aceite_ia,
                                                        "aceite_lgpd": aceite_lgpd,
                                                        "data_aceite": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                                    })
                                                    st.success("✅ Dependente adicionado ao carrinho com sucesso!")
                                                    st.session_state.aguardando_decisao = True
                                                    st.rerun()
                                            finally:
                                                db.close()

        # 🚨 ================= MARCADOR: CAMINHO C ================= 🚨
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
                ["**C1:** Termo/Certidão de Guarda Judicial + Certidão de Nascimento", "**C2:** Termo de Tutela Judicial + Certidão de Nascimento"],
                index=None, key="sub_opcao_c"
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
                        declaracao_escolar_c1 = st.file_uploader("Anexar Declaração Escolar de Matrícula 📚", type=["pdf", "png", "jpg", "jpeg"], key="declaracao_escolar_c1")
                        
                        st.divider()
                        aceite_ia = st.checkbox("Estou ciente de que os documentos enviados serão processados e analisados automaticamente por inteligência artificial para fins de validação cadastral.", key="ia_c1")
                        aceite_lgpd = st.checkbox("Concordo com o tratamento, armazenamento e uso dos dados para a concessão do Kit Escolar, em conformidade com a LGPD e as normas de compliance da instituição.", key="lgpd_c1")
                        salvar_c1 = st.form_submit_button("Validar e Adicionar ao Carrinho (C1)")

                    if salvar_c1:
                        erros_c1 = []
                        if not nome_filho_c1.strip(): erros_c1.append("O nome da criança é obrigatório.")
                        if not genero_c1: erros_c1.append("O gênero é obrigatório.")
                        if not st.session_state.escolaridade: erros_c1.append("A escolaridade é obrigatória.")
                        if not st.session_state.ano_escolar: erros_c1.append("O ano escolar é obrigatório.")
                        if not certidao_c1 or not termo_guarda_c1: erros_c1.append("Documento(s) ausente(s) ou ilegível(is)")
                        if not declaracao_escolar_c1: erros_c1.append("A declaração escolar de matrícula é obrigatória.")
                        if not aceite_ia or not aceite_lgpd: erros_c1.append("Você deve aceitar os termos de uso de IA e a política de privacidade (LGPD) para prosseguir.")
                            
                        if erros_c1:
                            for e in erros_c1: st.error(f"⚠️ {e}")
                        else:
                            with st.spinner("Analisando documentos com a IA... Aguarde"):
                                dados_cert_c1, err_cert_c1 = analisa_certidao(certidao_c1)
                                
                                if err_cert_c1:
                                    st.error(f"⚠️ {err_cert_c1}")
                                else:
                                    dados_ok, msg_dados = valida_dados_crianca_certidao(
                                        dados_cert_c1, nome_filho_c1, data_nascimento_c1, genero_c1
                                    )
                                    if not dados_ok:
                                        st.error(msg_dados)
                                    else:
                                        dados_decl_c1, err_decl_c1 = analisa_declaracao_escolar(declaracao_escolar_c1)
                                        decl_ok_c1 = False
                                        if err_decl_c1:
                                            st.error(err_decl_c1)
                                        else:
                                            decl_ok_c1, msg_decl_c1 = valida_declaracao_escolar(
                                                dados_decl_c1, dados_cert_c1.get("nome_crianca") or nome_filho_c1
                                            )
                                            if decl_ok_c1:
                                                st.success(msg_decl_c1)
                                            else:
                                                st.error(msg_decl_c1)

                                        if decl_ok_c1:
                                            dados_guarda, err_guarda = analisa_guarda_judicial(termo_guarda_c1)
                                        else:
                                            dados_guarda, err_guarda = None, "Declaração escolar inválida."
                                        if err_guarda:
                                            if decl_ok_c1:
                                                st.error(f"⚠️ {err_guarda}")
                                        elif not dados_guarda.get("documento_valido"):
                                            st.error("⚠️ O Termo de Guarda é inválido ou não pôde ser lido.")
                                        else:
                                            db = SessionLocal()
                                            try:
                                                nome_final_c1 = padroniza_texto(dados_cert_c1.get("nome_crianca", "")) or padroniza_texto(nome_filho_c1)
                                                if verificar_crianca_duplicada(db, nome_final_c1, data_nascimento_c1):
                                                    st.error("❌ Esta criança já está no seu carrinho ou já possui um kit cadastrado.")
                                                else:
                                                    st.session_state.lista_dependentes.append({
                                                        "ID_Dependente": None,
                                                        "ID_Colaborador": st.session_state.colaborador['Crachá'],
                                                        "Nome_filho": nome_final_c1,
                                                        "Gênero": genero_c1,
                                                        "Data_nascimento": data_nascimento_c1.strftime("%d/%m/%Y"),
                                                        "Escolaridade": st.session_state.escolaridade,
                                                        "Ano_escolar": st.session_state.ano_escolar,
                                                        "revisao_rh": "Sim (Guarda Judicial C1)",
                                                        "Fluxo_Documento": "C1 - Certidão de Nascimento + Guarda Judicial", # 🚨
                                                        "aceite_ia": aceite_ia,
                                                        "aceite_lgpd": aceite_lgpd,
                                                        "data_aceite": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
                        declaracao_escolar_c2 = st.file_uploader("Anexar Declaração Escolar de Matrícula 📚", type=["pdf", "png", "jpg", "jpeg"], key="declaracao_escolar_c2")
                        
                        st.divider()
                        aceite_ia = st.checkbox("Estou ciente de que os documentos enviados serão processados e analisados automaticamente por inteligência artificial para fins de validação cadastral.", key="ia_c2")
                        aceite_lgpd = st.checkbox("Concordo com o tratamento, armazenamento e uso dos dados para a concessão do Kit Escolar, em conformidade com a LGPD e as normas de compliance da instituição.", key="lgpd_c2")
                        salvar_c2 = st.form_submit_button("Validar e Adicionar ao Carrinho (C2)")

                    if salvar_c2:
                        erros_c2 = []
                        if not nome_filho_c2.strip(): erros_c2.append("O nome da criança é obrigatório.")
                        if not genero_c2: erros_c2.append("O gênero é obrigatório.")
                        if not st.session_state.escolaridade: erros_c2.append("A escolaridade é obrigatória.")
                        if not st.session_state.ano_escolar: erros_c2.append("O ano escolar é obrigatório.")
                        if not certidao_c2 or not termo_tutela_c2: erros_c2.append("Documento(s) ausente(s) ou ilegível(is)")
                        if not declaracao_escolar_c2: erros_c2.append("A declaração escolar de matrícula é obrigatória.")
                        if not aceite_ia or not aceite_lgpd: erros_c2.append("Você deve aceitar os termos de uso de IA e a política de privacidade (LGPD) para prosseguir.")
                            
                        if erros_c2:
                            for e in erros_c2: st.error(f"⚠️ {e}")
                        else:
                            with st.spinner("Analisando documentos com a IA... Aguarde"):
                                dados_cert_c2, err_cert_c2 = analisa_certidao(certidao_c2)
                                
                                if err_cert_c2:
                                    st.error(f"⚠️ {err_cert_c2}")
                                else:
                                    dados_ok, msg_dados = valida_dados_crianca_certidao(
                                        dados_cert_c2, nome_filho_c2, data_nascimento_c2, genero_c2
                                    )
                                    if not dados_ok:
                                        st.error(msg_dados)
                                    else:
                                        dados_decl_c2, err_decl_c2 = analisa_declaracao_escolar(declaracao_escolar_c2)
                                        decl_ok_c2 = False
                                        if err_decl_c2:
                                            st.error(err_decl_c2)
                                        else:
                                            decl_ok_c2, msg_decl_c2 = valida_declaracao_escolar(
                                                dados_decl_c2, dados_cert_c2.get("nome_crianca") or nome_filho_c2
                                            )
                                            if decl_ok_c2:
                                                st.success(msg_decl_c2)
                                            else:
                                                st.error(msg_decl_c2)

                                        if decl_ok_c2:
                                            dados_tutela, err_tutela = analisa_tutela_judicial(termo_tutela_c2)
                                        else:
                                            dados_tutela, err_tutela = None, "Declaração escolar inválida."
                                        if err_tutela:
                                            if decl_ok_c2:
                                                st.error(f"⚠️ {err_tutela}")
                                        elif not dados_tutela.get("documento_valido"):
                                            st.error("⚠️ O Termo de Tutela é inválido ou não pôde ser lido.")
                                        else:
                                            db = SessionLocal()
                                            try:
                                                nome_final_c2 = padroniza_texto(dados_cert_c2.get("nome_crianca", "")) or padroniza_texto(nome_filho_c2)
                                                if verificar_crianca_duplicada(db, nome_final_c2, data_nascimento_c2):
                                                    st.error("❌ Esta criança já está no seu carrinho ou já possui um kit cadastrado.")
                                                else:
                                                    st.session_state.lista_dependentes.append({
                                                        "ID_Dependente": None,
                                                        "ID_Colaborador": st.session_state.colaborador['Crachá'],
                                                        "Nome_filho": nome_final_c2,
                                                        "Gênero": genero_c2,
                                                        "Data_nascimento": data_nascimento_c2.strftime("%d/%m/%Y"),
                                                        "Escolaridade": st.session_state.escolaridade,
                                                        "Ano_escolar": st.session_state.ano_escolar,
                                                        "revisao_rh": "Sim (Tutela Judicial C2)",
                                                        "Fluxo_Documento": "C2 - Certidão de Nascimento + Tutela Judicial", # 🚨
                                                        "aceite_ia": aceite_ia,
                                                        "aceite_lgpd": aceite_lgpd,
                                                        "data_aceite": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                                    })
                                                    st.success("✅ Dependente adicionado ao carrinho com sucesso!")
                                                    st.session_state.aguardando_decisao = True
                                                    st.rerun()
                                            finally:
                                                db.close()
interface()