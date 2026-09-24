"""Oráculo — VA e VT por contrato: a dedução da base do INSS nunca sai de chute (DGX AA6, 24/09/2026).

Por que existe
--------------
Decisão do dono (24/09/2026): as notas da CONECTAMAIS PATRIMONIAL — todas cessão de mão de obra —
passam a reter 11% (Art. 31 da Lei 9.711/98) sobre `bruto − (VA + VT)`. São 9 notas/mês, R$ 252 mil;
só nas três linhas do cronograma de setembro a dedução vale R$ 1.431,98.

O risco não é «o número não aparecer» — é o número aparecer ERRADO. Duas formas de errar, ambas
plausíveis e ambas caras:

1. **Deduzir pelo desconto do empregado.** `folha_verba_espelho` tem «Desconto VT» (1010,
   R$ 22.565,23) e «Desconto VR» (1011, R$ 5.897,71). São 4% e 1% do salário DO EMPREGADO, não o
   custo do benefício pago pela empresa. Deduzir por ali dá um número MENOR e o dono paga MAIS
   INSS — o oposto do que ele pediu.
2. **Deduzir com efetivo errado.** Medido em 24/09 em produção: `allocations`,
   `employee_alocacoes` e a escala discordam sobre quem está em qual cliente, e nenhuma bate com
   o cronograma do dono. Base de imposto com efetivo errado custa o imposto E a multa.

O que afirma (recontado por SQL próprio, não pelo serviço)
----------------------------------------------------------
(a) o serviço não lê `folha_verba_espelho` nem as rubricas 1010/1011 — provado por AST (nenhum
    literal nem chamada) e por VALOR (o VA apurado de um cliente difere do somatório de 1011
    daquelas pessoas, isto é: não é a mesma base disfarçada).
(b) pessoa com vínculo encerrado antes da competência não entra na contagem do contrato — mesmo
    quando a escala ainda a tem lançada.
(c) a base do INSS recontada aqui é sempre `bruto − VA − VT`, e o texto que vai na nota escreve
    exatamente esses números (conferido contra as três linhas reais do cronograma do dono:
    Prime Arena, Laranjeiras Village e Ideal Flores).
(d) contrato sem apuração confiável devolve `sabe=False` com `va=None`/`vt=None` — nunca zero
    silencioso, que numa base de imposto é uma afirmação («não houve benefício»), não uma lacuna.
    E a CONTAGEM de funcionários é uma certeza SEPARADA do valor: quando as fontes de alocação
    discordam da escala, `pessoas` volta None — «QUANTIDADE DE FUNCIONÁRIOS NO CONTRATO» é
    declaração legal na nota, e a escala não responde essa pergunta sozinha (Ideal Flores: escala
    11, allocations 14, employee_alocacoes 12, efetivo real confirmado pelo dono 13).
(e) a contagem de pessoas por contrato não inventa gente: todo employee_id somado está em pelo
    menos uma das três fontes de alocação/escala daquele cliente na competência.

Estado medido no nascimento (produção, 24/09/2026)
--------------------------------------------------
    módulo `va_vt_contrato` não existe            → (a)(b)(c)(d)(e) VERMELHO
    beneficio_entregas / beneficio_entrega_itens  → 0 linhas
    folha_beneficio_conferencia 08/2026           → 54 pessoas, VR R$ 18.832,00, VT R$ 2.090,00
                                                     (43 de 54 com VT `sem_modalidade`)
    efetivo por cliente, 08/2026 (alloc/emp_aloc/escala/ponto/cronograma):
      Ideal Flores 14/13/11/13/12 · Laranjeiras 10/9/9/9/8 · Prime Arena 4/7/6/5/8

Como roda
---------
    docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" -e PYTHONPATH=/app \
      --env-file /opt/conecta-pro/.env -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \
      conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_aa6_va_vt.py

Sai 0 = verde; 1 = vermelho. Linha final `TOTAL desvios: N`.
"""

from __future__ import annotations

import ast
import asyncio
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

FONTE = Path("/app/modules/people_management/folha/services/va_vt_contrato.py")
if not FONTE.exists():  # rodando fora do container
    FONTE = Path(__file__).resolve().parents[1].parent / "modules/people_management/folha/services/va_vt_contrato.py"

#: as três linhas REAIS do cronograma do dono (09/2026, benefício de 08/2026)
CRONOGRAMA = [
    # tomador, bruto, VA, VT, base, INSS, pessoas
    ("Prime Arena", "29600.00", "1804.00", "880.00", "26916.00", "2960.76", 8),
    ("Laranjeiras Village", "42544.50", "2552.00", "1136.00", "38856.50", "4274.21", 8),
    # Ideal Flores: a planilha declara dedução 6.648,00 mas discrimina VA 2.244,00 + VT 2.160,00
    # = 4.404,00. 6648 − 4404 = 2244 = exatamente o VA de novo → o VA discriminado está PELA
    # METADE (deveria ler 4.488,00). Aqui vale a aritmética da própria nota: 4488 + 2160 = 6648.
    ("Ideal Flores", "65842.42", "4488.00", "2160.00", "59194.42", "6511.39", 12),
]

desvios: list[str] = []


def falha(msg: str) -> None:
    desvios.append(msg)
    print(f"  ✗ {msg}")


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _c(v) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ───────────────────────── (a) nunca o desconto do empregado ─────────────────────────


def a_ast() -> None:
    print("\n(a) o serviço não deduz pelo desconto do empregado (1010/1011 · folha_verba_espelho)")
    if not FONTE.exists():
        falha(f"{FONTE} não existe — o serviço da frente AA6 não foi escrito")
        return
    src = FONTE.read_text()
    try:
        arvore = ast.parse(src)
    except SyntaxError as e:
        falha(f"{FONTE.name} não compila: {e}")
        return
    # literais de string em QUALQUER posição executável, fora de docstrings e da constante-guarda
    proibidos = {"folha_verba_espelho", "verba_espelho"}
    achados = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.Constant) and isinstance(no.value, str):
            txt = no.value
            if any(p in txt for p in proibidos):
                achados.append(txt[:80])
    docstrings = {
        d.value.value
        for d in ast.walk(arvore)
        if isinstance(d, ast.Expr) and isinstance(d.value, ast.Constant) and isinstance(d.value.value, str)
    }
    achados = [a for a in achados if not any(a in d for d in docstrings)]
    if achados:
        falha(f"o serviço referencia a folha de desconto do empregado: {achados}")
    else:
        ok("nenhum SQL do serviço toca `folha_verba_espelho` (só a docstring explica por quê)")
    # a constante-guarda existe e está documentada
    if "RUBRICAS_PROIBIDAS" not in src:
        falha("o serviço não declara RUBRICAS_PROIBIDAS — a armadilha 1010/1011 fica sem registro")
    else:
        ok("RUBRICAS_PROIBIDAS declarada no serviço (1010/1011)")


async def a_valor(db) -> None:
    from sqlalchemy import text

    from modules.people_management.folha.services import va_vt_contrato as vv

    # a competência mais recente que TEM desconto de VT/VR na folha — comparar contra um mês
    # vazio deixaria a afirmação vazia (medido: 1010/1011 só existem de 01 a 07/2026)
    r = (
        await db.execute(
            text(
                "SELECT ano, mes, sum(valor) FROM folha_verba_espelho WHERE codigo IN ('1010','1011') "
                "GROUP BY 1,2 ORDER BY 1 DESC, 2 DESC LIMIT 1"
            )
        )
    ).first()
    if not r:
        falha("nenhuma linha 1010/1011 em folha_verba_espelho — a afirmação (a) por valor ficaria vazia")
        return
    ano_e, mes_e, espelho = r
    print(f"  · desconto do empregado (1010+1011) em {mes_e:02d}/{ano_e}: R$ {_c(espelho)}")
    linhas = await vv.apurar(db, ano_e, mes_e)
    total_apurado = sum(Decimal(str(ln["va_apurado"] or 0)) + Decimal(str(ln["vt_apurado"] or 0)) for ln in linhas)
    if _c(espelho) == _c(total_apurado):
        falha(
            f"o VA+VT apurado (R$ {total_apurado}) é IGUAL ao desconto do empregado "
            f"(1010+1011 = R$ {espelho}) — base errada disfarçada"
        )
    elif total_apurado == 0:
        falha(f"apuração de {mes_e:02d}/{ano_e} deu R$ 0,00 — comparação vazia, não prova nada")
    else:
        ok(
            f"{mes_e:02d}/{ano_e}: apurado R$ {_c(total_apurado)} ≠ desconto do empregado "
            f"R$ {_c(espelho)} — bases distintas, e a nossa é MAIOR (é custo, não desconto)"
        )
        if total_apurado < Decimal(str(espelho)):
            falha(
                "o apurado ficou MENOR que o desconto do empregado — sinal de que a base pode ter "
                "virado o desconto; o custo do benefício é sempre maior que o 4%+1% retido"
            )


# ───────────────────────── (b) quem saiu não conta ─────────────────────────


async def b_vinculo(db) -> None:
    from sqlalchemy import text

    from modules.people_management.folha.services import va_vt_contrato as vv

    print("\n(b) quem saiu antes da competência não entra na contagem do contrato")
    fora = (
        await db.execute(
            text(
                "SELECT DISTINCT e.id::text, e.nome, coalesce(e.data_desligamento, e.data_demissao) "
                "  FROM shifts s JOIN employees e ON e.id = s.employee_id "
                " WHERE s.shift_date BETWEEN date '2026-08-01' AND date '2026-08-31' "
                "   AND lower(coalesce(s.status,'')) <> 'cancelled' AND NOT coalesce(s.is_off_day,false) "
                "   AND coalesce(e.data_desligamento, e.data_demissao) < date '2026-08-01'"
            )
        )
    ).fetchall()
    linhas = await vv.apurar(db, 2026, 8)
    contados = {d["nome"] for ln in linhas for d in ln["detalhe"]}
    if not fora:
        ok("nenhum desligado com turno lançado em 08/2026 (nada a filtrar nesta competência)")
    for _eid, nome, dem in fora:
        if nome in contados:
            falha(f"{nome} (desligado em {dem:%d/%m/%Y}) foi contado num contrato de 08/2026")
        else:
            ok(f"{nome} (desligado em {dem:%d/%m/%Y}) tem turno lançado mas NÃO conta no contrato")
    # e não pode ser filtrado em SILÊNCIO: tem de sair na divergência de efetivo, com a causa
    vistos = {d["nome"]: d for ln in linhas for d in ln["efetivo"]["divergencias"]}
    for _eid, nome, _dem in fora:
        if nome not in vistos:
            falha(f"{nome} foi filtrado em silêncio — tem de aparecer na divergência de efetivo do contrato")
        elif "desligado" not in (vistos[nome]["causa"] or ""):
            falha(f"{nome} aparece na divergência mas sem a causa «desligado…»: {vistos[nome]['causa']}")


# ───────────────────────── (c) a base é bruto − VA − VT, e a nota escreve isso ─────────────────────────


def c_base() -> None:
    print("\n(c) base do INSS = bruto − VA − VT, e o texto da nota escreve exatamente esses números")
    from modules.people_management.folha.services import va_vt_contrato as vv

    for nome, bruto, va, vt, base_ok, inss_ok, pessoas in CRONOGRAMA:
        base = _c(Decimal(bruto) - Decimal(va) - Decimal(vt))
        inss = _c(base * Decimal("0.11"))
        if base != _c(base_ok):
            falha(f"{nome}: base recontada {base} ≠ cronograma {base_ok}")
            continue
        if abs(inss - _c(inss_ok)) > Decimal("0.01"):
            falha(f"{nome}: INSS recontado {inss} ≠ cronograma {inss_ok}")
            continue
        txt = vv.texto_discriminacao(bruto, va, vt, pessoas, "08/2026")
        for pedaco in (
            f"DEDUÇÕES DA BASE DE CÁLCULO: {vv.reais(Decimal(va) + Decimal(vt))}",
            f"QUANTIDADE DE FUNCIONÁRIOS NO CONTRATO: {pessoas:02d}",
            f"Vale Alimentação 08/2026: {vv.reais(va)}",
            f"Vale Transporte 08/2026: {vv.reais(vt)}",
            f"BASE DE CÁLCULO PARA RETENÇÃO DE INSS: {vv.reais(base)}",
            "Art. 31 da Lei n. 9.711/98",
            f"VALOR DA RETENÇÃO DE INSS (11%): {vv.reais(inss)}",
        ):
            if pedaco not in txt:
                falha(f"{nome}: o texto da nota não traz «{pedaco}»")
                break
        else:
            ok(f"{nome}: base {vv.reais(base)} · INSS {vv.reais(inss)} · discriminação completa na nota")
        if vv.inss_de(base) != inss:
            falha(f"{nome}: inss_de() diverge da reconta ({vv.inss_de(base)} vs {inss})")


# ───────────────────────── (d) «não sei» nunca vira zero ─────────────────────────


async def d_nao_sei(db) -> None:
    from modules.people_management.folha.services import va_vt_contrato as vv

    print("\n(d) contrato sem apuração confiável devolve «não sei», nunca zero silencioso")
    linhas = await vv.apurar(db, 2026, 8)
    if not linhas:
        falha("apurar() não devolveu nenhum contrato em 08/2026")
        return
    incertos = [ln for ln in linhas if not ln["sabe"]]
    for ln in linhas:
        if ln["sabe"] and (ln["va"] is None or ln["vt"] is None):
            falha(f"{ln['cliente']}: sabe=True mas VA/VT é None")
        if not ln["sabe"]:
            if ln["va"] is not None or ln["vt"] is not None:
                falha(f"{ln['cliente']}: sabe=False mas devolveu número ({ln['va']}/{ln['vt']})")
            elif not ln["motivos"]:
                falha(f"{ln['cliente']}: sabe=False sem motivo — silêncio não é resposta")
    ok(f"{len(incertos)} de {len(linhas)} contratos com o VALOR em «não sei», todos com motivo escrito")
    for ln in linhas:
        if not ln["pessoas_confiavel"] and ln["pessoas"] is not None:
            falha(f"{ln['cliente']}: contagem não confiável mas devolveu {ln['pessoas']} pessoas como se fosse")
        if not ln["pessoas_confiavel"] and not ln["pessoas_motivo"]:
            falha(f"{ln['cliente']}: contagem None sem motivo")
    n_inc = sum(1 for ln in linhas if not ln["pessoas_confiavel"])
    ok(f"{n_inc} de {len(linhas)} contratos com a CONTAGEM em «não sei» (valor apurado, cabeça não)")
    # a régua da contagem tem UM ponto de verdade conhecido: o dono confirmou 13 no Ideal Flores
    ideal = [ln for ln in linhas if "IDEAL FLORES" in ln["cliente"].upper()]
    if not ideal:
        falha("Ideal Flores não apareceu — sem ele não dá para conferir a régua da contagem")
    elif ideal[0]["pessoas_presentes"] != 13:
        falha(
            f"Ideal Flores: presentes no posto = {ideal[0]['pessoas_presentes']}, e o dono confirmou 13 "
            "(24/09/2026) — a régua «escala ∪ ponto, dentro do vínculo» deixou de bater"
        )
    else:
        ok("Ideal Flores: presentes no posto = 13, o mesmo efetivo que o dono confirmou em 24/09/2026")
    # a porta que a AA4 usa
    r = await vv.para_nota(db, 2026, 8, "47405340000166")  # Prime Arena
    if "sabe" not in r:
        falha("para_nota() não devolve a chave `sabe` — a emissão não tem como distinguir 0 de não sei")
    elif r["sabe"] is False and (r["va"] is not None or r["vt"] is not None):
        falha("para_nota(): sabe=False com número dentro")
    else:
        ok(f"para_nota(Prime Arena, 08/2026): sabe={r['sabe']} · va={r['va']} · vt={r['vt']}")
    r2 = await vv.para_nota(db, 2026, 8, "00000000000000")
    if r2["sabe"] is not False:
        falha("para_nota() de CNPJ inexistente devolveu sabe=True")
    else:
        ok("tomador inexistente → sabe=False, sem zero inventado")


# ───────────────────────── (e) ninguém entra do nada ─────────────────────────


async def e_pessoas(db) -> None:
    from sqlalchemy import text

    from modules.people_management.folha.services import va_vt_contrato as vv

    print("\n(e) toda pessoa somada num contrato está em alguma fonte de alocação/escala daquele cliente")
    linhas = await vv.apurar(db, 2026, 8)
    for ln in linhas:
        nomes = {d["nome"] for d in ln["detalhe"]}
        if not nomes:
            continue
        visto = {
            r[0]
            for r in (
                await db.execute(
                    text(
                        "SELECT e.nome FROM allocations a JOIN posts p ON p.id=a.post_id JOIN employees e ON e.id=a.employee_id "
                        " WHERE p.client_id = CAST(:c AS uuid) AND a.start_date <= date '2026-08-31' "
                        "   AND (a.end_date IS NULL OR a.end_date >= date '2026-08-01') "
                        "UNION SELECT e.nome FROM employee_alocacoes a JOIN condominios co ON co.id=a.condominio_id "
                        " JOIN employees e ON e.id=a.employee_id WHERE co.client_id = CAST(:c AS uuid) "
                        "   AND a.data_inicio <= date '2026-08-31' AND (a.data_fim IS NULL OR a.data_fim >= date '2026-08-01') "
                        "UNION SELECT e.nome FROM shifts s JOIN posts p ON p.id=s.post_id JOIN employees e ON e.id=s.employee_id "
                        " WHERE p.client_id = CAST(:c AS uuid) AND s.shift_date BETWEEN date '2026-08-01' AND date '2026-08-31' "
                        "   AND lower(coalesce(s.status,'')) <> 'cancelled' AND NOT coalesce(s.is_off_day,false)"
                    ),
                    {"c": ln["client_id"]},
                )
            ).fetchall()
        }
        intrusos = nomes - visto
        if intrusos:
            falha(f"{ln['cliente']}: pessoas somadas sem fonte no cliente — {sorted(intrusos)}")
        else:
            ok(f"{ln['cliente']}: {len(nomes)} pessoa(s), todas com fonte")
    # quem serviu dois clientes não pode ter o mês contado duas vezes: a soma dos dias de uma
    # pessoa em TODOS os contratos nunca passa dos dias do mês
    dias_mes = 31
    todos: dict[str, int] = {}
    for ln in linhas:
        for d in ln["detalhe"]:
            todos[d["nome"]] = todos.get(d["nome"], 0) + d["dias_vt"]
    excedidos = {n: v for n, v in todos.items() if v > dias_mes}
    if excedidos:
        falha(f"pessoa com mais dias que o mês, somando contratos: {excedidos} — seria deduzido duas vezes")
    else:
        ok(f"nenhuma pessoa com mais de {dias_mes} dias somando todos os contratos")


async def main() -> int:
    a_ast()
    if not FONTE.exists():
        print("\nTOTAL desvios:", len(desvios))
        return 1
    try:
        c_base()
    except Exception as e:  # noqa: BLE001
        falha(f"(c) explodiu: {e}")
    from core.database import async_session_factory

    async with async_session_factory() as db:
        for f in (a_valor, b_vinculo, d_nao_sei, e_pessoas):
            try:
                await f(db)
            except Exception as e:  # noqa: BLE001
                await db.rollback()
                falha(f"{f.__name__} explodiu: {type(e).__name__}: {e}")
    print("\nTOTAL desvios:", len(desvios))
    return 1 if desvios else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
