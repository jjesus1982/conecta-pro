"""Oráculo — reserva técnica, PLR sindicato e taxa administrativa saem da FONTE, nunca do código (12/09/2026).

Frente 7 do plano de paridade DigiExpress/DGX. O pré-mortem previu o defeito clássico desta casa:
o percentual vira literal no código ("3" escrito no classificador em vez de sair do plano de
contas — o balanço que não fechava). Reserva técnica varia por CCT, função e escala; PLR
sindicato é da convenção; taxa administrativa é decisão do dono. Nenhum dos três pode ser
chumbado, e nenhum pode ter default: parâmetro ausente é "parâmetro ausente", não 0 nem 10%.

Três afirmações:

  1. Nenhum arquivo de `modules/crm` atribui número literal a nome que contenha reserva/PLR/
     taxa admin (atribuição, default de função, keyword, `dict[...]`, `.get(chave, número)`).
     O detector é provado contra um trecho sabidamente errado antes de varrer — detector que
     não pega o exemplo ruim não vale como trava.
  2. Os três parâmetros existem no armazém de precificação (`crm_pricing_params`) COM vigência
     e origem — a mesma régua das margens por dimensão: número sem procedência ninguém confia.
  3. A simulação de um contrato REAL do staging lê exatamente esses parâmetros: o valor, a
     origem e a vigência que aparecem no resultado são os da linha do banco; parâmetro sem
     confirmação do dono NÃO entra no custo (o componente sai None com motivo), e parâmetro
     confirmado entra pelo percentual da linha — testado com a mesma função de resolução sobre
     uma cópia confirmada em memória, sem gravar nada.

Estado medido no nascimento (12/09/2026, staging): 0 ocorrências de "reserva" no repositório,
`crm_pricing_params` sem coluna de vigência/origem, e nenhum serviço de simulação por contrato —
afirmações 2 e 3 VERMELHAS.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho.
"""
from __future__ import annotations

import ast
import asyncio
import pathlib
import re
import sys
from datetime import date

CHAVES = ("reserva_tecnica_pct", "plr_sindicato_pct", "taxa_admin_pct")
NOME_SUSPEITO = re.compile(r"reserva|plr|taxa_adm|admin_pct|taxa_administr", re.I)
RAIZ_CRM = pathlib.Path("/app/modules/crm")

#: O detector tem de acusar TODAS estas linhas. Se deixar passar uma, o oráculo é cego.
TRECHO_RUIM = """
RESERVA_TECNICA = 0.10
def f(plr_sindicato_pct=0.05): pass
g(taxa_admin_pct=0.08)
p = {"reserva_tecnica_pct": 0.1}
x = params.get("plr_sindicato_pct", 0.0)
"""


def _num(n: ast.AST) -> bool:
    return isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool)


def literais_chumbados(src: str, arquivo: str) -> list[str]:
    """Linhas onde um nome suspeito recebe número literal."""
    achados: list[str] = []
    try:
        arvore = ast.parse(src)
    except SyntaxError as e:  # arquivo quebrado é problema de outro oráculo
        return [f"{arquivo}: não parseia ({e})"]

    def acusa(no: ast.AST, nome: str) -> None:
        achados.append(f"{arquivo}:{getattr(no, 'lineno', '?')} '{nome}' = número literal")

    for no in ast.walk(arvore):
        if isinstance(no, (ast.Assign, ast.AnnAssign)):
            alvos = no.targets if isinstance(no, ast.Assign) else [no.target]
            for a in alvos:
                nome = getattr(a, "id", None) or getattr(a, "attr", None) or ""
                if NOME_SUSPEITO.search(nome) and _num(no.value):
                    acusa(no, nome)
        elif isinstance(no, ast.keyword):
            if no.arg and NOME_SUSPEITO.search(no.arg) and _num(no.value):
                acusa(no, no.arg)
        elif isinstance(no, ast.arguments):
            pos = no.posonlyargs + no.args
            pares = list(zip(pos[len(pos) - len(no.defaults):], no.defaults, strict=True)) + list(zip(no.kwonlyargs, no.kw_defaults, strict=True))
            for a, d in pares:
                if d is not None and NOME_SUSPEITO.search(a.arg) and _num(d):
                    acusa(a, a.arg)
        elif isinstance(no, ast.Dict):
            for k, v in zip(no.keys, no.values, strict=True):
                if isinstance(k, ast.Constant) and isinstance(k.value, str) and NOME_SUSPEITO.search(k.value) and _num(v):
                    acusa(k, k.value)
        elif isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute) and no.func.attr == "get":
            if len(no.args) >= 2 and isinstance(no.args[0], ast.Constant) and isinstance(no.args[0].value, str) \
                    and NOME_SUSPEITO.search(no.args[0].value) and _num(no.args[1]):
                acusa(no, no.args[0].value)
    return achados


async def main() -> int:
    falhas: list[str] = []

    # 0) o detector pega o exemplo ruim (5 linhas → 5 acusações)
    prova = literais_chumbados(TRECHO_RUIM, "<prova>")
    if len(prova) != 5:
        falhas.append(f"detector cego: acusou {len(prova)} de 5 literais do trecho de prova — {prova}")

    # 1) nenhum literal em modules/crm
    n_arq = 0
    for py in sorted(RAIZ_CRM.rglob("*.py")):
        n_arq += 1
        for a in literais_chumbados(py.read_text(encoding="utf-8", errors="replace"), str(py)):
            falhas.append(f"percentual chumbado: {a}")

    # 2) os parâmetros existem no armazém com vigência e origem
    from sqlalchemy import text

    from core.database import get_db

    gen = get_db()
    db = await gen.__anext__()
    linhas: dict[str, dict] = {}
    try:
        rs = (await db.execute(text(
            "SELECT chave, valor::float AS valor, vigencia_inicio, vigencia_fim, origem, "
            "       confirmado_por, confirmado_em "
            "  FROM crm_pricing_params WHERE chave = ANY(:c)"), {"c": list(CHAVES)})).mappings().all()
        linhas = {r["chave"]: dict(r) for r in rs}
    except Exception as e:  # noqa: BLE001
        await db.rollback()
        falhas.append(f"armazém sem colunas de vigência/origem: {str(e).splitlines()[0][:160]}")
    for c in CHAVES:
        r = linhas.get(c)
        if not r:
            falhas.append(f"parâmetro '{c}' não existe em crm_pricing_params")
            continue
        if not r["vigencia_inicio"]:
            falhas.append(f"parâmetro '{c}' sem vigencia_inicio")
        if not (r["origem"] or "").strip():
            falhas.append(f"parâmetro '{c}' sem origem (CCT/decisão do dono)")

    # 3) a simulação de um contrato real lê a fonte
    try:
        from modules.crm.services import precificacao_contrato as prec
    except ImportError as e:
        falhas.append(f"serviço de simulação por contrato não existe: {e}")
        prec = None
    ctr = (await db.execute(text(
        "SELECT id::text, contract_number FROM contracts WHERE status='active' AND monthly_value > 0 "
        " ORDER BY monthly_value DESC LIMIT 1"))).first()
    if prec and ctr:
        ref = date.today()
        sim = await prec.simular_contrato(db, ctr[0], competencia=ref.strftime("%Y-%m"))
        params_sim = sim.get("parametros") or {}
        for c in CHAVES:
            p = params_sim.get(c)
            r = linhas.get(c)
            if not p:
                falhas.append(f"simulação de {ctr[1]} não expõe o parâmetro '{c}'")
                continue
            if r:
                if p.get("valor") != r["valor"] or (p.get("origem") or "") != (r["origem"] or ""):
                    falhas.append(f"'{c}' na simulação ({p.get('valor')}, {p.get('origem')!r}) ≠ banco "
                                  f"({r['valor']}, {r['origem']!r})")
                confirmado = bool(r["confirmado_em"])
                comp = (sim.get("componentes") or {}).get(c.removesuffix("_pct"))
                if confirmado and not isinstance(comp, (int, float)):
                    falhas.append(f"'{c}' confirmado no banco mas o componente não entrou no custo de {ctr[1]}")
                if not confirmado and comp is not None:
                    falhas.append(f"'{c}' SEM confirmação do dono e mesmo assim entrou no custo de {ctr[1]} "
                                  f"(componente={comp}) — default proibido")
            # caminho 'aplicado', sem gravar: a mesma função de resolução sobre uma cópia confirmada
            copia = dict(r or {}, chave=c, valor=0.07, vigencia_inicio=date(2026, 1, 1), vigencia_fim=None,
                         origem="prova", confirmado_por="oráculo", confirmado_em="2026-09-12")
            res = prec.resolver_parametro(copia, ref)
            if not (res.get("aplicavel") and res.get("valor") == 0.07):
                falhas.append(f"resolver_parametro não aplica linha confirmada e vigente: {res}")
            vencida = dict(copia, vigencia_fim=date(2025, 12, 31))
            if prec.resolver_parametro(vencida, ref).get("aplicavel"):
                falhas.append("resolver_parametro aplica parâmetro com vigência vencida")
    elif prec and not ctr:
        falhas.append("nenhum contrato ativo com valor no staging para simular")

    print(f"arquivos crm varridos: {n_arq} · parâmetros no armazém: {len(linhas)}/{len(CHAVES)} · "
          f"contrato simulado: {ctr[1] if ctr else '—'}")
    for f in falhas:
        print("FALHOU:", f)
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s): precificação não lê a fonte")
    print("OK precificação lê a fonte: nenhum percentual chumbado, os três parâmetros têm vigência e "
          "origem, e a simulação usa exatamente a linha do banco (sem confirmação = sem default)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)
