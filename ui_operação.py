import io
import re
from datetime import date
import pandas as pd
import streamlit as st
from config import MODALIDADES_OFICIAIS
from database import (
    atualizar_registro_individual,
    salvar_edicoes_lote,
    registrar_retorno_mao_lote,
)
from flow_rules import formatar_brl


def _to_date_or_none(val):
    if pd.isna(val) or val is None:
        return None
    return pd.to_datetime(val).date()


def _fmt_str_date(val) -> str | None:
    if val is None or pd.isna(val):
        return None
    return pd.to_datetime(val).strftime("%Y-%m-%d")


def _extrair_lista_nfs(texto_busca: str) -> list[str]:
    tokens = re.split(r"[\s,;]+", texto_busca.strip())
    return [t.strip() for t in tokens if t.strip().isdigit()]


def renderizar_aba_operacao(df: pd.DataFrame):
    with st.container(border=True):
        st.markdown("##### 🔎 Busca Rápida por Nota & Filtro da Frota (Mês Atual)")
        r1_c1, r1_c2, r1_c3 = st.columns([1.1, 1.2, 2.0])

        with r1_c1:
            filtro_mod = st.selectbox(
                "Modalidade / Veículo",
                options=["Todas"] + MODALIDADES_OFICIAIS,
                key="op_filtro_mod",
            )
        with r1_c2:
            filtro_mao = st.selectbox(
                "Situação da NF Física",
                options=[
                    "Todas",
                    "Aguardando voltar para mão",
                    "Já voltou para mão",
                    "Sem romaneio",
                ],
                key="op_filtro_mao",
            )
        with r1_c3:
            busca = st.text_input(
                "Buscar NF(s) ou Cliente (aceita várias NFs separadas por vírgula ou espaço)",
                placeholder="Ex: 181410 ou 181410, 181920, 181217 ou nome do cliente...",
                key="op_busca_texto",
            )

        opcoes_status = sorted(df["status_fluxo"].unique().tolist())
        filtro_status = st.multiselect(
            "Status Operacional",
            options=opcoes_status,
            default=opcoes_status,
            key="op_filtro_status",
        )

    df_filtrado = df.copy()
    if filtro_mod != "Todas":
        df_filtrado = df_filtrado[df_filtrado["transportadora"] == filtro_mod]
    if filtro_mao == "Aguardando voltar para mão":
        df_filtrado = df_filtrado[~df_filtrado["nf_na_mao"]]
    elif filtro_mao == "Já voltou para mão":
        df_filtrado = df_filtrado[df_filtrado["nf_na_mao"]]
    elif filtro_mao == "Sem romaneio":
        df_filtrado = df_filtrado[df_filtrado["status_fluxo"] == "🟠 Sem Romaneio (Faturada)"]
    if filtro_status:
        df_filtrado = df_filtrado[df_filtrado["status_fluxo"].isin(filtro_status)]

    nfs_buscadas = []
    if busca.strip():
        nfs_buscadas = _extrair_lista_nfs(busca)
        if len(nfs_buscadas) >= 2:
            df_filtrado = df_filtrado[df_filtrado["nf"].isin(nfs_buscadas)]
        else:
            termo = busca.strip().upper()
            df_filtrado = df_filtrado[
                df_filtrado["nf"].str.upper().str.contains(termo, na=False)
                | df_filtrado["cliente"].str.upper().str.contains(termo, na=False)
            ]

    if nfs_buscadas and not df_filtrado.empty:
        with st.container(border=True):
            st.markdown(f"**📥 Conferência Rápida — {len(df_filtrado)} NF(s) encontrada(s) na busca**")
            b_c1, b_c2, b_c3 = st.columns([1.2, 1.3, 1.5])
            with b_c1:
                data_lote_mao = st.date_input(
                    "Data que voltou para mão",
                    value=date.today(),
                    format="DD/MM/YYYY",
                    key="dt_lote_mao_input",
                )
            with b_c2:
                st.write("")
                st.write("")
                baixar_lote = st.checkbox("Já baixar no ERP também", value=False, key="chk_baixar_lote")
            with b_c3:
                st.write("")
                if st.button("Confirmar Retorno na Mão", type="primary", use_container_width=True):
                    qtd = registrar_retorno_mao_lote(
                        nfs=df_filtrado["nf"].tolist(),
                        data_retorno=data_lote_mao.strftime("%Y-%m-%d"),
                        baixar_erp=baixar_lote,
                    )
                    st.toast(f"{qtd} NF(s) registradas como voltadas para a mão!", icon="✅")
                    st.rerun()

    total_nfs = len(df_filtrado)
    na_mao_qtd = int(df_filtrado["nf_na_mao"].sum())
    pct_retorno = (na_mao_qtd / total_nfs * 100.0) if total_nfs > 0 else 0.0
    valor_total_filtrado = float(df_filtrado["valor_nf"].sum())

    c1, c2, c3, c4, c5, c6 = st.columns([0.85, 1.55, 1.0, 0.95, 0.95, 0.9])
    c1.metric("NFs (Mês Atual)", total_nfs)
    c2.metric("Valor Total (R$ NF)", formatar_brl(valor_total_filtrado))
    c3.metric("Taxa Retorno na Mão", f"{pct_retorno:.1f}%")
    c4.metric("🟢 NF na Mão", na_mao_qtd)
    c5.metric("🔵 Em Rota (Na Rua)", int((df_filtrado["status_fluxo"] == "🔵 Em Rota (Aguardando Retorno)").sum()))
    c6.metric("🟡 Pend. Baixa ERP", int((df_filtrado["status_fluxo"] == "🟡 NF na Mão (Pendente Baixa ERP)").sum()))

    st.write("")

    with st.expander("✏️ Atualizar Dados da NF (Saída / Entrega / Data que Voltou para Mão / Baixa)", expanded=True):
        df_opcoes_nf = df_filtrado if not df_filtrado.empty else df
        if df_opcoes_nf.empty:
            st.info("Nenhuma NF disponível para o filtro selecionado.")
        else:
            sel_col1, sel_col2 = st.columns([1.3, 3])
            with sel_col1:
                nf_selecionada = st.selectbox(
                    "Selecione a NF",
                    options=df_opcoes_nf["nf"].tolist(),
                    key="select_nf_edicao",
                )

            reg = df[df["nf"] == nf_selecionada].iloc[0]

            with sel_col2:
                ultima_att = reg["atualizado_em"] if pd.notna(reg["atualizado_em"]) else "—"
                valor_fmt = formatar_brl(reg["valor_nf"])
                st.markdown(
                    f"**Cliente:** `{reg['cliente']}` &nbsp;|&nbsp; "
                    f"**Veículo:** `{reg['transportadora']}` &nbsp;|&nbsp; "
                    f"**Valor NF:** `{valor_fmt}` &nbsp;|&nbsp; "
                    f"**Status:** {reg['status_fluxo']}<br>"
                    f"<span style='font-size:0.8rem; color:#64748b;'>Última atualização salva: {ultima_att}</span>",
                    unsafe_allow_html=True,
                )

            with st.form(key=f"form_nf_{nf_selecionada}", clear_on_submit=False):
                d1, d2, d3, d4 = st.columns(4)

                with d1:
                    st.date_input(
                        "Dt. Romaneio 🔒 (Imutável)",
                        value=_to_date_or_none(reg["dt_romaneio"]),
                        format="DD/MM/YYYY",
                        disabled=True,
                    )
                with d2:
                    dt_saida_in = st.date_input(
                        "Dia que Saiu",
                        value=_to_date_or_none(reg["dt_saida"]),
                        format="DD/MM/YYYY",
                    )
                with d3:
                    dt_real_in = st.date_input(
                        "Data da Entrega",
                        value=_to_date_or_none(reg["dt_entrega_real"]),
                        format="DD/MM/YYYY",
                    )
                with d4:
                    dt_mao_in = st.date_input(
                        "Data que Voltou para Mão",
                        value=_to_date_or_none(reg["dt_retorno_mao"]),
                        format="DD/MM/YYYY",
                    )

                o1, o2, o3 = st.columns([3.2, 1.1, 1.2])
                with o1:
                    obs_in = st.text_input(
                        "Observação (Motorista / Técnico / Ocorrência)",
                        value=reg["observacao"] or "",
                        placeholder="Ex: Entregue ao recebedor João; canhoto devolvido ao faturamento...",
                    )
                with o2:
                    st.write("")
                    st.write("")
                    baixada_in = st.checkbox(
                        "NF Baixada no ERP",
                        value=bool(reg["nf_baixada_sistema"]),
                    )
                with o3:
                    st.write("")
                    salvar_btn = st.form_submit_button(
                        "💾 Salvar Alterações",
                        type="primary",
                        use_container_width=True,
                    )

                if salvar_btn:
                    atualizar_registro_individual(
                        nf=nf_selecionada,
                        dt_saida=_fmt_str_date(dt_saida_in),
                        dt_entrega_real=_fmt_str_date(dt_real_in),
                        dt_retorno_mao=_fmt_str_date(dt_mao_in),
                        nf_baixada_sistema=baixada_in,
                        observacao=obs_in,
                    )
                    st.toast(f"NF {nf_selecionada} atualizada!", icon="✅")
                    st.rerun()

    st.write("")

    st.subheader(f"Controle de Entregas & Retorno de NFs — Mês Atual ({len(df_filtrado)} NFs)")

    colunas_exibicao = [
        "status_fluxo",
        "tempo_retorno",
        "nf",
        "transportadora",
        "cliente",
        "valor_nf",
        "dt_romaneio",
        "dt_saida",
        "dt_entrega_real",
        "dt_retorno_mao",
        "nf_baixada_sistema",
        "observacao",
    ]

    df_editor = df_filtrado[colunas_exibicao].copy()
    df_editor["nf_baixada_sistema"] = df_editor["nf_baixada_sistema"].astype(bool)

    editado = st.data_editor(
        df_editor,
        use_container_width=True,
        height=470,
        hide_index=True,
        disabled=["status_fluxo", "tempo_retorno", "nf", "transportadora", "cliente", "valor_nf", "dt_romaneio"],
        column_config={
            "status_fluxo": st.column_config.TextColumn("Status", width="medium"),
            "tempo_retorno": st.column_config.TextColumn("Ciclo", width="small"),
            "nf": st.column_config.TextColumn("NF", width="small"),
            "transportadora": st.column_config.TextColumn("Veículo", width="small"),
            "cliente": st.column_config.TextColumn("Cliente", width="large"),
            "valor_nf": st.column_config.NumberColumn("R$ NF", format="R$ %.2f", width="small"),
            "dt_romaneio": st.column_config.DateColumn("Dt. Romaneio 🔒", format="DD/MM/YYYY"),
            "dt_saida": st.column_config.DateColumn("Dia Saída", format="DD/MM/YYYY"),
            "dt_entrega_real": st.column_config.DateColumn("Data Entrega", format="DD/MM/YYYY"),
            "dt_retorno_mao": st.column_config.DateColumn("Voltou p/ Mão", format="DD/MM/YYYY"),
            "nf_baixada_sistema": st.column_config.CheckboxColumn("Baixada ERP?"),
            "observacao": st.column_config.TextColumn("Observação", width="large"),
        },
        key="grade_lote_frota",
    )

    b_col1, b_col2, _ = st.columns([1.4, 1.5, 3])
    with b_col1:
        if st.button("💾 Salvar Alterações da Tabela", type="primary", use_container_width=True):
            df_salvar = editado.copy()
            for col in ["dt_saida", "dt_entrega_real", "dt_retorno_mao"]:
                df_salvar[col] = pd.to_datetime(df_salvar[col], errors="coerce").dt.strftime("%Y-%m-%d")
            salvar_edicoes_lote(df_salvar)
            st.toast("Edições salvas com sucesso!", icon="✅")
            st.rerun()

    with b_col2:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df_filtrado.to_excel(writer, index=False, sheet_name="FrotaHigimed")
        st.download_button(
            label="📥 Exportar Excel (.xlsx)",
            data=buffer.getvalue(),
            file_name=f"FrotaHigimed_{date.today().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )