import streamlit as st
import requests
import time
import cv2
import numpy as np
from dotenv import load_dotenv
import os

load_dotenv()  



API_BASE_URL = os.getenv("API_BASE_URL")

st.set_page_config(page_title="Entrega de Kits", page_icon="📦", layout="centered")

# --- CONTROLE DE ESTADOS ---
if 'dados_lidos' not in st.session_state:
    st.session_state.dados_lidos = None

if 'codigo_extraido' not in st.session_state:
    st.session_state.codigo_extraido = None

# Callback para o campo de digitação/pistola USB
def submeter_codigo():
    # Remove o prefixo caso a pistola leia o QR Code completo com a tag
    codigo_limpo = st.session_state.input_codigo.replace("RETIRADA_KIT:", "").strip()
    st.session_state.codigo_extraido = codigo_limpo
    st.session_state.input_codigo = ""

st.title("📦 Sistema de Entrega - Kits Escolares")
st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.markdown("### 📷 Usar Câmera")
    foto_camera = st.camera_input("Tire a foto do QR Code", label_visibility="collapsed")
    
    if foto_camera:
        file_bytes = np.asarray(bytearray(foto_camera.read()), dtype=np.uint8)
        img = cv2.imdecode(file_bytes, 1)
        
        detector = cv2.QRCodeDetector()
        valor_qr, bbox, straight_qrcode = detector.detectAndDecode(img)
        
        if valor_qr:
            # Remove o prefixo lido pela câmera e guarda só o UUID
            st.session_state.codigo_extraido = valor_qr.replace("RETIRADA_KIT:", "").strip()
        else:
            st.warning("👀 Não foi possível ler o QR Code. Evite reflexos e tente focar melhor a imagem.")

with col2:
    st.markdown("### ⌨️ Pistola USB / Digitação")
    st.text_input(
        "Código:", 
        key="input_codigo", 
        placeholder="Bipe com o leitor ou digite...",
        on_change=submeter_codigo 
    )

# --- BUSCA DE DADOS ---
if st.session_state.codigo_extraido:
    try:
        resposta = requests.get(f"{API_BASE_URL}/info/{st.session_state.codigo_extraido}")
        if resposta.status_code == 200:
            st.session_state.dados_lidos = resposta.json()
        elif resposta.status_code == 404:
            st.error("❌ Código não localizado no banco de dados.")
            st.session_state.dados_lidos = None
    except requests.exceptions.ConnectionError:
        st.error("🔌 Erro de conexão com a API. Verifique se o FastAPI está rodando.")
        
    st.session_state.codigo_extraido = None

st.markdown("---")

# --- EXIBIÇÃO E BOTÃO DE BAIXA ---
if st.session_state.dados_lidos:
    dados = st.session_state.dados_lidos
    
    st.markdown(f"<h2 style='text-align: center; color: #1f77b4;'>Colaborador ID: {dados['id_colaborador']}</h2>", unsafe_allow_html=True)
    
    if dados["status"] == "ENTREGUE":
        st.error(f"⚠️ ATENÇÃO: Este kit já consta como ENTREGUE!")
    else:
        st.info(f"**Status Atual:** {dados['status']} | **Total de Kits:** {dados['qtd_kits']}")
        
        st.markdown("### 👨‍👩‍👧 Dependentes e Kits:")
        for dependente in dados["dependentes"]:
            st.success(f"**Filho(a):** {dependente['nome_filho']} ➔ **Kit:** {dependente['kit_escolhido']}")
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        if st.button("✅ CONFIRMAR ENTREGA E DAR BAIXA", use_container_width=True, type="primary"):
            payload = {"codigo_retirada": dados["codigo_retirada"]}
            res_baixa = requests.put(f"{API_BASE_URL}/baixa", json=payload)
            
            if res_baixa.status_code == 200:
                st.success("🎉 **Maravilha! Entrega registrada com sucesso.** Pode liberar os kits para o colaborador!")
                
                st.markdown("<h1 style='text-align: center; font-size: 80px; color: #28a745; margin-top: 20px;'>RH 4.0 💪</h1>", unsafe_allow_html=True)
                
                time.sleep(4)
                
                st.session_state.dados_lidos = None
                st.rerun()
            else:
                st.error("❌ Ocorreu um erro ao tentar dar a baixa. Verifique com o suporte.")