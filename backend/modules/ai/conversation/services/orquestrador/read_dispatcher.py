"""Dispatcher de LEITURA por módulo (Fase 6, balde VER).

Colapsa os N read-adapters flat de cada módulo (tools_read_crm/dp/financeiro) em UMA
tool `consultar_<modulo>(consulta, filtros)`, mantendo o chat sob o teto de tools do LLM
(24 reads flat → 3 dispatchers).

Cada read-adapter registra suas ops via `registrar_read(modulo, nome, desc, handler)` em vez
de `register(ToolDef(...))` flat; `montar_read_dispatchers()` gera 1 ToolDef `consultar_<mod>`
por módulo que ROTEIA `consulta` → handler REAL (as MESMAS funções, mesma resposta).

Paredes (inegociáveis):
- RBAC na fonte: `_gate(user, modulo)` ANTES de despachar — chamar o handler direto pula o
  Depends(require_permission) do controller; o belt (tools_for_modules) já filtra por módulo,
  o gate é o suspenders. Identidade REAL do usuário, nunca a conta de serviço.
- SÓ LEITURA: só ops de leitura são registradas aqui (nada cria/edita/apaga/move dinheiro).
- Fail-closed: consulta inválida → recusa clara listando as opções, nunca erro cru nem chute.
"""
from __future__ import annotations

from typing import Any

from core.auth.module_scope import user_has_module

from .tool_registry import ToolDef, get_tool, register

#: módulo → nome_op → {"handler": fn, "desc": str}
_READ_OPS: dict[str, dict[str, dict]] = {}


def registrar_read(modulo: str, nome: str, desc: str, handler) -> None:
    """Registra uma op de LEITURA sob um módulo (vira uma `consulta` do consultar_<modulo>)."""
    _READ_OPS.setdefault(modulo, {})[nome] = {"handler": handler, "desc": desc}


def _gate(user, modulo: str) -> None:
    # Suspenders: o handler chamado direto pula o Depends do controller; re-checamos o
    # módulo na fonte com a identidade real. Gate ANTES de resolver a consulta.
    if not user_has_module(user, modulo):
        raise PermissionError(modulo)


def _fazer_dispatch(modulo: str):
    async def _disp(db, user, scope, *, consulta=None, filtros=None, **_) -> Any:
        _gate(user, modulo)  # RBAC na fonte, antes de tudo
        ops = _READ_OPS.get(modulo, {})
        op = ops.get(consulta)
        if op is None:  # fail-closed: recusa clara com as opções, nunca chute
            return {"status": "recusado",
                    "motivo": f"consulta {consulta!r} inválida em {modulo}; "
                              f"opções: {', '.join(sorted(ops))}"}
        # filtros extras não previstos não quebram: os handlers aceitam **_
        return await op["handler"](db, user, scope, **(filtros or {}))
    return _disp


def montar_read_dispatchers() -> None:
    """Gera 1 ToolDef consultar_<modulo> por módulo com ops registradas. Idempotente
    (re-import não re-registra)."""
    for modulo, ops in _READ_OPS.items():
        nome = f"consultar_{modulo}"
        if get_tool(nome) is not None:
            continue
        nomes = sorted(ops)
        schema = {
            "type": "object",
            "properties": {
                "consulta": {"type": "string", "enum": nomes,
                             "description": "Qual consulta de leitura executar."},
                "filtros": {"type": "object",
                            "description": "Filtros opcionais da consulta (ex.: status, "
                                           "search/busca, cliente, mes, ano, page)."},
            },
            "required": ["consulta"],
        }
        linhas = "\n".join(f"- {n}: {ops[n]['desc']}" for n in nomes)
        desc = (f"Consultas de LEITURA do módulo {modulo} (só leitura, dados reais; vazio real "
                f"= sem dado, não fabrica). Informe 'consulta' (uma das abaixo) e 'filtros' "
                f"opcionais:\n{linhas}")
        register(ToolDef(nome, modulo, desc, schema, _fazer_dispatch(modulo), scope_kind="org"))
