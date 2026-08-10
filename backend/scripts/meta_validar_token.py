#!/usr/bin/env python3
"""Diz exatamente o que um token da Meta é, o que ele pode e o que falta.

Existe porque a falha mais comum não avisa na hora: o token sai do Business
Manager parecendo certo, e só falha depois — sem a permissão, sem a conta
atribuída, ou já expirado. Este script responde isso em uma rodada, sem
navegador e sem tentar login (a conta ficou sinalizada por acesso de dois IPs
em 2026-08-10; nada aqui toca em sessão de usuário).

  META_ADS_TOKEN=EAAG... python3 scripts/meta_validar_token.py
  META_CAPI_TOKEN=EAAG... python3 scripts/meta_validar_token.py --capi
"""

import argparse
import asyncio
import json
import os
import sys

import aiohttp

GRAPH = "https://graph.facebook.com"
VERSAO = os.getenv("META_GRAPH_VERSION", "v21.0")
# O que cada trilho precisa. Faltando qualquer uma, a integração falha em silêncio.
NECESSARIAS = {
    "ads": ("ads_read", "business_management"),
    "capi": (),  # token de dataset não usa scopes de usuário
}


async def _get(s, caminho, token, **params):
    url = f"{GRAPH}/{VERSAO}/{caminho}"
    async with s.get(url, params={**params, "access_token": token}, timeout=aiohttp.ClientTimeout(total=25)) as r:
        return r.status, await r.json()


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capi", action="store_true", help="valida o token do Conversions API")
    a = ap.parse_args()

    token = (os.getenv("META_CAPI_TOKEN") if a.capi else os.getenv("META_ADS_TOKEN")) or ""
    token = token.strip()
    if not token:
        print("Defina META_ADS_TOKEN (ou META_CAPI_TOKEN com --capi). Não vou adivinhar.")
        return 2

    problemas = []
    async with aiohttp.ClientSession() as s:
        # 1) o token é válido? de quem é? expira quando?
        st, dbg = await _get(s, "debug_token", token, input_token=token)
        d = (dbg or {}).get("data") or {}
        if st != 200 or not d.get("is_valid"):
            print(f"  TOKEN INVÁLIDO — {json.dumps(dbg)[:220]}")
            return 1
        expira = d.get("expires_at")
        print(f"  válido      : sim · app_id={d.get('app_id')} · tipo={d.get('type')}")
        print(f"  expira      : {'NUNCA (permanente)' if expira in (0, None) else f'timestamp {expira}'}")
        escopos = set(d.get("scopes") or [])
        print(f"  permissões  : {', '.join(sorted(escopos)) or '(nenhuma)'}")

        faltando = set(NECESSARIAS["capi" if a.capi else "ads"]) - escopos
        if faltando:
            problemas.append(f"faltam permissões: {', '.join(sorted(faltando))}")

        if not a.capi:
            # 2) o token ENXERGA alguma conta de anúncios? (o erro nº1: token ok, conta não atribuída)
            st2, contas = await _get(s, "me/adaccounts", token, fields="id,name,account_status,currency,timezone_name")
            lista = (contas or {}).get("data") or []
            print(f"  contas      : {len(lista)}")
            for c in lista:
                print(f"     {c.get('id')} · {c.get('name')} · {c.get('currency')} · {c.get('timezone_name')}")
            if not lista:
                problemas.append(
                    "o token não enxerga NENHUMA conta de anúncios — crie a conta e "
                    "atribua ao System User em Configurações → Usuários do sistema → Adicionar ativos"
                )
            alvo = os.getenv("META_AD_ACCOUNT_ID", "").strip()
            if alvo and not any(c.get("id") == (alvo if alvo.startswith("act_") else f"act_{alvo}") for c in lista):
                problemas.append(f"META_AD_ACCOUNT_ID={alvo} não está entre as contas que este token enxerga")

    print()
    if problemas:
        print("FALTA RESOLVER:")
        for p in problemas:
            print("  -", p)
        return 1
    print("TOKEN OK — pronto para ligar a sincronia.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
