"""Pareamento fiscal nosso × Portte por empresa+competência (Fase 5, a espinha).

Verdade = Portte (guia oficial em `fiscal_obligations`, puxada do Drive/Onvio).
Nosso = apuração da folha REAL (`hr_payslips`). Durante o paralelo de ~6 meses,
divergência = corrigir o NOSSO (a Portte é a fonte da verdade).

Oráculo (inegociável): cada valor (nosso e Portte) vem de query real, escopada por
empresa_id; divergência = diferença REAL, nunca fabricada. Rubrica sem guia da Portte
= None (a tela exibe "aguardando guia Portte"), nunca zero.
"""
from __future__ import annotations

from sqlalchemy import text

TOL = 0.02  # tolerância de 2 centavos (arredondamento)


def _status_linha(nosso, portte, tol: float = TOL):
    """Retorna (diff, bate). diff = nosso - portte. Se qualquer lado ausente → não bate."""
    if nosso is None or portte is None:
        return (0.0, False)
    diff = round(float(nosso) - float(portte), 2)
    return (diff, abs(diff) <= tol)


# Lucro Real: a guia INSS (DARF DCTFWeb) é o INSS TOTAL, não só o do empregado.
# Mesmas alíquotas do dctfweb_service: patronal 20% + RAT 3% + terceiros 5,8% sobre a
# base, mais o segurado retido. Só assim "nosso INSS" é comparável à guia da Portte.
INSS_PATRONAL_RAT_TERCEIROS = 0.288  # 0.20 + 0.03 + 0.058


def _inss_total(inss_segurado, inss_base):
    """INSS total (DARF) = segurado + 28,8% da base. None se sem base real."""
    if inss_base is None or float(inss_base) <= 0:
        return None
    return round(float(inss_segurado or 0) + float(inss_base) * INSS_PATRONAL_RAT_TERCEIROS, 2)


def _portte_valor(db, empresa_id: str, tipo: str, mes: int, ano: int):
    """Valor da guia oficial da Portte (fiscal_obligations) para o CNPJ+competência."""
    r = db.execute(
        text(
            "SELECT valor_devido FROM fiscal_obligations "
            "WHERE tipo=:t AND competencia_mes=:m AND competencia_ano=:a "
            "AND empresa_id=:e AND active=true "
            "ORDER BY updated_at DESC LIMIT 1"
        ),
        {"t": tipo, "m": mes, "a": ano, "e": empresa_id},
    ).fetchone()
    return float(r[0]) if r and r[0] is not None else None


def _nosso_folha(db, empresa_id: str, periodo: str):
    """FGTS e INSS-segurado reais da folha (hr_payslips) do CNPJ+competência."""
    r = db.execute(
        text(
            "SELECT COALESCE(SUM(fgts_value),0), COALESCE(SUM(inss_value),0), "
            "COALESCE(SUM(inss_base),0), COUNT(*) "
            "FROM hr_payslips WHERE reference_period=:p AND empresa_id=:e "
            "AND status <> 'cancelled'"
        ),
        {"p": periodo, "e": empresa_id},
    ).fetchone()
    if not r or not r[3]:
        return {}
    return {"FGTS": float(r[0]), "INSS": _inss_total(r[1], r[2])}


def comparar(db, empresa_id: str, competencia: str) -> dict:
    """competencia = 'MM/AAAA'. Cruza nosso (folha real) × Portte (guia) por rubrica."""
    mes, ano = int(competencia[:2]), int(competencia[3:])
    periodo = f"{ano}-{mes:02d}"
    nosso = _nosso_folha(db, empresa_id, periodo)
    linhas = []
    for rubrica in ("FGTS", "INSS", "DAS"):
        n = nosso.get(rubrica)
        p = _portte_valor(db, empresa_id, rubrica, mes, ano)
        diff, bate = _status_linha(n, p)
        linhas.append({"rubrica": rubrica, "nosso": n, "portte": p, "diff": diff, "bate": bate})
    considerados = [l for l in linhas if l["nosso"] is not None or l["portte"] is not None]
    batidos = [l for l in considerados if l["bate"]]
    pct = round(100.0 * len(batidos) / len(considerados), 1) if considerados else None
    return {
        "empresa_id": empresa_id,
        "competencia": competencia,
        "linhas": linhas,
        "pct_batido": pct,
        "considerados": len(considerados),
        "batidos": len(batidos),
    }


def competencias_disponiveis(db, empresa_id: str) -> list[str]:
    """Competências 'MM/AAAA' com folha real para o CNPJ (mais recente primeiro)."""
    rows = db.execute(
        text(
            "SELECT DISTINCT reference_period FROM hr_payslips "
            "WHERE empresa_id=:e AND status <> 'cancelled' AND reference_period IS NOT NULL "
            "ORDER BY reference_period DESC"
        ),
        {"e": empresa_id},
    ).fetchall()
    out = []
    for (rp,) in rows:
        try:
            ano, mes = rp.split("-")[:2]
            out.append(f"{int(mes):02d}/{int(ano)}")
        except Exception:  # noqa: BLE001
            continue
    return out
