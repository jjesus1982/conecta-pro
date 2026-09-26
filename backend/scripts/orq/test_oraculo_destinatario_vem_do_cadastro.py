"""Prova que mensagem para PESSOA resolve o telefone no cadastro, e que ambíguo RECUSA.

🔴 O QUE ACONTECEU EM 26/09/2026: eu errei o destinatário DUAS VEZES em dez minutos. O passo a
passo do ponto do **JAIR** foi para o **ANTONIO CARLOS VIEIRA**, e o do **EULER** para o
**ANTONIO DINIZ** — nos dois casos porque eu DIGITEI um número que estava no meu contexto de uma
mensagem anterior, em vez de ler o cadastro na hora do envio.

Jordan, depois do segundo: **"tem que ter o padrão"**. Ele está certo, e a lição é estrutural:
o remédio para "errei o número" não é *prestar mais atenção* — é **não ter onde errar**.
Enquanto existir um lugar onde se digita `'5592...'`, alguém digita o errado.

Este oráculo afirma as quatro paredes de `destinatario.py`, e cada uma vem de um erro real desta
casa. **Cada recusa tem a irmã de caminho feliz** — trava que só sabe dizer "não" fica verde
sobre capacidade morta.

  1. nome único → resolve, com o telefone do CADASTRO        (+ caminho feliz)
  2. nome ambíguo → RECUSA                                   ← o erro Jair→Antonio Carlos
  3. telefone malformado → RECUSA e NÃO adivinha              ← a THAYNA, 12 dígitos
  4. `mandar()` não aceita parâmetro de telefone              ← a porta que não pode reabrir
"""

import asyncio
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")

from core.database import async_session_factory  # noqa: E402

falhas: list[str] = []


async def main() -> None:
    from modules.integrations.connectors.whatsapp.destinatario import mandar, resolver

    # 4 — a assinatura não pode ter telefone. Esta é a parede mais barata e a mais importante:
    #     um `telefone=` aqui reabre o buraco inteiro.
    params = set(inspect.signature(mandar).parameters)
    proibidos = {p for p in params if any(t in p.lower() for t in ("fone", "phone", "numero", "jid"))}
    if proibidos:
        falhas.append(f"`mandar()` aceita {sorted(proibidos)} — a porta do erro está aberta")
    else:
        print(f"  ok  `mandar()` não aceita telefone (parâmetros: {sorted(params - {'db'})})")

    async with async_session_factory() as db:
        # 1 — caminho feliz: nome único resolve, e o telefone é o do banco
        alvo = await resolver(db, "JAIR SOARES DA ROCHA")
        if not alvo.get("ok"):
            falhas.append(f"nome completo e único NÃO resolveu: {alvo.get('motivo')} — se nem o "
                          "caminho feliz funciona, as recusas abaixo não provam nada")
        elif len(alvo.get("fone") or "") not in (10, 11):
            falhas.append(f"resolveu com telefone inválido: {alvo.get('fone')!r}")
        else:
            print(f"  ok  nome único resolve: {alvo['nome']} → {alvo['fone']} (do cadastro)")

        # 2 — ⭐ ambíguo RECUSA. Cinco ANTONIO nesta casa; escolher é o defeito.
        amb = await resolver(db, "ANTONIO")
        if amb.get("ok"):
            falhas.append(f"'ANTONIO' resolveu para UMA pessoa ({amb.get('nome')}) — há cinco, e "
                          "escolher sozinho é exatamente o erro Jair→Antonio Carlos")
        elif "AMBÍGUO" not in (amb.get("motivo") or ""):
            falhas.append(f"'ANTONIO' recusou pelo motivo errado: {amb.get('motivo')}")
        else:
            print(f"  ok  ambíguo recusa: {(amb['motivo'])[:74]}…")

        # 3 — telefone malformado recusa, e o motivo diz que NÃO se adivinha
        mal = await resolver(db, "THAYNA RHANNELE")
        if mal.get("ok"):
            falhas.append(f"THAYNA resolveu apesar do telefone de 12 dígitos: {mal.get('fone')!r}")
        elif "malformado" not in (mal.get("motivo") or "").lower():
            # se o cadastro dela foi corrigido, isto deixa de ser o caso de teste e eu digo isso
            print(f"  ⚠️ THAYNA não recusou por telefone: {(mal.get('motivo') or '')[:70]} "
                  "(o cadastro pode ter sido corrigido — confira antes de assumir defeito)")
        else:
            print("  ok  telefone malformado recusa e NÃO adivinha dígito")

        # desconhecido também recusa — controle de que a régua não diz sim para qualquer coisa
        nada = await resolver(db, "NOME_QUE_NUNCA_EXISTIU_9X7")
        if nada.get("ok"):
            falhas.append("nome inventado RESOLVEU — a régua diz sim para qualquer coisa")
        else:
            print("  ok  controle: nome inexistente recusa")

    if falhas:
        for f in falhas:
            print(f"  ❌ {f}")
        print(f"\nTEST destinatario_vem_do_cadastro FAIL ({len(falhas)})")
        sys.exit(1)
    print("\nTEST destinatario_vem_do_cadastro PASS")


if __name__ == "__main__":
    asyncio.run(main())
