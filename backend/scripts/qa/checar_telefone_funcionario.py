#!/usr/bin/env python3
"""O telefone do funcionário no cadastro EXISTE no WhatsApp? — perguntado ao WhatsApp.

Origem (11/09/2026). O Jordan mandou corrigir o número da MEIRE. O cadastro dela era
`(92) 94699767` — dez dígitos, que o normalizador aceita como fixo com DDD, então o sistema
mandava mensagem e se dava por satisfeito. O número real é `(92) 99469-9767`: faltava o nono
dígito. E ela não foi a única — cinco cadastros estavam assim.

O que torna isto invisível sem esta trava: **a casa nunca soube se a mensagem chegou**. O
lembrete de ponto registra "enviado"; o WhatsApp aceita o envio para um JID inexistente e a
mensagem morre. Medido no mesmo dia: 9 funcionários ativos têm telefone que NÃO EXISTE no
WhatsApp, e dois deles receberam 13 lembretes cada, todos no vazio. Do lado de dentro, tudo
verde; do lado de fora, ninguém recebeu nada.

Por isso a pergunta é feita ao WhatsApp (Baileys `on-whatsapp`), que é a fonte de fora — a
mesma postura do `checar_oraculo_externo`: releitura do nosso próprio banco não desmente o
nosso próprio banco. `on-whatsapp` só RESOLVE o número, não envia nada.

⚠️ Duas armadilhas medidas ao construir, e as duas viraram desenho:
  · **o lote mente por omissão**: pedindo 5 números, a API devolve só os 2 que existem — sem
    ordem e sem o mesmo tamanho. Casar por POSIÇÃO troca a resposta de uma pessoa pela de
    outra (a primeira versão desta sonda produziu uma tabela inteira, plausível e errada,
    dizendo que o número da Meire era o de outra pessoa). Aqui se pergunta UM de cada vez.
  · **falso negativo sob carga**: dois números existentes voltaram como inexistentes num lote.
    Três tentativas por número, e API fora do ar é "NÃO MEDIDO" com saída 0 — nunca vermelho
    falso. Trava que grita sem motivo é trava que ninguém lê.

    python3 backend/scripts/qa/checar_telefone_funcionario.py

Linha canônica: `TOTAL telefones malformados: N` (binária: N = 0).
"""
from __future__ import annotations

import json
import subprocess
import sys

CONTAINER = "conecta-pro-backend"

_SONDA = r'''
import asyncio, json, os, re, sys
import aiohttp
from sqlalchemy import text
from core.database import async_session_factory

def normaliza(bruto):
    """Dígitos de um celular BR válido (DDD + 9 + 8), ou "" se não dá para confiar.
    Mesma régua do `lembrete_ponto.normalizar_telefone`, apertada para CELULAR: o cadastro
    do funcionário é o número de WhatsApp dele, e fixo com DDD passava batido ali."""
    d = re.sub(r"\D", "", bruto or "")
    if len(d) != 11 or d[2] != "9" or not ("11" <= d[:2] <= "99"):
        return ""
    return d

async def main():
    async with async_session_factory() as db:
        linhas = (await db.execute(text(
            "SELECT nome, coalesce(nullif(celular,''), telefone, '') FROM employees "
            " WHERE coalesce(status,'ativo') <> 'inativo' AND coalesce(is_homologacao,false)=false "
            " ORDER BY nome"))).fetchall()
    base = os.getenv("BAILEYS_API_URL", "http://baileys-api:3025").rstrip("/")
    key = os.getenv("BAILEYS_API_KEY", "")
    sender = os.getenv("BAILEYS_COMPANY_PHONE") or os.getenv("WHATSAPP_SENDER") or "+558008804414"
    if not key:
        print("JSON " + json.dumps({"medido": False, "motivo": "BAILEYS_API_KEY ausente"}))
        return
    sem_fone, malformados, ausentes, ok = [], [], [], 0
    vivo = False
    async with aiohttp.ClientSession() as s:
        for nome, fone in linhas:
            if not (fone or "").strip():
                sem_fone.append(nome); continue
            d = normaliza(fone)
            if not d:
                malformados.append({"nome": nome, "fone": fone}); continue
            achou = ""
            for _ in range(3):
                try:
                    async with s.post(f"{base}/connections/{sender}/on-whatsapp",
                        json={"jids": [f"55{d}@s.whatsapp.net"]},
                        headers={"x-api-key": key, "Content-Type": "application/json"},
                        timeout=aiohttp.ClientTimeout(total=20)) as r:
                        data = await r.json() if r.status == 200 else None
                    if data is None:
                        await asyncio.sleep(1.5); continue
                    vivo = True
                    for it in (data if isinstance(data, list) else []):
                        if isinstance(it, dict) and it.get("exists") and it.get("jid"):
                            achou = re.sub(r"\D", "", str(it["jid"]).split("@")[0])
                    if achou: break
                except Exception:
                    pass
                await asyncio.sleep(1.5)
            (ok := ok + 1) if achou else ausentes.append({"nome": nome, "fone": fone})
            await asyncio.sleep(0.4)
    print("JSON " + json.dumps({"medido": vivo, "ok": ok, "sem_fone": sem_fone,
                                "malformados": malformados, "ausentes": ausentes}, ensure_ascii=False))
asyncio.run(main())
'''


def main() -> int:
    r = subprocess.run(  # noqa: S603 — nomes fixos
        ["/usr/bin/docker", "exec", "-e", "PYTHONPATH=/app", "-i", CONTAINER, "python3", "-"],
        input=_SONDA, capture_output=True, text=True, timeout=900,
    )
    linha = next((x for x in r.stdout.splitlines() if x.startswith("JSON ")), "")
    if not linha:
        print(f"ERRO: a sonda não devolveu resultado — {(r.stderr or '').strip()[-300:]}")
        return 2
    d = json.loads(linha[5:])
    if not d.get("medido"):
        # NÃO MEDIDO não é verde e não é vermelho: é a terceira coisa, e dizê-la é o ponto.
        print(f"NÃO MEDIDO: o WhatsApp não respondeu ({d.get('motivo', 'Baileys fora do ar')}) — "
              "isto não é 'todos os telefones estão certos'")
        print("TOTAL telefones malformados: 0")
        return 0

    for m in d["malformados"]:
        print(f"  MALFORMADO: {m['nome']} — {m['fone']!r} não é celular BR (DDD + 9 + 8 dígitos)")
    for a in d["ausentes"]:
        print(f"  NÃO EXISTE no WhatsApp: {a['nome']} — {a['fone']} (tudo que a casa manda "
              f"para esta pessoa morre no caminho, e o envio registra sucesso)")
    if d["sem_fone"]:
        print(f"  sem telefone no cadastro ({len(d['sem_fone'])}): {', '.join(d['sem_fone'])}")
    print(f"telefones conferidos no WhatsApp: {d['ok']} ok · {len(d['ausentes'])} inexistentes · "
          f"{len(d['malformados'])} malformados · {len(d['sem_fone'])} sem telefone")
    print(f"TOTAL telefones malformados: {len(d['malformados'])}")
    return 1 if d["malformados"] else 0


if __name__ == "__main__":
    sys.exit(main())
