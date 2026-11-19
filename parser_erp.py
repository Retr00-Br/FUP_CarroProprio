import io
import os
import re
import glob
from datetime import date
import pandas as pd
from config import MODALIDADES_MAP

def normalizar_modalidade(nome) -> str | None:
    if not isinstance(nome, str) or not nome.strip():
        return None
    upper = nome.upper().strip()
    for chave, padrao in MODALIDADES_MAP.items():
        if chave in upper:
            return padrao
    return None

def corrigir_texto(val) -> str:
    if pd.isna(val) or val is None:
        return ""
    texto = str(val).strip()
    if "Ã" in texto:
        try:
            texto = texto.encode("latin1", errors="ignore").decode("utf-8", errors="ignore")
        except Exception:
            pass
    return texto

def _converter_celula_valor(val) -> float:
    if pd.isna(val) or val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)

    texto = str(val).replace("R$", "").replace("\xa0", "").strip()
    if not texto or texto.lower() in ("nan", "none", "<na>"):
        return 0.0

    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    else:
        partes = texto.split(".")
        if len(partes) > 2 or (len(partes) == 2 and len(partes[1]) == 3):
            texto = "".join(partes)

    try:
        return float(texto)
    except ValueError:
        return 0.0

def parse_valor_br(serie: pd.Series) -> pd.Series:
    return serie.apply(_converter_celula_valor).astype(float)

def _encontrar_coluna_valor(df: pd.DataFrame) -> str | None:
    for col in df.columns:
        limpo = re.sub(r"\s+", " ", str(col)).strip().upper()
        if limpo in ("R$ NF", "R$NF", "VALOR NF", "VLR NF", "VLR. NF", "VALOR"):
            return col
    for col in df.columns:
        limpo = str(col).upper()
        if "R$" in limpo or "VALOR" in limpo or "VLR" in limpo:
            return col
    if len(df.columns) >= 5:
        return df.columns[4]
    return None

def localizar_planilha_repositorio() -> str | None:
    candidatos = []
    for pasta in ["dados_privados", "."]:
        if os.path.isdir(pasta):
            candidatos.extend(glob.glob(os.path.join(pasta, "SLA*.xls*")))
            candidatos.extend(glob.glob(os.path.join(pasta, "ROMANEIO*.xls*")))
    if not candidatos:
        return None
    candidatos.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return candidatos[0]

def carregar_extrato_erp(fonte) -> pd.DataFrame:
    """Lê extrato de romaneios e filtra exclusivamente Carro Próprio e Carro Técnica."""
    if hasattr(fonte, "getvalue"):
        raw_bytes = fonte.getvalue()
    elif isinstance(fonte, (str, os.PathLike)):
        with open(fonte, "rb") as f:
            raw_bytes = f.read()
    else:
        raw_bytes = fonte.read()

    df = None
    for enc in ("latin1", "utf-8", "cp1252"):
        try:
            temp = pd.read_csv(io.BytesIO(raw_bytes), sep="\t", encoding=enc)
            if len(temp.columns) >= 4:
                df = temp
                break
        except Exception:
            continue

    if df is None:
        df = pd.read_excel(io.BytesIO(raw_bytes))

    df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.columns]

    col_cliente = next((c for c in df.columns if "CLIENTE" in c.upper()), df.columns[0])
    col_nf = next((c for c in df.columns if c.upper() == "NF" or "NOTA" in c.upper()), df.columns[1])
    col_transp = next((c for c in df.columns if "TRANSP" in c.upper()), df.columns[2])
    col_romaneio = next((c for c in df.columns if "ROMANEIO" in c.upper()), None)
    col_valor = _encontrar_coluna_valor(df)

    df[col_cliente] = df[col_cliente].apply(corrigir_texto)
    df[col_transp] = df[col_transp].apply(corrigir_texto)

    df["Modalidade"] = df[col_transp].apply(normalizar_modalidade)
    df = df[df["Modalidade"].notna()].copy()

    df["NF_LIMPA"] = (
        df[col_nf]
        .fillna("")
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.strip()
    )
    df = df[~df["NF_LIMPA"].isin(["", "nan", "None", "<NA>"])].copy()

    df["valor_nf"] = parse_valor_br(df[col_valor]) if col_valor else 0.0

    if col_romaneio:
        dt_rom_raw = pd.to_datetime(
            df[col_romaneio].fillna("").astype(str).str.strip(),
            format="%d/%m/%Y",
            errors="coerce",
        )
        if dt_rom_raw.isna().all():
            dt_rom_raw = pd.to_datetime(df[col_romaneio], errors="coerce")
        df["dt_rom_dt"] = dt_rom_raw.where(dt_rom_raw.dt.year >= 2020, pd.NaT)
    else:
        df["dt_rom_dt"] = pd.NaT

    # Filtra mês atual (romaneadas no mês ou faturadas no mês ainda sem romaneio)
    hoje = date.today()
    mes_atual_mask = (df["dt_rom_dt"].dt.year == hoje.year) & (df["dt_rom_dt"].dt.month == hoje.month)
    sem_rom_mes_atual = df["dt_rom_dt"].isna() & (df["valor_nf"] > 0)
    df = df[mes_atual_mask | sem_rom_mes_atual].copy()

    # Agrupa por NF única consolidando valor e preservando a primeira data de romaneio válida
    df_agrupado = (
        df.groupby("NF_LIMPA", as_index=False)
        .agg({
            col_cliente: "first",
            "Modalidade": "first",
            "dt_rom_dt": "first",
            "valor_nf": "sum",
        })
    )

    return pd.DataFrame({
        "nf": df_agrupado["NF_LIMPA"],
        "cliente": df_agrupado[col_cliente],
        "transportadora": df_agrupado["Modalidade"],
        "dt_romaneio": df_agrupado["dt_rom_dt"].dt.strftime("%Y-%m-%d"),
        "valor_nf": df_agrupado["valor_nf"].round(2),
    }).reset_index(drop=True)