"""Oráculo — os executores existem NO PROCESSO QUE APROVA.

⭐ Este oráculo é o irmão do de leitura, e nasce de um defeito que os oráculos ESCONDERAM.
Todos os testes de ação importavam `tools_acao_crm` no topo: viam tudo registrado, passavam
verde, e o backend — que nunca importa esse módulo — falhava com "sem executor registrado"
em TODO rascunho de CRM. O Jordan tentava aprovar a proposta da VEGA desde 29/08.

Por isso: `import main_production` PRIMEIRO, e NENHUM import do orquestrador antes da
medição. O que este arquivo importa, ele mesmo cria.
"""
import sys
sys.path.insert(0, "/app")
import main_production  # noqa: F401  ← antes de tudo, sempre

FALHAS = []


def ok(cond, nome, detalhe=""):
    print("  %s %s%s" % ("✅" if cond else "❌", nome, (" — " + detalhe) if detalhe else ""))
    if not cond:
        FALHAS.append(nome)


print("\n== 1. o servidor SOZINHO (antes de qualquer guarda) ==")
_mods = [m for m in sys.modules if "tools_acao_crm" in m]
print("     tools_acao_crm no grafo de import do servidor: %s" % (bool(_mods)))
print("     (informativo: o conserto não é importar no startup, é a guarda no caminho)")

print("\n== 2. a guarda registra quando a aprovação precisa ==")
from modules.ai.conversation.services.orquestrador.acoes import rascunho as R

R._garantir_executores()
ok(len(R.EXECUTORES) > 0, "EXECUTORES deixou de ser vazio", f"{len(R.EXECUTORES)} registrados")
for tipo in ("pedir_cotacao", "criar_orcamento"):
    ok(tipo in R.EXECUTORES, f"executor de {tipo} presente",
       "sem ele a Central falha no clique do Jordan")

print("\n== 3. e a guarda roda DENTRO de executar_rascunho ==")
import inspect
src = inspect.getsource(R.executar_rascunho)
ok("_garantir_executores" in src, "executar_rascunho chama a guarda",
   "é o único ponto por onde TODA aprovação passa")

print("\n== 4. tipo desconhecido continua recusando ==")


class _D:
    tipo = "tipo_que_nao_existe_zzz"
    payload = {}


import asyncio
try:
    asyncio.run(R.executar_rascunho(None, None, _D()))
    ok(False, "tipo inexistente recusa", "executou algo que não devia")
except ValueError as e:
    ok("sem executor registrado" in str(e), "tipo inexistente recusa", str(e)[:52])
except Exception as e:  # noqa: BLE001
    ok(False, "tipo inexistente recusa", f"erro inesperado: {type(e).__name__}")

print("\n%s" % ("TODAS AS CHECAGENS PASSARAM" if not FALHAS
                else "FALHOU: " + " · ".join(FALHAS)))
if FALHAS:
    raise SystemExit(1)
