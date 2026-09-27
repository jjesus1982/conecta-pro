"""O Orlailson lança diária da RUA, pelo WhatsApp — e o VT+VR cai no financeiro do Jordan.

🔴 POR QUE EXISTE (27/09/2026). Jordan: *"orlailson lança diária, eu faço os pagamentos do VT e
VR. Quando ele lançar as diárias, ele pode dar os nomes pro José Luís no whatsapp, e o Hermes
entrar em ação e fazer, e chega pra mim, eu faço o pagamento, tudo indo pro sistema"*.

⭐ E a razão, na frase dele: **"na rua todo mundo usa o whatsapp, mas só abre o sistema quando
tá no escritório"**. É a tese inteira do agente nesta casa — o trabalho acontece na rua e o
registro espera o escritório. Entre os dois há um atraso que vira dado faltando.

## A máquina JÁ EXISTIA — faltava a porta

`diarias_service.lancar()` cria o lançamento, acha o preço por função e turno, e **programa o
VT+VR (R$32) daquele dia no Financeiro** para o Jordan conferir e pagar em lote. `excluir`
cancela em cascata. Nada disso precisou ser escrito: estava pronto e só a tela abria.

É o padrão que mais se repetiu em 27/09 — `substitutions` com zero linhas, `tentativa_falhou`
com zero linhas, a análise de foto que não chegava à tabela do vigia. **A dívida quase nunca é
código faltando; é código sem porta.**

## ⚠️ AS PAREDES, e por que cada uma existe

1. **Só quem lança diária lança.** `users.role` gerencial + conta ativa. Diária é dinheiro
   saindo; o nome de quem pediu tem de estar no registro.
2. **Nome ambíguo RECUSA.** Cinco ANTONIO nesta casa. Lançar diária para a pessoa errada é
   pagar a pessoa errada — e o erro só aparece no extrato.
3. **Diarista não cadastrado NÃO é inventado.** O cadastro exige CPF e PIX, e nenhum dos dois
   se deduz de um nome no WhatsApp. Devolve o que falta para um humano cadastrar.
4. **Não paga.** Cria o lançamento e deixa o VT+VR `a_revisar` no Financeiro. O pagamento
   continua sendo ato do Jordan, com o gate de sempre — dinheiro que sai nunca é happy-path.
5. **Confirma com VALOR.** A resposta diz quanto ficou cada diária e quanto some no VT+VR, para
   quem mandou poder desmentir na hora, não no fim do mês.
"""

from __future__ import annotations

import logging
from datetime import date as _date
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)

#: Quem pode lançar diária. Mesma régua da Central — diária é dinheiro.
ROLES_LANCA = ("admin", "gerente_operacional")

_SQL_AUTORIDADE = """
SELECT u.id::text AS user_id, u.role, e.nome
  FROM users u JOIN employees e ON e.id = u.employee_id
 WHERE u.is_active AND u.role = ANY(:roles) AND e.id = CAST(:e AS uuid)
"""

#: ⚠️ Busca por NOME, acento-insensível, sobre `diaria_diaristas` — que é tabela À PARTE de
#: `employees`. Medido em 26/09: dos 38 diaristas, 31 casam com `employees` por CPF e 7 não
#: existem lá. Procurar em `employees` acharia funcionário e lançaria diária para quem é CLT.
_SQL_DIARISTA = """
SELECT id, nome, cpf, coalesce(nullif(pix,''), '') AS pix, ativo
  FROM diaria_diaristas
 WHERE upper(translate(nome, 'ÁÀÂÃÉÊÍÓÔÕÚÇ', 'AAAAEEIOOOUC'))
       LIKE '%' || upper(translate(:q, 'ÁÀÂÃÉÊÍÓÔÕÚÇ', 'AAAAEEIOOOUC')) || '%'
"""


async def _achar_diarista(db, nome: str) -> dict[str, Any]:
    """Um diarista, ou a recusa dizendo por quê. Ambíguo nunca escolhe."""
    q = (nome or "").strip()
    if len(q) < 3:
        return {"ok": False, "motivo": f"«{q}» é curto demais para eu ter certeza de quem é"}
    linhas = (await db.execute(text(_SQL_DIARISTA), {"q": q})).mappings().all()
    if not linhas:
        return {"ok": False, "nao_cadastrado": True,
                "motivo": (f"«{q}» não está no cadastro de diaristas. Para cadastrar preciso do "
                           f"CPF e da chave PIX — não dá para deduzir nenhum dos dois do nome.")}
    if len(linhas) > 1:
        nomes = ", ".join(r["nome"] for r in linhas[:5])
        return {"ok": False, "motivo": (f"AMBÍGUO — «{q}» casa com {len(linhas)}: {nomes}. "
                                        f"Me diga o nome completo.")}
    r = linhas[0]
    if not r["ativo"]:
        return {"ok": False, "motivo": f"{r['nome']} está INATIVO no cadastro de diaristas"}
    return {"ok": True, "id": int(r["id"]), "nome": r["nome"],
            "tem_pix": bool(r["pix"]), "cpf": r["cpf"]}


async def lancar_varios(db, *, quem_pediu_employee_id: str | None, nomes: list[str],
                        posto: str, funcao: str = "AGENTE DE PORTARIA",
                        turno: str | None = None, data: str | None = None,
                        observacao: str | None = None) -> dict[str, Any]:
    """Lança a diária de vários nomes de uma vez e devolve o que dizer a quem pediu.

    ⭐ VÁRIOS DE UMA VEZ porque é assim que a pessoa fala: *"lança diária pro Erlon, pro Edvan
    e pro Jair hoje no Green Hills"*. Pedir um por vez transformaria uma frase em três
    conversas, e é exatamente a fricção que faz o registro esperar o escritório.

    ⚠️ Um nome que falha NÃO derruba os outros: cada um volta com o seu próprio desfecho. Meio
    lote lançado e dito é melhor que lote inteiro perdido por causa de um nome torto.
    """
    from modules.operacional.diaristas import diarias_service as _ds

    # 1 — autoridade
    if not quem_pediu_employee_id:
        return {"ok": False, "motivo": "não sei quem está pedindo — diária é dinheiro e o "
                                       "registro precisa do nome de quem mandou"}
    aut = (await db.execute(text(_SQL_AUTORIDADE),
                            {"roles": list(ROLES_LANCA),
                             "e": quem_pediu_employee_id})).mappings().first()
    if not aut:
        return {"ok": False, "sem_autoridade": True,
                "motivo": ("anotei, mas quem lança diária é a supervisão — vou levar o pedido a "
                           "eles em vez de lançar por conta")}

    dia = (data or "").strip() or _date.today().isoformat()
    try:
        _date.fromisoformat(dia)
    except ValueError:
        return {"ok": False, "motivo": f"«{data}» não é uma data que eu entenda (use AAAA-MM-DD)"}

    feitos, falharam = [], []
    for nome in [n for n in (nomes or []) if str(n).strip()]:
        achado = await _achar_diarista(db, str(nome))
        if not achado.get("ok"):
            falharam.append({"nome": nome, "motivo": achado["motivo"],
                             "nao_cadastrado": achado.get("nao_cadastrado", False)})
            continue
        try:
            r = await _ds.lancar(db, data=dia, diarista_id=achado["id"], funcao=funcao,
                                 posto=posto, turno=turno,
                                 observacao=(observacao or
                                             f"Lançado por {aut['nome']} via José Luís (WhatsApp)"),
                                 user_id=aut["user_id"])
        except Exception as exc:  # noqa: BLE001
            logger.error("diaria_por_whatsapp: %s falhou — %s", achado["nome"], exc, exc_info=True)
            falharam.append({"nome": achado["nome"], "motivo": f"erro ao lançar: {str(exc)[:120]}"})
            continue
        if not r.get("ok"):
            falharam.append({"nome": achado["nome"], "motivo": r.get("mensagem") or "recusado"})
            continue
        feitos.append({"nome": achado["nome"], "id": r["id"], "valor": r["valor"],
                       "turno": r.get("turno"), "tem_pix": achado["tem_pix"],
                       "vt_vr": r.get("vt_vr_enviado_financeiro", False)})

    total = sum(f["valor"] or 0 for f in feitos)
    sem_pix = [f["nome"] for f in feitos if not f["tem_pix"]]
    logger.info("diaria_por_whatsapp: %s lançou %s diária(s) em %s (%s), %s falha(s)",
                aut["nome"], len(feitos), posto, dia, len(falharam))

    partes = []
    if feitos:
        linhas = "\n".join(f"  • {f['nome']} — R$ {f['valor']:.2f}" for f in feitos)
        partes.append(f"✅ *{len(feitos)} diária(s)* lançada(s) em *{posto}* ({dia}):\n{linhas}\n"
                      f"*Total: R$ {total:.2f}*")
        if any(f["vt_vr"] for f in feitos):
            # ⭐ Dizer que o VT+VR FOI programado é o que fecha o ciclo com o Jordan: ele sabe
            # que tem algo esperando ele, sem ninguém avisar à mão.
            partes.append("💳 O *VT+VR (R$32/dia)* já foi para o Financeiro, aguardando o "
                          "Jordan conferir e pagar.")
        if sem_pix:
            # ⚠️ Sem PIX o pagamento trava lá na frente, e o lugar barato de resolver é agora.
            partes.append(f"⚠️ *Sem chave PIX no cadastro:* {', '.join(sem_pix)} — o pagamento "
                          f"vai travar. Me manda a chave que eu registro.")
    for f in falharam:
        partes.append(f"❌ *{f['nome']}*: {f['motivo']}")

    return {"ok": bool(feitos), "lancados": len(feitos), "falharam": len(falharam),
            "total": total, "dia": dia, "posto": posto, "por": aut["nome"],
            "sem_pix": sem_pix, "detalhe": feitos, "erros": falharam,
            "msg": "\n\n".join(partes) or "não consegui lançar nenhuma",
            "diga_a_pessoa": ("Confirme o TOTAL e os nomes — é o que permite ela desmentir na "
                              "hora, não no fim do mês. E NUNCA diga que pagou: o pagamento é "
                              "do Jordan, isto só lança.")}
