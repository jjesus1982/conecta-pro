"""Oráculo balde B: dashboards ai-command-center/agentes/consultor refletem as funções REAIS
da camada cognitiva (command_center/panorama), não casca. Roda no container."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# As telas do operacional foram agrupadas em abas: o slug de topo virou stub
# `{"type":"redirect","groupRef":…}` e a tela real é aba do grupo. Ler `scr[slug]`
# direto encontra o stub e acusa "não é dash/tabela/form" sobre tela que está lá.
# Foi o que derrubou 6 oráculos na varredura de 12/08 às 05:00.
from _fixtures import tela  # noqa: E402

from sqlalchemy import text

from core.database import async_session_factory
from modules.operacional.ai.controller import command_center
from modules.operacional.controllers.redesign_builders.operacional import build
from modules.operacional.services import consultor_coo_service as coo


def _kpi(scr, label):
    for k in scr.get("kpis", []):
        if k.get("l") == label:
            return k.get("v")
    return None


async def main() -> None:
    async with async_session_factory() as db:
        cc = await command_center(None, db)
        pan = await coo.panorama(db)
        scr = await build(db)
        col = int((await db.execute(text("SELECT count(*) FROM employees WHERE status='ativo'"))).scalar() or 0)

        acc = tela(scr, "ai-command-center")
        assert acc and acc.get("type") == "dash", "ai-command-center não é dash"
        assert _kpi(acc, "Efetivo ativo") == str(cc["overview"]["agentes_ativos"]) == str(col), \
            f"AICC efetivo {_kpi(acc,'Efetivo ativo')} != cc {cc['overview']['agentes_ativos']} / banco {col}"
        print(f"OK ai-command-center: efetivo={col}, cobertura={_kpi(acc,'Cobertura')}, risco={_kpi(acc,'Nível de risco')}")

        ag = tela(scr, "agentes")
        assert ag and ag.get("type") == "dash", "agentes não é dash"
        assert _kpi(ag, "Total de agentes") == str(cc["agents_status"]["total"]), "agentes total != command_center"
        print(f"OK agentes: total={_kpi(ag,'Total de agentes')}, presentes={_kpi(ag,'Presentes')}")

        # O consultor era um dash de KPIs e virou CHAT na unificação (Fase 7) — de propósito.
        # O assert antigo (`type == "dash"`) reprovava a mudança e parecia defeito do
        # operacional. Aqui se prova o que importa numa tela de chat: que não é casca — tem
        # rota real, campo que o backend espera e a lente do módulo certo.
        con = tela(scr, "consultor")
        assert con and con.get("type") == "chat", f"consultor deixou de ser chat: {con and con.get('type')}"
        chat = con.get("chat") or {}
        assert chat.get("endpoint") in {"/api/v1/consultores/chat/executar",
                                        "/api/v1/consultores/chat/consultar"}, \
            f"consultor aponta para endpoint desconhecido: {chat.get('endpoint')}"
        assert chat.get("field") == "pergunta", f"campo do payload != 'pergunta': {chat.get('field')}"
        assert chat.get("persona") == "operacional", \
            f"persona da lente != operacional: {chat.get('persona')}"
        assert chat.get("suggestions"), "chat sem sugestões — tela em branco para o usuário"
        print(f"OK consultor: chat -> {chat['endpoint']} (persona={chat['persona']}, "
              f"{len(chat['suggestions'])} sugestões)")

        # O panorama que alimentava aqueles KPIs continua tendo que ser real: o chat responde
        # em cima dele. Sem este check, trocar dash por chat viraria desculpa para não medir.
        assert pan["postos"]["ativos"] >= 0 and pan["ocorrencias"]["abertas"] >= 0, pan
        print(f"OK panorama COO: postos_ativos={pan['postos']['ativos']}, "
              f"occ_abertas={pan['ocorrencias']['abertas']}")


if __name__ == "__main__":
    asyncio.run(main())
