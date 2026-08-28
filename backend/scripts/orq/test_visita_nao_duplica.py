"""Oráculo — uma visita por cliente por conversa (28/08/2026).

A visita do The Sun PARTIU EM DUAS na conversa real do Jordan: 21 achados numa e 4 na
outra, 18 segundos entre a última gravação de uma e a criação da outra. Ele disse "vou
começar do zero" — querendo dizer "reenvio as mídias" — e o agente abriu visita nova.

⚠️ O custo não é organização: se ele mandasse gerar o PDF, sairia com 4 achados PARECENDO
completo. É o erro que mente com aparência de certo, o pior tipo.

⭐ CAUSA: TRÊS portas criam visita e só UMA tinha trava.
    `_mtool_abrir_visita`                    → tinha
    `criar_relatorio_visita` → `V.criar_relatorio` → NÃO tinha
    `crm/services/visit_reports.py`          → serviço, não conhece conversa

A trava vive na porta do WhatsApp e não no serviço porque é a CONVERSA que define
duplicata — o serviço do CRM não a conhece, e pô-la lá seria acoplar o CRM ao canal.

Invariante (não fotografia): **nenhum cliente tem duas visitas em `rascunho` na mesma
conversa.** Vale para as duas portas.
"""
import asyncio
import sys

sys.path.insert(0, "/app")

FALHAS: list[str] = []


def checar(cond: bool, titulo: str, detalhe: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FALHA'} · {titulo}{(' — ' + detalhe) if detalhe else ''}")
    if not cond:
        FALHAS.append(titulo)


async def main() -> int:
    import main_production  # noqa: F401,PLC0415

    from sqlalchemy import text

    from core.database import async_session_factory
    from modules.integrations.connectors.whatsapp import agent_service as A

    # 1 · INVARIANTE NO BANCO: nenhuma conversa com 2+ visitas em rascunho
    async with async_session_factory() as db:
        dups = (await db.execute(text(r"""
            SELECT substring(conteudo_md from '\[wa:(\d+)\]') conv, cliente_nome, count(*) n
            FROM crm_visit_reports
            WHERE status::text = 'rascunho' AND conteudo_md ~ '\[wa:\d+\]'
            GROUP BY 1, 2 HAVING count(*) > 1"""))).all()
    checar(not dups, "nenhuma conversa tem 2+ visitas em rascunho para o mesmo cliente",
           "; ".join(f"conv {c}: {n}x {nm[:26]}" for c, nm, n in dups) if dups else "")

    # 2 · AS DUAS PORTAS recusam a segunda visita
    async with async_session_factory() as db:
        alvo = (await db.execute(text(r"""
            SELECT substring(conteudo_md from '\[wa:(\d+)\]')::int conv, cliente_nome
            FROM crm_visit_reports
            WHERE status::text = 'rascunho' AND conteudo_md ~ '\[wa:\d+\]' LIMIT 1"""))).first()
    if not alvo:
        checar(False, "há visita aberta para exercitar as portas",
               "nenhuma visita em rascunho com marca de conversa — teste inconclusivo")
    else:
        conv, cli = alvo
        r1 = await A._mtool_abrir_visita_wrapper(conv, cli) if hasattr(
            A, "_mtool_abrir_visita_wrapper") else None
        async with async_session_factory() as db:
            r1 = await A._mtool_abrir_visita(db, {"cliente": cli}, conv)
        checar(bool(r1.get("ja_aberta")),
               "porta 1 (`abrir_visita`) recusa a segunda", str(r1)[:80])
        r2 = await A._exec_manager_tool(
            "criar_relatorio_visita", {"cliente_nome": cli, "panorama": "oráculo"}, conv)
        checar(bool(r2.get("ja_aberta")),
               "porta 2 (`criar_relatorio_visita`) recusa a segunda",
               "criou visita nova — a família não está fechada" if not r2.get("ja_aberta")
               else f"aponta para a de {r2.get('achados')} achado(s)")
        checar("começar do zero" in str(r2.get("instrucao", "")),
               "a recusa ENSINA o agente a não interpretar 'do zero' como 'descartar'")

    print()
    if FALHAS:
        print(f"  ❌ {len(FALHAS)} FALHA(S): {', '.join(FALHAS)}")
        return 1
    print("  ✅ o levantamento de campo não se parte em dois.")
    return 0


sys.exit(asyncio.run(main()))
