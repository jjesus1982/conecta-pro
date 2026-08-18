"""Prova a integração Asaas contra a API de verdade, em SANDBOX.

Roda os degraus na ordem em que cada um depende do anterior. Se um falha, para —
não adianta testar envio se a autenticação não passou.

    1. saldo              → prova que a chave autentica
    2. consulta de chave  → prova o que motivou a Asaas entrar (ver titular antes de pagar)
    3. envio de R$0,01    → só com --enviar, e só em sandbox
    4. status do envio    → prova que sabemos ler o resultado

Uso (a chave NUNCA vai como argumento, para não ficar no histórico do shell):

    ASAAS_API_KEY=$aact_hmlg_... python scripts/provar_asaas_sandbox.py
    ASAAS_API_KEY=$aact_hmlg_... python scripts/provar_asaas_sandbox.py --enviar

⚠️ Recusa chave de produção (`$aact_prod_`) de propósito. Este script existe para
provar a integração sem mover dinheiro real.
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys

# `tests/modules/` e afins mascaram o pacote real quando se roda por caminho;
# a raiz do backend tem de estar no lugar da pasta do script.
sys.path[0] = str(pathlib.Path(__file__).resolve().parents[1])

from modules.integrations.banking.adapters.asaas import (  # noqa: E402
    AsaasError,
    AsaasAdapter,
    ChavePixInvalida,
)
from modules.integrations.banking.adapters.base import BankCredentials  # noqa: E402

# CNPJ da Patrimonial — chave que sabemos existir, para a consulta ter resposta
# conferível. Em sandbox o DICT é fictício, então "não encontrada" aqui é resultado
# legítimo: o que se prova é que a CHAMADA funciona e distingue os casos.
CHAVE_DE_PROVA = "66014833000110"


def _chave() -> str:
    k = (os.getenv("ASAAS_API_KEY") or "").strip()
    if not k:
        sys.exit("ASAAS_API_KEY não definida. Rode: ASAAS_API_KEY=... python este_script.py")
    if k.startswith("$aact_prod_"):
        sys.exit("RECUSADO: essa é a chave de PRODUÇÃO. Este script é só de sandbox.")
    if not k.startswith("$aact_"):
        print(f"⚠️  a chave não começa com $aact_ — pode ser o Wallet ID, não a chave de API")
    return k


async def main(enviar: bool) -> None:
    ad = AsaasAdapter(BankCredentials(client_id="conecta", client_secret=_chave(),
                                      environment="sandbox"))

    print("1. saldo (prova a autenticação)")
    saldo = await ad.get_balance()
    print(f"   disponível R$ {saldo.available}")

    # 2a. chave que EXISTE. Criamos uma EVP na própria conta de sandbox, porque o DICT
    # de sandbox só conhece chaves de sandbox — consultar um CPF real ali dá 404 sempre,
    # e um teste que só sabe dizer "não achei" não prova que a consulta funciona.
    print("\n2a. consulta de chave que EXISTE (EVP desta conta)")
    async with ad._client() as cli:
        # Reusa a chave que já existe. Criar sempre dá 400 no segundo teste: há limite
        # de chaves por conta, e rodar a prova duas vezes não pode quebrar.
        r = await cli.get("/pix/addressKeys", headers=ad._headers())
        r.raise_for_status()
        ativas = [k for k in (r.json().get("data") or []) if k.get("status") == "ACTIVE"]
        if not ativas:
            r = await cli.post("/pix/addressKeys", headers=ad._headers(), json={"type": "EVP"})
            r.raise_for_status()
            ativas = [r.json()]
    minha = ativas[0]["key"]
    dono = await ad.validate_pix_key(minha)
    if not dono or not dono.get("titular"):
        sys.exit(f"   ❌ consulta não devolveu o titular: {dono}")
    print(f"   titular: {dono['titular']}  ·  doc: {dono['documento']}")
    print(f"   banco:   {dono['banco']} (código {dono['banco_codigo']})")

    # 2b. chave que NÃO existe. O caso que precisa ser DIFERENTE do de cima — e
    # diferente também de "a consulta falhou".
    print(f"\n2b. consulta de chave que NÃO existe — {CHAVE_DE_PROVA}")
    try:
        outro = await ad.validate_pix_key(CHAVE_DE_PROVA)
        print(f"   ⚠️  devolveu {outro!r} — esperado ChavePixInvalida ou None")
    except ChavePixInvalida as e:
        print(f"   recusada corretamente: {e}")

    if not enviar:
        print("\n3-4. envio: pulado (rode com --enviar para provar)")
        return

    # Envia para a chave criada em 2a — a própria conta. Mandar para CHAVE_DE_PROVA
    # falharia por chave inexistente e não provaria nada sobre o envio.
    print("\n3. envio de R$ 0,01")
    ref = "prova-sandbox-001"
    env = await ad.enviar_pix(chave=minha, valor="0.01",
                              referencia=ref, descricao="prova de integração")
    print(f"   id {env.get('id')}  ·  status {env.get('status')}")

    print("\n4. status")
    st = await ad.get_payment_status(env["id"])
    print(f"   {st}")


if __name__ == "__main__":
    try:
        asyncio.run(main("--enviar" in sys.argv))
    except AsaasError as e:
        if e.status == 401:
            # 401 é diferente de 403/404: a chamada CHEGOU e a credencial foi recusada.
            sys.exit("\n❌ 401 — a Asaas recusou a credencial.\n"
                     "   A chave de sandbox começa com $aact_hmlg_ e se gera em\n"
                     "   sandbox.asaas.com → Integrações → Chave de API.\n"
                     "   Wallet ID (o UUID) NÃO autentica: serve para receber split.")
        raise
