"""Frente 08 — tela MAPA DE FÉRIAS por idade do período aquisitivo (12/09/2026). Só leitura.

Formato da DGX: legenda por faixa com contagem, lista por pessoa do maior risco para o menor e
painel "vence em 30/60/90 dias". O cálculo mora em `hr/services/mapa_ferias.py` (régua única —
o oráculo `test_oraculo_mapa_ferias.py` confere a mesma função). Prefixo `_` = o discovery de
builders pula este arquivo; `departamento_pessoal.build()` chama `telas()` no fim.
Alcance hoje: deep-link `/redesign/departamento-pessoal?t=mapa-ferias` (aba no grupo Férias é
fiação do integrador em `_dp_grupos.GRUPOS`).
"""
from __future__ import annotations

from modules.people_management.hr.services import mapa_ferias as mf

_TOM = {mf.EM_AQUISICAO: "mut", "12–16": "ok", "17–19": "info", "20–22": "warn",
        mf.DOBRA: "bad", mf.AFASTADO_LONGO: "info", mf.NAO_CALCULADO: "mut"}
_ND = "#0F1B3A"


def _d(v) -> str:
    return v.strftime("%d/%m/%Y") if v else "—"


def _n(v) -> str:
    return "—" if v is None else str(v)


def _vence(r) -> str:
    d = r["dias_para_limite"]
    if d is None:
        return "—"
    if r["vencida"]:
        return f"vencida há {-d} d"
    return f"{d} d"


async def telas(db) -> dict:
    from modules.operacional.controllers.redesign_data_controller import S, b, initials, t

    linhas = await mf.mapa(db)
    hoje = mf.hoje_manaus()
    cont = dict.fromkeys(mf.FAIXAS, 0)
    for r in linhas:
        cont[r["faixa"]] += 1
    dobra = [r for r in linhas if r["faixa"] == mf.DOBRA]
    vencidas = [r for r in dobra if r["vencida"]]

    def _linha(r):
        tone = "bad" if r["vencida"] else _TOM[r["faixa"]]
        d = r["dias_para_limite"]
        tone_v = "bad" if r["vencida"] else ("warn" if d is not None and d <= 90 else "mut")
        return {"cells": [
            t(r["nome"], 600, _ND, initials(r["nome"] or "")), t(r["cargo"]), t(_d(r["ancora"])),
            t(_n(r["idade_meses"]), 600), b(r["faixa"], tone),
            t(f"{_n(r['usados'])} / {r['direito']}"), t(_n(r["restantes"]), 600),
            t(_d(r["limite"])), b(_vence(r), tone_v),
        ], "filtro": r["faixa"]}

    legenda = [{"left": f, "right": str(cont[f]), **S[_TOM[f]]} for f in mf.FAIXAS]

    def _janela(lo, hi):
        return [r for r in linhas if r["dias_para_limite"] is not None and lo < r["dias_para_limite"] <= hi]

    janelas = [("≤ 30 dias", _janela(-1, 30), "bad"), ("31–60 dias", _janela(30, 60), "warn"), ("61–90 dias", _janela(60, 90), "warn")]
    vence = []
    for rot, ps, tone in janelas:
        vence.append({"left": rot, "right": str(len(ps)), **S[tone if ps else "mut"]})
        vence += [{"left": f"    {r['nome']} — limite {_d(r['limite'])}", "right": f"{r['dias_para_limite']} d", **S[tone]} for r in ps]
    if len(vence) == 3 and not any(ps for _r, ps, _t in janelas):
        vence.append({"left": "Ninguém vence nos próximos 90 dias", "right": "0", **S["ok"]})

    nominal = [{"left": f"{r['nome']} — período desde {_d(r['inicio_periodo'])}, limite {_d(r['limite'])}",
                "right": ("VENCIDA · dobra" if r["vencida"] else f"{r['idade_meses']} meses"), **S["bad"]}
               for r in dobra] or [{"left": "Ninguém na faixa > 22 meses (calculado, não vazio)", "right": "0", **S["ok"]}]

    return {"mapa-ferias": {
        "title": "Mapa de férias — idade do período aquisitivo",
        "sub": f"{len(linhas)} ativos com vínculo · {len(dobra)} na faixa > 22 meses (risco de dobra) · "
               f"{len(vencidas)} já vencidas · hoje {_d(hoje)} · âncora = admissão ou retorno de afastamento > 6 meses (art. 133 CLT)",
        "cta": "—", "type": "table", "searchHint": "Buscar colaborador ou faixa…",
        "grid": "1.8fr 1.1fr 0.8fr 0.5fr 1.5fr 0.6fr 0.6fr 0.8fr 0.9fr",
        "cols": ["Colaborador", "Cargo", "Âncora", "Meses", "Faixa", "Gozados / direito", "Restantes", "Limite", "Vence em"],
        "rows": [_linha(r) for r in linhas],
        "panelGrid": "1fr 1fr 1fr",
        "panels": [
            {"title": "Legenda — idade do período aquisitivo (contagem)", "rows": legenda},
            {"title": "Vence em 30 / 60 / 90 dias", "rows": vence},
            {"title": "> 22 meses — alarme de dobra (nominal)", "rows": nominal},
        ],
    }}
