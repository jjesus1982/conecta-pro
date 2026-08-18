"""Confere as chaves PIX dos diaristas contra o DICT, pela Asaas.

É o que o app do banco faz e o nosso sistema não fazia: digitar a chave e ver o nome do
titular ANTES de pagar. O `validate_pix_key` do Inter aponta para endpoint que responde
404 e devolve vazio engolindo o erro — nunca validou nada.

⚠️ ESTE SCRIPT NÃO ENVIA DINHEIRO. Não importa `enviar_pix` nem chama `/transfers`:
é só leitura do DICT. Isso é proposital — a garantia tem de estar no código, não numa
promessa minha.

Roda em PRODUÇÃO por padrão, porque o DICT de sandbox só conhece chaves de sandbox e
consultar um CPF real lá devolve 404 sempre. Consulta é leitura: não move saldo.

    ASAAS_API_KEY=$aact_prod_... python scripts/conferir_chaves_pix_asaas.py
    ASAAS_API_KEY=... python scripts/conferir_chaves_pix_asaas.py --competencia 2026-08

O que a saída significa:
    ✅ confere   — o titular bate com o nome cadastrado
    ⚠️ DIVERGE   — a chave existe, mas está em nome de OUTRA pessoa. Olhar antes de pagar.
    ❌ não existe — chave não registrada no DICT. Pagamento falharia.
    ·  não sei   — a consulta falhou. NÃO é o mesmo que chave ruim.
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import re
import sys
import unicodedata
from datetime import date

sys.path[0] = str(pathlib.Path(__file__).resolve().parents[1])

from modules.integrations.banking.adapters.asaas import (  # noqa: E402
    AsaasAdapter,
    ChavePixInvalida,
)
from modules.integrations.banking.adapters.base import BankCredentials  # noqa: E402


def _normal(s: str) -> str:
    """Sem acento, sem pontuação, maiúsculo — para comparar nome do DICT com o cadastro."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z ]", " ", s.upper())


def _mesmo_titular(cadastro: str, dict_: str) -> bool:
    """Compara por PALAVRAS, não por igualdade.

    "MARIA DA CONCEICAO SILVA" no cadastro e "MARIA CONCEICAO SILVA" no DICT são a mesma
    pessoa; exigir string idêntica encheria a tela de divergência falsa e ninguém olharia
    mais. Exige o primeiro nome e o último sobrenome iguais.
    """
    a, b = _normal(cadastro).split(), _normal(dict_).split()
    if not a or not b:
        return False
    return a[0] == b[0] and a[-1] == b[-1]


#: Teto MEDIDO no endpoint de consulta: 20 chamadas por janela (`RateLimit-Limit: 20`).
#: 3,5s entre consultas mantém abaixo disso sem depender de sorte.
PAUSA = 3.5


async def _consultar_com_folego(ad, chave: str, tentativas: int = 3):
    """Consulta respeitando o teto. Ao levar 429, espera o `RateLimit-Reset` e repete.

    Sem isso, uma lista de 28 pessoas vira 8 conferidas e 20 "não sei" — e "não sei" por
    pressa nossa é indistinguível de "não sei" por chave problemática. O resultado ficaria
    inútil justamente onde precisa ser confiável.
    """
    from modules.integrations.banking.adapters.asaas import AsaasError

    for n in range(1, tentativas + 1):
        try:
            return await ad.validate_pix_key(chave)
        except AsaasError as e:
            if e.status != 429 or n == tentativas:
                raise
            espera = (e.corpo or {}).get("reset_s", 30)
            espera = espera + 2 if espera > 0 else 30
            print(f"    (limite da Asaas atingido — esperando {espera}s)", flush=True)
            await asyncio.sleep(espera)
    return None


async def main(competencia: str) -> None:
    from sqlalchemy import text

    from core.database.session import SyncSessionLocal

    chave = (os.getenv("ASAAS_API_KEY") or "").strip()
    if not chave:
        sys.exit("ASAAS_API_KEY não definida.")
    ambiente = "production" if chave.startswith("$aact_prod_") else "sandbox"
    if ambiente == "sandbox":
        print("⚠️  chave de SANDBOX: o DICT de sandbox não conhece CPF real, tudo dará "
              "'não existe'. Para conferência de verdade, use a chave de produção.\n")

    ano, mes = (int(x) for x in competencia.split("-"))
    ini = date(ano, mes, 1)
    fim = date(ano + (mes == 12), (mes % 12) + 1, 1)

    db = SyncSessionLocal()
    pessoas = db.execute(text("""
        SELECT d.nome, coalesce(d.cpf,'') cpf, nullif(d.pix,'') pix,
               count(*) dias, sum(l.valor)::numeric(12,2) total
          FROM diaria_lancamentos l
          JOIN diaria_diaristas d ON d.id = l.diarista_id
         WHERE l.data >= :i AND l.data < :f AND l.status = 'lancado'
         GROUP BY 1,2,3 ORDER BY 1
    """), {"i": ini, "f": fim}).mappings().all()
    db.close()

    if not pessoas:
        sys.exit(f"nenhum lançamento de diária em {competencia}.")

    ad = AsaasAdapter(BankCredentials(client_id="conecta", client_secret=chave,
                                      environment=ambiente))
    print(f"Conferindo {len(pessoas)} chave(s) PIX — competência {competencia} "
          f"({ambiente})\n")

    placar = {"ok": 0, "diverge": 0, "inexistente": 0, "sem_chave": 0, "nao_sei": 0}
    for i, p in enumerate(pessoas):
        # A pausa vai ANTES da consulta, não depois do sucesso: chave inexistente e
        # consulta falha também gastam uma chamada do teto de 20/janela.
        if i:
            await asyncio.sleep(PAUSA)
        rot = f"  {p['nome'][:32]:<32} R$ {p['total']:>9} ({p['dias']}d)"
        if not p["pix"]:
            placar["sem_chave"] += 1
            print(f"{rot}  ⛔ SEM CHAVE PIX cadastrada")
            continue
        try:
            d = await _consultar_com_folego(ad, p["pix"])
        except ChavePixInvalida as e:
            placar["inexistente"] += 1
            print(f"{rot}  ❌ {e}")
            continue
        if not d or not d.get("titular"):
            placar["nao_sei"] += 1
            print(f"{rot}  ·  não sei (consulta falhou) — NÃO é o mesmo que chave ruim")
            continue
        if _mesmo_titular(p["nome"], d["titular"]):
            placar["ok"] += 1
            print(f"{rot}  ✅ {d['titular']} · {d['banco']}")
        else:
            placar["diverge"] += 1
            print(f"{rot}  ⚠️  DIVERGE — chave está em nome de {d['titular']} "
                  f"({d['documento']}) · {d['banco']}")

    print(f"\n  {placar['ok']} conferem · {placar['diverge']} DIVERGEM · "
          f"{placar['inexistente']} não existem · {placar['sem_chave']} sem chave · "
          f"{placar['nao_sei']} não sei")
    if placar["diverge"] or placar["inexistente"]:
        print("\n  ⚠️  Resolver as divergências ANTES de pagar. Chave em nome de outra "
              "pessoa paga a outra pessoa — e PIX não volta.")


if __name__ == "__main__":
    comp = "2026-07"
    if "--competencia" in sys.argv:
        comp = sys.argv[sys.argv.index("--competencia") + 1]
    asyncio.run(main(comp))
