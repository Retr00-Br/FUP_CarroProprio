import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
from database import carregar_dados_expedicao, salvar_romaneios_db, atualizar_status_db

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Master Expedição - Sprint 1",
    page_icon="🚚",
    layout="wide"
)

st.sidebar.title("🚚 Controle Logístico - Sprint 1")
st.sidebar.markdown("---")
modo_visao = st.sidebar.radio(
    "Selecione o Painel:",
    [
        "📊 Dashboard Geral", 
        "📤 Bipagem - Saída Expedição", 
        "📥 Bipagem - Retorno Carga", 
        "📈 Gráfico de Pendências de Retorno",
        "⚙️ Importação de Romaneios"
    ]
)

# Carregamento do DataFrame principal
df_principal = carregar_dados_expedicao()

# ==============================================================================
# MODO: DASHBOARD GERAL (Com Plotly e Filtro de Calendário/Mês)
# ==============================================================================
if modo_visao == "📊 Dashboard Geral":
    st.title("📊 Painel Central de Controle de Entregas")
    
    if df_principal.empty:
        st.info("ℹ️ Banco de dados vazio. Realize a importação da planilha de romaneios na aba de configurações.")
    else:
        # Filtro de Período / Mês
        st.subheader("📅 Filtro de Competência / Carregamento")
        if "data_emissao" in df_principal.columns:
            df_principal["data_emissao"] = pd.to_datetime(df_principal["data_emissao"], errors="coerce")
            anos_disponiveis = sorted(df_principal["data_emissao"].dt.year.dropna().unique())
            
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                ano_sel = st.selectbox("Selecione o Ano:", options=anos_disponiveis if anos_disponiveis else [datetime.now().year])
            
            df_filtrado = df_principal[df_principal["data_emissao"].dt.year == ano_sel]
        else:
            df_filtrado = df_principal

        st.markdown("---")
        
        # KPIs Principais
        kpi1, kpi2, kpi3 = st.columns(3)
        total_notas = len(df_filtrado)
        faturamento = df_filtrado["valor_nota"].sum() if "valor_nota" in df_filtrado.columns else 0.0
        total_romaneios = df_filtrado["romaneio"].nunique() if "romaneio" in df_filtrado.columns else 0

        kpi1.metric("Volume de Notas Fiscais", f"{total_notas} NFs")
        kpi2.metric("Faturamento Consolidado", f"R$ {faturamento:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        kpi3.metric("Romaneios Ativos", f"{total_romaneios}")

        st.markdown("---")
        
        # Gráficos Interativos com Plotly
        col_g1, col_g2 = st.columns(2)
        
        with col_g1:
            st.subheader("🏆 Top Transportadoras por Romaneios")
            if "transportadora" in df_filtrado.columns and not df_filtrado.empty:
                df_transp = df_filtrado.groupby("transportadora")["romaneio"].nunique().reset_index()
                fig_transp = px.bar(df_transp, x="transportadora", y="romaneio", title="Romaneios por Transportadora", template="plotly_white")
                st.plotly_chart(fig_transp, use_container_width=True)
            else:
                st.info("Sem dados de transportadora disponíveis.")

        with col_g2:
            st.subheader("👤 Notas Carregadas por Funcionário")
            if "funcionario_carregamento" in df_filtrado.columns and not df_filtrado.empty:
                df_func = df_filtrado.groupby("funcionario_carregamento")["numero_nf"].count().reset_index()
                fig_func = px.pie(df_func, names="funcionario_carregamento", values="numero_nf", title="Distribuição por Funcionário", hole=0.4, template="plotly_white")
                st.plotly_chart(fig_func, use_container_width=True)
            else:
                st.info("Sem dados de funcionários disponíveis.")

# ==============================================================================
# MODO: BIPAGEM - SAÍDA EXPEDIÇÃO (Simplificado com número do romaneio)
# ==============================================================================
elif modo_visao == "📤 Bipagem - Saída Expedição":
    st.title("📤 Controle de Fluxo - Saída da Doca")
    
    if df_principal.empty:
        st.warning("📋 Banco de dados vazio.")
    else:
        romaneios_disponiveis = sorted(df_principal["romaneio"].dropna().astype(str).unique())
        romaneio_sel = st.selectbox("📋 Digite ou Selecione o Número do Romaneio:", romaneios_disponiveis)
        
        df_viagem = df_principal[df_principal["romaneio"].astype(str) == romaneio_sel]
        
        if not df_viagem.empty:
            st.success(f"Romaneio selecionado com {len(df_viagem)} notas associadas.")
            
            nf_bipada = st.text_input("Bipagem de Saída (Número da NF):", placeholder="Insira o número da nota...")
            if nf_bipada:
                if nf_bipada in df_viagem["numero_nf"].astype(str).values:
                    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    atualizar_status_db(nf_bipada, "status_ida", "EXPEDIDO", "data_carregamento_ida", agora)
                    st.success(f"Nota Fiscal {nf_bipada} marcada como expedida com sucesso!")
                    st.rerun()
                else:
                    st.error("❌ A Nota Fiscal bipada não pertence a este romaneio.")
                    
            st.markdown("---")
            st.dataframe(df_viagem, use_container_width=True)

# ==============================================================================
# MODO: BIPAGEM - RETORNO CARGA
# ==============================================================================
elif modo_visao == "📥 Bipagem - Retorno Carga":
    st.title("📥 Prestação de Contas - Retorno de Carga")
    
    if df_principal.empty:
        st.warning("📋 Banco de dados vazio.")
    else:
        romaneios_ret = sorted(df_principal["romaneio"].dropna().astype(str).unique())
        romaneio_sel_ret = st.selectbox("📋 Selecione o Romaneio em Retorno:", romaneios_ret)
        
        df_viagem_ret = df_principal[df_principal["romaneio"].astype(str) == romaneio_sel_ret]
        
        if not df_viagem_ret.empty:
            nf_retorno = st.text_input("Bipagem de Retorno / Canhoto (Número da NF):", placeholder="Insira a NF que retornou...")
            if nf_retorno:
                if nf_retorno in df_viagem_ret["numero_nf"].astype(str).values:
                    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    atualizar_status_db(nf_retorno, "status_volta", "RETORNADO / CANHOTO OK", "data_retorno_volta", agora)
                    st.success(f"Retorno da NF {nf_retorno} registrado com sucesso!")
                    st.rerun()
                else:
                    st.error("❌ A Nota Fiscal não pertence a este romaneio.")
            
            st.markdown("---")
            st.dataframe(df_viagem_ret, use_container_width=True)

# ==============================================================================
# MODO: GRÁFICO DE PENDÊNCIAS DE RETORNO (Com filtro de transportadora)
# ==============================================================================
elif modo_visao == "📈 Gráfico de Pendências de Retorno":
    st.title("📈 Monitoramento de Pendências de Retorno por Transportadora")
    
    if df_principal.empty:
        st.info("Sem dados cadastrados.")
    else:
        transportadoras = sorted(df_principal["transportadora"].dropna().unique()) if "transportadora" in df_principal.columns else []
        transp_escolhida = st.selectbox("Selecione a Transportadora:", transportadoras)
        
        if transp_escolhida:
            df_transp_view = df_principal[df_principal["transportadora"] == transp_escolhida].copy()
            
            # Exclui notas que possuem ressalva (ida ou volta) para evitar duplicidade de pendência
            if "ressalva_ida" in df_transp_view.columns and "ressalva_volta" in df_transp_view.columns:
                df_validas = df_transp_view[(df_transp_view["ressalva_ida"].isna()) & (df_transp_view["ressalva_volta"].isna())]
            else:
                df_validas = df_transp_view
                
            # Gráfico comparativo de Notas Retornadas vs Pendentes
            if "status_volta" in df_validas.columns:
                df_validas["status_pendencia"] = df_validas["status_volta"].apply(lambda x: "Retornado" if x == "RETORNADO / CANHOTO OK" else "Pendente")
                df_contagem = df_validas["status_pendencia"].value_counts().reset_index()
                df_contagem.columns = ["Status", "Quantidade"]
                
                fig_pend = px.bar(df_contagem, x="Status", y="Quantidade", color="Status", title=f"Status de Retorno - {transp_escolhida}", template="plotly_white")
                st.plotly_chart(fig_pend, use_container_width=True)
            
            st.subheader("📋 Relação Completa de Notas da Transportadora")
            st.dataframe(df_transp_view, use_container_width=True)

# ==============================================================================
# MODO: IMPORTAÇÃO DE ROMANEIOS (Substitui XML e elimina divergências)
# ==============================================================================
elif modo_visao == "⚙️ Importação de Romaneios":
    st.title("⚙️ Importação de Dados via Planilha de Romaneios")
    st.markdown("Faça o upload da planilha oficial de romaneios para alimentar o sistema.")
    
    arquivo_upload = st.file_uploader("Carregar Planilha de Romaneios (CSV ou Excel)", type=["csv", "xlsx"])
    
    if arquivo_upload is not None:
        try:
            if arquivo_upload.name.endswith('.csv'):
                df_novo = pd.read_csv(arquivo_upload)
            else:
                df_novo = pd.read_excel(arquivo_upload)
                
            st.write("Pré-visualização dos dados carregados:")
            st.dataframe(df_novo.head(), use_container_width=True)
            
            if st.button("💾 Salvar e Atualizar Base de Dados"):
                sucesso = salvar_romaneios_db(df_novo)
                if sucesso:
                    st.success("Base de dados alimentada com sucesso a partir da planilha!")
                else:
                    st.error("Erro ao salvar dados.")
        except Exception as e:
            st.error(f"Erro ao processar arquivo: {e}")