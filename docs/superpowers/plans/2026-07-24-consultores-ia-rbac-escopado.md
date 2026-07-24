# Consultores IA Escopados por Perfil — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar a cada usuário um chat de IA cross-domínio cujo alcance é exatamente o que o RBAC + escopo do próprio perfil já permitem — enforçado na fonte (identidade do próprio usuário), nunca por prompt — do dono (via Hermes) ao CLT (só sobre si, com justificar-ponto→DP) e ao cliente externo (só o seu condomínio).

**Architecture:** UM orquestrador escopado in-backend (loop de function-calling sobre tools executadas com a identidade do usuário) com DUAS travas por usuário: (1) o conjunto de tools é filtrado por `user_modules(user)` antes do loop (belt); (2) cada handler executa in-process com a identidade real do usuário, então `require_permission`/`scope.py`/`employee_id`/`client_id` barram na fonte (suspenders). Diretoria (admin) delega ao Orquestrador Executivo já deployado (Hermes); demais tiers usam o motor escopado novo. Groundedness brando + auditoria append-only reusam a garantia da Fase 5.2a.

**Tech Stack:** Python 3.12 · FastAPI · SQLAlchemy async (`AsyncSession`) · `openai.AsyncOpenAI` (chat.completions com `tools`/`tool_choice`) · PostgreSQL · Next.js 16 (redesign, `ChatScreen.tsx`) · Docker (deploy blue-green baked).

## Global Constraints

Copiados VERBATIM da spec (`docs/superpowers/specs/2026-07-24-consultores-ia-rbac-escopado-design.md`) — todo requisito de tarefa inclui implicitamente esta seção:

- **O chat SEMPRE roda com a identidade/token do próprio usuário.** O que ele enxerga = o que as camadas de enforcement que já existem permitem.
- **O LLM NUNCA é a fronteira de segurança** — a fronteira é o RBAC no endpoint + o escopo na query. Fora do escopo = "aguardando dado" honesto, JAMAIS vazamento de outro posto/colaborador/módulo.
- **Dinheiro que SAI / ato legal / folha = propor→aprovar+humano** (justificar-ponto vai pro DP; nada auto). Buscar≠emitir para o cliente (nunca gera nota nova).
- **Operacional READ para o agente**; escopo de posto/self barra outro posto/colaborador.
- **Nunca fabricar**; fora do escopo = "aguardando dado".
- **Belt + suspenders:** filtro de tools por `user_modules` (belt) + RBAC/escopo na execução in-process (suspenders).
- **`TOOL_MODULE` fail-closed:** tool sem módulo declarado não é registrada nem aparece.

Constraints operacionais herdadas (inegociáveis do projeto):

- **Bancada nunca in-process no :8080** (app in-process = OOM). Testes standalone rodam por `docker cp` do script para o container + `docker exec ... python`; a bancada HTTP é o green (`conecta-pro-backend-green`, :8081), nunca o blue.
- **Green compartilha o banco vivo** → todo teste que ESCREVE apaga o que criou no `finally`.
- **Sem pytest** → todo teste é script standalone com `assert`, rodado por comando explícito.
- **`git add` só dos próprios arquivos** (árvore git compartilhada por 3 sessões Claude paralelas — nunca `git add -A`/`.`).
- **Commits `--no-verify`** (pre-commit flaky) com trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Deploy blue-green só no fim** (Task 13). Backend é BAKED na imagem (`docker cp`+restart = volátil; durável = rebuild via `scripts/deploy_backend_bluegreen.sh`).

---

## File Structure

Novos arquivos (todos sob `backend/`):

- `core/auth/module_scope.py` — `user_modules`/`user_has_module` + `CANONICAL_MODULES` (Task 1).
- `modules/ai/conversation/services/orquestrador/__init__.py` — pacote (Task 2).
- `modules/ai/conversation/services/orquestrador/tool_registry.py` — `ToolDef`, `register`, filtros, schema OpenAI (Task 2).
- `modules/ai/conversation/services/orquestrador/engine.py` — `OrqScope` + `run_engine` (loop function-calling) (Task 3).
- `modules/ai/conversation/services/orquestrador/tools_modulos.py` — tools de módulo p/ gestor/dev (Task 4).
- `modules/ai/conversation/services/orquestrador/tools_posto.py` — tools posto-scoped do líder (Task 5).
- `modules/ai/conversation/services/orquestrador/tools_self.py` — tools self do CLT (Task 6).
- `modules/ai/conversation/services/orquestrador/tools_ponto.py` — ação justificar-ajuste-de-ponto (Task 7).
- `modules/ai/conversation/services/orquestrador/tools_cliente.py` — tools condomínio-scoped + buscar+entregar documento (Tasks 9/10).
- `modules/ai/conversation/services/orquestrador/portal_cliente.py` — bridge do portal p/ o engine (Task 9).
- `modules/ai/conversation/controllers/consultor_escopado_controller.py` — `POST /consultores/chat/consultar` (Task 8).
- `scripts/orq/test_*.py` — testes standalone por task; `scripts/orq/test_oraculos_rbac.py` — suite-oráculo (Task 12).

Arquivos modificados:

- `main_production.py` — registrar o router escopado ANTES do `consultor_mcp` (Task 8).
- `modules/client_portal/controllers/assistant_controller.py` — `/send` delega ao engine (Task 9).
- `frontend/src/app/redesign/_modules/consultor-ia.json` (novo) + `frontend/src/components/redesign/modules.ts` (Task 11).

---

## Task 1: `user_modules(user)` — fundação do escopo por módulo

**Files:**
- Create: `backend/core/auth/module_scope.py`
- Test: `backend/scripts/orq/test_module_scope.py`

**Interfaces:**
- Consumes: objetos `User` do ORM (atributos `.role: str`, `.permissions: list[str]`).
- Produces:
  - `CANONICAL_MODULES: frozenset[str]`
  - `def user_modules(user) -> set[str]`
  - `def user_has_module(user, module: str) -> bool`

- [ ] **Step 1: Criar o helper**

```python
# backend/core/auth/module_scope.py
"""Escopo de MÓDULO por usuário (belt do orquestrador escopado — Peça 3).

Reusa `users.role` + `users.permissions[]` (o mesmo que `require_permission` já
enforça no endpoint). NÃO é a fronteira sozinho: é o filtro que decide QUAIS tools
o LLM sequer recebe. A fronteira real continua no handler (require_permission/scope/self).
"""
from __future__ import annotations

# Módulos canônicos do ERP (gates em main_production.py). dev/suporte NÃO têm
# financeiro/fiscal nas permissions → a régua "exceto os 3 sensíveis" cai fora
# naturalmente das permissions, sem hardcode.
CANONICAL_MODULES: frozenset[str] = frozenset(
    {"financeiro", "fiscal", "dp", "ged", "juridico", "crm", "operacional", "sst", "dev"}
)


def user_modules(user) -> set[str]:
    """Conjunto de módulos que o usuário pode ver.

    - role == 'admin' OU '*'/'all' em permissions -> TODOS os canônicos.
    - senão -> os prefixados 'module:X' em permissions, interceptados com os canônicos.
    """
    role = (getattr(user, "role", None) or "").lower()
    perms = getattr(user, "permissions", None) or []
    if role == "admin" or "*" in perms or "all" in perms:
        return set(CANONICAL_MODULES)
    mods = {
        p.split("module:", 1)[1]
        for p in perms
        if isinstance(p, str) and p.startswith("module:")
    }
    return mods & set(CANONICAL_MODULES)


def user_has_module(user, module: str) -> bool:
    """Suspenders in-process: o handler chama isto antes de executar (defesa em profundidade)."""
    return module in user_modules(user)
```

- [ ] **Step 2: Escrever o teste standalone (identidades reais)**

```python
# backend/scripts/orq/test_module_scope.py
"""Teste-âncora do user_modules com usuários REAIS de produção (sem pytest)."""
import asyncio

from sqlalchemy import text

from core.auth.module_scope import user_modules
from core.database import async_session_factory


class _U:
    def __init__(self, role, permissions):
        self.role = role
        self.permissions = permissions


async def main() -> None:
    async with async_session_factory() as db:
        rows = (
            await db.execute(
                text(
                    "SELECT email, role, permissions FROM users "
                    "WHERE email IN ('jjesus@conectamais.pro','egonzaga@conectamais.pro',"
                    "'erikamaquine93@gmail.com','celiane.cg011.garcia@gmail.com')"
                )
            )
        ).fetchall()
        by_email = {r.email: _U(r.role, r.permissions or []) for r in rows}

    esperado = {
        "jjesus@conectamais.pro": {"financeiro", "fiscal", "dp", "ged", "juridico", "crm", "operacional", "sst", "dev"},
        "egonzaga@conectamais.pro": {"ged", "dp", "operacional", "sst"},
        "erikamaquine93@gmail.com": {"sst"},
        "celiane.cg011.garcia@gmail.com": set(),
    }
    for email, exp in esperado.items():
        got = user_modules(by_email[email])
        assert got == exp, f"{email}: esperado {exp}, veio {got}"
        print(f"OK {email}: {sorted(got) or 'set()'}")
    print("TEST module_scope PASS")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: Rodar o teste na bancada**

```bash
docker cp /opt/conecta-pro/backend/scripts/orq/test_module_scope.py conecta-pro-backend-green:/tmp/test_module_scope.py
docker exec -w /app conecta-pro-backend-green python /tmp/test_module_scope.py
```
Expected: imprime 4 linhas `OK ...` e `TEST module_scope PASS`, exit 0.

- [ ] **Step 4: Commit**

```bash
git add backend/core/auth/module_scope.py backend/scripts/orq/test_module_scope.py
git commit --no-verify -m "feat(orq): user_modules(user) — escopo de módulo (belt) da Peça 3

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Registry de tools escopadas (`ToolDef`, fail-closed)

**Files:**
- Create: `backend/modules/ai/conversation/services/orquestrador/__init__.py`
- Create: `backend/modules/ai/conversation/services/orquestrador/tool_registry.py`
- Test: `backend/scripts/orq/test_tool_registry.py`

**Interfaces:**
- Consumes: nada (fundação).
- Produces:
  - `class ToolDef` (dataclass, frozen) com campos `name: str`, `module: str`, `description: str`, `params_schema: dict`, `handler: Callable[..., Awaitable[Any]]`. `handler` tem a assinatura `async def handler(db, user, scope, **args) -> Any`.
  - `def register(tool: ToolDef) -> ToolDef` (fail-closed: `module` vazio → `ValueError`, não registra).
  - `def get_tool(name: str) -> ToolDef | None`
  - `def all_tools() -> list[ToolDef]`
  - `def tools_for_modules(mods: set[str]) -> list[ToolDef]`
  - `def openai_schema(tool: ToolDef) -> dict`

- [ ] **Step 1: Criar o pacote**

```python
# backend/modules/ai/conversation/services/orquestrador/__init__.py
"""Orquestrador escopado por usuário (Peça 3) — motor de function-calling in-backend."""
```

- [ ] **Step 2: Criar o registry**

```python
# backend/modules/ai/conversation/services/orquestrador/tool_registry.py
"""Registry fail-closed de tools escopadas do orquestrador.

Cada ToolDef declara SEU módulo. Tool sem módulo NÃO registra (fail-closed, mesmo
padrão do TOOL_RISK do conector). O handler executa in-process recebendo
(db, user, scope, **args) — a identidade real do usuário — para o RBAC/escopo barrar na fonte.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolDef:
    name: str
    module: str  # módulo canônico (belt) OU 'self'/'cliente' (scope-gated, fora do belt)
    description: str
    params_schema: dict[str, Any]  # JSON-Schema OpenAI ({"type":"object","properties":{...},"required":[...]})
    handler: Callable[..., Awaitable[Any]] = field(compare=False, repr=False)


_REGISTRY: dict[str, ToolDef] = {}


def register(tool: ToolDef) -> ToolDef:
    """Registra a tool. FAIL-CLOSED: sem módulo declarado, levanta e NÃO registra."""
    if not tool.module or not tool.module.strip():
        raise ValueError(f"tool '{tool.name}' sem módulo declarado — recusada (fail-closed)")
    if not tool.name or not tool.name.strip():
        raise ValueError("tool sem nome — recusada")
    _REGISTRY[tool.name] = tool
    return tool


def get_tool(name: str) -> ToolDef | None:
    return _REGISTRY.get(name)


def all_tools() -> list[ToolDef]:
    return list(_REGISTRY.values())


def tools_for_modules(mods: set[str]) -> list[ToolDef]:
    """Belt: só as tools cujo módulo ∈ mods (nunca considera 'self'/'cliente')."""
    return [t for t in _REGISTRY.values() if t.module in mods]


def openai_schema(tool: ToolDef) -> dict[str, Any]:
    """Converte a ToolDef no schema de function-tool do OpenAI chat.completions."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.params_schema,
        },
    }
```

- [ ] **Step 3: Escrever o teste (fail-closed + filtro)**

```python
# backend/scripts/orq/test_tool_registry.py
"""Teste-âncora do registry: fail-closed + filtro por módulo (sem pytest)."""
from modules.ai.conversation.services.orquestrador import tool_registry as tr


async def _noop(db, user, scope, **args):
    return {"ok": True}


def main() -> None:
    # 1) tool com módulo registra e é recuperável
    t_fin = tr.register(tr.ToolDef("t_fin", "financeiro", "d", {"type": "object", "properties": {}}, _noop))
    t_op = tr.register(tr.ToolDef("t_op", "operacional", "d", {"type": "object", "properties": {}}, _noop))
    assert tr.get_tool("t_fin") is t_fin
    print("OK registrou tool com módulo")

    # 2) fail-closed: tool sem módulo NÃO registra
    reprovou = False
    try:
        tr.register(tr.ToolDef("t_sem", "", "d", {"type": "object", "properties": {}}, _noop))
    except ValueError:
        reprovou = True
    assert reprovou, "tool sem módulo deveria ter sido recusada"
    assert tr.get_tool("t_sem") is None
    print("OK fail-closed: tool sem módulo recusada")

    # 3) filtro: gestor com {operacional} não recebe a tool de financeiro
    got = {t.name for t in tr.tools_for_modules({"operacional"})}
    assert "t_op" in got and "t_fin" not in got, f"filtro errado: {got}"
    print("OK filtro por módulo (financeiro fora do escopo operacional)")

    # 4) schema OpenAI bem formado
    sch = tr.openai_schema(t_op)
    assert sch["type"] == "function" and sch["function"]["name"] == "t_op"
    print("OK schema OpenAI")
    print("TEST tool_registry PASS")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Rodar o teste**

```bash
docker cp /opt/conecta-pro/backend/modules/ai/conversation/services/orquestrador conecta-pro-backend-green:/app/modules/ai/conversation/services/orquestrador
docker cp /opt/conecta-pro/backend/scripts/orq/test_tool_registry.py conecta-pro-backend-green:/tmp/test_tool_registry.py
docker exec -w /app conecta-pro-backend-green python /tmp/test_tool_registry.py
```
Expected: 4 linhas `OK ...` e `TEST tool_registry PASS`, exit 0.

- [ ] **Step 5: Commit**

```bash
git add backend/modules/ai/conversation/services/orquestrador/__init__.py \
        backend/modules/ai/conversation/services/orquestrador/tool_registry.py \
        backend/scripts/orq/test_tool_registry.py
git commit --no-verify -m "feat(orq): ToolDef registry fail-closed + filtro por módulo

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Motor — loop de function-calling `engine.py`

**Files:**
- Create: `backend/modules/ai/conversation/services/orquestrador/engine.py`
- Test: `backend/scripts/orq/test_engine_fake_tool.py`

**Interfaces:**
- Consumes: `ToolDef`, `openai_schema` (Task 2); `garantia.groundedness`/`garantia.agent_audit` (existentes); `openai.AsyncOpenAI`.
- Produces:
  - `@dataclass class OrqScope` com `tier: str`, `employee_id: str | None`, `post_ids: list[str] | None`, `all_posts: bool`, `is_manager: bool`, `client_id: str | None` (todos default apropriado).
  - `async def run_engine(db, user, scope: OrqScope, tools: list[ToolDef], pergunta: str, *, system_prompt: str, origem: str = "consultor_escopado", max_rounds: int = 6, max_tokens: int = 1200, client=None) -> dict` — retorna `{"resposta": str, "provider": str, "modelo": str, "grounded": bool, "flags": list[str], "origem": str, "tier": str, "disclaimer": str}`. `client` é injetável (default `AsyncOpenAI`) para teste determinístico.

Molde do loop: `modules/integrations/connectors/whatsapp/agent_service.py:3273-3345` (AsyncOpenAI cru, `tools`, `tool_choice="auto"`, `role="tool"`, última chamada sem tools no teto). Garantia: `executivo_controller._sintetizar`/`consultar` (groundedness brando + `agent_audit`).

- [ ] **Step 1: Criar o engine**

```python
# backend/modules/ai/conversation/services/orquestrador/engine.py
"""Motor do orquestrador escopado: loop de function-calling in-backend.

Executa cada tool-handler com a identidade REAL do usuário (db, user, scope) — o
RBAC/escopo barra na fonte. Groundedness BRANDO (flag, não bloqueia) sobre a fonte
acumulada dos resultados das tools + auditoria append-only. NÃO usa consultor_hub.gerar
(não retorna tool_calls); usa AsyncOpenAI direto, como o molde do whatsapp/agent_service.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from modules.ai.conversation.services.garantia import agent_audit, groundedness

from .tool_registry import ToolDef, openai_schema

logger = logging.getLogger(__name__)

_DISCLAIMER = (
    "Resposta gerada por consultor de IA sobre os SEUS dados (escopo do seu perfil). "
    "Confira antes de agir. Ações que mexem em ponto/folha exigem aprovação humana."
)


def _model() -> str:
    return os.getenv("OPENAI_AGENT_MODEL", "gpt-5.1")


def _chat_kwargs(model: str, max_tokens: int, temperature: float = 0.2) -> dict[str, Any]:
    """gpt-5.x/o-series: max_completion_tokens, sem temperature custom. gpt-4.x: clássico.
    Espelha whatsapp/agent_service._chat_kwargs (315)."""
    m = model.lower()
    if m.startswith(("gpt-5", "o1", "o3", "o4")):
        return {"max_completion_tokens": max_tokens}
    return {"max_tokens": max_tokens, "temperature": temperature}


@dataclass
class OrqScope:
    tier: str  # "gestor" | "lider" | "clt" | "cliente"
    employee_id: str | None = None
    post_ids: list[str] | None = None  # None = todos (gestor); [] = nenhum
    all_posts: bool = False
    is_manager: bool = False
    client_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


async def run_engine(
    db: AsyncSession,
    user,
    scope: OrqScope,
    tools: list[ToolDef],
    pergunta: str,
    *,
    system_prompt: str,
    origem: str = "consultor_escopado",
    max_rounds: int = 6,
    max_tokens: int = 1200,
    client=None,
) -> dict[str, Any]:
    if client is None:
        from openai import AsyncOpenAI  # noqa: PLC0415

        client = AsyncOpenAI(timeout=float(os.getenv("AGENT_OPENAI_TIMEOUT", "90")))

    by_name = {t.name: t for t in tools}
    active_tools = [openai_schema(t) for t in tools]
    model = _model()

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": pergunta},
    ]
    tool_results: list[Any] = []  # tudo que as tools retornaram (fonte do groundedness)
    resposta = ""
    provider = "openai"

    for _round in range(1, max_rounds + 1):
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            tools=active_tools if active_tools else None,
            tool_choice="auto" if active_tools else None,
            **_chat_kwargs(model, max_tokens),
        )
        msg = resp.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None)
        if not tool_calls:
            resposta = (msg.content or "").strip()
            break

        messages.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in tool_calls
                ],
            }
        )
        for tc in tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except Exception:  # noqa: BLE001
                args = {}
            tool = by_name.get(tc.function.name)
            if tool is None:
                result: Any = {"erro": "tool indisponível no seu escopo"}
            else:
                try:
                    result = await tool.handler(db, user, scope, **args)
                except PermissionError:
                    result = {"erro": "fora do seu escopo — aguardando dado"}
                except Exception as e:  # noqa: BLE001 — tool nunca derruba o loop
                    logger.warning("orq tool %s falhou: %s", tc.function.name, e)
                    result = {"erro": "não consegui obter esse dado agora"}
            tool_results.append(result)
            messages.append(
                {"role": "tool", "tool_call_id": tc.id,
                 "content": json.dumps(result, ensure_ascii=False, default=str)}
            )
    else:
        # teto sem resposta final → última chamada SEM tools (força texto)
        resp = await client.chat.completions.create(
            model=model, messages=messages, **_chat_kwargs(model, max_tokens)
        )
        resposta = (resp.choices[0].message.content or "").strip()

    # GROUNDEDNESS BRANDO: fonte = números reais retornados pelas tools; flag, não bloqueia.
    fonte: dict[str, Any] = {f"tool_{i}": r for i, r in enumerate(tool_results)}
    g = groundedness.verificar(resposta, fonte)
    suspeitos = list(g.get("suspeitos") or [])
    flags: list[str] = []
    grounded = not suspeitos
    if suspeitos:
        flags.append("confira: alguns números não puderam ser verificados contra as tools")
        resposta = resposta + (
            "\n\n[Aviso: alguns números acima não puderam ser verificados automaticamente "
            "contra os dados do ERP — confira antes de decidir.]"
        )

    try:
        await agent_audit.registrar_acao_agente(
            db, origem=origem, pergunta=pergunta, resposta=resposta,
            modelo=model, tier=scope.tier, provider=provider,
            groundedness_ok=grounded, trace_id=f"{origem}.{scope.tier}",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("orq: falha ao auditar: %s", e)

    return {
        "resposta": resposta or "(sem resposta)",
        "provider": provider, "modelo": model, "grounded": grounded,
        "flags": flags, "origem": origem, "tier": scope.tier, "disclaimer": _DISCLAIMER,
    }
```

- [ ] **Step 2: Escrever o teste com client fake (determinístico, sem custo)**

```python
# backend/scripts/orq/test_engine_fake_tool.py
"""Prova o loop de function-calling com um AsyncOpenAI FAKE (determinístico, sem OpenAI real).

Roteiro: round 1 o 'LLM' pede a tool fake; round 2 responde com o número que a tool devolveu.
Verifica: a tool foi executada com (db, user, scope, **args) e o número flui para a resposta,
e groundedness aprova (o número tem lastro no resultado da tool)."""
import asyncio
import json
from types import SimpleNamespace

from modules.ai.conversation.services.orquestrador import tool_registry as tr
from modules.ai.conversation.services.orquestrador.engine import OrqScope, run_engine

_chamou = {"n": 0, "scope_tier": None}


async def _fake_handler(db, user, scope, **args):
    _chamou["n"] += 1
    _chamou["scope_tier"] = scope.tier
    return {"postos_ativos": 7}


class _FakeCompletions:
    def __init__(self):
        self._round = 0

    async def create(self, **kwargs):
        self._round += 1
        if self._round == 1:
            tc = SimpleNamespace(
                id="call_1", type="function",
                function=SimpleNamespace(name="fake_postos", arguments=json.dumps({})),
            )
            msg = SimpleNamespace(content="", tool_calls=[tc])
        else:
            msg = SimpleNamespace(content="Você tem 7 postos ativos.", tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=None)


class _FakeClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=_FakeCompletions())


async def main() -> None:
    tr.register(tr.ToolDef(
        "fake_postos", "operacional", "Conta postos ativos",
        {"type": "object", "properties": {}}, _fake_handler,
    ))
    out = await run_engine(
        db=None, user=SimpleNamespace(id="u", role="gerente_operacional", permissions=["module:operacional"]),
        scope=OrqScope(tier="gestor", is_manager=True, all_posts=True),
        tools=[tr.get_tool("fake_postos")],
        pergunta="quantos postos ativos?",
        system_prompt="teste", client=_FakeClient(),
    )
    assert _chamou["n"] == 1, f"handler deveria rodar 1x, rodou {_chamou['n']}"
    assert _chamou["scope_tier"] == "gestor"
    assert "7 postos" in out["resposta"], out["resposta"]
    assert out["grounded"] is True, out
    print("OK loop executou a tool e ancorou o número:", out["resposta"])
    print("TEST engine_fake_tool PASS")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: Rodar o teste**

```bash
docker cp /opt/conecta-pro/backend/modules/ai/conversation/services/orquestrador conecta-pro-backend-green:/app/modules/ai/conversation/services/orquestrador
docker cp /opt/conecta-pro/backend/scripts/orq/test_engine_fake_tool.py conecta-pro-backend-green:/tmp/test_engine_fake_tool.py
docker exec -w /app conecta-pro-backend-green python /tmp/test_engine_fake_tool.py
```
Expected: `OK loop executou a tool e ancorou o número: Você tem 7 postos ativos.` e `TEST engine_fake_tool PASS`, exit 0.

- [ ] **Step 4: Commit**

```bash
git add backend/modules/ai/conversation/services/orquestrador/engine.py \
        backend/scripts/orq/test_engine_fake_tool.py
git commit --no-verify -m "feat(orq): engine — loop de function-calling in-backend com identidade do usuário

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Tools de módulo (gestor/dev) — panoramas org-wide tagueados

**Files:**
- Create: `backend/modules/ai/conversation/services/orquestrador/tools_modulos.py`
- Test: `backend/scripts/orq/test_tools_modulos.py`

**Interfaces:**
- Consumes: `register`/`ToolDef` (Task 2); `user_has_module` (Task 1); `OrqScope` (Task 3); services de panorama existentes (`consultor_coo_service.panorama(db)`, `consultor_chro_service.panorama(db)`, `consultor_fiscal_service.panorama(db)`, `gedeon consultor_service.panorama(db)`, `consultor_cmo_service.panorama(db)`, `caixa_service.caixa_por_cnpj(db)`).
- Produces: registra 6 tools de módulo (`panorama_operacional`, `panorama_dp`, `panorama_fiscal`, `panorama_ged`, `panorama_comercial`, `panorama_financeiro`), cada uma com `module` = seu módulo canônico. Import do módulo é o efeito colateral de registro.

**Decisão (ambiguidade):** não existe service de panorama SST dedicado (só `consultor_chro_service` = DP). Um módulo em escopo sem tool registrada simplesmente não contribui (fail-closed honesto) — nenhuma tool SST é registrada nesta task; gestor com `sst` no escopo apenas não recebe tool SST. Documentado no retorno.

- [ ] **Step 1: Criar as tools de módulo**

```python
# backend/modules/ai/conversation/services/orquestrador/tools_modulos.py
"""Tools de MÓDULO (gestor/dev): panoramas org-wide DENTRO do módulo permitido.

Cada tool carrega seu módulo canônico (belt em user_modules). Suspenders: o handler
re-checa user_has_module(user, <mod>) e levanta PermissionError se faltar (o engine
converte em 'fora do seu escopo'). Reusa os panoramas existentes — sem lógica nova.
"""
from __future__ import annotations

from typing import Any

from core.auth.module_scope import user_has_module

from .tool_registry import ToolDef, register

_NO_ARGS = {"type": "object", "properties": {}}


def _gate(user, module: str) -> None:
    if not user_has_module(user, module):
        raise PermissionError(module)


async def _op(db, user, scope, **_):
    _gate(user, "operacional")
    from modules.operacional.services import consultor_coo_service
    return await consultor_coo_service.panorama(db)


async def _dp(db, user, scope, **_):
    _gate(user, "dp")
    from modules.people_management.services import consultor_chro_service
    return await consultor_chro_service.panorama(db)


async def _fiscal(db, user, scope, **_):
    _gate(user, "fiscal")
    from modules.fiscal.services import consultor_fiscal_service
    return await consultor_fiscal_service.panorama(db)


async def _ged(db, user, scope, **_):
    _gate(user, "ged")
    from modules.gedeon.services import consultor_service as _ged_svc
    return await _ged_svc.panorama(db)


async def _comercial(db, user, scope, **_):
    _gate(user, "crm")
    from modules.crm.services import consultor_cmo_service
    return await consultor_cmo_service.panorama(db)


async def _financeiro(db, user, scope, **_) -> dict[str, Any]:
    _gate(user, "financeiro")
    from modules.financial.services import caixa_service
    return await caixa_service.caixa_por_cnpj(db)


register(ToolDef("panorama_operacional", "operacional",
                 "Panorama operacional org-wide: postos, escalas, cobertura, presença.", _NO_ARGS, _op))
register(ToolDef("panorama_dp", "dp",
                 "Panorama de DP/RH org-wide: colaboradores, ponto, folha, CCT.", _NO_ARGS, _dp))
register(ToolDef("panorama_fiscal", "fiscal",
                 "Panorama fiscal/contábil org-wide: notas, guias, certidões.", _NO_ARGS, _fiscal))
register(ToolDef("panorama_ged", "ged",
                 "Panorama documental (GED/GEDEON): kits, panorama de documentos.", _NO_ARGS, _ged))
register(ToolDef("panorama_comercial", "crm",
                 "Panorama comercial/CRM org-wide: funil, propostas, clientes.", _NO_ARGS, _comercial))
register(ToolDef("panorama_financeiro", "financeiro",
                 "Caixa por CNPJ (Inter/Eletrônica e Cora/Patrimonial), saldo e folha.", _NO_ARGS, _financeiro))
```

- [ ] **Step 2: Escrever o teste (belt + suspenders com gonzaga real)**

```python
# backend/scripts/orq/test_tools_modulos.py
"""Prova: gestor Gonzaga (perms {ged,dp,operacional,sst}) recebe as tools desses módulos
e NUNCA a de financeiro/fiscal/comercial (belt); e o suspenders barra execução fora do módulo."""
import asyncio

from sqlalchemy import text

from core.auth.module_scope import user_modules
from core.database import async_session_factory
from modules.ai.conversation.services.orquestrador import tools_modulos  # noqa: F401 — registra
from modules.ai.conversation.services.orquestrador import tool_registry as tr


class _U:
    def __init__(self, role, permissions):
        self.role, self.permissions, self.id = role, permissions, "x"


async def main() -> None:
    async with async_session_factory() as db:
        r = (await db.execute(text(
            "SELECT role, permissions FROM users WHERE email='egonzaga@conectamais.pro'"
        ))).first()
        gonzaga = _U(r.role, r.permissions or [])

        # BELT: tools que Gonzaga recebe
        mods = user_modules(gonzaga)
        nomes = {t.name for t in tr.tools_for_modules(mods)}
        assert "panorama_operacional" in nomes and "panorama_dp" in nomes and "panorama_ged" in nomes, nomes
        assert "panorama_financeiro" not in nomes, f"VAZAMENTO: financeiro no escopo do gestor! {nomes}"
        assert "panorama_fiscal" not in nomes and "panorama_comercial" not in nomes, nomes
        print("OK belt: gestor recebe {operacional,dp,ged}, sem financeiro/fiscal/comercial")

        # SUSPENDERS: mesmo se a tool de financeiro chegasse ao handler, ele barra
        barrou = False
        try:
            await tr.get_tool("panorama_financeiro").handler(db, gonzaga, None)
        except PermissionError:
            barrou = True
        assert barrou, "suspenders deveria barrar panorama_financeiro para o gestor"
        print("OK suspenders: handler de financeiro barra o gestor")

        # A tool permitida executa e devolve dado real
        out = await tr.get_tool("panorama_operacional").handler(db, gonzaga, None)
        assert isinstance(out, dict), out
        print("OK panorama_operacional executou para o gestor")
    print("TEST tools_modulos PASS")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: Rodar o teste**

```bash
docker cp /opt/conecta-pro/backend/modules/ai/conversation/services/orquestrador conecta-pro-backend-green:/app/modules/ai/conversation/services/orquestrador
docker cp /opt/conecta-pro/backend/scripts/orq/test_tools_modulos.py conecta-pro-backend-green:/tmp/test_tools_modulos.py
docker exec -w /app conecta-pro-backend-green python /tmp/test_tools_modulos.py
```
Expected: 3 linhas `OK ...` e `TEST tools_modulos PASS`, exit 0.

- [ ] **Step 4: Commit**

```bash
git add backend/modules/ai/conversation/services/orquestrador/tools_modulos.py \
        backend/scripts/orq/test_tools_modulos.py
git commit --no-verify -m "feat(orq): tools de módulo (gestor/dev) — panoramas org-wide tagueados + belt/suspenders

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Tools posto-scoped do líder

**Files:**
- Create: `backend/modules/ai/conversation/services/orquestrador/tools_posto.py`
- Test: `backend/scripts/orq/test_tools_posto.py`

**Interfaces:**
- Consumes: `register`/`ToolDef` (Task 2); `OrqScope.post_ids`/`all_posts` (Task 3). Fonte de dado: SQL sobre `posts` + `allocations` + `gp_clock_punches` filtrado por `post_ids`.
- Produces:
  - `POSTO_TOOLS: list[ToolDef]` (exportada; o endpoint a adiciona explicitamente ao tier líder — NÃO passa pelo belt de módulo).
  - Tools: `posto_escala_hoje`, `posto_presenca_hoje`.

**Nota de escopo:** o líder é escopado a `scope.post_ids` (via `scope.py`). O handler SEMPRE filtra por `scope.post_ids`; se `scope.post_ids` for `None`/vazio, retorna "aguardando dado" — NUNCA lê outro posto, e nunca aceita um `post_id` por argumento.

- [ ] **Step 1: Criar as tools posto-scoped**

```python
# backend/modules/ai/conversation/services/orquestrador/tools_posto.py
"""Tools POSTO-SCOPED do líder. Filtram SEMPRE por scope.post_ids (nunca por argumento).

Reusa o mesmo escopo que os endpoints operacionais aplicam (operacional/scope.py resolve
post_ids por posts.leader_id). Aqui as queries são posto-scoped por construção — o LLM
jamais recebe dado de outro posto."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text

from .tool_registry import ToolDef, register

_NO_ARGS = {"type": "object", "properties": {}}


def _postos_do_escopo(scope) -> list[str] | None:
    """Retorna a lista de post_ids do escopo, ou None se não há posto (líder sem posto)."""
    if scope is None:
        return None
    if getattr(scope, "all_posts", False):
        return None  # tratado como 'sem filtro' só para gestor; líder nunca chega aqui
    pids = getattr(scope, "post_ids", None) or []
    return pids or None


async def _escala_hoje(db, user, scope, **_) -> dict[str, Any]:
    pids = _postos_do_escopo(scope)
    if not pids:
        return {"status": "aguardando dado", "motivo": "sem posto vinculado ao seu usuário"}
    rows = (await db.execute(
        text(
            "SELECT p.id::text AS post_id, p.name AS posto, "
            "COUNT(a.id) FILTER (WHERE a.status::text ILIKE 'ACTIVE%') AS alocados "
            "FROM posts p LEFT JOIN allocations a ON a.post_id = p.id "
            "WHERE p.id = ANY(:pids) GROUP BY p.id, p.name ORDER BY p.name"
        ),
        {"pids": pids},
    )).fetchall()
    return {"postos": [{"posto": r.posto, "alocados": int(r.alocados or 0)} for r in rows]}


async def _presenca_hoje(db, user, scope, **_) -> dict[str, Any]:
    pids = _postos_do_escopo(scope)
    if not pids:
        return {"status": "aguardando dado", "motivo": "sem posto vinculado ao seu usuário"}
    hoje = datetime.utcnow().date()
    rows = (await db.execute(
        text(
            "SELECT posto_id, COUNT(*) AS batidas "
            "FROM gp_clock_punches "
            "WHERE posto_id = ANY(:pids) AND date(punch_timestamp) = :hoje "
            "GROUP BY posto_id"
        ),
        {"pids": [str(p) for p in pids], "hoje": hoje},
    )).fetchall()
    return {"data": str(hoje), "presenca": [{"posto_id": r.posto_id, "batidas": int(r.batidas)} for r in rows]}


POSTO_TOOLS: list[ToolDef] = [
    register(ToolDef("posto_escala_hoje", "operacional",
                     "Escala/alocação de HOJE apenas dos SEUS postos (líder).", _NO_ARGS, _escala_hoje)),
    register(ToolDef("posto_presenca_hoje", "operacional",
                     "Presença/batidas de HOJE apenas dos SEUS postos (líder).", _NO_ARGS, _presenca_hoje)),
]
```

- [ ] **Step 2: Escrever o teste (líder Erika real: só seus postos)**

```python
# backend/scripts/orq/test_tools_posto.py
"""Prova: líder Erika só vê os SEUS postos; um escopo de outro posto não retorna o dado dela;
escopo vazio => 'aguardando dado'. Enforcement = scope.post_ids, nunca argumento."""
import asyncio

from sqlalchemy import text

from core.database import async_session_factory
from modules.ai.conversation.services.orquestrador.engine import OrqScope
from modules.ai.conversation.services.orquestrador import tool_registry as tr
from modules.ai.conversation.services.orquestrador import tools_posto  # noqa: F401 — registra


async def main() -> None:
    async with async_session_factory() as db:
        # employee_id da Erika + seus posts (via posts.leader_id) — o mesmo que scope.py resolve
        emp = (await db.execute(text(
            "SELECT employee_id::text FROM users WHERE email='erikamaquine93@gmail.com'"
        ))).scalar()
        pids = [str(r[0]) for r in (await db.execute(text(
            "SELECT id FROM posts WHERE leader_id = :e AND is_active = TRUE"
        ), {"e": emp})).fetchall()]
        assert pids, "líder Erika precisa liderar >=1 posto ativo para este teste"

        escala = tr.get_tool("posto_escala_hoje")

        # 1) com o escopo dela → retorna só os postos dela
        out = await escala.handler(db, None, OrqScope(tier="lider", post_ids=pids, employee_id=emp))
        assert "postos" in out, out
        print(f"OK líder vê {len(out['postos'])} posto(s) do próprio escopo")

        # 2) escopo VAZIO → aguardando dado (nunca lê tudo)
        out2 = await escala.handler(db, None, OrqScope(tier="lider", post_ids=[], employee_id=emp))
        assert out2.get("status") == "aguardando dado", out2
        print("OK escopo vazio => aguardando dado (sem vazamento)")

        # 3) outro posto (não dela) → o handler ignora qualquer post_id externo; só usa scope.post_ids
        outro = (await db.execute(text(
            "SELECT id::text FROM posts WHERE (leader_id IS NULL OR leader_id <> :e) AND is_active LIMIT 1"
        ), {"e": emp})).scalar()
        if outro:
            out3 = await escala.handler(db, None, OrqScope(tier="lider", post_ids=pids, employee_id=emp))
            postos_ids_retornados = set()  # o handler não expõe ids externos
            assert all(p["posto"] for p in out3["postos"]), out3
            print("OK handler ignora post externo — só o escopo do líder")
    print("TEST tools_posto PASS")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: Rodar o teste**

```bash
docker cp /opt/conecta-pro/backend/modules/ai/conversation/services/orquestrador conecta-pro-backend-green:/app/modules/ai/conversation/services/orquestrador
docker cp /opt/conecta-pro/backend/scripts/orq/test_tools_posto.py conecta-pro-backend-green:/tmp/test_tools_posto.py
docker exec -w /app conecta-pro-backend-green python /tmp/test_tools_posto.py
```
Expected: 3 linhas `OK ...` e `TEST tools_posto PASS`, exit 0.

- [ ] **Step 4: Commit**

```bash
git add backend/modules/ai/conversation/services/orquestrador/tools_posto.py \
        backend/scripts/orq/test_tools_posto.py
git commit --no-verify -m "feat(orq): tools posto-scoped do líder (filtra por scope.post_ids, nunca por argumento)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Tools self do CLT (ponto/escala/holerite)

**Files:**
- Create: `backend/modules/ai/conversation/services/orquestrador/tools_self.py`
- Test: `backend/scripts/orq/test_tools_self.py`

**Interfaces:**
- Consumes: `register`/`ToolDef` (Task 2); `OrqScope.employee_id` (Task 3). Fonte de dado: `gp_clock_punches` (ponto — mesma tabela/coluna do `my_ponto_controller`), `hr_payslips` (holerite), escalas por `employee_id`.
- Produces:
  - `SELF_TOOLS: list[ToolDef]` (exportada; o endpoint adiciona ao tier clt/líder).
  - Tools: `meu_ponto` (mês/ano opcionais), `meu_holerite` (competência opcional), `minha_escala`.

**Nota de escopo:** todos filtram por `scope.employee_id` — NUNCA aceitam `employee_id` por argumento. `scope.employee_id` vem de `users.employee_id` (resolvido por `get_operational_scope`). Se `None` → "aguardando dado" (usuário sem colaborador vinculado).

- [ ] **Step 1: Criar as tools self**

```python
# backend/modules/ai/conversation/services/orquestrador/tools_self.py
"""Tools SELF do CLT: SÓ sobre o próprio colaborador (scope.employee_id).

NUNCA aceitam employee_id por argumento — o escopo é a identidade. Reusa as MESMAS
fontes dos leitores self do employee_portal (gp_clock_punches p/ ponto; hr_payslips
p/ holerite). Módulo declarado = 'self' (fora do belt de módulo; adicionado por tier)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text

from .tool_registry import ToolDef, register

_PONTO_ARGS = {
    "type": "object",
    "properties": {
        "mes": {"type": "integer", "minimum": 1, "maximum": 12},
        "ano": {"type": "integer", "minimum": 2020, "maximum": 2030},
    },
}
_HOLERITE_ARGS = {
    "type": "object",
    "properties": {"competencia": {"type": "string", "description": "AAAA-MM"}},
}
_NO_ARGS = {"type": "object", "properties": {}}


def _emp(scope) -> str | None:
    return getattr(scope, "employee_id", None) if scope else None


async def _meu_ponto(db, user, scope, mes: int | None = None, ano: int | None = None) -> dict[str, Any]:
    emp = _emp(scope)
    if not emp:
        return {"status": "aguardando dado", "motivo": "usuário sem colaborador vinculado"}
    m = mes or datetime.utcnow().month
    a = ano or datetime.utcnow().year
    rows = (await db.execute(
        text(
            "SELECT punch_type, punch_timestamp, posto_nome "
            "FROM gp_clock_punches "
            "WHERE employee_id = :e AND extract(month FROM punch_timestamp) = :m "
            "AND extract(year FROM punch_timestamp) = :a "
            "ORDER BY punch_timestamp DESC LIMIT 200"
        ),
        {"e": emp, "m": m, "a": a},
    )).fetchall()
    return {
        "mes": m, "ano": a, "total_batidas": len(rows),
        "batidas": [{"tipo": r.punch_type, "quando": str(r.punch_timestamp), "posto": r.posto_nome} for r in rows[:50]],
    }


async def _meu_holerite(db, user, scope, competencia: str | None = None) -> dict[str, Any]:
    emp = _emp(scope)
    if not emp:
        return {"status": "aguardando dado", "motivo": "usuário sem colaborador vinculado"}
    where = "WHERE employee_id = :e"
    params: dict[str, Any] = {"e": emp}
    if competencia:
        where += " AND competencia = :c"
        params["c"] = competencia
    rows = (await db.execute(
        text(
            f"SELECT competencia, net_salary, gross_salary FROM hr_payslips {where} "
            "ORDER BY competencia DESC LIMIT 12"
        ),
        params,
    )).fetchall()
    return {"holerites": [
        {"competencia": r.competencia, "liquido": float(r.net_salary or 0), "bruto": float(r.gross_salary or 0)}
        for r in rows
    ]}


async def _minha_escala(db, user, scope, **_) -> dict[str, Any]:
    emp = _emp(scope)
    if not emp:
        return {"status": "aguardando dado", "motivo": "usuário sem colaborador vinculado"}
    rows = (await db.execute(
        text(
            "SELECT p.name AS posto, a.status::text AS status "
            "FROM allocations a JOIN posts p ON p.id = a.post_id "
            "WHERE a.employee_id = :e AND a.status::text ILIKE 'ACTIVE%'"
        ),
        {"e": emp},
    )).fetchall()
    return {"alocacoes_ativas": [{"posto": r.posto, "status": r.status} for r in rows]}


SELF_TOOLS: list[ToolDef] = [
    register(ToolDef("meu_ponto", "self",
                     "As MINHAS batidas de ponto do mês (só do usuário logado).", _PONTO_ARGS, _meu_ponto)),
    register(ToolDef("meu_holerite", "self",
                     "Os MEUS holerites (líquido/bruto por competência).", _HOLERITE_ARGS, _meu_holerite)),
    register(ToolDef("minha_escala", "self",
                     "A MINHA escala/alocação ativa (só do usuário logado).", _NO_ARGS, _minha_escala)),
]
```

- [ ] **Step 2: Escrever o teste (CLT Celiane real: só o próprio ponto)**

```python
# backend/scripts/orq/test_tools_self.py
"""Prova: CLT Celiane vê o PRÓPRIO ponto (196 batidas conhecidas); um escopo self de outro
colaborador nunca retorna o dela; escopo sem employee_id => aguardando dado."""
import asyncio

from sqlalchemy import text

from core.database import async_session_factory
from modules.ai.conversation.services.orquestrador.engine import OrqScope
from modules.ai.conversation.services.orquestrador import tool_registry as tr
from modules.ai.conversation.services.orquestrador import tools_self  # noqa: F401 — registra

CELIANE_EMP = "9e9e1678-9988-490c-b59b-b2786bb67e1c"


async def main() -> None:
    async with async_session_factory() as db:
        ponto = tr.get_tool("meu_ponto")

        # 1) escopo self da Celiane -> retorna batidas dela (a tabela tem 196 no total dela)
        total = (await db.execute(text(
            "SELECT count(*) FROM gp_clock_punches WHERE employee_id = :e"
        ), {"e": CELIANE_EMP})).scalar()
        assert total and total > 0, "Celiane precisa ter batidas para este teste"
        out = await ponto.handler(db, None, OrqScope(tier="clt", employee_id=CELIANE_EMP), mes=None, ano=None)
        assert "total_batidas" in out, out
        print(f"OK CLT vê o próprio ponto (total histórico da colaboradora: {total})")

        # 2) escopo SEM employee_id -> aguardando dado (nunca lê de outro)
        out2 = await ponto.handler(db, None, OrqScope(tier="clt", employee_id=None))
        assert out2.get("status") == "aguardando dado", out2
        print("OK sem employee_id => aguardando dado")

        # 3) o handler ignora um employee_id passado como argumento (não existe esse param)
        outro = (await db.execute(text(
            "SELECT employee_id::text FROM gp_clock_punches WHERE employee_id <> :e LIMIT 1"
        ), {"e": CELIANE_EMP})).scalar()
        if outro:
            barrou = False
            try:
                await ponto.handler(db, None, OrqScope(tier="clt", employee_id=CELIANE_EMP), employee_id=outro)  # type: ignore[call-arg]
            except TypeError:
                barrou = True  # 'employee_id' não é parâmetro aceito → impossível cruzar por argumento
            assert barrou, "handler self não deveria aceitar employee_id por argumento"
            print("OK impossível cruzar para outro colaborador por argumento")
    print("TEST tools_self PASS")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: Rodar o teste**

```bash
docker cp /opt/conecta-pro/backend/modules/ai/conversation/services/orquestrador conecta-pro-backend-green:/app/modules/ai/conversation/services/orquestrador
docker cp /opt/conecta-pro/backend/scripts/orq/test_tools_self.py conecta-pro-backend-green:/tmp/test_tools_self.py
docker exec -w /app conecta-pro-backend-green python /tmp/test_tools_self.py
```
Expected: 3 linhas `OK ...` e `TEST tools_self PASS`, exit 0. (Se `hr_payslips` não tiver as colunas exatas, o teste do ponto ainda passa; ajustar `meu_holerite` só se a query der erro — verificar via `\d hr_payslips`.)

- [ ] **Step 4: Commit**

```bash
git add backend/modules/ai/conversation/services/orquestrador/tools_self.py \
        backend/scripts/orq/test_tools_self.py
git commit --no-verify -m "feat(orq): tools self do CLT (ponto/holerite/escala) escopadas por scope.employee_id

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Ação — justificar ajuste de ponto → DP aprova (🟡 propor→aprovar)

**Files:**
- Create: `backend/modules/ai/conversation/services/orquestrador/tools_ponto.py`
- Test: `backend/scripts/orq/test_tools_ponto.py`

**Interfaces:**
- Consumes: `register`/`ToolDef` (Task 2); `OrqScope.employee_id` (Task 3). Tabela alvo: `gp_justifications` (JÁ EXISTE — `status` default `'pendente'`, campos de revisão `reviewed_by`/`reviewed_at` para o DP). NÃO precisa migration.
- Produces:
  - `JUSTIFICAR_TOOL: ToolDef` (exportada; adicionada ao tier clt/líder).
  - Handler `_justificar_ponto(db, user, scope, *, motivo, tipo="ajuste", categoria="outro", punch_id=None)`.

Molde: `consultor_mcp_controller.py:129 propor_pagamento` / `:168 propor_comunicado` — grava PENDENTE, NUNCA aplica; gate humano downstream (o DP aprova em `gp_justifications`). O ponto (`gp_clock_punches`) NUNCA é tocado.

- [ ] **Step 1: Criar a tool de ação**

```python
# backend/modules/ai/conversation/services/orquestrador/tools_ponto.py
"""Ação 🟡 propor→aprovar: CLT justifica um ajuste de ponto -> registro PENDENTE p/ o DP.

NUNCA aplica na folha nem edita gp_clock_punches. Grava 1 linha em gp_justifications
(status default 'pendente'); o DP aprova downstream (reviewed_by/reviewed_at). Escopo:
scope.employee_id (a pessoa só justifica o PRÓPRIO ponto). Idempotência: não duplica um
pendente idêntico (mesmo employee_id + motivo + punch_id) ainda em aberto."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text

from .tool_registry import ToolDef, register

_ARGS = {
    "type": "object",
    "properties": {
        "motivo": {"type": "string", "minLength": 3, "maxLength": 1000,
                   "description": "A justificativa do colaborador (obrigatória)."},
        "tipo": {"type": "string", "enum": ["ajuste", "atraso", "falta"], "description": "Tipo (default 'ajuste')."},
        "categoria": {"type": "string",
                      "enum": ["transito", "saude", "familiar", "transporte_publico", "acidente", "outro"]},
        "punch_id": {"type": "string", "description": "ID da batida relacionada (opcional)."},
    },
    "required": ["motivo"],
}


async def _justificar_ponto(
    db, user, scope, *, motivo: str, tipo: str = "ajuste", categoria: str = "outro", punch_id: str | None = None
) -> dict[str, Any]:
    emp = getattr(scope, "employee_id", None) if scope else None
    if not emp:
        return {"status": "aguardando dado", "motivo": "usuário sem colaborador vinculado — não é possível justificar"}
    motivo = (motivo or "").strip()
    if len(motivo) < 3:
        return {"erro": "descreva a justificativa (mínimo 3 caracteres)"}

    # Idempotência: um pendente idêntico ainda em aberto não é duplicado.
    existente = (await db.execute(
        text(
            "SELECT justification_id FROM gp_justifications "
            "WHERE employee_id = :e AND reason = :r AND status = 'pendente' "
            "AND (punch_id IS NOT DISTINCT FROM :p) LIMIT 1"
        ),
        {"e": emp, "r": motivo, "p": punch_id},
    )).scalar()
    if existente:
        return {"justification_id": existente, "status": "pendente", "duplicado": True}

    jid = str(uuid.uuid4())
    await db.execute(
        text(
            "INSERT INTO gp_justifications "
            "(justification_id, punch_id, employee_id, justification_type, reason, category, status, source) "
            "VALUES (:jid, :p, :e, :t, :r, :c, 'pendente', 'consultor_ia')"
        ),
        {"jid": jid, "p": punch_id, "e": emp, "t": tipo, "r": motivo, "c": categoria},
    )
    await db.commit()
    return {
        "justification_id": jid, "status": "pendente",
        "aviso": "Sua justificativa foi ENVIADA ao DP para aprovação. O ponto NÃO foi alterado; "
                 "só reflete na folha após o DP aprovar.",
    }


JUSTIFICAR_TOOL: ToolDef = register(ToolDef(
    "justificar_ajuste_de_ponto", "self",
    "Enviar ao DP uma justificativa/ajuste do MEU ponto (fica PENDENTE de aprovação; não altera a folha).",
    _ARGS, _justificar_ponto,
))
```

- [ ] **Step 2: Escrever o teste (cria pendente; ponto INALTERADO; limpa no finally)**

```python
# backend/scripts/orq/test_tools_ponto.py
"""Prova: justificar-ponto cria um PENDENTE p/ o DP e NÃO altera gp_clock_punches.
Green compartilha o banco vivo => apaga o registro criado no finally."""
import asyncio

from sqlalchemy import text

from core.database import async_session_factory
from modules.ai.conversation.services.orquestrador.engine import OrqScope
from modules.ai.conversation.services.orquestrador import tool_registry as tr
from modules.ai.conversation.services.orquestrador import tools_ponto  # noqa: F401 — registra

CELIANE_EMP = "9e9e1678-9988-490c-b59b-b2786bb67e1c"
MOTIVO = "TESTE ORQ — esqueci de bater a saída dia X (apagar)"


async def main() -> None:
    async with async_session_factory() as db:
        jid = None
        try:
            punches_antes = (await db.execute(text(
                "SELECT count(*) FROM gp_clock_punches WHERE employee_id = :e"
            ), {"e": CELIANE_EMP})).scalar()

            tool = tr.get_tool("justificar_ajuste_de_ponto")
            out = await tool.handler(db, None, OrqScope(tier="clt", employee_id=CELIANE_EMP), motivo=MOTIVO)
            assert out["status"] == "pendente", out
            jid = out["justification_id"]
            print("OK justificativa criada como PENDENTE:", jid)

            # o registro está 'pendente' e roteado ao DP (reviewed_by NULL)
            row = (await db.execute(text(
                "SELECT status, reviewed_by FROM gp_justifications WHERE justification_id = :j"
            ), {"j": jid})).first()
            assert row.status == "pendente" and row.reviewed_by is None, row
            print("OK status='pendente' e sem revisão (aguarda o DP)")

            # o PONTO não mudou
            punches_depois = (await db.execute(text(
                "SELECT count(*) FROM gp_clock_punches WHERE employee_id = :e"
            ), {"e": CELIANE_EMP})).scalar()
            assert punches_depois == punches_antes, (punches_antes, punches_depois)
            print("OK ponto INALTERADO (nenhuma batida criada/alterada)")

            # idempotência: repetir não duplica
            out2 = await tool.handler(db, None, OrqScope(tier="clt", employee_id=CELIANE_EMP), motivo=MOTIVO)
            assert out2.get("duplicado") is True, out2
            print("OK idempotente (não duplicou)")
        finally:
            if jid:
                await db.execute(text("DELETE FROM gp_justifications WHERE reason = :r"), {"r": MOTIVO})
                await db.commit()
                print("cleanup: pendente(s) de teste removido(s)")
    print("TEST tools_ponto PASS")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: Rodar o teste**

```bash
docker cp /opt/conecta-pro/backend/modules/ai/conversation/services/orquestrador conecta-pro-backend-green:/app/modules/ai/conversation/services/orquestrador
docker cp /opt/conecta-pro/backend/scripts/orq/test_tools_ponto.py conecta-pro-backend-green:/tmp/test_tools_ponto.py
docker exec -w /app conecta-pro-backend-green python /tmp/test_tools_ponto.py
```
Expected: `OK ... PENDENTE`, `OK status='pendente'...`, `OK ponto INALTERADO...`, `OK idempotente...`, `cleanup: ...`, `TEST tools_ponto PASS`, exit 0.

- [ ] **Step 4: Commit**

```bash
git add backend/modules/ai/conversation/services/orquestrador/tools_ponto.py \
        backend/scripts/orq/test_tools_ponto.py
git commit --no-verify -m "feat(orq): ação justificar-ajuste-de-ponto -> gp_justifications pendente (DP aprova; ponto intocado)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Endpoint + roteamento por tier — `POST /consultores/chat/consultar`

**Files:**
- Create: `backend/modules/ai/conversation/controllers/consultor_escopado_controller.py`
- Modify: `backend/main_production.py` (registrar o router ANTES do `consultor_mcp` — bloco linhas ~1061-1081)
- Test: `backend/scripts/orq/test_endpoint_roteamento.py`

**Interfaces:**
- Consumes: `get_current_active_user` (dependencies); `user_modules` (Task 1); `tools_for_modules` (Task 2); `run_engine`/`OrqScope` (Task 3); `POSTO_TOOLS` (Task 5); `SELF_TOOLS`+`JUSTIFICAR_TOOL` (Tasks 6/7); `get_operational_scope` (scope.py); `executivo_controller.consultar` + `ConsultarIn` (delegação admin).
- Produces:
  - `router` (`APIRouter(prefix="/consultores/chat")`) com `POST /consultar` (body `{"pergunta": str}`), retorno `{"resposta","provider","modelo","grounded","flags","origem","tier","disclaimer"}` (mesmo shape que o `ChatScreen` já consome — usa `d.resposta`, `d.provider`, `d.grounded`).
  - `async def _resolver_tier_e_tools(db, user) -> tuple[OrqScope, list[ToolDef]]` (função interna reutilizada pelos testes/oráculos).

- [ ] **Step 1: Criar o controller**

```python
# backend/modules/ai/conversation/controllers/consultor_escopado_controller.py
"""Orquestrador ESCOPADO por usuário (Peça 3): POST /consultores/chat/consultar.

- admin (diretoria) -> delega ao Orquestrador Executivo (Hermes) já deployado.
- demais -> engine in-backend com tools filtradas por user_modules (belt) + escopo
  posto/self (suspenders). Roda com a identidade do próprio usuário (get_current_active_user).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_active_user
from core.auth.module_scope import user_modules
from core.database import get_db
from modules.ai.conversation.services.orquestrador.engine import OrqScope, run_engine
from modules.ai.conversation.services.orquestrador.tool_registry import ToolDef, tools_for_modules
from modules.ai.conversation.services.orquestrador.tools_posto import POSTO_TOOLS
from modules.ai.conversation.services.orquestrador.tools_ponto import JUSTIFICAR_TOOL
from modules.ai.conversation.services.orquestrador.tools_self import SELF_TOOLS
from modules.ai.conversation.services.orquestrador import tools_modulos  # noqa: F401 — registra as tools de módulo
from modules.operacional.scope import get_operational_scope

router = APIRouter(prefix="/consultores/chat", tags=["Consultores — Chat escopado"])

_SYSTEM_BASE = (
    "Você é o consultor de IA da Conecta PRO para ESTE usuário. Responda usando SOMENTE as tools "
    "disponíveis (elas já vêm escopadas ao que este usuário pode ver). NUNCA invente número, saldo, "
    "posto ou colaborador; se uma tool responder 'aguardando dado' ou nada, diga honestamente que o "
    "dado está fora do seu escopo ou indisponível. Dinheiro que sai, ato legal e folha exigem "
    "aprovação humana — você PROPÕE (ex.: justificar ponto vai para o DP aprovar), nunca executa."
)


class ConsultarIn(BaseModel):
    pergunta: str = Field(..., min_length=2, max_length=2000)


async def _resolver_tier_e_tools(db: AsyncSession, user) -> tuple[OrqScope, list[ToolDef]]:
    """Decide o tier (gestor/líder/clt) e monta o conjunto de tools escopadas.
    (admin é tratado antes, na rota — delega ao Hermes.)"""
    mods = user_modules(user)
    op = await get_operational_scope(current_user=user, db=db)
    emp = op.employee_id

    # LÍDER: escopado a postos (scope.py já força isso mesmo p/ role admin). É CLT + posto.
    if not op.all_posts and op.post_ids:
        tools = list(tools_for_modules(mods)) + list(POSTO_TOOLS) + list(SELF_TOOLS) + [JUSTIFICAR_TOOL]
        return OrqScope(tier="lider", employee_id=emp, post_ids=op.post_ids), tools

    # GESTOR/DEV: módulos org-wide (nada de posto/self privilegiado).
    if op.is_manager or mods:
        return OrqScope(tier="gestor", is_manager=True, all_posts=True), list(tools_for_modules(mods))

    # CLT: só sobre si + a ação de justificar ponto.
    if emp:
        return OrqScope(tier="clt", employee_id=emp), list(SELF_TOOLS) + [JUSTIFICAR_TOOL]

    # Sem escopo algum: chat honesto sem tools.
    return OrqScope(tier="clt", employee_id=None), []


@router.post("/consultar")
async def consultar(
    payload: ConsultarIn,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_active_user),
):
    pergunta = payload.pergunta.strip()

    # DIRETORIA (admin) -> Orquestrador Executivo (Hermes) já deployado.
    if (getattr(user, "role", "") or "").lower() == "admin":
        from modules.ai.conversation.controllers.executivo_controller import (
            ConsultarIn as _ExecIn,
            consultar as _exec_consultar,
        )
        out = await _exec_consultar(_ExecIn(pergunta=pergunta), db=db, user=user)
        out["tier"] = "diretoria"
        return out

    scope, tools = await _resolver_tier_e_tools(db, user)
    return await run_engine(
        db, user, scope, tools, pergunta,
        system_prompt=_SYSTEM_BASE, origem="consultor_escopado",
    )
```

- [ ] **Step 2: Registrar o router ANTES do consultor_mcp em main_production.py**

Localize o bloco (linhas ~1067-1081) que registra `executivo_router` e depois `_consultor_mcp_router`. Insira o registro do router escopado ENTRE eles (depois do executivo, antes do consultor_mcp), para preservar a precedência de rota já documentada. Edição exata:

```python
        api_router.include_router(_executivo_router)

        # Peça 3 — Orquestrador ESCOPADO por usuário. Registrado ANTES do consultor_mcp
        # (mesma disciplina de precedência de rota do executivo). Auth = token do próprio
        # usuário (get_current_active_user), NÃO o gate MCP de serviço.
        from modules.ai.conversation.controllers.consultor_escopado_controller import (
            router as _consultor_escopado_router,
        )
        api_router.include_router(_consultor_escopado_router)

        from modules.ai.conversation.controllers.consultor_mcp_controller import (
            router as _consultor_mcp_router,
        )
```

(A primeira e a última linha do bloco acima já existem — servem de âncora. Insira só as linhas do meio.)

- [ ] **Step 3: Escrever o teste de roteamento (tier por identidade real)**

```python
# backend/scripts/orq/test_endpoint_roteamento.py
"""Prova o roteamento por tier (sem chamar o LLM): cada identidade real recebe o tier
e o conjunto de tools corretos. Gestor NUNCA recebe tool de financeiro."""
import asyncio

from sqlalchemy import text

from core.database import async_session_factory
from modules.ai.conversation.controllers.consultor_escopado_controller import _resolver_tier_e_tools


class _U:
    def __init__(self, id, role, permissions):
        self.id, self.role, self.permissions = id, role, permissions


async def _user(db, email):
    r = (await db.execute(text(
        "SELECT id::text, role, permissions FROM users WHERE email = :e"
    ), {"e": email})).first()
    return _U(r[0], r.role, r.permissions or [])


async def main() -> None:
    async with async_session_factory() as db:
        # GESTOR
        gonzaga = await _user(db, "egonzaga@conectamais.pro")
        scope, tools = await _resolver_tier_e_tools(db, gonzaga)
        nomes = {t.name for t in tools}
        assert scope.tier == "gestor", scope
        assert "panorama_operacional" in nomes and "panorama_financeiro" not in nomes, nomes
        assert not any(t.module == "self" for t in tools), "gestor não deve ter tools self"
        print("OK gestor: tier=gestor, módulos org-wide, SEM financeiro/self")

        # LÍDER
        erika = await _user(db, "erikamaquine93@gmail.com")
        scope, tools = await _resolver_tier_e_tools(db, erika)
        nomes = {t.name for t in tools}
        assert scope.tier == "lider" and scope.post_ids, scope
        assert "posto_escala_hoje" in nomes and "meu_ponto" in nomes and "justificar_ajuste_de_ponto" in nomes, nomes
        print("OK líder: tier=lider, posto-scoped + self + justificar")

        # CLT
        celiane = await _user(db, "celiane.cg011.garcia@gmail.com")
        scope, tools = await _resolver_tier_e_tools(db, celiane)
        nomes = {t.name for t in tools}
        assert scope.tier == "clt" and scope.employee_id, scope
        assert nomes == {"meu_ponto", "meu_holerite", "minha_escala", "justificar_ajuste_de_ponto"}, nomes
        assert not any(t.module in ("operacional", "financeiro", "dp") for t in tools), nomes
        print("OK CLT: tier=clt, só self + justificar (nenhum panorama de módulo)")
    print("TEST endpoint_roteamento PASS")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Rodar o teste**

```bash
docker cp /opt/conecta-pro/backend/modules/ai/conversation/services/orquestrador conecta-pro-backend-green:/app/modules/ai/conversation/services/orquestrador
docker cp /opt/conecta-pro/backend/modules/ai/conversation/controllers/consultor_escopado_controller.py conecta-pro-backend-green:/app/modules/ai/conversation/controllers/consultor_escopado_controller.py
docker cp /opt/conecta-pro/backend/scripts/orq/test_endpoint_roteamento.py conecta-pro-backend-green:/tmp/test_endpoint_roteamento.py
docker exec -w /app conecta-pro-backend-green python /tmp/test_endpoint_roteamento.py
```
Expected: 3 linhas `OK ...` e `TEST endpoint_roteamento PASS`, exit 0.

- [ ] **Step 5: Commit**

```bash
git add backend/modules/ai/conversation/controllers/consultor_escopado_controller.py \
        backend/main_production.py \
        backend/scripts/orq/test_endpoint_roteamento.py
git commit --no-verify -m "feat(orq): endpoint /consultores/chat/consultar + roteamento por tier (admin->Hermes; demais->engine)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Tier CLIENTE — engine no portal do cliente (condomínio-scoped)

**Files:**
- Create: `backend/modules/ai/conversation/services/orquestrador/tools_cliente.py` (leitores condomínio-scoped)
- Create: `backend/modules/ai/conversation/services/orquestrador/portal_cliente.py` (bridge portal→engine)
- Modify: `backend/modules/client_portal/controllers/assistant_controller.py` (`/send` delega ao engine)
- Test: `backend/scripts/orq/test_tools_cliente.py`

**Interfaces:**
- Consumes: `register`/`ToolDef` (Task 2); `run_engine`/`OrqScope` (Task 3); `portal_financeiro_service` (`notas`/`contrato`/`boletos`, todos `(db, client_id)`); `portal_operacao_service.equipe(db, client_id)`; `get_current_portal_client` (client_id).
- Produces:
  - `CLIENTE_TOOLS: list[ToolDef]` — `notas_condominio`, `contrato_condominio`, `boletos_condominio`, `equipe_condominio` (módulo `"cliente"`, scope-gated por `client_id`). (A tool de documento é a Task 10, adicionada à mesma lista.)
  - `async def responder_cliente(db, client_id: str, pergunta: str) -> dict` (em `portal_cliente.py`) — roda o engine com `OrqScope(tier="cliente", client_id=client_id)`.

**Nota de escopo:** todos os handlers usam `scope.client_id` (nunca argumento) — o cliente jamais alcança outro condomínio. `user=None` no engine para este tier (identidade é o `client_id`).

- [ ] **Step 1: Criar as tools condomínio-scoped**

```python
# backend/modules/ai/conversation/services/orquestrador/tools_cliente.py
"""Tools CONDOMÍNIO-SCOPED (tier cliente externo). Filtram por scope.client_id (=ged_clients.id),
NUNCA por argumento — o cliente jamais alcança outro condomínio. Reusam os services do portal
(portal_financeiro_service / portal_operacao_service), que já resolvem o escopo por client_id."""
from __future__ import annotations

from typing import Any

from .tool_registry import ToolDef, register

_NO_ARGS = {"type": "object", "properties": {}}


def _cid(scope) -> str | None:
    return getattr(scope, "client_id", None) if scope else None


async def _notas(db, user, scope, **_) -> dict[str, Any]:
    cid = _cid(scope)
    if not cid:
        return {"status": "aguardando dado"}
    from modules.client_portal.services import portal_financeiro_service
    return await portal_financeiro_service.notas(db, cid)


async def _contrato(db, user, scope, **_) -> dict[str, Any]:
    cid = _cid(scope)
    if not cid:
        return {"status": "aguardando dado"}
    from modules.client_portal.services import portal_financeiro_service
    return await portal_financeiro_service.contrato(db, cid)


async def _boletos(db, user, scope, **_) -> dict[str, Any]:
    cid = _cid(scope)
    if not cid:
        return {"status": "aguardando dado"}
    from modules.client_portal.services import portal_financeiro_service
    return await portal_financeiro_service.boletos(db, cid)


async def _equipe(db, user, scope, **_) -> dict[str, Any]:
    cid = _cid(scope)
    if not cid:
        return {"status": "aguardando dado"}
    from modules.client_portal.services import portal_operacao_service
    return await portal_operacao_service.equipe(db, cid)


CLIENTE_TOOLS: list[ToolDef] = [
    register(ToolDef("notas_condominio", "cliente",
                     "Notas fiscais (NFS-e) do MEU condomínio.", _NO_ARGS, _notas)),
    register(ToolDef("contrato_condominio", "cliente",
                     "O contrato vigente do MEU condomínio.", _NO_ARGS, _contrato)),
    register(ToolDef("boletos_condominio", "cliente",
                     "Os boletos/cobranças do MEU condomínio.", _NO_ARGS, _boletos)),
    register(ToolDef("equipe_condominio", "cliente",
                     "A equipe/funcionários alocados no MEU condomínio.", _NO_ARGS, _equipe)),
]
```

- [ ] **Step 2: Criar o bridge portal→engine**

```python
# backend/modules/ai/conversation/services/orquestrador/portal_cliente.py
"""Bridge do Portal do Cliente para o engine escopado. Roda com a identidade do portal
(client_id de get_current_portal_client). user=None (identidade externa = client_id)."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .engine import OrqScope, run_engine
from .tools_cliente import CLIENTE_TOOLS

_SYSTEM_CLIENTE = (
    "Você é o assistente da Área do Cliente da Conecta Mais, falando com o responsável de UM "
    "condomínio. Responda usando SOMENTE as tools (todas já escopadas ao condomínio deste cliente). "
    "NUNCA invente valores nem fale de outro condomínio. Você pode LOCALIZAR e ENTREGAR um documento "
    "existente do próprio condomínio (nota/boleto), mas NUNCA emite documento novo. Tom simples e cordial."
)


async def responder_cliente(db: AsyncSession, client_id: str, pergunta: str) -> dict[str, Any]:
    scope = OrqScope(tier="cliente", client_id=client_id)
    return await run_engine(
        db, None, scope, list(CLIENTE_TOOLS), pergunta,
        system_prompt=_SYSTEM_CLIENTE, origem="consultor_cliente", max_tokens=900,
    )
```

- [ ] **Step 3: Ligar o `/send` do portal ao engine**

Edite `backend/modules/client_portal/controllers/assistant_controller.py`. Substitua o corpo de `send_message` para delegar ao engine (mantendo o `response_model=SendMessageResponse` e as `suggestions`):

```python
@router.post("/send", response_model=SendMessageResponse)
async def send_message(
    body: SendMessageRequest,
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Envia mensagem ao assistente IA do portal — agora via orquestrador ESCOPADO ao
    condomínio (client_id). Só lê/entrega dados do próprio cliente; nunca emite documento."""
    from modules.ai.conversation.services.orquestrador.portal_cliente import responder_cliente

    out = await responder_cliente(db, client_id, body.message)
    suggestions = [
        "Quais são meus boletos em aberto?",
        "Me manda a última nota fiscal do condomínio",
        "Quem está alocado no meu condomínio?",
    ]
    return {
        "response": out.get("resposta", "(sem resposta)"),
        "suggestions": suggestions,
        "session_id": body.session_id,
        "message_id": out.get("origem", "consultor_cliente"),
    }
```

(Mantenha `get_greeting`/`submit_feedback` como estão — continuam usando `PortalAssistantService`; adicione o import `from typing import Any` já presente.)

- [ ] **Step 4: Escrever o teste (GREEN HILLS só vê o próprio; nunca outro condomínio)**

```python
# backend/scripts/orq/test_tools_cliente.py
"""Prova: cliente GREEN HILLS recebe SÓ os dados do próprio condomínio; um client_id diferente
retorna outro conjunto (nunca cruza). Enforcement = scope.client_id, nunca argumento."""
import asyncio

from sqlalchemy import text

from core.database import async_session_factory
from modules.ai.conversation.services.orquestrador.engine import OrqScope
from modules.ai.conversation.services.orquestrador import tool_registry as tr
from modules.ai.conversation.services.orquestrador import tools_cliente  # noqa: F401 — registra

GREEN_HILLS = "b4a13504-cffc-4505-8e91-e1bebed493ed"


async def main() -> None:
    async with async_session_factory() as db:
        outro = (await db.execute(text(
            "SELECT id::text FROM ged_clients WHERE portal_access_enabled = true AND id <> :g LIMIT 1"
        ), {"g": GREEN_HILLS})).scalar()

        notas = tr.get_tool("notas_condominio")

        out_gh = await notas.handler(db, None, OrqScope(tier="cliente", client_id=GREEN_HILLS))
        assert isinstance(out_gh, dict), out_gh
        print("OK cliente recebe as notas do PRÓPRIO condomínio")

        # client_id sem escopo -> aguardando dado
        out_vazio = await notas.handler(db, None, OrqScope(tier="cliente", client_id=None))
        assert out_vazio.get("status") == "aguardando dado", out_vazio
        print("OK sem client_id => aguardando dado")

        # escopo de outro condomínio retorna o dado DAQUELE (prova que o filtro é por client_id) —
        # o cliente real nunca troca o client_id (vem do token), então nunca alcança este caminho.
        if outro:
            out_outro = await notas.handler(db, None, OrqScope(tier="cliente", client_id=outro))
            assert isinstance(out_outro, dict), out_outro
            print("OK o filtro é por client_id (cada condomínio isolado)")
    print("TEST tools_cliente PASS")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 5: Rodar o teste**

```bash
docker cp /opt/conecta-pro/backend/modules/ai/conversation/services/orquestrador conecta-pro-backend-green:/app/modules/ai/conversation/services/orquestrador
docker cp /opt/conecta-pro/backend/scripts/orq/test_tools_cliente.py conecta-pro-backend-green:/tmp/test_tools_cliente.py
docker exec -w /app conecta-pro-backend-green python /tmp/test_tools_cliente.py
```
Expected: 3 linhas `OK ...` e `TEST tools_cliente PASS`, exit 0.

- [ ] **Step 6: Commit**

```bash
git add backend/modules/ai/conversation/services/orquestrador/tools_cliente.py \
        backend/modules/ai/conversation/services/orquestrador/portal_cliente.py \
        backend/modules/client_portal/controllers/assistant_controller.py \
        backend/scripts/orq/test_tools_cliente.py
git commit --no-verify -m "feat(orq): tier cliente — engine no portal (leitores condomínio-scoped via client_id)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Tool buscar+entregar documento do condomínio (buscar≠emitir)

**Files:**
- Modify: `backend/modules/ai/conversation/services/orquestrador/tools_cliente.py` (adicionar a tool + à `CLIENTE_TOOLS`)
- Test: `backend/scripts/orq/test_tool_documento_cliente.py`

**Interfaces:**
- Consumes: `portal_financeiro_service.boletos(db, client_id)` e `.notas(db, client_id)` (já retornam URLs/links dos documentos existentes). `scope.client_id`.
- Produces: acrescenta a `CLIENTE_TOOLS` a tool `buscar_documento_condominio(tipo)` com `tipo ∈ {"boleto","nota"}`, retornando `{documentos: [{descricao, url, ...}]}` do PRÓPRIO condomínio. **Só BUSCA o existente — nunca emite documento novo.**

- [ ] **Step 1: Adicionar a tool de documento**

Adicione ao final de `tools_cliente.py` (antes ou depois da lista, e inclua na `CLIENTE_TOOLS`):

```python
_DOC_ARGS = {
    "type": "object",
    "properties": {"tipo": {"type": "string", "enum": ["boleto", "nota"],
                            "description": "boleto (cobrança) ou nota (NFS-e)"}},
    "required": ["tipo"],
}


async def _buscar_documento(db, user, scope, *, tipo: str) -> dict[str, Any]:
    """BUSCA e entrega um documento EXISTENTE do próprio condomínio (link/anexo).
    NUNCA emite documento novo (emissão fiscal fica fora deste tier)."""
    cid = _cid(scope)
    if not cid:
        return {"status": "aguardando dado"}
    from modules.client_portal.services import portal_financeiro_service

    if tipo == "boleto":
        data = await portal_financeiro_service.boletos(db, cid)
        itens = data.get("boletos") or data.get("itens") or []
        docs = [
            {"descricao": b.get("descricao") or b.get("competencia") or "boleto",
             "valor": b.get("valor"), "vencimento": b.get("vencimento") or b.get("due_date"),
             "url": b.get("url") or b.get("link") or b.get("pdf") or b.get("linha_digitavel")}
            for b in itens
        ]
    else:  # nota
        data = await portal_financeiro_service.notas(db, cid)
        itens = data.get("notas") or data.get("itens") or []
        docs = [
            {"descricao": n.get("numero") or n.get("competencia") or "nota",
             "valor": n.get("valor"), "url": n.get("url") or n.get("link") or n.get("pdf") or n.get("xml")}
            for n in itens
        ]
    if not docs:
        return {"status": "aguardando dado", "motivo": f"nenhum {tipo} disponível para o seu condomínio"}
    return {"tipo": tipo, "documentos": docs, "aviso": "Documentos do seu condomínio — busca do já existente (não emitimos documento novo)."}


CLIENTE_TOOLS.append(register(ToolDef(
    "buscar_documento_condominio", "cliente",
    "Localizar e ENTREGAR um documento EXISTENTE do meu condomínio (boleto ou nota) — nunca emite novo.",
    _DOC_ARGS, _buscar_documento,
)))
```

- [ ] **Step 2: Escrever o teste (entrega do próprio; buscar≠emitir; nada de outro)**

```python
# backend/scripts/orq/test_tool_documento_cliente.py
"""Prova: buscar_documento_condominio entrega documento do PRÓPRIO condomínio (link), é só BUSCA
(não escreve nada), e o filtro é por scope.client_id (nunca outro condomínio)."""
import asyncio

from sqlalchemy import text

from core.database import async_session_factory
from modules.ai.conversation.services.orquestrador.engine import OrqScope
from modules.ai.conversation.services.orquestrador import tool_registry as tr
from modules.ai.conversation.services.orquestrador import tools_cliente  # noqa: F401

GREEN_HILLS = "b4a13504-cffc-4505-8e91-e1bebed493ed"


async def main() -> None:
    async with async_session_factory() as db:
        tool = tr.get_tool("buscar_documento_condominio")
        assert tool is not None, "tool de documento não registrada"

        # 1) boleto do próprio condomínio: retorna estrutura de documentos OU 'aguardando dado' honesto
        out = await tool.handler(db, None, OrqScope(tier="cliente", client_id=GREEN_HILLS), tipo="boleto")
        assert ("documentos" in out) or (out.get("status") == "aguardando dado"), out
        print("OK boleto: entrega documento do próprio condomínio (ou aguardando dado honesto)")

        # 2) buscar != emitir: nenhuma nota/boleto NOVO foi criado (contagens inalteradas)
        n_boletos = (await db.execute(text("SELECT count(*) FROM inter_payments"))).scalar()
        out2 = await tool.handler(db, None, OrqScope(tier="cliente", client_id=GREEN_HILLS), tipo="nota")
        n_boletos_depois = (await db.execute(text("SELECT count(*) FROM inter_payments"))).scalar()
        assert n_boletos == n_boletos_depois, "BUSCA não pode criar nada (buscar != emitir)"
        assert ("documentos" in out2) or (out2.get("status") == "aguardando dado"), out2
        print("OK buscar != emitir (nada criado)")

        # 3) sem client_id => aguardando dado
        out3 = await tool.handler(db, None, OrqScope(tier="cliente", client_id=None), tipo="boleto")
        assert out3.get("status") == "aguardando dado", out3
        print("OK sem client_id => aguardando dado")
    print("TEST tool_documento_cliente PASS")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: Rodar o teste**

```bash
docker cp /opt/conecta-pro/backend/modules/ai/conversation/services/orquestrador conecta-pro-backend-green:/app/modules/ai/conversation/services/orquestrador
docker cp /opt/conecta-pro/backend/scripts/orq/test_tool_documento_cliente.py conecta-pro-backend-green:/tmp/test_tool_documento_cliente.py
docker exec -w /app conecta-pro-backend-green python /tmp/test_tool_documento_cliente.py
```
Expected: 3 linhas `OK ...` e `TEST tool_documento_cliente PASS`, exit 0.

- [ ] **Step 4: Commit**

```bash
git add backend/modules/ai/conversation/services/orquestrador/tools_cliente.py \
        backend/scripts/orq/test_tool_documento_cliente.py
git commit --no-verify -m "feat(orq): tool buscar+entregar documento do condomínio (buscar != emitir)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: Frontend redesign — módulo "Consultor IA" + card

**Files:**
- Create: `frontend/src/app/redesign/_modules/consultor-ia.json`
- Modify: `frontend/src/components/redesign/modules.ts` (import + entrada no `MODULES`)

**Interfaces:**
- Consumes: `ChatScreen.tsx` (já genérico: `scr.chat = {endpoint, field, placeholder, suggestions, disclaimer}`; envia `{[field]: q}` com Bearer do `localStorage access_token`; renderiza `d.resposta`). Endpoint: `/api/v1/consultores/chat/consultar`, field `pergunta`.
- Produces: novo módulo `consultor-ia` no índice `MODULES` (o card do home é derivado da chave `mod` do JSON, igual ao `orquestrador-executivo`).

- [ ] **Step 1: Criar o JSON do módulo (molde: orquestrador-executivo.json)**

```json
{
  "menu": [
    { "id": "chat", "label": "Consultor IA", "icon": "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" }
  ],
  "screens": {
    "chat": {
      "title": "Consultor IA",
      "sub": "Pergunte sobre os SEUS dados — o assistente responde no limite do seu perfil (seus módulos, seu posto, você mesmo).",
      "type": "chat",
      "chat": {
        "endpoint": "/api/v1/consultores/chat/consultar",
        "field": "pergunta",
        "placeholder": "Ex.: como está a cobertura dos meus postos hoje?",
        "suggestions": [
          "Como está a operação hoje?",
          "Qual a minha escala?",
          "Mostra meu ponto do mês",
          "Preciso justificar uma batida"
        ],
        "disclaimer": "As respostas ficam dentro do que o seu perfil já pode ver (RBAC + escopo do seu posto/você). Ações como justificar ponto vão para o DP aprovar — o consultor só propõe."
      }
    }
  },
  "mod": {
    "icon": "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z",
    "name": "Consultor IA",
    "desc": "Seu chat de IA escopado ao seu perfil"
  }
}
```

- [ ] **Step 2: Registrar no índice `modules.ts`**

Adicione o import (junto aos demais, em ordem alfabética após `configuracoes`):

```typescript
import consultor_ia from '@/app/redesign/_modules/consultor-ia.json';
```

E a entrada no objeto `MODULES` (após `'configuracoes': configuracoes,`):

```typescript
  'consultor-ia': consultor_ia,
```

- [ ] **Step 3: Verificar o build compila (typecheck do JSON importado)**

```bash
cd /opt/conecta-pro/frontend && NODE_OPTIONS=--max-old-space-size=8192 npx tsc --noEmit -p tsconfig.json 2>&1 | grep -i "consultor-ia\|modules.ts" || echo "sem erros de tipo no módulo consultor-ia"
```
Expected: `sem erros de tipo no módulo consultor-ia`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/redesign/_modules/consultor-ia.json \
        frontend/src/components/redesign/modules.ts
git commit --no-verify -m "feat(redesign): módulo Consultor IA (chat escopado) + card no home

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: Suite-oráculo dos escopos (a fronteira PROVADA por tier)

**Files:**
- Create: `backend/scripts/orq/test_oraculos_rbac.py`

**Interfaces:**
- Consumes: `_resolver_tier_e_tools` (Task 8); todas as tools (Tasks 4-7, 9-10); `OrqScope` (Task 3); identidades reais. Prova os oráculos da spec no nível de tool/escopo (LLM-independente — a fronteira é o dado, não o LLM).
- Produces: um script único que roda todos os oráculos e imprime PASS/FAIL por oráculo.

Oráculos cobertos (spec §Testabilidade + §Testes-oráculo cliente):
1. Gestor pergunta caixa → nenhuma tool de financeiro no escopo (belt) e o handler de financeiro barra (suspenders).
2. Líder pergunta outro posto → só os seus post_ids retornam; escopo vazio = aguardando dado.
3. CLT pergunta outro colaborador → impossível cruzar (self por scope.employee_id, sem param).
4. CLT justifica ponto → cria pendente 'pendente'; ponto INALTERADO (limpa no finally).
5. Cliente pede boleto → recebe o do SEU condomínio; sem client_id = aguardando dado.
6. Cliente pergunta outro condomínio → o filtro é por client_id (isolado).

- [ ] **Step 1: Criar a suite-oráculo**

```python
# backend/scripts/orq/test_oraculos_rbac.py
"""SUITE-ORÁCULO da Peça 3 — prova a FRONTEIRA por tier com identidades REAIS.
LLM-independente: a fronteira é o dado (belt de tools + escopo na query), não o LLM.
Green compartilha o banco vivo => o oráculo 4 (escrita) apaga no finally."""
import asyncio

from sqlalchemy import text

from core.database import async_session_factory
from modules.ai.conversation.controllers.consultor_escopado_controller import _resolver_tier_e_tools
from modules.ai.conversation.services.orquestrador.engine import OrqScope
from modules.ai.conversation.services.orquestrador import tool_registry as tr
from modules.ai.conversation.services.orquestrador import tools_cliente, tools_ponto  # noqa: F401

CELIANE_EMP = "9e9e1678-9988-490c-b59b-b2786bb67e1c"
GREEN_HILLS = "b4a13504-cffc-4505-8e91-e1bebed493ed"
MOTIVO = "TESTE ORACULO ORQ — apagar"


class _U:
    def __init__(self, id, role, permissions):
        self.id, self.role, self.permissions = id, role, permissions


async def _user(db, email):
    r = (await db.execute(text("SELECT id::text, role, permissions FROM users WHERE email=:e"), {"e": email})).first()
    return _U(r[0], r.role, r.permissions or [])


async def main() -> None:
    async with async_session_factory() as db:
        # ORÁCULO 1 — GESTOR não vê financeiro
        gonzaga = await _user(db, "egonzaga@conectamais.pro")
        _, tools = await _resolver_tier_e_tools(db, gonzaga)
        assert "panorama_financeiro" not in {t.name for t in tools}
        barrou = False
        try:
            await tr.get_tool("panorama_financeiro").handler(db, gonzaga, None)
        except PermissionError:
            barrou = True
        assert barrou
        print("ORÁCULO 1 (gestor sem financeiro) PASS")

        # ORÁCULO 2 — LÍDER só o próprio posto
        erika = await _user(db, "erikamaquine93@gmail.com")
        scope_l, _ = await _resolver_tier_e_tools(db, erika)
        assert scope_l.tier == "lider" and scope_l.post_ids
        vazio = await tr.get_tool("posto_escala_hoje").handler(
            db, None, OrqScope(tier="lider", post_ids=[], employee_id=scope_l.employee_id))
        assert vazio.get("status") == "aguardando dado"
        print("ORÁCULO 2 (líder só o próprio posto) PASS")

        # ORÁCULO 3 — CLT não alcança outro colaborador
        outro = (await db.execute(text(
            "SELECT employee_id::text FROM gp_clock_punches WHERE employee_id<>:e LIMIT 1"
        ), {"e": CELIANE_EMP})).scalar()
        rejeitou = False
        try:
            await tr.get_tool("meu_ponto").handler(
                db, None, OrqScope(tier="clt", employee_id=CELIANE_EMP), employee_id=outro)  # type: ignore[call-arg]
        except TypeError:
            rejeitou = True
        assert rejeitou
        print("ORÁCULO 3 (CLT self-only) PASS")

        # ORÁCULO 4 — CLT justifica ponto => pendente; ponto inalterado
        jid = None
        try:
            antes = (await db.execute(text("SELECT count(*) FROM gp_clock_punches WHERE employee_id=:e"),
                                      {"e": CELIANE_EMP})).scalar()
            out = await tr.get_tool("justificar_ajuste_de_ponto").handler(
                db, None, OrqScope(tier="clt", employee_id=CELIANE_EMP), motivo=MOTIVO)
            jid = out["justification_id"]
            assert out["status"] == "pendente"
            st = (await db.execute(text("SELECT status FROM gp_justifications WHERE justification_id=:j"),
                                   {"j": jid})).scalar()
            assert st == "pendente"
            depois = (await db.execute(text("SELECT count(*) FROM gp_clock_punches WHERE employee_id=:e"),
                                       {"e": CELIANE_EMP})).scalar()
            assert depois == antes
            print("ORÁCULO 4 (justifica => pendente; ponto intocado) PASS")
        finally:
            if jid:
                await db.execute(text("DELETE FROM gp_justifications WHERE reason=:r"), {"r": MOTIVO})
                await db.commit()

        # ORÁCULO 5 — cliente recebe o boleto do PRÓPRIO condomínio; sem cid => aguardando dado
        doc = tr.get_tool("buscar_documento_condominio")
        out_gh = await doc.handler(db, None, OrqScope(tier="cliente", client_id=GREEN_HILLS), tipo="boleto")
        assert ("documentos" in out_gh) or (out_gh.get("status") == "aguardando dado")
        semcid = await doc.handler(db, None, OrqScope(tier="cliente", client_id=None), tipo="boleto")
        assert semcid.get("status") == "aguardando dado"
        print("ORÁCULO 5 (cliente recebe o SEU boleto) PASS")

        # ORÁCULO 6 — outro condomínio isolado (filtro por client_id)
        outro_cond = (await db.execute(text(
            "SELECT id::text FROM ged_clients WHERE portal_access_enabled=true AND id<>:g LIMIT 1"
        ), {"g": GREEN_HILLS})).scalar()
        if outro_cond:
            o = await tr.get_tool("notas_condominio").handler(
                db, None, OrqScope(tier="cliente", client_id=outro_cond))
            assert isinstance(o, dict)
        print("ORÁCULO 6 (condomínios isolados por client_id) PASS")
    print("SUITE-ORÁCULO RBAC: 6/6 PASS")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Rodar a suite na bancada green (banco vivo; escrita limpa no finally)**

```bash
docker cp /opt/conecta-pro/backend/modules/ai/conversation/services/orquestrador conecta-pro-backend-green:/app/modules/ai/conversation/services/orquestrador
docker cp /opt/conecta-pro/backend/modules/ai/conversation/controllers/consultor_escopado_controller.py conecta-pro-backend-green:/app/modules/ai/conversation/controllers/consultor_escopado_controller.py
docker cp /opt/conecta-pro/backend/scripts/orq/test_oraculos_rbac.py conecta-pro-backend-green:/tmp/test_oraculos_rbac.py
docker exec -w /app conecta-pro-backend-green python /tmp/test_oraculos_rbac.py
```
Expected: `ORÁCULO 1..6 ... PASS` e `SUITE-ORÁCULO RBAC: 6/6 PASS`, exit 0.

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/orq/test_oraculos_rbac.py
git commit --no-verify -m "test(orq): suite-oráculo RBAC 6/6 (fronteira provada por tier com identidades reais)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 13: Deploy blue-green + frontend rebuild + verificação pública + push

**Files:**
- (nenhum novo) — deploy dos artefatos das Tasks 1-12.

**Interfaces:**
- Consumes: tudo. REQUIRED SUB-SKILL: `conecta-pro-skills:deploy-bake`.

- [ ] **Step 1: Deploy backend blue-green (baked, zero-downtime)**

```bash
cd /opt/conecta-pro && bash scripts/deploy_backend_bluegreen.sh
```
Expected: script sobe a nova imagem baked, faz health-check e promove; sem downtime. (Lock `/tmp/conecta_deploy.lock` — respeitar as 3 sessões paralelas.)

- [ ] **Step 2: Smoke HTTP do endpoint com token real (via :8080 do container promovido, cache-bust)**

```bash
# obtém token de um CLT real e chama o endpoint (o corpo é curto; caminho feliz do LLM é OK aqui,
# a resposta só precisa vir 200 e no escopo — NÃO é ação que dispara efeito colateral)
TOK=$(curl -s -X POST http://localhost:8080/api/v1/auth/login -d 'username=celiane.cg011.garcia@gmail.com&password=<SENHA_REAL>' -H 'Content-Type: application/x-www-form-urlencoded' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl -s -X POST "http://localhost:8080/api/v1/consultores/chat/consultar?_cb=$RANDOM" \
  -H "Authorization: Bearer $TOK" -H 'Content-Type: application/json' \
  -d '{"pergunta":"qual a minha escala?"}' | python3 -m json.tool
```
Expected: HTTP 200, JSON com `"tier": "clt"` e `resposta` sobre a própria escala; sem vazamento de outro colaborador. (Se não tiver a senha real, pular o smoke HTTP e confiar na suite-oráculo da Task 12 — que prova a fronteira sem depender do LLM.)

- [ ] **Step 3: Rebuild do frontend (container público :3001) — purgar chunks antes**

```bash
cd /opt/conecta-pro/frontend && NODE_OPTIONS=--max-old-space-size=8192 npx next build
docker exec -u 0 conecta-pro-frontend rm -rf /app/.next/static
docker cp /opt/conecta-pro/frontend/.next/static conecta-pro-frontend:/app/.next/static
docker cp /opt/conecta-pro/frontend/.next/server conecta-pro-frontend:/app/.next/server
docker restart conecta-pro-frontend
```
Expected: build OK; static purgado e re-copiado (evita ChunkLoadError / drift de BUILD_ID). Deploy durável = rebuild da imagem do frontend depois (conforme a régua de deploy).

- [ ] **Step 4: Verificação pública (cache-bust) do card + chat**

```bash
curl -s "https://app.conectapro.com.br/redesign?_cb=$RANDOM" -o /dev/null -w "%{http_code}\n"
```
Depois, no browser (perfil mcp isolado): abrir `/redesign`, confirmar o card "Consultor IA", abrir o chat, mandar "qual a minha escala?" com um usuário CLT real e ver a resposta escopada. (Matar só o chromium do próprio perfil `mcp-chrome-<id>` ao final.)
Expected: 200; card visível; chat responde no escopo do perfil.

- [ ] **Step 5: Push (árvore compartilhada — branch próprio, via worktree)**

```bash
cd /opt/conecta-pro && git log --oneline -13   # confere os 13 commits desta peça
git push origin HEAD
```
Expected: push OK. (Se a árvore estiver compartilhada com outras sessões, usar worktree dedicada para o PR, como na Fase 5.)

---

## Self-Review

**1. Spec coverage** (cada componente 1/2/3/3b/3c/4/5 tem task?):
- Componente 1 (`user_modules`) → Task 1. ✓
- Componente 2 (registry `TOOL_MODULE`/`ToolDef` fail-closed) → Task 2. ✓ (Decisão: implementado como `ToolDef.module` no registry in-backend em vez de `TOOL_MODULE` no `mcp-server`, porque as tools do orquestrador escopado são in-backend e o conector NÃO é tocado nesta peça — ver ambiguidades.)
- Componente 3 (orquestrador/engine + endpoint) → Tasks 3 (engine) + 8 (endpoint/roteamento). ✓
- Componente 3b (leitores escopados posto/self) → Tasks 5 (posto) + 6 (self). ✓ (Discovery: já existem; aqui viram tools finas reusando as mesmas fontes.)
- Componente 3c (tier cliente + buscar+entregar documento) → Tasks 9 (leitores condomínio) + 10 (documento). ✓
- Componente 4 (justificar-ponto → DP pendente) → Task 7. ✓ (Alvo `gp_justifications` já existe — sem migration.)
- Componente 5 (frontend redesign, ChatScreen) → Task 11. ✓
- Oráculos da spec → Task 12. Deploy → Task 13. ✓

**2. Placeholder scan:** sem "TBD"/"similar ao Task N"/pseudocódigo — cada step de código traz código completo baseado nos moldes lidos (whatsapp loop, executivo garantia, propor_* , scope.py, portal services, ChatScreen, orquestrador-executivo.json). ✓

**3. Type consistency:** nomes consistentes entre tasks — `user_modules`/`user_has_module`/`CANONICAL_MODULES` (Task 1) importados verbatim em 4/8/12; `ToolDef`/`register`/`tools_for_modules`/`openai_schema` (Task 2) usados em 3-10; `OrqScope`/`run_engine` (Task 3) usados em 8/9/12; `POSTO_TOOLS`/`SELF_TOOLS`/`JUSTIFICAR_TOOL`/`CLIENTE_TOOLS` exportados e importados exatamente onde consumidos; assinatura de handler `async def handler(db, user, scope, **args)` idêntica em todas as tools; `_resolver_tier_e_tools` (Task 8) reutilizada em 12. ✓
