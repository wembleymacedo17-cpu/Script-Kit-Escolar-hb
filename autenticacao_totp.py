import io
import base64
import pyotp
import qrcode
import streamlit as st
from sqlalchemy import text


def gerar_secret_totp():
    """Gera uma nova chave secreta Base32."""
    return pyotp.random_base32()


def gerar_qrcode_base64(secret_key: str, nome_usuario: str) -> str:
    """Gera o QR Code em formato imagem Base64 para exibição nativa no Streamlit."""
    totp = pyotp.TOTP(secret_key)
    uri = totp.provisioning_uri(name=nome_usuario, issuer_name="Funfarme - Kit Escolar")
    
    img = qrcode.make(uri)
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")


def validar_codigo_totp(secret_key: str, codigo_digitado: str) -> bool:
    """Valida o código de 6 dígitos considerando a janela de tempo ampliada (tolera dessincronização)."""
    if not secret_key or not codigo_digitado:
        return False
    totp = pyotp.TOTP(secret_key)
    # valid_window=3 tolera até 1 minuto e meio de diferença de relógio entre o celular e o servidor
    return totp.verify(codigo_digitado, valid_window=3)


def verificar_autenticacao_totp(colaborador: dict, engine_db) -> bool:
    """
    Interface visual do Streamlit para o fluxo de TOTP.
    Retorna True quando o colaborador é autenticado com sucesso.
    """
    st.subheader("🔒 Validação de Segurança (2FA)")

    # Normaliza chaves para evitar KeyError (lê tanto 'Nome' quanto 'nome', 'Crachá' quanto 'cracha')
    nome_colab = colaborador.get("Nome") or colaborador.get("nome") or "Colaborador"
    cracha_colab = colaborador.get("Crachá") or colaborador.get("cracha") or colaborador.get("id")

    # -------------------------------------------------------------
    # FLUXO 1: PRIMEIRO ACESSO (Cadastra a chave e lê o QR Code)
    # -------------------------------------------------------------
    if not colaborador.get("totp_ativo") or not colaborador.get("totp_secret"):
        st.info("👋 **Primeiro acesso detectado!** Para garantir a segurança da sua solicitação, configure o seu validador em poucas etapas:")

        if "temp_totp_secret" not in st.session_state:
            st.session_state.temp_totp_secret = gerar_secret_totp()

        secret = st.session_state.temp_totp_secret

        st.markdown("1️⃣ Baixe o aplicativo **Google Authenticator**, **Microsoft Authenticator** ou **Authy** na loja do seu celular.")
        st.markdown("2️⃣ Abra o aplicativo, selecione **Ler QR Code** e aponte a câmera para a imagem abaixo:")

        img_b64 = gerar_qrcode_base64(secret, nome_colab)
        st.markdown(
            f'<div style="text-align: center; margin: 15px 0;"><img src="data:image/png;base64,{img_b64}" width="220"></div>',
            unsafe_allow_html=True
        )
        st.caption(f"Ou insira a chave manualmente no aplicativo: `{secret}`")
        st.divider()

        with st.form("form_ativar_totp"):
            codigo_ativacao = st.text_input("Digite o código de 6 dígitos gerado no aplicativo:", max_chars=6)
            btn_ativar = st.form_submit_button("Confirmar e Ativar Acesso", type="primary", use_container_width=True)

        if btn_ativar:
            if validar_codigo_totp(secret, codigo_ativacao):
                # Salva no banco de dados e ativa o TOTP usando o crachá normalizado
                query_update = """
                    UPDATE colaboradores 
                    SET totp_secret = :secret, totp_ativo = TRUE 
                    WHERE cracha = :cracha
                """
                with engine_db.begin() as conn:
                    conn.execute(text(query_update), {"secret": secret, "cracha": cracha_colab})

                # Atualiza os dados na sessão
                colaborador["totp_secret"] = secret
                colaborador["totp_ativo"] = True
                del st.session_state.temp_totp_secret

                st.success("✅ Validador configurado com sucesso!")
                return True
            else:
                st.error("❌ Código incorreto. Verifique o horário do seu celular e tente novamente.")
        
        return False

    # -------------------------------------------------------------
    # FLUXO 2: ACESSOS RECURRENTES (Apenas digita o código)
    # -------------------------------------------------------------
    else:
        with st.form("form_login_totp"):
            st.write(f"Olá, **{nome_colab}**! Digite o código de 6 dígitos do seu aplicativo autenticador:")
            codigo_login = st.text_input("Código do Authenticator", max_chars=6)
            btn_entrar = st.form_submit_button("Entrar no Sistema", type="primary", use_container_width=True)

        if btn_entrar:
            if validar_codigo_totp(colaborador["totp_secret"], codigo_login):
                st.success("✅ Autenticado com sucesso!")
                return True
            else:
                st.error("❌ Código inválido ou expirado. Tente novamente.")

        return False