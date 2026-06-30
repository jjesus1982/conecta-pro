"""GEDEON — Alinhamento com o módulo DP (espelho do Sólides).

O ponto/cadastro do Sólides é espelhado no DP (tabelas solides_*). Este serviço cruza a
FOLHA do kit (fonte do GEDEON) com o espelho do DP (solides_employees) e com as ausências
(solides_absences) do mês — pra garantir que kit e DP contam a MESMA história:
  - quem está na folha do kit mas não tem espelho no DP (cadastro a sincronizar);
  - afastamentos/licenças do mês (explicam, por ex., a falta de VT/VR — liga no ATLAS);
  - escala: lista os condomínios elegíveis a partir de clients (contrato ativo).
"""

from __future__ import annotations

from sqlalchemy import text


def alinhamento_dp(competencia: str, condominio: str) -> dict:
    """Cruza a folha do kit com o espelho do DP (solides_employees + ausências do mês)."""
    from core.database.session import get_sync_db
    from modules.gdrive.services.gdrive_service import gdrive_service
    from modules.gedeon.services import kit_cache
    from modules.gedeon.services.kit_ficha_service import _client_id_do_condominio, _norm, _pertence

    if not gdrive_service._service:
        gdrive_service.check_status()
    svc = gdrive_service._service
    folha = [n for n in (kit_cache.nomes_folha(svc, condominio, competencia) if svc else []) if n.strip()]

    m, a = int(competencia.split(".")[0]), int(competencia.split(".")[1])
    ini, fim = f"{a}-{m:02d}-01", (f"{a}-{m+1:02d}-01" if m < 12 else f"{a+1}-01-01")

    with get_sync_db() as db:
        cid = _client_id_do_condominio(db, condominio)
        # espelho DP do condomínio (por condominio_id quando casar, senão todos)
        dp_rows = db.execute(text("SELECT nome, cargo_nome FROM solides_employees")).fetchall()
        dp_nomes = [(_norm(r[0]), r[0], r[1]) for r in dp_rows]
        absences = db.execute(
            text(
                """SELECT colaborador_nome, tipo, data_inicio, data_fim FROM solides_absences
                   WHERE data_inicio < :fim AND (data_fim IS NULL OR data_fim >= :ini)"""
            ),
            {"ini": ini, "fim": fim},
        ).fetchall()

    com_espelho, sem_espelho = [], []
    for nome in folha:
        casou = next((orig for nn, orig, _c in dp_nomes if _pertence(nome, {nn})), None)
        (com_espelho if casou else sem_espelho).append({"folha": nome, "dp": casou})

    afastados = []
    for cn, tipo, di, dfim in absences:
        if any(_pertence(cn, {_norm(f)}) for f in folha):
            afastados.append({"funcionario": cn, "tipo": tipo, "inicio": str(di), "fim": str(dfim) if dfim else None})

    return {
        "competencia": competencia,
        "condominio": condominio,
        "cliente_id": str(cid) if cid else None,
        "funcionarios_folha": len(folha),
        "com_espelho_dp": len(com_espelho),
        "sem_espelho_dp": sem_espelho,
        "afastamentos_mes": afastados,
        "nota": "Afastados/licenças explicam ausência de VT/VR no kit (ver ATLAS).",
    }


def condominios_elegiveis() -> dict:
    """Escala: condomínios com contrato ATIVO em clients (além dos 7 padrão do GEDEON)."""
    from core.database.session import get_sync_db
    from modules.gedeon.services.kit_orchestrator import CONDOMINIOS_PADRAO

    with get_sync_db() as db:
        rows = db.execute(
            text(
                """SELECT DISTINCT c.name, COALESCE(ct.monthly_value, c.mrr) AS valor
                   FROM clients c
                   LEFT JOIN contracts ct ON ct.client_id = c.id AND ct.status = 'active'
                   WHERE c.ativo = true
                   ORDER BY c.name"""
            )
        ).fetchall()
    elegiveis = [{"nome": r[0], "valor": float(r[1]) if r[1] else None} for r in rows]
    return {
        "padrao_gedeon": CONDOMINIOS_PADRAO,
        "total_clientes_ativos": len(elegiveis),
        "clientes": elegiveis,
    }
