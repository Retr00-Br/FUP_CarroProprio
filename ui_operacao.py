import io
import re
from datetime import date
import pandas as pd
import streamlit as st
from config import MODALIDADES_OFICIAIS, CORES_FAROL, MOTIVOS_NAO_RETORNO
from database import (
    atualizar_registro_individual,
    salvar_edicoes_lote,
    registrar_retorno_mao_lote,
    registrar_nao_retornou_lote,
    marcar_jundiai_orgao_lote,
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
    mes_atual = date.today().strftime("%Y-%m")
    competencias = sorted([c for c in df["competencia"].unique() if c != "Sem Data"], reverse=True)
    opcoes_periodo = ["Todos os Meses (Banco Completo)"] + competencias
    if "Sem Data" in df["competencia"].values:
        opcoes_periodo.append("Sem Data")
    idx_padrao = opcoes_periodo.index(mes_atual) if mes_atual in opcoes_periodo else 0

    with st.container(border=True):
        st.markdown("##### 🔎 Busca Rápida por Nota, Período & Ticagem Jundiaí / Órgãos Públicos")
        r1_c1, r1_c2, r1_c3, r1_c4 = st.columns([1.15, 1.0, 1.35, 1.8])

        with r1_c1:
            filtro_periodo = st.selectbox(
                "Competência (Histórico)",
                options=opcoes_periodo,
                index=idx_padrao,
                key="op_filtro_periodo",
            )
        with r1_c2:
            filtro_mod = st.selectbox(
                "Veículo",
                options=["Todas"] + MODALIDADES_OFICIAIS,
                key="op_filtro_mod",
            )
        with r1_c3:
            filtro_orgao = st.selectbox(
                "Jundiaí / Órgãos Públicos",
                options=[
                    "Todas as Notas",
                    "🏛️ Somente Jundiaí / Órgãos Públicos (TJ, TRE...)",
                    "Demais Clientes (Privado / Hospitalar)",
                ],
                key="op_filtro_orgao",
            )
        with r1_c4:
            busca = st.text_input(
                "Buscar NF(s) ou Cliente (várias NFs separadas por vírgula/espaço)",
                placeholder="Ex: 181410, 181920 ou TJ / TRE / Jundiaí...",
                key="op_busca_texto",
            )

        r2_c1, r2_c2 = st.columns([1.3, 3.0])
        with r2_c1:
            filtro_mao = st.selectbox(
                "Situação da NF Física",
                options=[
                    "Todas",
                    "Não retornou (Registrado)",
                    "Em rota (Aguardando retorno)",
                    "Já voltou para mão",
                    "Sem romaneio",
                ],
                key="op_filtro_mao",
            )
        with r2_c2:
            opcoes_status = list(CORES_FAROL.keys())
            filtro_status = st.multiselect(
                "Status Operacional",
                options=opcoes_status,
                default=opcoes_status,
                key="op_filtro_status_v4",
            )

    df_filtrado = df.copy()
    if filtro_periodo != "Todos os Meses (Banco Completo)":
        df_filtrado = df_filtrado[df_filtrado["competencia"] == filtro_periodo]
    if filtro_mod != "Todas":
        df_filtrado = df_filtrado[df_filtrado["transportadora"] == filtro_mod]
    if filtro_orgao == "🏛️ Somente Jundiaí / Órgãos Públicos (TJ, TRE...)":
        df_filtrado = df_filtrado[df_filtrado["is_jundiai_orgao"]]
    elif filtro_orgao == "Demais Clientes (Privado / Hospitalar)":
        df_filtrado = df_filtrado[~df_filtrado["is_jundiai_orgao"]]

    if filtro_mao == "Não retornou (Registrado)":
        df_filtrado = df_filtrado[df_filtrado["flag_nao_retornou"]]
    elif filtro_mao == "Em rota (Aguardando retorno)":
        df_filtrado = df_filtrado[df_filtrado["status_fluxo"] == "🔵 Em Rota (Aguardando Retorno)"]
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
            st.markdown(f"**📥 Ação Rápida em Lote — {len(df_filtrado)} NF(s) encontrada(s) na busca**")
            b_c1, b_c2, b_c3, b_c4, b_c5 = st.columns([1.0, 1.3, 1.15, 1.15, 1.2])
            with b_c1:
                data_lote_mao = st.date_input(
                    "Data retorno na mão",
                    value=date.today(),
                    format="DD/MM/YYYY",
                    key="dt_lote_mao_input",
                )
            with b_c2:
                motivo_lote = st.selectbox(
                    "Motivo (se não retornou)",
                    options=MOTIVOS_NAO_RETORNO,
                    key="motivo_lote_input",
                )
            with b_c3:
                st.write("")
                if st.button("✅ Voltou p/ Mão", type="primary", use_container_width=True):
                    qtd = registrar_retorno_mao_lote(
                        nfs=df_filtrado["nf"].tolist(),
                        data_retorno=data_lote_mao.strftime("%Y-%m-%d"),
                        baixar_erp=False,
                    )
                    st.toast(f"{qtd} NF(s) registradas como voltadas para a mão!", icon="✅")
                    st.rerun()
            with b_c4:
                st.write("")
                if st.button("🔴 Não Retornou", use_container_width=True):
                    qtd = registrar_nao_retornou_lote(
                        nfs=df_filtrado["nf"].tolist(),
                        motivo=motivo_lote,
                    )
                    st.toast(f"{qtd} NF(s) marcadas como Não Retornou!", icon="⚠️")
                    st.rerun()
            with b_c5:
                st.write("")
                if st.button("🏛️ Ticar Jundiaí/Órgão", use_container_width=True):
                    qtd = marcar_jundiai_orgao_lote(
                        nfs=df_filtrado["nf"].tolist(),
                        marcar=True,
                    )
                    st.toast(f"{qtd} NF(s) ticadas como Jundiaí / Órgão Público!", icon="🏛️")
                    st.rerun()

    total_nfs = len(df_filtrado)
    na_mao_qtd = int(df_filtrado["nf_na_mao"].sum())
    nao_ret_qtd = int(df_filtrado["flag_nao_retornou"].sum())
    orgaos_qtd = int(df_filtrado["is_jundiai_orgao"].sum())
    pct_retorno = (na_mao_qtd / total_nfs * 100.0) if total_nfs > 0 else 0.0
    valor_total_filtrado = float(df_filtrado["valor_nf"].sum())

    c1, c2, c3, c4, c5, c6 = st.columns([0.85, 1.45, 0.9, 0.9, 0.9, 1.0])
    c1.metric("NFs Filtradas", total_nfs)
    c2.metric("Valor Total (R$ NF)", formatar_brl(valor_total_filtrado))
    c3.metric("Taxa Retorno", f"{pct_retorno:.1f}%")
    c4.metric("🟢 NF na Mão", na_mao_qtd)
    c5.metric("🔴 Não Retornou", nao_ret_qtd)
    c6.metric("🏛️ Jundiaí / Órgãos", orgaos_qtd)

    st.write("")

    with st.expander("✏️ Atualizar Dados da NF (Saída / Entrega / Não Retornou / Jundiaí & Órgãos / Baixa)", expanded=True):
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
                tag_orgao = " · 🏛️ Jundiaí / Órgão Público" if reg["is_jundiai_orgao"] else ""
                st.markdown(
                    f"**Cliente:** `{reg['cliente']}` &nbsp;|&nbsp; "
                    f"**Veículo:** `{reg['transportadora']}` &nbsp;|&nbsp; "
                    f"**Valor NF:** `{valor_fmt}` &nbsp;|&nbsp; "
                    f"**Status:** {reg['status_fluxo']}{tag_orgao}<br>"
                    f"<span style='font-size:0.8rem; color:#64748b;'>Última atualização salva no banco: {ultima_att}</span>",
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

                m1, m2, m3, m4 = st.columns([1.3, 1.7, 1.25, 1.0])
                with m1:
                    st.write("")
                    nao_retornou_in = st.checkbox(
                        "🔴 Não Retornou Ainda",
                        value=bool(reg["flag_nao_retornou"]),
                    )
                with m2:
                    motivo_atual = reg["motivo_nao_retorno"] or ""
                    opcoes_motivos = (
                        MOTIVOS_NAO_RETORNO
                        if motivo_atual in MOTIVOS_NAO_RETORNO
                        else [motivo_atual] + MOTIVOS_NAO_RETORNO
                    )
                    motivo_in = st.selectbox(
                        "Motivo do Não Retorno",
                        options=opcoes_motivos,
                        index=opcoes_motivos.index(motivo_atual),
                    )
                with m3:
                    st.write("")
                    jundiai_orgao_in = st.checkbox(
                        "🏛️ Jundiaí / Órgão Público",
                        value=bool(reg["is_jundiai_orgao"]),
                    )
                with m4:
                    st.write("")
                    baixada_in = st.checkbox(
                        "NF Baixada ERP",
                        value=bool(reg["nf_baixada_sistema"]),
                    )

                o1, o2 = st.columns([3.5, 1.2])
                with o1:
                    obs_in = st.text_input(
                        "Observação (Motorista / Técnico / Protocolo TJ-TRE / Ocorrência)",
                        value=reg["observacao"] or "",
                        placeholder="Ex: Protocolado no TJ Jundiaí; canhoto retido para assinatura do setor...",
                    )
                with o2:
                    st.write("")
                    salvar_btn = st.form_submit_button(
                        "💾 Salvar no Banco",
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
                        nao_retornou=nao_retornou_in,
                        motivo_nao_retorno=motivo_in,
                        nota_jundiai_orgao=jundiai_orgao_in,
                        observacao=obs_in,
                    )
                    st.toast(f"NF {nf_selecionada} gravada permanentemente!", icon="✅")
                    st.rerun()

    st.write("")

    # --- PAINEL DEDICADO DE TICAGEM RÁPIDA: NOTAS DE JUNDIAÍ & ÓRGÃOS PÚBLICOS (TJ, TRE, ETC.) ---
    with st.expander("🏛️ Painel de Ticagem — Notas de Jundiaí & Órgãos Públicos (TJ, TRE e afins)", expanded=False):
        df_orgaos = df_filtrado[df_filtrado["is_jundiai_orgao"]].copy()
        st.caption(
            "Notas identificadas automaticamente (TJ, TRE, Secretarias, Assembleia, Jundiaí) ou ticadas manualmente. "
            "Marque diretamente na tabela abaixo quem já voltou para a mão, não retornou ou foi baixado no ERP."
        )
        if df_orgaos.empty:
            st.info("Nenhuma nota de Jundiaí / Órgão Público no filtro atual.")
        else:
            cols_orgaos = [
                "is_jundiai_orgao",
                "status_fluxo",
                "nf",
                "cliente",
                "valor_nf",
                "dt_romaneio",
                "dt_saida",
                "flag_nao_retornou",
                "motivo_nao_retorno",
                "dt_retorno_mao",
                "nf_baixada_sistema",
                "observacao",
            ]
            ed_orgaos_df = df_orgaos[cols_orgaos].copy().rename(
                columns={
                    "is_jundiai_orgao": "nota_jundiai_orgao",
                    "flag_nao_retornou": "nao_retornou",
                }
            )
            ed_orgaos_df["nota_jundiai_orgao"] = ed_orgaos_df["nota_jundiai_orgao"].astype(bool)
            ed_orgaos_df["nao_retornou"] = ed_orgaos_df["nao_retornou"].astype(bool)
            ed_orgaos_df["nf_baixada_sistema"] = ed_orgaos_df["nf_baixada_sistema"].astype(bool)

            editado_orgaos = st.data_editor(
                ed_orgaos_df,
                use_container_width=True,
                height=340,
                hide_index=True,
                disabled=["status_fluxo", "nf", "cliente", "valor_nf", "dt_romaneio"],
                column_config={
                    "nota_jundiai_orgao": st.column_config.CheckboxColumn("🏛️ Jundiaí/Órgão?"),
                    "status_fluxo": st.column_config.TextColumn("Status", width="medium"),
                    "nf": st.column_config.TextColumn("NF", width="small"),
                    "cliente": st.column_config.TextColumn("Órgão / Cliente", width="large"),
                    "valor_nf": st.column_config.NumberColumn("R$ NF", format="R$ %.2f", width="small"),
                    "dt_romaneio": st.column_config.DateColumn("Dt. Romaneio 🔒", format="DD/MM/YYYY"),
                    "dt_saida": st.column_config.DateColumn("Dia Saída", format="DD/MM/YYYY"),
                    "nao_retornou": st.column_config.CheckboxColumn("Não Retornou?"),
                    "motivo_nao_retorno": st.column_config.SelectboxColumn(
                        "Motivo", options=MOTIVOS_NAO_RETORNO, width="medium"
                    ),
                    "dt_retorno_mao": st.column_config.DateColumn("Voltou p/ Mão", format="DD/MM/YYYY"),
                    "nf_baixada_sistema": st.column_config.CheckboxColumn("Baixada ERP?"),
                    "observacao": st.column_config.TextColumn("Protocolo / Obs.", width="large"),
                },
                key="grade_jundiai_orgaos",
            )
            if st.button("💾 Salvar Ticagem Jundiaí / Órgãos Públicos", type="primary"):
                df_salvar_org = editado_orgaos.copy()
                for col in ["dt_saida", "dt_entrega_real", "dt_retorno_mao"]:
                    if col not in df_salvar_org.columns:
                        df_salvar_org[col] = None
                    else:
                        df_salvar_org[col] = pd.to_datetime(df_salvar_org[col], errors="coerce").dt.strftime("%Y-%m-%d")
                salvar_edicoes_lote(df_salvar_org)
                st.toast("Ticagem de Jundiaí / Órgãos Públicos salva!", icon="🏛️")
                st.rerun()

    st.write("")

    st.subheader(f"Controle Geral de Entregas & Retorno de NFs ({len(df_filtrado)} NFs)")

    colunas_exibicao = [
        "status_fluxo",
        "is_jundiai_orgao",
        "tempo_retorno",
        "nf",
        "transportadora",
        "cliente",
        "valor_nf",
        "dt_romaneio",
        "dt_saida",
        "dt_entrega_real",
        "flag_nao_retornou",
        "motivo_nao_retorno",
        "dt_retorno_mao",
        "nf_baixada_sistema",
        "observacao",
    ]

    df_editor = df_filtrado[colunas_exibicao].copy()
    df_editor = df_editor.rename(
        columns={
            "flag_nao_retornou": "nao_retornou",
            "is_jundiai_orgao": "nota_jundiai_orgao",
        }
    )
    df_editor["nf_baixada_sistema"] = df_editor["nf_baixada_sistema"].astype(bool)
    df_editor["nao_retornou"] = df_editor["nao_retornou"].astype(bool)
    df_editor["nota_jundiai_orgao"] = df_editor["nota_jundiai_orgao"].astype(bool)

    editado = st.data_editor(
        df_editor,
        use_container_width=True,
        height=470,
        hide_index=True,
        disabled=["status_fluxo", "tempo_retorno", "nf", "transportadora", "cliente", "valor_nf", "dt_romaneio"],
        column_config={
            "status_fluxo": st.column_config.TextColumn("Status", width="medium"),
            "nota_jundiai_orgao": st.column_config.CheckboxColumn("🏛️ Jundiaí/Órgão?"),
            "tempo_retorno": st.column_config.TextColumn("Ciclo", width="small"),
            "nf": st.column_config.TextColumn("NF", width="small"),
            "transportadora": st.column_config.TextColumn("Veículo", width="small"),
            "cliente": st.column_config.TextColumn("Cliente", width="large"),
            "valor_nf": st.column_config.NumberColumn("R$ NF", format="R$ %.2f", width="small"),
            "dt_romaneio": st.column_config.DateColumn("Dt. Romaneio 🔒", format="DD/MM/YYYY"),
            "dt_saida": st.column_config.DateColumn("Dia Saída", format="DD/MM/YYYY"),
            "dt_entrega_real": st.column_config.DateColumn("Data Entrega", format="DD/MM/YYYY"),
            "nao_retornou": st.column_config.CheckboxColumn("Não Retornou?"),
            "motivo_nao_retorno": st.column_config.SelectboxColumn(
                "Motivo Não Retorno",
                options=MOTIVOS_NAO_RETORNO,
                width="medium",
            ),
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
            st.toast("Edições salvas no banco local!", icon="✅")
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