"""Conhecimento de domínio + playbooks por agente (Fase 5.4b).
Lê uploads/agent_knowledge/consultores/<agente>.md em runtime (ensina sem rebuild).
RAG-lite por overlap de keywords (molde juridico/conhecimento_service). Fail-open.
"""
from __future__ import annotations
import os, re
from pathlib import Path

_DIR = Path(os.getenv("CONSULTOR_KB_DIR", "/app/uploads/agent_knowledge/consultores"))
_CACHE: dict[str, tuple[float, list[tuple[str, str]]]] = {}
_STOP = {"de","a","o","que","e","do","da","em","um","para","com","nao","os","no","se","na","por",
         "mais","as","dos","como","mas","ao","das","seu","sua","ou","quando","muito","ja","tambem",
         "so","pelo","pela","ate","isso","entre","sem","mesmo","aos","seus","quem","nas","esse",
         "voce","essa","num","nem","suas","meu","qual","nos","lhe","este","dele","uma"}

def _tokens(txt: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9à-ÿ]{3,}", txt.lower()) if w not in _STOP}

def _secoes(agente: str) -> list[tuple[str, str]]:
    p = _DIR / f"{agente}.md"
    try:
        st = p.stat()
    except OSError:
        return []  # fail-open
    cached = _CACHE.get(agente)
    if cached and cached[0] == st.st_mtime:
        return cached[1]
    txt = p.read_text(encoding="utf-8")
    secoes: list[tuple[str, str]] = []
    cur_t, cur_b = None, []
    for line in txt.splitlines():
        if line.startswith("## "):
            if cur_t is not None:
                secoes.append((cur_t, "\n".join(cur_b).strip()))
            cur_t, cur_b = line[3:].strip(), []
        elif cur_t is not None:
            cur_b.append(line)
    if cur_t is not None:
        secoes.append((cur_t, "\n".join(cur_b).strip()))
    _CACHE[agente] = (st.st_mtime, secoes)
    return secoes

def contexto_para_prompt(agente: str, pergunta: str = "", *, max_secoes: int = 3) -> str:
    secoes = _secoes(agente)
    if not secoes:
        return ""
    q = _tokens(pergunta)
    if not q:
        escolhidas = secoes[:max_secoes]
    else:
        ranked = sorted(secoes, key=lambda s: len(_tokens(s[0] + " " + s[1]) & q), reverse=True)
        escolhidas = [s for s in ranked if _tokens(s[0] + " " + s[1]) & q][:max_secoes] or secoes[:1]
    corpo = "\n\n".join(f"### {t}\n{b}" for t, b in escolhidas if b)
    if not corpo:
        return ""
    return "\n\n[CONHECIMENTO DE DOMINIO - fatos reais; use-os, nao invente alem disto]\n" + corpo


if __name__ == "__main__":
    import shutil
    import tempfile

    tmpdir = tempfile.mkdtemp(prefix="kb_teste_5.4b_")
    os.environ["CONSULTOR_KB_DIR"] = tmpdir
    _DIR = Path(tmpdir)  # reatribui o global do módulo (bloco roda em escopo de módulo, não função)
    _CACHE.clear()

    AGENTE = "teste_agente"
    MD_CONTEUDO = (
        "## Conhecimento: CCT\n"
        "corpo com palavra piso do dissídio\n\n"
        "## Playbook: fechamento\n"
        "corpo do playbook de fechamento do mes\n\n"
        "## Outra\n"
        "corpo de outra secao qualquer\n"
    )

    try:
        md_path = Path(tmpdir) / f"{AGENTE}.md"
        md_path.write_text(MD_CONTEUDO, encoding="utf-8")

        # (a) keyword match: pergunta sobre "piso" deve trazer a seção CCT
        out_a = contexto_para_prompt(AGENTE, "qual o piso?")
        assert "[CONHECIMENTO DE DOMINIO" in out_a, out_a
        assert "Conhecimento: CCT" in out_a, out_a
        assert "piso" in out_a, out_a
        print("PASS (a) keyword match traz secao certa")

        # (b) agente inexistente -> "" fail-open, sem exceção
        out_b = contexto_para_prompt("agente_que_nao_existe_5_4b", "x")
        assert out_b == "", repr(out_b)
        print("PASS (b) fail-open agente inexistente")

        # (c) sem pergunta -> primeiras max_secoes (na ordem do arquivo)
        out_c = contexto_para_prompt(AGENTE, "", max_secoes=2)
        assert "Conhecimento: CCT" in out_c, out_c
        assert "Playbook: fechamento" in out_c, out_c
        assert "Outra" not in out_c, out_c
        print("PASS (c) sem pergunta retorna primeiras max_secoes")

        # (d) cache por mtime: 2 chamadas seguidas sem mudar mtime -> idempotente
        #     (confirma via contador de leituras: monkeypatch Path.read_text)
        leituras = {"n": 0}
        orig_read_text = Path.read_text

        def _contando_read_text(self, *a, **kw):
            if self == md_path:
                leituras["n"] += 1
            return orig_read_text(self, *a, **kw)

        Path.read_text = _contando_read_text
        try:
            _CACHE.clear()
            r1 = contexto_para_prompt(AGENTE, "piso")
            r2 = contexto_para_prompt(AGENTE, "piso")
            assert r1 == r2, "cache deveria devolver resultado idêntico"
            assert leituras["n"] == 1, f"esperava 1 leitura (cache hit na 2a), teve {leituras['n']}"
        finally:
            Path.read_text = orig_read_text
        print("PASS (d) cache por mtime evita releitura")

        # (e) .md vazio / sem secoes -> ""
        vazio_path = Path(tmpdir) / "vazio.md"
        vazio_path.write_text("", encoding="utf-8")
        out_e = contexto_para_prompt("vazio", "qualquer coisa")
        assert out_e == "", repr(out_e)
        print("PASS (e) md vazio/sem secoes retorna string vazia")

        print("TODOS PASS")
    finally:
        _CACHE.clear()
        shutil.rmtree(tmpdir, ignore_errors=True)
