"""
API do sistema Kit Escolar.

Responsável pela parte do fluxo que acontece DEPOIS que o colaborador já
finalizou o cadastro no Streamlit (kit-colaborador.py) e recebeu o QR Code.

Rotas:
- GET  /api/kits/consultar/{codigo_retirada}   -> usada quando a câmera lê o QR Code
- POST /api/kits/dar-baixa/{codigo_retirada}   -> usada quando o funcionário aperta "ENTREGAR KIT"

Para rodar:
    uvicorn api_baixas:app --reload
"""

from datetime import datetime

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import SessionLocal, Retirada, Colaborador

app = FastAPI(title="API Kit Escolar")

# CORS liberado para qualquer origem: a leitura do QR Code pode vir de um
# app de câmera (AppSheet/Glide) ou de uma página web separada, então não dá
# para restringir a um único domínio conhecido de antemão.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===================== DEPENDÊNCIA DE BANCO =====================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ===================== SCHEMAS (respostas da API) =====================
class RetiradaConsultaResponse(BaseModel):
    codigo_retirada: str
    nome_colaborador: str
    cracha: int
    qtd_kits: int
    resumo_kits: str | None
    status: str
    data_geracao: datetime
    data_entrega: datetime | None


class MensagemResponse(BaseModel):
    mensagem: str


class ErroResponse(BaseModel):
    erro: str


# ===================== ROTAS =====================
@app.get("/")
def home():
    return {"status": "API Kit Escolar no ar"}


@app.get(
    "/api/kits/consultar/{codigo_retirada}",
    response_model=RetiradaConsultaResponse,
    responses={404: {"model": ErroResponse}, 409: {"model": ErroResponse}},
)
def consultar_retirada(codigo_retirada: str, db: Session = Depends(get_db)):
    """
    Chamada assim que a câmera lê o QR Code, ANTES de o funcionário apertar
    qualquer botão. Só mostra os dados na tela; não altera nada no banco.
    """
    retirada = (
        db.query(Retirada)
        .filter(Retirada.codigo_retirada == codigo_retirada)
        .first()
    )

    if not retirada:
        raise HTTPException(status_code=404, detail="Código de retirada não encontrado.")

    if retirada.status == "ENTREGUE":
        # Devolve 409 (conflito) para o front-end distinguir de um 200 normal
        # e mostrar o alerta vermelho "kit já retirado" sem liberar o botão.
        raise HTTPException(status_code=409, detail="Este kit já foi entregue.")

    colaborador = db.query(Colaborador).filter(Colaborador.id == retirada.id_colaborador).first()

    return RetiradaConsultaResponse(
        codigo_retirada=retirada.codigo_retirada,
        nome_colaborador=colaborador.nome if colaborador else "Colaborador não encontrado",
        cracha=colaborador.cracha if colaborador else 0,
        qtd_kits=retirada.qtd_kits,
        resumo_kits=retirada.resumo_kits,
        status=retirada.status,
        data_geracao=retirada.data_geracao,
        data_entrega=retirada.data_entrega,
    )


@app.post(
    "/api/kits/dar-baixa/{codigo_retirada}",
    response_model=MensagemResponse,
    responses={404: {"model": ErroResponse}, 409: {"model": ErroResponse}},
)
def dar_baixa_retirada(codigo_retirada: str, db: Session = Depends(get_db)):
    """
    Chamada quando o funcionário aperta o botão "ENTREGAR KIT",
    depois de já ter visto os dados na tela via /consultar.
    """
    retirada = (
        db.query(Retirada)
        .filter(Retirada.codigo_retirada == codigo_retirada)
        .first()
    )

    if not retirada:
        raise HTTPException(status_code=404, detail="Código de retirada não encontrado.")

    if retirada.status == "ENTREGUE":
        raise HTTPException(status_code=409, detail="Este kit já foi entregue anteriormente.")

    retirada.status = "ENTREGUE"
    retirada.data_entrega = datetime.utcnow()
    db.commit()

    return MensagemResponse(mensagem="Sucesso! Baixa confirmada.")