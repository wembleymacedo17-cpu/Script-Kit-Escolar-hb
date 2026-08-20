import streamlit as st
from database import SessionLocal, Dependente, Colaborador, Retirada
from notificador_revisao import NotificadorEmail, SMTP_SERVER, SMTP_PORT, LOGIN_SMTP, SENHA_KEY, EMAIL_REMETENTE

st.set_page_config(page_title="Revisão RH - Documentos", layout="wide")

def buscar_dependentes_revisao():
    """
    Consulta os dependentes, faz JOIN com colaboradores pelo crachá 
    e LEFT JOIN com retiradas para capturar o e-mail cadastrado pelo usuário.
    """
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
    """
    Aprova o documento, atualiza status e envia e-mail de aprovação.
    """
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
        corpo_email = f"""Olá, {nome_colaborador}.

O RH analisou o documento enviado para o dependente {dependente.nome_filho} e sua documentação foi APROVADA com sucesso!

Seu kit já está registrado no nosso sistema. Em breve divulgaremos as datas de entrega.

Atenciosamente,
Equipe de Recursos Humanos"""

        sucesso = notificador.disparar(
            remetente=EMAIL_REMETENTE,
            destinatarios=[email_destino],
            assunto=assunto,
            corpo=corpo_email
        )

        if sucesso:
            st.success("✅ Documento aprovado! Status atualizado e e-mail de aprovação enviado.")
        else:
            st.warning("⚠️ Documento aprovado, mas houve um erro ao enviar o e-mail de notificação.")
            
    except Exception as e:
        db.rollback()
        st.error(f"Erro ao aprovar documento: {e}")
    finally:
        db.close()

def enviar_email_reprovacao(id_dependente, nome_colaborador, email_destino):
    """
    Reprova e envia e-mail solicitando correção.
    """
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
        corpo_email = f"""Olá, {nome_colaborador}.

O documento enviado para o dependente {dependente.nome_filho} não pôde ser validado pelo nosso sistema.
Motivo apontado: {dependente.motivo_reprova_ia}

Por favor, acesse o sistema novamente e envie um documento legível contendo a filiação correta (se enviou o RG, lembre-se de fotografar o lado que contém o nome dos pais).

Em caso de dúvidas, procure o RH.

Atenciosamente,
Equipe de Recursos Humanos"""

        sucesso = notificador.disparar(
            remetente=EMAIL_REMETENTE,
            destinatarios=[email_destino],
            assunto=assunto,
            corpo=corpo_email
        )

        if sucesso:
            st.success(f"📧 E-mail com instruções de correção enviado para {email_destino}!")
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
    
    # Mapeia os 4 valores retornados na consulta: dep, nome_col, cracha, email_retirada
    opcoes = {
        f"{dep.nome_filho} (Colaborador: {nome_col})": (dep, nome_col, cracha, email_ret) 
        for dep, nome_col, cracha, email_ret in registros
    }
    selecao = st.selectbox("Selecione um dependente para revisar:", list(opcoes.keys()))
    
    if selecao:
        dep_selecionado, nome_colaborador, cracha_colaborador, email_retirada = opcoes[selecao]
        
        col_info, col_img = st.columns([1, 1.5])
        
        with col_info:
            st.subheader("📋 Dados da Revisão")
            st.markdown(f"**Nome do Colaborador:** {nome_colaborador}")
            st.markdown(f"**Crachá:** {cracha_colaborador}")
            st.markdown(f"**Nome do Filho(a):** {dep_selecionado.nome_filho}")
            
            st.error(f"**🤖 Motivo da Reprovação (IA):**\n\n{dep_selecionado.motivo_reprova_ia}")
            
            st.write("---")
            st.subheader("⚙️ Ações de Revisão")
            st.write("Analise a imagem ao lado e decida a ação apropriada.")
            
            # 📧 CAMPO DE E-MAIL EDITÁVEL (Já vem preenchido com o dado da tabela retiradas)
            st.markdown("**E-mail de Contato (Editável)**")
            email_colaborador = st.text_input(
                "E-mail do colaborador:", 
                value=email_retirada or "", 
                placeholder="Rh_4.0@empresa.com.br"
            )
            
            # Ação 1: Erro do Sistema / Falso Negativo (APROVAR)
            if st.button("✅ Aprovar Documento (Erro da IA)", use_container_width=True, type="primary"):
                if not email_colaborador:
                    st.warning("⚠️ Informe ou ajuste o e-mail do colaborador para enviar a confirmação.")
                else:
                    aprovar_documento(dep_selecionado.id_dependente, cracha_colaborador, nome_colaborador, email_colaborador)
                    st.rerun()
                
            st.write("---")
            
            # Ação 2: Erro Real do Usuário (REPROVAR)
            if st.button("❌ Reprovar e Enviar Instruções (Erro do Usuário)", use_container_width=True):
                if not email_colaborador:
                    st.warning("⚠️ Informe ou ajuste o e-mail do colaborador para enviar as instruções.")
                else:
                    enviar_email_reprovacao(dep_selecionado.id_dependente, nome_colaborador, email_colaborador)
                    st.rerun()

        with col_img:
            st.subheader("📄 Visualização do Documento")
            if dep_selecionado.url_documento:
                try:
                    st.image(dep_selecionado.url_documento, caption=f"Documento de {dep_selecionado.nome_filho}", use_container_width=True)
                except Exception:
                    st.warning("⚠️ Não foi possível carregar a imagem a partir da URL fornecida.")
            else:
                st.warning("Nenhuma URL de documento cadastrada para este dependente.")