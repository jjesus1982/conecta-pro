"""Certidões de CNPJ pela API do Infosimples — fonte que realmente responde.

Por que existe: os clientes que raspam portal não conseguem mais emitir. Medido em
11/08/2026, com os dois CNPJs do grupo:

  • `cnd_client` (RFB): o portal exige login gov.br → cai para BrasilAPI, que só devolve
    situação CADASTRAL, e retorna `indeterminado_portal_indisponivel`;
  • `crf_client` (Caixa): mesma coisa;
  • `prefeitura_manaus_client`: pior — carregava a PÁGINA DE SERVIÇO da SEMEF e procurava
    "débito"/"pendência"/"irregular" no HTML. Palavras que existem em qualquer página que
    EXPLICA o que é uma certidão de débitos. Resultado: dizia `irregular` para todo CNPJ,
    inclusive o do Banco do Brasil usado como controle.

O Infosimples resolve captcha/gov.br e devolve o documento. Token já configurado
(`INFOSIMPLES_TOKEN`). Provado no mesmo dia: `caixa/regularidade` e `tribunal/tst/cndt`
responderam code 200 para os dois CNPJs, com número de CRF e validade reais.

Consulta é PAGA por chamada — por isso o sync só cai aqui quando precisa, e o teto de
"pular se válida por mais de 10 dias" do chamador continua valendo.

Nunca estima validade: sem data do órgão, devolve `sem_validade` e o chamador não grava.
Foi um fallback de "hoje + 180 dias" que fabricou quatro certidões em 11/08.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BASE = "https://api.infosimples.com/api/v2/consultas"

#: apelido interno → serviço na Infosimples. Só entram os provados respondendo.
SERVICOS = {
    "crf_fgts": "caixa/regularidade",
    "cndt_trabalhista": "tribunal/tst/cndt",
    "cnd_federal": "receita-federal/pgfn",
}

_TIMEOUT_HTTP = 120.0


def habilitado() -> bool:
    return bool((os.getenv("INFOSIMPLES_TOKEN") or "").strip())


def _iso(br: str | None) -> str | None:
    """'05/09/2026' → '2026-09-05'. Devolve None se não for data — nunca chuta."""
    if not br:
        return None
    try:
        return datetime.strptime(br.strip()[:10], "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None


def _do_crf(d: dict) -> dict[str, Any]:
    """CRF-FGTS: a validade vem no histórico (Emissão | Início | Fim | Número), mais nova
    primeiro. `situacao` REGULAR sozinha não basta: sem a data não há certidão."""
    hist = d.get("historico_lista") or []
    fim = numero = None
    if hist and isinstance(hist[0], list) and len(hist[0]) >= 4:
        fim, numero = hist[0][2], hist[0][3]
    return {
        "situacao": (d.get("situacao") or "").strip().lower() or "regular",
        "data_validade": _iso(fim),
        "numero": numero or d.get("crf"),
    }


def _do_cndt(d: dict) -> dict[str, Any]:
    return {
        "situacao": "regular" if (d.get("validade") or d.get("numero")) else "",
        "data_validade": _iso(d.get("validade")),
        "numero": d.get("numero") or d.get("certidao"),
    }


def _do_pgfn(d: dict) -> dict[str, Any]:
    return {
        "situacao": (d.get("situacao") or d.get("tipo_certidao") or "").strip().lower(),
        "data_validade": _iso(d.get("validade") or d.get("data_validade")),
        "numero": d.get("numero") or d.get("codigo_controle"),
    }


_PARSERS = {"crf_fgts": _do_crf, "cndt_trabalhista": _do_cndt, "cnd_federal": _do_pgfn}


async def consultar(tipo: str, cnpj: str) -> dict[str, Any]:
    """Consulta uma certidão de CNPJ. Devolve o formato que `_buscar_e_salvar_certidao` espera.

    `situacao` só volta preenchida quando o órgão respondeu; `data_validade` só quando a
    data veio do documento. Quem grava decide a partir daí — este módulo não afirma nada
    que a fonte não disse.
    """
    servico = SERVICOS.get(tipo)
    if not servico:
        return {"situacao": "erro_consulta", "mensagem": f"tipo sem serviço mapeado: {tipo}"}
    token = (os.getenv("INFOSIMPLES_TOKEN") or "").strip()
    if not token:
        return {"situacao": "erro_consulta", "mensagem": "INFOSIMPLES_TOKEN não configurado"}

    digitos = "".join(ch for ch in (cnpj or "") if ch.isdigit())
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_HTTP) as cli:
            resp = await cli.post(f"{_BASE}/{servico}",
                                  data={"token": token, "cnpj": digitos, "timeout": 600})
        payload = resp.json()
    except Exception as exc:  # noqa: BLE001 — falha de rede não pode virar certidão
        logger.warning("[infosimples] %s/%s falhou: %s", servico, digitos, exc)
        return {"situacao": "erro_consulta", "mensagem": str(exc)[:200]}

    code = payload.get("code")
    if code != 200:
        # 611 = "dados incompletos no site de origem": o órgão respondeu mal, não a empresa.
        logger.info("[infosimples] %s/%s code=%s %s", servico, digitos, code,
                    payload.get("code_message"))
        return {"situacao": "indeterminado_fonte",
                "mensagem": f"code {code}: {payload.get('code_message')}"}

    dados = (payload.get("data") or [{}])[0]
    out = _PARSERS[tipo](dados)
    out.update({
        "cnpj": digitos,
        "fonte": f"Infosimples/{servico}",
        "recibo": (payload.get("site_receipts") or [None])[0],
        "consultado_em": datetime.utcnow().isoformat(),
    })
    if not out.get("data_validade"):
        out["situacao"] = out.get("situacao") or "sem_validade"
    return out


if __name__ == "__main__":
    # Self-check sem rede: a conversão de data e o parser do CRF são a lógica que erra calado.
    assert _iso("05/09/2026") == "2026-09-05"
    assert _iso("") is None and _iso(None) is None
    assert _iso("nao é data") is None, "data inválida não pode virar validade"
    crf = _do_crf({"situacao": "REGULAR", "crf": "X",
                   "historico_lista": [["07/08/2026", "07/08/2026", "05/09/2026", "2026080707"]]})
    assert crf == {"situacao": "regular", "data_validade": "2026-09-05", "numero": "2026080707"}, crf
    assert _do_crf({"situacao": "REGULAR"})["data_validade"] is None, "sem histórico não há validade"
    assert _do_cndt({"validade": "07/02/2027", "numero": "N"})["data_validade"] == "2027-02-07"
    assert _do_cndt({})["data_validade"] is None
    print("self-check OK")
