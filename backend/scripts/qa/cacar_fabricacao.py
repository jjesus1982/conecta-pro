#!/usr/bin/env python3
"""Caça código que INVENTA valor quando a fonte falha.

Todos os defeitos graves de 11-12/08/2026 tinham a mesma forma: uma decisão de "o que fazer
quando não sei", tomada para o lado de afirmar. Nenhum era erro de lógica.

  cnd_sync_task      sem data do órgão -> `utcnow() + timedelta(180)`
                     Portal fora do ar virava certidão válida por seis meses. Quatro
                     nasceram assim, incluindo a CRF-FGTS vencida "renovada".

  sefaz_am_client    `except: ...` devolvendo veredito
                     Dizia `regular` para QUALQUER CNPJ, inclusive um inexistente.

  fiscal.py          `WHERE data_emissao >= (SELECT max(data_emissao) FROM ...) - interval`
                     Janela ancorada na última nota do ARQUIVO: o "faturamento 12m"
                     congelava enquanto a empresa faturava.

  proativo/tasks     `"\\n- ".join(titulos[:20])`
                     Digest cortava em 20 e não dizia. Item sumia; quem lê conclui que a
                     lista é a lista.

As quatro assinaturas são greppáveis. Este caçador as procura no código todo.

É ESTÁTICO e propenso a falso positivo — cada achado é PISTA, não veredito. O que ele
garante é que nenhuma delas passe despercebida.

Uso:
    python3 scripts/qa/cacar_fabricacao.py [caminho]
    python3 scripts/qa/cacar_fabricacao.py --self-check
"""
from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path

RAIZ = Path(os.getenv("QA_RAIZ", "/app"))

#: nomes que denunciam que o valor calculado É uma afirmação sobre o mundo
_PALAVRAS_VALIDADE = ("validade", "valid", "venc", "expiry", "expira", "prazo", "vigencia")

#: (a) data inventada: hoje + N dias virando validade/vencimento
_RE_DATA_INVENTADA = re.compile(
    r"(?P<alvo>\w*(?:" + "|".join(_PALAVRAS_VALIDADE) + r")\w*)\s*=\s*[^\n]*"
    r"(?:utcnow\(\)|now\(\)|today\(\))\s*\+\s*timedelta", re.I)

#: (c) janela ancorada no max() da própria tabela em vez de na data de hoje.
#: `[\s"\']*` entre os pedaços porque SQL nesta casa vive quebrado em várias strings
#: concatenadas — e o caso real (fiscal.py) era exatamente assim.
_SEP = r"[\s\"\']*"
_RE_ANCORA_MAX = re.compile(
    r">=" + _SEP + r"\(" + _SEP + r"SELECT\s+max\s*\([^)]*\)" + _SEP +
    r"FROM\b[^)]*\)" + _SEP + r"-" + _SEP + r"interval", re.I)

#: (d) corte de lista alimentando texto que alguém vai LER
_RE_CORTE_MUDO = re.compile(r"\[\s*:\s*(?P<n>\d{1,4})\s*\][^\n]*\.join\(|"
                            r"\.join\([^\n]*\[\s*:\s*(?P<n2>\d{1,4})\s*\]")

#: palavras que denunciam que o retorno do `except` é um VEREDITO, não um "não deu"
_CHAVES_DE_VEREDITO = ("situacao", "regular", "valid", "aprovad", "ok\":", "'ok'", "status\":",
                       "'status'", "negativa", "conforme", "sucesso", "success")

#: se o retorno contém alguma destas, ele está DIZENDO que não deu certo — é honesto
_PALAVRAS_HONESTAS = ("false", "erro", "error", "falha", "indispon", "desconhec", "sem_",
                      "nao_", "não ", "invalid", "inválid", "pendente", "aguardando",
                      "requer_manual", "recusad", "none", "vazio", "not_found", "timeout")

_AVISO_DE_CORTE = ("não listados", "nao listados", "restante", "a mais", "outros", "total",
                   "truncad", "demais", "+{", "len(")


def _linha(texto: str, pos: int) -> int:
    return texto[:pos].count("\n") + 1


def _except_que_afirma(texto: str, caminho: str) -> list[dict]:
    """(b) handler de exceção que RETORNA valor — engolir o erro e afirmar assim mesmo.

    AST porque regex não distingue `except: return None` (honesto) de
    `except: return {"situacao": "regular"}` (afirmação sem base).
    """
    try:
        arvore = ast.parse(texto)
    except SyntaxError:
        return []
    achados = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.ExceptHandler):
            continue
        for filho in ast.walk(no):
            if not isinstance(filho, ast.Return) or filho.value is None:
                continue
            v = filho.value
            # `return None` / `return []` / `return {}` / `return 0` são honestos: não afirmam.
            if isinstance(v, ast.Constant) and (v.value is None or v.value in (0, "", False)):
                continue
            if isinstance(v, (ast.List, ast.Tuple, ast.Set)) and not v.elts:
                continue
            if isinstance(v, ast.Dict) and not v.keys:
                continue
            # Só é fabricação quando o valor devolvido AFIRMA algo sobre o mundo. Um dict
            # com `{"erro": ...}` é honesto; `{"situacao": "regular"}` não é. Sem este filtro
            # o caçador acusa centenas de `except: return []`-com-conteúdo inofensivos.
            texto_ret = ast.unparse(v).lower()
            if not any(k in texto_ret for k in _CHAVES_DE_VEREDITO):
                continue
            # E só quando a afirmação é POSITIVA. `{'ok': False, 'erro': ...}` e
            # `{'status': 'indisponível'}` são o padrão HONESTO — reportam o fracasso, e
            # acusá-los ensina a ignorar o caçador. O filtro anterior olhava a chave e não
            # o valor: 234 pistas, quase todas dessas.
            if any(h in texto_ret for h in _PALAVRAS_HONESTAS):
                continue
            achados.append({
                "arquivo": caminho, "linha": filho.lineno, "tipo": "except-que-afirma",
                "trecho": ast.unparse(filho)[:90],
                "porque": "o erro foi engolido e ainda assim se devolveu um valor — "
                          "quem chama não distingue resposta de fracasso",
            })
    return achados


def achados_no_arquivo(caminho: Path, rotulo: str | None = None) -> list[dict]:
    try:
        texto = caminho.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    nome = rotulo or str(caminho)
    out: list[dict] = []

    for m in _RE_DATA_INVENTADA.finditer(texto):
        out.append({"arquivo": nome, "linha": _linha(texto, m.start()), "tipo": "data-inventada",
                    "trecho": m.group(0)[:90].replace("\n", " "),
                    "porque": f"'{m.group('alvo')}' é afirmação sobre o mundo e está sendo "
                              f"calculada a partir de hoje, não lida da fonte"})

    for m in _RE_ANCORA_MAX.finditer(texto):
        out.append({"arquivo": nome, "linha": _linha(texto, m.start()), "tipo": "janela-ancorada",
                    "trecho": m.group(0)[:90].replace("\n", " "),
                    "porque": "janela ancorada no max() da própria tabela: congela quando a "
                              "tabela para de crescer, e o rótulo continua dizendo '12 meses'"})

    for m in _RE_CORTE_MUDO.finditer(texto):
        n = m.group("n") or m.group("n2")
        # `"".join(c for c in nome ...)[:30]` é montagem de slug, não corte de lista para
        # leitura humana. Sem esta exclusão o caçador acusa 26 e a maioria é slug.
        if " for " in m.group(0):
            continue
        ini = texto.rfind("\n", 0, max(0, m.start() - 400))
        redor = texto[max(0, ini):m.end() + 400].lower()
        if any(a.lower() in redor for a in _AVISO_DE_CORTE):
            continue  # o corte se anuncia
        out.append({"arquivo": nome, "linha": _linha(texto, m.start()), "tipo": "corte-mudo",
                    "trecho": m.group(0)[:90].replace("\n", " "),
                    "porque": f"lista cortada em {n} e emendada em texto sem dizer que cortou "
                              f"— quem lê conclui que a lista é a lista"})

    out.extend(_except_que_afirma(texto, nome))
    return out


def varrer(raiz: Path) -> list[dict]:
    achados = []
    for p in sorted(raiz.rglob("*.py")):
        if any(x in p.parts for x in ("__pycache__", "venv", "node_modules", ".git")):
            continue
        rot = str(p.relative_to(raiz)) if str(p).startswith(str(raiz)) else str(p)
        achados.extend(achados_no_arquivo(p, rot))
    return achados


def _self_check() -> None:
    """As provas são os quatro casos REAIS. Caçador que não pega o próprio histórico não serve."""
    import tempfile

    bom = '''
import os
from datetime import datetime, timedelta

def valida(resultado):
    data_validade = resultado.get("data_validade")
    if data_validade is None:
        return {"status": "sem_validade"}
    return {"ok": True}

def honesto():
    try:
        return consultar()
    except Exception:
        return None

def corte_anunciado(titulos):
    corpo = "- " + "\\n- ".join(titulos[:20])
    if len(titulos) > 20:
        corpo += f"(+{len(titulos)-20} não listados)"
    return corpo
'''
    ruim = '''
from datetime import datetime, timedelta

def valida(resultado, tipo):
    data_validade = (datetime.utcnow() + timedelta(days=180)).date()
    return data_validade

def afirma():
    try:
        return consultar()
    except Exception:
        return {"situacao": "regular", "regular": True}

def corte_mudo(titulos):
    return "Itens:\\n- " + "\\n- ".join(titulos[:20])

SQL = ("SELECT sum(v) FROM nfse WHERE data_emissao >= "
       "(SELECT max(data_emissao) FROM nfse) - interval '12 months'")
'''
    with tempfile.TemporaryDirectory() as d:
        pb, pr = Path(d) / "bom.py", Path(d) / "ruim.py"
        pb.write_text(bom)
        pr.write_text(ruim)
        a_bom = achados_no_arquivo(pb, "bom.py")
        a_ruim = achados_no_arquivo(pr, "ruim.py")

    tipos = {a["tipo"] for a in a_ruim}
    for esperado in ("data-inventada", "except-que-afirma", "corte-mudo", "janela-ancorada"):
        assert esperado in tipos, f"não pegou {esperado}: {sorted(tipos)}"
    assert not a_bom, f"acusou código honesto: {[(x['tipo'], x['trecho']) for x in a_bom]}"
    print("self-check OK — pega as 4 assinaturas reais, 0 falso positivo no código honesto")


def main() -> int:
    alvo = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else RAIZ / "modules"
    achados = varrer(alvo)
    if not achados:
        print("nenhuma assinatura de fabricação encontrada")
        return 0
    por_tipo: dict[str, list[dict]] = {}
    for a in achados:
        por_tipo.setdefault(a["tipo"], []).append(a)
    print(f"{len(achados)} pista(s) em {alvo}:\n")
    for tipo in ("data-inventada", "janela-ancorada", "corte-mudo", "except-que-afirma"):
        itens = por_tipo.get(tipo, [])
        if not itens:
            continue
        print(f"── {tipo} ({len(itens)}) — {itens[0]['porque']}")
        for a in itens[:12]:
            print(f"   {a['arquivo']}:{a['linha']}  {a['trecho']}")
        if len(itens) > 12:
            print(f"   (+{len(itens) - 12} não listadas aqui)")
        print()
    return 1


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
        raise SystemExit(0)
    raise SystemExit(main())
