"""Prazos / Compliance (Jurídico) — CRUD + agregação read-only.

Fonte da verdade: tabela real `juridico_prazos` (titulo, tipo, data_limite,
status, contrato_id, descricao). O status é RECOMPUTADO na leitura: um prazo
'aberto' cuja data_limite já passou é reportado como 'atrasado' (sem escrever
no banco — cálculo cego sobre o fato).

Além dos prazos gravados, o GET agrega prazos AUTOMÁTICOS (read-only, id
prefixado) computados a partir de dado real:
  - fim de vigência de contratos ativos (`contracts.end_date`)
  - validade de certidões (`ged_certidoes.expiry_date`)
Esses agregados NÃO são gravados — são calculados a cada leitura para não
duplicar a verdade. Vazio → 0 honesto.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Janelas de alerta (dias) para prazos vencendo
_JANELAS = (7, 15, 30)

_STATUS_VALIDOS = {"aberto", "cumprido", "atrasado"}


def _dias(d: date | None, hoje: date) -> int | None:
    return (d - hoje).days if d else None


def _status_calculado(status: str | None, data_limite: date | None, hoje: date) -> str:
    """Atrasado se data_limite < hoje e o prazo ainda está 'aberto'."""
    s = (status or "aberto").lower()
    if s == "aberto" and data_limite is not None and data_limite < hoje:
        return "atrasado"
    return s


def _nivel_alerta(dias: int | None) -> str | None:
    """Menor janela em que o prazo se enquadra (só para prazos abertos futuros)."""
    if dias is None or dias < 0:
        return None
    for j in _JANELAS:
        if dias <= j:
            return f"{j}d"
    return None


async def _prazos_gravados(db: AsyncSession, hoje: date) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            text(
                """
                SELECT p.id, p.titulo, p.tipo, p.data_limite, p.status,
                       p.contrato_id, p.descricao, p.created_at,
                       c.contract_number, c.name AS contrato_nome
                FROM juridico_prazos p
                LEFT JOIN contracts c ON c.id = p.contrato_id
                ORDER BY p.data_limite ASC NULLS LAST
                """
            )
        )
    ).mappings().all()
    out: list[dict[str, Any]] = []
    for r in rows:
        dl = r["data_limite"]
        dias = _dias(dl, hoje)
        out.append(
            {
                "id": str(r["id"]),
                "origem": "prazo",
                "editavel": True,
                "titulo": r["titulo"],
                "tipo": r["tipo"] or "geral",
                "data_limite": dl.isoformat() if dl else None,
                "dias_restantes": dias,
                "status": _status_calculado(r["status"], dl, hoje),
                "status_registrado": (r["status"] or "aberto").lower(),
                "contrato_id": str(r["contrato_id"]) if r["contrato_id"] else None,
                "contrato_numero": r["contract_number"],
                "contrato_nome": r["contrato_nome"],
                "descricao": r["descricao"],
                "nivel_alerta": _nivel_alerta(dias),
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
        )
    return out


async def _prazos_de_contratos(db: AsyncSession, hoje: date) -> list[dict[str, Any]]:
    """Fim de vigência de contratos ativos como prazos automáticos read-only."""
    rows = (
        await db.execute(
            text(
                """
                SELECT c.id, c.contract_number, c.name, c.end_date, c.status
                FROM contracts c
                WHERE c.end_date IS NOT NULL
                  AND lower(c.status::text) = 'active'
                ORDER BY c.end_date ASC
                """
            )
        )
    ).mappings().all()
    out: list[dict[str, Any]] = []
    for r in rows:
        dl = r["end_date"]
        dias = _dias(dl, hoje)
        atrasado = dias is not None and dias < 0
        out.append(
            {
                "id": f"contrato:{r['id']}",
                "origem": "contrato",
                "editavel": False,
                "titulo": f"Fim de vigência — {r['name'] or r['contract_number'] or 'contrato'}",
                "tipo": "vigencia_contrato",
                "data_limite": dl.isoformat() if dl else None,
                "dias_restantes": dias,
                "status": "atrasado" if atrasado else "aberto",
                "status_registrado": None,
                "contrato_id": str(r["id"]),
                "contrato_numero": r["contract_number"],
                "contrato_nome": r["name"],
                "descricao": "Vencimento da vigência do contrato (automático).",
                "nivel_alerta": _nivel_alerta(dias),
                "created_at": None,
            }
        )
    return out


async def _prazos_de_certidoes(db: AsyncSession, hoje: date) -> list[dict[str, Any]]:
    """Validade de certidões (ged_certidoes.expiry_date) como prazos read-only."""
    rows = (
        await db.execute(
            text(
                """
                SELECT id, name, document_type, expiry_date
                FROM ged_certidoes
                WHERE expiry_date IS NOT NULL
                ORDER BY expiry_date ASC
                """
            )
        )
    ).mappings().all()
    out: list[dict[str, Any]] = []
    for r in rows:
        dl = r["expiry_date"]
        dias = _dias(dl, hoje)
        atrasado = dias is not None and dias < 0
        out.append(
            {
                "id": f"certidao:{r['id']}",
                "origem": "certidao",
                "editavel": False,
                "titulo": f"Validade — {r['name']}",
                "tipo": "validade_certidao",
                "data_limite": dl.isoformat() if dl else None,
                "dias_restantes": dias,
                "status": "atrasado" if atrasado else "aberto",
                "status_registrado": None,
                "contrato_id": None,
                "contrato_numero": None,
                "contrato_nome": None,
                "descricao": f"Certidão {r['document_type']} vence nesta data (automático).",
                "nivel_alerta": _nivel_alerta(dias),
                "created_at": None,
            }
        )
    return out


async def listar_prazos(
    db: AsyncSession,
    *,
    incluir_automaticos: bool = True,
    status: str | None = None,
) -> dict[str, Any]:
    """Lista prazos (gravados + automáticos) com status calculado.

    `status` opcional filtra pelo status CALCULADO (aberto|cumprido|atrasado).
    """
    hoje = date.today()
    itens = await _prazos_gravados(db, hoje)
    if incluir_automaticos:
        itens += await _prazos_de_contratos(db, hoje)
        itens += await _prazos_de_certidoes(db, hoje)

    # ordena por dias restantes (atrasados primeiro), None por último
    itens.sort(key=lambda p: (p["dias_restantes"] is None, p["dias_restantes"] if p["dias_restantes"] is not None else 0))

    if status:
        itens = [p for p in itens if p["status"] == status.lower()]

    resumo = {
        "abertos": sum(1 for p in itens if p["status"] == "aberto"),
        "atrasados": sum(1 for p in itens if p["status"] == "atrasado"),
        "cumpridos": sum(1 for p in itens if p["status"] == "cumprido"),
    }
    return {
        "referencia": hoje.isoformat(),
        "total": len(itens),
        "resumo": resumo,
        "prazos": itens,
    }


async def alertas_prazos(db: AsyncSession) -> dict[str, Any]:
    """Prazos vencendo em ≤7 / ≤15 / ≤30 dias + atrasados (gravados + automáticos)."""
    hoje = date.today()
    dados = await listar_prazos(db, incluir_automaticos=True)
    prazos = dados["prazos"]

    def _na_janela(j: int) -> list[dict[str, Any]]:
        return [
            p
            for p in prazos
            if p["status"] == "aberto"
            and p["dias_restantes"] is not None
            and 0 <= p["dias_restantes"] <= j
        ]

    atrasados = [p for p in prazos if p["status"] == "atrasado"]
    return {
        "referencia": hoje.isoformat(),
        "atrasados": {"total": len(atrasados), "itens": atrasados},
        "vencendo_7d": {"total": len(_na_janela(7)), "itens": _na_janela(7)},
        "vencendo_15d": {"total": len(_na_janela(15)), "itens": _na_janela(15)},
        "vencendo_30d": {"total": len(_na_janela(30)), "itens": _na_janela(30)},
    }


async def criar_prazo(
    db: AsyncSession,
    *,
    titulo: str,
    data_limite: date,
    tipo: str | None = None,
    status: str = "aberto",
    contrato_id: str | None = None,
    descricao: str | None = None,
) -> dict[str, Any]:
    """Cria um prazo em juridico_prazos e devolve o registro com status calculado."""
    st = (status or "aberto").lower()
    if st not in _STATUS_VALIDOS:
        st = "aberto"
    contrato_uuid: UUID | None = None
    if contrato_id:
        contrato_uuid = UUID(str(contrato_id))

    row = (
        await db.execute(
            text(
                """
                INSERT INTO juridico_prazos (titulo, tipo, data_limite, status, contrato_id, descricao)
                VALUES (:titulo, :tipo, :data_limite, :status, :contrato_id, :descricao)
                RETURNING id, titulo, tipo, data_limite, status, contrato_id, descricao, created_at
                """
            ),
            {
                "titulo": titulo,
                "tipo": tipo,
                "data_limite": data_limite,
                "status": st,
                "contrato_id": contrato_uuid,
                "descricao": descricao,
            },
        )
    ).mappings().one()
    await db.commit()

    hoje = date.today()
    dl = row["data_limite"]
    return {
        "id": str(row["id"]),
        "origem": "prazo",
        "editavel": True,
        "titulo": row["titulo"],
        "tipo": row["tipo"] or "geral",
        "data_limite": dl.isoformat() if dl else None,
        "dias_restantes": _dias(dl, hoje),
        "status": _status_calculado(row["status"], dl, hoje),
        "status_registrado": (row["status"] or "aberto").lower(),
        "contrato_id": str(row["contrato_id"]) if row["contrato_id"] else None,
        "descricao": row["descricao"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }
