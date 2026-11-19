import pandas as pd
import plotly.express as px
import streamlit as st
from config import (
    MODALIDADES_OFICIAIS,
    CORES_FAROL,
)
from flow_rules import formatar_brl


def renderizar_aba_graficos(df: pd.DataFrame):
    with st.container(border=True):
        st.markdown("##### 🎛️ Filtros Analíticos — Frota Própria & Técnica")

        mod_selecionadas = st.pills(
            "Modalidade",
            options=MODALIDADES_OFICIAIS,
            default=MODALIDADES_OFICIAIS,
            selection_mode="multi",
            key="pills_graf_mod",
        )

        opcoes_status = sorted(df["status_fluxo"].unique().tolist())
        status_selecionado = st.pills(
            "Status das NFs",
            options=opcoes_status,
            default=opcoes_status,
            selection_mode="multi",
            key="pills_graf_status",
        )

    df_g = df.copy()
    df_g = df_g[df_g["transportadora"].isin(mod_selecionadas)] if mod_selecionadas else df_g.iloc[0:0]
    df_g = df_g[df_g["status_fluxo"].isin(status_selecionado)] if status_selecionado else df_g.iloc[0:0]

    if df_g.empty:
        st.info("Selecione ao menos uma modalidade e um status acima para visualizar os indicadores.")
        return

    total_nfs = len(df_g)
    na_mao = int(df_g["nf_na_mao"].sum())
    pct_retorno = (na_mao / total_nfs * 100.0) if total_nfs > 0 else 0.0
    valor_total = float(df_g["valor_nf"].sum())

    concluidas_mao = df_g[df_g["dt_retorno_mao"].notna() & df_g["dt_saida"].notna()].copy()
    if not concluidas_mao.empty:
        dias_medio = (concluidas_mao["dt_retorno_mao"] - concluidas_mao["dt_saida"]).dt.days.clip(lower=0).mean()
        tempo_medio_fmt = f"{dias_medio:.1f} dias"
    else:
        tempo_medio_fmt = "—"

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Taxa de Retorno na Mão", f"{pct_retorno:.1f}%")
    k2.metric("Tempo Médio Retorno NF", tempo_medio_fmt)
    k3.metric("Valor Embarcado (R$ NF)", formatar_brl(valor_total))
    k4.metric("NFs Aguardando Retorno", int((~df_g["nf_na_mao"]).sum()))

    st.write("")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Status das NFs por Modalidade")
        resumo = df_g.groupby(["transportadora", "status_fluxo"]).size().reset_index(name="Quantidade")
        fig_bar = px.bar(
            resumo,
            x="transportadora",
            y="Quantidade",
            color="status_fluxo",
            color_discrete_map=CORES_FAROL,
            barmode="stack",
            text_auto=True,
        )
        fig_bar.update_layout(
            xaxis_title="",
            yaxis_title="Quantidade de NFs",
            legend_title="Status",
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(t=15, b=15, l=10, r=10),
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    with col2:
        st.subheader("Distribuição Geral de Retorno & Baixa")
        resumo_st = df_g["status_fluxo"].value_counts().reset_index()
        resumo_st.columns = ["Status", "Total"]
        fig_donut = px.pie(
            resumo_st,
            names="Status",
            values="Total",
            color="Status",
            color_discrete_map=CORES_FAROL,
            hole=0.52,
        )
        fig_donut.update_traces(textposition="inside", textinfo="percent+value")
        fig_donut.update_layout(paper_bgcolor="rgba(0,0,0,0)", margin=dict(t=15, b=15, l=10, r=10))
        st.plotly_chart(fig_donut, use_container_width=True)

    st.divider()
    st.subheader("Resumo Consolidado por Veículo / Modalidade")
    linhas = []
    for mod, grp in df_g.groupby("transportadora"):
        tot = len(grp)
        mao = int(grp["nf_na_mao"].sum())
        linhas.append({
            "Modalidade": mod,
            "Total NFs": tot,
            "Valor Total (R$)": formatar_brl(float(grp["valor_nf"].sum())),
            "NFs na Mão": mao,
            "Aguardando Retorno": tot - mao,
            "Pendente Baixa ERP": int((grp["status_fluxo"] == "🟡 NF na Mão (Pendente Baixa ERP)").sum()),
            "Taxa de Retorno (%)": f"{(mao / tot * 100.0):.1f}%" if tot > 0 else "0.0%",
        })
    st.dataframe(pd.DataFrame(linhas), use_container_width=True, hide_index=True)