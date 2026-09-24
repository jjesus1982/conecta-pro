"""Oráculo — Parâmetros do sistema por CNPJ (DGX F4, 24/09/2026).

Por que existe: o DGX guarda um valor por (parâmetro, empresa) e tem UMA tela de Configurações.
Aqui `system_configs` era global, sem porta de edição, e os parâmetros de negócio viviam
chumbados em Python (40% do adiantamento, 15 min de tolerância do ponto...). O risco de um
leitor único é ele MENTIR baixinho: default no código diferente do banco, valor por empresa
que não vence o global, edição sem trilha.

O que afirma:
  a) toda chave semeada pela frente existe no banco com `descricao` e `grupo` preenchidos;
  b) `param('folha.adiantamento_percentual')` é o que `calculo_service` usa de fato: default
     do código == valor semeado, e o adiantamento recalculado de 1 colaborador em 09/2026 ==
     salário base × parâmetro (paralelo cego: o valor não mudou);
  c) valor por empresa vence o global e empresa sem valor cai no global (fixture
     'FIXTURE DGX F4', apagada ao fim);
  d) gravar por `parametro-salvar` deixa no `historico` quem, quando, de → para;
  e) nenhum `param()`/`param_sync()` no código tem default que contradiga o seed (AST sobre
     backend/core e backend/modules, default avaliado no namespace do módulo);
  f) a tela `parametros` está fiada no build de `configuracoes` e no EXTRA_MENU, e lista
     todas as chaves ativas com uma coluna por empresa do grupo.

Estado medido no nascimento (sandbox, 24/09/2026): `core/parametros.py` e a frente não
existiam → VERMELHO na importação.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho. Linha final `TOTAL ...`.
"""

from __future__ import annotations

import ast
import asyncio
import importlib
import inspect
import sys
from decimal import Decimal
from pathlib import Path

CHAVE_FIX = "dgx.f4.fixture"
CM, PAT = "35710481000103", "66014833000110"


def _iguais(default, seed: str) -> bool:
    if isinstance(default, bool):
        return str(default).lower() == seed.strip().lower()
    try:
        return Decimal(str(default)) == Decimal(seed)
    except ArithmeticError:
        return str(default) == seed


def _varredura_ast(seed: dict[str, str | None]) -> list[str]:
    """(e) todo chamador de param/param_sync: chave semeada e default igual ao seed."""
    falhas: list[str] = []
    raiz = Path("/app")
    usos = 0
    for arq in list((raiz / "core").rglob("*.py")) + list((raiz / "modules").rglob("*.py")):
        if "_quarentena" in str(arq) or arq.name == "parametros.py":
            continue
        try:
            arvore = ast.parse(arq.read_text(encoding="utf8"))
        except (SyntaxError, OSError):
            continue
        mod = None
        for no in ast.walk(arvore):
            if not isinstance(no, ast.Call):
                continue
            nome = no.func.attr if isinstance(no.func, ast.Attribute) else getattr(no.func, "id", "")
            if nome not in ("param", "param_sync"):
                continue
            usos += 1
            chave_no = (
                no.args[1] if len(no.args) > 1 else next((k.value for k in no.keywords if k.arg == "chave"), None)
            )
            if not isinstance(chave_no, ast.Constant) or not isinstance(chave_no.value, str):
                falhas.append(f"{arq}:{no.lineno}: chave de param() não é literal — o oráculo não consegue conferir")
                continue
            chave = chave_no.value
            if chave not in seed:
                falhas.append(f"{arq}:{no.lineno}: param({chave!r}) sem linha no seed — default sem par no banco")
                continue
            default_no = next((k.value for k in no.keywords if k.arg == "default"), None)
            if default_no is None or seed[chave] is None:
                continue
            if mod is None:
                dotted = ".".join(arq.relative_to(raiz).with_suffix("").parts)
                try:
                    mod = importlib.import_module(dotted)
                except Exception as e:  # noqa: BLE001
                    falhas.append(f"{arq}: não importa para avaliar o default: {str(e)[:80]}")
                    break
            try:
                default = eval(ast.unparse(default_no), vars(mod))  # noqa: S307 # nosec B307 — fonte nosso, QA
            except Exception as e:  # noqa: BLE001
                falhas.append(f"{arq}:{no.lineno}: default de {chave!r} não avalia: {e}")
                continue
            if not _iguais(default, seed[chave]):
                falhas.append(f"{arq}:{no.lineno}: default {default!r} de {chave!r} contradiz o seed {seed[chave]!r}")
    if usos < 2:
        falhas.append(
            f"só {usos} chamador(es) de param() no código — a prova de conceito pedia 2 (adiantamento + tolerância)"
        )
    return falhas


def _recalculo_adiantamento(pct: Decimal) -> tuple[str | None, str | None]:
    """(b) recalcula holerites de 09/2026 até achar um adiantamento pelo percentual; devolve (nome, falha)."""
    from sqlalchemy import text

    from core.database.session import SyncSessionLocal
    from modules.people_management.folha.services import calculo_service as cs

    with SyncSessionLocal() as db:
        emps = db.execute(
            text(
                "SELECT id::text, nome, salario_base FROM employees WHERE status = 'ativo' "
                "AND coalesce(tipo_contrato,'') NOT ILIKE '%pj%' AND salario_base > 0 ORDER BY nome LIMIT 15"
            )
        ).fetchall()
        for eid, nome, sal in emps:
            try:
                h = cs.calcular_folha_colaborador(db, eid, 9, 2026)
            except Exception:  # noqa: BLE001
                db.rollback()
                continue
            linha = next(
                (
                    d
                    for d in h.get("descontos", [])
                    if d.get("codigo") == "1045" and "(integral)" in (d.get("referencia") or "")
                ),
                None,
            )
            if not linha:
                continue
            esperado = cs._d(cs._d(sal) * pct)
            if f"{int(pct * 100)}%" not in linha["referencia"]:
                return nome, f"{nome}: referência {linha['referencia']!r} não traz {int(pct * 100)}%"
            if Decimal(str(linha["valor"])) != esperado:
                # base efetiva pode ser o piso CCT (> cadastro): só acusa se nem o piso explica
                base_implicita = (Decimal(str(linha["valor"])) / pct).quantize(Decimal("0.01"))
                if base_implicita < cs._d(sal):
                    return nome, f"{nome}: adiantamento {linha['valor']} ≠ {esperado} (base {sal} × {pct})"
            return nome, None
    return None, None


async def main() -> int:  # noqa: C901, PLR0912, PLR0915
    from sqlalchemy import text

    from core.database import async_session_factory

    falhas: list[str] = []
    try:
        from core import parametros as prm
        from modules.operacional.controllers.redesign_builders import _dgx_f4_parametros as f4
        from modules.operacional.controllers.redesign_builders import configuracoes as cfg
    except Exception as e:  # noqa: BLE001
        print(f"FALHOU: leitor/frente não importa: {e}")
        print("TOTAL parâmetros por CNPJ: 1 falha")
        return 1

    seed = {s["chave"]: s["valor"] for s in f4.SEED}

    # f) fiação
    if "_dgx_f4" not in inspect.getsource(cfg.build):
        falhas.append("configuracoes.build() não chama a frente — tela sem porta")
    ids_menu = {m.get("id") for m in cfg.EXTRA_MENU}
    for tid in ("parametros", "parametro-editar"):
        if tid not in ids_menu:
            falhas.append(f"'{tid}' fora do EXTRA_MENU de configuracoes — tela sem porta")

    async with async_session_factory() as db:
        await f4._ensure(db)
        await db.commit()

        # a) seed com descricao e grupo
        rows = (
            await db.execute(
                text(
                    "SELECT chave, nullif(trim(coalesce(descricao,'')),''), nullif(trim(coalesce(grupo,'')),'') "
                    "FROM system_configs WHERE chave = ANY(:ks)"
                ),
                {"ks": list(seed)},
            )
        ).fetchall()
        achadas = {r[0]: r for r in rows}
        for ch in seed:
            r = achadas.get(ch)
            if r is None:
                falhas.append(f"{ch}: não está no banco depois do _ensure")
            elif not r[1] or not r[2]:
                falhas.append(f"{ch}: sem descricao/grupo ({r[1]!r}, {r[2]!r})")
        grupos = {r[2] for r in rows if r[2]}

        # b) adiantamento — default do código == seed, e o holerite usa o parâmetro
        from modules.people_management.folha.services import calculo_service as cs

        prm.invalidar()
        v = await prm.param(db, "folha.adiantamento_percentual", default=None)
        if v is None:
            falhas.append("folha.adiantamento_percentual sem valor no banco")
        else:
            pct = Decimal(str(v)) / Decimal(100)
            if pct != cs.ADIANTAMENTO_PERCENTUAL:
                falhas.append(
                    f"banco diz {pct} e calculo_service.ADIANTAMENTO_PERCENTUAL é {cs.ADIANTAMENTO_PERCENTUAL}"
                )
            nome, falha = await asyncio.to_thread(_recalculo_adiantamento, pct)
            if falha:
                falhas.append(falha)
            recalculado = nome or "ninguém (todos com adiantamento pago ou espelho)"

        # c) + d) fixture: empresa vence global; salvar deixa histórico
        prm.invalidar()
        await db.execute(text("DELETE FROM system_configs WHERE chave = :c"), {"c": CHAVE_FIX})
        await db.execute(
            text(
                "INSERT INTO system_configs (id, chave, nome, valor, tipo, grupo, descricao, valor_por_empresa) "
                "VALUES (gen_random_uuid(), :c, 'FIXTURE DGX F4', '10', 'integer', 'fixture', 'FIXTURE DGX F4', "
                "CAST(:vpe AS jsonb))"
            ),
            {"c": CHAVE_FIX, "vpe": f'{{"{PAT}": "20"}}'},
        )
        await db.commit()
        try:
            g, c, p = (
                await prm.param(db, CHAVE_FIX, default=0),
                await prm.param(db, CHAVE_FIX, empresa_cnpj="35.710.481/0001-03", default=0),
                await prm.param(db, CHAVE_FIX, empresa_cnpj=PAT, default=0),
            )
            if (g, c, p) != (10, 10, 20):
                falhas.append(
                    f"global/ConectaMais/Patrimonial = {(g, c, p)} — esperado (10, 10, 20): empresa tem de vencer, sem valor cai no global"
                )
            if not isinstance(p, int):
                falhas.append(f"tipo integer devolveu {type(p).__name__}")
            if await prm.param(db, "chave.que.nao.existe", default="x") != "x":
                falhas.append("chave inexistente não devolve o default")
            r = await f4.salvar(db, CHAVE_FIX, CM, "30", quem="oraculo-f4")
            if not r.get("ok"):
                falhas.append(f"salvar não devolveu ok: {r}")
            hist = (
                await db.execute(text("SELECT historico FROM system_configs WHERE chave = :c"), {"c": CHAVE_FIX})
            ).scalar() or []
            ult = hist[-1] if hist else {}
            if (
                not hist
                or ult.get("quem") != "oraculo-f4"
                or ult.get("de") not in (None, "")
                or ult.get("para") != "30"
                or ult.get("empresa") != CM
                or not ult.get("quando")
            ):
                falhas.append(f"histórico não registrou quem/quando/de→para/empresa: {ult}")
            if await prm.param(db, CHAVE_FIX, empresa_cnpj=CM, default=0) != 30:
                falhas.append("valor salvo pela ação não é o lido em seguida (cache não invalidado?)")
            try:
                await f4.salvar(db, CHAVE_FIX, CM, "abc", quem="oraculo-f4")
                falhas.append("'abc' aceito num parâmetro integer")
            except ValueError:
                pass
        finally:
            await db.execute(
                text("DELETE FROM system_configs WHERE chave = :c AND descricao = 'FIXTURE DGX F4'"), {"c": CHAVE_FIX}
            )
            await db.commit()
            prm.invalidar()

        # f) tela
        out: dict = {}
        await f4.telas(db, out)
        scr = out.get("parametros")
        n_ativas = (await db.execute(text("SELECT count(*) FROM system_configs WHERE ativo"))).scalar()
        if not scr:
            falhas.append("telas() não devolve 'parametros'")
        else:
            if len(scr.get("rows") or []) != n_ativas:
                falhas.append(f"tela lista {len(scr.get('rows') or [])} parâmetros e o banco tem {n_ativas} ativos")
            cols = scr.get("cols") or []
            if not any("Patrimonial" in c for c in cols) or not any("Eletr" in c or "Conecta Mais" in c for c in cols):
                falhas.append(f"tela sem coluna por empresa do grupo: {cols}")
        if "parametro-editar" not in out:
            falhas.append("telas() não devolve 'parametro-editar'")

    # e) chamadores
    falhas += _varredura_ast(seed)

    print(f"seed: {len(seed)} chaves em {len(grupos)} grupos · ativas no banco: {n_ativas}")
    if v is not None:
        print(f"adiantamento: {v}% no banco == {cs.ADIANTAMENTO_PERCENTUAL} no código · recalculado: {recalculado}")
    for f in falhas:
        print("FALHOU:", f)
    print(f"TOTAL parâmetros por CNPJ: {len(falhas)} falha(s)")
    if falhas:
        return 1
    print(
        "OK parâmetros por CNPJ: seed descrito, adiantamento igual ao código, empresa vence global, histórico gravado, defaults batem"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
