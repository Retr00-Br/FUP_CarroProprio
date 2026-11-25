import glob
import os
import shutil
import sqlite3
from datetime import date, datetime
import pandas as pd
from config import (
    BASE_DIR,
    DB_PATH,
    PASTA_BACKUPS,
    MODALIDADES_OFICIAIS,
    detectar_jundiai_orgao_publico,
)
from parser_erp import localizar_planilha_repositorio, carregar_extrato_erp


def get_conn():
    pasta_db = os.path.dirname(DB_PATH)
    if pasta_db:
        os.makedirs(pasta_db, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=DELETE;")
    conn.execute("PRAGMA synchronous=FULL;")
    return conn


def criar_backup_automatico() -> str | None:
    if not os.path.exists(DB_PATH):
        return None
    os.makedirs(PASTA_BACKUPS, exist_ok=True)
    hoje_str = date.today().strftime("%Y%m%d")
    destino = os.path.join(PASTA_BACKUPS, f"fuphigimed_{hoje_str}.db")
    shutil.copy2(DB_PATH, destino)

    backups = sorted(glob.glob(os.path.join(PASTA_BACKUPS, "fuphigimed_*.db")))
    for antigo in backups[:-15]:
        try:
            os.remove(antigo)
        except OSError:
            pass
    return destino


def init_db():
    banco_raiz_antigo = os.path.join(BASE_DIR, "fuphigimed.db")
    if os.path.exists(banco_raiz_antigo) and not os.path.exists(DB_PATH):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        shutil.move(banco_raiz_antigo, DB_PATH)

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
                nao_retornou INTEGER DEFAULT 0,
                motivo_nao_retorno TEXT DEFAULT '',
                nota_jundiai_orgao INTEGER DEFAULT 0,
                observacao TEXT DEFAULT '',
                atualizado_em TEXT
            )
        """)
        colunas = [r[1] for r in conn.execute("PRAGMA table_info(entregas_fup)").fetchall()]
        if "valor_nf" not in colunas:
            conn.execute("ALTER TABLE entregas_fup ADD COLUMN valor_nf REAL DEFAULT 0.0")
        if "dt_retorno_mao" not in colunas:
            conn.execute("ALTER TABLE entregas_fup ADD COLUMN dt_retorno_mao TEXT")
        if "nao_retornou" not in colunas:
            conn.execute("ALTER TABLE entregas_fup ADD COLUMN nao_retornou INTEGER DEFAULT 0")
        if "motivo_nao_retorno" not in colunas:
            conn.execute("ALTER TABLE entregas_fup ADD COLUMN motivo_nao_retorno TEXT DEFAULT ''")
        if "nota_jundiai_orgao" not in colunas:
            conn.execute("ALTER TABLE entregas_fup ADD COLUMN nota_jundiai_orgao INTEGER DEFAULT 0")
            # Classifica registros já existentes no banco
            rows = conn.execute("SELECT nf, cliente FROM entregas_fup").fetchall()
            for nf_id, cli in rows:
                if detectar_jundiai_orgao_publico(cli):
                    conn.execute(
                        "UPDATE entregas_fup SET nota_jundiai_orgao = 1 WHERE nf = ?",
                        (nf_id,),
                    )

        conn.execute("""
            CREATE TABLE IF NOT EXISTS controle_ingestao (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                arquivo TEXT,
                mtime REAL,
                ultima_execucao TEXT
            )
        """)


def aplicar_upsert_dataframe(df_erp: pd.DataFrame) -> tuple[int, int]:
    """Insere novas NFs e atualiza existentes preservando todo o histórico permanente."""
    init_db()
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    novos, atualizados = 0, 0

    with get_conn() as conn:
        existentes = pd.read_sql("SELECT nf, dt_saida, valor_nf FROM entregas_fup", conn)
        map_existentes = existentes.set_index("nf").to_dict(orient="index")

        for _, row in df_erp.iterrows():
            nf = str(row["nf"])
            romaneio_ok = 1 if pd.notna(row["dt_romaneio"]) else 0
            dt_saida_erp = row["dt_romaneio"] if pd.notna(row["dt_romaneio"]) else None
            valor_nf = float(row["valor_nf"]) if pd.notna(row["valor_nf"]) else 0.0
            is_orgao = 1 if detectar_jundiai_orgao_publico(row["cliente"]) else 0

            if nf not in map_existentes:
                conn.execute("""
                    INSERT INTO entregas_fup (
                        nf, cliente, transportadora, valor_nf, dt_saida,
                        dt_entrega_real, dt_retorno_mao, dt_romaneio,
                        romaneio_preenchido, nf_baixada_sistema,
                        nao_retornou, motivo_nao_retorno,
                        nota_jundiai_orgao, atualizado_em
                    ) VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?, 0, 0, '', ?, ?)
                """, (
                    nf, row["cliente"], row["transportadora"], valor_nf, dt_saida_erp,
                    row["dt_romaneio"], romaneio_ok, is_orgao, agora
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
                        nota_jundiai_orgao = CASE WHEN ? = 1 THEN 1 ELSE nota_jundiai_orgao END,
                        atualizado_em = ?
                    WHERE nf = ?
                """, (
                    row["cliente"], row["transportadora"], valor_final,
                    dt_saida_final, row["dt_romaneio"], romaneio_ok, is_orgao, agora, nf
                ))
                atualizados += 1

    criar_backup_automatico()
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


def carregar_dados(apenas_mes_atual: bool = False) -> pd.DataFrame:
    """Carrega os registros salvos permanentemente no banco local."""
    init_db()
    placeholders = ",".join(["?"] * len(MODALIDADES_OFICIAIS))
    with get_conn() as conn:
        if apenas_mes_atual:
            prefixo_mes = date.today().strftime("%Y-%m")
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
        else:
            df = pd.read_sql(
                f"SELECT * FROM entregas_fup WHERE transportadora IN ({placeholders})",
                conn,
                params=tuple(MODALIDADES_OFICIAIS),
            )

    if "valor_nf" in df.columns:
        df["valor_nf"] = pd.to_numeric(df["valor_nf"], errors="coerce").fillna(0.0)
    if "nao_retornou" in df.columns:
        df["nao_retornou"] = pd.to_numeric(df["nao_retornou"], errors="coerce").fillna(0).astype(int)
    if "nota_jundiai_orgao" in df.columns:
        df["nota_jundiai_orgao"] = pd.to_numeric(df["nota_jundiai_orgao"], errors="coerce").fillna(0).astype(int)
    if "motivo_nao_retorno" in df.columns:
        df["motivo_nao_retorno"] = df["motivo_nao_retorno"].fillna("")
    return df


def atualizar_registro_individual(
    nf: str,
    dt_saida: str | None,
    dt_entrega_real: str | None,
    dt_retorno_mao: str | None,
    nf_baixada_sistema: bool,
    nao_retornou: bool,
    motivo_nao_retorno: str,
    nota_jundiai_orgao: bool,
    observacao: str,
):
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if dt_retorno_mao or nf_baixada_sistema:
        nao_retornou_final = 0
        motivo_final = ""
    else:
        nao_retornou_final = int(bool(nao_retornou))
        motivo_final = (motivo_nao_retorno or "").strip() if nao_retornou_final else ""

    with get_conn() as conn:
        conn.execute("""
            UPDATE entregas_fup
            SET dt_saida = ?,
                dt_entrega_real = ?,
                dt_retorno_mao = ?,
                nf_baixada_sistema = ?,
                nao_retornou = ?,
                motivo_nao_retorno = ?,
                nota_jundiai_orgao = ?,
                observacao = ?,
                atualizado_em = ?
            WHERE nf = ?
        """, (
            dt_saida,
            dt_entrega_real,
            dt_retorno_mao,
            int(bool(nf_baixada_sistema)),
            nao_retornou_final,
            motivo_final,
            int(bool(nota_jundiai_orgao)),
            observacao,
            agora,
            nf,
        ))
    criar_backup_automatico()


def registrar_retorno_mao_lote(nfs: list[str], data_retorno: str, baixar_erp: bool = False) -> int:
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
                    nao_retornou = 0,
                    motivo_nao_retorno = '',
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
                    nao_retornou = 0,
                    motivo_nao_retorno = '',
                    atualizado_em = ?
                WHERE nf IN ({placeholders})
                """,
                (data_retorno, data_retorno, agora, *nfs),
            )
        qtd = cur.rowcount
    criar_backup_automatico()
    return qtd


def registrar_nao_retornou_lote(nfs: list[str], motivo: str = "") -> int:
    if not nfs:
        return 0
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    placeholders = ",".join(["?"] * len(nfs))
    with get_conn() as conn:
        cur = conn.execute(
            f"""
            UPDATE entregas_fup
            SET nao_retornou = 1,
                motivo_nao_retorno = CASE WHEN ? <> '' THEN ? ELSE motivo_nao_retorno END,
                atualizado_em = ?
            WHERE nf IN ({placeholders})
              AND dt_retorno_mao IS NULL
              AND nf_baixada_sistema = 0
            """,
            (motivo.strip(), motivo.strip(), agora, *nfs),
        )
        qtd = cur.rowcount
    criar_backup_automatico()
    return qtd


def marcar_jundiai_orgao_lote(nfs: list[str], marcar: bool = True) -> int:
    """Tica ou destica em lote notas de Jundiaí / Órgãos Públicos (TJ, TRE, etc.)."""
    if not nfs:
        return 0
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    placeholders = ",".join(["?"] * len(nfs))
    with get_conn() as conn:
        cur = conn.execute(
            f"""
            UPDATE entregas_fup
            SET nota_jundiai_orgao = ?,
                atualizado_em = ?
            WHERE nf IN ({placeholders})
            """,
            (int(bool(marcar)), agora, *nfs),
        )
        qtd = cur.rowcount
    criar_backup_automatico()
    return qtd


def salvar_edicoes_lote(df_editado: pd.DataFrame):
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        for _, row in df_editado.iterrows():
            dt_ret = row["dt_retorno_mao"]
            baixada = bool(row["nf_baixada_sistema"])
            nao_ret = False if (dt_ret or baixada) else bool(row.get("nao_retornou", False))
            motivo = "" if not nao_ret else str(row.get("motivo_nao_retorno") or "").strip()
            is_orgao = bool(row.get("nota_jundiai_orgao", False))

            conn.execute("""
                UPDATE entregas_fup
                SET dt_saida = ?,
                    dt_entrega_real = ?,
                    dt_retorno_mao = ?,
                    nf_baixada_sistema = ?,
                    nao_retornou = ?,
                    motivo_nao_retorno = ?,
                    nota_jundiai_orgao = ?,
                    observacao = ?,
                    atualizado_em = ?
                WHERE nf = ?
            """, (
                row["dt_saida"],
                row["dt_entrega_real"],
                dt_ret,
                int(baixada),
                int(nao_ret),
                motivo,
                int(is_orgao),
                row["observacao"],
                agora,
                row["nf"],
            ))
    criar_backup_automatico()