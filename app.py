import streamlit as st
from config import aplicar_estilo_higimed, buscar_imagem_corporativa
from parser_erp import carregar_extrato_erp
from database import sincronizar_erp_backend, carregar_dados, aplicar_upsert_dataframe
from flow_rules import enriquecer_fluxo_frota, formatar_brl
from ui_operacao import renderizar_aba_operacao
from ui_graficos import renderizar_aba_graficos

st.set_page_config(
    page_title="FUPHigimed | Frota Própria & Técnica",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="collapsed",
)
aplicar_estilo_higimed()

sincronizar_erp_backend()

logo_path = buscar_imagem_corporativa(["logomaster.webp"], ["logo"])
caminhao_path = buscar_imagem_corporativa(["caminhãomaster.jpg", "caminhaomaster.jpg"], ["caminhao", "caminhão", "truck"])

with st.container():
    st.markdown('<div class="banner-institucional">', unsafe_allow_html=True)
    col_logo, col_titulo, col_caminhao = st.columns([1.3, 3.2, 1.5], vertical_alignment="center")

    with col_logo:
        if logo_path:
            st.image(logo_path, use_container_width=True)
        else:
            st.markdown("### MASTER HIGIMED")

    with col_titulo:
        st.markdown(
            """
            <div style="padding-left: 10px;">
                <p class="titulo-sistema">FUPHigimed — Controle de Frota Própria &amp; Técnica</p>
                <p class="subtitulo-sistema">Distribuindo Saúde e Bem Estar · Saídas, Retorno de NF em Mão &amp; Baixa ERP</p>
                <span class="badge-transportadoras">Carro Próprio · Carro Técnica</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_caminhao:
        if caminhao_path:
            st.image(caminhao_path, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

df_raw = carregar_dados()

if not df_raw.empty:
    df = enriquecer_fluxo_frota(df_raw)
    aba_operacao, aba_graficos = st.tabs(["📋 Operação & Retorno de NFs", "📊 Indicadores da Frota"])

    with aba_operacao:
        renderizar_aba_operacao(df)

    with aba_graficos:
        renderizar_aba_graficos(df)
else:
    st.info("Base aguardando sincronização inicial de Carro Próprio e Carro Técnica do mês atual.")

st.write("")
with st.expander("🔒 Área Restrita — Sincronização Segura do Banco (Sem Git)", expanded=df_raw.empty):
    senha_configurada = st.secrets.get("ADMIN_PASSWORD", "")
    col_auth1, col_auth2 = st.columns([1.2, 2.5])
    with col_auth1:
        senha_digitada = st.text_input("Chave de Acesso Admin", type="password", key="admin_pwd_input")
    with col_auth2:
        if senha_configurada and senha_digitada == senha_configurada:
            arq_memoria = st.file_uploader(
                "Processar extrato de romaneios em memória (não salva arquivo no repositório)",
                type=["xls", "xlsx", "csv", "txt"],
                key="upload_seguro_admin",
            )
            if arq_memoria is not None and st.button("Sincronizar Agora", type="primary"):
                df_novo = carregar_extrato_erp(arq_memoria)
                novos, att = aplicar_upsert_dataframe(df_novo)
                soma_lida = formatar_brl(df_novo["valor_nf"].sum())
                st.success(
                    f"Banco atualizado! {len(df_novo)} NFs processadas ({novos} novas | {att} atualizadas) · "
                    f"Valor total lido: {soma_lida}"
                )
                st.rerun()
        elif senha_digitada:
            st.error("Chave de acesso inválida.")
        else:
            st.caption("Informe a chave administrativa configurada em `st.secrets` para alimentar o banco sem expor planilhas no Git.")