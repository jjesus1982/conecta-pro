"""Oráculo — a GRADE real/contratual e o MAPA DE PONTO contam as MESMAS pessoas que a régua
da triagem (12/09/2026, frente 4 do plano DigiExpress).

Por que existe: o pré-mortem da frente 4 previu que "a tela vai mostrar número diferente do
que o Hermes falou às 08:30" — dois caminhos para a mesma pergunta viram duas verdades (a tela
de férias mostrou 15 onde havia 19). E previu que "posto descoberto vai ser pintado para gente
que não devia estar lá" — a Cintia (afastada pelo INSS) e o Aryelton (contrato suspenso)
apareceram com centenas de batidas; sem `SQL_NAO_AUSENTE_HOJE` a grade cobra quem está de
licença.

O que afirma, contra as FONTES (não contra o próprio módulo):
  1. A rota `/api/v1/redesign/data/{slug}` está em `app.routes` e o builder do operacional
     entrega as telas `mapa-de-ponto` e `grid-real-contratual`.
  2. Pessoa a pessoa: o conjunto (turno, pessoa) do mapa de HOJE == o conjunto da régua, que é
     `shifts` do dia (turno esperado, como `presenca_ao_vivo` define) × colaborador ativo, não
     homologação, e `coorte_ponto.SQL_NAO_AUSENTE_HOJE` (férias/afastado/reta final fora).
  3. Ninguém que a régua exclui HOJE aparece no mapa — nem como descoberto, nem como nada.
  4. A coluna de HOJE da grade, posto a posto, tem `contratual` == turnos da régua no posto e
     `real` == turnos atendidos no mapa. Uma régua, duas superfícies.

Estado medido no nascimento (12/09/2026, staging): as telas NÃO existiam (ImportError do módulo
`mapa_de_ponto`); a triagem era só prosa do Hermes; `presenca_ao_vivo` NÃO aplicava
`SQL_NAO_AUSENTE_HOJE` — o ADAILSON (reta final, último dia registrado) tinha turno hoje às
19:00 no Laranjeiras e sairia como ausente.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho.
"""
from __future__ import annotations

import asyncio
import sys

#: A régua, escrita AQUI de novo de propósito (o oráculo afirma a regra, não a foto): turno
#: esperado do dia × pessoa ativa, não homologação, não ausente hoje.
_SQL_REGUA = """
SELECT sh.id::text AS shift_id, sh.employee_id::text AS employee_id, e.nome, sh.post_id::text AS post_id
  FROM shifts sh JOIN employees e ON e.id = sh.employee_id
 WHERE sh.shift_date = (now() AT TIME ZONE 'America/Manaus')::date
   AND sh.employee_id IS NOT NULL AND sh.is_off_day = FALSE AND sh.status <> 'cancelled'
   AND sh.is_active = TRUE
   AND lower(coalesce(e.status,'')) = 'ativo' AND coalesce(e.is_homologacao,false) = false
   {nao_ausente}
"""

#: Quem tem turno hoje mas a régua EXCLUI (o que a tela não pode cobrar).
_SQL_EXCLUIDOS = """
SELECT DISTINCT sh.employee_id::text, e.nome
  FROM shifts sh JOIN employees e ON e.id = sh.employee_id
 WHERE sh.shift_date = (now() AT TIME ZONE 'America/Manaus')::date
   AND sh.employee_id IS NOT NULL AND sh.is_off_day = FALSE AND sh.status <> 'cancelled'
   AND sh.is_active = TRUE
   AND NOT (lower(coalesce(e.status,'')) = 'ativo' AND coalesce(e.is_homologacao,false) = false
            {nao_ausente})
"""

_ATENDIDOS = {"ok", "atendido_com_atraso", "atendido_posto_incorreto"}


async def main() -> int:
    from sqlalchemy import text

    from core.database import get_db
    from modules.people_management.ponto.coorte_ponto import SQL_NAO_AUSENTE_HOJE

    falhas: list[str] = []

    # 1) rota montada + telas entregues pelo builder do módulo
    from main_production import app

    rotas = [r.path for r in app.routes if getattr(r, "path", "") == "/api/v1/redesign/data/{slug}"]
    if not rotas:
        falhas.append("a rota /api/v1/redesign/data/{slug} não está em app.routes")

    gen = get_db()
    db = await gen.__anext__()
    try:
        from modules.operacional.controllers.redesign_data_controller import BUILDERS

        telas = await BUILDERS["operacional"](db)
    except Exception as exc:  # noqa: BLE001 — o builder não existir É o vermelho
        print(f"FALHOU: builder do operacional não entregou telas: {type(exc).__name__}: {exc}")
        raise AssertionError("as telas da frente 4 não existem") from exc
    mapa, grade = telas.get("mapa-de-ponto"), telas.get("grid-real-contratual")
    for nome, tela in (("mapa-de-ponto", mapa), ("grid-real-contratual", grade)):
        if not isinstance(tela, dict) or "_meta" not in tela:
            falhas.append(f"tela '{nome}' ausente do builder do operacional (ou sem _meta)")
    if falhas:
        for f in falhas:
            print("FALHOU:", f)
        raise AssertionError(f"{len(falhas)} desvio(s): a grade/mapa não existem ainda")

    # 2) pessoa a pessoa contra a régua
    regua = (await db.execute(text(_SQL_REGUA.format(nao_ausente=SQL_NAO_AUSENTE_HOJE)))).mappings().all()
    esperado = {(r["shift_id"], r["employee_id"]) for r in regua}
    itens = mapa["_meta"]["itens"]
    visto = {(i["shift_id"], i["employee_id"]) for i in itens}
    nome_de = {r["employee_id"]: r["nome"] for r in regua}
    for sid, eid in sorted(esperado - visto):
        falhas.append(f"{nome_de[eid]} tem turno hoje pela régua (shift {sid[:8]}) e NÃO está no mapa")
    for sid, eid in sorted(visto - esperado):
        quem = next((i["nome"] for i in itens if i["shift_id"] == sid), eid)
        falhas.append(f"{quem} está no mapa (shift {sid[:8]}) e a régua NÃO o espera hoje")

    # 3) excluídos pela régua não aparecem — nem como descoberto
    excluidos = (await db.execute(text(_SQL_EXCLUIDOS.format(nao_ausente=SQL_NAO_AUSENTE_HOJE)))).all()
    ids_excl = {e for e, _ in excluidos}
    for i in itens + mapa["_meta"].get("fora_de_escala", []):
        if i["employee_id"] in ids_excl:
            falhas.append(f"{i['nome']} está de férias/afastado/reta final e aparece no mapa como "
                          f"'{i.get('estado')}' — a régua diz que não é cobrado")

    # 4) coluna de HOJE da grade == mapa, posto a posto
    hoje = mapa["_meta"]["dia"]
    por_posto_regua: dict[str, int] = {}
    for r in regua:
        por_posto_regua[r["post_id"]] = por_posto_regua.get(r["post_id"], 0) + 1
    por_posto_real: dict[str, int] = {}
    for i in itens:
        if i.get("estado") in _ATENDIDOS:
            por_posto_real[i["post_id"]] = por_posto_real.get(i["post_id"], 0) + 1
    celulas = {p["post_id"]: p["dias"].get(hoje) for p in grade["_meta"]["postos"]}
    for pid, contratual in por_posto_regua.items():
        cel = celulas.get(pid)
        if not cel:
            falhas.append(f"posto {pid[:8]} tem {contratual} turno(s) hoje pela régua e não tem célula na grade")
            continue
        if cel["contratual"] != contratual:
            falhas.append(f"grade diz contratual={cel['contratual']} e a régua diz {contratual} no posto {pid[:8]} hoje")
        if cel["real"] != por_posto_real.get(pid, 0):
            falhas.append(f"grade diz real={cel['real']} e o mapa diz {por_posto_real.get(pid, 0)} no posto {pid[:8]} hoje")

    print(f"régua hoje: {len(esperado)} turno(s) · mapa: {len(itens)} · excluídos pela régua: "
          f"{len(ids_excl)} · postos na grade hoje: {len(por_posto_regua)}")
    for f in falhas:
        print("FALHOU:", f)
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) entre a grade/mapa e a régua da triagem")
    print("OK grade/mapa: a mesma régua da triagem, pessoa a pessoa; ninguém de férias/afastado cobrado")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)
