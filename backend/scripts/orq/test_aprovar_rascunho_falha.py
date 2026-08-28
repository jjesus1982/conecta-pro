"""Oráculo — quando a aprovação FALHA, o motivo tem de sobreviver (28/08/2026).

O Jordan clicou "aprovar" na proposta da Vega e viu "não foi possível salvar". Fomos ao
banco e o rascunho estava com `status='rascunho'` e **`erro_execucao = NULL`** — que é
indistinguível de "nunca foi tentado". Ficamos adivinhando.

⭐ A causa: `await db.rollback()` no `except` expira TODOS os objetos da sessão, inclusive o
`current_user`. A linha seguinte fazia `d2.decidido_por = current_user.id` → lazy-load fora
do contexto async → `MissingGreenlet`. **O tratador de erro morria antes de gravar o erro**,
e o motivo original era a segunda vítima.

⚠️ E o defeito já tinha sido achado e consertado no `aprovar_lote`, 57 linhas abaixo, no
MESMO arquivo, com o comentário explicando o remédio — e o `aprovar_rascunho` ficou quebrado.
É a família viva depois do conserto do caso que apareceu.

⭐ QUEM PROVA É A ROTA. Chamando a função em processo o defeito NÃO aparece: o
`MissingGreenlet` depende do contexto async do servidor. Este oráculo bate no HTTP.

Invariante: rascunho cuja execução falha termina com `status='falha'` E `erro_execucao`
PREENCHIDO. O 500 é esperado; o silêncio, não.
"""
import asyncio
import sys
import uuid

sys.path.insert(0, "/app")

MARCA = "__ORACULO_FALHA_APROVACAO__"
FALHAS: list[str] = []


def checar(cond: bool, titulo: str, detalhe: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FALHA'} · {titulo}{(' — ' + detalhe) if detalhe else ''}")
    if not cond:
        FALHAS.append(titulo)


async def main() -> int:
    import httpx
    from sqlalchemy import select, text

    from core.auth.jwt import create_access_token
    from core.database import async_session_factory
    from core.models.user import User

    draft_id = str(uuid.uuid4())
    async with async_session_factory() as db:
        u = (await db.execute(select(User).where(
            User.email == "jjesus@conectamais.pro"))).scalars().first()
        if u is None:
            print("  ⛔ usuário do dono não encontrado"); return 1
        # Rascunho de um tipo que o executor NÃO conhece: a execução falha de verdade,
        # que é a única forma de exercitar o `except`. Payload inofensivo.
        await db.execute(text("""
            INSERT INTO agent_drafts (id, tipo, modulo, titulo, resumo, payload, status,
                                      gate, requires_otp, roles_aprovador, solicitado_por)
            VALUES (cast(:i AS uuid), :t, 'crm', :ti, 'oráculo', '{}'::jsonb, 'rascunho',
                    '🟡', false, ARRAY['admin']::text[], :u)"""),
            {"i": draft_id, "t": f"{MARCA}_tipo_inexistente", "ti": MARCA, "u": str(u.id)})
        await db.commit()

    try:
        token = create_access_token(str(u.id))
        async with httpx.AsyncClient(base_url="http://localhost:8080", timeout=60) as cli:
            r = await cli.post("/api/v1/redesign/action/aprovar-rascunho",
                               params={"draft_id": draft_id}, json={},
                               headers={"Authorization": f"Bearer {token}"})
        print(f"  rota respondeu HTTP {r.status_code}")
        checar(r.status_code in (400, 409, 422, 500),
               "a rota responde erro (não 200 mentindo sucesso)", str(r.status_code))

        async with async_session_factory() as db:
            row = (await db.execute(text(
                "SELECT status, erro_execucao FROM agent_drafts WHERE id = cast(:i AS uuid)"),
                {"i": draft_id})).first()
        st, err = (row or (None, None))
        print(f"  no banco: status={st!r} erro_execucao={(err or '')[:70]!r}")
        checar(st == "falha", "o rascunho fica com status 'falha'", f"status={st!r}")
        checar(bool(err),
               "⭐ o MOTIVO da falha foi gravado (não é NULL)",
               "erro_execucao vazio — o tratador de erro morreu antes de commitar")
    finally:
        async with async_session_factory() as db:
            await db.execute(text("DELETE FROM agent_drafts WHERE id = cast(:i AS uuid)"),
                             {"i": draft_id})
            await db.commit()

    print()
    if FALHAS:
        print(f"  ❌ {len(FALHAS)} FALHA(S): {', '.join(FALHAS)}")
        return 1
    print("  ✅ falha de aprovação deixa rastro — o erro não é a própria vítima.")
    return 0


sys.exit(asyncio.run(main()))
