"""Recibo de DCTFWeb que chega pelo Onvio também dá baixa na obrigação.

O buraco, medido em 15/08/2026: a DCTFWeb da competência 07/2026 estava **transmitida desde
11/08** — recibo `0000050000514331309`, `TOTAL R$ 1.758,05`, **saldo a pagar R$ 0,00** — e as
três acessórias (DCTFWEB, ESOCIAL, EFD_REINF) apareciam `pendente` vencendo naquele mesmo
dia. O painel dizia ao Jordan que ele tinha três prazos estourando hoje sem saber quanto
pagar, e os três já estavam cumpridos.

A regra de baixa existia e estava certa — `marcar_acessorias`, em `guias_drive_service`. O
que faltava era o gatilho: ela só era chamada pelo caminho do **Drive**, e o Drive virou
pasta de documentos cadastrais. Os documentos vêm do **Onvio**, cuja extração guarda
`numero_recibo` e `data_transmissao` em `onvio_documents.detalhes_json` — e parava ali.

Prazo cumprido que continua aceso é a mesma doença dos R$68 mil de abril a julho: assusta,
não informa, e ensina a ignorar o painel.

⚠️ Só dá baixa com recibo do EMISSOR. Sem `numero_recibo` no documento, não faz nada —
"provavelmente foi entregue" não é baixa.

Roda:
    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 -c \
      "from modules.fiscal_contabil.obrigacoes.baixa_por_recibo_onvio import baixar; print(baixar())"
"""

from __future__ import annotations

import json
import logging
import re

from sqlalchemy import text

logger = logging.getLogger(__name__)

#: A RFB nomeia o arquivo com o CNPJ (`DCTFWEB Recibo_35710481000103_072026_...`). É a
#: atribuição mais confiável que existe hoje: o `dctfweb_extractor` ainda guarda só um
#: booleano `cnpj_validado`, contra um CNPJ cravado no regex — mesmo defeito que o
#: `fgts_extractor` tinha. Quando ele passar a capturar, esta função prefere o capturado.
#: `(?<!\d)…(?!\d)` e não `\b`: o nome do arquivo separa os campos com UNDERSCORE, e `_` é
#: caractere de palavra — `\b` não existe entre `_` e um dígito, então `\b(\d{14})\b` não
#: casava `Recibo_35710481000103_072026`. O self-check pegou.
_RE_CNPJ_ARQUIVO = re.compile(r"(?<!\d)(\d{14})(?!\d)")

_SQL_RECIBOS = """
    SELECT nome_arquivo, mes_ref, detalhes_json
      FROM onvio_documents
     WHERE categoria LIKE 'dctfweb%'
       AND detalhes_json IS NOT NULL
       AND mes_ref ~ '^[0-9]{2}\\.[0-9]{4}$'
"""


def _competencia(mes_ref: str) -> tuple[int, int] | None:
    """'07.2026' → (7, 2026). Devolve None em qualquer outro formato — não adivinha."""
    try:
        mes, ano = mes_ref.split(".")
        return int(mes), int(ano)
    except (ValueError, AttributeError):
        return None


def baixar(db=None) -> dict:
    """Dá baixa nas acessórias de toda competência que tem recibo de DCTFWeb no Onvio."""
    from modules.fiscal_contabil.obrigacoes.guias_drive_service import marcar_acessorias

    proprio = db is None
    if proprio:
        from core.database.session import SyncSessionLocal
        db = SyncSessionLocal()

    try:
        vistos: set[tuple[str, int, int]] = set()
        resultado: dict = {"baixadas": [], "sem_recibo": 0, "sem_empresa": 0}

        for nome, mes_ref, detalhes in db.execute(text(_SQL_RECIBOS)).fetchall():
            comp = _competencia(mes_ref)
            if not comp:
                continue
            mes, ano = comp
            d = detalhes if isinstance(detalhes, dict) else json.loads(detalhes or "{}")
            det = d.get("detalhes") or {}
            recibo = det.get("numero_recibo")
            if not recibo:
                resultado["sem_recibo"] += 1
                continue

            cnpj = det.get("cnpj_empregador")
            if not cnpj:
                m = _RE_CNPJ_ARQUIVO.search(nome or "")
                cnpj = m.group(1) if m else None
            if not cnpj:
                resultado["sem_empresa"] += 1
                continue

            emp = db.execute(text(
                "SELECT id::text FROM empresas "
                " WHERE replace(replace(replace(cnpj,'.',''),'/',''),'-','') = :c LIMIT 1"),
                {"c": cnpj}).scalar()
            if not emp:
                resultado["sem_empresa"] += 1
                continue

            chave = (emp, mes, ano)
            if chave in vistos:      # os 6 arquivos da DCTFWeb trazem o MESMO recibo
                continue
            vistos.add(chave)

            marcadas = marcar_acessorias(
                db, emp, mes, ano, recibo,
                f"transmitida em {det.get('data_transmissao') or 'data não extraída'}; "
                f"fonte onvio {nome}")
            if marcadas:
                resultado["baixadas"].append(
                    {"empresa_id": emp, "competencia": f"{mes:02d}/{ano}",
                     "recibo": recibo, "tipos": marcadas})

        db.commit()
        logger.info("[baixa_onvio] %s competência(s) baixada(s)", len(resultado["baixadas"]))
        return resultado
    finally:
        if proprio:
            db.close()


if __name__ == "__main__":
    # Self-check sem banco: o parser de competência é onde um formato novo passa calado.
    assert _competencia("07.2026") == (7, 2026)
    assert _competencia("2026") is None, "só o ano não é competência"
    assert _competencia("") is None and _competencia(None) is None
    assert _competencia("07/2026") is None, "o Onvio grava com PONTO; barra não é o formato"
    assert _RE_CNPJ_ARQUIVO.search("DCTFWEB Recibo_35710481000103_072026_40_x.pdf").group(1) \
        == "35710481000103"
    assert _RE_CNPJ_ARQUIVO.search("GFD FGTS 07.2026_Conecta Mais.pdf") is None
    print("self-check OK")
