"""Portal do Cliente — Visitas de gestão ao condomínio (rondas de inspeção).

Mostra ao síndico QUANDO a gestão da Conecta esteve no condomínio, o que fez
(check-in/checkout, reunião, verificação) e as fotos de evidência — prova de
serviço prestado, escopada ao condomínio do cliente.

SANITIZAÇÃO (mesma doutrina das ocorrências do portal):
- Allowlist de tipos: só checkpoints de visita (check-in/out, reunião,
  verificação de posto, observação geral). Checkpoints ligados a OCORRÊNCIA,
  MEDIDA DISCIPLINAR ou verificação de FUNCIONÁRIO ficam de fora.
- NUNCA expor: descrição/observações internas do supervisor, dados de
  funcionários, categoria/severidade de infração.
- Fotos: apenas de checkpoints allowlisted; download validado na cadeia
  cliente→posto→ronda→checkpoint→arquivo (path-safe).

Horários: created_at do banco é UTC naive → convertidos para America/Manaus.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.client_portal.services.portal_operacao_service import _resolver

TZ_MANAUS = ZoneInfo("America/Manaus")
FOTOS_DIR = Path("/app/uploads/rondas")

TIPOS_VISIVEIS = (
    "checkin_condominio",
    "checkout_condominio",
    "reuniao",
    "verificacao_posto",
    "observacao_geral",
)

TIPO_LABEL = {
    "checkin_condominio": "Chegada ao condomínio",
    "checkout_condominio": "Saída do condomínio",
    "reuniao": "Reunião",
    "verificacao_posto": "Verificação do posto",
    "observacao_geral": "Observação geral",
}

PAPEL_LABEL = {
    "gerente_operacional": "Gerência Operacional",
    "supervisor_operacional": "Supervisão Operacional",
    "inspetor_operacional": "Inspetoria",
    "lider_servico": "Liderança de Serviço",
}


def _manaus(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone(TZ_MANAUS).replace(tzinfo=None)


async def visitas(db: AsyncSession, client_id: str, limite: int = 10) -> dict:
    """Últimas visitas de gestão ao condomínio do cliente, sanitizadas."""
    ctx = await _resolver(db, client_id)
    if not ctx.get("post_ids"):
        return {"condominio": ctx.get("cond_nome"), "visitas": [],
                "mensagem": "Nenhum posto vinculado ao condomínio."}

    rows = (
        await db.execute(
            text(
                """
                SELECT r.id::text AS round_id, r.status, r.inspector_role,
                       r.duration_minutes,
                       c.id::text AS checkpoint_id, c.checkpoint_type,
                       c.created_at, c.photos
                FROM inspection_rounds r
                JOIN inspection_checkpoints c ON c.inspection_round_id = r.id
                WHERE r.is_active
                  AND c.post_id = ANY(CAST(:pids AS uuid[]))
                  AND c.checkpoint_type = ANY(CAST(:tipos AS text[]))
                  AND c.occurrence_id IS NULL
                  AND c.disciplinary_action_id IS NULL
                ORDER BY c.created_at DESC
                LIMIT 300
                """
            ),
            {"pids": ctx["post_ids"], "tipos": list(TIPOS_VISIVEIS)},
        )
    ).mappings().all()

    por_ronda: dict[str, dict] = {}
    for r in rows:
        v = por_ronda.setdefault(
            r["round_id"],
            {
                "round_id": r["round_id"],
                "status": r["status"],
                "responsavel": PAPEL_LABEL.get(r["inspector_role"] or "", "Gestão Conecta"),
                "duracao_minutos": r["duration_minutes"],
                "checkin": None,
                "checkout": None,
                "atividades": [],
                "fotos": [],
            },
        )
        quando = _manaus(r["created_at"])
        item = {
            "tipo": r["checkpoint_type"],
            "tipo_label": TIPO_LABEL.get(r["checkpoint_type"], r["checkpoint_type"]),
            "hora": quando.isoformat(timespec="minutes") if quando else None,
        }
        if r["checkpoint_type"] == "checkin_condominio":
            v["checkin"] = item["hora"]
        elif r["checkpoint_type"] == "checkout_condominio":
            v["checkout"] = item["hora"]
        else:
            v["atividades"].append(item)
        for foto in (r["photos"] or []):
            arquivo = foto.get("arquivo") if isinstance(foto, dict) else None
            if arquivo:
                v["fotos"].append(
                    {
                        "checkpoint_id": r["checkpoint_id"],
                        "arquivo": arquivo,
                        "url": (
                            f"/api/v1/portal/operacao/visitas/{r['round_id']}"
                            f"/checkpoints/{r['checkpoint_id']}/fotos/{arquivo}"
                        ),
                    }
                )

    # data da visita = menor hora entre os checkpoints (ordenar por ela, desc)
    visitas_lista = []
    for v in por_ronda.values():
        horas = [h for h in [v["checkin"], v["checkout"]] + [a["hora"] for a in v["atividades"]] if h]
        v["data"] = min(horas)[:10] if horas else None
        v["inicio"] = min(horas) if horas else None
        visitas_lista.append(v)
    visitas_lista.sort(key=lambda x: x["inicio"] or "", reverse=True)

    return {
        "condominio": ctx.get("cond_nome"),
        "total_visitas": len(visitas_lista),
        "visitas": visitas_lista[:limite],
    }


async def foto_autorizada(
    db: AsyncSession, client_id: str, round_id: str, checkpoint_id: str, nome: str
) -> Path | None:
    """Valida a cadeia cliente→posto→ronda→checkpoint→foto e devolve o path (ou None)."""
    ctx = await _resolver(db, client_id)
    if not ctx.get("post_ids"):
        return None
    ok = (
        await db.execute(
            text(
                """
                SELECT 1
                FROM inspection_checkpoints c
                JOIN inspection_rounds r ON r.id = c.inspection_round_id AND r.is_active
                WHERE c.id = CAST(:cid AS uuid)
                  AND c.inspection_round_id = CAST(:rid AS uuid)
                  AND c.post_id = ANY(CAST(:pids AS uuid[]))
                  AND c.checkpoint_type = ANY(CAST(:tipos AS text[]))
                  AND c.occurrence_id IS NULL
                  AND c.disciplinary_action_id IS NULL
                  AND c.photos::text LIKE :arq
                """
            ),
            {
                "cid": checkpoint_id, "rid": round_id, "pids": ctx["post_ids"],
                "tipos": list(TIPOS_VISIVEIS), "arq": f'%"{nome}"%',
            },
        )
    ).first()
    if not ok:
        return None
    base = (FOTOS_DIR / round_id / checkpoint_id).resolve()
    alvo = (base / nome).resolve()
    if not str(alvo).startswith(str(base)) or not alvo.is_file():
        return None
    return alvo
