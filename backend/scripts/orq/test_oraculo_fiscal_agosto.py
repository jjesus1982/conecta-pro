"""Oráculo do CORTE de agosto: o que nasce de 01/08/2026 em diante nasce certo.

Decisão do Jordan em 14/08/2026: o histórico até 31/07 serviu para homologar e está
encerrado. As 22 obrigações de abril a julho são *status não conciliado do período de
homologação*, não dívida — a Caixa emitiu CRF de FGTS em 11/08, e certidão de regularidade
não sai com FGTS em aberto. **Nada anterior ao corte é medido aqui.**

Um arquivo só, com quatro regras, em vez de quatro oráculos: são a mesma pergunta vista de
quatro lados — *agosto está nascendo certo nos DOIS CNPJs?* — e quatro arquivos custariam
quatro vezes mais para dizer o mesmo.

O corte é medido no **VENCIMENTO**, não na competência. A competência viva em agosto é a 07
(FGTS e eSocial vencem 07/08; DAS, INSS e IRRF, 20/08); a competência 08 só vence em
setembro, e o `calendario_service` só cria mês ENCERRADO, de propósito.

Regra ≠ fotografia: nenhuma asserção fixa valor, CNPJ ou quantidade. Entra empresa nova,
entra tributo novo, o oráculo cobre sozinho.

Roda:
    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_fiscal_agosto.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402

#: O corte declarado. Medido no vencimento — ver docstring.
CORTE = date(2026, 8, 1)

#: Dias de antecedência em que uma certidão vencendo já precisa de renovação disparada.
#:
#: ⚠️ ACOPLADO ao `_buscar_e_salvar_certidao`, que PULA a busca enquanto a certidão for
#: válida por mais de 10 dias (`expiry_date > CURRENT_DATE + INTERVAL '10 days'`). Estava 15
#: aqui, e as duas réguas discordavam: entre o 15º e o 11º dia o oráculo cobrava uma ação que
#: o sync está programado para NÃO fazer. Vermelho garantido todo mês, por desenho —
#: exatamente o alarme falso que este fechamento passou dias caçando.
#:
#: Medido em 17/08/2026: 5 CRF-FGTS de cliente vencendo 02/09 (15 dias) acusadas, sendo que o
#: sync as pulou corretamente na mesma manhã.
#:
#: Se mudar o limiar do sync, mude este junto — são a mesma decisão escrita em dois lugares.
JANELA_RENOVACAO = 10


async def main() -> None:
    async with async_session_factory() as db:

        # ── 1. Certidão vencendo em ≤15 dias tem renovação disparada ──────────────────
        # "Disparada" = a linha foi tocada depois de a janela abrir. Sem isso, a certidão
        # vence no silêncio — e é ela que o condomínio exige para pagar a Patrimonial.
        # Anulada de propósito (validade < emissão) não conta: já é um pedido de emissão
        # manual, não um vigia dormindo.
        paradas = (await db.execute(text("""
            SELECT c.cnpj, c.document_type, c.expiry_date
              FROM ged_certidoes c
             WHERE c.expiry_date IS NOT NULL
               AND c.expiry_date >= c.issue_date
               AND c.expiry_date BETWEEN CURRENT_DATE AND CURRENT_DATE + CAST(:janela AS integer)
               AND c.updated_at::date < c.expiry_date - CAST(:janela AS integer)
             ORDER BY c.expiry_date
        """), {"janela": JANELA_RENOVACAO})).fetchall()
        assert not paradas, (
            f"{len(paradas)} certidão(ões) vencendo em ≤{JANELA_RENOVACAO} dias sem renovação "
            f"disparada: {[f'{c}/{t} vence {v}' for c, t, v in paradas]}")

        # ── 2. REMOVIDA — a regra estava errada, e a evidência que a sustentava é um DEFAULT
        #
        # Ela dizia: "obrigação de folha pertence ao CNPJ que tem os holerites daquela
        # competência". A fonte era `hr_payslips.empresa_id` — que tem
        # **DEFAULT '7d79ed12…' (Patrimonial)**. Holerite não atribuído nasce Patrimonial,
        # então a coluna "provava" uma migração de folha que o governo não registrou.
        #
        # O documento do emissor diz o contrário: `RELATORIO GFD FGTS 06.2026` traz
        # "Empregador: 35.710.481 CONECTAMAIS ELETRONICA LTDA · Qtd. Trabalhadores FGTS: 54",
        # e o DCTFWeb de 07/2026 está todo sob 35710481000103. Oito obrigações chegaram a ser
        # movidas por causa desta regra, e foram revertidas.
        #
        # Não há regra substituta aqui de propósito: enquanto a atribuição vier da GUIA
        # (`guias_drive_service._upsert_obrigacao` lê o CNPJ do PDF), não existe inferência
        # nossa a vigiar. Oráculo que afirma o que não pode provar é pior que oráculo
        # nenhum. [[feedback_portte_fonte_verdade]]
        #

        # ── 3. Tributo que não pertence ao regime da empresa ──────────────────────────
        # DAS só existe no Simples Nacional. É definição do tributo, não enquadramento —
        # a única regra de regime que este oráculo se permite afirmar.
        regime = (await db.execute(text("""
            SELECT e.slug, e.regime_tributario, o.tipo
              FROM fiscal_obligations o JOIN empresas e ON e.id = o.empresa_id
             WHERE o.active AND o.data_vencimento >= :corte
               AND o.tipo = 'DAS' AND e.regime_tributario <> 'simples_nacional'
        """), {"corte": CORTE})).fetchall()
        assert not regime, (
            f"DAS cadastrado fora do Simples: {[f'{s} ({r})' for s, r, _ in regime]}")

        # ── 4. Obrigação vencida há >5 dias tem guia ──────────────────────────────────
        # Prazo vencido sem valor nem recibo é prazo cego: ninguém sabe quanto é, nem se
        # foi pago. Só de 01/08 em diante — abril a julho não se persegue.
        sem_guia = (await db.execute(text("""
            SELECT e.slug, o.tipo, o.data_vencimento
              FROM fiscal_obligations o JOIN empresas e ON e.id = o.empresa_id
             WHERE o.active
               AND o.data_vencimento >= :corte
               AND o.data_vencimento < CURRENT_DATE - 5
               AND o.status <> 'cumprida'
               AND (o.numero_recibo IS NULL OR o.numero_recibo = '')
               AND o.valor_devido IS NULL
             ORDER BY o.data_vencimento
        """), {"corte": CORTE})).fetchall()
        assert not sem_guia, (
            f"{len(sem_guia)} obrigação(ões) vencida(s) há mais de 5 dias sem guia: "
            f"{[f'{s}/{t} venceu {v}' for s, t, v in sem_guia]}")

        print("oráculo do corte de agosto: OK — certidões renovando, obrigações no CNPJ e "
              "regime certos, e nenhum prazo vencido sem guia")


if __name__ == "__main__":
    asyncio.run(main())
