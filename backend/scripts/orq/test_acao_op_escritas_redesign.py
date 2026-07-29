"""Ações redesign (escrita) passagem-turno / instrucao-posto / banco-horas criam registro REAL
via os controllers existentes. Cria, confere no banco e LIMPA (não clobba dado real)."""
import asyncio
import uuid
from datetime import date
from types import SimpleNamespace

from sqlalchemy import text

from core.database import async_session_factory
from modules.operacional.controllers.redesign_builders.operacional import (
    rd_action_banco_horas, rd_action_instrucao_posto, rd_action_passagem_turno,
)


def _user():
    return SimpleNamespace(id=uuid.uuid4(), name="Teste Redesign", email="teste@conectapro.com.br",
                           condominio_id=None, tenant_id=None)


async def main() -> None:
    async with async_session_factory() as db:
        user = _user()
        # 1) passagem-turno
        post = (await db.execute(text("SELECT id FROM posts WHERE coalesce(is_active,true) LIMIT 1"))).first()
        assert post, "sem posto ativo"
        r = await rd_action_passagem_turno(current_user=user, payload={
            "post_id": str(post[0]), "turno": "diurno", "resumo": "Turno tranquilo — teste oráculo redesign",
            "data_turno": date.today().isoformat()}, db=db)
        assert r.get("ok") and r.get("id"), f"passagem falhou: {r}"
        chk = (await db.execute(text("SELECT resumo FROM operacional_passagens_turno WHERE id::text=:i"), {"i": r["id"]})).first()
        assert chk and "teste oráculo redesign" in chk[0], "passagem não persistiu"
        await db.execute(text("DELETE FROM operacional_passagens_turno WHERE id::text=:i"), {"i": r["id"]}); await db.commit()
        print(f"OK passagem-turno: id={r['id']} (criada+limpa)")

        # 2) instrucao-posto — escolhe posto SEM instrução (net-new p/ poder limpar sem clobar)
        p2 = (await db.execute(text(
            "SELECT p.id FROM posts p LEFT JOIN operacional_post_orders po ON po.post_id=p.id "
            "WHERE coalesce(p.is_active,true) AND po.id IS NULL LIMIT 1"))).first()
        if p2:
            r2 = await rd_action_instrucao_posto(current_user=user, payload={
                "post_id": str(p2[0]), "titulo": "POP teste", "conteudo": "Procedimento de teste oráculo redesign — apagar"}, db=db)
            assert r2.get("ok"), f"instrucao falhou: {r2}"
            chk2 = (await db.execute(text("SELECT conteudo FROM operacional_post_orders WHERE post_id::text=:i"), {"i": str(p2[0])})).first()
            assert chk2 and "teste oráculo" in chk2[0], "instrucao não persistiu"
            await db.execute(text("DELETE FROM operacional_post_orders WHERE post_id::text=:i"), {"i": str(p2[0])}); await db.commit()
            print(f"OK instrucao-posto: post={p2[0]} v{r2.get('versao')} (criada+limpa)")
        else:
            print("SKIP instrucao-posto: todos os postos já têm instrução")

        # 3) banco-horas
        emp = (await db.execute(text("SELECT id FROM employees WHERE coalesce(status,'')='ativo' LIMIT 1"))).first()
        assert emp, "sem employee ativo"
        r3 = await rd_action_banco_horas(current_user=user, payload={
            "employee_id": str(emp[0]), "entry_type": "credit", "hours": "8",
            "reference_date": date.today().isoformat(), "reason": "teste oráculo redesign"}, db=db)
        assert r3.get("ok") and r3.get("id"), f"banco-horas falhou: {r3}"
        chk3 = (await db.execute(text("SELECT hours FROM time_bank WHERE id::text=:i"), {"i": r3["id"]})).first()
        assert chk3 and abs(float(chk3[0]) - 8.0) < 0.01, "banco-horas não persistiu"
        await db.execute(text("DELETE FROM time_bank WHERE id::text=:i"), {"i": r3["id"]})
        await db.execute(text("DELETE FROM redesign_gate_otp WHERE ref LIKE 'idem:bh:%'")); await db.commit()
        print(f"OK banco-horas: id={r3['id']} (criado+limpo)")


if __name__ == "__main__":
    asyncio.run(main())
