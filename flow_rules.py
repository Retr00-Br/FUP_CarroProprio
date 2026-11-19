from datetime import date
import pandas as pd

def formatar_brl(valor: float) -> str:
    if pd.isna(valor) or valor is None:
        return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def enriquecer_fluxo_frota(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    hoje = pd.Timestamp(date.today())

    for col in ["dt_saida", "dt_entrega_real", "dt_retorno_mao", "dt_romaneio"]:
        df[col] = pd.to_datetime(df[col], errors="coerce")

    df["valor_nf"] = pd.to_numeric(df["valor_nf"], errors="coerce").fillna(0.0)
    df["ja_saiu"] = df["dt_saida"].notna()
    df["nf_na_mao"] = df["dt_retorno_mao"].notna()

    def calcular_status(row) -> str:
        na_mao = pd.notna(row["dt_retorno_mao"])
        baixada = bool(row["nf_baixada_sistema"])
        romaneio = bool(row["romaneio_preenchido"]) or pd.notna(row["dt_saida"])

        if na_mao:
            if baixada:
                return "🟢 NF na Mão & Baixada"
            return "🟡 NF na Mão (Pendente Baixa ERP)"

        if not romaneio:
            return "🟠 Sem Romaneio (Faturada)"

        return "🔵 Em Rota (Aguardando Retorno)"

    def calcular_tempo_retorno(row) -> str:
        saida = row["dt_saida"]
        retorno = row["dt_retorno_mao"]
        if pd.isna(saida):
            return "Aguardando saída"
        if pd.notna(retorno):
            dias = max(0, int((retorno - saida).days))
            return "Mesmo dia" if dias == 0 else f"Voltou em {dias}d"
        dias_rua = max(0, int((hoje - saida).days))
        return "Saiu hoje" if dias_rua == 0 else f"{dias_rua}d em rua"

    df["status_fluxo"] = df.apply(calcular_status, axis=1)
    df["tempo_retorno"] = df.apply(calcular_tempo_retorno, axis=1)
    return df