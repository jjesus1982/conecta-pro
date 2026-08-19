"""Quais CNDs da Patrimonial estão faltando — imprime os PORTAIS, um por linha.

Existe como arquivo, e não embutido no `cnd_auto_retry.sh`, porque a versão inline tinha as
aspas destroçadas pelo shell e o `2>/dev/null` engolia o `SyntaxError`: o script saía
dizendo "não falta nada" e o cron seguia feliz sem nunca pedir a certidão. Silêncio fingindo
sucesso — exatamente o defeito que este módulo passou o dia caçando.

⭐ Certidão negativa é exigida SÓ da PATRIMONIAL (decisão do Jordan, 19/08/2026): ela presta
mão de obra e é dela que o contratante cobra CND para pagar fatura e licitar. A Eletrônica
vende segurança eletrônica — "basta nota e boleto".

⚠️ `crf_fgts` fica de fora: a Caixa bloqueia este IP na borda (403 Azion, e o Chromium real
toma o mesmo 403). Ele vem pelo Infosimples, no ciclo diário.

Uso:  docker exec -w /app -e PYTHONPATH=/app conecta-pro-backend python /app/.../cnd_faltantes.py
"""

from __future__ import annotations

import datetime
import re
import sys

from sqlalchemy import text

from core.database.session import get_sync_db

#: portal que o robô sabe emitir → document_type correspondente
PORTAL_DOC = {
    "federal": "certidao_negativa_federal",
    "prefeitura": "certidao_negativa_municipal",
    "sefaz_am": "certidao_negativa_estadual",
    "cndt": "certidao_negativa_trabalhista",
}

CNPJ_PATRIMONIAL = "66014833000110"

#: Renova com 15 dias de antecedência — tempo de a Receita/SEMEF cooperarem antes do vencimento.
DIAS_DE_FOLGA = 15

_SQL = """
    SELECT expiry_date
      FROM ged_certidoes
     WHERE document_type = :dt
       AND replace(replace(replace(coalesce(cnpj,''),'.',''),'/',''),'-','') = :c
       -- registro que NÃO confirma nada não conta como certidão: o fallback da BrasilAPI
       -- (regular: null) fez a Federal da Eletrônica dormir até 2027 sem ninguém tentar.
       AND coalesce(notes,'') NOT LIKE '%"regular": null%'
       AND coalesce(notes,'') NOT LIKE '%indeterminado%'
     LIMIT 1
"""


def faltantes(cnpj: str = CNPJ_PATRIMONIAL) -> list[str]:
    limite = datetime.date.today() + datetime.timedelta(days=DIAS_DE_FOLGA)
    digitos = re.sub(r"\D", "", cnpj)
    falta: list[str] = []
    with get_sync_db() as db:
        for portal, dt in PORTAL_DOC.items():
            r = db.execute(text(_SQL), {"dt": dt, "c": digitos}).fetchone()
            if not (r and r[0] and r[0] > limite):
                falta.append(portal)
    return falta


if __name__ == "__main__":
    try:
        for p in faltantes():
            print(p)
    except Exception as exc:  # noqa: BLE001
        # Falha vai para stderr E devolve código != 0: quem chama precisa distinguir
        # "nada falta" de "não consegui perguntar". Foi confundir os dois que deixou o
        # retry mudo.
        print(f"ERRO ao consultar certidões: {exc}", file=sys.stderr)
        sys.exit(2)
