"""SUITE-ORÁCULO da Fase 5.4b (conhecimento de domínio file-based + guarda
anti-burla) — a prova formal, executável e MUTAÇÃO-TESTADA de que:
  (a) `consultor_conhecimento_service.contexto_para_prompt` é fail-open, só
      injeta quando há conhecimento real, e NUNCA fabrica dado além do que
      está no .md; e
  (b) nenhum handler de ação registrado em `acoes/*.py` (as 6 tools onda_a/
      b/c da Fase 5.4) pode pular a primitiva `base.propor()` e chamar
      execução direta — a guarda estrutural (AST) que a discovery pediu.

Doutrina (molde da suite 5.4, test_oraculos_acoes_5_4.py): a fronteira provada
é o DADO/CÓDIGO real (saída do serviço vs. bytes do .md; símbolos REALMENTE
chamados/importados no corpo do handler via AST), nunca a alegação. Cada
inviolável = 1 oráculo, e cada oráculo tem que MORDER sob a mutação
correspondente — se não morde, o oráculo é fraco e é reforçado até morder.

Os 4 oráculos (spec Fase 5.4b, Task 4):
  1. fail-open — agente inexistente e CONSULTOR_KB_DIR vazio → "" sem exceção
     (nunca derruba o chat).
  2. injeção presente/ausente — com .md presente, a saída carrega o marcador
     "[CONHECIMENTO DE DOMINIO"; sem .md, "" — prova que o system_prompt só
     ganha o bloco quando há conhecimento real.
  3. nunca-fabricar — com um .md de valor conhecido, todo NÚMERO que aparece
     na saída de `contexto_para_prompt` já estava no .md (saída ⊆ .md); a
     saída nunca acrescenta afirmação numérica nova.
  4. anti-burla (AST) — varre `acoes/*.py` (exclui `base.py`, dono da
     primitiva `propor`), localiza via AST todo handler REGISTRADO por um
     `ToolDef(...)` (a mesma via pela qual o orquestrador liga tool→função) e
     garante que nenhum desses handlers CHAMA/IMPORTA um símbolo de EXECUÇÃO
     direta (`executar_lote`, `gerar_otp_lote`, `gerar_otp`, `enviar_pix`,
     `transmitir_evento_sst`, `transmitir_evento`, `pagar`, `emitir`). A
     única via de ação permitida é `propor(...)`/`base.propor`.

MUTAÇÃO-TESTE (2 — prova que a suite morde; molde 5.4):
  M1 — cria (no throwaway, dentro do próprio dir `acoes/`) um `onda_mut.py`
       com um handler REGISTRADO via ToolDef que chama `executar_lote(...)`
       direto (sem propor) → o oráculo 4 deve FALHAR apontando ESSE arquivo e
       ESSE handler (não um erro genérico).
  M2 — monkeypatch de `contexto_para_prompt` que concatena um número extra
       não presente no .md → o oráculo 3 deve FALHAR.
Se uma mutação NÃO derrubar o oráculo certo, o oráculo é fraco.

Bancada: throwaway `docker run --rm --memory=2g` (imagem conecta-pro-backend,
PYTHONPATH=/app, `python -m` ou `python arquivo.py`). NÃO precisa DB (nenhum
oráculo desta suite toca o banco — conhecimento é arquivo, anti-burla é AST
estático). NUNCA rodar contra backend vivo/green:8080. Toda escrita é em
diretório temporário (tempfile.mkdtemp) ou em `onda_mut.py` (removido no
finally) — 0 remanescentes; imprime PASS/FAIL por oráculo + resultado das 2
mutações; exit 0 só se os 4 oráculos PASS E as 2 mutações MORDEREM.
"""
from __future__ import annotations

import ast
import re
import shutil
import sys
import tempfile
import traceback
import uuid
from pathlib import Path

# ── Unidades sob prova ──
from modules.ai.conversation.services import consultor_conhecimento_service as kb
from modules.ai.conversation.services.orquestrador.acoes import base as _base_mod

ACOES_DIR = Path(_base_mod.__file__).resolve().parent

#: símbolos de EXECUÇÃO direta banidos no corpo de um handler de ação (a única
#: via permitida é propor()/base.propor).
PROIBIDOS = frozenset({
    "executar_lote", "gerar_otp_lote", "gerar_otp", "enviar_pix",
    "transmitir_evento_sst", "transmitir_evento", "pagar", "emitir",
})

_NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")


class OracleFail(AssertionError):
    pass


def _numeros(txt: str) -> set[str]:
    return set(_NUM_RE.findall(txt or ""))


# ───────────────────────── oráculo 4 — anti-burla (AST) ─────────────────────

def _handlers_registrados(tree: ast.Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    """Localiza, via AST, todo `ToolDef(..., handler=<fn>)` (ou 5º posicional —
    a assinatura real é `ToolDef(name, module, description, params_schema,
    handler, scope_kind=...)`) do arquivo, e resolve `<fn>` para a função
    module-level correspondente NESTE mesmo arquivo. É a MESMA via pela qual o
    tool_registry liga tool→handler — não é convenção de nome, é o fio real."""
    funcs = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    handler_names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        callee = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
        if callee != "ToolDef":
            continue
        hname = None
        for kw in node.keywords:
            if kw.arg == "handler" and isinstance(kw.value, ast.Name):
                hname = kw.value.id
        if hname is None and len(node.args) >= 5 and isinstance(node.args[4], ast.Name):
            hname = node.args[4].id
        if hname:
            handler_names.add(hname)
    return {n: funcs[n] for n in handler_names if n in funcs}


def _simbolos_chamados(fn_node: ast.AST) -> set[str]:
    """Nomes REALMENTE chamados/importados no corpo do handler (AST — não
    substring, p/ não confundir menção em COMENTÁRIO/docstring com chamada de
    código real; molde de `_code_symbols` da suite 5.4)."""
    names: set[str] = set()
    for node in ast.walk(fn_node):
        if isinstance(node, ast.Import):
            for a in node.names:
                names.add(a.asname or a.name.split(".")[-1])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                names.add(a.asname or a.name)
        elif isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                names.add(f.id)
            elif isinstance(f, ast.Attribute):
                names.add(f.attr)
    return names


def _scan_acoes_dir(acoes_dir: Path) -> tuple[list[tuple[str, str, str]], int]:
    """Varre `acoes/*.py` (exclui base.py — dono da primitiva `propor` — e
    __init__.py). Retorna (violações, total_handlers_escaneados). Violação =
    (arquivo, handler, símbolos proibidos encontrados)."""
    violacoes: list[tuple[str, str, str]] = []
    total = 0
    for path in sorted(acoes_dir.glob("*.py")):
        if path.name in ("base.py", "__init__.py"):
            continue
        src = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src, filename=str(path))
        except SyntaxError as exc:
            violacoes.append((path.name, "<parse>", f"SyntaxError: {exc}"))
            continue
        for hname, fn_node in _handlers_registrados(tree).items():
            total += 1
            hit = _simbolos_chamados(fn_node) & PROIBIDOS
            if hit:
                violacoes.append((path.name, hname, ",".join(sorted(hit))))
    return violacoes, total


# ───────────────────────── oráculos 1/2/3 reutilizáveis (p/ mutação) ────────

def _oraculo_1(contexto_fn) -> str:
    """fail-open: agente inexistente E CONSULTOR_KB_DIR vazio → "" sem exceção."""
    agente_fantasma = "inexistente_5_4b_" + uuid.uuid4().hex[:8]
    out_a = contexto_fn(agente_fantasma, "qualquer pergunta")
    if out_a != "":
        raise OracleFail(f"agente inexistente: esperado '', veio {out_a!r}")

    tmp_vazio = tempfile.mkdtemp(prefix="kb54b_vazio_")
    try:
        orig_dir, orig_cache = kb._DIR, dict(kb._CACHE)
        kb._DIR = Path(tmp_vazio)
        kb._CACHE.clear()
        try:
            out_b = contexto_fn("qualquer_agente_5_4b", "x")
            if out_b != "":
                raise OracleFail(f"CONSULTOR_KB_DIR vazio: esperado '', veio {out_b!r}")
        finally:
            kb._DIR = orig_dir
            kb._CACHE.clear()
            kb._CACHE.update(orig_cache)
    finally:
        shutil.rmtree(tmp_vazio, ignore_errors=True)
    return "agente inexistente -> ''; CONSULTOR_KB_DIR vazio -> '' (ambos sem exceção)"


def _oraculo_2(contexto_fn) -> str:
    """injeção presente/ausente: com .md → bloco "[CONHECIMENTO DE DOMINIO";
    sem .md (agente distinto, mesmo diretório) → ""."""
    tmp = tempfile.mkdtemp(prefix="kb54b_o2_")
    try:
        agente = "agente_o2_" + uuid.uuid4().hex[:6]
        md = ("## Conhecimento: Teste O2\n"
              "corpo de teste com a palavra chave alvo presente\n")
        (Path(tmp) / f"{agente}.md").write_text(md, encoding="utf-8")

        orig_dir, orig_cache = kb._DIR, dict(kb._CACHE)
        kb._DIR = Path(tmp)
        kb._CACHE.clear()
        try:
            presente = contexto_fn(agente, "qual a palavra chave alvo?")
            if "[CONHECIMENTO DE DOMINIO" not in presente:
                raise OracleFail(f".md presente mas bloco ausente da saída: {presente!r}")
            ausente = contexto_fn("agente_sem_md_" + uuid.uuid4().hex[:6], "qual a palavra chave alvo?")
            if ausente != "":
                raise OracleFail(f"agente sem .md: esperado '', veio {ausente!r}")
        finally:
            kb._DIR = orig_dir
            kb._CACHE.clear()
            kb._CACHE.update(orig_cache)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return "com .md -> contém '[CONHECIMENTO DE DOMINIO'; sem .md -> ''"


def _oraculo_3(contexto_fn) -> str:
    """nunca-fabricar: TODO número na saída já estava no .md (saída ⊆ .md).
    `contexto_fn` é o alvo — real (deve passar) ou mutante M2 (deve morder)."""
    tmp = tempfile.mkdtemp(prefix="kb54b_o3_")
    try:
        agente = "agente_o3_" + uuid.uuid4().hex[:6]
        md_texto = (
            "## Conhecimento: CCT piso\n"
            "piso R$1.670 (2026), FGTS 8%, INSS 11%\n\n"
            "## Playbook: fechamento\n"
            "corpo do playbook, competencia 2026-06\n"
        )
        (Path(tmp) / f"{agente}.md").write_text(md_texto, encoding="utf-8")

        orig_dir, orig_cache = kb._DIR, dict(kb._CACHE)
        kb._DIR = Path(tmp)
        kb._CACHE.clear()
        try:
            saida = contexto_fn(agente, "piso")
            if not saida:
                raise OracleFail("saída vazia — não é possível provar nunca-fabricar (esperado conteúdo do .md)")
            nums_saida = _numeros(saida)
            nums_md = _numeros(md_texto)
            extras = nums_saida - nums_md
            if extras:
                raise OracleFail(
                    f"saída contém número(s) NÃO presentes no .md (fabricação!): {sorted(extras)} "
                    f"(saída={sorted(nums_saida)} md={sorted(nums_md)})")
        finally:
            kb._DIR = orig_dir
            kb._CACHE.clear()
            kb._CACHE.update(orig_cache)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return "saída ⊆ .md — nenhum número novo (números da saída ⊆ números do .md)"


# ───────────────────────── mutações ──────────────────────────────

_ONDA_MUT_SRC = '''"""MUTAÇÃO-TESTE 5.4b (M1) — NÃO É CÓDIGO REAL, gerado e removido pela suite
test_oraculos_5_4b.py só para provar que o oráculo 4 (anti-burla) morde um
handler que pula propor() e chama execução direta."""
from __future__ import annotations

from ..tool_registry import ToolDef, register


async def _propor_evil_mut(db, user, scope, **kw):
    # BYPASS proibido: chama execução direta sem passar por base.propor().
    resultado = await executar_lote(db, kw.get("lote_id"), otp="000000")
    return {"status": "executado", "resultado": resultado}


EVIL_TOOL_MUT = register(ToolDef(
    "propor_evil_mut_5_4b", "dp", "MUTAÇÃO 5.4b — NÃO USAR EM PRODUÇÃO",
    {"type": "object", "properties": {}}, _propor_evil_mut,
))
'''


def _contexto_MUT_fabrica(agente: str, pergunta: str = "", *, max_secoes: int = 3) -> str:
    """MUTAÇÃO M2: cópia do serviço real que concatena um número extra que NÃO
    está no .md (fabricação) → deve derrubar o oráculo 3."""
    out = kb.contexto_para_prompt(agente, pergunta, max_secoes=max_secoes)
    if out:
        return out + "\nValor adicional fabricado: R$ 87.654,00 (NÃO está no .md)"
    return out


def _expect_bite(fn) -> tuple[bool, str]:
    """A mutação MORDE se o oráculo (síncrono) FALHA sob ela."""
    try:
        fn()
    except (AssertionError, OracleFail) as exc:
        return True, f"mordeu ({type(exc).__name__}: {exc})"
    return False, "NÃO mordeu — oráculo passou sob mutação (oráculo FRACO!)"


def main() -> int:
    results: list[tuple[str, str, bool, str]] = []

    def record(n, desc: str, ok: bool, detail: str = "") -> None:
        results.append((n, desc, ok, detail))
        tag = "PASS" if ok else "FAIL"
        rot = f"ORACULO {n}" if isinstance(n, int) else str(n)
        print(f"{rot} {desc} ... {tag}{(' — ' + detail) if detail else ''}")

    # ════════════════ ORÁCULO 1 — fail-open ════════════════════════════════
    try:
        det = _oraculo_1(kb.contexto_para_prompt)
        record(1, "fail-open (agente inexistente + CONSULTOR_KB_DIR vazio) -> ''", True, det)
    except Exception as exc:
        record(1, "fail-open (agente inexistente + CONSULTOR_KB_DIR vazio) -> ''",
               False, f"{type(exc).__name__}: {exc}")

    # ════════════════ ORÁCULO 2 — injeção presente/ausente ═════════════════
    try:
        det = _oraculo_2(kb.contexto_para_prompt)
        record(2, "injeção presente/ausente ('[CONHECIMENTO DE DOMINIO' só com .md)", True, det)
    except Exception as exc:
        record(2, "injeção presente/ausente ('[CONHECIMENTO DE DOMINIO' só com .md)",
               False, f"{type(exc).__name__}: {exc}")

    # ════════════════ ORÁCULO 3 — nunca-fabricar ═══════════════════════════
    try:
        det = _oraculo_3(kb.contexto_para_prompt)
        record(3, "nunca-fabricar (saída ⊆ .md, sem número novo)", True, det)
    except Exception as exc:
        record(3, "nunca-fabricar (saída ⊆ .md, sem número novo)",
               False, f"{type(exc).__name__}: {exc}")

    # ════════════════ ORÁCULO 4 — anti-burla (AST) ═════════════════════════
    try:
        violacoes, total = _scan_acoes_dir(ACOES_DIR)
        if violacoes:
            raise OracleFail(f"{len(violacoes)} handler(s) com execução direta: {violacoes}")
        if total < 6:
            # as 6 tools da Fase 5.4 (cobrança/proposta/kit/substituição/lote/esocial)
            raise OracleFail(f"esperado >=6 handlers registrados via ToolDef, achou {total} "
                              f"(scan pode estar quebrado — falso PASS por não achar nada)")
        record(4, "anti-burla (AST): nenhum handler chama/importa execução direta", True,
               f"{total} handler(s) escaneado(s) em {ACOES_DIR.name}/*.py — 0 violação")
    except Exception as exc:
        record(4, "anti-burla (AST): nenhum handler chama/importa execução direta",
               False, f"{type(exc).__name__}: {exc}")

    # ════════════════ MUTAÇÃO-TESTE — a suite MORDE? ═══════════════════════
    # M2 primeiro (não toca disco em acoes/): mutante do serviço fabrica número extra.
    m2_ok, m2_det = _expect_bite(lambda: _oraculo_3(_contexto_MUT_fabrica))
    record("MUTAÇÃO M2", "serviço fabrica número extra não presente no .md -> oráculo 3", m2_ok, m2_det)

    # M1: escreve onda_mut.py DENTRO de acoes/ (throwaway; removido no finally).
    mut_path = ACOES_DIR / "onda_mut.py"
    m1_ok, m1_det = False, "não executado"
    try:
        if mut_path.exists():
            raise RuntimeError(f"{mut_path} já existe — recusa sobrescrever (não é meu)")
        mut_path.write_text(_ONDA_MUT_SRC, encoding="utf-8")

        def _checa_mutado():
            # MESMA asserção do oráculo 4 real (0 violações) — sob a mutação, isto
            # tem que FALHAR (é o que prova que o oráculo morde).
            violacoes, _total = _scan_acoes_dir(ACOES_DIR)
            if violacoes:
                raise OracleFail(f"{len(violacoes)} handler(s) com execução direta: {violacoes}")

        m1_ok, m1_det = _expect_bite(_checa_mutado)
        if m1_ok:
            # Não basta morder — tem que apontar NOMINALMENTE o handler certo (arquivo +
            # função + símbolo), não um erro genérico qualquer (senão o oráculo é fraco).
            violacoes, _total = _scan_acoes_dir(ACOES_DIR)
            alvo = [v for v in violacoes if v[0] == "onda_mut.py" and v[1] == "_propor_evil_mut"
                    and "executar_lote" in v[2]]
            if not alvo:
                m1_ok = False
                m1_det = (f"mordeu mas NÃO apontou onda_mut.py/_propor_evil_mut/executar_lote "
                          f"nominalmente (violações vistas: {violacoes}) — oráculo mal-direcionado")
            else:
                m1_det += f"; aponta nominalmente {alvo[0]}"
    finally:
        mut_path.unlink(missing_ok=True)
        pyc_dir = ACOES_DIR / "__pycache__"
        if pyc_dir.is_dir():
            for pyc in pyc_dir.glob("onda_mut.*"):
                pyc.unlink(missing_ok=True)
    record("MUTAÇÃO M1", "handler registrado chama executar_lote direto (sem propor) -> "
                          "oráculo 4 aponta ONDA_MUT.PY/_PROPOR_EVIL_MUT", m1_ok, m1_det)

    # ════════════════ LIMPEZA — prova de 0 remanescentes ═══════════════════
    remanescentes = [str(p) for p in ACOES_DIR.glob("*mut*")]  # onda_mut.py + eventual .pyc
    total_rem = len(remanescentes)
    if total_rem == 0:
        print("\nLIMPEZA OK — 0 remanescentes (onda_mut.py removido; tempdirs kb54b_* removidos)")
    else:
        print(f"\nLIMPEZA FALHOU — remanescentes: {remanescentes}")
    record("LIMPEZA", "0 remanescentes do que a suite criou", total_rem == 0, f"total={total_rem}")

    # ══════════════ RESUMO ══════════════
    oraculos = [r for r in results if isinstance(r[0], int)]
    mutacoes = [r for r in results if isinstance(r[0], str) and r[0].startswith("MUTAÇÃO")]
    limpeza = [r for r in results if r[0] == "LIMPEZA"]
    n_pass = sum(1 for r in oraculos if r[2])
    n_bite = sum(1 for r in mutacoes if r[2])
    print("\n" + "═" * 68)
    print(f"RESUMO: {n_pass}/{len(oraculos)} oráculos PASS  |  "
          f"{n_bite}/{len(mutacoes)} mutações MORDERAM  |  "
          f"limpeza {'OK' if limpeza and limpeza[0][2] else 'FALHOU'}")
    falhas = [r for r in results if not r[2]]
    if falhas:
        print("FALHAS (findings — é o gate mordendo, NÃO ajustar o teste):")
        for n, desc, _ok, det in falhas:
            print(f"  ✗ {n} {desc} — {det}")
        print("═" * 68)
        print("GATE: BLOQUEADO.")
        return 1
    print("═" * 68)
    print(f"OK suite 5.4b ({n_pass}/{len(oraculos)} oráculos + {n_bite}/{len(mutacoes)} mutações) — GATE LIBERADO.")
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception:
        traceback.print_exc()
        code = 2
    raise SystemExit(code)
