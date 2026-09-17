#!/usr/bin/env python3
"""Prova cada chave PIX com R$ 0,01 e mostra QUEM recebeu, antes do lote de verdade.

Origem: 16/09/2026. O Jordan perguntou se o Conecta PRO confere a chave contra o titular como
o app do banco faz. Não confere, e não tem como: a API Banking do Inter não expõe consulta DICT
— treze caminhos testados contra a API real, nenhum existe. O nome do recebedor só aparece
DEPOIS de o PIX estar PAGO (medido com R$ 0,01 para a chave dele, autorizado).

Então a conferência prévia se faz do único jeito possível: mandando um centavo, olhando o nome
que volta, e só então liberando o valor cheio. É o que o app do banco faz por dentro, feito por
fora — e custa R$ 0,54 para conferir 54 pessoas.

    # sem mandar nada, só listar o que seria testado:
    python3 backend/scripts/provar_chaves_por_centavo.py --arquivo /tmp/fila.json

    # mandando de verdade (exige a confirmação por extenso):
    python3 backend/scripts/provar_chaves_por_centavo.py --arquivo /tmp/fila.json \
        --enviar --confirmo "SIM, ENVIAR CENTAVOS"

O arquivo é um JSON com `fila`: lista de {nome_cad, cpf, pix, total}. Escreve o resultado em
`--saida` (default /tmp/prova_chaves.json) para a tela e o relatório lerem.

⚠️ MOVE DINHEIRO REAL. R$ 0,01 por pessoa, não estornável. Por isso o padrão é NÃO enviar.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys
from decimal import Decimal

sys.path[0] = str(pathlib.Path(__file__).resolve().parents[1])

from modules.financial.services.conferencia_pix import conferir  # noqa: E402

#: Entre um envio e a consulta. Medido: com 3s o status já estava PAGO e o nome disponível.
ESPERA_S = 4.0
CENTAVO = Decimal("0.01")


async def _adapter():
    from modules.integrations.banking.adapters.base import BankCredentials  # noqa: PLC0415
    from modules.integrations.banking.adapters.inter import InterAdapter  # noqa: PLC0415

    cred = BankCredentials(
        client_id=os.getenv("INTER_CLIENT_ID", ""),
        client_secret=os.getenv("INTER_CLIENT_SECRET", ""),
        certificate_path=os.getenv("INTER_CERT_PATH"),
        private_key_path=os.getenv("INTER_KEY_PATH"),
        agency=os.getenv("INTER_AGENCY"),
        account=os.getenv("INTER_ACCOUNT"),
        environment=os.getenv("INTER_ENVIRONMENT", "production"),
    )
    a = InterAdapter(cred)
    if not await a.authenticate():
        print("RECUSO: não autenticou no Inter")
        return None
    return a


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arquivo", required=True)
    # Sem default em /tmp: o arquivo carrega nome e CPF de 54 pessoas, e /tmp é legível por
    # qualquer processo do container. Quem chama diz onde quer.
    ap.add_argument("--saida", default=str(pathlib.Path.home() / "prova_chaves.json"))
    ap.add_argument("--enviar", action="store_true")
    ap.add_argument("--confirmo", default="")
    ap.add_argument("--limite", type=int, default=0, help="testa só os N primeiros")
    args = ap.parse_args()

    with open(args.arquivo, encoding="utf8") as fh:
        d = json.load(fh)
    fila = d["fila"] if isinstance(d, dict) else d
    if args.limite:
        fila = fila[: args.limite]

    if not args.enviar:
        print(f"ENSAIO — nada foi enviado. {len(fila)} chave(s) seriam testadas:")
        for x in fila[:8]:
            print(f"   {x['nome_cad'][:34]:34s} {x['pix']}")
        if len(fila) > 8:
            print(f"   (+{len(fila) - 8} não listadas)")
        print(f"\nCusto se enviar: R$ {len(fila) * 0.01:,.2f}")
        print('Para enviar de verdade: --enviar --confirmo "SIM, ENVIAR CENTAVOS"')
        return 0

    if args.confirmo != "SIM, ENVIAR CENTAVOS":
        print('RECUSO: --enviar exige --confirmo "SIM, ENVIAR CENTAVOS" (dinheiro real)')
        return 2

    a = await _adapter()
    if a is None:
        return 2

    res = []
    for i, x in enumerate(fila, 1):
        env = await a.enviar_pix(
            chave=x["pix"], tipo_chave="", valor=CENTAVO, nome_recebedor="", descricao="Conferencia de chave PIX"
        )
        linha = {"nome_cad": x["nome_cad"], "pix": x["pix"], "cpf": x.get("cpf", ""), "valor_previsto": x.get("total")}
        if not env.get("success"):
            linha |= {
                "veredito": "FALHOU O ENVIO",
                "ok": False,
                "detalhe": str(env.get("detail") or env.get("error"))[:200],
            }
            res.append(linha)
            print(f"  {i:3d}/{len(fila)}  ❌ {x['nome_cad'][:32]:32s} {linha['detalhe'][:70]}")
            continue

        cod = env.get("codigoSolicitacao", "")
        await asyncio.sleep(ESPERA_S)
        c = await a.consultar_pix_pagamento(cod)
        v = conferir(
            nome_banco=c.get("recebedor_nome", ""),
            documento_banco=c.get("recebedor_documento", ""),
            nome_nosso=x["nome_cad"],
            documento_nosso=x.get("cpf", ""),
        )
        linha |= {
            "codigo": cod,
            "status": c.get("status", ""),
            "nome_banco": c.get("recebedor_nome", ""),
            "documento_banco": c.get("recebedor_documento", ""),
            **v,
        }
        res.append(linha)
        icone = {"confere": "✅", "DIVERGE": "⚠️", "nao_confirmado": "·"}.get(v["veredito"], "?")
        print(
            f"  {i:3d}/{len(fila)}  {icone} {x['nome_cad'][:32]:32s} banco: {c.get('recebedor_nome', '(vazio)')[:34]}"
        )

    pathlib.Path(args.saida).write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf8")
    bons = sum(1 for r in res if r.get("ok") is True)
    ruins = [r for r in res if r.get("ok") is False]
    print(f"\n   {bons} confere(m) · {len(ruins)} com problema · {len(res) - bons - len(ruins)} não confirmado(s)")
    for r in ruins:
        print(f"   {r['veredito']}  {r['nome_cad']}: {r.get('detalhe', '')[:110]}")
    print(f"   resultado em {args.saida}")
    print(f"\nTOTAL: {len(ruins)} chave(s) com problema")
    return 1 if ruins else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
