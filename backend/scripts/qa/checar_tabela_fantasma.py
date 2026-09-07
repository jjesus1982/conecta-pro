#!/usr/bin/env python3
"""O modelo declara `__tablename__` de uma tabela que não existe em schema NENHUM.

Achado em 07/09/2026, auditando a limpeza dos 🔴. O censo daquela noite mediu 691 tabelas
existentes e classificou 392 como mortas por não terem linha. **Esta família é invisível
para esse censo por construção: não se conta linha de tabela que não existe.**

São 73 nomes declarados sem tabela por trás, e 29 deles são `gov_*` — a camada de
persistência inteira do fiscal/governo, sem uma migration sequer que os crie:

    gov_sync_logs · gov_certidoes · gov_guias_recolhimento · gov_documentos_fiscais
    gov_eventos_esocial · gov_declaracoes_dctfweb · gov_arquivos_sped · +22

`gov_sync_logs` é o pai declarado de 8 chaves estrangeiras. E é lido pelo painel de status
dos serviços de governo, que faz `except → return {}`:

    00:05:29 WARNING Falha ao agregar gov_sync_logs (status marcado como desconhecido)

O painel devolve vazio todo dia, no nível WARNING, e nunca devolveu outra coisa. Quem for
depurar "o beat de certidão rodou?" vai consultar um instrumento que não lê nada — e as
certidões de verdade moram em `ged_certidoes`.

⚠️ **`__tablename__` sem tabela não é o mesmo que tabela sem linha.** A segunda é decisão de
produto (ninguém usou ainda). A primeira é código que nunca teve como funcionar: a primeira
query levanta `UndefinedTable`, e se ela estiver dentro de um `except` amplo, levanta calada.

GRADIENTE: a classe referenciada FORA do próprio arquivo é a que alguém vai consultar um
dia — essas reprovam. Modelo declarado e nunca importado por ninguém é entulho, e sai no
relatório como informação.

LIMITE: só pega `__tablename__` literal. Nome montado em runtime, `__table_args__` com
schema explícito e tabela criada por `create_all` fora do alembic passam batido.

    python3 backend/scripts/qa/checar_tabela_fantasma.py
    python3 backend/scripts/qa/checar_tabela_fantasma.py --self-check
"""
from __future__ import annotations

import asyncio
import re
import sys
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
IGNORAR = ("venv", "__pycache__", "_orphaned", "_quarentena")
TABLENAME = re.compile(r'^\s*__tablename__\s*=\s*["\']([a-zA-Z_][\w]*)["\']', re.M)
CLASSE = re.compile(r"^class\s+(\w+)\s*\(", re.M)


def declaradas(raiz: Path = RAIZ) -> dict[str, list[tuple[str, int, str]]]:
    """tabela -> [(arquivo, linha, classe que a declara)]"""
    out: dict[str, list[tuple[str, int, str]]] = defaultdict(list)
    for arq in sorted(raiz.rglob("*.py")):
        if any(x in p for p in arq.parts for x in IGNORAR):
            continue
        try:
            txt = arq.read_text(errors="ignore")
        except OSError:
            continue
        for m in TABLENAME.finditer(txt):
            linha = txt[: m.start()].count("\n") + 1
            classes = [c for c in CLASSE.finditer(txt) if c.start() < m.start()]
            dono = classes[-1].group(1) if classes else "?"
            out[m.group(1)].append((str(arq.relative_to(raiz)), linha, dono))
    return out


_CORPUS: dict[str, str] = {}


def _carregar(raiz: Path) -> dict[str, str]:
    """A árvore inteira uma vez só. A primeira versão relia 3.200 arquivos por classe."""
    if _CORPUS:
        return _CORPUS
    for arq in raiz.rglob("*.py"):
        if any(x in p for p in arq.parts for x in IGNORAR):
            continue
        try:
            _CORPUS[str(arq.relative_to(raiz))] = arq.read_text(errors="ignore")
        except OSError:
            continue
    return _CORPUS


def _referenciada_fora(classe: str, arquivo: str, raiz: Path = RAIZ) -> bool:
    """Alguém usa esta classe fora do arquivo que a declara? Então alguém vai consultá-la."""
    alvo = re.compile(rf"\b{re.escape(classe)}\b")
    return any(alvo.search(txt) for nome, txt in _carregar(raiz).items() if nome != arquivo)


async def _tabelas_do_banco() -> set[str]:
    import main_production  # noqa: F401 — primeiro, sempre
    from sqlalchemy import text

    from core.database import async_session_factory

    async with async_session_factory() as db:
        # TODOS os schemas de propósito: a quarentena `lixo_*` conta como existente —
        # tabela movida é reversível; tabela que nunca existiu, não.
        r = await db.execute(text(
            "select c.relname from pg_class c join pg_namespace n on n.oid=c.relnamespace "
            "where c.relkind in ('r','v','m','p') and n.nspname not in "
            "('pg_catalog','information_schema')"
        ))
        return {x[0] for x in r}


def _self_check() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        raiz = Path(d)
        (raiz / "m").mkdir()
        (raiz / "m" / "modelo.py").write_text(
            'class Viva(Base):\n    __tablename__ = "viva"\n\n'
            'class Fantasma(Base):\n    __tablename__ = "fantasma"\n'
        )
        (raiz / "m" / "usa.py").write_text("from m.modelo import Fantasma\nx = Fantasma\n")
        d_ = declaradas(raiz)
        assert set(d_) == {"viva", "fantasma"}, d_
        assert d_["fantasma"][0][2] == "Fantasma", d_["fantasma"]
        assert _referenciada_fora("Fantasma", "m/modelo.py", raiz) is True
        assert _referenciada_fora("Viva", "m/modelo.py", raiz) is False
    print("self-check OK: acha __tablename__, o dono, e se a classe vaza do arquivo")


async def main() -> int:
    if "--self-check" in sys.argv:
        _self_check()
        return 0

    decl = declaradas()
    reais = await _tabelas_do_banco()
    fantasmas = {t: v for t, v in decl.items() if t not in reais}

    usadas, entulho = [], []
    for tab, ocs in sorted(fantasmas.items()):
        arq, lin, classe = ocs[0]
        (usadas if _referenciada_fora(classe, arq) else entulho).append((tab, arq, lin, classe))

    fam: dict[str, int] = defaultdict(int)
    for tab in fantasmas:
        fam[tab.split("_")[0]] += 1

    if usadas:
        print(f"💥 TABELA DECLARADA QUE NÃO EXISTE, e a classe é usada fora ({len(usadas)})")
        for tab, arq, lin, classe in usadas:
            print(f"   {tab:38s} {classe:28s} {arq}:{lin}")
    if entulho:
        print(f"\n🔇 declarada, inexistente, classe nunca usada fora ({len(entulho)}) — entulho")
        for tab, arq, lin, classe in entulho[:12]:
            print(f"   {tab:38s} {arq}:{lin}")
        if len(entulho) > 12:
            print(f"   ... mais {len(entulho) - 12}")

    print(f"\ndeclaradas {len(decl)} · existem {len(decl) - len(fantasmas)} · "
          f"fantasmas {len(fantasmas)} ({len(usadas)} usadas · {len(entulho)} entulho)")
    top = sorted(fam.items(), key=lambda x: -x[1])[:5]
    print("por família: " + " · ".join(f"{k}_* {n}" for k, n in top if n > 1))

    if usadas:
        print("FAIL checar_tabela_fantasma")
        return 1
    print("OK checar_tabela_fantasma: nenhuma tabela fantasma alcançável por código")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
