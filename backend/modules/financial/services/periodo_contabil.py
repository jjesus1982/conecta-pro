"""Corte contábil: a partir de quando o razão é a verdade.

Decisão do Jordan em 2026-08-11: **de agosto/2026 em diante** a empresa opera
dentro do Conecta PRO. Janeiro a julho foram vividos fora dele — o dado veio de
CSV e da Portte, e reconciliar aquilo é arqueologia cara e de baixo retorno.

Fechar o período NÃO é parar de olhar. Sem trava, os lançamentos antigos
continuam no razão e qualquer relatório acumulado mistura o período arqueológico
com o real — daqui a três meses alguém abre um DRE do ano e recebe um número
contaminado sem perceber. "Fechar" é isto aqui: nada novo entra antes do corte,
e o que for barrado é CONTADO, não engolido.

Saldo de abertura em 01/08/2026, provado por dois caminhos independentes:
  • Banco Inter  R$    725,47 — o próprio Inter (GET /banking/v2/saldo?dataSaldo=
    2026-07-31) e a nossa corrente (abertura 01/01 R$7.625,62 + movimento até
    31/07) dão o MESMO número, diferença R$0,00;
  • Cora SCD     R$ 17.938,36 — conta nasceu em 15/07/2026 com R$0,00;
  • consolidado  R$ 18.663,83, e abertura + agosto = saldo real dos bancos hoje.
"""

from __future__ import annotations

import os
import re
from datetime import date

# Ajustável por env para o dia em que o corte mudar (virada de exercício, por
# exemplo) sem precisar de deploy de código.
CORTE_CONTABIL = date.fromisoformat(os.getenv("CONECTA_CORTE_CONTABIL", "2026-08-01"))

# Saldo de abertura medido no corte, por conta bancária (ids reais).
ABERTURA_NO_CORTE: dict[str, float] = {
    "20663dc9-805c-4721-bc1f-62a041cee3c1": 725.47,  # Banco Inter
    "1268590a-0a2b-4b16-b959-6c14fe838d93": 17938.36,  # Cora SCD
}


#: Fragmento SQL: o que conta como conta EM ABERTO — a perseguir, cobrar, somar
#: em "vencido". Usar em `receivable_accounts` e `payable_accounts`.
#:
#: `pago` e `cancelada` sempre estiveram fora. **`suspensa` passou a ficar fora em
#: 14/08/2026**: o Jordan mandou reparcelar todos os débitos da Eletrônica com a
#: União, e enquanto isso eles não são cobrança — mas continuavam somando em
#: "vencido". Eram R$140.799,11 aparecendo como dívida a perseguir de um total de
#: R$152.172,72, ou seja, 93% do número era ruído. Quem olha a tela decide caixa
#: por ela.
#:
#: Vive aqui, e não copiado em cada consulta, porque estava escrito à mão em 7
#: lugares (visão do financeiro, tasks de notificação e 4 regras proativas) — a
#: sétima cópia é a que ninguém lembra de atualizar.
SQL_CONTA_EM_ABERTO = (
    "coalesce(status::text,'') NOT ILIKE '%pag%' "
    "AND coalesce(status::text,'') NOT ILIKE '%cancel%' "
    "AND coalesce(status::text,'') <> 'suspensa'"
)


#: Cache do corte por empresa (`empresas.corte_contabil`). O corte é POR EMPRESA
#: desde 26/09/2026: a decisão de 11/08 — "jan–jul foram vividos fora do sistema" —
#: era sobre a ELETRÔNICA, cujo dado veio de CSV e da Portte. A PATRIMONIAL abriu o
#: CNPJ em 31/03/2026 e sempre operou dentro do sistema, com fonte primária (notas do
#: ADN e PGDAS-D). Aplicar a arqueologia da irmã nela custava junho inteiro: 11 notas,
#: R$ 315.764,86 emitidas contra R$ 79.594,13 lançados, e um junho que aparecia com
#: prejuízo de R$ 58 mil por falta de receita, não por falta de resultado.
#:
#: O fato mora em UMA linha do banco (`empresas.corte_contabil`), lida tanto daqui
#: quanto do gatilho `fn_bloqueia_periodo_fechado` — dois leitores, uma verdade.
_CORTE_CACHE: dict[str, date] = {}


def corte_da_empresa(empresa_id: str | None) -> date:
    """Corte contábil desta empresa. Sem empresa, ou sem coluna preenchida: o global."""
    chave = str(empresa_id or "")
    if not chave:
        return CORTE_CONTABIL
    if chave not in _CORTE_CACHE:
        _CORTE_CACHE[chave] = _ler_corte_no_banco(chave) or CORTE_CONTABIL
    return _CORTE_CACHE[chave]


def _ler_corte_no_banco(empresa_id: str) -> date | None:
    """Lê `empresas.corte_contabil`. Qualquer falha devolve None → corte global, que é
    o lado SEGURO: na dúvida o período fica fechado, não aberto."""
    try:
        import psycopg2

        url = re.sub(r"\+asyncpg|\+psycopg2?", "", os.getenv("DATABASE_URL", ""))
        if not url:
            return None
        with psycopg2.connect(url) as conn, conn.cursor() as cur:
            cur.execute("SELECT corte_contabil FROM empresas WHERE id = %s", (empresa_id,))
            linha = cur.fetchone()
            return linha[0] if linha else None
    except Exception:  # noqa: BLE001 — sem banco, o corte global vale
        return None


def corte_mais_antigo() -> date:
    """O corte MAIS ANTIGO entre todas as empresas — para quem varre sem escopo.

    Consulta que não filtra `empresa_id` não pode usar o corte de UMA empresa: usar o da
    Eletrônica (01/08) numa varredura geral esconde junho e julho da Patrimonial, que tem
    corte 01/06. Medido em 26/09/2026: era exatamente isso que acontecia em
    `cobertura_sistema.medir`, em `reconciliation_service.religar_recebiveis_pagos` e em 4
    regras proativas.

    Escolher o mais antigo erra para o lado de MOSTRAR A MAIS, e mostrar a mais é uma
    linha que alguém lê e descarta; esconder é uma linha que ninguém sabe que existe.
    """
    try:
        import psycopg2  # noqa: PLC0415

        url = re.sub(r"\+asyncpg|\+psycopg2?", "", os.getenv("DATABASE_URL", ""))
        if not url:
            return CORTE_CONTABIL
        with psycopg2.connect(url) as conn, conn.cursor() as cur:
            cur.execute("SELECT min(corte_contabil) FROM empresas WHERE corte_contabil IS NOT NULL")
            linha = cur.fetchone()
            menor = linha[0] if linha else None
        # Empresa com `corte_contabil` NULL cai no global; o mínimo real considera os dois.
        return min(menor, CORTE_CONTABIL) if menor else CORTE_CONTABIL
    except Exception:  # noqa: BLE001 — sem banco, o corte global vale
        return CORTE_CONTABIL


def periodo_fechado(d: date | None, empresa_id: str | None = None) -> bool:
    """True se a data cai em período fechado (antes do corte DESTA empresa).

    `None` não é fechado: quem trata data ausente é quem chama — aqui responder
    "fechado" esconderia o registro sem data atrás do motivo errado.
    """
    return d is not None and d < corte_da_empresa(empresa_id)
