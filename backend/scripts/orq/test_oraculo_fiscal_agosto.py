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

#: Obrigações que nascem da FOLHA: pertencem a quem tem os holerites da competência, não a
#: quem tem o histórico. A folha migrou de CNPJ em 06/2026 e o calendário não percebeu.
TIPOS_DE_FOLHA = ("FGTS", "INSS", "IRRF", "ESOCIAL", "FGTS_CONSIGNADO")

#: Dias de antecedência em que uma certidão vencendo já precisa de renovação disparada.
JANELA_RENOVACAO = 15


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

        # ── 2. Obrigação de folha mora num CNPJ que EMPREGA ───────────────────────────
        # A primeira versão desta regra dizia "pertence a quem tem a MAIORIA dos holerites",
        # e a realidade a desmentiu no mesmo dia: a folha está REPARTIDA. A guia
        # `GFD FGTS 07.2026`, emitida pela Portte em 11/08, mostra a Eletrônica com **uma**
        # trabalhadora (categoria 101, base R$1.670 = piso da CCT, FGTS R$133,60), enquanto
        # a Patrimonial carrega 51 holerites. Pela regra antiga, o FGTS legítimo da
        # Eletrônica — com guia do governo na mão — virava achado.
        #
        # Ordem de evidência, e ela é o ponto: **documento do emissor ganha da nossa
        # inferência**. `valor_devido` preenchido quer dizer que alguém lastreou aquilo num
        # papel, e `hr_payslips` não sabe de tudo (a trabalhadora da Eletrônica não aparece
        # lá). Então só se acusa o CNPJ sem folha quando TAMBÉM não há valor sustentando —
        # aí não existe nem papel nem gente.
        fora = (await db.execute(text("""
            SELECT e.slug, o.tipo, o.competencia_mes, o.competencia_ano, dono.slug
              FROM fiscal_obligations o
              JOIN empresas e ON e.id = o.empresa_id
              JOIN LATERAL (
                    SELECT e2.slug
                      FROM hr_payslips p JOIN empresas e2 ON e2.id = p.empresa_id
                     WHERE extract(year  from p.competence_start) = o.competencia_ano
                       AND extract(month from p.competence_start) = o.competencia_mes
                     GROUP BY e2.slug ORDER BY count(*) DESC LIMIT 1
                   ) dono ON true
             WHERE o.active
               AND o.data_vencimento >= :corte
               AND o.tipo = ANY(:folha)
               AND dono.slug <> e.slug
               AND o.valor_devido IS NULL
               AND NOT EXISTS (SELECT 1 FROM hr_payslips p2
                                WHERE p2.empresa_id = o.empresa_id
                                  AND extract(year  from p2.competence_start) = o.competencia_ano
                                  AND extract(month from p2.competence_start) = o.competencia_mes)
        """), {"corte": CORTE, "folha": list(TIPOS_DE_FOLHA)})).fetchall()
        assert not fora, (
            f"{len(fora)} obrigação(ões) de folha no CNPJ errado: "
            f"{[f'{s}/{t} de {m:02d}/{a} — a folha é da {d}' for s, t, m, a, d in fora]}")

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
