#!/usr/bin/env python3
"""Trava: competência/data que o usuário não disse vem do SERVIDOR, nunca do modelo.

Nasceu de um caso real (24/08/2026): um porteiro com 91 batidas no mês perguntou "quantas
horas eu fiz esse mês" e recebeu "nenhuma batida de ponto consta no sistema para você". A
tool estava certa; o modelo é que chamou `meu_ponto` com `mes=7, ano=2025` — deduziu a data do
treinamento dele. Resposta confiante e falsa sobre o dado de uma pessoa é pior que recusa.

`meu_ponto` foi o que apareceu porque alguém perguntou. As outras erram caladas — por isso
esta trava varre a FAMÍLIA: toda tool registrada que aceita mês/ano/competência/data.

A regra: **período omitido pelo usuário é resolvido pelo servidor.** Na prática, uma de três:
  · normalizador declarado (`_periodo`, `_norm_mes_ano`, `_hoje_manaus`);
  · dia civil de Manaus / `now()` / `date_trunc` no próprio SQL;
  · "o mais recente" (holerite pago mais novo) — que também não é chute de calendário.

⚠️ Segue UM nível de helper de propósito. A primeira versão olhava só o corpo do handler e
acusou 11 tools; conferindo à mão, `gerar_dre_doc` chama `_periodo(mes, ano)` e
`meu_holerite_doc` cai no holerite mais recente — as duas estavam certas. Trava que grita sem
motivo é trava que se aprende a ignorar, e foi o que quase aconteceu aqui.

Parâmetro de período OBRIGATÓRIO é caso à parte: força o modelo a preencher. Só é aceitável
quando a data É a pergunta (propor substituição PARA o dia tal), e cada um fica declarado
abaixo com o motivo — decisão humana registrada, não exceção genérica.

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/qa/checar_periodo_do_servidor.py
"""
from __future__ import annotations

import inspect
import re
import sys

PERIODO = re.compile(
    r"^(mes|ano|competencia|compet|data|data_inicio|data_fim|periodo|referencia|"
    r"mes_ano|inicio|fim)$", re.I)

#: Marcas de que QUEM decide o período é o servidor.
RESOLVEDORES = (
    "_hoje_manaus", "_norm_mes_ano", "_periodo", "America/Manaus",
    "date_trunc", "now()", "CURRENT_DATE", "_resolve_payslip",
    # "o mais recente" também é o servidor decidindo — e é o que `meu_holerite` faz
    # (ORDER BY reference_year DESC, reference_month DESC LIMIT 12).
    "reference_year DESC", "reference_period DESC",
)

#: Tools em que o período NÃO é um padrão a calcular: é FILTRO (omitir = sem filtro) ou
#: CHAVE DE BUSCA (achar o pagamento por data). Omitir não vira chute de calendário.
#: Conferidas à mão em 24/08/2026, uma a uma, lendo o handler.
PERIODO_E_FILTRO: dict[str, str] = {
    "gerar_relatorio_nfse_doc": "competência entra na lista de `conds`; sem ela, sem filtro",
    "gerar_comprovante_pagamento_doc": "`data` é uma das 3 formas de ACHAR o pagamento "
                                       "(id | beneficiário | data), não um período padrão",
}

#: Tools em que a data É a pergunta e portanto pode ser obrigatória. Uma linha por tool,
#: com o motivo — entrar aqui é afirmar "sem a data o pedido não existe".
PERIODO_EXPLICITO: dict[str, str] = {
    "propor_substituicao": "substituir alguém EM QUAL DIA — sem a data não há proposta",
    "propor_lote_pagamento": "o lote é DE uma competência; supor qual pagaria o mês errado",
    "propor_esocial": "o evento é DE uma referência; supor qual transmitiria o período errado",
}


def _fonte_com_helpers(fn) -> str:
    """Corpo do handler + o corpo dos helpers do mesmo módulo que ele chama (1 nível)."""
    try:
        src = inspect.getsource(fn)
    except Exception:  # noqa: BLE001
        return ""
    mod = sys.modules.get(getattr(fn, "__module__", "") or "")
    if mod is None:
        return src
    for nome in set(re.findall(r"\b(_[a-z_][a-z0-9_]*)\s*\(", src)):
        alvo = getattr(mod, nome, None)
        if alvo is None or not callable(alvo):
            continue
        try:
            src += "\n" + inspect.getsource(alvo)
        except Exception:  # noqa: BLE001
            continue
    return src


def main() -> int:
    import modules.ai.conversation.controllers.consultor_escopado_controller  # noqa: F401
    from modules.ai.conversation.services.orquestrador.tool_registry import all_tools

    sem_servidor: list[str] = []
    obrigatorias_nao_declaradas: list[str] = []
    com_periodo = 0

    for t in sorted(all_tools(), key=lambda x: x.name):
        props = (t.params_schema or {}).get("properties") or {}
        req = set((t.params_schema or {}).get("required") or [])
        alvo = {p for p in props if PERIODO.match(p)}
        if not alvo:
            continue
        com_periodo += 1

        exigidos = sorted(req & alvo)
        if exigidos and t.name not in PERIODO_EXPLICITO:
            obrigatorias_nao_declaradas.append(
                f"{t.name} exige {exigidos} do modelo — se a data não for a própria pergunta, "
                f"o servidor tem de resolver; se for, declare em PERIODO_EXPLICITO com o motivo")
            continue
        if exigidos:
            continue  # declarada: a data É a pergunta

        if t.name in PERIODO_E_FILTRO:
            continue  # o período é filtro/chave, não default (motivo declarado acima)

        fonte = _fonte_com_helpers(t.handler)
        if not any(m in fonte for m in RESOLVEDORES):
            sem_servidor.append(
                f"{t.name} aceita {sorted(alvo)} e, quando o usuário não diz, nada no servidor "
                f"resolve o período — o valor vem do modelo, que deduz do treinamento")

    vivas = {t.name for t in all_tools()}
    fantasmas = sorted(n for n in (set(PERIODO_EXPLICITO) | set(PERIODO_E_FILTRO))
                       if n not in vivas)

    print(f"  {com_periodo} tool(s) com parâmetro de período")
    falhas = sem_servidor + obrigatorias_nao_declaradas + [
        f"PERIODO_EXPLICITO declara tool inexistente (gaveta): {n}" for n in fantasmas]
    for f in falhas:
        print(f"  - {f}")
    if falhas:
        print(f"\n{len(falhas)} problema(s): período que o usuário não disse está vindo do "
              f"modelo. Ele deduz do treinamento e erra o ANO — foi assim que um porteiro com "
              f"91 batidas ouviu que não tinha ponto nenhum.")
        return 1
    print("  confere: todo período omitido é resolvido pelo servidor")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
