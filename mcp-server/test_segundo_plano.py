"""Segundo plano não pode virar porta dos fundos das duas paredes.

As paredes do conector (`gate_propose` e `identidade`) vivem no middleware `on_call_tool`
do FastMCP, e ele julga o nome da chamada EXTERNA. Quando nasceu o despachante
`executar_em_segundo_plano`, a chamada externa passou a ser sempre ele — e a ferramenta que
realmente roda ficou invisível para as duas paredes.

Concretamente, sem o que este teste tranca: `executar_em_segundo_plano("enviar_link_assinatura")`
entraria por uma porta que o middleware lê como inofensiva e mandaria um link de assinatura
para um cliente real, sem passar pela aprovação humana. E o `_TOKEN` da identidade é solto
no `finally` do middleware quando a chamada externa retorna — mas o job continua vivo depois
disso, então sem carregar o token para dentro da task o job perderia o usuário no meio e
cairia na conta de serviço. É a escalada silenciosa que a F2 existe para impedir.

⚠️ Este teste roda no BUILD da imagem (Dockerfile), com fastmcp presente — ele importa o
server de verdade em vez de medir o texto do arquivo. Caçador de regex mede o regex.

    python test_segundo_plano.py
"""
from __future__ import annotations

import asyncio
import os

os.environ["MCP_MODO"] = "agente"  # as duas paredes só existem no modo agente

import gate_propose  # noqa: E402
import identidade  # noqa: E402
import server as S  # noqa: E402
import tool_risk_manifest as M  # noqa: E402

TIMEOUT_ESPERADO = S.TIMEOUT_JOB


def test_modo_agente_ativo() -> None:
    """Sem isto o teste inteiro passaria vazio — as paredes estariam desligadas."""
    assert gate_propose.MODO_AGENTE, "MCP_MODO=agente não pegou; as paredes estão dormindo"
    assert identidade.MODO_AGENTE


def test_propose_nao_passa_por_segundo_plano() -> None:
    propostas = [n for n, c in M.TOOL_RISK.items() if c == "propose"]
    assert len(propostas) >= 3, f"só {len(propostas)} tools propose — manifesto encolheu?"
    identidade._TOKEN.set("jwt-sintetico")  # identidade presente: isola o gate propose
    for nome in propostas:
        if not hasattr(S, nome):
            continue
        r = asyncio.run(S.executar_em_segundo_plano(nome, {}))
        assert r.get("codigo") == "PRECISA_APROVACAO", (
            f"`{nome}` é propose e ENTROU em segundo plano: {r}")
    identidade._TOKEN.set(None)
    print(f"OK propose barrado em segundo plano ({len(propostas)} tools)")


def test_sensivel_sem_identidade_nao_passa() -> None:
    identidade._TOKEN.set(None)
    alvo = next((n for n in M.TOOL_RISK
                 if identidade.sensivel(n)
                 and not gate_propose.precisa_aprovacao(n)
                 and hasattr(S, n)), None)
    assert alvo, "nenhuma tool sensível não-propose — não dá para provar esta parede"
    r = asyncio.run(S.executar_em_segundo_plano(alvo, {}))
    assert r.get("codigo") == "SEM_IDENTIDADE", f"`{alvo}` rodou sem identidade: {r}"
    print(f"OK sem identidade barrado em segundo plano (via {alvo})")


def test_caminho_feliz_existe() -> None:
    """Irmã obrigatória das duas recusas acima.

    Duas paredes verdes sobre um despachante que não despacha nada seriam 2/2 sobre
    capacidade morta — o oráculo cúmplice desta casa.
    """
    async def sonda() -> dict:
        return {"token": identidade._TOKEN.get(), "em_job": S._EM_JOB.get()}

    setattr(S, "sonda_de_teste", sonda)
    M.TOOL_RISK["sonda_de_teste"] = "read"
    gate_propose.TOOL_RISK["sonda_de_teste"] = "read"

    async def roda() -> dict:
        identidade._TOKEN.set("jwt-do-chamador")
        r = await S.executar_em_segundo_plano("sonda_de_teste", {})
        assert r.get("ok"), f"read foi barrado em segundo plano: {r}"
        for _ in range(40):
            if (await S.status_job(r["job_id"])).get("pronto"):
                break
            await asyncio.sleep(0.1)
        return await S.resultado_job(r["job_id"])

    fim = asyncio.run(roda())
    dentro = fim.get("resultado") or {}
    assert dentro.get("token") == "jwt-do-chamador", (
        f"o job perdeu a identidade do chamador: {dentro} — cairia na conta de serviço")
    assert dentro.get("em_job") is True, "o job não marcou o contexto; o timeout longo não valeria"
    print("OK read roda em segundo plano, carregando a identidade de quem pediu")


def test_timeout_longo_e_o_FATO_nao_a_flag() -> None:
    """Dentro do job o httpx recebe 600s de verdade — não só `_EM_JOB is True`.

    ⭐ A versão anterior deste teste conferia a FLAG. Flag ligada é um proxy: ela prova que o
    contexto foi marcado, não que alguém leu a marca. Se o `timeout=` de alguma chamada
    tivesse ficado literal, a flag continuaria verde e a operação longa morreria aos 40s do
    mesmo jeito — com o agente achando que o job protegia.

    E o login fica em 20s nos dois: login lento é login quebrado, não operação longa.
    """
    import httpx

    visto: list = []
    original = httpx.AsyncClient.request

    async def espia(self, method, url, **kw):  # noqa: ANN001
        visto.append((method, str(url), kw.get("timeout")))
        return await original(self, method, url, **kw)

    async def roda() -> None:
        httpx.AsyncClient.request = espia
        # Este teste mede o TETO, não as paredes — e elas têm teste próprio acima. Sem
        # identidade o despacho é recusado antes de qualquer HTTP, e o teste mediria o
        # silêncio de uma recusa em vez do timeout. Desligar a parede aqui é explícito e
        # restaurado no `finally`; o que NÃO pode é o teste passar sem medir nada.
        modo_antes = identidade.MODO_AGENTE
        identidade.MODO_AGENTE = False
        identidade._TOKEN.set(None)
        try:
            await S.erp.get("/crm/contracts", params={"page_size": 1})
            fora = [t for m, u, t in visto if "contracts" in u]
            assert fora and fora[-1] == 40, f"fora do job o teto mudou: {fora}"
            logins = [t for m, u, t in visto if "login" in u]
            assert all(t == 20 for t in logins), f"o login saiu do teto de 20s: {logins}"

            visto.clear()
            j = await S.executar_em_segundo_plano("listar_contratos", {"limite": 1})
            for _ in range(40):
                if (await S.status_job(j["job_id"])).get("pronto"):
                    break
                await asyncio.sleep(0.2)
            dentro = [t for m, u, t in visto if "contracts" in u]
            assert dentro and dentro[-1] == TIMEOUT_ESPERADO, (
                f"dentro do job o teto continuou {dentro} — o job só mudaria a espera de "
                f"lugar e morreria no mesmo ponto")
            logins = [t for m, u, t in visto if "login" in u]
            assert all(t == 20 for t in logins), f"o login herdou o teto do job: {logins}"
        finally:
            httpx.AsyncClient.request = original
            identidade.MODO_AGENTE = modo_antes

    asyncio.run(roda())
    print(f"OK teto real: 40s fora, {TIMEOUT_ESPERADO}s dentro, login em 20s nos dois")


def test_desconhecida_recusa() -> None:
    r = asyncio.run(S.executar_em_segundo_plano("ferramenta_que_nao_existe", {}))
    assert r.get("codigo") == "FERRAMENTA_DESCONHECIDA", r
    print("OK ferramenta inexistente recusada")


if __name__ == "__main__":
    for fn in (test_modo_agente_ativo, test_propose_nao_passa_por_segundo_plano,
               test_sensivel_sem_identidade_nao_passa, test_caminho_feliz_existe,
               test_timeout_longo_e_o_FATO_nao_a_flag, test_desconhecida_recusa):
        fn()
        print(f"PASS {fn.__name__}")
    print("TEST test_segundo_plano PASS")
