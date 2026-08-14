import smtplib
import mimetypes
from email.message import EmailMessage
from pathlib import Path
from dotenv import load_dotenv
import os

# Carrega variáveis de ambiente
load_dotenv()

# Lendo credenciais do .env
SMTP_SERVER = os.getenv("SERVIDOR_BREVO")
SMTP_PORT = os.getenv("PORTA_BREVO")
LOGIN_SMTP = os.getenv("LOGIN_SMTP")               
SENHA_KEY = os.getenv("SENHA")                     
EMAIL_REMETENTE = os.getenv("EMAIL_REMETENTE")    

print(SMTP_SERVER, SMTP_PORT, LOGIN_SMTP, SENHA_KEY, EMAIL_REMETENTE)



class NotificadorEmail:
    def __init__(self, smtp_server: str, smtp_port: int, login_smtp: str, senha: str):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.login_smtp = login_smtp
        self.senha = senha

    def disparar(self, remetente: str, destinatarios: str | list[str], assunto: str, corpo: str, caminho_imagem: str):
        """
        Monta e envia o e-mail com uma imagem anexada via SMTP.
        """
        if isinstance(destinatarios, str):
            destinatarios = [destinatarios]

        msg = EmailMessage()
        msg['Subject'] = assunto
        msg['From'] = remetente
        msg['To'] = ", ".join(destinatarios)
        msg.set_content(corpo)

        # Trata imagem
        caminho_arq = Path(caminho_imagem)
        if not caminho_arq.exists():
            print(f"❌ Erro: O arquivo de imagem não existe no caminho: {caminho_imagem}")
            return

        tipo_mime, _ = mimetypes.guess_type(caminho_imagem)
        if tipo_mime is None:
            tipo_mime = 'application/octet-stream'
        tipo_principal, sub_tipo = tipo_mime.split('/')

        with open(caminho_arq, 'rb') as img:
            msg.add_attachment(
                img.read(), 
                maintype=tipo_principal, 
                subtype=sub_tipo, 
                filename=caminho_arq.name
            )

        # Envio SMTP
        try:
            print("Conectando ao servidor Brevo...")
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.login_smtp, self.senha)
                server.send_message(msg)
                
            print(f"✅ Sucesso: E-mail enviado para {len(destinatarios)} destinatário(s).")
            
        except smtplib.SMTPAuthenticationError as e:
            print(f"❌ Erro de Autenticação retornado pelo Brevo:\n{e}")
        except Exception as e:
            print(f"❌ Erro ao enviar e-mail: {e}")


# ==========================================
# Execução
# ==========================================
if __name__ == "__main__":

    notificador = NotificadorEmail(
        smtp_server=SMTP_SERVER, 
        smtp_port=SMTP_PORT, 
        login_smtp=LOGIN_SMTP, 
        senha=SENHA_KEY
    )
    
    # Se EMAIL_REMETENTE não estiver no .env, usa o LOGIN_SMTP como fallback
    remetente_final = EMAIL_REMETENTE if EMAIL_REMETENTE else LOGIN_SMTP

    notificador.disparar(
        remetente=remetente_final,
        destinatarios=["enfermeirobraian@gmail.com","anne_chaves@outlook.com","lidiane.marin@hotmail.com"],
        assunto="teste envio qrcode",
        corpo="Olá, segue em anexo a imagem do QR Code de teste.",
        caminho_imagem=r"C:\Users\WEMBLEY.MACEDO\Desktop\qrcode_retirada_135ba04f-7190-4918-ba62-6ad8f163aebc.png"
    )
