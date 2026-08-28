"""Oráculo — ETAPA 1: a leitura do comercial no WhatsApp do dono (28/08/2026).

O que este oráculo defende, em ordem de gravidade:

1. NENHUMA AÇÃO VAZA. A etapa 1 é leitura. Se um nome de `agir_crm` entrar em
   `_CONSULTAS_CAMPO`, o Jordan grava no CRM de dentro de um corredor sem aprovação
   nenhuma — que é exatamente o que a etapa 2 existe para decidir com calma.
2. O CLIENTE NÃO VÊ. `consultar_comercial` é do dono; aparecer no conjunto público
   entregaria catálogo, contratos e propostas a um número anônimo.
3. SEM FANTASMA. Consulta listada que não existe no Bartolo vira tool que promete e
   recusa — pior que não existir, porque o modelo tenta e o Jordan espera.
4. A ALLOW-LIST MANDA. Consulta real do Bartolo que não foi liberada tem de ser recusada
   pelo executor, não só ausente do schema — schema é sugestão, executor é parede.
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, "/app")
os.environ.setdefault("AGENT_VISITA_EMAIL_INTERNO", "jjesus@conectamais.pro")

FALHAS: list[str] = []


def checar(cond: bool, titulo: str, detalhe: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FALHA'} · {titulo}{(' — ' + detalhe) if detalhe else ''}")
    if not cond:
        FALHAS.append(titulo)


async def main() -> int:
    # ⭐ ORDEM IMPORTA, e é a lição de 28/08/2026: a 1ª versão deste oráculo importava
    # `tools_read_crm` no topo e por isso PASSAVA 8/8 com a capacidade DESLIGADA em
    # produção. Quem popula o registro é esse import — fazendo-o aqui, o oráculo criava
    # o mundo que queria medir. O servidor não o fazia, e o José Luís respondeu ao Jordan
    # "não tenho o preço aqui no painel" com o catálogo a um passo.
    #
    # Então: primeiro `main_production` (o MESMO grafo do servidor), e a checagem de
    # "o servidor enxerga" acontece ANTES de qualquer import do orquestrador.
    import main_production  # noqa: F401,PLC0415

    from modules.integrations.connectors.whatsapp import agent_service as _A0
    servidor_ve = "consultar_comercial" in {
        (spec.get("function") or {}).get("name") for spec in _A0._tools_ativas(owner=True)}
    checar(servidor_ve, "O SERVIDOR enxerga consultar_comercial (grafo real de import)",
           "" if servidor_ve else "a tool existe no código e NÃO está no ar — "
                                  "`_READ_OPS['crm']` vazio neste grafo")

    from modules.ai.conversation.services.orquestrador import (  # noqa: F401
        tools_acao_crm, tools_read_crm,
    )
    from modules.ai.conversation.services.orquestrador import agir_dispatcher as AD
    from modules.ai.conversation.services.orquestrador import read_dispatcher as RD
    from modules.integrations.connectors.whatsapp import agent_service as A

    reads = set(RD._READ_OPS.get("crm") or {})
    acoes = set(next((d for d in (getattr(AD, a, None) for a in dir(AD))
                      if isinstance(d, dict) and d.get("crm")), {}).get("crm") or {})
    print(f"\n  registro do Bartolo: {len(reads)} consultas · {len(acoes)} ações\n")

    # ── 1. nenhuma ação na allow-list ──────────────────────────────────────────
    vazou = sorted(set(A._CONSULTAS_CAMPO) & acoes)
    checar(not vazou, "nenhuma AÇÃO na allow-list de campo",
           f"vazaram: {', '.join(vazou)}" if vazou else f"{len(A._CONSULTAS_CAMPO)} consultas, 0 ações")

    # ── 2. sem fantasma: tudo que prometo existe ───────────────────────────────
    fantasmas = sorted(set(A._CONSULTAS_CAMPO) - reads)
    checar(not fantasmas, "toda consulta liberada existe no Bartolo",
           f"inexistentes: {', '.join(fantasmas)}" if fantasmas else "")

    # ── 3. aparece para o dono, não para o cliente ─────────────────────────────
    def nomes(schemas):
        return {(s.get("function") or {}).get("name") for s in schemas}

    dono = nomes(A._tools_ativas(owner=True))
    cliente = nomes(A._tools_ativas(owner=False))
    checar("consultar_comercial" in dono, "o DONO enxerga consultar_comercial")
    checar("consultar_comercial" not in cliente,
           "o CLIENTE não enxerga consultar_comercial",
           "vazou para o canal público!" if "consultar_comercial" in cliente else "")

    # ── 4. o enum do schema == a allow-list, sem sobra ─────────────────────────
    spec = next((s for s in A._tools_ativas(owner=True)
                 if (s.get("function") or {}).get("name") == "consultar_comercial"), None)
    if spec is None:
        checar(False, "schema de consultar_comercial montado")
    else:
        enum = set((spec["function"]["parameters"]["properties"]["consulta"]).get("enum") or [])
        checar(enum <= set(A._CONSULTAS_CAMPO), "o enum não excede a allow-list",
               f"sobra: {sorted(enum - set(A._CONSULTAS_CAMPO))}")
        checar(not (enum & acoes), "o enum não contém ação")

    # ── 5. o EXECUTOR recusa consulta fora da lista (schema é sugestão) ────────
    fora = sorted(reads - set(A._CONSULTAS_CAMPO))
    if fora:
        r = await A._exec_manager_tool("consultar_comercial", {"consulta": fora[0]}, 1)
        checar(r.get("status") == "recusado",
               f"executor RECUSA consulta não liberada ({fora[0]})", str(r)[:90])
    r2 = await A._exec_manager_tool("consultar_comercial", {"consulta": "apagar_tudo"}, 1)
    checar(r2.get("status") == "recusado", "executor recusa consulta inventada", str(r2)[:90])

    # ── 5b. CAMINHO FELIZ: a consulta liberada RESPONDE ───────────────────────
    # ⚠️ A 1ª versão só testava RECUSA — e recusa retorna antes de tocar no dispatcher.
    # Por isso ela passou 8/8 enquanto o executor respondia "consultar_crm não está
    # registrado neste processo" para toda consulta válida. Testar só o "não" prova que
    # a porta fecha, nunca que ela abre.
    ok = await A._exec_manager_tool(
        "consultar_comercial", {"consulta": "catalogo", "filtros": {"busca": "bullet"}}, 1)
    checar(isinstance(ok, dict) and not ok.get("erro"),
           "consulta LIBERADA responde de verdade (catalogo/bullet)", str(ok)[:100])

    # ── 6. peso do prompt: o número que o T6 pediu ─────────────────────────────
    def peso(o):
        return len(json.dumps(o, ensure_ascii=False)) // 4

    sem = [s for s in A._tools_ativas(owner=True)
           if (s.get("function") or {}).get("name") != "consultar_comercial"]
    com = A._tools_ativas(owner=True)
    print(f"\n  prompt do José Luís: ~{peso(sem)} → ~{peso(com)} tokens "
          f"(+{peso(com) - peso(sem)}) · {len(sem)} → {len(com)} tools")

    print()
    if FALHAS:
        print(f"  ❌ {len(FALHAS)} FALHA(S): {', '.join(FALHAS)}")
        return 1
    print("  ✅ etapa 1 íntegra: leitura é leitura, e o cliente não vê.")
    return 0


sys.exit(asyncio.run(main()))
