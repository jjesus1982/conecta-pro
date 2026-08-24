"""Ação redesign: /action/medida-administrativa cria linha REAL em disciplinary_actions.
Chama a função do router diretamente (sem HTTP) com um current_user fake e confere no banco."""
import asyncio
import uuid
from datetime import date
from types import SimpleNamespace

from sqlalchemy import text

from core.database import async_session_factory
from modules.operacional.controllers.redesign_builders.operacional import rd_action_medida_administrativa


#: ZZ FIXO no motivo. Este oráculo cria uma ADVERTÊNCIA DISCIPLINAR na ficha de alguém e não
#: limpava NADA — nem entrada, nem saída. Entre 03/08 e 24/08 acumulou 26 das 31 linhas de
#: `disciplinary_actions` (84% da tabela), todas no mesmo colaborador.
#:
#: ⚠️ E ele escapou da trava de desmonte porque escreve pela CAMADA DE APLICAÇÃO
#: (`rd_action_medida_administrativa`), sem uma linha de SQL — a detecção por
#: INSERT/UPDATE/DELETE não o via. A trava foi corrigida junto.
_MARCA = "ZZAtraso reiterado — teste oráculo redesign"
_MARCAS_ANTIGAS = ("Atraso reiterado — teste oráculo redesign",)


async def _limpar_por_marca(db) -> int:
    """Apaga a advertência sintética por MARCA, nunca por id: a execução morta por sinal não
    deixa o id, e o órfão é justamente o que ficou de fora dele."""
    n = 0
    for marca in (_MARCA, *_MARCAS_ANTIGAS):
        r = await db.execute(text(
            "DELETE FROM disciplinary_actions WHERE reason_description = :m"), {"m": marca})
        n += r.rowcount or 0
    await db.execute(text("DELETE FROM redesign_gate_otp WHERE ref LIKE 'idem:medida%'"))
    await db.commit()
    return n


async def main() -> None:
    async with async_session_factory() as db:
        # ENTRADA: varre o que ficou de execuções anteriores (inclusive as 26 sem marca ZZ).
        _orf = await _limpar_por_marca(db)
        if _orf:
            print(f"entrada: {_orf} advertência(s) de teste órfã(s) removida(s)")
        emp = (await db.execute(text(
            "SELECT id, nome FROM employees WHERE coalesce(status,'')='ativo' "
            "AND length(regexp_replace(coalesce(cpf,''), '\\D', '', 'g')) >= 11 LIMIT 1"))).first()
        assert emp, "sem employee ativo com CPF p/ testar"
        # admin: valida a CRIAÇÃO da medida, não a parede de escopo (testada em test_escopo_equipe_operacional)
        user = SimpleNamespace(id=uuid.uuid4(), role="admin", permissions=["*"], condominio_id=None, tenant_id=None)
        payload = {"action_type": "advertencia_escrita", "employee_id": str(emp[0]),
                   "reason_category": "atraso",
                   "reason_description": _MARCA,
                   "incident_date": date.today().isoformat()}
        res = await rd_action_medida_administrativa(current_user=user, payload=payload, db=db)
        assert res.get("ok") and res.get("id"), f"ação não retornou ok/id: {res}"
        row = (await db.execute(
            text("SELECT employee_name, status::text FROM disciplinary_actions WHERE id::text=:i"),
            {"i": str(res["id"])})).first()
        assert row and row[0] == (emp[1] or "—"), f"linha não persistiu com nome real: {row}"
        print(f"OK ação: criou disciplinary_action id={res['id']} nome={row[0]} status={row[1]}")
        # SAÍDA: advertência é documento na ficha de uma pessoa — não pode sobrar nem uma.
        await _limpar_por_marca(db)


if __name__ == "__main__":
    asyncio.run(main())
