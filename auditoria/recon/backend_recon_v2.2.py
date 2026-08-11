#!/usr/bin/env python3
"""Backend recon do Conecta PRO — mapa 'codado × exposto × órfão' por módulo (READ-ONLY).

v2 (2026-08-07). Roda NO HOST (/opt/conecta-pro). Orquestra:
  1) dump das rotas MONTADAS (docker exec no container: main_production:app) — a verdade do
     que existe — JUNTO com o nome da função e o summary/docstring de cada endpoint.
  2) índice token→arquivo da SUPERFÍCIE (frontend/src clássico + redesign_builders +
     redesign_data_controller). Índice, não blob: a classificação exige que os segmentos
     distintivos da rota CO-OCORRAM NO MESMO ARQUIVO.
  3) tabelas que os builders do redesign leem por SQL direto — o redesign mostra dado sem
     chamar rota, então isso identifica falso-órfão de GET.
  4) classifica: EXPOSTO · ÓRFÃO (com motivo) · GERADOR de documento · 💰 dinheiro · 🏛️ gov.
  5) --curl: sonda uma amostra viva (200/4xx/5xx) p/ pegar 500 de schema drift.

O QUE MUDOU NA v2 (e por quê)
  a) PAREAMENTO POR CAMINHO, não substring. A v1 fazia `key in corpus` — substring numa
     string de megabytes com todos os tokens do front. `/hr/contracts/{id}/document` era
     dado como COBERTO porque a palavra "document" aparecia em qualquer lugar. Medido em
     2026-08-07 no people-management: 89 de 449 "expostas" (20%) só casavam por substring.
     Esse erro ESCONDE buraco — pior que o falso-órfão, que a v1 já documentava.
  b) LÊ O CONTROLLER. Cada rota vem com nome da função e a 1a linha da docstring/summary,
     então o relatório diz O QUE a capacidade é, não só que existe um path.
  c) CRUZA COM O SQL DOS BUILDERS. Órfã de GET cujo recurso casa com tabela que o builder
     lê vira "provável falso-órfão", em vez de entrar na fila como buraco.

Uso:
  python3 backend_recon.py <prefixo-de-rota>
  python3 backend_recon.py people-management --surface redesign
  python3 backend_recon.py financial --curl --token <BEARER>
  python3 backend_recon.py --self-check          # valida a logica de pareamento, sem docker

NÃO escreve nada. NÃO deploya. Ancora tudo em rota+arquivo (evidência).
"""

import json
import os
import re
import subprocess
import sys

HOST_ROOT = "/opt/conecta-pro"
CONTAINER = "conecta-pro-backend"

_REDESIGN = [
    f"{HOST_ROOT}/backend/modules/operacional/controllers/redesign_builders",
    f"{HOST_ROOT}/backend/modules/operacional/controllers/redesign_data_controller.py",
    f"{HOST_ROOT}/frontend/src/app/redesign",
    f"{HOST_ROOT}/frontend/src/components/redesign",
]
_CLASSIC = [
    f"{HOST_ROOT}/frontend/src/app/modulos",
    f"{HOST_ROOT}/frontend/src",
]
SURFACE_SETS = {"all": _CLASSIC + _REDESIGN, "redesign": _REDESIGN, "classic": _CLASSIC}
_EXCLUDE_DIRS = {"classic": ["redesign"], "all": [], "redesign": []}
_BUILDERS_DIR = f"{HOST_ROOT}/backend/modules/operacional/controllers/redesign_builders"

GEN = re.compile(
    r"(pdf|xml|download|export|zip|danfse|danfe|comprovante|espelho|recibo|dominio|holerite|/csv)",
    re.I,
)
# `payroll` e `pay-batch` entraram na v2: /dp/payroll/pay-batch passava SEM a flag 💰 na v1
# (tem "pay-batch", nao "payment") — e e a porta de entrada da fila de pagamento da folha.
MONEY = re.compile(
    r"(payslip|holerite|folha|recibo|dominio|pix|pagamento|payment|payroll|pay-batch|boleto|comprovante|inter)",
    re.I,
)
# `das` e `nfe` PRECISAM de fronteira de segmento: sem isso, "marcar-toDAS" e
# "mediDAS-administrativas" levavam a flag de governo (18 falsos no operacional, medido
# 2026-08-07). A sigla so vale como segmento inteiro do path.
_GOV_SIGLA = r"(?<![a-z])(das|nfe|nfse|darf|dctf|sped|reinf|fgts|ecac)(?![a-z])"
GOV = re.compile(rf"(esocial|danfse|gov|fiscal|caixa|{_GOV_SIGLA})", re.I)

#: Segmentos que nao identificam recurso — nao servem de prova de cobertura.
_GENERICOS = {
    "pdf", "download", "xml", "export", "view", "view-url", "download-zip", "zip",
    "preview", "csv", "list", "all", "data", "info", "status", "detail", "details",
}


# ===========================================================================
# 1. Rotas montadas + o que cada uma FAZ
# ===========================================================================
def dump_routes(prefix):
    """Rotas montadas sob <prefix>, com nome da funcao e summary/docstring."""
    code = (
        "import inspect, json\n"
        "from main_production import app\n"
        "out=[]\n"
        "for r in app.routes:\n"
        "  p=getattr(r,'path','')\n"
        f"  if '{prefix}' not in p: continue\n"
        "  ep=getattr(r,'endpoint',None)\n"
        "  doc=''\n"
        "  try:\n"
        "    doc=(inspect.getdoc(ep) or '').strip().split('\\n')[0] if ep else ''\n"
        "  except Exception: pass\n"
        "  out.append({'path':p,'methods':sorted(getattr(r,'methods',[]) or []),\n"
        "              'name':getattr(r,'name','') or '',\n"
        "              'summary':(getattr(r,'summary','') or ''),'doc':doc})\n"
        "print('<<J>>'+json.dumps(out)+'<<J>>')\n"
    )
    r = subprocess.run(
        ["docker", "exec", "-e", "PYTHONPATH=/app", CONTAINER, "python3", "-c", code],
        capture_output=True, text=True, timeout=180,
    )
    m = re.search(r"<<J>>(.*?)<<J>>", r.stdout, re.S)
    if not m:
        sys.stderr.write("ERRO no dump de rotas:\n" + r.stdout[-500:] + r.stderr[-500:])
        sys.exit(1)
    return json.loads(m.group(1))


def descricao(rt):
    """Uma linha dizendo o que a rota faz (summary > docstring > nome da funcao)."""
    for k in ("summary", "doc"):
        v = (rt.get(k) or "").strip()
        if v:
            return v[:96]
    return (rt.get("name") or "").replace("_", " ")[:96]


# ===========================================================================
# 2. Superficie: indice token -> arquivos (nao blob)
# ===========================================================================
def build_index(surface="all"):
    """{token: {arquivos}} da superficie escolhida.

    A v1 concatenava tudo num blob e testava `key in corpus` — substring global, que dava
    coberto para qualquer palavra que existisse em qualquer canto. Aqui guardamos QUEM cita
    cada token, para exigir CO-OCORRENCIA no mesmo arquivo (ver `cobertura`).
    """
    dirs = SURFACE_SETS.get(surface, SURFACE_SETS["all"])
    excl = _EXCLUDE_DIRS.get(surface, [])
    idx: dict[str, set] = {}
    for d in dirs:
        if not os.path.exists(d):
            continue
        # -H obrigatorio: sem ele o grep OMITE o nome quando o alvo e UM arquivo (o caso do
        # redesign_data_controller.py). A linha sai "732:token" em vez de "arq:732:token", o
        # split(':',2) devolve 2 campos e o parser abaixo descartava TUDO em silencio — 18.483
        # tokens daquele arquivo ficaram fora do indice, inflando o balde de orfaos.
        cmd = ["grep", "-rnoIEH", "[A-Za-z0-9/._-]{3,}", d]
        if os.path.isdir(d):
            cmd += ["--include=*.tsx", "--include=*.ts", "--include=*.py"]
            cmd += [f"--exclude-dir={x}" for x in excl]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=180).stdout
        except Exception:
            continue
        for linha in out.splitlines():
            # formato: caminho:linha:token
            partes = linha.split(":", 2)
            if len(partes) < 3:
                continue
            arq, tok = partes[0], partes[2]
            # COMENTARIO NAO E COBERTURA. Um builder que escreve "# de fora: /docs/orcamento/pdf
            # exige lista" punha o token 'orcamento' no indice e a rota aparecia COBERTA — o
            # medidor passava a bajular quem documentava o que NAO ligou. Medido 10/08/2026:
            # dizia 79 rotas fechadas quando eram 43. Documentar exclusao e o certo; o
            # instrumento e que nao pode contar isso como tela.
            if arq.endswith(".py") and _linha_e_comentario(arq, partes[1]):
                continue
            for pedaco in tok.strip("/").split("/"):
                if len(pedaco) >= 3:
                    idx.setdefault(pedaco, set()).add(arq)
    return idx


_CACHE_COMENT: dict = {}


def _linha_e_comentario(arq, num) -> bool:
    """True se a linha `num` de `arq` (1-based) e comentario ou esta dentro de docstring.

    Usa `tokenize`, nao regex: '#' dentro de string nao e comentario, e docstring de varias
    linhas precisa do bloco inteiro. Cacheia por arquivo — a checagem roda por TOKEN.
    """
    linhas = _CACHE_COMENT.get(arq)
    if linhas is None:
        linhas = set()
        try:
            import io
            import tokenize as _tk
            with open(arq, "rb") as fh:
                for t in _tk.tokenize(io.BytesIO(fh.read()).readline):
                    if t.type == _tk.COMMENT:
                        linhas.add(t.start[0])
                    elif t.type == _tk.STRING and t.start[0] != t.end[0]:
                        # string multi-linha: docstring/bloco. So conta como comentario quando
                        # NAO ha codigo antes dela na linha (senao seria SQL de verdade).
                        if not t.line[: t.start[1]].strip():
                            linhas.update(range(t.start[0], t.end[0] + 1))
        except Exception:  # noqa: BLE001 — arquivo ilegivel nao pode derrubar a medicao
            linhas = set()
        _CACHE_COMENT[arq] = linhas
    try:
        return int(num) in linhas
    except (TypeError, ValueError):
        return False


def segmentos(path):
    """Segmentos literais que IDENTIFICAM o recurso (sem api/v1/params/genericos)."""
    segs = [
        s for s in path.split("/")
        if s and not s.startswith("{") and s not in ("api", "v1") and ":" not in s
    ]
    return [s for s in segs if s.lower() not in _GENERICOS and len(s) >= 3]


def cobertura(path, idx):
    """(coberto?, arquivos, motivo). Exige CO-OCORRENCIA dos segmentos mais RAROS.

    Duas decisoes que a v1 nao tinha:

    1. Co-ocorrencia no MESMO arquivo, em vez de substring global. `key in corpus` dava
       coberto para qualquer palavra existente em qualquer canto do front.
    2. Os dois segmentos MAIS RAROS, nao os dois ultimos. Raridade e o que discrimina:
       `employee`, `hr` e `status` aparecem em centenas de arquivos e nao provam nada;
       `vacations` e `balance` provam. Pegar "os dois ultimos" escolheria
       `employee`+`balance` em /hr/vacations/employee/{id}/balance e perderia o par bom.

    Segmento algum citado no front => orfa, e o motivo nomeia qual faltou.
    """
    segs = segmentos(path)
    if not segs:
        return False, [], "sem segmento identificador"

    ausentes = [s for s in segs if not idx.get(s)]
    if ausentes:
        return False, [], f"segmento nao citado no front: {','.join(sorted(set(ausentes)))}"

    # mais raro = menos arquivos citam = mais poder discriminante
    ordenados = sorted(segs, key=lambda s: (len(idx[s]), s))
    chave = ordenados[:2] if len(ordenados) >= 2 else ordenados[:1]
    comuns = set.intersection(*(idx[s] for s in chave))
    if comuns:
        forca = (
            f"co-ocorrencia {'+'.join(chave)}"
            if len(chave) >= 2
            else f"segmento unico '{chave[0]}' (prova fraca)"
        )
        return True, sorted(comuns)[:3], forca
    return False, [], f"{'+'.join(chave)} citados, mas NUNCA no mesmo arquivo"


# ===========================================================================
# 3. Tabelas que os builders do redesign leem por SQL direto
# ===========================================================================
_TAB = re.compile(r"\b(?:FROM|JOIN)\s+([a-z_][a-z0-9_]{3,})", re.I)


def tabelas_dos_builders():
    """{tabela} lida por SQL direto nos builders do redesign.

    O redesign monta tela lendo o banco, sem chamar rota. Sem isto, todo GET vira 'orfao'
    mesmo quando a tela mostra o dado — foi a maior fonte de ruido da v1 (130 GETs).
    """
    tabs: set[str] = set()
    if not os.path.isdir(_BUILDERS_DIR):
        return tabs
    try:
        out = subprocess.run(
            ["grep", "-rhoiE", r"(FROM|JOIN)[[:space:]]+[a-z_][a-z0-9_]{3,}", _BUILDERS_DIR],
            capture_output=True, text=True, timeout=60,
        ).stdout
    except Exception:
        return tabs
    for m in _TAB.finditer(out):
        tabs.add(m.group(1).lower())
    return tabs


def provavel_falso_orfao(path, methods, tabelas):
    """GET cujo recurso casa com tabela que o builder le direto -> a tela mostra o dado."""
    if "GET" not in methods:
        return None
    for s in segmentos(path):
        alvo = s.lower().replace("-", "_")
        for t in tabelas:
            if alvo == t or alvo in t or t.endswith(alvo):
                return t
    return None


# ===========================================================================
# 4. Sonda viva (opcional)
# ===========================================================================
def curl(path, token):
    if "{" in path:
        return "(tem param — pular curl)"
    try:
        r = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "15",
             "http://localhost:8080" + path, "-H", f"Authorization: Bearer {token}"],
            capture_output=True, text=True, timeout=20,
        )
        return r.stdout.strip()
    except Exception:
        return "ERR"


# ===========================================================================
# self-check — valida a logica de pareamento sem docker e sem banco
# ===========================================================================
def _self_check():
    # `hr` e `employee` sao conectores: aparecem em MUITOS arquivos, nao discriminam.
    muitos = {f"f{i}.ts" for i in range(50)}
    idx = {
        "hr": muitos, "employee": muitos, "sst": muitos,
        "contracts": {"a.ts"}, "document": {"b.ts"},   # raros, mas em arquivos DIFERENTES
        "vacations": {"c.ts"}, "balance": {"c.ts"},    # raros e no MESMO arquivo
        "ppp": {"sst.ts"}, "prontuario": {"sst.ts"},
    }
    ok, _, motivo = cobertura("/api/v1/x/hr/contracts/{id}/document", idx)
    assert not ok, "v1 dava coberto por substring; v2 exige mesmo arquivo"
    assert "NUNCA no mesmo arquivo" in motivo, motivo

    # os dois RAROS sao vacations+balance; 'employee' (conector) nao pode roubar o par
    ok, arqs, motivo = cobertura("/api/v1/x/hr/vacations/employee/{id}/balance", idx)
    assert ok and arqs == ["c.ts"], (ok, arqs, motivo)
    assert "vacations" in motivo and "balance" in motivo, motivo

    # ancora de 3 chars: a v1 dava orfao automatico (guard de min-4). Agora conta.
    ok, _, _ = cobertura("/api/v1/x/sst/ppp/{employee_id}/prontuario", idx)
    assert ok, "ppp+prontuario no mesmo arquivo tem de contar como coberto"

    # segmento que o front nunca cita => orfa, com o nome do segmento no motivo
    ok, _, motivo = cobertura("/api/v1/x/hr/rescisao/{id}/trct", idx)
    assert not ok and "rescisao" in motivo, motivo

    # genericos nao provam nada; 'hr'/'x' sao curtos demais para discriminar. Uma rota
    # so de genericos+conectores fica SEM segmento identificador -> a ferramenta declara
    # que nao consegue julgar, em vez de chutar coberto ou orfao.
    assert segmentos("/api/v1/x/hr/status/list") == [], segmentos("/api/v1/x/hr/status/list")
    ok, _, motivo = cobertura("/api/v1/x/hr/status/list", idx)
    assert not ok and motivo == "sem segmento identificador", motivo

    assert MONEY.search("/dp/payroll/pay-batch"), "pay-batch tem de levar a flag de dinheiro"

    # siglas de governo so valem como SEGMENTO: "marcar-toDAS" nao e DAS do Simples
    assert not GOV.search("/comunicacao/notificacoes/marcar-todas"), "das dentro de palavra"
    assert not GOV.search("/operacional/medidas-administrativas/templates"), "das em medidas"
    assert GOV.search("/financial/fiscal/das/calcular"), "DAS como segmento tem de contar"
    assert GOV.search("/fiscal/nfse-multi/emitir"), "nfse tem de contar"

    tab = {"gp_clock_punches", "hr_payslips"}
    assert provavel_falso_orfao("/x/hr/payslips", ["GET"], tab) == "hr_payslips"
    assert provavel_falso_orfao("/x/hr/payslips", ["POST"], tab) is None

    print("self-check OK — 15 asserts")


# ===========================================================================
def main():
    if "--self-check" in sys.argv:
        _self_check()
        return
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    prefix = sys.argv[1]
    do_curl = "--curl" in sys.argv
    token = sys.argv[sys.argv.index("--token") + 1] if "--token" in sys.argv else None
    surface = sys.argv[sys.argv.index("--surface") + 1] if "--surface" in sys.argv else "all"
    if surface not in SURFACE_SETS:
        sys.stderr.write(f"--surface invalido: {surface} (use all|redesign|classic)\n")
        sys.exit(1)

    routes = dump_routes(prefix)
    idx = build_index(surface)
    tabelas = tabelas_dos_builders() if surface in ("redesign", "all") else set()

    exposto, orfao = [], []
    for rt in routes:
        p, methods = rt["path"], rt["methods"]
        ok, arqs, motivo = cobertura(p, idx)
        rt.update(
            exposed=ok, arquivos=arqs, motivo=motivo,
            gerador=bool(GEN.search(p)), money=bool(MONEY.search(p)), gov=bool(GOV.search(p)),
            falso_orfao=None if ok else provavel_falso_orfao(p, methods, tabelas),
        )
        if do_curl and "GET" in methods:
            rt["http"] = curl(p, token)
        (exposto if ok else orfao).append(rt)

    ger_orfao = [r for r in orfao if r["gerador"] and not r["falso_orfao"]]
    prov_falso = [r for r in orfao if r["falso_orfao"]]
    reais = [r for r in orfao if not r["falso_orfao"]]
    escrita = [r for r in reais if {"POST", "PUT", "DELETE", "PATCH"} & set(r["methods"])]

    _sfx = {"all": "classico+redesign", "redesign": "SO redesign (gap p/ matar o classico)",
            "classic": "SO classico"}[surface]
    print(f"=== BACKEND RECON v2 — prefixo '{prefix}' · superficie: {_sfx} ===")
    print(f"rotas montadas: {len(routes)} · EXPOSTAS: {len(exposto)} · ORFAS: {len(orfao)}")
    print(f"  das orfas: {len(prov_falso)} provaveis FALSO-ORFAO (builder le a tabela direto)")
    print(f"             {len(reais)} candidatas reais — destas, {len(escrita)} sao de ESCRITA")
    print(f"GERADORES DE DOCUMENTO orfaos: {len(ger_orfao)}")
    print()

    print("### 🔴 GERADORES ORFAOS (documento codado, sem superficie) — prioridade")
    for r in sorted(ger_orfao, key=lambda x: x["path"]):
        flag = ("💰" if r["money"] else "") + ("🏛️" if r["gov"] else "")
        print(f"  {','.join(r['methods']):8} {r['path']} {flag}")
        print(f"           → {descricao(r)}")
        print(f"           motivo: {r['motivo']}")
    print()

    print("### 🟠 ORFAS DE ESCRITA (acao que o front nao alcanca) — fila de trabalho")
    for r in sorted(escrita, key=lambda x: x["path"]):
        if r["gerador"]:
            continue
        flag = ("💰" if r["money"] else "") + ("🏛️" if r["gov"] else "")
        h = (" http=" + r.get("http", "")) if do_curl and "http" in r else ""
        print(f"  {','.join(r['methods']):8} {r['path']} {flag}{h}")
        print(f"           → {descricao(r)}")
    print()

    print("### ⚪ ORFAS DE LEITURA (candidatas reais, sem escrita)")
    for r in sorted(reais, key=lambda x: x["path"]):
        if r["gerador"] or r in escrita:
            continue
        print(f"  {','.join(r['methods']):8} {r['path']}  → {descricao(r)}")
    print()

    print(f"### 🔵 PROVAVEIS FALSO-ORFAO ({len(prov_falso)}) — builder le a tabela direto")
    for r in sorted(prov_falso, key=lambda x: x["path"]):
        print(f"  {','.join(r['methods']):8} {r['path']}  (tabela: {r['falso_orfao']})")
    print()

    # Sem corte silencioso: a lista de EXPOSTAS e longa, mas truncar sem avisar faria o
    # relatorio parecer completo quando nao esta (principio da skill: "no silent caps").
    _LIM = int(sys.argv[sys.argv.index("--limite-expostas") + 1]) if "--limite-expostas" in sys.argv else 0
    mostrar = exposto if _LIM <= 0 else sorted(exposto, key=lambda x: x["path"])[:_LIM]
    corte = "" if _LIM <= 0 else f" — MOSTRANDO {len(mostrar)} de {len(exposto)} (--limite-expostas)"
    print(f"### ✅ EXPOSTAS ({len(exposto)}) — com o arquivo que prova{corte}")
    for r in sorted(mostrar, key=lambda x: x["path"]):
        arq = (r["arquivos"][0] if r["arquivos"] else "").replace(HOST_ROOT + "/", "")
        print(f"  {','.join(r['methods']):8} {r['path']}")
        print(f"           → {descricao(r)}  [{r['motivo']}] {arq}")


if __name__ == "__main__":
    main()
