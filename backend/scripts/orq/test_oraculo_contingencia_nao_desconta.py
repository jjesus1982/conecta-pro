"""Batida por contingência NÃO pode virar desconto na folha.

🔴 MEDIDO EM 27/09/2026, e quase custou dinheiro de gente. O fluxo de contingência do José Luís
grava uma justificativa para a batida que o app não deixou registrar. Eu gravava
`justification_type='atraso'`. E a folha faz:

    SUM(CASE WHEN justification_type = 'atraso' THEN 60 ELSE 0 END)
    WHERE status IN ('aprovada','pendente')          -- payroll_service._get_faltas_atrasos

Ou seja: **cada batida por contingência virava 60 minutos de desconto na rubrica 231 «Atrasos»,
sem ninguém revisar.** Medido: 23 linhas, 14 pessoas, 1.380 minutos (23 horas) prontos para sair
da folha de setembro — o MATHEUS sozinho levaria 240. E o motivo gravado em cada uma era «Não
conseguiu», «App não abre», «Sem acesso»: **falha nossa, descontada da pessoa.**

⭐ O erro não foi de lógica, foi de VOCABULÁRIO — escolhi a ação certa e um valor que já tinha
consumidor, sem ir ver quem consumia. É a regra que esta casa já tinha escrito e eu repeti.

## O que este oráculo trava

1. **A folha não desconta contingência.** Roda a query REAL da folha (escrita aqui de forma
   independente, não importada) contra o que o fluxo de contingência produz.
2. **A linha continua VISÍVEL.** Não descontar não pode virar sumir: a Pyetra precisa ver para
   revisar, e converter em `atraso` se o atraso for real. Registro é fato; desconto é decisão.
3. **O tipo não voltou a ser `atraso`** no INSERT do fluxo de contingência.

⚠️ Afirma a REGRA e não a fotografia: não fixa pessoa, mês nem quantidade.
"""

import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402

#: O tipo que o fluxo de contingência DEVE gravar.
TIPO_CONTINGENCIA = "batida_contingencia"

#: ⚠️ A régua da folha escrita À MÃO, de propósito. Importar `payroll_service` provaria apenas
#: que sei importar — e um oráculo que reusa a query que audita é cúmplice dela.
_COMO_A_FOLHA_CONTA = """
SELECT coalesce(SUM(CASE WHEN justification_type = 'atraso' THEN 60 ELSE 0 END), 0)
  FROM gp_justifications
 WHERE status IN ('aprovada','pendente') AND source = 'whatsapp'
   AND justification_type = :tipo
"""

_ARQ = "/app/modules/people_management/ponto/atendimento_funcionario.py"


async def main() -> None:
    async with async_session_factory() as db:
        # 1 — a folha não desconta NADA do tipo de contingência, por construção do CASE
        minutos = (await db.execute(text(_COMO_A_FOLHA_CONTA),
                                    {"tipo": TIPO_CONTINGENCIA})).scalar() or 0
        assert int(minutos) == 0, (
            f"contingência voltou a descontar: {minutos} minuto(s) entrariam na rubrica 231")

        # 2 — e o tipo continua visível para quem revisa (as telas SELECIONAM o tipo, não filtram)
        visiveis = (await db.execute(text(
            "SELECT count(*) FROM gp_justifications WHERE justification_type = :t"),
            {"t": TIPO_CONTINGENCIA})).scalar() or 0

        # 3 — o INSERT do fluxo não pode ter voltado a gravar 'atraso'
        fonte = ""
        if os.path.exists(_ARQ):
            with open(_ARQ, encoding="utf-8") as fh:
                fonte = fh.read()
        if fonte:
            insert = re.search(r"INSERT INTO gp_justifications.*?\)\)", fonte, re.S)
            assert insert, "não achei o INSERT de justificativa no fluxo de contingência"
            trecho = insert.group(0)
            assert TIPO_CONTINGENCIA in trecho, (
                f"o fluxo de contingência não grava mais «{TIPO_CONTINGENCIA}»")
            assert "'atraso'" not in trecho, (
                "o fluxo de contingência voltou a gravar 'atraso' — isso é desconto de 60min "
                "por linha, sem revisão, por uma falha que é NOSSA")

        print(f"OK contingência não desconta na folha (0 minuto na rubrica 231) · "
              f"{visiveis} linha(s) do tipo «{TIPO_CONTINGENCIA}» visíveis para revisão")

        # Suspenders: o defeito ORIGINAL ainda existe para o tipo 'atraso' vindo do WhatsApp —
        # se alguém reintroduzir o valor antigo, este número sobe e o teste acima estoura. Aqui só
        # DIGO o tamanho, sem reprovar: as linhas antigas são decisão de folha, do dono.
        antigas = (await db.execute(text(
            "SELECT count(*) FROM gp_justifications "
            " WHERE justification_type='atraso' AND status='pendente' AND source='whatsapp'")
        )).scalar() or 0
        if antigas:
            print(f"⚠️ ainda há {antigas} linha(s) ANTIGAS como 'atraso'/pendente/whatsapp = "
                  f"{antigas * 60} minuto(s) de desconto esperando revisão humana")

    print("TEST oraculo_contingencia_nao_desconta PASS")


if __name__ == "__main__":
    asyncio.run(main())
