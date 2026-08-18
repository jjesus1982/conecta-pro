"""O gerador de VA/VT enxerga o pagamento em QUALQUER banco, não só no Inter.

Em 14/08/2026 o VA/VT saiu pelo Cora — Sólides R$ 28.266 (8 pagamentos) e Sinetran
R$ 3.490 (6). O montador só falava com a API do Inter, então o bloco `vavt` devolveu
`gerados: 0` com o dinheiro pago e o comprovante faltando nos 7 kits.

A asserção é a REGRA, não a fotografia: conta os pagamentos de VA/VT por SQL próprio
(independente do filtro do gerador) e exige que o gerador ache o mesmo tanto. Se amanhã
o pagamento voltar pro Inter, migrar pro BTG ou dobrar de volume, o oráculo acompanha.
"""

import asyncio
import os
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from core.database.session import get_sync_db  # noqa: E402
from modules.gedeon.services.inter_kit_service import _mes_pagamento  # noqa: E402
from modules.gedeon.services.kit_orchestrator import _extrato_outros_bancos  # noqa: E402

# Fornecedores de VA/VT. Mesma lista do gerador, mas o CASAMENTO é feito aqui por SQL
# próprio — o oráculo não reusa o filtro que audita.
SQL_VAVT = text(
    "SELECT count(*) FROM bank_transactions bt JOIN bank_accounts ba ON ba.id = bt.bank_account_id "
    " WHERE bt.transaction_date BETWEEN :ini AND :fim AND bt.amount < 0 "
    "   AND ba.bank_name NOT ILIKE '%Inter%' "
    "   AND upper(coalesce(bt.counterparty_name,'') || ' ' || coalesce(bt.description,'')) "
    "       ~ 'SOLIDES|SINETRAN|SIND DAS EMP'"
)


def _competencia_com_vavt() -> str | None:
    """Acha uma competência cuja janela de pagamento tenha VA/VT fora do Inter.
    Sem UUID nem mês chumbado: o oráculo procura o caso, não o decora."""
    from datetime import date

    hoje = date.today()
    for recuo in range(0, 6):
        m, a = hoje.month - recuo, hoje.year
        while m < 1:
            m, a = m + 12, a - 1
        comp = f"{m:02d}.{a}"
        ini, fim = _mes_pagamento(comp)
        with get_sync_db() as db:
            n = db.execute(SQL_VAVT, {"ini": date.fromisoformat(ini), "fim": date.fromisoformat(fim)}).scalar()
        if n:
            return comp
    return None


async def main() -> None:
    comp = _competencia_com_vavt()
    if not comp:
        print("SKIP nenhuma competência recente com VA/VT fora do Inter — nada a provar")
        print("TEST oraculo_vavt_multibanco PASS")
        return

    from datetime import date

    ini, fim = _mes_pagamento(comp)
    with get_sync_db() as db:
        esperado = db.execute(SQL_VAVT, {"ini": date.fromisoformat(ini), "fim": date.fromisoformat(fim)}).scalar()

    txs = _extrato_outros_bancos(get_sync_db, comp)
    assert txs, f"extrato de outros bancos veio vazio na janela {ini}..{fim} de {comp}"

    from modules.gedeon.services.inter_comprovantes_gerais import gerar_comprovantes_va_vt

    rel = gerar_comprovantes_va_vt(comp, txs, emitido_em=fim, dry_run=True)
    achado = rel["gerados"]

    # A trava principal: o gerador não pode perder pagamento que o banco tem.
    assert achado >= esperado, (
        f"competência {comp}: o banco tem {esperado} pagamentos de VA/VT fora do Inter "
        f"e o gerador achou {achado} — comprovante sumiria do kit"
    )
    # Suspenders: o defeito original era exatamente zero. Que não volte.
    assert achado > 0, "gerador voltou a devolver 0 com VA/VT pago (defeito de 14/08/2026)"

    print(f"OK {comp}: banco tem {esperado} pagamentos de VA/VT fora do Inter, gerador achou {achado}")
    print(f"OK extrato de outros bancos na janela {ini}..{fim}: {len(txs)} transações")
    print("TEST oraculo_vavt_multibanco PASS")


if __name__ == "__main__":
    asyncio.run(main())
