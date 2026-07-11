"""Portal do Cliente — Resumo mensal automático (reengajamento).

Todo dia 1º (beat) cada cliente com portal habilitado recebe, na caixa do portal
e por e-mail (se PORTAL_NOTIFY_ENABLED=true), o retrato do mês anterior do SEU
condomínio: kit documental, assiduidade da equipe, ocorrências e visitas de
gestão. 100% dado real — seção sem dado sai como "sem registros", nunca inventa.
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.client_portal.services import portal_notify_service
from modules.client_portal.services.portal_operacao_service import _resolver, assiduidade

logger = logging.getLogger(__name__)

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
         "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


def competencia_anterior(hoje: date | None = None) -> str:
    h = hoje or date.today()
    m, a = (12, h.year - 1) if h.month == 1 else (h.month - 1, h.year)
    return f"{a}-{m:02d}"


async def montar_resumo(db: AsyncSession, client_id: str, competencia: str) -> dict:
    """Coleta os fatos do mês para UM cliente. Não envia nada."""
    ano, mes = int(competencia[:4]), int(competencia[5:7])
    ctx = await _resolver(db, client_id)

    # Kit documental da competência
    kit = (
        await db.execute(
            text(
                """SELECT id::text, status FROM ged_document_kits
                   WHERE client_id = :cid
                     AND to_char(reference_month, 'YYYY-MM') = :comp
                   ORDER BY created_at DESC LIMIT 1"""
            ),
            {"cid": client_id, "comp": competencia},
        )
    ).first()

    # Assiduidade real da equipe (serviço existente do portal, mesma competência)
    assid = {}
    try:
        assid = await assiduidade(db, client_id, competencia)
    except Exception as exc:  # dado indisponível ≠ inventar
        logger.warning("Resumo mensal: assiduidade indisponível p/ %s: %s", client_id, exc)

    ocorrencias = visitas = 0
    if ctx.get("post_ids"):
        ocorrencias = (
            await db.execute(
                text(
                    """SELECT count(*) FROM occurrences o
                       WHERE o.post_id = ANY(CAST(:pids AS uuid[])) AND o.is_active
                         AND o.category IN ('operacional','seguranca_trabalho','outros')
                         AND EXTRACT(MONTH FROM o.occurred_at) = :m
                         AND EXTRACT(YEAR FROM o.occurred_at) = :a"""
                ),
                {"pids": ctx["post_ids"], "m": mes, "a": ano},
            )
        ).scalar() or 0
        visitas = (
            await db.execute(
                text(
                    """SELECT count(DISTINCT r.id)
                       FROM inspection_rounds r
                       JOIN inspection_checkpoints c ON c.inspection_round_id = r.id
                       WHERE r.is_active
                         AND c.post_id = ANY(CAST(:pids AS uuid[]))
                         AND EXTRACT(MONTH FROM c.created_at AT TIME ZONE 'UTC'
                                     AT TIME ZONE 'America/Manaus') = :m
                         AND EXTRACT(YEAR FROM c.created_at AT TIME ZONE 'UTC'
                                     AT TIME ZONE 'America/Manaus') = :a"""
                ),
                {"pids": ctx["post_ids"], "m": mes, "a": ano},
            )
        ).scalar() or 0

    return {
        "competencia": competencia,
        "condominio": ctx.get("cond_nome"),
        "kit": {"id": kit[0], "status": kit[1]} if kit else None,
        "assiduidade": assid.get("resumo") or assid or None,
        "ocorrencias": int(ocorrencias),
        "visitas_gestao": int(visitas),
    }


def _texto(resumo: dict) -> tuple[str, str]:
    comp = resumo["competencia"]
    mes_nome = MESES[int(comp[5:7]) - 1]
    titulo = f"Resumo de {mes_nome} — {resumo.get('condominio') or 'seu condomínio'}"
    linhas = []
    if resumo.get("kit"):
        st = resumo["kit"]["status"]
        linhas.append(
            "📄 Kit documental do mês: "
            + ("disponível no portal" if st in ("enviado", "em_montagem") else st)
        )
    else:
        linhas.append("📄 Kit documental do mês: em preparação")
    assid = resumo.get("assiduidade") or {}
    taxa = assid.get("taxa_presenca") or assid.get("presenca_pct")
    if taxa is not None:
        linhas.append(f"👥 Presença da equipe: {taxa}%")
    linhas.append(
        f"📋 Ocorrências operacionais no mês: {resumo['ocorrencias']}"
        if resumo["ocorrencias"] else "📋 Nenhuma ocorrência operacional no mês"
    )
    linhas.append(
        f"🧭 Visitas da gestão Conecta ao condomínio: {resumo['visitas_gestao']}"
        if resumo["visitas_gestao"] else "🧭 Visitas da gestão: sem registros no mês"
    )
    linhas.append("\nAcesse o portal para os detalhes completos e documentos.")
    return titulo, "\n".join(linhas)


async def enviar_resumo_cliente(
    db: AsyncSession,
    client_id: str,
    competencia: str | None = None,
    enviar_email: bool = True,
    email_override: str | None = None,
) -> dict:
    comp = competencia or competencia_anterior()
    resumo = await montar_resumo(db, client_id, comp)
    titulo, msg = _texto(resumo)
    envio = await portal_notify_service.notificar(
        db, client_id, tipo="resumo_mensal", titulo=titulo, mensagem=msg,
        link="/area-cliente", forcar_email=enviar_email, email_override=email_override,
    )
    return {"client_id": client_id, "competencia": comp, "resumo": resumo, "envio": envio}


async def enviar_resumo_todos(db: AsyncSession, competencia: str | None = None) -> dict:
    comp = competencia or competencia_anterior()
    clientes = (
        await db.execute(
            text("SELECT id::text, name FROM ged_clients WHERE portal_access_enabled = TRUE")
        )
    ).all()
    ok, falhas = 0, []
    for cid, nome in clientes:
        try:
            await enviar_resumo_cliente(db, cid, comp)
            ok += 1
        except Exception as exc:
            logger.error("Resumo mensal falhou p/ %s (%s): %s", nome, cid, exc)
            falhas.append(nome)
    return {"competencia": comp, "enviados": ok, "falhas": falhas}
