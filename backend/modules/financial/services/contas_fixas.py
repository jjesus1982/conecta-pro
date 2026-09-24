"""Contas fixas → título do mês (DGX F11, 24/09/2026).

`financial_custos_recorrentes` já existia (3 linhas de teste, todas inativas) e só era PROJEÇÃO:
entrava no fluxo de caixa do CFO e nunca virava conta a pagar. O DGX chama isso de «Conta Fixa»
e a diferença que importa é uma: a recorrência GERA o título ("Gerado Até" na grade dele).

Aqui: `gerar_titulos_do_mes(db, 'AAAA-MM', user_id)` cria UMA conta a pagar por custo ativo por
competência, pelo mesmo `PayableService.create_account` da tela «Registrar conta» (não é INSERT
cru em `payable_accounts`). A idempotência é o vínculo `fin_contas_fixas_geradas(custo_id,
competencia)` com chave primária — rodar duas vezes não duplica, e o oráculo
`test_oraculo_financeiro_cadastros.py` (bloco c) prova isso.

Não paga nada: só registra o título. O pagamento continua no fluxo com OTP.
"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

#: mesmo tenant "empresa" que TODAS as contas registradas pelo redesign usam
COND_EMPRESA = UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

_SQL_ATIVOS = """
SELECT c.id, coalesce(c.categoria,'fixo'), coalesce(c.descricao,'—'), c.valor, coalesce(c.dia_vencimento, 10),
       c.favorecido, c.parcelas_total, coalesce(c.parcelas_pagas, 0),
       (SELECT count(*) FROM fin_contas_fixas_geradas g WHERE g.custo_id = c.id) AS geradas
  FROM financial_custos_recorrentes c
 WHERE coalesce(c.ativo, true) AND c.encerrado_em IS NULL AND coalesce(c.valor, 0) > 0
 ORDER BY c.id
"""


def vencimento_na_competencia(competencia: str, dia: int) -> date:
    """'2026-02' + dia 31 → 28/02/2026 (o dia é cortado no último dia do mês)."""
    ano, mes = int(competencia[:4]), int(competencia[5:7])
    return date(ano, mes, min(int(dia or 10), calendar.monthrange(ano, mes)[1]))


async def gerar_titulos_do_mes(db: AsyncSession, competencia: str, user_id) -> dict:
    """Um título por conta fixa ativa na competência. Idempotente. Devolve {criados, pulados, itens}."""
    from modules.financial.schemas.payable import PayableAccountCreate
    from modules.financial.services.payable_service import PayableService

    if not (len(competencia) == 7 and competencia[4] == "-"):
        raise ValueError("Competência deve ser AAAA-MM.")
    svc = PayableService(db)
    criados, pulados, itens = 0, 0, []
    for cid, cat, desc, valor, dia, favorecido, p_total, p_pagas, geradas in (
        await db.execute(text(_SQL_ATIVOS))
    ).fetchall():
        if p_total and (int(p_pagas) + int(geradas)) >= int(p_total):
            pulados += 1  # parcelamento já completo
            continue
        ja = (
            await db.execute(
                text("SELECT 1 FROM fin_contas_fixas_geradas WHERE custo_id=:c AND competencia=:m"),
                {"c": cid, "m": competencia},
            )
        ).first()
        if ja:
            pulados += 1
            continue
        venc = vencimento_na_competencia(competencia, dia)
        conta = await svc.create_account(
            PayableAccountCreate(
                condominio_id=COND_EMPRESA,
                description=f"{desc} — {competencia[5:7]}/{competencia[:4]}",
                gross_value=Decimal(str(valor)),
                due_date=venc,
                competence_date=date(int(competencia[:4]), int(competencia[5:7]), 1),
                supplier_name=(favorecido or "").strip() or None,
                is_recurring=True,
                notes=f"Conta fixa #{cid} ({cat}) — gerada pela tela «Contas fixas»",
            ),
            user_id,
        )
        await db.execute(
            text(
                "INSERT INTO fin_contas_fixas_geradas (custo_id, competencia, payable_id) VALUES (:c, :m, :p) "
                "ON CONFLICT (custo_id, competencia) DO NOTHING"
            ),
            {"c": cid, "m": competencia, "p": str(conta.id)},
        )
        criados += 1
        itens.append(
            {"custo_id": cid, "descricao": desc, "valor": float(valor), "vencimento": venc.strftime("%d/%m/%Y")}
        )
    await db.commit()
    return {"competencia": competencia, "criados": criados, "pulados": pulados, "itens": itens}
