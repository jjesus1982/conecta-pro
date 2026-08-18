"""As quatro calculadoras fiscais como tools — módulo `fiscal`, scope_kind="org".

O chat escopado passa a CALCULAR o que as telas de `/modulos/fiscal` já calculam: DAS do
Simples, impostos no Lucro Real, o comparativo entre os dois regimes e a retenção na fonte
sobre NFS-e.

⭐ **Reusa o ALGORITMO, não reescreve.** Cada handler chama a COROUTINE do controller REAL
in-process — o mesmo `fiscal_controller` que a tela chama —, então tool e tela não podem
divergir: se a regra mudar num lugar, muda nos dois. A lição de IA dormente desta base é
exatamente esta: agente que reimplementa a conta vira casca que discorda do sistema.

Paredes:
- RBAC na fonte: chamar o controller direto PULA o `Depends(require_permission)` dele, então
  todo handler faz `_gate(user)` antes. O belt (`tools_for_modules`) já filtra por módulo; o
  gate é o suspensório. É gate de DIRETORIA.
- **Não move nada.** As quatro são cálculo puro: não gravam, não emitem, não transmitem.
- Nunca fabricar: parâmetro que falta vira RECUSA com a pergunta, nunca um default silencioso.

⚠️ **`regime_empresa` é obrigatório em `calcular_retencoes`, e o default é armadilha.** Sem
liminar os dois regimes dão o mesmo total, então a lacuna fica invisível; com liminar marcada
e regime em branco o motor aplicava a liminar da PATRIMONIAL a um cálculo da ELETRÔNICA —
medido em 15/08/2026, R$ 1.850,00 contra R$ 2.215,00 numa nota de R$ 10.000. Retenção decide
quanto o cliente deposita. A recusa vive no controller e o schema desta tool não inventa
default para tapá-la.
"""
from __future__ import annotations

from typing import Any

from core.auth.module_scope import user_has_module

from .tool_registry import ToolDef, register

_MOD = "fiscal"

#: Liminares reconhecidas pelo motor. Enumeradas para o LLM não inventar nome de liminar —
#: liminar inexistente zeraria tributo que a empresa deve.
_LIMINARES = ["pis_cofins_zero", "inss_nao_retido"]


def _gate(user) -> None:
    if not user_has_module(user, _MOD):
        raise PermissionError(_MOD)


def _dump(res) -> Any:
    return res.model_dump(mode="json") if hasattr(res, "model_dump") else res


# ── handlers: cada um chama a coroutine do controller que a tela usa ──────────────

async def _calcular_das(db, user, scope, *, receita_mes=None, rbt12=None,
                        liminares=None, **_) -> Any:
    _gate(user)
    from modules.financial.controllers.fiscal_controller import (
        calcular_simples_nacional,
    )
    from modules.financial.schemas.fiscal_schemas import CalculoSimplesRequest

    if receita_mes is None or rbt12 is None:
        return {"status": "recusado",
                "motivo": "Preciso da receita do mês e do RBT12 (receita bruta acumulada dos "
                          "últimos 12 meses). A alíquota efetiva do Simples depende do RBT12 — "
                          "sem ele o DAS sairia de uma faixa errada."}
    req = CalculoSimplesRequest(receita_mes=receita_mes, rbt12=rbt12,
                                liminares=liminares or [])
    return _dump(await calcular_simples_nacional(req, current_user=user))


async def _calcular_lucro_real(db, user, scope, *, receita_mes=None,
                               receita_trimestre=None, custos_dedutiveis_mes=0, **_) -> Any:
    _gate(user)
    from modules.financial.controllers.fiscal_controller import (
        calcular_lucro_real as _rota,
    )
    from modules.financial.schemas.fiscal_schemas import CalculoLucroRealRequest

    if receita_mes is None or receita_trimestre is None:
        return {"status": "recusado",
                "motivo": "Preciso da receita do mês E da receita do trimestre: o adicional de "
                          "10% do IRPJ incide sobre o que passa de R$ 20 mil/mês no trimestre, "
                          "então sem o acumulado trimestral o imposto sai subestimado."}
    req = CalculoLucroRealRequest(receita_mes=receita_mes,
                                  receita_trimestre=receita_trimestre,
                                  custos_dedutiveis_mes=custos_dedutiveis_mes or 0)
    return _dump(await _rota(req, current_user=user))


async def _comparar_regimes(db, user, scope, *, receita_anual=None,
                            custos_dedutiveis_anual=0, liminares=None, **_) -> Any:
    _gate(user)
    from modules.financial.controllers.fiscal_controller import (
        comparar_regimes as _rota,
    )
    from modules.financial.schemas.fiscal_schemas import ComparativoRegimesRequest

    if receita_anual is None:
        return {"status": "recusado",
                "motivo": "Preciso da receita ANUAL para comparar os regimes."}
    req = ComparativoRegimesRequest(receita_anual=receita_anual,
                                    custos_dedutiveis_anual=custos_dedutiveis_anual or 0,
                                    liminares=liminares or [])
    return _dump(await _rota(req, current_user=user))


async def _calcular_retencoes(db, user, scope, *, valor_servico=None,
                              regime_empresa=None, liminares=None, **_) -> Any:
    _gate(user)
    from fastapi import HTTPException

    from modules.financial.controllers.fiscal_controller import (
        calcular_retencoes_nfse as _rota,
    )
    from modules.financial.schemas.fiscal_schemas import RetencoesNFSeRequest

    if valor_servico is None:
        return {"status": "recusado", "motivo": "Preciso do valor do serviço da nota."}
    req = RetencoesNFSeRequest(valor_servico=valor_servico,
                               regime_empresa=regime_empresa,
                               liminares=liminares or [])
    try:
        return _dump(await _rota(req, current_user=user))
    except HTTPException as e:
        # A recusa por regime ausente é do CONTROLLER, e é a mesma que a tela recebe.
        # Devolvê-la como recusa (e não como erro) faz o LLM perguntar em vez de chutar.
        return {"status": "recusado", "motivo": e.detail}


# ── registro ─────────────────────────────────────────────────────────────────────

_NUM = {"type": "number"}
_LIM = {"type": "array", "items": {"type": "string", "enum": _LIMINARES},
        "description": "Liminares ATIVAS da empresa. Só as listadas; não invente outras."}

register(ToolDef(
    "calcular_das", _MOD,
    "Calcula o DAS do Simples Nacional (Anexo III) a partir da receita do mês e do RBT12 "
    "(receita bruta dos últimos 12 meses). Devolve alíquota nominal, alíquota EFETIVA e o "
    "valor do DAS. Aplica liminares quando informadas. Só diretoria (belt fiscal). "
    "Cálculo puro: não grava nem emite nada.",
    {"type": "object",
     "properties": {"receita_mes": _NUM, "rbt12": _NUM, "liminares": _LIM},
     "required": ["receita_mes", "rbt12"]},
    _calcular_das, scope_kind="org"))

register(ToolDef(
    "calcular_lucro_real", _MOD,
    "Calcula os impostos no regime de Lucro Real (IRPJ com adicional de 10%, CSLL, PIS e "
    "COFINS não-cumulativos, ISS). Exige a receita do MÊS e a do TRIMESTRE — o adicional de "
    "IRPJ é trimestral. Só diretoria (belt fiscal). Cálculo puro: não grava nada.",
    {"type": "object",
     "properties": {"receita_mes": _NUM, "receita_trimestre": _NUM,
                    "custos_dedutiveis_mes": _NUM},
     "required": ["receita_mes", "receita_trimestre"]},
    _calcular_lucro_real, scope_kind="org"))

register(ToolDef(
    "comparar_regimes", _MOD,
    "Compara a carga tributária ANUAL entre Simples Nacional e Lucro Real e diz qual sai "
    "mais barato. Serve para decidir quando a Eletrônica volta ao Simples. Só diretoria "
    "(belt fiscal). Cálculo puro: não grava nada.",
    {"type": "object",
     "properties": {"receita_anual": _NUM, "custos_dedutiveis_anual": _NUM,
                    "liminares": _LIM},
     "required": ["receita_anual"]},
    _comparar_regimes, scope_kind="org"))

register(ToolDef(
    "calcular_retencoes", _MOD,
    "Calcula as retenções na fonte sobre uma NFS-e (INSS 11%, IR 1,5%, CSLL 1%, PIS 0,65%, "
    "COFINS 3%, ISS 5%) e o líquido a receber. ⚠️ O REGIME DO EMISSOR É OBRIGATÓRIO — "
    "'simples_nacional' (Patrimonial) ou 'lucro_real' (Eletrônica): com liminar ativa a "
    "retenção muda com o regime, e chutar aqui erra quanto o cliente deposita. Sem o regime, "
    "PERGUNTE. Só diretoria (belt fiscal). Cálculo puro: não grava nem emite nota.",
    {"type": "object",
     "properties": {"valor_servico": _NUM,
                    "regime_empresa": {"type": "string",
                                       "enum": ["simples_nacional", "lucro_real"],
                                       "description": "Regime do EMISSOR da nota. Obrigatório."},
                    "liminares": _LIM},
     "required": ["valor_servico", "regime_empresa"]},
    _calcular_retencoes, scope_kind="org"))
