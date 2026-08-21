import streamlit as st
import os
import requests
from io import BytesIO
from PIL import Image
import google.generativeai as genai

from database import SessionLocal, Dependente, Colaborador, Retirada
from notificador_revisao import NotificadorEmail, SMTP_SERVER, SMTP_PORT, LOGIN_SMTP, SENHA_KEY, EMAIL_REMETENTE

st.set_page_config(page_title="Revisão RH - Documentos", layout="wide")

# ===================== CONFIGURAÇÃO GEMINI =====================
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

def analisar_documentos_com_ia(doc_identidade_fonte, declaracao_fonte, motivo_reprova, nome_colaborador, nome_filho):
    """
    Envia o RG/Certidão e a Declaração Escolar para o Gemini analisar junto com o motivo do erro.
    """
    try:
        conteudo_gemini = []
        
        # 1. Processa RG ou Certidão de Nascimento
        if doc_identidade_fonte:
            if isinstance(doc_identidade_fonte, str):
                resp = requests.get(doc_identidade_fonte, timeout=10)
                resp.raise_for_status()
                img_doc = Image.open(BytesIO(resp.content))
                conteudo_gemini.append("--- Documento de Identidade (URL) ---")
                conteudo_gemini.append(img_doc)
            else:
                doc_identidade_fonte.seek(0)
                nome_arq = doc_identidade_fonte.name.lower()
                if nome_arq.endswith('.pdf'):
                    bytes_pdf = doc_identidade_fonte.read()
                    conteudo_gemini.append({"mime_type": "application/pdf", "data": bytes_pdf})
                else:
                    img_doc = Image.open(doc_identidade_fonte)
                    conteudo_gemini.append("--- Documento de Identidade (Imagem) ---")
                    conteudo_gemini.append(img_doc)
            
        # 2. Processa Declaração Escolar
        if declaracao_fonte:
            declaracao_fonte.seek(0)
            nome_decl = declaracao_fonte.name.lower()
            if nome_decl.endswith('.pdf'):
                bytes_decl = declaracao_fonte.read()
                conteudo_gemini.append({"mime_type": "application/pdf", "data": bytes_decl})
            else:
                img_decl = Image.open(declaracao_fonte)
                conteudo_gemini.append("--- Declaração Escolar (Imagem) ---")
                conteudo_gemini.append(img_decl)

        if not conteudo_gemini:
            return "⚠️ Nenhum documento foi fornecido para análise da IA."

        model = genai.GenerativeModel('gemini-3.1-flash-lite')
        motivo_texto = motivo_reprova or "Não especificado pelo sistema"
        
        prompt = f"""
        Você é um assistente de Recursos Humanos empático, rigoroso e claro.
        O sistema automatizado barrou o cadastro do dependente {nome_filho} do colaborador {nome_colaborador}.
        O erro apontado pelo sistema foi: '{motivo_texto}'.

        Sua tarefa:
        1. Analise os documentos fornecidos (RG/Certidão de Nascimento e/ou Declaração Escolar).
        2. Identifique exatamente por que o erro ocorreu (ex: divergência de nome, documento ilegível, série incompatível na declaração, falta de filiação, etc).
        3. Escreva EXATAMENTE O CORPO DO E-MAIL a ser enviado para o colaborador, explicando o problema de forma clara e orientando como regularizar sua inscrição no sistema.

        REGRAS DO E-MAIL:
        - Comece com "Olá, {nome_colaborador}."
        - Finalize com "Atenciosamente,\nEquipe de Recursos Humanos"
        - Seja gentil, mas direto e instrutivo.
        - NÃO INCLUA "Assunto:", retorne estritamente o corpo do texto.
        """
        
        conteudo_gemini.insert(0, prompt)
        
        resposta = model.generate_content(conteudo_gemini)
        return resposta.text
    except Exception as e:
        return f"⚠️ Ocorreu um erro ao gerar a análise com a IA: {e}"

# ===================== FUNÇÕES DE BANCO E E-MAIL =====================

def buscar_dependentes_revisao():
    db = SessionLocal()
    try:
        resultados = db.query(
            Dependente,
            Colaborador.nome.label("nome_colaborador"),
            Colaborador.cracha.label("cracha_colaborador"),
            Retirada.email.label("email_retirada")
        ).join(
            Colaborador, Colaborador.cracha == Dependente.id_colaborador
        ).outerjoin(
            Retirada, Retirada.id_colaborador == Dependente.id_colaborador
        ).filter(
            Dependente.revisao_rh != 'Não'
        ).all()
        return resultados
    finally:
        db.close()

def aprovar_documento(id_dependente, cracha_colaborador, nome_colaborador, email_destino):
    db = SessionLocal()
    try:
        dependente = db.query(Dependente).filter(Dependente.id_dependente == id_dependente).first()
        if dependente:
            dependente.revisao_rh = 'Não'
            
        retirada = db.query(Retirada).filter(Retirada.id_colaborador == cracha_colaborador).first()
        if retirada:
            retirada.status = 'PENDENTE'
            
        db.commit()
        
        notificador = NotificadorEmail(
            smtp_server=SMTP_SERVER,
            smtp_port=SMTP_PORT,
            login_smtp=LOGIN_SMTP,
            senha=SENHA_KEY
        )
        
        assunto = "✅ Cadastro Aprovado - Kit Escolar"
        corpo_email = f"Olá, {nome_colaborador}.\n\nO RH analisou o documento enviado para o dependente {dependente.nome_filho} e sua documentação foi APROVADA com sucesso!\n\nSeu kit já está registrado no nosso sistema. Em breve divulgaremos as datas de entrega.\n\nAtenciosamente,\nEquipe de Recursos Humanos"

        sucesso = notificador.disparar(remetente=EMAIL_REMETENTE, destinatarios=[email_destino], assunto=assunto, corpo=corpo_email)
        if sucesso:
            st.success("✅ Documento aprovado! Status atualizado e e-mail de aprovação enviado.")
        else:
            st.warning("⚠️ Documento aprovado, mas houve um erro ao enviar o e-mail de notificação.")
    except Exception as e:
        db.rollback()
        st.error(f"Erro ao aprovar documento: {e}")
    finally:
        db.close()

def enviar_email_reprovacao(id_dependente, nome_colaborador, email_destino, corpo_personalizado):
    db = SessionLocal()
    try:
        dependente = db.query(Dependente).filter(Dependente.id_dependente == id_dependente).first()
        if not dependente:
            st.error("Dependente não encontrado.")
            return

        dependente.revisao_rh = 'Reprovado - Aguardando Correção'
        db.commit()
        
        notificador = NotificadorEmail(
            smtp_server=SMTP_SERVER,
            smtp_port=SMTP_PORT,
            login_smtp=LOGIN_SMTP,
            senha=SENHA_KEY
        )
        
        assunto = "⚠️ Ação Necessária: Correção no Cadastro do Kit Escolar"
        sucesso = notificador.disparar(remetente=EMAIL_REMETENTE, destinatarios=[email_destino], assunto=assunto, corpo=corpo_personalizado)
        if sucesso:
            st.success(f"📧 E-mail com instruções enviado para {email_destino}!")
        else:
            st.error("❌ O e-mail falhou ao ser enviado. Verifique os logs no console.")
    except Exception as e:
        db.rollback()
        st.error(f"Erro ao processar reprovação: {e}")
    finally:
        db.close()


# ===================== INTERFACE DO USUÁRIO =====================

st.title("📂 Painel de Revisão de Documentos - RH")
st.write("Avalie os documentos que foram barrados pela Inteligência Artificial.")
st.divider()

registros = buscar_dependentes_revisao()

if not registros:
    st.info("🎉 Excelente! Não há documentos pendentes de revisão no momento.")
else:
    st.write(f"**{len(registros)} documento(s) aguardando análise.**")
    
    opcoes = {
        f"{dep.nome_filho} (Colaborador: {nome_col})": (dep, nome_col, cracha, email_ret) 
        for dep, nome_col, cracha, email_ret in registros
    }
    selecao = st.selectbox("Selecione um dependente para revisar:", list(opcoes.keys()))
    
    if selecao:
        dep_selecionado, nome_colaborador, cracha_colaborador, email_retirada = opcoes[selecao]
        
        col_info, col_img = st.columns([1, 1.5])
        
        chave_estado_msg = f"msg_{dep_selecionado.id_dependente}"
        motivo_exibicao = dep_selecionado.motivo_reprova_ia or "Não especificado pelo sistema"
        
        texto_padrao = f"Olá, {nome_colaborador}.\n\nO documento enviado para o dependente {dep_selecionado.nome_filho} não pôde ser validado pelo nosso sistema.\nMotivo apontado: {motivo_exibicao}\n\nPor favor, acesse o sistema novamente e envie os documentos corretos.\n\nEm caso de dúvidas, procure o RH.\n\nAtenciosamente,\nEquipe de Recursos Humanos"
        
        if chave_estado_msg not in st.session_state:
            st.session_state[chave_estado_msg] = texto_padrao

        with col_info:
            st.subheader("📋 Dados da Revisão")
            st.markdown(f"**Nome do Colaborador:** {nome_colaborador}")
            st.markdown(f"**Crachá:** {cracha_colaborador}")
            st.markdown(f"**Nome do Filho(a):** {dep_selecionado.nome_filho}")
            
            st.error(f"**🤖 Motivo da Reprovação (IA):**\n\n{motivo_exibicao}")
            
            st.write("---")
            st.subheader("⚙️ Ações de Revisão")
            
            email_colaborador = st.text_input("E-mail de Contato (Editável):", value=email_retirada or "", placeholder="email@empresa.com.br")
            
            corpo_email_reprovacao = st.text_area(
                "📝 Corpo do E-mail (Gere com IA ao lado ou digite):", 
                value=st.session_state[chave_estado_msg], 
                height=250
            )
            
            if st.button("✅ Aprovar Documento (Falso Negativo da IA)", use_container_width=True, type="primary"):
                if not email_colaborador:
                    st.warning("⚠️ Informe o e-mail do colaborador para aprovar.")
                else:
                    aprovar_documento(dep_selecionado.id_dependente, cracha_colaborador, nome_colaborador, email_colaborador)
                    st.rerun()
                
            if st.button("❌ Reprovar e Enviar Instruções", use_container_width=True):
                if not email_colaborador:
                    st.warning("⚠️ Informe o e-mail do colaborador para enviar as instruções.")
                else:
                    enviar_email_reprovacao(dep_selecionado.id_dependente, nome_colaborador, email_colaborador, corpo_email_reprovacao)
                    st.rerun()

        with col_img:
            st.subheader("📄 Visualização e Envio de Documentos")
            
            st.markdown("### 🛠️ Painel de Testes e Envio Manual")
            st.info("Envie os tipos de documento necessários (PDF ou Imagem) para a validação da IA:")
            
            # 1. Uploader para RG ou Certidão
            arquivo_rg_certidao = st.file_uploader(
                "1️⃣ RG ou Certidão de Nascimento", 
                type=["pdf", "png", "jpg", "jpeg"], 
                key=f"up_rg_{dep_selecionado.id_dependente}"
            )
            
            # 2. Uploader para Declaração Escolar (Corrigido para dep_selecionado)
            arquivo_declaracao = st.file_uploader(
                "2️⃣ Declaração Escolar", 
                type=["pdf", "png", "jpg", "jpeg"], 
                key=f"up_decl_{dep_selecionado.id_dependente}" if hasattr(dep_selecionado, 'id_dependente') else "up_decl_default"
            )
            
            fonte_rg_para_ia = None
            
            if arquivo_rg_certidao:
                arquivo_rg_certidao.seek(0)
                nome_arq = arquivo_rg_certidao.name.lower()
                if nome_arq.endswith('.pdf'):
                    st.info(f"📄 PDF carregado (RG/Certidão): {arquivo_rg_certidao.name}")
                else:
                    st.image(arquivo_rg_certidao, caption="RG/Certidão enviado manualmente", use_container_width=True)
                fonte_rg_para_ia = arquivo_rg_certidao
            elif dep_selecionado.url_documento:
                try:
                    st.image(dep_selecionado.url_documento, caption=f"Documento do Banco de {dep_selecionado.nome_filho}", use_container_width=True)
                    fonte_rg_para_ia = dep_selecionado.url_documento
                except Exception:
                    st.warning("⚠️ Não foi possível carregar a imagem a partir da URL do banco.")

            if arquivo_declaracao:
                arquivo_declaracao.seek(0)
                nome_decl = arquivo_declaracao.name.lower()
                if nome_decl.endswith('.pdf'):
                    st.info(f"📄 PDF carregado (Declaração): {arquivo_declaracao.name}")
                else:
                    st.image(arquivo_declaracao, caption="Declaração Escolar enviada manualmente", use_container_width=True)

            if fonte_rg_para_ia or arquivo_declaracao:
                st.write("---")
                st.markdown("### 🧠 Assistente Analítico (Gemini)")
                st.write("A IA cruzará o motivo do erro com os documentos enviados (PDFs ou Imagens) para montar a resposta.")
                
                if st.button("🪄 Gerar Resposta Analítica", use_container_width=True):
                    with st.spinner("A IA está analisando os arquivos e gerando as instruções..."):
                        texto_ia = analisar_documentos_com_ia(
                            fonte_rg_para_ia,
                            arquivo_declaracao,
                            dep_selecionado.motivo_reprova_ia,
                            nome_colaborador,
                            dep_selecionado.nome_filho
                        )
                        st.session_state[chave_estado_msg] = texto_ia
                        st.rerun()
            else:
                st.warning("⚠️ Envie pelo menos um dos documentos para habilitar a análise da IA.")