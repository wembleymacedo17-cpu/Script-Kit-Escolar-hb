import io
import base64
import pyotp
import qrcode
import streamlit as st
from sqlalchemy import text
from datetime import datetime, date
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
    """Valida o código de 6 dígitos com tolerância de relógio."""
    if not secret_key or not codigo_digitado:
        return False
    secret_limpa = str(secret_key).strip()
    codigo_limpo = str(codigo_digitado).strip()
    totp = pyotp.TOTP(secret_limpa)
    return totp.verify(codigo_limpo, valid_window=3)

def verificar_autenticacao_totp(colaborador: dict, engine_db) -> bool:
    """Interface do Streamlit para o fluxo de TOTP com Trava de Segurança Cadastral."""
    st.subheader("🔒 Validação de Segurança (2FA)")

    nome_colab = colaborador.get("Nome") or colaborador.get("nome") or "Colaborador"
    cracha_colab = colaborador.get("Crachá") or colaborador.get("cracha") or colaborador.get("id")
    secret_cadastrado = colaborador.get("totp_secret")
    
    data_nasc_banco = colaborador.get("data_nascimento")

    # -------------------------------------------------------------
    # FLUXO 1: PRIMEIRO ACESSO (Confirmação de Identidade pré-QR Code)
    # -------------------------------------------------------------
    if not colaborador.get("totp_ativo") or not secret_cadastrado:
        
        # Estado temporário para saber se a pessoa passou no teste de identidade
        if "identidade_confirmada" not in st.session_state:
            st.session_state.identidade_confirmada = False

        if not st.session_state.identidade_confirmada:
            st.info("👋 **Primeiro acesso detectado!** Para sua segurança, confirme seus dados cadastrais para liberar a configuração do aplicativo autenticador:")

            with st.form("form_valida_identidade"):
                st.write(f"Colaborador: **{nome_colab}** | Crachá: **{cracha_colab}**")
                
                dt_informada = st.date_input(
                    "Informe sua Data de Nascimento para validar a titularidade:",
                    min_value=date(1940, 1, 1),
                    max_value=date.today(),
                    format="DD/MM/YYYY"
                )
                
                btn_validar_dados = st.form_submit_button("Confirmar Identidade", type="primary", use_container_width=True)

            if btn_validar_dados:
                data_nasc_convertida = None
                
                if data_nasc_banco:
                    # Se já for um objeto date ou datetime do Python
                    if hasattr(data_nasc_banco, "date"):
                        data_nasc_convertida = data_nasc_banco.date()
                    elif isinstance(data_nasc_banco, date):
                        data_nasc_convertida = data_nasc_banco
                    elif isinstance(data_nasc_banco, str):
                        for formato in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"):
                            try:
                                data_nasc_convertida = datetime.strptime(data_nasc_banco.strip(), formato).date()
                                break
                            except ValueError:
                                continue

                if data_nasc_convertida and dt_informada == data_nasc_convertida:
                    st.session_state.identidade_confirmada = True
                    st.success("✅ Identidade confirmada!")
                    st.rerun()
                else:
                    st.error("❌ Data de nascimento incorreta. O cadastro do 2FA não pôde ser liberado.")
            
            return False

        # -------------------------------------------------------------
        # LIBERAÇÃO DO QR CODE APÓS CONFIRMAR IDENTIDADE
        # -------------------------------------------------------------
        st.markdown("1️⃣ Baixe o aplicativo **Google Authenticator** ou **Authy** na loja do seu celular.")
        st.markdown("2️⃣ Abra o aplicativo, selecione **Ler QR Code** e aponte a câmera:")

        if "temp_totp_secret" not in st.session_state:
            st.session_state.temp_totp_secret = pyotp.random_base32()

        secret = st.session_state.temp_totp_secret

        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(name=nome_colab, issuer_name="Funfarme - Kit Escolar")
        
        img = qrcode.make(uri)
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

        st.markdown(
            f'<div style="text-align: center; margin: 15px 0;"><img src="data:image/png;base64,{img_b64}" width="200"></div>',
            unsafe_allow_html=True
        )
        st.caption(f"Chave de inserção manual: `{secret}`")
        st.divider()

        with st.form("form_ativar_totp"):
            codigo_ativacao = st.text_input("Digite o código de 6 dígitos gerado no aplicativo:", max_chars=6)
            btn_ativar = st.form_submit_button("Ativar Segurança e Acessar", type="primary", use_container_width=True)

        if btn_ativar:
            if validar_codigo_totp(secret, codigo_ativacao):
                query_update = """
                    UPDATE colaboradores 
                    SET totp_secret = :secret, totp_ativo = TRUE 
                    WHERE cracha = :cracha
                """
                with engine_db.begin() as conn:
                    conn.execute(text(query_update), {"secret": str(secret).strip(), "cracha": cracha_colab})

                colaborador["totp_secret"] = str(secret).strip()
                colaborador["totp_ativo"] = True
                
                if "temp_totp_secret" in st.session_state:
                    del st.session_state.temp_totp_secret
                if "identidade_confirmada" in st.session_state:
                    del st.session_state.identidade_confirmada

                st.success("✅ Validador configurado com sucesso!")
                return True
            else:
                st.error("❌ Código incorreto. Verifique o relógio do celular e tente novamente.")

        return False

    # -------------------------------------------------------------
    # FLUXO 2: ACESSOS RECORRENTES (Já configurado anteriormente)
    # -------------------------------------------------------------
    else:
        with st.form("form_login_totp"):
            st.write(f"Olá, **{nome_colab}**! Digite o código de 6 dígitos do seu aplicativo autenticador:")
            codigo_login = st.text_input("Código do Authenticator", max_chars=6)
            btn_entrar = st.form_submit_button("Entrar no Sistema", type="primary", use_container_width=True)

        if btn_entrar:
            if validar_codigo_totp(secret_cadastrado, codigo_login):
                return True
            else:
                st.error("❌ Código inválido ou expirado. Tente novamente.")

        return False