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
from datetime import date

# Ajustável por env para o dia em que o corte mudar (virada de exercício, por
# exemplo) sem precisar de deploy de código.
CORTE_CONTABIL = date.fromisoformat(os.getenv("CONECTA_CORTE_CONTABIL", "2026-08-01"))

# Saldo de abertura medido no corte, por conta bancária (ids reais).
ABERTURA_NO_CORTE: dict[str, float] = {
    "20663dc9-805c-4721-bc1f-62a041cee3c1": 725.47,    # Banco Inter
    "1268590a-0a2b-4b16-b959-6c14fe838d93": 17938.36,  # Cora SCD
}


def periodo_fechado(d: date | None) -> bool:
    """True se a data cai em período fechado (antes do corte).

    `None` não é fechado: quem trata data ausente é quem chama — aqui responder
    "fechado" esconderia o registro sem data atrás do motivo errado.
    """
    return d is not None and d < CORTE_CONTABIL
