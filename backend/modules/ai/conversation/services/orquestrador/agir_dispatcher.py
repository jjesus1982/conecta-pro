"""Dispatcher de AÇÃO por módulo (Fase 6, balde FAZER).

Espelha `read_dispatcher.py`: colapsa as N ações reversíveis de cada módulo em UMA
tool `agir_<modulo>(acao, dados)`, mantendo o chat sob o teto de tools do LLM. A
diferença para o READ é o EFEITO: aqui cada ação só PROPÕE (via `acoes.base.propor`,
que NUNCA executa — insere PENDENTE e um humano aprova depois). O LLM jamais efetiva.

Cada tools_acao_<mod> registra suas ações via `registrar_acao(modulo, nome, desc,
handler)` em vez de `register(ToolDef(...))` flat; `montar_acao_dispatchers()` gera 1
ToolDef `agir_<mod>` por módulo que ROTEIA `acao` → handler `_propor_*` REAL.

Paredes (inegociáveis):
- RBAC na fonte: `_gate(user, modulo)` ANTES de despachar (reusa o de read_dispatcher —
  o handler chamado direto pula o Depends do controller; o gate é o suspenders).
- LLM NUNCA executa: os handlers só chamam `propor()` (PENDENTE + aprovação humana).
- Fail-closed: acao inválida → recusa clara listando as opções, nunca erro cru nem chute.
"""
from __future__ import annotations

from typing import Any

from .read_dispatcher import _gate  # RBAC na fonte, idêntico ao READ (reuso)
from .tool_registry import ToolDef, get_tool, register

#: módulo → nome_acao → {"handler": fn, "desc": str}
_ACOES: dict[str, dict[str, dict]] = {}


def registrar_acao(modulo: str, nome: str, desc: str, handler) -> None:
    """Registra uma AÇÃO reversível sob um módulo (vira uma `acao` do agir_<modulo>)."""
    _ACOES.setdefault(modulo, {})[nome] = {"handler": handler, "desc": desc}


def _fazer_acao_dispatch(modulo: str):
    async def _disp(db, user, scope, *, acao=None, dados=None, **_) -> Any:
        _gate(user, modulo)  # RBAC na fonte, antes de tudo
        acoes = _ACOES.get(modulo, {})
        op = acoes.get(acao)
        if op is None:  # fail-closed: recusa clara com as opções, nunca chute
            return {"status": "recusado",
                    "motivo": f"acao {acao!r} inválida em {modulo}; "
                              f"opções: {', '.join(sorted(acoes))}"}
        # dados são validados no próprio handler (_propor_*), que devolve {"erro":...}
        # amigável em vez de estourar; campos extras não previstos não quebram (**_).
        return await op["handler"](db, user, scope, **(dados or {}))
    return _disp


def montar_acao_dispatchers() -> None:
    """Gera 1 ToolDef agir_<modulo> por módulo com ações registradas. Idempotente
    (re-import não re-registra)."""
    for modulo, acoes in _ACOES.items():
        nome = f"agir_{modulo}"
        if get_tool(nome) is not None:
            continue
        nomes = sorted(acoes)
        schema = {
            "type": "object",
            "properties": {
                "acao": {"type": "string", "enum": nomes,
                         "description": "Qual ação PROPOR (nada é executado; fica pendente de aprovação humana)."},
                "dados": {"type": "object",
                          "description": "Campos da ação (ver a descrição de cada acao abaixo)."},
            },
            "required": ["acao"],
        }
        linhas = "\n".join(f"- {n}: {acoes[n]['desc']}" for n in nomes)
        desc = (f"Ações reversíveis do módulo {modulo} — você PROPÕE, um humano aprova; "
                f"NADA é executado pela IA. Informe 'acao' (uma das abaixo) e 'dados':\n{linhas}")
        register(ToolDef(nome, modulo, desc, schema, _fazer_acao_dispatch(modulo), scope_kind="org"))
