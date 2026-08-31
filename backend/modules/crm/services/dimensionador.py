"""Dimensionador de projeto — quantidade a partir de REGRA, com origem citada.

31/08/2026. O Jordan, olhando a tela de aprovação: *"preciso que o sistema aprenda o
contexto de cada projeto, agir como um especialista e dimensionar. da forma como tá hoje
não adianta nada"*.

Hoje o agente é um DIGITADOR: ele dita "cabo, rack, nobreak" e o sistema reencaminha. Quem
dimensiona é ele; quem lembra do projeto é ele; quem percebeu que faltava switch giga foi o
fornecedor. O objetivo é inverter — o sistema propõe e a tela serve para ele CORRIGIR.

⚠️ E dimensionar é o convite perfeito para fabricação. "12 racks, 2.400m de cabo" sai lindo
de um LLM e pode ser inteiramente inventado; se ele aprovar e mandar ao fornecedor, o
prejuízo é real. Por isso três decisões duras:

1. **NÃO HÁ LLM AQUI.** É aritmética sobre campo estruturado. O que não é conta, não é
   dimensionado.
2. **Todo número carrega REGRA e ORIGEM**, e elas vão para a tela — não como rodapé, como
   conteúdo. Número sem regra não vira item: vira PENDÊNCIA NOMEADA.
3. **Lê `parametros` e `specifications`. Nunca prosa.** O `panorama` do The Sun é
   append-only e as primeiras entradas dizem "32 câmeras" quando são 64 — quem lê texto
   corrido dimensiona meio projeto.

O que ele NÃO faz: escolher produto. Quantidade a partir de regra é aritmética auditável;
qual NVR comprar envolve preço, fornecedor, relação e margem — nada disso é conta, e é
decisão do Jordan.
"""
from __future__ import annotations

import math
from typing import Any

from sqlalchemy import text

from core.logging import logger


def _p(params: dict, chave: str) -> tuple[Any, str] | tuple[None, None]:
    """(valor, origem) de um parâmetro, ou (None, None). Origem ausente = parâmetro inútil."""
    d = (params or {}).get(chave) or {}
    if not isinstance(d, dict) or d.get("valor") is None or not d.get("origem"):
        return (None, None)
    return (d["valor"], d["origem"])


async def dimensionar_visita(db, visit_report_id: str) -> dict:
    """Dimensiona o que dá para dimensionar e NOMEIA o que não dá.

    Devolve `{obra, linhas:[...], bloqueios:{incognita: [itens]}}`, onde cada linha é
    `{item, quantidade, regra, origem, bloqueado_por}`. `quantidade=None` com
    `bloqueado_por` preenchido é resposta VÁLIDA e é metade do valor: hoje o Jordan não
    sabe nem o que está travado.
    """
    v = (await db.execute(text(
        "SELECT id::text, cliente_nome, coalesce(parametros,'{}'::jsonb) parametros "
        "FROM crm_visit_reports WHERE id::text = :i"), {"i": visit_report_id})).mappings().first()
    if not v:
        return {"erro": f"não achei a visita {visit_report_id!r}"}

    params = v["parametros"] or {}
    linhas: list[dict] = []
    bloqueios: dict[str, list[str]] = {}

    def bloqueia(item: str, incognita: str, regra: str) -> None:
        linhas.append({"item": item, "quantidade": None, "regra": regra,
                       "origem": None, "bloqueado_por": incognita})
        bloqueios.setdefault(incognita, []).append(item)

    cams, org_cams = _p(params, "cameras")
    canais, org_canais = _p(params, "canais_por_nvr")
    slots, org_slots = _p(params, "slots_hd_por_nvr")
    nb_rack, org_nb = _p(params, "nobreak_por_rack")
    racks, org_racks = _p(params, "racks")   # ← ninguém preencheu: é levantamento de campo

    # ── NVR: câmeras ÷ canais ────────────────────────────────────────────────────────────
    nvr = None
    if cams and canais:
        nvr = math.ceil(cams / canais)
        linhas.append({
            "item": "NVR (gravador)", "quantidade": nvr,
            "regra": f"{cams} câmeras ÷ {canais} canais por gravador, arredondado para cima",
            "origem": f"câmeras: {org_cams} · canais: {org_canais}", "bloqueado_por": None})
    else:
        bloqueia("NVR (gravador)", "número de câmeras ou canais por gravador",
                 "câmeras ÷ canais")

    # ── HD: NVR × slots ──────────────────────────────────────────────────────────────────
    if nvr and slots:
        linhas.append({
            "item": "HD de vigilância", "quantidade": nvr * slots,
            "regra": f"{nvr} gravadores × {slots} slots cada",
            "origem": f"gravadores: calculado acima · slots: {org_slots}",
            "bloqueado_por": None})
    else:
        bloqueia("HD de vigilância", "slots de HD por gravador", "gravadores × slots")

    # ── RACK: NÃO SE ESTIMA. ─────────────────────────────────────────────────────────────
    # Dá vontade de escrever "1 rack a cada 16 câmeras" e está errado: depende de distância,
    # de onde há energia e de onde o equipamento cabe. É levantamento de campo, e o campo é
    # ele. Procurei regra REAL nas propostas anteriores — a única com rack tem 2 câmeras e
    # 1 rack, o que é coincidência, não razão. Sem dado, incógnita nomeada.
    if racks:
        linhas.append({"item": "Rack", "quantidade": racks,
                       "regra": "levantamento de campo", "origem": org_racks,
                       "bloqueado_por": None})
    else:
        bloqueia("Rack", "pontos de concentração (levantamento em campo)",
                 "um rack por ponto de concentração — depende de distância, energia e espaço")

    # ── NOBREAK: 1 por rack ──────────────────────────────────────────────────────────────
    if racks and nb_rack:
        linhas.append({"item": "Nobreak", "quantidade": racks * nb_rack,
                       "regra": f"{nb_rack} por rack × {racks} racks",
                       "origem": org_nb, "bloqueado_por": None})
    else:
        bloqueia("Nobreak", "pontos de concentração (levantamento em campo)",
                 f"{nb_rack or '?'} por rack" + (f" ({org_nb})" if org_nb else ""))

    # ── SWITCH GIGA e CABO: dependem da mesma incógnita ──────────────────────────────────
    if not racks:
        bloqueia("Switch GIGA", "pontos de concentração (levantamento em campo)",
                 "interligação entre racks — quantidade sai da topologia")
    bloqueia("Cabo", "metragem (levantamento em campo)",
             "backbone entre racks + descida por câmera — não há regra que produza metros")
    bloqueia("Eletrocalha", "metragem (levantamento em campo)",
             "acompanha o cabo")

    logger.info("dimensionador: visita %s → %d linhas, %d dimensionadas, %d bloqueios",
                visit_report_id, len(linhas),
                sum(1 for x in linhas if x["quantidade"] is not None), len(bloqueios))
    return {"obra": v["cliente_nome"], "visita": v["id"], "linhas": linhas,
            "bloqueios": bloqueios}


def render_texto(d: dict) -> str:
    """A tela em texto — é este o formato que o Jordan pediu para poder CORRIGIR."""
    if d.get("erro"):
        return str(d["erro"])
    out = [f"DIMENSIONAMENTO — {d['obra']}", ""]
    for l in d["linhas"]:
        if l["quantidade"] is not None:
            out.append(f"  {l['quantidade']:>3}  {l['item']:<20} {l['regra']}")
            out.append(f"       {'':<20} origem: {l['origem']}")
        else:
            out.append(f"    ?  {l['item']:<20} {l['regra']}")
            out.append(f"       {'':<20} 🔒 bloqueado por: {l['bloqueado_por']}")
    if d["bloqueios"]:
        out.append("")
        for inc, itens in d["bloqueios"].items():
            out.append(f"  🔒 {len(itens)} item(ns) bloqueados por: {inc}")
            out.append(f"       {', '.join(itens)}")
    return "\n".join(out)
