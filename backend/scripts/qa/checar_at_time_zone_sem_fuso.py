#!/usr/bin/env python3
"""`AT TIME ZONE 'America/Manaus'` aplicado a coluna SEM fuso — a conversão que SOMA 4h.

Nasceu do risco 3 do pré-mortem da frente 4 (12/09/2026): *"a grade vai ficar 1 hora errada"*.
`communication_notifications.created_at` é `timestamp without time zone` guardando UTC. Em
Postgres, `AT TIME ZONE 'America/Manaus'` sobre um valor SEM fuso não converte de UTC para
Manaus — ele INTERPRETA o valor como sendo hora de Manaus e devolve um `timestamptz`, o que na
prática soma 4h na leitura. Foi assim que se leu **16:32 no lugar de 08:32**. Numa grade hora a
hora, isso pinta o turno errado; num alerta, manda o aviso para a hora errada.

A forma certa, para coluna sem fuso que guarda UTC:
    coluna AT TIME ZONE 'UTC' AT TIME ZONE 'America/Manaus'
Para `timestamptz`, `AT TIME ZONE 'America/Manaus'` sozinho está CERTO — e é por isso que este
caçador cruza cada ocorrência com o `information_schema` em vez de acusar pelo texto.

O SEGUNDO defeito, e ele é o oposto: há colunas sem fuso que guardam hora LOCAL de Manaus por
convenção declarada — `gp_clock_punches.punch_timestamp` é assim (ver `punch_service`, e
medido em 12/09: batida 17:02 com `created_at` 21:02 UTC). Nelas QUALQUER `AT TIME ZONE` está
errado, inclusive o par UTC→Manaus, que tiraria mais 4h. Ficam em `GUARDAM_LOCAL`.

LIMITES, porque número grande sem limite vira mentira:
- Só SQL literal em `.py`. Query montada por ORM ou concatenada em várias linhas escapa.
- A tabela sai do `FROM`/`JOIN` mais próximo (janela de 2.000 caracteres para cada lado),
  casando o alias: `h.created_at` num `FROM gp_holerites h` é julgado por ESSA tabela. Sem isso
  o check seria inútil para `created_at`, que existe em centenas de tabelas e basta UMA ser
  `timestamptz` para calar — que é exatamente a coluna do incidente.
- Não resolvendo o alias, julga pelo conjunto de tipos do nome da coluna e só acusa quando
  NENHUMA tabela a tem como `timestamptz` — erra para MENOS, nunca para mais.
- Precisa do Postgres para julgar. Sem ele (`QA_PG` / staging fora do ar), RECUSA rodar em vez
  de sair aprovando por ausência de medição — fila vazia não é resultado.

    python3 backend/scripts/qa/checar_at_time_zone_sem_fuso.py
    python3 backend/scripts/qa/checar_at_time_zone_sem_fuso.py --self-check
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(os.getenv("QA_BACKEND", "/opt/conecta-pro/backend"))
PG_CONTAINER = os.getenv("QA_PG", "conecta-pro-postgres-staging")
PG_DB = os.getenv("QA_PG_DB", "conecta_pro_staging")

#: Coluna sem fuso que guarda hora LOCAL de Manaus por convenção declarada no código que a
#: escreve. Sobre ela, QUALQUER conversão está errada — inclusive a "certa" UTC→Manaus.
GUARDAM_LOCAL = {"punch_timestamp"}

_TZ = r"AT\s+TIME\s+ZONE\s+"
#: A forma CERTA (o par), com o que ela converte. Casada PRIMEIRO, e o trecho sai da varredura.
_RE_PAR = re.compile(r"([A-Za-z_][\w.]*)\s*(?:\n\s*)?" + _TZ + r"'UTC'\s*(?:\n\s*)?" + _TZ
                     + r"'America/Manaus'", re.IGNORECASE)
#: `AT TIME ZONE 'America/Manaus'` sozinho, precedido do que está sendo convertido.
_RE = re.compile(r"([A-Za-z_][\w.]*(?:\(\))?|\)|')\s*(?:\n\s*)?" + _TZ + r"'America/Manaus'",
                 re.IGNORECASE)
#: Expressões que JÁ são timestamptz — `now()` e `current_timestamp` convertem certo sozinhas.
_JA_TEM_FUSO = {"now()", "current_timestamp", "statement_timestamp()", "clock_timestamp()"}


def _tipos_por_coluna() -> tuple[dict[tuple[str, str], str], dict[str, set[str]]]:
    """({(tabela, coluna): tipo}, {coluna: {tipos}}) — uma consulta, o banco inteiro."""
    sql = ("SELECT json_agg(json_build_array(table_name, column_name, data_type)) "
           "FROM information_schema.columns "
           "WHERE data_type LIKE 'timestamp%' AND table_schema = 'public'")
    try:
        out = subprocess.run(  # noqa: S603 — comando fixo, só o nome do container vem de env
            ["/usr/bin/docker", "exec", PG_CONTAINER, "psql", "-U", "postgres", "-d", PG_DB,
             "-tAc", sql], capture_output=True, text=True, timeout=60)
    except Exception as exc:  # noqa: BLE001
        print(f"RECUSO: não consegui falar com o Postgres ({PG_CONTAINER}/{PG_DB}): {exc}")
        raise SystemExit(2) from exc
    if out.returncode != 0 or not out.stdout.strip():
        print(f"RECUSO: {PG_CONTAINER}/{PG_DB} não respondeu — sem o schema este check não "
              f"julga nada, e sair verde por isso seria pior que não rodar.\n{out.stderr[:300]}")
        raise SystemExit(2)
    por_tab: dict[tuple[str, str], str] = {}
    por_col: dict[str, set[str]] = {}
    for tabela, coluna, tipo in json.loads(out.stdout.strip()):
        por_tab[(tabela.lower(), coluna.lower())] = tipo
        por_col.setdefault(coluna.lower(), set()).add(tipo)
    return por_tab, por_col


#: `FROM tabela alias` / `JOIN tabela AS alias` — o que dá para resolver sem parser de SQL.
# O alias é OPCIONAL e o `\s+` que o precede também: `FROM communication_notifications` no fim
# da string não casava, e o check calava em toda query sem alias — pego pelo --self-check.
_RE_FROM = re.compile(r"\b(?:FROM|JOIN)\s+([a-z_][\w]*)(?:\s+(?:AS\s+)?([a-z_]\w*))?", re.IGNORECASE)
#: Quanto texto antes da ocorrência ainda conta como "a mesma query".
JANELA = 2000


#: Palavra que vem depois do nome da tabela e NÃO é alias.
_NAO_E_ALIAS = {"on", "as", "where", "using", "left", "right", "inner", "outer", "full", "cross",
                "join", "group", "order", "limit", "having", "union", "and", "or", "set"}


def _tabela_de(texto: str, pos: int, alvo: str, por_tab) -> str | None:
    """Tabela do `x.coluna` (ou da coluna solta), pelo FROM/JOIN MAIS PRÓXIMO que a tenha.

    Distância absoluta, para os dois lados: num `SELECT to_char(h.created_at AT TIME ZONE …)
    FROM hr_vacation_requests h` o FROM vem depois; num `FROM opportunities WHERE …
    updated_at AT TIME ZONE …` vem antes. Olhar só para um lado calava metade dos casos, e
    preferir um dos lados fazia o check pegar a tabela da query SEGUINTE no mesmo arquivo.
    """
    col = alvo.split(".")[-1].lower()
    alias = alvo.split(".")[0].lower() if "." in alvo else None
    cands: list[tuple[int, str]] = []
    for m in _RE_FROM.finditer(texto[max(0, pos - JANELA): pos + JANELA]):
        tabela, ap = m.group(1).lower(), (m.group(2) or "").lower()
        if ap in _NAO_E_ALIAS:
            ap = ""
        if (alias is None or alias in (ap, tabela)) and (tabela, col) in por_tab:
            cands.append((abs(max(0, pos - JANELA) + m.start() - pos), tabela))
    return min(cands)[1] if cands else None


def _self_check() -> int:
    """Prova que o check acusa o padrão errado E cala no certo — sobre o schema REAL.

    Trava que só sabe dizer "0" é indistinguível de trava quebrada. Os casos abaixo são os do
    banco: `communication_notifications.created_at` (sem fuso, o do incidente) e
    `crm_meetings.quando` (com fuso, onde a conversão sozinha está certa).
    """
    import tempfile

    casos = [
        ("errado_sem_alias.py", "SELECT to_char(created_at AT TIME ZONE 'America/Manaus','HH24:MI') "
                                "FROM communication_notifications", 1),
        ("errado_com_alias.py", "SELECT n.created_at AT TIME ZONE 'America/Manaus' "
                                "FROM communication_notifications n", 1),
        ("certo_par.py", "SELECT created_at AT TIME ZONE 'UTC' AT TIME ZONE 'America/Manaus' "
                         "FROM communication_notifications", 0),
        ("certo_timestamptz.py", "SELECT quando AT TIME ZONE 'America/Manaus' FROM crm_meetings", 0),
        ("certo_now.py", "SELECT (now() AT TIME ZONE 'America/Manaus')::date", 0),
        ("errado_local.py", "SELECT punch_timestamp AT TIME ZONE 'UTC' AT TIME ZONE 'America/Manaus' "
                            "FROM gp_clock_punches", 1),
    ]
    falhas = 0
    with tempfile.TemporaryDirectory() as d:
        raiz = Path(d)
        for nome, sql, _ in casos:
            (raiz / nome).write_text(f'X = """{sql}"""\n', encoding="utf-8")
        global RAIZ
        antes, RAIZ = RAIZ, raiz
        try:
            por_tab, por_col = _tipos_por_coluna()
            for nome, _sql, esperado in casos:
                achados = _varrer(raiz / nome, por_tab, por_col)
                if len(achados) != esperado:
                    falhas += 1
                    print(f"SELF-CHECK FALHOU: {nome} deveria acusar {esperado} e acusou {len(achados)}")
        finally:
            RAIZ = antes
    print(f"self-check: {len(casos) - falhas}/{len(casos)} casos corretos")
    return 1 if falhas else 0


def _varrer(py: Path, por_tab, por_col) -> list[tuple[str, int, str, str]]:
    """Achados de UM arquivo. Separado de `main` para o self-check usar o mesmo código."""
    achados: list[tuple[str, int, str, str]] = []
    try:
        texto = py.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return achados
    if "America/Manaus" not in texto:
        return achados

    def _linha(pos: int) -> int:
        return texto[:pos].count("\n") + 1

    # 1) os PARES (forma certa) saem do texto antes da segunda varredura — senão o `'` que
    #    fecha 'UTC' vira o "alvo" do Manaus sozinho e a forma certa é acusada de errada.
    restante = texto
    for m in _RE_PAR.finditer(texto):
        alvo = m.group(1)
        if alvo.split(".")[-1].lower() in GUARDAM_LOCAL:
            achados.append((str(py), _linha(m.start()), alvo,
                            "guarda hora LOCAL de Manaus — o par UTC→Manaus tira mais 4h"))
        restante = restante.replace(m.group(0), " " * len(m.group(0)), 1)

    # 2) o Manaus SOZINHO, no que sobrou
    for m in _RE.finditer(restante):
        alvo = m.group(1)
        col = alvo.split(".")[-1].lower()
        if alvo.lower() in _JA_TEM_FUSO or alvo in (")", "'"):
            continue  # já é timestamptz, ou expressão que não dá para julgar (subestima)
        if col in GUARDAM_LOCAL:
            achados.append((str(py), _linha(m.start()), alvo,
                            "guarda hora LOCAL de Manaus — não se converte"))
            continue
        tabela = _tabela_de(restante, m.start(), alvo, por_tab)
        if tabela:
            if por_tab[(tabela, col)] != "timestamp with time zone":
                achados.append((str(py), _linha(m.start()), alvo,
                                f"`{tabela}.{col}` é `timestamp without time zone` — "
                                f"falta o AT TIME ZONE 'UTC' antes"))
            continue
        t = por_col.get(col)
        if t and "timestamp with time zone" not in t:
            achados.append((str(py), _linha(m.start()), alvo,
                            "é `timestamp without time zone` em toda tabela que a tem — "
                            "falta o AT TIME ZONE 'UTC' antes"))
    return achados


def main() -> int:
    if "--self-check" in sys.argv:
        return _self_check()
    if not RAIZ.is_dir():
        print(f"RECUSO: {RAIZ} não existe — este check roda no HOST, sobre o backend do repositório.")
        return 2
    por_tab, por_col = _tipos_por_coluna()
    achados: list[tuple[str, int, str, str]] = []

    for py in RAIZ.rglob("*.py"):
        if "__pycache__" in py.parts or py.name == Path(__file__).name:
            continue
        achados.extend(_varrer(py, por_tab, por_col))

    for arq, linha, alvo, por_que in achados:
        print(f"  {arq}:{linha} — `{alvo} AT TIME ZONE 'America/Manaus'`: {por_que}")
    print(f"TOTAL conversões erradas: {len(achados)}")
    return 1 if achados else 0


if __name__ == "__main__":
    sys.exit(main())
