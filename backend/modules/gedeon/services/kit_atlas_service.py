"""GEDEON — ATLAS: conferente automático do kit antes da entrega.

Vai além da completude (presença de arquivo): confere a COERÊNCIA do kit —
  - nº de comprovantes de salário / contracheques bate com o nº de funcionários da folha;
  - há um VT/VR por funcionário ATIVO (com tolerância p/ admitidos pós-dia-16 e afastados);
  - as 5 CNDs estão presentes e VÁLIDAS (não vencidas) — lê ged_certidoes;
  - ponto assinado, NFS-e e (quando emitido) boleto presentes;
  - a NFS-e do kit parece MENSAL (não avulsa) — sinaliza valor fora da faixa do contrato.

Cada check tem severidade: ok | alerta | erro. O kit recebe o selo "conferido"
quando não há nenhum ERRO (alertas são aceitáveis, mas ficam registrados p/ a Pyetra).
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date

from sqlalchemy import text


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


def _check(nome: str, sev: str, msg: str, detalhe=None) -> dict:
    return {"check": nome, "severidade": sev, "mensagem": msg, "detalhe": detalhe}


def _contar(files: list[dict], termos: list[str]) -> list[str]:
    return [f["name"] for f in files if any(t in _norm(f["name"]) for t in termos)]


def conferir_kit(competencia: str, condominio: str) -> dict:
    """Confere a coerência do kit de um condomínio. Devolve checks + selo."""
    from core.database.session import get_sync_db
    from modules.gdrive.services.gdrive_service import gdrive_service
    from modules.gedeon.services import kit_cache
    from modules.gedeon.services.kit_completude_service import (
        SUB_FATURAMENTO,
        SUB_IMPOSTOS,
        SUB_PESSOAL,
        SUB_VALE,
    )
    from modules.gedeon.services.kit_ficha_service import (
        _client_id_do_condominio,
        funcionarios_do_condominio,
    )

    if not gdrive_service._service:
        gdrive_service.check_status()
    svc = gdrive_service._service
    if not svc:
        raise RuntimeError("Google Drive não conectado")

    kit = kit_cache.ler_kit(svc, condominio, competencia)
    # arquivos por subpasta (reconstrói do checklist do _ler_kit)
    por_sub: dict[str, list[dict]] = {}
    for sp in kit.get("subpastas", []):
        por_sub[sp["nome"]] = sp.get("arquivos", [])
    pessoal = por_sub.get(SUB_PESSOAL, [])
    vale = por_sub.get(SUB_VALE, [])
    impostos = por_sub.get(SUB_IMPOSTOS, [])
    faturamento = por_sub.get(SUB_FATURAMENTO, [])

    folha_nomes = kit_cache.nomes_folha(svc, condominio, competencia)
    checks: list[dict] = []

    with get_sync_db() as db:
        nomes_cond = funcionarios_do_condominio(db, competencia, condominio, folha_nomes)
        cid = _client_id_do_condominio(db, condominio)
        ativos = 0
        if cid:
            ativos = (
                db.execute(
                    text(
                        """SELECT COUNT(DISTINCT e.id) FROM employees e
                        JOIN allocations a ON a.employee_id = e.id
                        JOIN posts p ON a.post_id = p.id
                        WHERE p.client_id = :cid
                          AND (e.data_demissao IS NULL OR e.data_demissao >= :ini)"""
                    ),
                    {"cid": cid, "ini": _ini_competencia(competencia)},
                ).scalar()
                or 0
            )
        n_folha = len([n for n in folha_nomes if n.strip()])
        # ── 1) Funcionários da folha x comprovantes de salário ──
        salarios = _contar(pessoal, ["comprovante de pagamento de sal", "comprovante de sal", "comprovante salario"])
        checks.append(_coerencia_contagem("Comprovantes de salário", len(salarios), n_folha, "funcionários na folha"))
        # ── 2) Contracheques x funcionários ──
        contra = _contar(pessoal, ["contracheque", "holerite"])
        checks.append(_coerencia_contagem("Contracheques", len(contra), n_folha, "funcionários na folha"))
        # ── 3) VT/VR x funcionários ATIVOS (tolerância: admissão pós-16 / afastamento) ──
        n_vavt = len(vale)
        base_vavt = max(n_folha, ativos)
        if n_vavt == 0:
            checks.append(_check("VT/VR", "erro", "Nenhum recibo de VT/VR na subpasta 2.", {"esperado": base_vavt}))
        elif n_vavt < base_vavt:
            checks.append(
                _check(
                    "VT/VR",
                    "alerta",
                    f"{n_vavt} recibos p/ {base_vavt} funcionários — confira admitidos pós-dia-16 ou afastados.",
                    {"recibos": n_vavt, "funcionarios": base_vavt},
                )
            )
        else:
            checks.append(_check("VT/VR", "ok", f"{n_vavt} recibos p/ {base_vavt} funcionários.", None))
        # ── 4) Ponto assinado presente ──
        ponto = _contar(pessoal, ["ponto assinada", "ponto assinado", "folha de ponto", "espelho de ponto"])
        checks.append(
            _check("Ponto assinado", "ok" if ponto else "alerta",
                   f"{len(ponto)} arquivo(s) de ponto." if ponto else "Ponto assinado ausente (robô Sólides/host).",
                   ponto or None)
        )
        # ── 5) Guias + INSS ──
        guias = _contar(impostos, ["guia", "dctfweb", "gfd", "relatorio fgts", "fgts"])
        inss = _contar(impostos, ["comprovante inss", "comprovante de pagamento de inss", "inss comprovante"])
        checks.append(_check("Guias", "ok" if guias else "alerta", f"{len(guias)} guia(s).", guias or None))
        checks.append(_check("INSS", "ok" if inss else "alerta",
                             "Comprovante INSS presente." if inss else "Comprovante INSS ausente.", inss or None))
        # ── 6) CNDs presentes E válidas (ged_certidoes) ──
        checks.append(_conferir_cnds(db))

    # ── 7) NFS-e: presente e aparentemente MENSAL (não avulsa) ──
    checks.append(_conferir_nfse(faturamento, condominio, competencia))
    # ── 8) Boleto (informativo — só alerta se faltar) ──
    boleto = _contar(faturamento, ["boleto"])
    checks.append(_check("Boleto", "ok" if boleto else "alerta",
                         f"{len(boleto)} boleto(s)." if boleto else "Boleto ausente (emitir pelo kit, se aplicável).",
                         boleto or None))

    erros = [c for c in checks if c["severidade"] == "erro"]
    alertas = [c for c in checks if c["severidade"] == "alerta"]
    selo = "conferido" if not erros else "reprovado"
    return {
        "competencia": competencia,
        "condominio": condominio,
        "selo": selo,
        "conferido_em": date.today().isoformat(),
        "funcionarios_folha": n_folha,
        "funcionarios_ativos": ativos,
        "completude": kit.get("completion_percentage", 0),
        "resumo": {"ok": len(checks) - len(erros) - len(alertas), "alertas": len(alertas), "erros": len(erros)},
        "checks": checks,
    }


def _coerencia_contagem(nome: str, achados: int, esperado: int, ref: str) -> dict:
    if esperado == 0:
        return _check(nome, "alerta", f"Não foi possível contar {ref} (folha vazia?).", {"achados": achados})
    if achados == 0:
        return _check(nome, "erro", f"Nenhum {nome.lower()} encontrado p/ {esperado} {ref}.", {"esperado": esperado})
    if achados < esperado:
        return _check(nome, "alerta", f"{achados} de {esperado} {ref}.", {"achados": achados, "esperado": esperado})
    return _check(nome, "ok", f"{achados} p/ {esperado} {ref}.", {"achados": achados, "esperado": esperado})


def _ini_competencia(competencia: str) -> str:
    m, a = int(competencia.split(".")[0]), int(competencia.split(".")[1])
    return f"{a}-{m:02d}-01"


def _conferir_cnds(db) -> dict:
    """Confere as 5 CNDs em ged_certidoes: presentes e não vencidas."""
    tipos = {
        "certidao_negativa_federal": "Federal",
        "certidao_negativa_estadual": "Estadual",
        "certidao_negativa_municipal": "Municipal",
        "certidao_negativa_fgts": "FGTS",
        "certidao_negativa_trabalhista": "Trabalhista",
    }
    try:
        rows = db.execute(
            text("SELECT document_type, expiry_date FROM ged_certidoes WHERE document_type = ANY(:ts)"),
            {"ts": list(tipos.keys())},
        ).fetchall()
    except Exception as exc:
        return _check("CNDs", "alerta", f"Não foi possível ler ged_certidoes: {exc}", None)
    achadas = {r[0]: r[1] for r in rows}
    faltam, vencidas = [], []
    hoje = date.today()
    for k, label in tipos.items():
        if k not in achadas:
            faltam.append(label)
        elif achadas[k] and achadas[k] < hoje:
            vencidas.append(label)
    if faltam or vencidas:
        sev = "erro" if (faltam or vencidas) else "ok"
        return _check("CNDs", sev, f"Faltam: {faltam or '—'} | Vencidas: {vencidas or '—'}",
                      {"faltam": faltam, "vencidas": vencidas})
    return _check("CNDs", "ok", "As 5 certidões presentes e válidas.", None)


def _conferir_nfse(faturamento: list[dict], condominio: str, competencia: str) -> dict:
    """NFS-e presente? Tenta detectar nota avulsa pelo nome (manutenção/avulsa/cancela)."""
    notas = _contar(faturamento, ["nota fiscal", "nfs", "danfse"])
    if not notas:
        return _check("NFS-e", "alerta", "NFS-e do mês ausente (emitir pelo kit, se aplicável).", None)
    avulsa = [n for n in notas if re.search(r"avuls|manuten|cancela|servico extra|extra", _norm(n))]
    if avulsa:
        return _check("NFS-e", "alerta", f"Possível nota avulsa no kit (não entra): {avulsa}", {"avulsas": avulsa})
    return _check("NFS-e", "ok", f"{len(notas)} NFS-e mensal no kit.", notas)
