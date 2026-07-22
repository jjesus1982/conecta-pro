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
from tests.fundacao._mcp_token import make_token

BASE = os.environ["MCP_TEST_BASE"]  # obrigatório; setado só no docker exec sancionado dentro do green


async def _post(path, json):
    async with AsyncClient(base_url=BASE, timeout=60) as ac:
        return await ac.post(path, json=json, headers={"Authorization": f"Bearer {make_token()}"})


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


# funções de teste das Tasks 4/5/6 são ADICIONADAS abaixo neste mesmo arquivo.
_TESTS = [test_origem_invalida_recusada, test_consulta_cfo_responde]

if __name__ == "__main__":  # runner standalone, sem pytest
    import sys, traceback
    fail = 0
    for fn in _TESTS:
        try:
            fn(); print(f"PASS {fn.__name__}")
        except Exception:
            fail += 1; print(f"FAIL {fn.__name__}"); traceback.print_exc()
    sys.exit(1 if fail else 0)
