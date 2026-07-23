"""CAIXA POR CNPJ — a camada executiva/CFO CIENTE DE CNPJ (🟢 READ).

O Grupo opera com DUAS contas: Banco **Inter** (Conecta Eletrônica, CNPJ1) e Banco
**Cora** (Conecta Patrimonial, CNPJ2). Antes, o executivo lia SÓ o Inter e misturava a
folha total — decisões de mão de obra (que é Patrimonial/Cora) liam a conta errada.

`caixa_por_cnpj(db)` devolve, POR CNPJ e com PROVENIÊNCIA de cada número:
- **saldo** — Inter via `cfo_service._saldo_inter_vivo()` (Redis→adapter, fallback cadastro);
  Cora lido de `bank_accounts` (coluna mantida fresca pelo cora_sync_service — NÃO chamamos a
  API Cora no caminho da request).
- **folha** — pelo COLABORADOR ATIVO (a régua da transição), última competência de holerite,
  agrupada por `employees.empresa_id` (NÃO por `hr_payslips.empresa_id`, que reflete onde foi
  PAGO no passado).

DOUTRINA: nunca fabricar dado. Saldo/folha ausente → None + fonte "aguardando dado".
As colunas `empresa_id` existem no DB mas NÃO nos models `bank_account.py`/`payslip.py`
(drift conhecido) → aqui é SQL cru via `text()`, sem tocar no ORM.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.empresas.services.classificador_cargo import META_EMPRESA

logger = logging.getLogger(__name__)


def _src(valor: Any, source: str) -> dict[str, Any]:
    """Embrulha um número com sua PROVENIÊNCIA — mesmo contrato de dado dos quick-wins."""
    return {"valor": valor, "source": source}


async def _saldo_inter(db: AsyncSession) -> tuple[float | None, str, str | None]:
    """Saldo da Eletrônica = Banco Inter. Vivo (Redis→adapter); fallback cadastro
    (bank_accounts bank_code 077). Retorna (saldo, fonte, as_of_iso|None)."""
    from modules.financial import cfo_service

    vivo = await cfo_service._saldo_inter_vivo()  # noqa: SLF001 — reuso do choke point existente
    if vivo is not None:
        return float(vivo), "Banco Inter (ao vivo)", None
    # Fallback: cadastro (a coluna current_balance é sincronizada). None se não houver linha.
    row = (
        await db.execute(
            text(
                "SELECT current_balance, last_balance_update FROM bank_accounts "
                "WHERE bank_code = '077' AND ativo IS NOT FALSE LIMIT 1"
            )
        )
    ).first()
    if row and row[0] is not None:
        as_of = row[1].isoformat() if row[1] is not None else None
        return float(row[0]), "Banco Inter (cadastro — vivo indisponível)", as_of
    return None, "aguardando dado (Inter sem saldo cadastrado)", None


async def _saldo_cora(db: AsyncSession) -> tuple[float | None, str, str | None]:
    """Saldo da Patrimonial = Banco Cora. Lido de bank_accounts (coluna mantida fresca
    pelo cora_sync_service; NÃO chamamos a API Cora aqui — mTLS pesado no caminho da
    request). Retorna (saldo, fonte, as_of_iso|None). Ausente/NULL → None + aguardando."""
    row = (
        await db.execute(
            text(
                "SELECT current_balance, last_balance_update FROM bank_accounts "
                "WHERE bank_code = '403' AND ativo IS NOT FALSE LIMIT 1"
            )
        )
    ).first()
    if row and row[0] is not None:
        as_of = row[1].isoformat() if row[1] is not None else None
        return float(row[0]), "Banco Cora (sync)", as_of
    return None, "aguardando dado (Cora sem saldo sincronizado)", None


async def _folha_por_empresa(db: AsyncSession) -> dict[str, dict[str, Any]]:
    """Folha (SUM total_earnings) e nº de ativos POR empresa, pelo COLABORADOR ativo,
    na última competência de holerite. Chave = slug. Vazio se não houver holerites."""
    out: dict[str, dict[str, Any]] = {}
    try:
        rows = (
            await db.execute(
                text(
                    "SELECT e.slug, COALESCE(SUM(hp.total_earnings),0) AS folha, "
                    "COUNT(DISTINCT hp.employee_id) AS n "
                    "FROM hr_payslips hp "
                    "JOIN employees em ON em.id = hp.employee_id "
                    "JOIN empresas e ON e.id = em.empresa_id "
                    "WHERE em.is_active IS TRUE "
                    "  AND (hp.reference_year, hp.reference_month) = ("
                    "       SELECT reference_year, reference_month FROM hr_payslips "
                    "       ORDER BY reference_year DESC, reference_month DESC LIMIT 1) "
                    "GROUP BY e.slug"
                )
            )
        ).mappings().all()
        for r in rows:
            out[r["slug"]] = {"folha": float(r["folha"] or 0.0), "n": int(r["n"] or 0)}
    except Exception as e:  # noqa: BLE001 — folha é complementar; nunca derruba o caixa
        logger.warning("caixa_por_cnpj: folha por empresa indisponível: %s", e)
    return out


async def caixa_por_cnpj(db: AsyncSession) -> dict[str, Any]:
    """Fotografia de CAIXA + FOLHA por CNPJ, com proveniência. 🟢 READ.

    Retorna {'eletronica': {...}, 'patrimonial': {...}, 'consolidado': {...}}.
    Cada bloco: empresa_id, slug, nome, banco, saldo, saldo_fonte, as_of, folha,
    folha_fonte, funcionarios_ativos. Ausências vêm None + fonte 'aguardando dado'.
    """
    saldo_e, fonte_e, as_of_e = await _saldo_inter(db)
    saldo_p, fonte_p, as_of_p = await _saldo_cora(db)
    folhas = await _folha_por_empresa(db)

    def _bloco(natureza: str, saldo: float | None, saldo_fonte: str, as_of: str | None) -> dict[str, Any]:
        meta = META_EMPRESA[natureza]
        f = folhas.get(meta["slug"])
        if f is not None:
            folha_val: float | None = f["folha"]
            n_ativos: int | None = f["n"]
            folha_fonte = (
                "hr_payslips × employees ativos (última competência, por employees.empresa_id)"
            )
        else:
            folha_val, n_ativos = None, None
            folha_fonte = "aguardando dado (sem holerite de colaborador ativo nesta empresa)"
        return {
            "empresa_id": meta["empresa_id"],
            "slug": meta["slug"],
            "nome": meta["nome"],
            "banco": meta["banco"],
            "saldo": saldo,
            "saldo_fonte": saldo_fonte,
            "as_of": as_of,
            "folha": folha_val,
            "folha_fonte": folha_fonte,
            "funcionarios_ativos": n_ativos,
        }

    eletronica = _bloco("eletronica", saldo_e, fonte_e, as_of_e)
    patrimonial = _bloco("patrimonial", saldo_p, fonte_p, as_of_p)

    saldos = [b["saldo"] for b in (eletronica, patrimonial) if b["saldo"] is not None]
    folhas_v = [b["folha"] for b in (eletronica, patrimonial) if b["folha"] is not None]
    consolidado = {
        "saldo_total": _src(
            round(sum(saldos), 2) if saldos else None,
            "soma dos saldos disponíveis (Inter + Cora)"
            if saldos else "aguardando dado (nenhum saldo disponível)",
        ),
        "folha_total": _src(
            round(sum(folhas_v), 2) if folhas_v else None,
            "soma da folha por CNPJ (colaboradores ativos, última competência)"
            if folhas_v else "aguardando dado (nenhuma folha apurável)",
        ),
    }
    return {"eletronica": eletronica, "patrimonial": patrimonial, "consolidado": consolidado}


# ─────────────────────────────────────────────────────────────────────────────
# TESTE-ÂNCORA standalone (sem pytest) — requer DATABASE_URL real (bancada, NUNCA
# in-process em :8080). `DATABASE_URL_TESTE=... python caixa_service.py`.
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import asyncio
    import json
    import os

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    async def main() -> None:
        engine = create_async_engine(os.environ["DATABASE_URL_TESTE"])
        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session() as db:
            caixa = await caixa_por_cnpj(db)
            print(json.dumps(caixa, ensure_ascii=False, indent=2, default=str))
            assert caixa["eletronica"]["banco"] == "Inter"
            assert caixa["patrimonial"]["banco"] == "Cora"
        await engine.dispose()

    asyncio.run(main())
