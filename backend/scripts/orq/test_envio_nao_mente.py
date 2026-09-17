#!/usr/bin/env python3
"""«Enviado» tem de significar que chegou a um número que EXISTE.

Origem: 17/09/2026. O Jordan: «preciso apenas que tudo funcione, sem bug, sem regressão». O
arsenal apontou 5 funcionários ativos com WhatsApp inexistente — e o cruzamento mostrou que
4 deles estavam na cobrança de assinatura disparada minutos antes, a que terminou com
«30 enviados, 0 falhas». Bianca (3 documentos parados), Eidy (2) e Ediwilson (2) nunca
receberam nada, nem naquele disparo nem nos anteriores.

O buraco estava no `_resolve_jid`: ele devolvia `None` em três situações diferentes — o
WhatsApp dizer que o número não existe, um erro de rede, e a chave não estar configurada — e
o envio tratava as três como «segue com o original». Falha de infra não pode bloquear o envio;
número morto tem de bloquear. São coisas diferentes e precisavam de respostas diferentes.

E o detalhe que quase escapou: para número morto o Baileys devolve **HTTP 200 com lista
VAZIA**, não `exists: false`. A primeira versão da correção tratava lista vazia como «não
consegui perguntar» — e deixava passar exatamente o caso que se queria pegar. Só apareceu
porque fui ver a resposta crua da API em vez de confiar no que eu tinha escrito.

## A regra afirmada

Número que o WhatsApp diz não existir NÃO recebe envio silencioso: `_send_message` devolve
`status: error` com `erro: numero_inexistente`. Número vivo segue normal. Quando não dá para
perguntar (rede, chave), segue com o original — infra quebrada não pode calar a empresa.

    python3 backend/scripts/orq/test_envio_nao_mente.py

Linha canônica: `TOTAL: <n> caso(s) em que o envio mente`. Exit 1 quando há achado.
"""

from __future__ import annotations

import subprocess
import sys

DOCKER = "/usr/bin/docker"  # nosec B607 - absoluto por causa do ruff S607

#: Número real de funcionária ATIVA, medido como inexistente em 17/09/2026. Se um dia passar a
#: existir (ela pode criar conta), a trava avisa — e aí se troca por outro comprovadamente morto.
_MORTO = "+5592988887777"

_PROVA = r"""
import sys, asyncio, json
sys.path.insert(0, '/app')
from modules.integrations.connectors.whatsapp.service import WhatsAppService, NUMERO_NAO_EXISTE

async def main():
    import os, aiohttp
    sv = WhatsAppService()

    # 0) PERGUNTA DIRETA ao Baileys — a fonte de fora. Sem isto, o «SEM_RESPOSTA» do
    #    resolvedor é ambíguo: pode ser rede caída (aceitável) ou o defeito de tratar a
    #    lista vazia como «não consegui perguntar» (o bug de 17/09). Medindo os dois, a
    #    trava sabe qual é qual — e a sabotagem de teste deixou de passar batida.
    base = os.getenv('BAILEYS_API_URL', 'http://baileys-api:3025').rstrip('/')
    key = os.getenv('BAILEYS_API_KEY', '')
    sender = os.getenv('BAILEYS_COMPANY_PHONE') or os.getenv('WHATSAPP_SENDER') or '+558008804414'
    d = ''.join(c for c in MORTO if c.isdigit())
    cru = 'INDISPONIVEL'
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(f'{base}/connections/{sender}/on-whatsapp',
                              json={'jids': [f'{d}@s.whatsapp.net']},
                              headers={'x-api-key': key, 'Content-Type': 'application/json'},
                              timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status == 200:
                    data = await r.json()
                    cru = 'VIVO' if (isinstance(data, list) and data) else 'MORTO'
    except Exception:
        pass
    print('BAILEYS|' + cru)

    # 1) o resolvedor separa «não existe» de «não consegui perguntar»
    r = await sv._resolve_jid(MORTO)
    print('RESOLVE|' + ('NAO_EXISTE' if r == NUMERO_NAO_EXISTE else ('VIVO:' + r if r else 'SEM_RESPOSTA')))
    # 2) o envio recusa, em vez de dizer sucesso
    env = await sv._send_message(MORTO, '[trava: nao deve sair]')
    print('ENVIO|' + str(env.get('status')) + '|' + str(env.get('erro') or ''))

asyncio.run(main())
"""


import sys as _sys  # noqa: E402

_sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from _fixtures import exige_host  # noqa: E402


def main() -> int:
    exige_host("fala com o Baileys e com outro container por docker")
    achados: list[str] = []
    try:
        codigo = f'MORTO = "{_MORTO}"\n{_PROVA}'
        saida = subprocess.run(  # noqa: S603  # nosec B603 - argv fixo, sem shell
            [DOCKER, "exec", "-e", "PYTHONPATH=/app", "conecta-pro-backend", "python3", "-c", codigo],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        ).stdout
        res = {}
        for linha in saida.strip().splitlines():
            if "|" in linha:
                partes = linha.split("|")
                res[partes[0]] = partes[1:]

        baileys = (res.get("BAILEYS") or ["INDISPONIVEL"])[0]
        resolve = (res.get("RESOLVE") or [""])[0]

        if baileys == "INDISPONIVEL":
            print("  (Baileys fora do ar — regra não conferida nesta rodada)")
        elif baileys == "MORTO" and resolve == "SEM_RESPOSTA":
            # O Baileys RESPONDEU que o número não existe e o resolvedor não percebeu.
            # É exatamente o defeito de 17/09: lista vazia lida como «não consegui perguntar».
            achados.append(
                "o Baileys respondeu que o número NÃO existe e o resolvedor devolveu "
                "«não consegui perguntar» — a mensagem sairia e morreria no caminho, com "
                "sucesso no relatório"
            )
        elif resolve == "SEM_RESPOSTA":
            print("  (Baileys não respondeu — regra não conferida nesta rodada)")
        elif resolve.startswith("VIVO:"):
            print(f"  ({_MORTO} passou a existir — troque o número desta trava)")
        elif resolve != "NAO_EXISTE":
            achados.append(f"o resolvedor devolveu {resolve!r} para um número inexistente")
        else:
            envio = res.get("ENVIO") or ["", ""]
            if envio[0] != "error":
                achados.append(
                    f"o envio para número inexistente devolveu status={envio[0]!r} — voltou a "
                    "reportar sucesso para mensagem que morre no caminho"
                )
            elif len(envio) < 2 or envio[1] != "numero_inexistente":
                achados.append(
                    f"o envio recusou, mas sem dizer por quê (erro={envio[1:]!r}) — quem lê o "
                    "relatório não descobre que o telefone do cadastro está morto"
                )
    except (OSError, subprocess.SubprocessError) as exc:
        achados.append(f"não deu para provar o envio: {exc}")

    for a in achados:
        print(f"  ✗ {a}")
    print(f"TOTAL: {len(achados)} caso(s) em que o envio mente")
    return 1 if achados else 0


if __name__ == "__main__":
    sys.exit(main())
