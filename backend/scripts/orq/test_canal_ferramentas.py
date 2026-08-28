#!/usr/bin/env python3
"""Oráculo do ESCOPO DE CANAL — uma ferramenta, duas caras, sem vazamento.

Decisão do Jordan (27/08/2026): unificar José Luís e Bartolo numa ferramenta só. O que
NÃO se unifica é quem pode chamar o quê:

    canal `interno`  → usuário AUTENTICADO do ERP, com RBAC por módulo
    canal `publico`  → CLIENTE no WhatsApp, identificado pelo TELEFONE da conversa

Uma tool de forecast, margem ou MRR no canal público é estranho lendo o funil da empresa.
Esta casa já cometeu esse erro uma vez: `resumo_financeiro` devolveu MRR sem identidade
porque o grupo dele era "comercial".

⭐ CANAL ≠ TRANSPORTE, e confundir os dois quase custou caro. A primeira versão da ponte
dava ao Jordan-no-WhatsApp `tools_do_canal("interno")` inteiro — 12 tools do Bartolo do
chat, cujo handler espera (db, user, scope) e não `conversation_id`. Todas quebrariam na
execução. Canal diz QUEM PERGUNTA; transporte diz QUEM SABE EXECUTAR.

Seis invariantes:
  1. toda tool do registro declara pelo menos um canal VÁLIDO
  2. tool nova nasce `interno` (fail-closed) — canal público exige declaração
  3. NENHUMA tool está nos dois canais sem alguém ter escrito isso de propósito
  4. o canal público NÃO contém tool de dinheiro/estratégia (lista negra explícita)
  5. EQUIVALÊNCIA: a lista derivada do registro é IDÊNTICA à lista local, nos dois
     estados da flag de cotação e nos dois papéis (owner e externo)
  6. `papel` só FILTRA o conjunto externo — nunca acrescenta

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \\
        /app/scripts/orq/test_canal_ferramentas.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, "/app")

#: O que NUNCA pode aparecer para um cliente, por assunto. Lista de nomes E de radicais —
#: nome novo com "forecast" dentro cai aqui sem ninguém precisar lembrar de atualizar.
_PROIBIDO_NO_PUBLICO = (
    "forecast", "margem", "mrr", "funil", "pipeline", "rentabilidade", "runway",
    "inadimplencia", "folha", "holerite", "salario", "custo", "lucro", "dre",
    "extrato", "saldo", "pagamento", "pagar", "cobranca", "meta_", "panorama",
)


def main() -> int:
    import modules.ai.conversation.services.orquestrador.tools_acao_crm  # noqa: F401
    import modules.ai.conversation.services.orquestrador.tools_comercial_doc  # noqa: F401
    from modules.ai.conversation.services.orquestrador.tool_registry import (
        VALID_CANAIS, _REGISTRY, ToolDef, tools_do_canal,
    )
    from modules.integrations.connectors.whatsapp import agent_service as A

    falhas: list[str] = []

    # 1 · todo mundo declara canal válido
    for t in _REGISTRY.values():
        if not t.canais or set(t.canais) - VALID_CANAIS:
            falhas.append(f"tool {t.name!r} com canal inválido/ausente: {t.canais!r}")

    # 2 · fail-closed: o default é interno
    async def _nada(**_kw):
        return {}

    padrao = ToolDef("zz_probe_canal", "crm", "x",
                     {"type": "object", "properties": {}}, _nada)
    if padrao.canais != ("interno",):
        falhas.append(f"o DEFAULT de canal virou {padrao.canais!r} — tool nova tem de "
                      f"nascer invisível ao cliente")

    # 3 · ninguém nos dois canais por acidente
    ambos = [t.name for t in _REGISTRY.values() if len(set(t.canais)) > 1]
    if ambos:
        falhas.append(f"tools em MAIS DE UM canal (revisar uma a uma): {ambos}")

    # 4 · o canal público não vê dinheiro nem estratégia
    for t in tools_do_canal("publico"):
        achado = [p for p in _PROIBIDO_NO_PUBLICO if p in t.name.lower()]
        if achado:
            falhas.append(f"tool {t.name!r} está no canal PÚBLICO e casa com "
                          f"{achado} — cliente não vê isso")

    # 5 · EQUIVALÊNCIA — a derivação do registro não pode mudar o que o agente oferece.
    #     É esta invariante que apanhou as duas regressões da primeira versão da ponte.
    def nomes(lista) -> list[str]:
        return sorted((x.get("function") or {}).get("name") for x in lista)

    antes = os.environ.get("AGENT_COTA_EM_CHAT")
    try:
        for flag in ("false", "true"):
            os.environ["AGENT_COTA_EM_CHAT"] = flag
            local = nomes(A.TOOLS + A.TOOLS_COTACAO if A._cota_em_chat() else A.TOOLS)
            derivado = nomes(A._tools_ativas(owner=False))
            if local != derivado:
                falhas.append(
                    f"cota={flag}: lista EXTERNA derivada difere da local — "
                    f"só numa delas: {sorted(set(local) ^ set(derivado))}")
        # ⚠️ 28/08/2026 — a invariante mudou de forma, não de rigor. O conjunto do dono
        # deixou de ser SÓ o registro: ganhou duas adições deliberadas, cada uma com o seu
        # construtor nomeado — `_leitura_campo()` (consultar_comercial) e
        # `_cotacao_do_dono()` (simular_preco, montar_proposta). Elas ficam FORA do registro
        # de propósito: registrá-las faria aparecerem também no Bartolo, que já tem as
        # capacidades por outro caminho.
        #
        # A comparação passa a ser contra `registro ∪ adições NOMEADAS`, e não contra um
        # "ignore as diferenças": tool que entrar na lista do dono sem passar por um desses
        # dois construtores continua derrubando este teste. Afrouxar seria trocar a parede
        # por um aviso.
        #
        # ⭐ E registro o que este teste apanhou: a etapa 1 (consultar_comercial) foi ao ar
        # com ele VERMELHO porque eu rodei os oráculos irmãos que me lembrei, não os que
        # tocavam o mesmo arquivo. `git grep` do símbolo alterado teria dito quais eram.
        adicoes = nomes(A._extras_do_dono())   # construtor ÚNICO: tool nova entra sozinha
        local_i = sorted(set(nomes(A.MANAGER_TOOLS)) | set(adicoes))
        deriv_i = nomes(A._tools_ativas(owner=True))
        if local_i != deriv_i:
            falhas.append(f"lista INTERNA derivada difere da local — só numa delas: "
                          f"{sorted(set(local_i) ^ set(deriv_i))[:8]}")
    finally:
        if antes is None:
            os.environ.pop("AGENT_COTA_EM_CHAT", None)
        else:
            os.environ["AGENT_COTA_EM_CHAT"] = antes

    # 6 · papel só filtra
    externo = set(nomes(A._tools_ativas(owner=False)))
    for papel in A._PAPEIS:
        do_papel = set(nomes(A._tools_ativas(owner=False, papel=papel)))
        if not do_papel <= externo:
            falhas.append(f"papel {papel!r} ACRESCENTA tool fora do conjunto externo: "
                          f"{sorted(do_papel - externo)}")

    if falhas:
        for f in falhas:
            print(f"FALHOU: {f}")
        return 1
    pub, intr = len(tools_do_canal("publico")), len(tools_do_canal("interno"))
    print(f"OK canal_ferramentas: 6/6 — {pub} tool(s) no canal público e {intr} no "
          f"interno, nenhuma nos dois; tool nova nasce interna; nada de dinheiro ou "
          f"estratégia no público; e a lista derivada do registro é IDÊNTICA à local "
          f"nos dois estados da flag e nos dois papéis.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
