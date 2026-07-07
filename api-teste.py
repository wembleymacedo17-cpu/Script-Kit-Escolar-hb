from fastapi import FastAPI


app = FastAPI()

teste = { 
    "nome": "John Doe",                       ###  AQUI SERia um select que BUSCARIA NO BANCO DE DADOS ? 
    "idade": 30,
    "email": "john.doe@example.com" 

}
#------------------------ Criando a rota de teste ------------------------#

@app.get("/")                                 ####  aQUI FICARIA OUQE NO MEU P´ROJETO  ?:
def home():
    return  {"busca": teste["nome"], "idade": teste["idade"]}    


#-------------------------

