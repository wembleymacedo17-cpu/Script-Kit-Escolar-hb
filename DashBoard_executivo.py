import streamlit as st
import pandas as pd
from datetime import datetime
import plotly.express as px 
from database import engine

# Carregamento dos dados
df_dependentes = pd.read_sql("SELECT * FROM dependentes", con=engine)
df_logs = pd.read_sql("SELECT * FROM logs_auditoria", con=engine)
df_colaborador = pd.read_sql("SELECT * FROM colaboradores", con=engine)
df_retiradas = pd.read_sql("SELECT * FROM retiradas", con=engine)
df_escolhas_kits = pd.read_sql("SELECT * FROM escolhas_kits", con=engine)







# Tratamento prévio da idade e faixa etária (necessário para o filtro funcionar completo se precisar)
df_dependentes['data_nascimento'] = pd.to_datetime(df_dependentes['data_nascimento'])
hoje = pd.to_datetime('today')
df_dependentes['idade'] = (hoje - df_dependentes['data_nascimento']).dt.days // 365

limites = [0, 4, 7, 11, 15, 19]
rotulos = ['0-3 anos', '4-6 anos', '7-10 anos', '11-14 anos', '15-18 anos']

df_dependentes['faixa_etaria'] = pd.cut(
    df_dependentes['idade'], 
    bins=limites, 
    labels=rotulos, 
    right=False
)

# ========================== BARRA LATERAL (FILTROS) ==========================
st.sidebar.header("🔍 Filtros Globais")

# 1. Filtro de Gênero
generos_disponiveis = ["Todos"] + list(df_dependentes['genero'].dropna().unique())
genero_selecionado = st.sidebar.selectbox("Filtrar por Gênero", options=generos_disponiveis)

# 2. Filtro de Faixa Etária
faixas_disponiveis = ["Todas"] + rotulos
faixa_selecionada = st.sidebar.selectbox("Filtrar por Faixa Etária", options=faixas_disponiveis)

# Aplicando os filtros no DataFrame base
df_filtrado = df_dependentes.copy()

if genero_selecionado != "Todos":
    df_filtrado = df_filtrado[df_filtrado['genero'] == genero_selecionado]

if faixa_selecionada != "Todas":
    df_filtrado = df_filtrado[df_filtrado['faixa_etaria'] == faixa_selecionada]

# ========================== 1. TOTAIS E MÉDIA DE DEPENDENTES ==========================
# IMPORTANTE: Usamos 'df_filtrado' para que os números reajam às escolhas da barra lateral!
qtd_dependentes = len(df_filtrado)
qtd_colaboradores_com_dep = df_filtrado['id_colaborador'].nunique()

if qtd_colaboradores_com_dep > 0:
    media_dependente = qtd_dependentes / qtd_colaboradores_com_dep
else:
    media_dependente = 0.0

# ========================== 2. EXIBIÇÃO NO STREAMLIT (KPIs) ==========================
st.title("📊 Painel Executivo - Análise de Cadastros")

col1, col2, col3 = st.columns(3)

with col1:
    st.metric(label="Total de Dependentes (Filtrado)", value=qtd_dependentes)

with col2:
    st.metric(label="Colaboradores Participantes", value=qtd_colaboradores_com_dep)

with col3:
    st.metric(label="Média de Dependentes / Colaborador", value=f"{media_dependente:.2f}")

st.divider()

# ========================== 3. GRÁFICOS DE FAIXA ETÁRIA E GÊNERO ==========================
col_graf1, col_graf2 = st.columns(2)

with col_graf1:
    # Gráfico de Gênero (Rosca) baseado nos dados filtrados
    df_genero = df_filtrado['genero'].value_counts().reset_index()
    df_genero.columns = ['Gênero', 'Quantidade']
    
    fig_genero = px.pie(
        df_genero, 
        names='Gênero', 
        values='Quantidade', 
        hole=0.4, 
        title="Distribuição por Gênero"
    )
    st.plotly_chart(fig_genero, use_container_width=True)

with col_graf2:
    # Gráfico de Faixa Etária (Colunas) baseado nos dados filtrados
    df_faixa = df_filtrado['faixa_etaria'].value_counts().reset_index()
    df_faixa.columns = ['Faixa Etária', 'Quantidade']
    df_faixa = df_faixa.sort_values('Faixa Etária')
    
    fig_faixa = px.bar(
        df_faixa, 
        x='Faixa Etária', 
        y='Quantidade', 
        title="Distribuição por Faixa Etária",
        text='Quantidade'
    )
    fig_faixa.update_traces(textposition='outside')
    st.plotly_chart(fig_faixa, use_container_width=True)

st.divider()
st.subheader("📈 Análise de Comportamento e Processos")

# ========================== 4. VOLUME DE CADASTROS POR DIA ==========================
# Trunca a data com hora para apenas a data (YYYY-MM-DD)
df_filtrado['data_cadastro_dia'] = pd.to_datetime(df_filtrado['data_cadastro']).dt.date

df_cadastros_dia = (
    df_filtrado.groupby('data_cadastro_dia')['id_dependente']
    .count()
    .reset_index()
)
df_cadastros_dia.columns = ['Data', 'Cadastros']
df_cadastros_dia = df_cadastros_dia.sort_values('Data')

fig_linha = px.line(
    df_cadastros_dia,
    x='Data',
    y='Cadastros',
    markers=True,
    title="Volume Diário de Cadastros (Evolução Temporal)",
    labels={'Data': 'Data do Cadastro', 'Cadastros': 'Qtd. Cadastros'}
)
fig_linha.update_traces(line_color='#1F77B4', line_width=3)
st.plotly_chart(fig_linha, use_container_width=True)

# ========================== 5. FLUXOS E ESCOLARIDADE ==========================
col_comp1, col_comp2 = st.columns(2)

with col_comp1:
    # Contagem por Fluxo de Documentos (A1, A2, B1, etc.)
    df_fluxo = df_filtrado['fluxo_documento'].value_counts().reset_index()
    df_fluxo.columns = ['Fluxo', 'Quantidade']
    
    fig_fluxo = px.bar(
        df_fluxo,
        x='Quantidade',
        y='Fluxo',
        orientation='h',
        text='Quantidade',
        title="Cadastros por Fluxo de Origem",
        color='Fluxo',
        color_discrete_sequence=px.colors.qualitative.Pastel
    )
    fig_fluxo.update_traces(textposition='outside')
    st.plotly_chart(fig_fluxo, use_container_width=True)

with col_comp2:
    # Distribuição por Escolaridade
    df_escolaridade = df_filtrado['escolaridade'].value_counts().reset_index()
    df_escolaridade.columns = ['Escolaridade', 'Quantidade']
    
    fig_escolaridade = px.bar(
        df_escolaridade,
        x='Escolaridade',
        y='Quantidade',
        text='Quantidade',
        title="Distribuição por Nível de Escolaridade",
        color_discrete_sequence=['#2CA02C']
    )
    fig_escolaridade.update_traces(textposition='outside')
    st.plotly_chart(fig_escolaridade, use_container_width=True)

# ========================== 6. RANKING DE CARGOS CADASTRADOS ==========================
# Merge com o DataFrame de Colaboradores para resgatar os nomes dos cargos
df_dep_cargo = pd.merge(
    df_filtrado, 
    df_colaborador[['cracha', 'titulo_reduzido_cargo']], 
    left_on='id_colaborador', 
    right_on='cracha', 
    how='left'
)

df_cargos_rank = (
    df_dep_cargo['titulo_reduzido_cargo']
    .value_counts()
    .reset_index()
    .head(20)  # Top 10 cargos com mais dependentes
)
df_cargos_rank.columns = ['Cargo', 'Quantidade de Dependentes']

fig_cargos = px.bar(
    df_cargos_rank,
    x='Quantidade de Dependentes',
    y='Cargo',
    orientation='h',
    text='Quantidade de Dependentes',
    title="Top 10 Cargos dos Colaboradores com Dependentes Cadastrados",
    color_discrete_sequence=['#FF7F0E']
)
fig_cargos.update_layout(yaxis={'categoryorder': 'total ascending'})  # Ordena do maior para o menor
fig_cargos.update_traces(textposition='outside')

st.plotly_chart(fig_cargos, use_container_width=True)


st.divider()
st.subheader("💰 Análise Financeira e Logística de Kits")

# ========================== 1. UNINDO DEPENDENTES E ESCOLHAS DE KITS ==========================
df_kits_completo = pd.merge(
    df_filtrado,
    df_escolhas_kits[['id_dependente', 'kit_escolhido', 'data_escolha']],
    on='id_dependente',
    how='inner'
)

# ========================== 2. SIMULADOR DE CUSTOS (SIDEBAR OU CORPO) ==========================
st.sidebar.markdown("---")
st.sidebar.header("💵 Simulação de Valoração dos Kits")

# Entradas dinâmicas para simulação de preços unitários (R$)
preco_infantil = st.sidebar.number_input("Preço Kit Infantil (R$)", min_value=0.0, value=80.0, step=5.0)
preco_fund_1 = st.sidebar.number_input("Preço Kit Fundamental I (R$)", min_value=0.0, value=110.0, step=5.0)
preco_fund_2 = st.sidebar.number_input("Preço Kit Fundamental II (R$)", min_value=0.0, value=130.0, step=5.0)
preco_medio = st.sidebar.number_input("Preço Kit Ensino Médio (R$)", min_value=0.0, value=150.0, step=5.0)

# Mapeamento de preços por escolaridade
mapa_precos = {
    'Educação Infantil': preco_infantil,
    'Ensino Fundamental I': preco_fund_1,
    'Ensino Fundamental II': preco_fund_2,
    'Ensino Médio': preco_medio
}

# Atribui o valor unitário estimado a cada dependente com base na escolaridade
df_kits_completo['valor_unitario'] = df_kits_completo['escolaridade'].map(mapa_precos).fillna(0.0)

# ========================== 3. CÁLCULO DE GASTOS E KPIs FINANCEIROS ==========================
custo_total_simulado = df_kits_completo['valor_unitario'].sum()
total_kits_escolhidos = len(df_kits_completo)

# Consolidação do gasto por Nível Escolar
df_gastos_nivel = (
    df_kits_completo.groupby('escolaridade')
    .agg(
        Qtd_Kits=('id_dependente', 'count'),
        Custo_Total=('valor_unitario', 'sum')
    )
    .reset_index()
)

# Exibição de KPIs Financeiros no topo da seção
col_fin1, col_fin2, col_fin3 = st.columns(3)

with col_fin1:
    st.metric(label="Custo Total Simulado", value=f"R$ {custo_total_simulado:,.2f}")

with col_fin2:
    st.metric(label="Total de Kits Selecionados", value=total_kits_escolhidos)

with col_fin3:
    ticket_medio = (custo_total_simulado / total_kits_escolhidos) if total_kits_escolhidos > 0 else 0.0
    st.metric(label="Custo Médio por Kit", value=f"R$ {ticket_medio:,.2f}")

# ========================== 4. VISUALIZAÇÃO DE GASTOS E RANKING DE KITS ==========================
col_log1, col_log2 = st.columns(2)

with col_log1:
    # Gráfico de Projeção Financeira por Nível Escolar
    fig_gastos = px.bar(
        df_gastos_nivel,
        x='escolaridade',
        y='Custo_Total',
        text='Custo_Total',
        title="Gasto Projetado por Nível Escolar (R$)",
        labels={'escolaridade': 'Escolaridade', 'Custo_Total': 'Custo Total (R$)'},
        color_discrete_sequence=['#27AE60']
    )
    fig_gastos.update_traces(texttemplate='R$ %{text:,.2f}', textposition='outside')
    st.plotly_chart(fig_gastos, use_container_width=True)

with col_log2:
    # Ranking dos Modelos de Kits Mais Solicitados
    df_ranking_kits = df_kits_completo['kit_escolhido'].value_counts().reset_index()
    df_ranking_kits.columns = ['Modelo do Kit', 'Quantidade']
    
    fig_ranking_kits = px.bar(
        df_ranking_kits,
        x='Quantidade',
        y='Modelo do Kit',
        orientation='h',
        text='Quantidade',
        title="Ranking de Modelos de Kits Solicitados",
        color='Quantidade',
        color_continuous_scale='Viridis'
    )
    fig_ranking_kits.update_traces(textposition='outside')
    fig_ranking_kits.update_layout(yaxis={'categoryorder': 'total ascending'})
    st.plotly_chart(fig_ranking_kits, use_container_width=True)

st.divider()
st.subheader("🤖 Eficiência da Inteligência Artificial e Auditoria")

# ========================== 1. PROCESSAMENTO DE DADOS DA IA ==========================
# Categorização da taxa de sucesso da IA no df_filtrado
def classificar_status_ia(linha):
    # Se o documento passou direto e aceito pela IA sem quarentena
    if linha.get('aceite_ia') == True and (pd.isna(linha.get('revisao_rh')) or linha.get('revisao_rh') == ''):
        return 'Aprovado Direto (IA)'
    elif 'Revisão Manual' in str(linha.get('revisao_rh')) or linha.get('aceite_ia') == False:
        return 'Quarentena / Revisão RH'
    else:
        return 'Processado RH'

df_filtrado['status_processamento'] = df_filtrado.apply(classificar_status_ia, axis=1)

# Contagem das categorias
df_status_ia = df_filtrado['status_processamento'].value_counts().reset_index()
df_status_ia.columns = ['Status', 'Quantidade']

# Cálculo de Percentuais para KPIs
total_analisados = len(df_filtrado)
qtd_aprovado_ia = df_filtrado[df_filtrado['status_processamento'] == 'Aprovado Direto (IA)'].shape[0]
qtd_quarentena = df_filtrado[df_filtrado['status_processamento'] == 'Quarentena / Revisão RH'].shape[0]

taxa_automacao = (qtd_aprovado_ia / total_analisados * 100) if total_analisados > 0 else 0.0
taxa_quarentena = (qtd_quarentena / total_analisados * 100) if total_analisados > 0 else 0.0

# ========================== 2. KPIs DE EFICIÊNCIA ==========================
col_ia1, col_ia2, col_ia3 = st.columns(3)

with col_ia1:
    st.metric(
        label="Taxa de Aprovação Direta (IA)", 
        value=f"{taxa_automacao:.1f}%",
        help="Percentual de cadastros validados automaticamente pela IA sem necessidade de intervenção humana."
    )

with col_ia2:
    st.metric(
        label="Taxa de Quarentena (Bypass / RH)", 
        value=f"{taxa_quarentena:.1f}%",
        help="Percentual de cadastros encaminhados para a esteira de validação manual do RH."
    )

with col_ia3:
    st.metric(
        label="Total de Documentos Analisados", 
        value=total_analisados
    )

# ========================== 3. VISUALIZAÇÕES DE EFICIÊNCIA E REJEIÇÕES ==========================
col_graf_ia1, col_graf_ia2 = st.columns(2)

with col_graf_ia1:
    # Gráfico de Rosca: Desempenho da IA vs. Quarentena
    fig_status_ia = px.pie(
        df_status_ia,
        names='Status',
        values='Quantidade',
        hole=0.4,
        title="Desempenho da Validação (IA vs. Quarentena RH)",
        color='Status',
        color_discrete_map={
            'Aprovado Direto (IA)': '#2ECC71',
            'Quarentena / Revisão RH': '#E74C3C',
            'Processado RH': '#3498DB'
        }
    )
    fig_status_ia.update_traces(textinfo='percent+label')
    st.plotly_chart(fig_status_ia, use_container_width=True)

with col_graf_ia2:
    # Gráfico de Barras: Motivos de Reprovação/Divergência detectados pela IA
    df_reprovacoes = (
        df_filtrado[df_filtrado['motivo_reprova_ia'].notnull() & (df_filtrado['motivo_reprova_ia'] != '')]
        ['motivo_reprova_ia']
        .value_counts()
        .reset_index()
    )
    df_reprovacoes.columns = ['Motivo da Rejeição', 'Quantidade']

    if not df_reprovacoes.empty:
        fig_reprova = px.bar(
            df_reprovacoes,
            x='Quantidade',
            y='Motivo da Rejeição',
            orientation='h',
            text='Quantidade',
            title="Principais Motivos de Reprovação de Documentos (IA)",
            color_discrete_sequence=['#E67E22']
        )
        fig_reprova.update_traces(textposition='outside')
        fig_reprova.update_layout(yaxis={'categoryorder': 'total ascending'})
        st.plotly_chart(fig_reprova, use_container_width=True)
    else:
        st.info("🎉 Nenhuma reprovação registrada na base de dados selecionada.")    