#!/usr/bin/env python3
"""Lista literal no código × valores REAIS da coluna no banco.

Os dois defeitos mais caros de 11-12/08/2026 foram o mesmo erro:

  fiscal.py     `status NOT IN ('pago','paga','concluido','concluida')`
                A tabela usa 'cumprida'. Toda obrigação cumprida contava como pendente:
                31 anunciadas, 5 de verdade.

  _fin_contabil `if conta[:1] == "3": receita  elif "4": despesa`
                O plano usa 4=Receita e 5=Despesa, e não tem grupo 3. A receita virou
                despesa negativa e virou o "PL": +R$ 2,02 MILHÕES onde há prejuízo de
                R$ 97 mil. E as 12 contas de despesa sumiram do balanço.

Nenhum é bug de lógica. Nos dois, alguém CHUTOU o vocabulário do domínio em vez de medir —
e o código ficou certo em relação ao que o autor imaginou, errado em relação ao banco.

Isto é mecânico: extrai as listas literais comparadas contra coluna, roda o DISTINCT real, e
denuncia LITERAL QUE NÃO EXISTE na coluna — o código falando um vocabulário que a tabela não
tem. `CRITICO` = a lista inteira está fora, ou seja, o filtro nunca casou nada.

O que NÃO é achado: existir no banco valor fora da lista. Filtro serve para isso. A primeira
versão confundiu as duas coisas e acusou 126 de 173 — linter ruidoso é linter desligado.

LIMITE CONHECIDO — atribuição de tabela: a tabela vem do `FROM` mais próximo antes da
comparação. Em SQL com JOIN, subquery ou duas queries na mesma função, pode pegar a tabela
errada e comparar contra a coluna de outra. Trate cada achado como PISTA a conferir, não
como veredito — confira o SQL na linha apontada antes de mexer.

Uso:
    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/qa/checar_vocabulario.py
    ... --self-check     (só as provas, sem banco)
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path

RAIZ = Path(os.getenv("QA_RAIZ", "/app"))

#: `coluna IN ('a','b')` / `coluna NOT IN (...)`. Aceita o que a casa escreve em volta da
#: coluna: `lower(coalesce(status::text,''))`, `p.status::text`, `o.tipo`.
_RE_IN = re.compile(
    r"""(?P<expr>[\w.]*\(?[\w.]*\bcoalesce\([^)]*\)|[\w.]+(?:::\w+)?)   # expressão da coluna
        \s+(?P<neg>NOT\s+)?IN\s*\(\s*
        (?P<lista>'[^)]*?')                                              # só literais
        \s*\)""",
    re.I | re.X,
)
_RE_COLUNA = re.compile(r"\b(\w+)\s*(?:::\w+)?\s*(?:,|\)|$)")
_RE_FROM = re.compile(r"\bFROM\s+([a-z_][a-z0-9_]*)", re.I)
#: `FROM employees c` / `JOIN payable_accounts p` — alias -> tabela
_RE_ALIAS = re.compile(r"\b(?:FROM|JOIN)\s+([a-z_][a-z0-9_]*)\s+(?:AS\s+)?([a-z][a-z0-9_]*)\b", re.I)
_RE_LITERAL = re.compile(r"'([^']*)'")

#: Colunas que não são vocabulário fechado — comparar contra DISTINCT não diz nada.
_IGNORAR_COLUNA = {"id", "uuid", "cnpj", "cpf", "email", "code", "codigo", "nome", "name"}


def _alias_de(expr: str) -> str | None:
    """`lower(c.status::text)` -> 'c'. Sem qualificador, None."""
    m = re.search(r"\b([a-z][a-z0-9_]*)\s*\.\s*[a-z_][a-z0-9_]*", expr, re.I)
    return m.group(1).lower() if m else None


def _coluna_de(expr: str) -> str | None:
    """Último identificador da expressão: `lower(coalesce(o.status::text,''))` -> status."""
    ids = re.findall(r"[a-z_][a-z0-9_]*", expr, re.I)
    fora = {"lower", "upper", "coalesce", "trim", "cast", "text", "nullif", "left", "right"}
    reais = [i for i in ids if i.lower() not in fora]
    return reais[-1].lower() if reais else None


def achados_no_arquivo(caminho: Path) -> list[dict]:
    """Ocorrências de lista literal comparada contra coluna, com a tabela do mesmo SQL."""
    try:
        texto = caminho.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    if " IN (" not in texto.upper() and " IN(" not in texto.upper():
        return []

    out = []
    for m in _RE_IN.finditer(texto):
        coluna = _coluna_de(m.group("expr"))
        if not coluna or coluna in _IGNORAR_COLUNA:
            continue
        literais = _RE_LITERAL.findall(m.group("lista"))
        if not literais or any(len(x) > 40 for x in literais):
            continue
        # tabela: o FROM mais próximo ANTES da comparação, dentro do mesmo trecho
        antes = texto[max(0, m.start() - 600):m.start()]
        tabelas = _RE_FROM.findall(antes)
        if not tabelas:
            continue

        # INDETERMINADO em vez de CRITICO quando a atribuição de tabela não é confiável.
        # Sugestão do T1 (12/08), depois de dois falsos positivos no financeiro com a mesma
        # raiz: `c.status` era de employees e não de bank_transactions (SQL montado por
        # helper), e numa função com duas queries a marcada era payable_accounts, não a de
        # cima. Acusar CRITICO sobre atribuição chutada gasta a confiança da trava.
        # O FROM pode vir DEPOIS: em `SUM(x) FILTER (WHERE status IN (...))` a comparação
        # está na lista do SELECT, e a janela para trás pega o FROM da query ANTERIOR. Foi o
        # 2o falso positivo do T1 — payable_accounts marcada como bank_transactions.
        # Se houver fronteira de string (`text(` ou aspas triplas) entre o último FROM e a
        # comparação, aquele FROM é de OUTRO comando: procura o do bloco atual, à frente.
        depois = texto[m.end():m.end() + 800]
        ult_from = antes.upper().rfind("FROM ")
        fronteira = max(antes.rfind('"""'), antes.rfind("text("))
        if fronteira > ult_from:
            adiante = _RE_FROM.findall(depois.split('"""')[0])
            if adiante:
                tabelas = [adiante[0]]
                antes = antes + depois        # aliases do bloco atual entram na resolução
            else:
                tabelas = []
        if not tabelas:
            continue

        apelidos = {a.lower(): t.lower() for t, a in _RE_ALIAS.findall(antes)}
        alias = _alias_de(m.group("expr"))
        if alias and alias in apelidos:
            tabela, incerto = apelidos[alias], False        # qualificador resolvido: confia
        elif alias:
            tabela, incerto = tabelas[-1].lower(), True     # qualificador que não resolve
        else:
            tabela = tabelas[-1].lower()
            incerto = len(set(t.lower() for t in tabelas)) > 1   # mais de um FROM na janela

        out.append({
            "incerto": incerto,
            "arquivo": str(caminho.relative_to(RAIZ)) if str(caminho).startswith(str(RAIZ)) else str(caminho),
            "linha": texto[:m.start()].count("\n") + 1,
            "tabela": tabela,
            "coluna": coluna,
            "negado": bool(m.group("neg")),
            "literais": sorted(set(literais)),
        })
    return out


def varrer(raiz: Path) -> list[dict]:
    achados = []
    for p in raiz.rglob("*.py"):
        if any(x in p.parts for x in ("__pycache__", "venv", "node_modules", "tests", "scripts")):
            continue
        achados.extend(achados_no_arquivo(p))
    return achados


async def confrontar(achados: list[dict]) -> list[dict]:
    """Roda o DISTINCT real de cada (tabela, coluna) e devolve o que a lista não prevê."""
    from sqlalchemy import text

    from core.database import async_session_factory

    divergentes = []
    cache: dict[tuple[str, str], set[str] | None] = {}
    async with async_session_factory() as db:
        for a in achados:
            chave = (a["tabela"], a["coluna"])
            if chave not in cache:
                try:
                    rows = (await db.execute(text(
                        f"SELECT DISTINCT {a['coluna']}::text FROM {a['tabela']} "
                        f"WHERE {a['coluna']} IS NOT NULL LIMIT 60"))).fetchall()
                    cache[chave] = {str(r[0]).lower() for r in rows}
                except Exception:  # noqa: BLE001 — tabela/coluna que não existe não é achado daqui
                    await db.rollback()
                    cache[chave] = None
            reais = cache[chave]
            if not reais:
                continue
            previstos = {x.lower() for x in a["literais"]}
            # O sinal NÃO é "existe valor no banco fora da lista" — filtro serve para isso, e
            # a primeira versão deste check acusou 126 de 173 por confundir as duas coisas.
            # O sinal é LITERAL QUE NÃO EXISTE NA COLUNA: o código fala um vocabulário que a
            # tabela não tem. No caso fiscal, 'pago'/'paga'/'concluido'/'concluida' — os
            # quatro ausentes, porque a tabela diz 'cumprida'. O filtro nunca casou nada.
            fantasmas = sorted(previstos - reais)
            if not fantasmas:
                continue
            divergentes.append({
                **a,
                "literais_inexistentes": fantasmas,
                "no_banco": sorted(reais),
                "gravidade": ("INDETERMINADO" if a.get("incerto") else
                              "CRITICO" if len(fantasmas) == len(previstos) else "ATENCAO"),
            })
    # Crítico primeiro: lista inteiramente fora do vocabulário é filtro que nunca casa.
    return sorted(divergentes, key=lambda d: (d["gravidade"] != "CRITICO", d["arquivo"]))


def _self_check() -> None:
    """As provas são os dois casos reais — se o caçador não os pega, não serve."""
    import tempfile

    caso = '''
    obr = await _scalar(db,
        "SELECT count(*) FROM fiscal_obligations "
        "WHERE status::text NOT IN ('pago','paga','concluido','concluida')")
    ok = await _scalar(db, "SELECT count(*) FROM users WHERE role IN ('admin','supervisor')")
    livre = await _scalar(db, "SELECT count(*) FROM employees WHERE nome IN ('a','b')")
    '''
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "caso.py"
        p.write_text(caso)
        got = achados_no_arquivo(p)

    achou = {(a["tabela"], a["coluna"]) for a in got}
    assert ("fiscal_obligations", "status") in achou, f"não pegou o caso real: {achou}"
    assert ("users", "role") in achou, f"não pegou IN simples: {achou}"
    assert ("employees", "nome") not in achou, "coluna livre (nome) não deveria entrar"

    alvo = next(a for a in got if a["tabela"] == "fiscal_obligations")
    assert alvo["negado"] is True
    assert alvo["literais"] == ["concluida", "concluido", "paga", "pago"], alvo["literais"]
    assert _coluna_de("lower(coalesce(o.status::text,''))") == "status"
    assert _coluna_de("p.tipo_lancamento") == "tipo_lancamento"

    # O critério: literal que NÃO existe na coluna. Sem isto o check acusa todo filtro
    # intencional — foi o que aconteceu na 1a versão (126 de 173) e mata a ferramenta.
    def _classificar(literais, no_banco):
        f = sorted({x.lower() for x in literais} - {x.lower() for x in no_banco})
        return None if not f else ("CRITICO" if len(f) == len(literais) else "ATENCAO")

    assert _classificar(["pago", "paga", "concluido", "concluida"],
                        ["cumprida", "pendente"]) == "CRITICO", "o caso fiscal tem que ser crítico"
    assert _classificar(["draft", "published"], ["draft", "published"]) is None, \
        "filtro cujos literais existem NÃO é achado, mesmo com outros valores no banco"
    assert _classificar(["published", "arquivada"], ["draft", "published"]) == "ATENCAO"
    print("self-check OK — pega os casos reais, ignora coluna livre e filtro legítimo")


async def main() -> int:
    achados = varrer(RAIZ / "modules")
    print(f"listas literais comparadas contra coluna: {len(achados)}")
    divergentes = await confrontar(achados)
    if not divergentes:
        print("nenhuma divergência: toda lista cobre os valores que existem no banco")
        return 0
    criticos = [d for d in divergentes if d["gravidade"] == "CRITICO"]
    print(f"\n{len(divergentes)} lista(s) com literal que NAO EXISTE na coluna "
          f"({len(criticos)} crítica(s) — lista inteira fora do vocabulário):\n")
    for d in divergentes:
        print(f"  [{d['gravidade']}] {d['arquivo']}:{d['linha']}")
        print(f"    {d['tabela']}.{d['coluna']}  {'NOT ' if d['negado'] else ''}IN {d['literais']}")
        print(f"    não existe na coluna: {d['literais_inexistentes']}")
        print(f"    a coluna tem: {d['no_banco']}\n")
    return 1 if criticos else 0


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
        raise SystemExit(0)
    sys.path.insert(0, str(RAIZ))
    raise SystemExit(asyncio.run(main()))
