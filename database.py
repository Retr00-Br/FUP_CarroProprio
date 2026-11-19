import os
import sqlite3
from datetime import date, datetime
import pandas as pd
from config import DB_PATH, MODALIDADES_OFICIAIS
from parser_erp import localizar_planilha_repositorio, carregar_extrato_erp

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS entregas_fup (
                nf TEXT PRIMARY KEY,
                cliente TEXT,
                transportadora TEXT,
                valor_nf REAL DEFAULT 0.0,
                dt_saida TEXT,
                dt_entrega_real TEXT,
                dt_retorno_mao TEXT,
                dt_romaneio TEXT,
                romaneio_preenchido INTEGER DEFAULT 0,
                nf_baixada_sistema INTEGER DEFAULT 0,
                observacao TEXT DEFAULT '',
                atualizado_em TEXT
            )
        """)
        colunas = [r[1] for r in conn.execute("PRAGMA table_info(entregas_fup)").fetchall()]
        if "valor_nf" not in colunas:
            conn.execute("ALTER TABLE entregas_fup ADD COLUMN valor_nf REAL DEFAULT 0.0")
        if "dt_retorno_mao" not in colunas:
            conn.execute("ALTER TABLE entregas_fup ADD COLUMN dt_retorno_mao TEXT")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS controle_ingestao (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                arquivo TEXT,
                mtime REAL,
                ultima_execucao TEXT
            )
        """)

def aplicar_upsert_dataframe(df_erp: pd.DataFrame) -> tuple[int, int]:
    init_db()
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    novos, atualizados = 0, 0

    with get_conn() as conn:
        existentes = pd.read_sql("SELECT nf, dt_saida, valor_nf FROM entregas_fup", conn)
        map_existentes = existentes.set_index("nf").to_dict(orient="index")

        for _, row in df_erp.iterrows():
            nf = row["nf"]
            romaneio_ok = 1 if pd.notna(row["dt_romaneio"]) else 0
            dt_saida_erp = row["dt_romaneio"] if pd.notna(row["dt_romaneio"]) else None
            valor_nf = float(row["valor_nf"]) if pd.notna(row["valor_nf"]) else 0.0

            if nf not in map_existentes:
                conn.execute("""
                    INSERT INTO entregas_fup (
                        nf, cliente, transportadora, valor_nf, dt_saida,
                        dt_entrega_real, dt_retorno_mao, dt_romaneio,
                        romaneio_preenchido, nf_baixada_sistema, atualizado_em
                    ) VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?, 0, ?)
                """, (
                    nf, row["cliente"], row["transportadora"], valor_nf, dt_saida_erp,
                    row["dt_romaneio"], romaneio_ok, agora
                ))
                novos += 1
            else:
                antigo = map_existentes[nf]
                dt_saida_final = antigo["dt_saida"] or dt_saida_erp
                valor_final = valor_nf if valor_nf > 0 else float(antigo.get("valor_nf") or 0.0)
                conn.execute("""
                    UPDATE entregas_fup
                    SET cliente = ?,
                        transportadora = ?,
                        valor_nf = ?,
                        dt_saida = ?,
                        dt_romaneio = COALESCE(?, dt_romaneio),
                        romaneio_preenchido = CASE WHEN ? = 1 THEN 1 ELSE romaneio_preenchido END,
                        atualizado_em = ?
                    WHERE nf = ?
                """, (
                    row["cliente"], row["transportadora"], valor_final,
                    dt_saida_final, row["dt_romaneio"], romaneio_ok, agora, nf
                ))
                atualizados += 1

    return novos, atualizados

def sincronizar_erp_backend():
    init_db()
    caminho = localizar_planilha_repositorio()
    if not caminho:
        return

    mtime_atual = os.path.getmtime(caminho)
    with get_conn() as conn:
        cur = conn.execute("SELECT arquivo, mtime FROM controle_ingestao WHERE id = 1").fetchone()
        soma_valores = conn.execute(
            "SELECT COALESCE(SUM(valor_nf), 0) FROM entregas_fup WHERE transportadora IN ('Carro Próprio', 'Carro Técnica')"
        ).fetchone()[0]

        if cur and cur[0] == caminho and cur[1] == mtime_atual and soma_valores > 0:
            return

    df_erp = carregar_extrato_erp(caminho)
    aplicar_upsert_dataframe(df_erp)

    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO controle_ingestao (id, arquivo, mtime, ultima_execucao)
            VALUES (1, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                arquivo = excluded.arquivo,
                mtime = excluded.mtime,
                ultima_execucao = excluded.ultima_execucao
        """, (caminho, mtime_atual, agora))

def carregar_dados() -> pd.DataFrame:
    """Retorna exclusivamente os registros de Carro Próprio e Carro Técnica do mês atual."""
    init_db()
    prefixo_mes = date.today().strftime("%Y-%m")
    placeholders = ",".join(["?"] * len(MODALIDADES_OFICIAIS))
    with get_conn() as conn:
        df = pd.read_sql(
            f"""
            SELECT * FROM entregas_fup
            WHERE transportadora IN ({placeholders})
              AND (
                  dt_romaneio LIKE ?
                  OR dt_saida LIKE ?
                  OR (dt_romaneio IS NULL AND valor_nf > 0)
              )
            """,
            conn,
            params=(*MODALIDADES_OFICIAIS, f"{prefixo_mes}%", f"{prefixo_mes}%"),
        )
    if "valor_nf" in df.columns:
        df["valor_nf"] = pd.to_numeric(df["valor_nf"], errors="coerce").fillna(0.0)
    return df

def atualizar_registro_individual(
    nf: str,
    dt_saida: str | None,
    dt_entrega_real: str | None,
    dt_retorno_mao: str | None,
    nf_baixada_sistema: bool,
    observacao: str,
):
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        conn.execute("""
            UPDATE entregas_fup
            SET dt_saida = ?,
                dt_entrega_real = ?,
                dt_retorno_mao = ?,
                nf_baixada_sistema = ?,
                observacao = ?,
                atualizado_em = ?
            WHERE nf = ?
        """, (
            dt_saida,
            dt_entrega_real,
            dt_retorno_mao,
            int(bool(nf_baixada_sistema)),
            observacao,
            agora,
            nf,
        ))

def registrar_retorno_mao_lote(nfs: list[str], data_retorno: str, baixar_erp: bool = False) -> int:
    """Marca rapidamente a data que as NFs voltaram para a mão (conferência física)."""
    if not nfs:
        return 0
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    placeholders = ",".join(["?"] * len(nfs))
    with get_conn() as conn:
        if baixar_erp:
            cur = conn.execute(
                f"""
                UPDATE entregas_fup
                SET dt_retorno_mao = ?,
                    dt_entrega_real = COALESCE(dt_entrega_real, ?),
                    nf_baixada_sistema = 1,
                    atualizado_em = ?
                WHERE nf IN ({placeholders})
                """,
                (data_retorno, data_retorno, agora, *nfs),
            )
        else:
            cur = conn.execute(
                f"""
                UPDATE entregas_fup
                SET dt_retorno_mao = ?,
                    dt_entrega_real = COALESCE(dt_entrega_real, ?),
                    atualizado_em = ?
                WHERE nf IN ({placeholders})
                """,
                (data_retorno, data_retorno, agora, *nfs),
            )
        return cur.rowcount

def salvar_edicoes_lote(df_editado: pd.DataFrame):
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        for _, row in df_editado.iterrows():
            conn.execute("""
                UPDATE entregas_fup
                SET dt_saida = ?,
                    dt_entrega_real = ?,
                    dt_retorno_mao = ?,
                    nf_baixada_sistema = ?,
                    observacao = ?,
                    atualizado_em = ?
                WHERE nf = ?
            """, (
                row["dt_saida"],
                row["dt_entrega_real"],
                row["dt_retorno_mao"],
                int(bool(row["nf_baixada_sistema"])),
                row["observacao"],
                agora,
                row["nf"],
            ))