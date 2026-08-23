import streamlit as st
import os
import json
import requests
from io import BytesIO
from PIL import Image
import google.generativeai as genai
from datetime import datetime
from database import SessionLocal, Dependente, Colaborador, Retirada, EscolhaKit
from notificador_revisao import NotificadorEmail, SMTP_SERVER, SMTP_PORT, LOGIN_SMTP, SENHA_KEY, EMAIL_REMETENTE

st.set_page_config(page_title="Revisão RH - Documentos", layout="wide")

# ===================== CONFIGURAÇÃO GEMINI =====================
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

def analisar_documentos_com_ia(doc_identidade_fonte, declaracao_fonte, doc_vinculo_fonte, motivo_reprova, nome_colaborador, nome_filho):
    try:
        conteudo_gemini = []
        
        if doc_identidade_fonte:
            if isinstance(doc_identidade_fonte, str):
                resp = requests.get(doc_identidade_fonte, timeout=10)
                resp.raise_for_status()
                img_doc = Image.open(BytesIO(resp.content))
                conteudo_gemini.append("--- Documento de Identidade da Criança (URL) ---")
                conteudo_gemini.append(img_doc)
            else:
                doc_identidade_fonte.seek(0)
                if doc_identidade_fonte.name.lower().endswith('.pdf'):
                    conteudo_gemini.append({"mime_type": "application/pdf", "data": doc_identidade_fonte.read()})
                else:
                    conteudo_gemini.append("--- Documento de Identidade da Criança ---")
                    conteudo_gemini.append(Image.open(doc_identidade_fonte))
            
        if declaracao_fonte:
            declaracao_fonte.seek(0)
            if declaracao_fonte.name.lower().endswith('.pdf'):
                conteudo_gemini.append({"mime_type": "application/pdf", "data": declaracao_fonte.read()})
            else:
                conteudo_gemini.append("--- Declaração Escolar ---")
                conteudo_gemini.append(Image.open(declaracao_fonte))

        if doc_vinculo_fonte:
            doc_vinculo_fonte.seek(0)
            if doc_vinculo_fonte.name.lower().endswith('.pdf'):
                conteudo_gemini.append({"mime_type": "application/pdf", "data": doc_vinculo_fonte.read()})
            else:
                conteudo_gemini.append("--- Documento de Vínculo ---")
                conteudo_gemini.append(Image.open(doc_vinculo_fonte))

        if not conteudo_gemini:
            return {"sugestao_acao": "REPROVAR", "analise_tecnica_rh": "⚠️ Nenhum documento fornecido.", "corpo_email": ""}

        model = genai.GenerativeModel(
            'gemini-3.1-flash-lite',
            generation_config={"response_mime_type": "application/json"}
        )
        
        motivo_texto = motivo_reprova or "Não especificado pelo sistema"
        data_hoje_str = datetime.now().strftime("%d/%m/%Y")
        ano_atual_str = datetime.now().strftime("%Y")

        prompt = f"""
        Você é um especialista em Recursos Humanos da instituição Funfarme.
        O cadastro do dependente {nome_filho} do colaborador {nome_colaborador} caiu em quarentena do RH.
        Motivo apontado pela automação: '{motivo_texto}'.
        Data atual do sistema: {data_hoje_str} (Ano Letivo: {ano_atual_str}).

        SUA TAREFA:
        1. Analise se os documentos cumprem os requisitos para concessão do Kit Escolar {ano_atual_str}.
        2. Escolha entre "APROVAR" ou "REPROVAR".
        3. Se a opção for REPROVAR, você OBRIGATORIAMENTE deve redigir o e-mail completo orientando o colaborador sobre qual documento foi recusado e o que ele precisa corrigir.

        REGRA OBRIGATÓRIA DO E-MAIL:
        - NUNCA oriente o colaborador a enviar o documento por e-mail para o RH.
        - Sempre oriente o colaborador a ACESSAR O SISTEMA NOVAMENTE para refazer o cadastro do dependente com a documentação corrigida.

        ESQUEMA JSON OBRIGATÓRIO (MANTENHA EXATAMENTE ESTAS CHAVES):
        {{
            "sugestao_acao": "REPROVAR" ou "APROVAR",
            "analise_tecnica_rh": "Explicação técnica detalhada para o agente do RH.",
            "corpo_email": "Olá, {nome_colaborador}. Informamos que... [Instruções claras e detalhadas do que corrigir e aviso para refazer o cadastro no sistema]. Atenciosamente,\\nEquipe de Recursos Humanos"
        }}
        """
        
        conteudo_gemini.insert(0, prompt)
        resposta = model.generate_content(conteudo_gemini)
        return json.loads(resposta.text.strip())
    except Exception as e:
        return {
            "sugestao_acao": "REPROVAR",
            "analise_tecnica_rh": f"⚠️ Erro ao processar análise da IA: {e}",
            "corpo_email": f"Olá, {nome_colaborador}.\n\nPor favor, revise os documentos enviados para o dependente {nome_filho} e efetue o recadastro no sistema.\n\nAtenciosamente,\nEquipe de Recursos Humanos"
        }

# ===================== FUNÇÕES DE BANCO E E-MAIL =====================

def buscar_dependentes_revisao():
    db = SessionLocal()
    try:
        return db.query(
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
    finally:
        db.close()

def aprovar_documento(id_dependente, cracha_colaborador, nome_colaborador, email_destino, corpo_personalizado=None):
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
        
        if corpo_personalizado and corpo_personalizado.strip():
            corpo_email = corpo_personalizado
        else:
            corpo_email = f"Olá, {nome_colaborador}.\n\nO RH analisou o documento enviado para o dependente {dependente.nome_filho} e sua documentação foi APROVADA com sucesso!\n\nSeu kit já está registrado no nosso sistema. Em breve divulgaremos as datas de entrega.\n\nAtenciosamente,\nEquipe de Recursos Humanos"

        sucesso = notificador.disparar(remetente=EMAIL_REMETENTE, destinatarios=[email_destino], assunto=assunto, corpo=corpo_email)
        if sucesso:
            st.success("✅ Documento aprovado! Status atualizado e e-mail enviado.")
        else:
            st.warning("⚠️ Documento aprovado, mas houve falha no envio do e-mail.")
    except Exception as e:
        db.rollback()
        st.error(f"Erro ao aprovar documento: {e}")
    finally:
        db.close()

def enviar_email_reprovacao(id_dependente, cracha_colaborador, nome_colaborador, email_destino, corpo_personalizado):
    db = SessionLocal()
    try:
        dependente = db.query(Dependente).filter(Dependente.id_dependente == id_dependente).first()
        if not dependente:
            st.error("Dependente não encontrado.")
            return
        
        notificador = NotificadorEmail(
            smtp_server=SMTP_SERVER,
            smtp_port=SMTP_PORT,
            login_smtp=LOGIN_SMTP,
            senha=SENHA_KEY
        )
        
        assunto = "⚠️ Ação Necessária: Correção no Cadastro do Kit Escolar"
        sucesso = notificador.disparar(remetente=EMAIL_REMETENTE, destinatarios=[email_destino], assunto=assunto, corpo=corpo_personalizado)
        
        if sucesso:
            db.query(EscolhaKit).filter(EscolhaKit.id_dependente == id_dependente).delete(synchronize_session=False)
            db.delete(dependente)
            db.query(Retirada).filter(Retirada.id_colaborador == cracha_colaborador).delete(synchronize_session=False)
            
            db.commit()
            st.success(f"📧 E-mail enviado para {email_destino} e cadastro liberado para nova tentativa!")
        else:
            st.error("❌ O e-mail falhou ao ser enviado. Registro mantido.")
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
        
        col_info, col_img = st.columns([1.1, 1.4])
        
        chave_estado_msg = f"msg_{dep_selecionado.id_dependente}"
        chave_estado_analise = f"analise_{dep_selecionado.id_dependente}"
        chave_versao_widget = f"v_reprov_{dep_selecionado.id_dependente}"
        
        motivo_exibicao = dep_selecionado.motivo_reprova_ia or "Não especificado pelo sistema"
        
        if chave_estado_msg not in st.session_state:
            st.session_state[chave_estado_msg] = ""
        if chave_estado_analise not in st.session_state:
            st.session_state[chave_estado_analise] = None
        if chave_versao_widget not in st.session_state:
            st.session_state[chave_versao_widget] = 0

        with col_info:
            st.subheader("📋 Dados da Revisão")
            st.markdown(f"**Nome do Colaborador:** {nome_colaborador}")
            st.markdown(f"**Crachá:** {cracha_colaborador}")
            st.markdown(f"**Nome do Filho(a):** {dep_selecionado.nome_filho}")
            
            st.error(f"**🤖 Motivo da Reprovação (IA):**\n\n{motivo_exibicao}")
            
            if st.session_state[chave_estado_analise]:
                res_ia = st.session_state[chave_estado_analise]
                st.write("---")
                st.subheader("🧠 Sugestão e Análise da IA (RH)")
                
                if res_ia.get("sugestao_acao") == "APROVAR":
                    st.success(f"**Recomendação:** APROVAR CADASTRO\n\n**Justificativa:** {res_ia.get('analise_tecnica_rh')}")
                else:
                    st.warning(f"**Recomendação:** REPROVAR E SOLICITAR CORREÇÃO\n\n**Justificativa:** {res_ia.get('analise_tecnica_rh')}")

            st.write("---")
            st.subheader("⚙️ Ações de Revisão")
            
            email_colaborador = st.text_input("E-mail de Contato (Editável):", value=email_retirada or "", placeholder="email@empresa.com.br")
            
            msg_aprovacao_padrao = f"Olá, {nome_colaborador}.\n\nO RH analisou o documento enviado para o dependente {dep_selecionado.nome_filho} e sua documentação foi APROVADA com sucesso!\n\nSeu kit já está registrado no nosso sistema. Em breve divulgaremos as datas de entrega.\n\nAtenciosamente,\nEquipe de Recursos Humanos"
            
            tab_aprovar, tab_reprovar = st.tabs(["✅ Aprovar Cadastro", "❌ Reprovar Cadastro"])
            
            # 🟢 ABA 1: APROVAÇÃO
            with tab_aprovar:
                corpo_email_aprovacao = st.text_area(
                    "📝 E-mail de Aprovação (Editável):", 
                    value=msg_aprovacao_padrao, 
                    height=180,
                    key=f"aprov_{dep_selecionado.id_dependente}"
                )
                
                if st.button("✅ Confirmar Aprovação", use_container_width=True, type="primary"):
                    if not email_colaborador:
                        st.warning("⚠️ Informe o e-mail do colaborador para aprovar.")
                    else:
                        aprovar_documento(
                            dep_selecionado.id_dependente, 
                            cracha_colaborador, 
                            nome_colaborador, 
                            email_colaborador,
                            corpo_email_aprovacao
                        )
                        st.rerun()

            # 🔴 ABA 2: REPROVAÇÃO
            with tab_reprovar:
                # Key dinâmica baseada na versão do session_state
                key_dinamica_reprov = f"reprov_{dep_selecionado.id_dependente}_v{st.session_state[chave_versao_widget]}"
                
                corpo_email_reprovacao = st.text_area(
                    "📝 E-mail de Reprovação (Gere com a IA ao lado ou digite):", 
                    value=st.session_state[chave_estado_msg], 
                    height=180,
                    key=key_dinamica_reprov
                )
                
                if st.button("❌ Confirmar Reprovação e Limpar Cadastro", use_container_width=True):
                    if not email_colaborador:
                        st.warning("⚠️ Informe o e-mail do colaborador para enviar as instruções.")
                    elif not corpo_email_reprovacao.strip():
                        st.warning("⚠️ O corpo do e-mail não pode estar vazio ao reprovar.")
                    else:
                        enviar_email_reprovacao(
                            dep_selecionado.id_dependente, 
                            cracha_colaborador, 
                            nome_colaborador, 
                            email_colaborador, 
                            corpo_email_reprovacao
                        )
                        st.rerun()

        with col_img:
            st.subheader("📄 Visualização e Envio de Documentos")
            
            st.markdown("### 🛠️ Painel de Testes e Envio Manual")
            st.info("Envie os tipos de documento necessários (PDF ou Imagem) para efetuar a validação:")
            
            arquivo_rg_certidao = st.file_uploader(
                "1️⃣ RG ou Certidão de Nascimento", 
                type=["pdf", "png", "jpg", "jpeg"], 
                key=f"up_rg_{dep_selecionado.id_dependente}"
            )
            
            arquivo_declaracao = st.file_uploader(
                "2️⃣ Declaração Escolar", 
                type=["pdf", "png", "jpg", "jpeg"], 
                key=f"up_decl_{dep_selecionado.id_dependente}"
            )

            arquivo_vinculo = st.file_uploader(
                "3️⃣ Documento de Vínculo (União Estável / Casamento / Guarda)", 
                type=["pdf", "png", "jpg", "jpeg"], 
                key=f"up_vinc_{dep_selecionado.id_dependente}"
            )
            
            fonte_rg_para_ia = None
            
            if arquivo_rg_certidao:
                arquivo_rg_certidao.seek(0)
                if not arquivo_rg_certidao.name.lower().endswith('.pdf'):
                    st.image(arquivo_rg_certidao, caption="RG/Certidão enviado manualmente", use_container_width=True)
                fonte_rg_para_ia = arquivo_rg_certidao

            elif dep_selecionado.url_documento and str(dep_selecionado.url_documento).strip() != "None":
                urls = [u.strip() for u in str(dep_selecionado.url_documento).split(",") if u.strip()]
                
                st.markdown("### 📎 Anexos Originais (Enviados na Quarentena)")
                for i, link in enumerate(urls, 1):
                    try:
                        if link.lower().endswith('.pdf'):
                            st.info(f"📄 **Anexo {i}:** [Clique para visualizar o PDF]({link})")
                        else:
                            st.image(link, caption=f"Anexo {i} - Banco de Dados", use_container_width=True)
                    except Exception:
                        st.warning(f"⚠️ Não foi possível carregar o anexo {i}.")
                        
                fonte_rg_para_ia = urls[0] if urls else None

            else:
                st.warning("⚠️ **Nenhum documento encontrado no banco de dados para este registro.**")

            if fonte_rg_para_ia or arquivo_declaracao or arquivo_vinculo:
                st.write("---")
                st.markdown("### 🧠 Assistente Analítico (Gemini)")
                st.write("A IA cruzará as informações para orientar o RH e sugerir o e-mail.")
                
                if st.button("🪄 Analisar Caso (Auxiliar RH)", use_container_width=True):
                    with st.spinner("Analisando documentos, gerando parecer e rascunho de e-mail..."):
                        resultado = analisar_documentos_com_ia(
                            fonte_rg_para_ia,
                            arquivo_declaracao,
                            arquivo_vinculo,
                            dep_selecionado.motivo_reprova_ia,
                            nome_colaborador,
                            dep_selecionado.nome_filho
                        )
                        st.session_state[chave_estado_analise] = resultado
                        
                        email_gerado = resultado.get("corpo_email", "")
                        
                        if not email_gerado or resultado.get("sugestao_acao") == "REPROVAR":
                            email_gerado = (
                                f"Olá, {nome_colaborador}.\n\n"
                                f"Informamos que a análise do cadastro do seu dependente, {dep_selecionado.nome_filho}, "
                                f"para o Kit Escolar não foi aprovada no momento.\n\n"
                                f"Motivo/Orientação: {resultado.get('analise_tecnica_rh', 'Documento inconsistente.')}\n\n"
                                f"Seu cadastro anterior foi liberado. Por gentileza, acesse o sistema novamente e realize um novo cadastro anexando a documentação corrigida.\n\n"
                                f"Atenciosamente,\nEquipe de Recursos Humanos"
                            )
                        
                        # Atualiza o texto e força o incremento da versão da key
                        st.session_state[chave_estado_msg] = email_gerado
                        st.session_state[chave_versao_widget] += 1
                        st.rerun()
            else:
                st.info("💡 Envie pelo menos um documento para habilitar o gerador analítico da IA.")