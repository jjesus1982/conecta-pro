"""GEDEON — bloco "ponto" do kit a partir do NOSSO ponto (09/09/2026).

Antes o ponto do kit vinha do robô do Sólides (host, Playwright) — e a conta do Sólides está bloqueada por
pagamento. Decisão do dono em 09/09: "já temos o nosso sistema de ponto, usado real no dia a dia; coleta dele".
Fonte: `time_sheets` (espelho calculado pelo motor do ponto, 53 colaboradores em 08/2026) → o MESMO PDF que o DP
baixa em /hr/espelho-ponto (montar_espelho_ponto_pdf, com o bloco de autenticidade se já houver assinatura).
Sem espelho calculado = falta declarada (não inventa folha a partir de batida crua).
"""
from __future__ import annotations

import logging
import re
import unicodedata
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import text

logger = logging.getLogger(__name__)
PONTO_KIT_STORAGE = Path("/app/uploads/kits/ponto")


def _norm(s: str | None) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper().strip()


def _janela_kit(mes: int, ano: int) -> tuple[date, date]:
    """Período da FOLHA DE PONTO do kit: 26 do mês anterior a 25 da competência (regra da Pyetra, 09/09/2026)."""
    fim = date(ano, mes, 25)
    ini = date(ano - 1, 12, 26) if mes == 1 else date(ano, mes - 1, 26)
    return ini, fim


def _dias_corridos(db, employee_id: str, ini: date, fim: date, dias_apurados: list[dict]) -> list[dict]:
    """TODOS os dias do período, não só os trabalhados (Pyetra: "precisamos dos dias de 26/x a 25/y corridos").

    Usa o que o motor apurou quando existe; nos demais, lê as batidas do dia e marca folga/sem registro.
    """
    from sqlalchemy import text as _t

    por_data = {str(d.get("date") or d.get("data"))[:10]: d for d in (dias_apurados or [])}
    linhas_bd = db.execute(_t(
        "SELECT punch_timestamp::date AS d, min(punch_timestamp::time) AS ent, max(punch_timestamp::time) AS sai, count(*) AS n "
        "FROM gp_clock_punches WHERE employee_id = CAST(:e AS uuid) AND punch_timestamp::date BETWEEN :i AND :f "
        "GROUP BY 1"), {"e": str(employee_id), "i": ini, "f": fim}).fetchall()
    batidas = {str(r[0]): r for r in linhas_bd}
    out: list[dict] = []
    d = ini
    while d <= fim:
        chave = d.isoformat()
        if chave in por_data:
            out.append(por_data[chave])
        elif chave in batidas:
            r = batidas[chave]
            out.append({"date": chave, "entrada": str(r[1])[:5], "saida": str(r[2])[:5],
                        "ocorrencia": "Registro de ponto" if r[3] > 1 else "Batida única"})
        else:
            out.append({"date": chave, "entrada": "—", "saida": "—",
                        "ocorrencia": "Folga / sem registro"})
        d += timedelta(days=1)
    return out


def espelho_pdf_do_mes(db, employee_id: str, mes: int, ano: int) -> tuple[bytes | None, str, str | None]:
    """(pdf, nome_do_funcionario, motivo_da_falta). Reusa ler_espelho + montar_espelho_ponto_pdf do DP.

    09/09/2026 (Pyetra): a folha de ponto do KIT cobre 26/x a 25/y com TODOS os dias corridos — a apuração legal
    (time_sheets) continua mensal civil; aqui só o documento muda de janela.
    """
    from modules.people_management.hr.services.espelho_ponto_pdf import montar_espelho_ponto_pdf
    from modules.people_management.hr.services.espelho_ponto_service import ler_espelho

    esp = ler_espelho(db, employee_id, mes, ano)
    nome = (esp or {}).get("employee_name") or db.execute(
        text("SELECT nome FROM employees WHERE id = CAST(:e AS uuid)"), {"e": employee_id}
    ).scalar() or employee_id
    if not esp:
        return None, nome, f"espelho de {mes:02d}/{ano} não calculado no ponto (rodar o cálculo do mês)"
    signatarios = None
    try:
        from modules.signatures.helpers import status_documento_sync

        stt = status_documento_sync("espelho_ponto", esp["time_sheet_id"])
        if stt:
            signatarios = stt.get("signatarios")
    except Exception:  # noqa: BLE001
        signatarios = None
    ini, fim = _janela_kit(mes, ano)
    esp = dict(esp)
    esp["dias"] = _dias_corridos(db, employee_id, ini, fim, esp.get("dias") or [])
    esp["periodo_kit"] = f"{ini:%d/%m/%Y} a {fim:%d/%m/%Y}"
    return montar_espelho_ponto_pdf(esp, signatarios=signatarios), nome, None


def arquivar_ponto_proprio(competencia: str, condominios: list[str], dry_run: bool = False) -> dict:
    """Para cada condomínio: colaboradores alocados → espelho do mês → "Folha de Ponto_<Nome>.pdf" na subpasta
    de pessoal do kit (mesma convenção do robô do Sólides, sem o 'Assinada' quando não há assinatura)."""
    from core.database.session import get_sync_db
    from modules.gdrive.services.gdrive_service import gdrive_service
    from modules.gedeon.services.kit_ficha_service import _client_id_do_condominio
    from modules.gedeon.services.kit_layout import _arquivo_ja_existe, pasta_kit_arquivo

    mes, ano = int(competencia.split(".")[0]), int(competencia.split(".")[1])
    rel: dict = {"competencia": competencia, "arquivados": 0, "ja_existiam": 0, "faltas": [], "por_condominio": {}}
    if not dry_run and not gdrive_service._service:
        gdrive_service.check_status()
    cache: dict = {}
    with get_sync_db() as db:
        for cond in condominios:
            cid = _client_id_do_condominio(db, cond)
            if not cid:
                rel["faltas"].append(f"{cond}: não casa com nenhum cliente (clients/condominiums)")
                continue
            emps = db.execute(
                text(
                    "SELECT DISTINCT e.id::text, e.nome FROM employees e JOIN allocations a ON a.employee_id = e.id "
                    "JOIN posts p ON p.id = a.post_id WHERE p.client_id = CAST(:c AS uuid) AND coalesce(e.status,'active') <> 'inactive'"
                ),
                {"c": cid},
            ).fetchall()
            n = 0
            for eid, nome in emps:
                pdf, nome_esp, motivo = espelho_pdf_do_mes(db, eid, mes, ano)
                if not pdf:
                    rel["faltas"].append(f"{cond} / {nome}: {motivo}")
                    continue
                fn = f"Folha de Ponto_{(nome_esp or nome).title()}.pdf"
                d = PONTO_KIT_STORAGE / competencia / re.sub(r"[^A-Za-z0-9_-]+", "_", _norm(cond))
                d.mkdir(parents=True, exist_ok=True)
                path = d / fn
                path.write_bytes(pdf)
                if dry_run:
                    n += 1
                    continue
                folder = pasta_kit_arquivo(cond, competencia, fn, cache)
                if not folder:
                    rel["faltas"].append(f"{cond}: pasta do kit no Drive indisponível")
                    break
                if _arquivo_ja_existe(folder, fn):
                    rel["ja_existiam"] += 1
                    continue
                if gdrive_service.fazer_upload_arquivo(str(path), folder, fn):
                    n += 1
                else:
                    rel["faltas"].append(f"{cond} / {nome}: upload falhou")
            rel["por_condominio"][cond] = n
            rel["arquivados"] += n
    logger.info("GEDEON ponto próprio %s: %s", competencia, rel)
    return rel
