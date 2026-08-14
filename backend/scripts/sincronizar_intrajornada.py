#!/usr/bin/env python3
"""Sincroniza `employees.recebe_intrajornada` com o que o CONTRACHEQUE pagou.

A REGRA, dita pelo Jordan em 14/08/2026:

    recebe o adicional de intrajornada no contracheque  →  NÃO faz a pausa  →  2 batidas
    NÃO recebe o adicional                              →  almoça uma hora  →  4 batidas

Quem decide não é o cadastro nem o posto: é a FOLHA. O adicional de intrajornada é dinheiro
pago, registrado em `folha_verba_espelho` sob os códigos **0030** (Intrajornada Diurno) e
**0031** (Intrajornada Noturna). Se a empresa pagou, a pessoa não faz a pausa — e o ponto
dela tem 2 batidas, não 4.

POR QUE ISTO EXISTE. Até 13/08/2026 o número de batidas vinha de
`posts.tem_intervalo_almoco`, um flag de POSTO. O intervalo é de PESSOA: no mesmo Ideal
Flores há quem almoce e quem receba o adicional. Com os NOVE postos em `false`, o app
fechava o dia na 2ª batida e 36 pessoas de 12x36 não conseguiram registrar a volta do
almoço — com print e áudio de quem sofreu.

DIVERGÊNCIA MEDIDA em 14/08: 5 pessoas em que a folha PAGOU o adicional e o cadastro dizia
que não recebia. O sistema esperava 4 batidas delas quando deveria esperar 2.

🔴 ERRO MEU, EM 14/08, E A CORREÇÃO ESTÁ AQUI. A primeira versão consultava a folha
INTEIRA, sem competência. Com isso pegou lançamentos de meses antigos e marcou 5 pessoas
como "recebe hoje": MAIARA, BIANCA, FRANCISCO RAMON, ERIKA e PAULO. A planilha do Jordan
olhava JULHO e dizia "não recebe" em quatro delas — e as batidas observadas concordavam com
ele (BIANCA 3,4 · ERIKA 3,94 · FRANCISCO 4,0: essa gente almoça). Reverti as 5 para
`false`. **Adicional pago em março não diz nada sobre a jornada de agosto**; verba é fato
DA COMPETÊNCIA, e ler sem janela transforma histórico em estado atual.

⚠️ NÃO INVENTA NADA. Só marca `recebe_intrajornada = true` para quem tem verba 0030/0031 na
competência informada. Sem verba não há adicional; sem adicional, a pessoa almoça.

🔴 SEGUNDO FURO, ACHADO NA MESMA RODADA: quem NÃO TEM FOLHA no mês fica de fora. A CINTIA
apareceu como "folha não pagou → passa a 4 batidas", e ela tem ZERO verbas em 07/2026 e um
afastamento aberto desde 21/05 (acidente de trajeto). Ela não trabalhou — a ausência do
adicional não diz nada sobre a jornada dela. "Fora da janela de cobertura, ausência não é
prova", e a janela aqui é ter folha no mês.

⚠️ E NÃO RODE SOZINHO CONTRA A DECISÃO DO DP. Onde existe planilha conferida pelo Jordan,
ela vence: ela cruza cadastro, folha da competência certa E batidas observadas — três
fontes, não uma. Este script serve para ACHAR divergência e levar a ele, não para decidir.

🔴 CASO VIVO, 14/08/2026 — A MAIARA. Ela mudou do Ideal Flores para o Villa Dei Fiori em
09/08, em definitivo, e o Jordan decidiu que ela PASSA A RECEBER o adicional: no Dei Fiori
todos os agentes de portaria recebem. O cadastro dela está em `true` e ela bate 2 vezes.

    Se você rodar este script hoje, ele vai querer voltá-la para `false` — e vai estar
    "certo" pela regra que ele conhece: a folha de 07/2026 dela é do Ideal Flores, onde
    ninguém recebe, e não tem verba 0030/0031. A DECISÃO É MAIS NOVA QUE A COMPETÊNCIA.

Ela já recebeu o adicional de fevereiro a maio/2026 e parou em junho; agora volta a receber.
Então nem "nunca recebeu" serve de pista aqui. Antes de aplicar, confira a lista de alvos
contra transferências recentes de posto — mudança de posto muda a regra ANTES de a folha
mostrar, e este script só enxerga a folha.

E o inverso também vale: a partir da competência em que o adicional for pago a ela, o script
volta a concordar sozinho. O buraco é só a janela entre a decisão e o pagamento.

Ensaio é o padrão. Aplicar: --aplicar. Acima do teto de 10: --forcar.

    docker exec -e PYTHONPATH=/app conecta-pro-backend \\
      python3 /app/scripts/sincronizar_intrajornada.py
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/scripts/qa")

from _mutacao import Mutacao  # noqa: E402
from sqlalchemy import text  # noqa: E402

from core.database.session import async_session_factory  # noqa: E402

#: Os códigos do adicional na folha. Se aparecer um terceiro, ele entra AQUI — e não numa
#: condição espalhada por aí. `LIKE '%INTRA%'` não serve: pegaria rubrica de rescisão.
VERBAS_INTRAJORNADA = ("0030", "0031")

#: Competência de referência. A verba é fato DO MÊS: adicional pago em março não diz nada
#: sobre a jornada de agosto. Sem esta janela o script confunde histórico com estado atual —
#: foi exatamente o que ele fez na primeira versão. A tabela guarda `ano`/`mes` separados,
#: não uma coluna `competencia`; conferido antes de escrever a query.
COMP_ANO, COMP_MES = 2026, 7

SQL_DIVERGENTES = text(
    "WITH folha AS ("
    "  SELECT DISTINCT employee_id FROM folha_verba_espelho "
    "  WHERE codigo = ANY(:codigos) AND ano = :ano AND mes = :mes) "
    "SELECT e.id::text AS id, e.nome AS nome, e.cargo AS cargo, "
    "       (f.employee_id IS NOT NULL) AS folha_pagou, "
    "       coalesce(e.recebe_intrajornada, false) AS cadastro "
    "FROM employees e LEFT JOIN folha f ON f.employee_id = e.id "
    "WHERE lower(coalesce(e.status,'')) = 'ativo' "
    "  AND upper(coalesce(e.nome,'')) NOT LIKE '%TESTE%' "
    "  AND upper(coalesce(e.nome,'')) NOT LIKE '%HOMOLOGA%' "
    "  AND (f.employee_id IS NOT NULL) IS DISTINCT FROM coalesce(e.recebe_intrajornada, false) "
    # quem não tem NENHUMA verba na competência não trabalhou (afastado, férias, admissão
    # posterior). A ausência do adicional aí não é sinal — é falta de amostra.
    "  AND EXISTS (SELECT 1 FROM folha_verba_espelho fx "
    "              WHERE fx.employee_id = e.id AND fx.ano = :ano AND fx.mes = :mes) "
    "ORDER BY e.nome"
)


async def main() -> int:
    m = Mutacao("sincronizar recebe_intrajornada com a folha", teto=10)

    async with async_session_factory() as db:
        linhas = (await db.execute(
            SQL_DIVERGENTES,
            {"codigos": list(VERBAS_INTRAJORNADA), "ano": COMP_ANO, "mes": COMP_MES},
        )).mappings().all()

        alvos = [
            (r["id"][:8],
             f"{r['nome']} ({r['cargo']}) — folha "
             f"{'PAGOU' if r['folha_pagou'] else 'não pagou'} · cadastro dizia "
             f"{'recebe' if r['cadastro'] else 'não recebe'} → passa a "
             f"{'2 batidas' if r['folha_pagou'] else '4 batidas'}")
            for r in linhas
        ]
        print(f"\n══ intrajornada: cadastro × contracheque de {COMP_MES:02d}/{COMP_ANO} — "
              f"{len(linhas)} divergência(s) ══")
        print("   (a planilha conferida pelo Jordan VENCE este script — ele acha, ela decide)")

        if not m.confirmar(alvos):
            return 0

        n = (await db.execute(text(
            "UPDATE employees e SET recebe_intrajornada = EXISTS ("
            "  SELECT 1 FROM folha_verba_espelho f "
            "  WHERE f.employee_id = e.id AND f.codigo = ANY(:codigos) "
            "    AND f.ano = :ano AND f.mes = :mes), updated_at = now() "
            "WHERE lower(coalesce(e.status,'')) = 'ativo' "
            "  AND upper(coalesce(e.nome,'')) NOT LIKE '%TESTE%' "
            "  AND upper(coalesce(e.nome,'')) NOT LIKE '%HOMOLOGA%' "
            "  AND EXISTS (SELECT 1 FROM folha_verba_espelho f2 "
            "              WHERE f2.employee_id = e.id AND f2.codigo = ANY(:codigos) "
            "                AND f2.ano = :ano AND f2.mes = :mes) "
            "      IS DISTINCT FROM coalesce(e.recebe_intrajornada, false) "
            "  AND EXISTS (SELECT 1 FROM folha_verba_espelho fx "
            "              WHERE fx.employee_id = e.id AND fx.ano = :ano AND fx.mes = :mes)"
        ), {"codigos": list(VERBAS_INTRAJORNADA), "ano": COMP_ANO, "mes": COMP_MES})).rowcount
        await db.commit()
        m.feito(n)

        conf = (await db.execute(text(
            "SELECT count(*) FILTER (WHERE coalesce(recebe_intrajornada,false)) AS de_2, "
            "       count(*) FILTER (WHERE NOT coalesce(recebe_intrajornada,false)) AS de_4, "
            "       count(*) AS total FROM employees "
            "WHERE lower(coalesce(status,'')) = 'ativo' "
            "  AND upper(coalesce(nome,'')) NOT LIKE '%TESTE%' "
            "  AND upper(coalesce(nome,'')) NOT LIKE '%HOMOLOGA%'"
        ))).first()
        print(f"  DEPOIS: {conf[0]} pessoa(s) com 2 batidas (recebem o adicional) · "
              f"{conf[1]} com 4 · {conf[2]} no total")
        restam = (await db.execute(
            SQL_DIVERGENTES,
            {"codigos": list(VERBAS_INTRAJORNADA), "ano": COMP_ANO, "mes": COMP_MES},
        )).rowcount
        print(f"  divergências restantes: {restam}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
