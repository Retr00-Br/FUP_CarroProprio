import os
from config import DB_PATH
from database import init_db, aplicar_upsert_dataframe, criar_backup_automatico, get_conn
from parser_erp import localizar_planilha_repositorio, carregar_extrato_erp


def main():
    pasta_db = os.path.dirname(DB_PATH)
    if pasta_db:
        os.makedirs(pasta_db, exist_ok=True)

    init_db()
    print(f"[OK] Banco SQLite permanente pronto em: {DB_PATH}")

    planilha = localizar_planilha_repositorio()
    if planilha:
        df_erp = carregar_extrato_erp(planilha)
        novos, atualizados = aplicar_upsert_dataframe(df_erp)
        print(f"[OK] Planilha '{planilha}' importada -> {novos} novas NFs | {atualizados} atualizadas.")
    else:
        print("[AVISO] Nenhuma planilha SLA*.xls encontrada na pasta do projeto.")

    backup_gerado = criar_backup_automatico()
    if backup_gerado:
        print(f"[OK] Snapshot de segurança salvo em: {backup_gerado}")

    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM entregas_fup").fetchone()[0]
        orgaos = conn.execute(
            "SELECT COUNT(*) FROM entregas_fup WHERE nota_jundiai_orgao = 1"
        ).fetchone()[0]
        print(f"[INFO] Total acumulado no banco (permanente): {total} NFs ({orgaos} Jundiaí / Órgãos Públicos)")


if __name__ == "__main__":
    main()