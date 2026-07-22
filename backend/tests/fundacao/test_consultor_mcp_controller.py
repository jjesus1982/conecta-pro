"""Testa o controller MCP dos consultores pela rota real (disciplina: verificar pela rota da tela).
Standalone (sem pytest): httpx contra a BANCADA green. Rodar por:
docker exec conecta-pro-backend-green sh -c 'cd /app && PYTHONPATH=/app python tests/fundacao/test_consultor_mcp_controller.py'
(depois de docker cp do controller pro green + restart do green — ver 'Ambiente de execução de teste').

NOTA (corrigido na Task 3): `docker port conecta-pro-backend-green` mostra 8080/tcp -> 0.0.0.0:8081
— isso é o mapeamento visto do HOST. Este teste roda via `docker exec`, ou seja, DENTRO do
namespace de rede do container green, onde o uvicorn escuta em 127.0.0.1:8080 (confirmado:
CMD `--port 8080`; socket connect a 127.0.0.1:8080 = sucesso, a 127.0.0.1:8081 = recusado).
Esse 8080 é o loopback INTERNO do próprio green — não tem nenhuma relação com o :8080 público
do host (container conecta-pro-backend, produção), que continua intocado."""
import asyncio
import os
from httpx import AsyncClient
from sqlalchemy import text
from tests.fundacao._mcp_token import make_token

BASE = os.environ["MCP_TEST_BASE"]  # obrigatório; setado só no docker exec sancionado dentro do green


async def _post(path, json):
    async with AsyncClient(base_url=BASE, timeout=60) as ac:
        return await ac.post(path, json=json, headers={"Authorization": f"Bearer {make_token()}"})


async def _db_exec(sql, params):
    """Executa um write no banco de forma robusta a event-loops (dispose do pool estagnado antes).

    Cada teste roda seu próprio asyncio.run() (loop novo); connections pooladas por um
    teste anterior ficam presas ao loop antigo já fechado, e pool_pre_ping=True derruba
    com "Future attached to a different loop" no checkout. Descarta o pool antes de usar.
    """
    from core.database import async_session_factory, engine
    await engine.dispose()  # descarta conexões presas a loops de testes anteriores
    async with async_session_factory() as db:
        await db.execute(text(sql), params)
        await db.commit()


async def _db_scalar(sql, params):
    """Lê uma linha do banco, robusto a event-loops (mesmo contorno de _db_exec)."""
    from core.database import async_session_factory, engine
    await engine.dispose()
    async with async_session_factory() as db:
        return (await db.execute(text(sql), params)).first()


def test_origem_invalida_recusada():
    # unidade pura: 422 acontece ANTES de gerar()/OpenAI
    async def run():
        r = await _post("/consultores/mcp/marketing/consultar", {"pergunta": "oi"})
        assert r.status_code == 422, r.text
    asyncio.run(run())


def test_consulta_cfo_responde():
    # chama gerar() → precisa de OPENAI_API_KEY no container (presente em prod)
    async def run():
        r = await _post("/consultores/mcp/cfo/consultar", {"pergunta": "Resuma o caixa em uma frase."})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["origem"] == "cfo"
        assert isinstance(body["resposta"], str) and len(body["resposta"]) > 0
    asyncio.run(run())


def test_feedback_grava_memoria():
    # ⚠️ green compartilha o banco vivo E registrar_feedback grava em consultor_memorias, que
    # contexto_compartilhado injeta como "memória permanente" em TODOS os 8 consultores. Usa um
    # marcador de teste e DELETA no finally — nunca deixar correção-fake na memória viva.
    _MARK = "TESTE 5.1 (apagar) feedback automatizado"
    async def run():
        r = await _post("/consultores/mcp/feedback",
                        {"origem": "cfo", "correcao": _MARK, "consulta_id": None})
        try:
            assert r.status_code == 200, r.text
            assert r.json().get("ok") is True
        finally:
            await _db_exec(
                "DELETE FROM consultor_memorias WHERE fonte='feedback_gestor' AND conteudo LIKE :m",
                {"m": f"%{_MARK}%"},
            )
    asyncio.run(run())


def test_propor_pagamento_nasce_preparado():
    # ⚠️ green compartilha o BANCO VIVO: esta proposta apareceria na fila real de OTP do Jordan.
    # O teste DELETA a linha no fim (bloco finally) — não deixar pagamento-teste na produção.
    async def run():
        r = await _post("/consultores/mcp/propor-pagamento",
                        {"valor": 1.23, "pix_key": "teste@conectapro.com.br", "descricao": "TESTE 5.1 (apagar)"})
        assert r.status_code == 200, r.text
        pid = r.json()["payment_id"]
        try:
            assert r.json()["status"] == "preparado"
            # oráculo de segurança: nasce 'preparado', JAMAIS 'aprovado'/'executado'
            row = await _db_scalar("SELECT status FROM inter_payments WHERE id=:i", {"i": pid})
            assert row is not None and row[0] == "preparado"
        finally:
            # limpeza OBRIGATÓRIA: remove o pagamento-teste da fila de produção
            await _db_exec("DELETE FROM inter_payments WHERE id=:i AND status='preparado'", {"i": pid})
    asyncio.run(run())


def test_propor_comunicado_nasce_rascunho():
    # ⚠️ green compartilha o BANCO VIVO: o rascunho apareceria nos comunicados reais. DELETA no fim.
    async def run():
        r = await _post("/consultores/mcp/propor-comunicado",
                        {"titulo": "TESTE 5.1 (apagar)", "corpo": "corpo de teste"})
        assert r.status_code == 200, r.text
        aid = r.json()["announcement_id"]
        try:
            assert r.json()["status"] == "rascunho"
            row = await _db_scalar(
                "SELECT status, enviar_push, enviar_email FROM communication_announcements WHERE id=:i",
                {"i": aid},
            )
            assert row is not None and row[0] == "rascunho"
            assert not row[1] and not row[2]
        finally:
            # limpeza OBRIGATÓRIA: remove o comunicado-teste da produção (só se ainda rascunho)
            await _db_exec("DELETE FROM communication_announcements WHERE id=:i AND status='rascunho'", {"i": aid})
    asyncio.run(run())


# funções de teste das Tasks 4/5/6 são ADICIONADAS abaixo neste mesmo arquivo.
_TESTS = [test_origem_invalida_recusada, test_consulta_cfo_responde, test_feedback_grava_memoria,
          test_propor_pagamento_nasce_preparado, test_propor_comunicado_nasce_rascunho]

if __name__ == "__main__":  # runner standalone, sem pytest
    import sys, traceback
    fail = 0
    for fn in _TESTS:
        try:
            fn(); print(f"PASS {fn.__name__}")
        except Exception:
            fail += 1; print(f"FAIL {fn.__name__}"); traceback.print_exc()
    sys.exit(1 if fail else 0)
