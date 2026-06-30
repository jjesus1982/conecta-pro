"""GEDEON — Robô do GED do Sólides (documentos ASSINADOS), CLASSIFICAÇÃO POR CONTEÚDO.

Roda no HOST. Playwright SÓ para logar (Pyetra) e capturar o token+headers da API REST
do GED (apis.tangerino.com.br/ged/api/v1); daí fala direto com a API (robusto).

LIÇÃO-CHAVE (2026-06-29): o recibo mensal de VT/VR é "RECIBO DE VALE TRANSPORTE E REFEIÇÃO"
mas é nomeado SÓ pelo funcionário ("ANTONIO CARLOS VIEIRA.pdf"), e existe em VÁRIOS formatos
de nome (DECLARAÇÃO DE RECEBIMENTO DE CARTÃO VALE, DESLOCAMENTO VALE TRANSPORTE, etc.). Por isso
NÃO dá pra classificar pelo NOME — baixa os candidatos e lê o CONTEÚDO do PDF (fitz no host).

Candidatos = (a) docs nomeados só com nome de pessoa (o recibo mensal) recentes; (b) docs com
palavra-chave de VT/VR/férias/13º no nome. Para cada dono pega o mais recente, lê o texto e
classifica. Dedup por dono+tipo (mais recente). Salva em uploads/solides_ged/ + manifesto."""

import datetime
import json
import re
import sys
import unicodedata

import fitz  # PyMuPDF (host tem)
import httpx
from playwright.sync_api import sync_playwright

DEST = "/opt/conecta-pro/uploads/solides_ged"
API = "https://apis.tangerino.com.br/ged/api/v1/documents/parent/"
LOGIN = "https://app.tangerino.com.br/Tangerino/pages/LoginPage"
GED_PAGE = "https://app.tangerino.com.br/Tangerino/pages/GEDSignatures?funcionalidade=131"
HOP = {"host", "connection", "content-length", "accept-encoding"}

# palavras que indicam um TIPO no nome (logo, NÃO é o recibo "NOME.pdf")
TIPO_KW = re.compile(
    r"folhaponto|folha de ponto|acordo|termo|ficha|declara|descri|regulamento|autoriz|"
    r"autodeclar|formulario|contrato|comunica|aviso|advert|suspens|\bepi\b|vedacao|"
    r"atualiz|cargo|norma|exame|aso|admiss|rescis",
    re.I,
)
# palavras-chave de VT/VR no nome (candidato explícito, qualquer data)
VALE_KW = re.compile(r"vale|transporte|aliment|refei|deslocamento|cart[ãa]o|\bvt\b|\bvr\b", re.I)
FERIAS_KW = re.compile(r"f[ée]rias", re.I)
DECIMO_KW = re.compile(r"d[ée]cimo|13[ºo]?\s*sal", re.I)


def _u(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return s.upper()


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def creds() -> dict:
    e = {}
    for l in open("/opt/conecta-pro/credentials/solides_web.env"):
        if "=" in l and not l.startswith("#"):
            k, v = l.strip().split("=", 1)
            e[k] = v
    return e


def eh_nome_pessoa(s: str) -> bool:
    s = (s or "").strip()
    if not s or re.search(r"\d", s) or TIPO_KW.search(s):
        return False
    toks = s.split()
    return 2 <= len(toks) <= 6 and all(re.match(r"^[A-Za-zÀ-ÿ.'-]+$", t) for t in toks)


def dono_do_doc(d: dict) -> str | None:
    """Extrai o funcionário do documento: nome puro do doc, ou parte após '_', ou parent.name."""
    nome = d.get("name", "")
    base = re.sub(r"\.pdf$", "", nome, flags=re.I)
    bare = re.sub(r"\s*[-–]\s*\d.*$", "", base)  # tira " - 26-04-2026 ate ..."
    bare = re.sub(r"\s*\(\d+\)\s*$", "", bare).strip()
    if eh_nome_pessoa(bare):
        return bare
    if "_" in base:  # "RECIBO ..._FERNANDO MIGUEL"
        tail = re.sub(r"\.pdf$", "", base.split("_")[-1], flags=re.I).strip()
        if eh_nome_pessoa(tail):
            return tail
    parent = (d.get("parent") or {}).get("name", "")
    if eh_nome_pessoa(parent):
        return parent
    return None


def classificar_conteudo(txt: str):
    """Classifica pelo TEXTO do PDF. CUIDADO: o contracheque/demonstrativo tem 'VALE TRANSPORTE'
    como RUBRICA — NÃO é recibo. Exigir o TÍTULO do recibo/declaração, não a palavra solta."""
    t = _u(txt)
    # contracheque/demonstrativo/folha → descarta (tem 'vale transporte' como rubrica)
    eh_contracheque = (
        ("VENCIMENTOS" in t and "DESCONTOS" in t)
        or "CRED. TRAB" in t
        or "DESC. EMP" in t
        or "DEMONSTRATIVO DE PAGAMENTO" in t
        or "RECIBO DE PAGAMENTO DE SALARIO" in t
        or "LIQUIDO A RECEBER" in t
    )
    # termo de adesão/atualização do VT (cadastro, one-time) NÃO é o recibo mensal do kit
    eh_termo_cadastro = "TERMO DE SOLICITACAO" in t or "ATUALIZACAO DO VALE" in t
    eh_recibo_vtvr = (
        "RECIBO DE VALE" in t
        or "RECEBIMENTO DE CARTAO VALE" in t
        or ("DESLOCAMENTO" in t and "VALE" in t)
        or ("RECEBI DE" in t and ("VALE TRANSPORTE" in t or "VALE REFEI" in t or "VALE ALIMENT" in t))
    )
    if eh_recibo_vtvr and not eh_contracheque and not eh_termo_cadastro:
        return "vale_vt_vr", "Recibo Vale Transporte e Refeição Assinado"
    if not eh_contracheque and "FERIAS" in t and ("RECIBO" in t or "GOZO" in t):
        return "ferias", "Recibo de Férias Assinado"
    if "RECIBO" in t and ("DECIMO TERCEIRO" in t or "13 SALARIO" in t or "13O SALARIO" in t):
        return "decimo_terceiro", "Recibo 13º Salário Assinado"
    return None, None


def nome_do_conteudo(txt: str) -> str | None:
    """Lê o 'NOME:' do recibo (o signatário) — mais confiável que o nome do arquivo."""
    m = re.search(r"NOME\s*:?\s*\n?\s*([A-Za-zÀ-ÿ' .]{5,60})", txt)
    if m:
        cand = m.group(1).strip()
        if eh_nome_pessoa(cand):
            return cand
    return None


def ref_do_recibo(txt: str) -> str | None:
    """Mês de referência do recibo de VT/VR (ex.: 'ref.05/2026' -> '05.2026'). O recibo é
    pago adiantado, então o kit do mês trabalhado leva a ref DAQUELE mês (não a mais recente)."""
    m = re.search(r"ref\.?\s*(\d{2})/(\d{4})", txt, re.I)
    if m:
        return f"{m.group(1)}.{m.group(2)}"
    # fallback: período "17/05/2026 a 16/06/2026" -> usa o mês de início (05.2026)
    m = re.search(r"per[íi]odo de\s*\d{2}/(\d{2})/(\d{4})", txt, re.I)
    if m:
        return f"{m.group(1)}.{m.group(2)}"
    return None


def capturar_sessao_api():
    e = creds()
    cap = {"h": None, "uid": "2061675"}
    with sync_playwright() as b0:
        b = b0.chromium.launch(headless=True)
        pg = b.new_context().new_page()

        def on_req(r):
            if "ged/api/v1/documents/parent" in r.url:
                if not cap["h"]:
                    cap["h"] = dict(r.headers)
                m = re.search(r"tangerinoUserId=(\d+)", r.url)
                if m:
                    cap["uid"] = m.group(1)

        pg.on("request", on_req)
        pg.goto(LOGIN, wait_until="domcontentloaded", timeout=30000)
        pg.wait_for_timeout(2500)
        pg.fill("input[name=login]", e["PYETRA_USER"])
        pg.fill("input[name=password]", e["PYETRA_SOLIDES_PASS"])
        pg.click("input[name=btnLogin]")
        pg.wait_for_timeout(8000)
        if "LoginPage" in pg.url:
            raise SystemExit("login falhou")
        pg.goto(GED_PAGE, wait_until="domcontentloaded", timeout=40000)
        pg.wait_for_timeout(9000)
        b.close()
    if not cap["h"]:
        raise SystemExit("não capturou o token da API do GED")
    return {k: v for k, v in cap["h"].items() if k.lower() not in HOP}, cap["uid"]


def listar_todos_assinados(cli, uid) -> list[dict]:
    todos = []
    for page in range(1, 60):
        p = {
            "pageNumber": page,
            "pageSize": 100,
            "signed": "true",
            "role": "ADMINISTRATOR",
            "tangerinoUserId": uid,
            "sortBy": "createdAt",
            "sortDirection": "DESC",
        }
        lst = cli.get(API, params=p).json().get("item", {}).get("list", [])
        if not lst:
            break
        todos += lst
        if len(lst) < 100:
            break
    return todos


def baixar(dias: int = 150, competencia: str | None = None) -> list[dict]:
    import os

    os.makedirs(DEST, exist_ok=True)
    headers, uid = capturar_sessao_api()
    cli = httpx.Client(timeout=60, headers=headers)
    todos = listar_todos_assinados(cli, uid)
    # Janela dos "NOME.pdf": se há competência alvo, foca no mês dela (o recibo de VT/VR é
    # criado ~dia 17 do mês da ref) até o dia 15 do mês seguinte — assim o recibo do mês
    # SEGUINTE (adiantado) fica de fora. Sem competência, usa os últimos `dias`.
    if competencia:
        cm, ca = int(competencia.split(".")[0]), int(competencia.split(".")[1])
        jan_ini = f"{ca}-{cm:02d}-01"
        a2, m2 = (ca, cm + 1) if cm < 12 else (ca + 1, 1)
        jan_fim = f"{a2}-{m2:02d}-15"
    else:
        jan_ini = (datetime.date.today() - datetime.timedelta(days=dias)).isoformat()
        jan_fim = "9999-99-99"

    # candidatos por DONO: recibo "NOME.pdf" na janela OU doc com palavra-chave de vale/férias/13º
    cand: dict = {}
    pendentes: list = []  # docs aguardando assinatura (status != COMPLETED) → pendentes.json
    for d in todos:
        st = (d.get("status") or {}).get("value")
        if st != "COMPLETED":
            # ainda não assinado: registra como pendência (só os que parecem recibo de pessoa)
            dono_p = dono_do_doc(d)
            nome_p = d.get("name", "")
            kw_p = VALE_KW.search(nome_p) or FERIAS_KW.search(nome_p) or DECIMO_KW.search(nome_p)
            if dono_p and (eh_nome_pessoa(re.sub(r"\.pdf$", "", nome_p, flags=re.I)) or kw_p):
                pendentes.append(
                    {"funcionario": dono_p, "documento": nome_p, "status": st or "PENDENTE",
                     "created": (d.get("createdAt") or "")[:10]}
                )
            continue
        dono = dono_do_doc(d)
        if not dono:
            continue
        nome = d.get("name", "")
        created = (d.get("createdAt") or "")[:10]
        bare_pessoa = eh_nome_pessoa(re.sub(r"\.pdf$", "", nome, flags=re.I))
        kw = VALE_KW.search(nome) or FERIAS_KW.search(nome) or DECIMO_KW.search(nome)
        if not ((bare_pessoa and jan_ini <= created <= jan_fim) or kw):
            continue
        cand.setdefault(_u(dono), []).append((created, d, dono))

    print(
        f"{len(todos)} assinados | {len(cand)} donos candidatos"
        + (f" | VT/VR ref alvo={competencia}" if competencia else ""),
        file=sys.stderr,
    )
    melhor: dict = {}  # (dono, tipo) -> {created, bytes, label, dono}
    baixados_bytes = {}
    for chave, ds in cand.items():
        ds.sort(key=lambda x: x[0], reverse=True)
        tem_vtvr = False  # já achei o VT/VR certo (ref alvo) desse dono?
        for created, d, dono in ds[:8]:  # olha até 8 do dono (o da ref pode não ser o mais novo)
            url = d.get("signedUrl") or d.get("fileUrl")
            if not url:
                continue
            try:
                content = httpx.get(url, timeout=90).content
                if content[:4] != b"%PDF":
                    continue
                txt = "\n".join(p.get_text() for p in fitz.open(stream=content, filetype="pdf"))
            except Exception:
                continue
            tipo, label = classificar_conteudo(txt)
            if not tipo:
                continue
            if tipo == "vale_vt_vr":
                if tem_vtvr:
                    continue
                ref = ref_do_recibo(txt)
                # o recibo de VT/VR é pago adiantado → no kit do mês trabalhado entra o recibo
                # MENSAL com ref DAQUELE mês (competencia). Sem ref (termo/declaração avulsa) ou
                # ref de outro mês → não serve p/ este kit; segue procurando.
                if competencia and ref != competencia:
                    continue
                tem_vtvr = True
            dono_real = nome_do_conteudo(txt) or dono  # prioriza o NOME: do recibo
            k = (_u(dono_real), tipo)
            if k not in melhor or created > melhor[k]["created"]:
                fn = f"{tipo}__{slug(dono_real)}.pdf"
                melhor[k] = {"funcionario": dono_real, "tipo": tipo, "label": label, "created": created, "arquivo": fn}
                baixados_bytes[fn] = content

    manifesto = []
    for k, m in melhor.items():
        open(f"{DEST}/{m['arquivo']}", "wb").write(baixados_bytes[m["arquivo"]])
        manifesto.append({**m, "bytes": len(baixados_bytes[m["arquivo"]])})
    json.dump(manifesto, open(f"{DEST}/manifesto.json", "w"), ensure_ascii=False, indent=2)
    # dedup pendentes por (funcionário, documento) e grava p/ o painel de assinaturas
    _seen = set()
    pend_uniq = []
    for p in pendentes:
        k = (_u(p["funcionario"]), p["documento"])
        if k not in _seen:
            _seen.add(k)
            pend_uniq.append(p)
    json.dump(pend_uniq, open(f"{DEST}/pendentes.json", "w"), ensure_ascii=False, indent=2)
    print(f"{len(pend_uniq)} docs aguardando assinatura → pendentes.json", file=sys.stderr)
    return manifesto


if __name__ == "__main__":
    # arg1 = competência MM.YYYY (filtra o VT/VR pela ref daquele mês); arg2 opcional = dias
    competencia = None
    dias = 150
    for a in sys.argv[1:]:
        if re.match(r"^\d{2}\.\d{4}$", a):
            competencia = a
        elif a.isdigit():
            dias = int(a)
    m = baixar(dias=dias, competencia=competencia)
    from collections import Counter

    alvo = f" | VT/VR ref={competencia}" if competencia else ""
    print(f"baixados {len(m)} documentos assinados (conteúdo, últimos {dias}d{alvo}):")
    for tipo, n in Counter(x["tipo"] for x in m).most_common():
        print(f"  {tipo}: {n}")
