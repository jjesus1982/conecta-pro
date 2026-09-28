"""Oráculo — o lote do cartão de ponto imprime QUEM ELA ESCOLHEU (28/09/2026).

Por que existe: a tela «Cartão de ponto em lote» tinha competência, condomínio, função e três
sim/não, e NENHUM jeito de escolher pessoa. Medido antes do conserto, no container de produção:
`candidatos(None, None, False)` → 53 ids → 53 espelhos, 14.283.110 bytes, 23,0 s — todas as vezes,
para qualquer pedido. Quem queria 2 folhas recebia 53.

O defeito é o da família «um lado oferece, o outro não aceita», e aqui eram TRÊS lados: o form
(sem campo), o POST /action (que monta o link) e o GET /pdf (que monta o PDF e refazia a lista
sozinho). Consertar um só deixaria o PDF saindo com 53.

O que afirma (regra, não fotografia — nenhum nome, id ou data fixos):
  a. o form do lote tem um campo cuja chave é `colaboradores`, de um tipo que o renderizador do
     redesign já desenha, e cujas OPÇÕES são colaboradores reais (todo value é id de employee
     ativo não-homologação);
  b. `_filtros_lote` lê a seleção nos DOIS formatos que existem — lista (front `multiselect`) e
     string com vírgulas (Hermes/curl) — e ausência/vazio vira None = «todos», preservando hoje;
  c. `candidatos(..., seleção de N)` devolve EXATAMENTE os N pedidos, e sem seleção devolve
     estritamente mais que N (a seleção filtra de verdade, e None não filtra);
  d. seleção que não casa com os outros filtros devolve VAZIO — nunca cai de volta para todos;
  e. as duas pontas conversam: o POST aceita a chave que o form manda, a contagem da mensagem é
     a da seleção (N), e o link devolvido carrega `colaboradores=<ids>`;
  f. o GET do PDF aceita `colaboradores`, e com N ids sai um PDF com N espelhos (header
     X-Cartao-Lote) e MENOS bytes que o lote inteiro;
  g. o GET com seleção que não casa responde 400 dizendo isso — não devolve o lote inteiro.

Como pegou vermelho: rodado contra `git show HEAD:...` dos dois arquivos, acusou
«(c) candidatos() nem aceita seleção: TypeError ... takes 4 positional arguments but 5 were
given» + (a), (b), (e), (f), (g) — 7 desvios.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho. Última linha: `TOTAL desvios: N`.
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

# Tipos de campo que ModuleView.tsx (frontend/src/components/redesign/ModuleView.tsx) sabe
# desenhar com seleção múltipla. O oráculo roda no container, onde não há frontend, então a
# lista é a ponte: mudar de tipo aqui obriga a conferir o renderizador lá.
_TIPOS_MULTIPLOS = {"multiselect"}

_SQL_COM_ESPELHO = """
SELECT e.id::text
  FROM employees e
 WHERE lower(coalesce(e.status,'')) = 'ativo' AND coalesce(e.is_homologacao,false) = false
   AND EXISTS (SELECT 1 FROM time_sheets ts WHERE ts.employee_id = e.id::text
                AND ts.reference_month = :m AND ts.reference_year = :a
                AND coalesce(ts.is_deleted,false) = false)
 ORDER BY e.nome
"""
_SQL_ULTIMA_COMPETENCIA = """
SELECT reference_year, reference_month FROM time_sheets
 WHERE coalesce(is_deleted,false) = false
 GROUP BY 1,2 HAVING count(*) >= 3 ORDER BY 1 DESC, 2 DESC LIMIT 1
"""


async def main() -> int:  # noqa: C901, PLR0912, PLR0915
    from core.database import async_session_factory
    from core.database.session import SyncSessionLocal
    from modules.operacional.controllers.redesign_builders import _dgx_f7_ponto as f7
    from modules.people_management.ponto import cartao_lote

    falhas: list[str] = []
    async with async_session_factory() as db:
        comp = (await db.execute(text(_SQL_ULTIMA_COMPETENCIA))).first()
        if not comp:
            print("SEM DADO: nenhuma competência com 3+ espelhos calculados — oráculo não roda.")
            return 1
        ano, mes = int(comp[0]), int(comp[1])
        com_espelho = [r[0] for r in (await db.execute(text(_SQL_COM_ESPELHO), {"m": mes, "a": ano})).all()]
        if len(com_espelho) < 3:
            print(f"SEM DADO: só {len(com_espelho)} colaborador(es) com espelho em {mes:02d}/{ano}.")
            return 1
        sel = com_espelho[:2]
        n = len(sel)

        # ── a) o form oferece a escolha, com opções que existem ─────────────────────────
        op = await f7._opcoes(db)
        campos = f7._tela_cartao_lote(op)["fields"]
        campo = next((c for c in campos if c.get("key") == "colaboradores"), None)
        if campo is None:
            falhas.append(f"(a) o form do lote não tem campo `colaboradores` — chaves: {[c.get('key') for c in campos]}")
        else:
            if campo.get("type") not in _TIPOS_MULTIPLOS:
                falhas.append(
                    f"(a) campo `colaboradores` é type={campo.get('type')!r}; o renderizador do redesign "
                    f"só faz seleção múltipla com {sorted(_TIPOS_MULTIPLOS)} — tipo novo não se inventa"
                )
            vals = [str(o.get("value")) for o in (campo.get("options") or [])]
            if not vals:
                falhas.append("(a) campo `colaboradores` sem opções — ela não teria ninguém para escolher")
            else:
                ativos = {
                    r[0]
                    for r in (
                        await db.execute(
                            text(
                                "SELECT id::text FROM employees WHERE lower(coalesce(status,''))='ativo' "
                                "AND coalesce(is_homologacao,false)=false"
                            )
                        )
                    ).all()
                }
                forasteiros = [v for v in vals if v not in ativos]
                if forasteiros:
                    falhas.append(
                        f"(a) {len(forasteiros)} opção(ões) de `colaboradores` não são employee ativo "
                        f"(ex.: {forasteiros[0]}) — opção que o filtro não casa é opção mentirosa"
                    )

        # ── b) os dois formatos de seleção, e vazio = todos ─────────────────────────────
        try:
            base = {"competencia": f"{mes:02d}/{ano}"}
            como_lista = f7._filtros_lote({**base, "colaboradores": sel})["ids"]
            como_texto = f7._filtros_lote({**base, "colaboradores": ",".join(sel)})["ids"]
            sem = f7._filtros_lote(base)["ids"]
            vazio = f7._filtros_lote({**base, "colaboradores": []})["ids"]
            if como_lista != sel:
                falhas.append(f"(b) seleção como LISTA (o que o front manda) virou {como_lista!r}, esperado {sel!r}")
            if como_texto != sel:
                falhas.append(f"(b) seleção como TEXTO com vírgulas virou {como_texto!r}, esperado {sel!r}")
            if sem is not None or vazio is not None:
                falhas.append(f"(b) sem seleção deveria ser None (=todos); veio {sem!r} / vazio {vazio!r}")
        except Exception as e:  # noqa: BLE001
            falhas.append(f"(b) _filtros_lote não entende `colaboradores`: {type(e).__name__}: {e}")

        # ── c/d) quem entra no lote ─────────────────────────────────────────────────────
        def _cands(ids):
            with SyncSessionLocal() as s:
                return [i for i, _nome in cartao_lote.candidatos(s, None, None, False, ids)]

        try:
            todos, escolhidos = _cands(None), _cands(sel)
            # (d) id que não pertence à base: seleção não casa → vazio, nunca todos
            fantasma = _cands(["00000000-0000-0000-0000-000000000000"])
        except TypeError as e:
            todos = escolhidos = fantasma = None
            falhas.append(f"(c) candidatos() nem aceita seleção: TypeError: {e}")
        if escolhidos is not None:
            if sorted(escolhidos) != sorted(sel):
                falhas.append(f"(c) com {n} escolhidos, candidatos devolveu {len(escolhidos)}: {escolhidos!r}")
            if len(todos) <= n:
                falhas.append(f"(c) sem seleção deveria trazer mais que {n}; trouxe {len(todos)} — nada foi provado")
            if fantasma:
                falhas.append(f"(d) seleção que não casa devolveu {len(fantasma)} pessoa(s) — vazio virou tudo")

        # ── e) POST /action: aceita a chave do form e leva a seleção no link ────────────
        from sqlalchemy import select  # noqa: PLC0415

        from core.auth.module_scope import user_modules  # noqa: PLC0415
        from core.models.user import User  # noqa: PLC0415

        usuarios = (await db.execute(select(User).where(User.is_active.is_(True)))).scalars().all()
        dp_user = next((u for u in usuarios if "dp" in user_modules(u)), None)
        if dp_user is None:
            falhas.append("(e) nenhum usuário ativo com o módulo `dp` — sem quem chame a ação")
        else:
            try:
                r = await f7.rd_cartao_lote(
                    dp_user, payload={"competencia": f"{mes:02d}/{ano}", "colaboradores": sel}, db=db
                )
                url = r["doc"]["url"]
                if f"colaboradores={','.join(sel)}" not in url:
                    falhas.append(f"(e) o link do PDF não leva a seleção: {url}")
                if not r["message"].startswith(f"{n} de {n} "):
                    falhas.append(f"(e) a mensagem não fala dos {n} escolhidos: {r['message']!r}")
            except Exception as e:  # noqa: BLE001
                falhas.append(f"(e) POST do lote recusou a chave `colaboradores`: {type(e).__name__}: {e}")

        # ── f/g) GET do PDF: a ponta que realmente monta o arquivo ─────────────────────
        async def _pdf(ids_qs: str):
            return await f7.rd_cartao_lote_get(
                ano=ano, mes=mes, current_user=dp_user, colaboradores=ids_qs, detalhes=0
            )

        if dp_user is not None:
            try:
                resp = await _pdf(",".join(sel))
                cab = resp.headers.get("X-Cartao-Lote", "")
                if not cab.startswith(f"{n} espelho"):
                    falhas.append(f"(f) o PDF não saiu com {n} espelhos: X-Cartao-Lote={cab!r}")
                inteiro = await _pdf("")
                if len(resp.body) >= len(inteiro.body):
                    falhas.append(
                        f"(f) PDF de {n} ({len(resp.body)} bytes) não é menor que o do lote inteiro "
                        f"({len(inteiro.body)} bytes) — a seleção não chegou no gerador"
                    )
            except TypeError as e:
                falhas.append(f"(f) o GET do PDF não aceita `colaboradores`: {e}")
            except Exception as e:  # noqa: BLE001
                falhas.append(f"(f) GET do PDF falhou com seleção: {type(e).__name__}: {e}")
            try:
                await _pdf("00000000-0000-0000-0000-000000000000")
                falhas.append("(g) seleção que não casa NÃO deu erro — o PDF saiu com o lote inteiro?")
            except Exception as e:  # noqa: BLE001
                cod = getattr(e, "status_code", None)
                if cod != 400:
                    falhas.append(f"(g) seleção que não casa deveria dar 400; deu {cod} ({type(e).__name__}: {e})")

    for f in falhas:
        print(f"DESVIO: {f}")
    print(f"TOTAL desvios: {len(falhas)}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    raise SystemExit(asyncio.run(main()))
