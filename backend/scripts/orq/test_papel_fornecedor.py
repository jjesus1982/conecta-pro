"""Oráculo — papel FORNECEDOR.

Critério de aceite (T6, e é o certo): não é componente verde. É **o Renier perguntar
"Qual cabo?" e o José Luís responder algo útil, sem inventar spec e sem escalar para
humano** — que foi o que ele fez às 15:13:52 de 31/08.

Por isso a parte 4 roda um TURNO DE VERDADE sobre a conversa real, com `notify_owner`
interceptado. `gerar_resposta` não envia nada — ela devolve texto.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fixtures import bloqueado  # noqa: E402
sys.path.insert(0, "/app")
import main_production  # noqa: F401

FALHAS = []
FONE_RENIER = "5592994298002"


def ok(cond, nome, detalhe=""):
    print("  %s %s%s" % ("✅" if cond else "❌", nome, (" — " + detalhe) if detalhe else ""))
    if not cond:
        FALHAS.append(nome)


async def main():
    from core.database import async_session_factory
    from modules.integrations.connectors.whatsapp import agent_service as A

    print("\n== 1. o telefone do fornecedor vira PAPEL ==")
    async with async_session_factory() as db:
        f = await A._fornecedor_do_telefone(db, FONE_RENIER)
        ok(f is not None and "HAWK" in (f or {}).get("name", ""),
           "5592994298002 → HAWK EYE", str((f or {}).get("name")))
        # o nono dígito e o DDI somem e aparecem conforme quem cadastrou
        for variante in ("92994298002", "994298002", "+55 (92) 99429-8002"):
            g = await A._fornecedor_do_telefone(db, variante)
            ok(g is not None, f"variante {variante!r} também resolve")
        ok((await A._fornecedor_do_telefone(db, "5511999999999")) is None,
           "número desconhecido NÃO vira fornecedor")

    print("\n== 2. o contexto carrega a COTAÇÃO com os itens ==")
    ctx = await A._contexto_fornecedor(f)
    ok("HAWKEYE-" in ctx, "traz o número da cotação", ctx.split("\n")[2][:50] if len(ctx.split("\n")) > 2 else "")
    ok("cabo" in ctx.lower(), "traz os ITENS", "sem item, 'qual cabo?' é enigma")
    ok("não invente" in ctx.lower() or "não tem especificação" in ctx.lower(),
       "avisa que item nu não tem spec registrada")
    for proibido in ("cliente", "contrato", "funil"):
        ok(proibido not in ctx.lower(), f"NÃO vaza {proibido}",
           "fornecedor não enxerga o outro lado")

    print("\n== 3. as tools do papel ==")
    t_forn = {(x.get("function") or {}).get("name") for x in A._tools_ativas(False, "fornecedor")}
    t_sdr = {(x.get("function") or {}).get("name") for x in A._tools_ativas(False, "sdr")}
    ok("perguntar_ao_jordan" in t_forn, "fornecedor tem perguntar_ao_jordan")
    ok("registrar_resposta_cotacao" in t_forn, "fornecedor tem registrar_resposta_cotacao")
    ok("perguntar_ao_jordan" not in t_sdr, "CLIENTE não tem as tools de fornecedor",
       "separação por interlocutor")
    ok(not (t_forn & {"consultar_minha_conta", "abrir_ordem_servico", "montar_proposta"}),
       "fornecedor não tem tool de cliente", str(sorted(t_forn)))

    print("\n== 4. 🎯 O TURNO REAL — 'Qual cabo?' na conversa do Renier ==")
    from modules.crm.services import orchestration as _orq
    perguntas, orig = [], _orq.notify_owner

    async def _fake(msg):
        perguntas.append(msg)
        return True

    _orq.notify_owner = _fake
    try:
        # a guarda anti-loop guarda a falha por 5 min: sem limpar, uma rodada anterior de
        # teste faz esta medir o silenciador em vez de medir o agente.
        from core.cache.redis import get_redis
        await (await get_redis()).delete("jl:falha:conv:86")
        texto = await A.gerar_resposta(86)
    finally:
        _orq.notify_owner = orig

    if True:  # sempre: no 402 o agente devolve um texto de FALLBACK, não vazio (medido 06/09)
        # O agente engole a exceção do provedor e responde com frase de contorno; o que
        # denuncia é o registro em `llm_usage`. Sem saldo/cota no provedor a pergunta deste oráculo não tem resposta
        # hoje — é BLOQUEADO, não vermelho (06/09/2026: dias seguidos de "Insufficient
        # Balance" contados como defeito do José Luís).
        from sqlalchemy import text

        from core.database import async_session_factory
        from modules.ai.conversation.services.llm_credit_alert import _e_erro_de_credito
        async with async_session_factory() as db:
            erro = (await db.execute(text(
                "SELECT erro FROM llm_usage WHERE ok = false AND criado_em > now() - "
                "interval '3 minutes' ORDER BY criado_em DESC LIMIT 1"))).scalar()
        if erro and _e_erro_de_credito(erro):
            bloqueado(f"provedor de LLM sem crédito: {erro[:90]}")

    print("     RESPOSTA GERADA:\n     " + str(texto or "«nada»")[:400].replace("\n", "\n     "))
    baixo = (texto or "").lower()
    ok(bool(texto), "gerou resposta")
    ok("chamar alguém da equipe" not in baixo and "me perdi" not in baixo,
       "NÃO escalou para humano nem se perdeu", "era o comportamento das 15:13")
    # não pode inventar especificação
    inventou = [x for x in ("cat6", "cat 6", "cat5e", "3kva", "1500va", "12u", "19u")
                if x in baixo]
    ok(not inventou or bool(perguntas), "não inventou spec do nada",
       f"citou {inventou} — só vale se veio do contexto ou perguntou" if inventou else "")
    ok(bool(perguntas) or "jordan" in baixo or "confirmo" in baixo or "sugir" in baixo
       or "padrão" in baixo or "recomend" in baixo,
       "ou perguntou ao Jordan, ou devolveu a pergunta ao fornecedor",
       f"perguntas ao dono: {len(perguntas)}")
    # 🎯 o critério final: com a spec registrada, ele RESPONDE a spec — não promete responder
    ok("100% cobre" in baixo or "categoria 5" in baixo or "cat 5" in baixo,
       "RESPONDEU a especificação real do cabo",
       "é a spec que está em purchase_quotation_items.specifications")
    ok("1200" in baixo or "9u" in baixo,
       "e a de nobreak/rack também", "o contexto tem, ele usa")

    print("\n%s" % ("TODAS AS CHECAGENS PASSARAM" if not FALHAS
                    else "FALHOU (%d): " % len(FALHAS) + " · ".join(f[:38] for f in FALHAS)))
    if FALHAS:
        raise SystemExit(1)


asyncio.run(main())
