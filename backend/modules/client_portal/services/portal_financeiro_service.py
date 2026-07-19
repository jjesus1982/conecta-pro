"""Portal do Cliente — Financeiro: NFS-e, contrato e histórico.

O condomínio vê suas notas fiscais de serviço (nfses), o contrato vigente e um resumo
financeiro. Escopo por CNPJ do tomador = ged_clients.cnpj.
"""

from __future__ import annotations

import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _digits(s: str | None) -> str:
    return re.sub(r"[^0-9]", "", s or "")


async def _cnpj_e_cliente(db: AsyncSession, client_id: str) -> tuple[str, str | None]:
    row = (
        await db.execute(
            text(
                """SELECT g.cnpj, c.id AS cliente_id
                   FROM ged_clients g
                   LEFT JOIN clients c ON regexp_replace(c.document_number,'[^0-9]','','g')
                                        = regexp_replace(COALESCE(g.cnpj,''),'[^0-9]','','g') AND g.cnpj IS NOT NULL
                   WHERE g.id = :cid"""
            ),
            {"cid": client_id},
        )
    ).mappings().first()
    if not row:
        return "", None
    return _digits(row["cnpj"]), (str(row["cliente_id"]) if row["cliente_id"] else None)


async def notas(db: AsyncSession, client_id: str) -> dict:
    """NFS-e emitidas para o condomínio (por CNPJ do tomador)."""
    cnpj, _ = await _cnpj_e_cliente(db, client_id)
    if not cnpj:
        return {"notas": [], "total": 0, "valor_total": 0.0}
    # [Veracidade] Fonte autoritativa = nfse_emitidas_nacional (77 notas jan-jun,
    # cStat 100). A tabela `nfses` so tem 27 notas jan-fev (R$542k) e exibia
    # historico fiscal INCOMPLETO ao cliente no portal (faltavam mar-jun).
    # `nfse_emitidas_nacional` nao tem link_nfse/status (todas autorizadas = cStat 100).
    rows = (
        await db.execute(
            text(
                """SELECT numero, data_emissao, competencia, valor_servicos, descricao,
                          tomador_nome
                   FROM nfse_emitidas_nacional
                   WHERE regexp_replace(COALESCE(tomador_cnpj,''),'[^0-9]','','g') = :cnpj
                   ORDER BY competencia DESC, data_emissao DESC"""
            ),
            {"cnpj": cnpj},
        )
    ).mappings().all()
    notas = [
        {
            "numero": r["numero"],
            "emissao": str(r["data_emissao"])[:10] if r["data_emissao"] else None,
            "competencia": r["competencia"],
            "valor": float(r["valor_servicos"] or 0),
            "status": "autorizada",
            "link": None,
            "descricao": (r["descricao"] or "")[:120],
        }
        for r in rows
    ]
    return {
        "notas": notas,
        "total": len(notas),
        "valor_total": round(sum(n["valor"] for n in notas), 2),
    }


async def contrato(db: AsyncSession, client_id: str) -> dict:
    """Contrato vigente do condomínio."""
    _, cliente_id = await _cnpj_e_cliente(db, client_id)
    if not cliente_id:
        return {"contrato": None}
    r = (
        await db.execute(
            text(
                """SELECT contract_number, status, monthly_value, total_value, signed_by_client,
                          renewal_period_months
                   FROM contracts WHERE client_id = :cid AND status = 'active'
                   ORDER BY monthly_value DESC LIMIT 1"""
            ),
            {"cid": cliente_id},
        )
    ).mappings().first()
    if not r:
        return {"contrato": None}
    return {
        "contrato": {
            "numero": r["contract_number"],
            "status": r["status"],
            "valor_mensal": float(r["monthly_value"] or 0),
            "valor_total": float(r["total_value"] or 0) if r["total_value"] else None,
            "assinado": bool(r["signed_by_client"]),
            "renovacao_meses": r["renewal_period_months"],
        }
    }


async def boletos(db: AsyncSession, client_id: str) -> dict:
    """Boletos/cobranças do condomínio — Multi-CNPJ E4: união dos DOIS bancos.

    Inter (Eletrônica, legado) + Cora (Patrimonial, via receivable_accounts com
    metadata.banco='cora'). O condomínio vê a fatura da empresa que o atende.
    """
    _, cliente_id = await _cnpj_e_cliente(db, client_id)
    out = []
    if cliente_id:
        try:
            rows = (
                await db.execute(
                    text(
                        """SELECT seu_numero, valor, vencimento, status FROM inter_cobrancas
                           WHERE cliente_id = :cid ORDER BY vencimento DESC LIMIT 24"""
                    ),
                    {"cid": cliente_id},
                )
            ).mappings().all()
            out = [
                {"numero": r["seu_numero"], "valor": float(r["valor"] or 0),
                 "vencimento": str(r["vencimento"]) if r["vencimento"] else None,
                 "status": r["status"], "banco": "Inter"}
                for r in rows
            ]
        except Exception:
            out = []
        try:
            rows_cora = (
                await db.execute(
                    text(
                        """SELECT ra.pix_txid AS numero, ra.gross_value AS valor,
                                  ra.due_date AS vencimento, ra.status,
                                  ra.metadata->>'boleto_digitavel' AS digitavel,
                                  ra.pix_copy_paste
                           FROM receivable_accounts ra
                           WHERE ra.metadata->>'client_id' = :cid
                             AND ra.metadata->>'banco' = 'cora'
                           ORDER BY ra.due_date DESC LIMIT 24"""
                    ),
                    {"cid": str(cliente_id)},
                )
            ).mappings().all()
            out += [
                {"numero": r["numero"], "valor": float(r["valor"] or 0),
                 "vencimento": str(r["vencimento"]) if r["vencimento"] else None,
                 "status": r["status"], "banco": "Cora",
                 "boleto_digitavel": r["digitavel"], "pix_copia_cola": r["pix_copy_paste"]}
                for r in rows_cora
            ]
        except Exception:  # noqa: BLE001
            pass
        out.sort(key=lambda b: b.get("vencimento") or "", reverse=True)
    return {"boletos": out[:24], "total": len(out[:24])}


async def resumo(db: AsyncSession, client_id: str) -> dict:
    n = await notas(db, client_id)
    c = await contrato(db, client_id)
    return {
        "notas_total": n["total"],
        "faturado_total": n["valor_total"],
        "contrato_mensal": (c["contrato"] or {}).get("valor_mensal", 0),
        "contrato_ativo": c["contrato"] is not None,
    }
