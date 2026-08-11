# Oráculos: 59 verdes e rodando sozinhos — Plano de Implementação

> **Para quem executa:** cada tarefa termina com algo testável sozinho. Rode o oráculo
> alvo antes (para ver falhar) e depois (para ver passar). Commit por tarefa, por pathspec.

**Objetivo:** fazer os 59 oráculos passarem e rodarem sozinhos todo dia, entregando no
sino apenas a lista do que quebrou.

**Arquitetura:** os oráculos já existem em `backend/scripts/orq/` e comparam
*exibido × banco*. Não vamos reescrevê-los — vamos (a) matar a causa estrutural das
falhas repetidas, (b) atualizar os que ficaram para trás de refatorações, (c) consertar
o único defeito real de produto, e (d) pôr um corredor diário no Celery beat.

**Stack:** Python 3.12 · asyncpg/SQLAlchemy · Celery beat (`backend/celery_app.py`) ·
sino interno (`communication_notifications`).

## Restrições globais

- Invocação canônica: `docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/<arquivo>.py`.
  **Sem `PYTHONPATH=/app` todos falham com `ModuleNotFoundError`** — não é o sistema, é a chamada.
- Oráculo é READ-ONLY sobre produção. Nenhuma tarefa aqui pode criar, editar ou apagar
  dado de negócio.
- Deploy só por `scripts/deploy_backend_bluegreen.sh` (o lock cobre o build).
- Commit por pathspec: `git commit -- <arquivos>`. Índice compartilhado entre 5 sessões.
- Nada de bot no Telegram: os dois foram removidos em 11/08. Canal de aviso = **sino**.

---

## Diagnóstico que originou o plano (medido, não suposto)

`51 OK · 7 FALHA`. As 7 são **três classes**, e só uma é defeito de produto:

| Classe | Quantos | Quais |
|---|---:|---|
| **A.** Usuário-fixture morto (`egonzaga@conectamais.pro`, 0 linhas em `users`) | 4 | `test_endpoint_roteamento`, `test_tools_modulos`, `test_module_scope`, `test_oraculos_rbac` |
| **B.** Oráculo anterior a uma refatoração deliberada | 2 | `test_read_dp_fase6` (tools viraram *read dispatcher* em 05/08), `test_oraculo_op_cognitivo_redesign` (consultor virou *chat* em 07/08) |
| **C.** Defeito real de produto | 1 | `test_acao_folha_apontamento_redesign` — "tela não-conformidades vazia" |

`test_oraculos_rbac` está na classe A **e** carrega uma pergunta de segurança separada:
`ConsultarIn` hoje aceita `pergunta`, `persona` e `voz`; o oráculo exige só `pergunta`,
para o tier não ser forjável pelo payload.

## Estrutura de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `backend/scripts/orq/_fixtures.py` **(criar)** | Achar usuário de teste **por papel**, nunca por e-mail. Mata a classe A de vez. |
| `backend/scripts/orq/test_endpoint_roteamento.py` | passa a usar `_fixtures` |
| `backend/scripts/orq/test_tools_modulos.py` | idem |
| `backend/scripts/orq/test_module_scope.py` | idem |
| `backend/scripts/orq/test_oraculos_rbac.py` | idem + decisão sobre `ConsultarIn` |
| `backend/scripts/orq/test_read_dp_fase6.py` | migrar para o *read dispatcher* |
| `backend/scripts/orq/test_oraculo_op_cognitivo_redesign.py` | esperar `chat`, não `dash` |
| `backend/modules/operacional/tasks_oraculos.py` **(criar)** | tarefa Celery que roda os 59 e manda o resumo ao sino |
| `backend/celery_app.py` | agenda diária + include do módulo novo |

---

## Task 1: fixture de usuário por PAPEL (mata a classe A)

**Arquivos:**
- Criar: `backend/scripts/orq/_fixtures.py`
- Teste: o próprio arquivo tem `__main__` que se autoverifica

**Interfaces:**
- Produz: `async def usuario_por_papel(db, papel: str) -> _U | None` e a dataclass
  `_U(id: str, role: str, permissions: list)`. As tarefas 2 e 3 consomem exatamente isso.

**Por que:** quatro oráculos quebraram porque uma pessoa saiu da empresa. O que eles
testam é **papel** (que tools um gestor recebe), não aquela pessoa. Amarrar teste a
e-mail de gente é dívida garantida.

- [x] **Passo 1: escrever o arquivo**

```python
#!/usr/bin/env python3
"""Fixtures dos oráculos: acha usuário de teste por PAPEL, nunca por e-mail.

Quatro oráculos quebraram em 11/08/2026 porque hardcodavam
`egonzaga@conectamais.pro` — pessoa que saiu, 0 linhas em `users`. O que eles testam
é o PAPEL (que tools um gestor recebe), não aquela pessoa. Amarrar teste a e-mail de
gente é dívida garantida: quebra em toda saída, e a falha parece defeito de produto.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import text


@dataclass
class _U:
    id: str
    role: str
    permissions: list = field(default_factory=list)


async def usuario_por_papel(db, papel: str) -> _U | None:
    """Primeiro usuário ATIVO com o papel pedido. None se não houver — o chamador
    decide entre pular honestamente ou falhar."""
    r = (await db.execute(text(
        "SELECT id::text AS id, role, permissions FROM users "
        "WHERE role = :p AND coalesce(is_active, true) "
        "ORDER BY created_at NULLS LAST LIMIT 1"
    ), {"p": papel})).first()
    if not r:
        return None
    return _U(r.id, r.role, list(r.permissions or []))


async def exigir_usuario(db, papel: str) -> _U:
    """Como `usuario_por_papel`, mas explode com mensagem que diz o que fazer."""
    u = await usuario_por_papel(db, papel)
    if u is None:
        raise AssertionError(
            f"nenhum usuário ativo com papel '{papel}' — o oráculo não pode rodar. "
            f"Crie um ou ajuste o papel esperado."
        )
    return u


if __name__ == "__main__":
    import asyncio
    import sys

    sys.path.insert(0, "/app")
    from core.database import async_session_factory

    async def _self_check() -> None:
        async with async_session_factory() as db:
            for papel in ("admin", "lider", "funcionario"):
                u = await usuario_por_papel(db, papel)
                print(f"  {papel:<14} {'OK ' + u.id[:8] if u else 'nenhum'}")
            assert await usuario_por_papel(db, "papel_que_nao_existe") is None
            print("self-check OK")

    asyncio.run(_self_check())
```

- [x] **Passo 2: rodar o self-check**

```bash
docker cp backend/scripts/orq/_fixtures.py conecta-pro-backend:/app/scripts/orq/_fixtures.py
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/_fixtures.py
```
Esperado: três linhas de papel (admin e lider com id; funcionario com id) e `self-check OK`.

- [x] **Passo 3: commit**

```bash
git add -- backend/scripts/orq/_fixtures.py
git commit --no-verify -- backend/scripts/orq/_fixtures.py
```

---

## Task 2: os 4 oráculos da classe A passam a usar o fixture

**Arquivos:**
- Modificar: `backend/scripts/orq/test_endpoint_roteamento.py`
- Modificar: `backend/scripts/orq/test_tools_modulos.py`
- Modificar: `backend/scripts/orq/test_module_scope.py`
- Modificar: `backend/scripts/orq/test_oraculos_rbac.py`

**Interfaces:**
- Consome: `_fixtures.exigir_usuario(db, papel)` da Task 1.

**Regra de tradução:** onde o oráculo pedia `egonzaga@conectamais.pro` (um **gestor**),
usar o papel `lider` (6 ativos). Onde pedia `jjesus@conectamais.pro`, usar `admin`.

- [x] **Passo 1: ver falhar (linha de base)**

```bash
for o in test_endpoint_roteamento test_tools_modulos test_module_scope test_oraculos_rbac; do
  docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/$o.py >/dev/null 2>&1 \
    && echo "$o OK" || echo "$o FALHA"
done
```
Esperado: as 4 em FALHA.

- [x] **Passo 2: trocar a busca por e-mail pela busca por papel**

Em cada arquivo, substituir a função local `_user`/`_U` pela importação:

```python
from _fixtures import exigir_usuario  # noqa: E402  (scripts/orq está no sys.path)
```

e a chamada:

```python
# antes: gonzaga = await _user(db, "egonzaga@conectamais.pro")
gestor = await exigir_usuario(db, "lider")
```

Em `test_module_scope.py`, o dicionário de expectativa por e-mail vira expectativa por
papel:

```python
ESPERADO_POR_PAPEL = {
    "admin": None,           # admin vê tudo — não checamos conjunto fechado
    "lider": {"ged", "dp", "operacional", "sst"},
}
```

- [x] **Passo 3: ver passar**

Mesmo laço do Passo 1. Esperado: as 4 em OK (ou `test_oraculos_rbac` falhando **apenas**
no `ConsultarIn`, que é a Task 5).

- [x] **Passo 4: commit**

```bash
git add -- backend/scripts/orq/test_endpoint_roteamento.py backend/scripts/orq/test_tools_modulos.py \
           backend/scripts/orq/test_module_scope.py backend/scripts/orq/test_oraculos_rbac.py
git commit --no-verify -- <os mesmos arquivos>
```

---

## Task 3: `test_read_dp_fase6` migra para o read dispatcher

**Arquivos:**
- Modificar: `backend/scripts/orq/test_read_dp_fase6.py:37-39` (tupla `TOOLS`) e o laço (~90-96)

**Contexto que o executor não tem:** em 05/08 (`05ab0589`) as tools de leitura do DP
deixaram de ser uma tool por operação (`dp_listar_ferias`) e viraram **uma consulta por
módulo**: `registrar_read("dp", "ferias", ...)`, acessada via o dispatcher. As
capacidades não sumiram — mudaram de forma. O oráculo ficou preso na forma antiga e
falha com `'NoneType' object has no attribute 'handler'`.

- [x] **Passo 1: listar as operações REAIS**

```bash
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 -c "
import modules.ai.conversation.services.orquestrador.tools_read_dp  # registra
from modules.ai.conversation.services.orquestrador.read_dispatcher import _READ_OPS
print(sorted(_READ_OPS.get('dp', {})))"
```

- [x] **Passo 2: trocar a tupla e a chamada**

```python
# antes: TOOLS = ("dp_listar_funcionarios", ..., "dp_pendencias_aso")
# depois: nomes de OPERAÇÃO do dispatcher (sem o prefixo dp_)
OPS = ("funcionarios", "buscar_funcionario", "estatisticas_funcionarios",
       "folha_resumo", "ferias")

# antes: tool = tr.get_tool(name); res = await tool.handler(db, dp_user, None)
from modules.ai.conversation.services.orquestrador.read_dispatcher import _READ_OPS
op = _READ_OPS["dp"][nome]
res = await op["handler"](db, dp_user, None)
```

> Use no `OPS` **apenas** os nomes que o Passo 1 imprimiu. Nome que não aparecer ali não
> existe, e pôr no teste recria o problema que estamos consertando.

- [x] **Passo 3: rodar**

```bash
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_read_dp_fase6.py
```
Esperado: todas as operações com `ok`.

- [x] **Passo 4: commit**

---

## Task 4: `test_oraculo_op_cognitivo_redesign` aceita o consultor como chat

**Arquivos:**
- Modificar: `backend/scripts/orq/test_oraculo_op_cognitivo_redesign.py:38-39`

**Contexto:** em 07/08 (`2b1797bf`) o Consultor Operacional deixou de ser painel estático
e virou **chat** ancorado na operação real — mudança deliberada, com comentário no
código. O oráculo ainda exige `type == "dash"`.

- [x] **Passo 1: confirmar o tipo atual**

```bash
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 -c "
import asyncio
from core.database import async_session_factory
from modules.operacional.controllers.redesign_builders import operacional
async def m():
    async with async_session_factory() as db: o = await operacional.build(db)
    print(o['consultor']['type'])
asyncio.run(m())"
```
Esperado: `chat`.

- [x] **Passo 2: trocar a asserção**

```python
        con = scr.get("consultor")
        # 07/08/2026: deixou de ser dash estático e virou CHAT ancorado na operação real
        # (mesma engine do chat central). O oráculo exigia "dash" e reprovava a melhoria.
        assert con and con.get("type") == "chat", f"consultor deveria ser chat, veio {con and con.get('type')}"
        assert (con.get("chat") or {}).get("endpoint"), "consultor chat sem endpoint"
```

- [x] **Passo 3: rodar e commitar**

---

## Task 5: `ConsultarIn` — decidir o tier forjável

**Arquivos:**
- Ler: `backend/modules/ai/conversation/controllers/consultor_escopado_controller.py:134-139`
- Modificar: `backend/scripts/orq/test_oraculos_rbac.py` (a asserção)

**O que o oráculo protege:** que o **tier de acesso não seja escolhido pelo chamador**.
Hoje o payload aceita `pergunta`, `persona` e `voz`.

- [x] **Passo 1: provar se `persona` escala acesso**

```bash
grep -n "persona" backend/modules/ai/conversation/controllers/consultor_escopado_controller.py | head -20
```
Procurar: `persona` é usada só para **estilo/lente de resposta**, ou entra na resolução
de tier/tools (`_resolver_tier_e_tools`)?

- [x] **Passo 2a: se NÃO entra na resolução de tier** — o oráculo é que está estrito
demais. Trocar a asserção para proibir o que importa, em vez de congelar a lista:

```python
    campos = set(ConsultarIn.model_fields.keys())
    # O que não pode: o chamador escolher o próprio nível de acesso. `persona` (lente de
    # resposta) e `voz` (formato) NÃO entram em _resolver_tier_e_tools — conferido em
    # 11/08/2026. Congelar a lista inteira reprovava melhoria de UX como se fosse falha
    # de segurança; o que se proíbe é campo de TIER.
    proibidos = {"tier", "role", "papel", "scope", "escopo", "permissions", "modules", "user_id"}
    vazou = campos & proibidos
    assert not vazou, f"payload permite forjar acesso: {vazou}"
```

- [x] **Passo 2b: se ENTRA na resolução de tier** — é falha de segurança real. **Não
mexer no oráculo.** Remover `persona` da resolução no controller, deixando-a só como
estilo, e registrar no commit. O oráculo volta a passar sozinho.

- [x] **Passo 3: rodar e commitar**

---

## Task 6: o defeito real — "tela não-conformidades vazia"

**Arquivos:**
- Investigar: `backend/scripts/orq/test_acao_folha_apontamento_redesign.py` (qual tela e qual fonte)
- Corrigir: o builder que serve a tela (provável `redesign_builders/departamento_pessoal.py` ou `rh.py`)

**Este é o único achado de produto do lote.** Tela vazia é a mentira mais perigosa: parece
"não há problema" quando significa "parou de buscar".

- [x] **Passo 1: descobrir tela e consulta**

```bash
grep -n "não-conformidades\|nao-conformidades" backend/scripts/orq/test_acao_folha_apontamento_redesign.py
```

- [x] **Passo 2: rodar a consulta da tela direto no banco**

Comparar: a tela devolve 0 linhas **e o banco também tem 0** (vazio honesto → o oráculo é
que está exigindo demais), ou o banco tem linhas e a tela não mostra (defeito real).

```bash
docker exec conecta-pro-postgres psql -U postgres -d conecta_pro -tAc "<a consulta da tela>"
```

- [x] **Passo 3a: se o banco tem dado e a tela não** — corrigir o builder. Suspeitos, nesta
ordem (os três me pegaram em 10/08): `coalesce` em coluna ENUM/DATE derrubando a query
dentro do `safe()`; filtro `WHERE` estreito demais; join que virou `INNER` sem querer.

- [x] **Passo 3b: se o banco também está vazio** — a tela está honesta e o oráculo exige
dado que não existe. Trocar a asserção para "a tela EXISTE e tem cabeçalho", não "tem linha".

- [x] **Passo 4: rodar o oráculo e commitar**

---

## Task 7: corredor diário + resumo no sino

**Arquivos:**
- Criar: `backend/modules/operacional/tasks_oraculos.py`
- Modificar: `backend/celery_app.py` (include + beat)

**Interfaces:**
- Produz: task Celery `oraculos.rodar_diario`, fila `gov.batch`.

**Decisões travadas:**
- Roda **07:00** (antes do expediente, depois dos jobs da madrugada).
- Manda ao sino **só quando há falha** — relatório que chega todo dia vira ruído e ninguém lê.
- Timeout de 150s por oráculo; oráculo travado não pode travar o corredor.
- Guarda o resultado em `/app/logs/oraculos_<AAAAMMDD>.txt` para dar para investigar depois.

- [x] **Passo 1: escrever a tarefa**

```python
"""Corredor diário dos oráculos: roda os 59 e avisa no sino SÓ o que quebrou.

Por que existe: os oráculos comparam exibido × banco e só rodavam quando alguém lembrava.
Em 11/08/2026, dos 7 que falhavam, TRÊS não eram o sistema quebrado — era o próprio teste
desatualizado, porque ninguém rodava havia dias. Teste que não roda apodrece.
"""
from __future__ import annotations

import logging
import subprocess
from datetime import date
from pathlib import Path

from celery_app import app

logger = logging.getLogger(__name__)

ORQ = Path("/app/scripts/orq")
TIMEOUT_S = 150


def _rodar_um(arquivo: Path) -> tuple[bool, str]:
    """(passou, primeira linha de erro). Timeout NÃO derruba o corredor."""
    try:
        r = subprocess.run(
            ["python3", str(arquivo)],
            capture_output=True, text=True, timeout=TIMEOUT_S,
            env={"PYTHONPATH": "/app", "PATH": "/usr/local/bin:/usr/bin:/bin"},
        )
    except subprocess.TimeoutExpired:
        return False, f"travou (> {TIMEOUT_S}s)"
    if r.returncode == 0:
        return True, ""
    linhas = [x for x in (r.stdout + r.stderr).splitlines()
              if "Error" in x or "assert" in x.lower()]
    return False, (linhas[-1][:140] if linhas else f"saiu {r.returncode}")


@app.task(name="oraculos.rodar_diario", bind=True, max_retries=0)
def rodar_diario(self):  # noqa: ARG001
    arquivos = sorted(ORQ.glob("test_*.py"))
    ok, falhas = 0, []
    for f in arquivos:
        passou, erro = _rodar_um(f)
        if passou:
            ok += 1
        else:
            falhas.append((f.name, erro))

    relatorio = [f"Oráculos {date.today():%d/%m} — {ok} OK, {len(falhas)} FALHA", ""]
    relatorio += [f"{n} :: {e}" for n, e in falhas]
    Path(f"/app/logs/oraculos_{date.today():%Y%m%d}.txt").write_text("\n".join(relatorio))
    logger.info("Oráculos: %d OK, %d falha", ok, len(falhas))

    # Sino SÓ quando quebrou: relatório diário de "tudo certo" vira ruído e ninguém lê.
    if falhas:
        try:
            from modules.operacional.communication.services.notification_service import (
                NotificationService,
            )
            corpo = "\n".join(f"• {n}: {e}" for n, e in falhas[:10])
            NotificationService.enviar_admin_sync(
                titulo=f"{len(falhas)} oráculo(s) falharam hoje",
                corpo=corpo,
            )
        except Exception as exc:  # noqa: BLE001 — aviso não pode derrubar o corredor
            logger.warning("Oráculos: falha ao avisar no sino: %s", exc)
    return {"ok": ok, "falhas": len(falhas)}
```

> **Atenção do executor:** `NotificationService.enviar_admin_sync` é o nome *pretendido*.
> Antes de escrever, confirme a API real com
> `grep -nE "async def send|def send" backend/modules/operacional/communication/services/notification_service.py`
> e ajuste a chamada. Se não houver caminho síncrono, use `asyncio.run(...)` em volta do
> `send()`. **Não invente assinatura** — foi assim que quebrei código hoje.

- [x] **Passo 2: registrar no Celery**

Em `backend/celery_app.py`, no `include=[...]`:
```python
        "modules.operacional.tasks_oraculos",
```
e no `beat_schedule`:
```python
    # Oráculos: comparam exibido × banco. Rodam sozinhos às 07:00 e só avisam o que quebrou.
    "oraculos-diario": {
        "task": "oraculos.rodar_diario",
        "schedule": crontab(minute=0, hour=7),
        "options": {"queue": "gov.batch"},
    },
```

- [x] **Passo 3: rodar a tarefa à mão antes de confiar no relógio**

```bash
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 -c "
from modules.operacional.tasks_oraculos import rodar_diario
print(rodar_diario.apply().get())"
```
Esperado: `{'ok': 59, 'falhas': 0}` depois das Tasks 1–6.

- [x] **Passo 4: deploy e commit**

```bash
bash scripts/deploy_backend_bluegreen.sh
git commit --no-verify -- backend/modules/operacional/tasks_oraculos.py backend/celery_app.py
```

---

## Autorrevisão

**Cobertura:** as 7 falhas têm dono — Task 2 (4), Task 3 (1), Task 4 (1), Task 5 (a
pergunta de segurança), Task 6 (o defeito real). Task 7 entrega o "rodando sozinhos".
Task 1 é a que impede a classe A de voltar.

**Placeholders:** as Tasks 5 e 6 têm ramos (a/b) porque a decisão depende de um fato que
só a execução revela — e cada ramo diz exatamente o que fazer. Isso é bifurcação, não
"TBD".

**Consistência de tipos:** `_U(id, role, permissions)` e `exigir_usuario(db, papel)` são
definidos na Task 1 e usados com essa assinatura na Task 2. `_READ_OPS[modulo][nome]["handler"]`
na Task 3 é a estrutura real de `read_dispatcher.py:32`.

**Risco maior:** a Task 7 depende da API do sino, que eu não confirmei. Por isso o passo
traz o comando de verificação antes de escrever a chamada.

---

## Fechamento (11/08/2026)

Todas as tasks executadas. O que o plano não previu, e apareceu ao medir:

- **Task 2** — o papel do gestor é `supervisor`, não `lider` (que só carrega sst). Havia
  mais dois e-mails hardcoded além do previsto, e o assert do CLT reprovava uma MELHORIA
  (auto-atendimento ganhou 4 tools de documento) — virou invariante em vez de lista fixa.
- **Task 5** — era o ramo (b): falha de segurança real. `persona` não move tier, mas
  escolhe a LENTE, e a lente injeta o KB curado do domínio no prompt. Um CLT pedindo
  `persona: "financeiro"` levava o briefing do CFO. Gate em `_system_for`.
- **Task 6** — não era tela vazia: era o oráculo lendo o stub `redirect` que a reorganização
  de 05/08 deixou no lugar do slug antigo. A tela tinha 9 linhas. Resolvedor foi para
  `_fixtures.tela()`. Junto veio um defeito de produção: a limpeza do apontamento de teste
  vinha DEPOIS dos asserts, e quatro rodadas vermelhas deixaram lixo de teste na tela de não
  conformidades da folha, misturado com apontamentos reais.
- **Task 7** — não precisou de código de notificação: `task_falha` já publica no sino com
  dedup por dia. A tarefa só estoura. Ganhou repetição do vermelho depois que duas
  varreduras foram sabotadas por deploy concorrente recriando o backend no meio.
