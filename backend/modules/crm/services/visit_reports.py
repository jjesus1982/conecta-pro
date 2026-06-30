"""Assistente de Visita Técnica & Comercial — José Luís ajuda o Jordan no campo.

Fluxo: Jordan informa cliente + panorama, manda fotos/áudios/vídeos (analisados pela visão/Whisper
do agente ou pelo Cowork) → viram "achados" → José Luís/Cowork sintetizam um relatório técnico+comercial
estruturado → vira PDF (selo Conecta Mais), lead/oportunidade no CRM e reunião agendada (com confirmação).

A INTELIGÊNCIA (análise de mídia + redação) é do LLM (José Luís no WhatsApp ou o Claude no Cowork);
este serviço PERSISTE, gera o PDF, cadastra no CRM e agenda. Sem inventar dado.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ── Relatório de visita ────────────────────────────────────────────────────────────────────
async def criar_relatorio(
    db: AsyncSession,
    *,
    cliente_nome: str,
    panorama: str | None = None,
    data_visita=None,
    criado_por: str | None = None,
    lead_id=None,
    deal_id=None,
    cliente_id=None,
) -> dict:
    row = (
        (
            await db.execute(
                text("""
        INSERT INTO crm_visit_reports
          (id, cliente_nome, panorama, data_visita, criado_por, lead_id, deal_id, cliente_id,
           created_at, updated_at)
        VALUES (gen_random_uuid(), :nome, :pan, :dt, :por, :lid, :did, :cid, now(), now())
        RETURNING id, cliente_nome, status
    """),
                {
                    "nome": cliente_nome,
                    "pan": panorama,
                    "dt": data_visita,
                    "por": criado_por,
                    "lid": lead_id,
                    "did": deal_id,
                    "cid": cliente_id,
                },
            )
        )
        .mappings()
        .first()
    )
    await db.commit()
    return {"id": str(row["id"]), "cliente": row["cliente_nome"], "status": row["status"]}


async def _achar(db: AsyncSession, ref: str) -> dict | None:
    r = (
        (
            await db.execute(
                text("""
        SELECT * FROM crm_visit_reports
        WHERE id::text=:r OR cliente_nome ILIKE :like ORDER BY updated_at DESC LIMIT 1
    """),
                {"r": ref, "like": f"%{ref}%"},
            )
        )
        .mappings()
        .first()
    )
    return dict(r) if r else None


async def adicionar_achados(db: AsyncSession, ref: str, achados: list) -> dict:
    """Anexa achados (análises de fotos/áudios/vídeos ou notas) ao relatório."""
    rel = await _achar(db, ref)
    if not rel:
        return {"ok": False, "motivo": "relatório de visita não encontrado"}
    norm = []
    for a in achados or []:
        if isinstance(a, dict):
            norm.append({"tipo": a.get("tipo") or "nota", "descricao": a.get("descricao") or ""})
        else:
            norm.append({"tipo": "nota", "descricao": str(a)})
    await db.execute(
        text("UPDATE crm_visit_reports SET achados = achados || CAST(:novos AS jsonb), updated_at=now() WHERE id=:id"),
        {"novos": json.dumps(norm, ensure_ascii=False), "id": rel["id"]},
    )
    await db.commit()
    total = len(rel.get("achados") or []) + len(norm)
    return {"ok": True, "id": str(rel["id"]), "achados_adicionados": len(norm), "achados_total": total}


async def montar_relatorio(
    db: AsyncSession,
    ref: str,
    *,
    situacao_atual=None,
    diagnostico_tecnico=None,
    oportunidade_comercial=None,
    proximos_passos=None,
    conteudo_md=None,
) -> dict:
    """Grava o relatório sintetizado (o LLM redige; aqui persiste). Campos None não sobrescrevem."""
    rel = await _achar(db, ref)
    if not rel:
        return {"ok": False, "motivo": "relatório de visita não encontrado"}
    await db.execute(
        text("""
        UPDATE crm_visit_reports SET
          situacao_atual = COALESCE(:sit, situacao_atual),
          diagnostico_tecnico = COALESCE(:diag, diagnostico_tecnico),
          oportunidade_comercial = COALESCE(:op, oportunidade_comercial),
          proximos_passos = COALESCE(:prox, proximos_passos),
          conteudo_md = COALESCE(:md, conteudo_md), updated_at=now()
        WHERE id=:id
    """),
        {
            "sit": situacao_atual,
            "diag": diagnostico_tecnico,
            "op": oportunidade_comercial,
            "prox": proximos_passos,
            "md": conteudo_md,
            "id": rel["id"],
        },
    )
    await db.commit()
    return {"ok": True, "id": str(rel["id"]), "cliente": rel["cliente_nome"]}


async def get_relatorio(db: AsyncSession, ref: str) -> dict | None:
    return await _achar(db, ref)


async def listar_relatorios(db: AsyncSession, limit: int = 30) -> list[dict]:
    rows = (
        (
            await db.execute(
                text("""
        SELECT id, cliente_nome, status, to_char(created_at,'DD/MM/YYYY') AS criado,
               jsonb_array_length(achados) AS qtd_achados,
               (situacao_atual IS NOT NULL) AS tem_diagnostico
        FROM crm_visit_reports ORDER BY updated_at DESC LIMIT :l
    """),
                {"l": limit},
            )
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


async def pdf_data(db: AsyncSession, ref: str) -> dict | None:
    rel = await _achar(db, ref)
    if not rel:
        return None
    return {
        "numero": str(rel["id"])[:8].upper(),
        "cliente_nome": rel["cliente_nome"],
        "data_visita": rel["data_visita"],
        "panorama": rel["panorama"],
        "situacao_atual": rel["situacao_atual"],
        "diagnostico_tecnico": rel["diagnostico_tecnico"],
        "oportunidade_comercial": rel["oportunidade_comercial"],
        "proximos_passos": rel["proximos_passos"],
        "achados": rel["achados"],
        "responsavel": rel.get("criado_por") or "Conecta Mais — Vendas e Projetos",
    }


async def finalizar(db: AsyncSession, ref: str) -> dict:
    rel = await _achar(db, ref)
    if not rel:
        return {"ok": False, "motivo": "não encontrado"}
    await db.execute(
        text("UPDATE crm_visit_reports SET status='finalizado', updated_at=now() WHERE id=:id"), {"id": rel["id"]}
    )
    await db.commit()
    return {"ok": True, "id": str(rel["id"]), "status": "finalizado"}


# ── Cadastro de lead/oportunidade a partir da visita ───────────────────────────────────────
async def registrar_lead_da_visita(
    db: AsyncSession, ref: str, *, telefone=None, cnpj=None, segmento=None, valor_estimado=None
) -> dict:
    """Cria/atualiza lead + oportunidade a partir do relatório de visita."""
    from modules.crm.services.phone import canonical_br

    rel = await _achar(db, ref)
    if not rel:
        return {"ok": False, "motivo": "relatório não encontrado"}
    nome = rel["cliente_nome"] or "Cliente (visita)"
    lead_id = rel.get("lead_id")
    phone_c = canonical_br(telefone) if telefone else None
    # acha lead existente por telefone, senão cria
    if not lead_id and phone_c:
        ex = (
            await db.execute(
                text(
                    "SELECT id FROM leads WHERE regexp_replace(coalesce(phone,''),'\\D','','g')=:p "
                    "AND is_active LIMIT 1"
                ),
                {"p": phone_c},
            )
        ).first()
        if ex:
            lead_id = str(ex[0])
    if not lead_id:
        row = (
            (
                await db.execute(
                    text("""
            INSERT INTO leads (id, name, phone, company, source, status, score, probability,
                               expected_value, is_active, created_at, updated_at)
            VALUES (gen_random_uuid(), :n, :p, :n, 'visita_tecnica', 'qualified', 60, 50,
                    :v, true, now(), now())
            RETURNING id
        """),
                    {"n": nome[:255], "p": phone_c, "v": float(valor_estimado or 0)},
                )
            )
            .mappings()
            .first()
        )
        lead_id = str(row["id"])
    # cria oportunidade
    deal = (
        (
            await db.execute(
                text("""
        INSERT INTO opportunities
          (id, title, company_name, contact_name, contact_email, contact_phone, stage, priority,
           value, probability, lead_id, is_active, created_at, updated_at)
        VALUES (gen_random_uuid(), :t, :c, :c, '', :p, 'qualification', 'medium', :v, 25, :lid,
                true, now(), now())
        RETURNING id
    """),
                {
                    "t": f"Visita técnica — {nome}",
                    "c": nome[:255],
                    "p": phone_c,
                    "v": float(valor_estimado or 0),
                    "lid": lead_id,
                },
            )
        )
        .mappings()
        .first()
    )
    await db.execute(
        text("UPDATE crm_visit_reports SET lead_id=:lid, deal_id=:did, updated_at=now() WHERE id=:id"),
        {"lid": lead_id, "did": str(deal["id"]), "id": rel["id"]},
    )
    await db.commit()
    return {"ok": True, "lead_id": lead_id, "deal_id": str(deal["id"]), "cliente": nome}


# ── Reuniões (sugerir → confirmar; com lembrete pré-reunião) ────────────────────────────────
async def sugerir_reuniao(
    db: AsyncSession,
    *,
    titulo: str,
    quando: datetime,
    cliente_nome=None,
    local=None,
    tipo: str = "reuniao",
    lead_id=None,
    deal_id=None,
    visit_report_id=None,
    criado_por=None,
    notes=None,
) -> dict:
    row = (
        (
            await db.execute(
                text("""
        INSERT INTO crm_meetings
          (id, titulo, cliente_nome, quando, local, tipo, status, lead_id, deal_id, visit_report_id,
           criado_por, notes, created_at, updated_at)
        VALUES (gen_random_uuid(), :t, :c, :q, :loc, :tp, 'sugerido', :lid, :did, :vid, :por, :nt, now(), now())
        RETURNING id
    """),
                {
                    "t": titulo,
                    "c": cliente_nome,
                    "q": quando,
                    "loc": local,
                    "tp": tipo,
                    "lid": lead_id,
                    "did": deal_id,
                    "vid": visit_report_id,
                    "por": criado_por,
                    "nt": notes,
                },
            )
        )
        .mappings()
        .first()
    )
    await db.commit()
    return {"ok": True, "id": str(row["id"]), "status": "sugerido", "quando": quando.isoformat()}


async def confirmar_reuniao(db: AsyncSession, meeting_id: str) -> dict:
    row = (
        (
            await db.execute(
                text(
                    "UPDATE crm_meetings SET status='confirmado', updated_at=now() WHERE id=:id "
                    "RETURNING titulo, to_char(quando,'DD/MM HH24:MI') AS quando"
                ),
                {"id": meeting_id},
            )
        )
        .mappings()
        .first()
    )
    await db.commit()
    return {"ok": bool(row), **(dict(row) if row else {})}


async def cancelar_reuniao(db: AsyncSession, meeting_id: str) -> dict:
    await db.execute(
        text("UPDATE crm_meetings SET status='cancelado', updated_at=now() WHERE id=:id"), {"id": meeting_id}
    )
    await db.commit()
    return {"ok": True, "status": "cancelado"}


async def listar_reunioes(db: AsyncSession, futuras: bool = True, limit: int = 30) -> list[dict]:
    where = "WHERE status <> 'cancelado'" + (" AND quando >= now() - interval '1 day'" if futuras else "")
    rows = (
        (
            await db.execute(
                text(f"""
        SELECT id, titulo, cliente_nome, to_char(quando,'DD/MM/YYYY HH24:MI') AS quando,
               local, tipo, status FROM crm_meetings {where} ORDER BY quando ASC LIMIT :l
    """),
                {"l": limit},
            )
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]
