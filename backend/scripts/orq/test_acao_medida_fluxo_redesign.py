"""Fluxo de aprovação de medida via redesign: submeter→aprovar reusa DisciplinaryService via gate.
Cria uma medida real, roda o fluxo, confere status no banco e LIMPA."""
import asyncio
import uuid
from datetime import date
from types import SimpleNamespace

from sqlalchemy import text

from core.database import async_session_factory
from modules.operacional.controllers.redesign_builders.operacional import (
    rd_action_medida_administrativa, rd_action_medida_aprovar, rd_action_medida_documento,
    rd_action_medida_submeter,
)


async def main() -> None:
    async with async_session_factory() as db:
        # re-rodável: limpa marcadores de idempotência e resíduo de testes anteriores
        await db.execute(text("DELETE FROM disciplinary_actions WHERE reason_description LIKE '%Fluxo aprovacao%teste oraculo%'"))
        await db.execute(text("DELETE FROM redesign_gate_otp WHERE ref LIKE 'idem:medida%'"))
        await db.commit()
        emp = (await db.execute(text(
            "SELECT id, nome FROM employees WHERE coalesce(status,'')='ativo' "
            "AND length(regexp_replace(coalesce(cpf,''),'\\D','','g'))>=11 LIMIT 1"))).first()
        assert emp, "sem employee ativo com CPF"
        # tenant real que tem os templates disciplinares (submit gera doc do template do tenant)
        tid = (await db.execute(text("SELECT tenant_id FROM disciplinary_templates WHERE coalesce(is_active,true) LIMIT 1"))).scalar()
        # admin: o teste valida o FLUXO de aprovação, não a parede de escopo de equipe (testada
        # em test_escopo_equipe_operacional) — admin ignora o escopo e alcança qualquer colaborador.
        u = SimpleNamespace(id=uuid.uuid4(), name="Teste", email="t@conectapro.com.br",
                            role="admin", permissions=["*"],
                            condominio_id=None, tenant_id=str(tid) if tid else None)
        cre = await rd_action_medida_administrativa(current_user=u, payload={
            "employee_id": str(emp[0]), "action_type": "advertencia_escrita", "reason_category": "atraso",
            "reason_description": "Fluxo aprovacao — teste oraculo redesign", "incident_date": date.today().isoformat()}, db=db)
        aid = cre["id"]
        sub = await rd_action_medida_submeter(current_user=u, payload={"action_id": aid}, db=db)
        assert sub["ok"] and sub["status"] == "pendente_aprovacao", f"submeter: {sub}"
        apr = await rd_action_medida_aprovar(current_user=u, payload={"action_id": aid, "notes": "ok"}, db=db)
        # aprovar move a medida ADIANTE no fluxo real (aprovada OU pendente_assinatura se exige assinatura)
        assert apr["ok"] and apr["status"] in ("aprovada", "pendente_assinatura"), f"aprovar: {apr}"
        st = (await db.execute(text("SELECT status::text FROM disciplinary_actions WHERE id::text=:i"), {"i": aid})).scalar()
        assert st == apr["status"], f"banco {st} != retorno {apr['status']}"
        doc = await rd_action_medida_documento(current_user=u, payload={"action_id": aid}, db=db)
        assert doc.get("ok") and (doc.get("document_text") or doc.get("doc") or doc.get("document_hash") or doc.get("html")), f"documento vazio: {list(doc)}"
        await db.execute(text("DELETE FROM disciplinary_actions WHERE id::text=:i"), {"i": aid})
        await db.execute(text("DELETE FROM redesign_gate_otp WHERE ref LIKE 'idem:medida%'"))
        await db.commit()
        print(f"OK fluxo medida: {aid} rascunho->pendente->{apr['status']} (exibido==banco; criada+limpa)")


if __name__ == "__main__":
    asyncio.run(main())
