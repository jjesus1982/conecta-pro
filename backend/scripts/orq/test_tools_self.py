"""Prova: CLT Celiane vê o PRÓPRIO ponto/holerite/escala (dados reais); um escopo self de
outro colaborador nunca retorna o dela (e vice-versa); escopo sem employee_id => aguardando
dado; injeção de employee_id como kwarg é IMPOSSÍVEL (TypeError — não é parâmetro aceito)."""
import asyncio

from sqlalchemy import text

from core.database import async_session_factory
from modules.ai.conversation.services.orquestrador.engine import OrqScope
from modules.ai.conversation.services.orquestrador import tool_registry as tr
from modules.ai.conversation.services.orquestrador import tools_self  # noqa: F401 — registra

CELIANE_EMP = "9e9e1678-9988-490c-b59b-b2786bb67e1c"


async def main() -> None:
    async with async_session_factory() as db:
        ponto = tr.get_tool("meu_ponto")
        holerite = tr.get_tool("meu_holerite")
        escala = tr.get_tool("minha_escala")

        # 1) escopo self da Celiane -> retorna batidas dela (a tabela tem 196 no total dela)
        total = (await db.execute(text(
            "SELECT count(*) FROM gp_clock_punches WHERE employee_id = :e"
        ), {"e": CELIANE_EMP})).scalar()
        assert total and total > 0, "Celiane precisa ter batidas para este teste"
        out = await ponto.handler(db, None, OrqScope(tier="clt", employee_id=CELIANE_EMP), mes=None, ano=None)
        assert "total_batidas" in out, out
        print(f"OK CLT vê o próprio ponto (total histórico da colaboradora: {total})")

        # 1b) o mês/ano DEFAULT vem do dia civil de MANAUS (SQL), nunca de utcnow() — a
        # contagem retornada tem de bater com a contagem real do banco p/ o mês resolvido.
        esperado = (await db.execute(text(
            "SELECT count(*) FROM gp_clock_punches WHERE employee_id = :e "
            "AND extract(month FROM punch_timestamp) = :m AND extract(year FROM punch_timestamp) = :a"
        ), {"e": CELIANE_EMP, "m": out["mes"], "a": out["ano"]})).scalar()
        assert out["total_batidas"] == esperado, (out["total_batidas"], esperado)
        print(f"OK mês/ano default (Manaus) = {out['mes']:02d}/{out['ano']}, contagem bate com o banco ({esperado})")

        # 2) escopo SEM employee_id -> aguardando dado (nunca lê de outro)
        out2 = await ponto.handler(db, None, OrqScope(tier="clt", employee_id=None))
        assert out2.get("status") == "aguardando dado", out2
        out2h = await holerite.handler(db, None, OrqScope(tier="clt", employee_id=None))
        assert out2h.get("status") == "aguardando dado", out2h
        out2e = await escala.handler(db, None, OrqScope(tier="clt", employee_id=None))
        assert out2e.get("status") == "aguardando dado", out2e
        print("OK sem employee_id => aguardando dado (ponto/holerite/escala)")

        # 3) o handler ignora um employee_id passado como argumento (não existe esse param)
        outro = (await db.execute(text(
            "SELECT employee_id::text FROM gp_clock_punches WHERE employee_id <> :e LIMIT 1"
        ), {"e": CELIANE_EMP})).scalar()
        assert outro, "precisa existir >=1 batida de outro colaborador p/ este teste"
        barrou = False
        try:
            await ponto.handler(db, None, OrqScope(tier="clt", employee_id=CELIANE_EMP), employee_id=outro)  # type: ignore[call-arg]
        except TypeError:
            barrou = True  # 'employee_id' não é parâmetro aceito → impossível cruzar por argumento
        assert barrou, "handler self não deveria aceitar employee_id por argumento"
        print("OK impossível cruzar para outro colaborador por argumento")

        # 4) PROVA DO NEGATIVO (conteúdo, não só forma): o escopo self de OUTRO colaborador
        # retorna SÓ os postos/horários dele — nunca os dela — e vice-versa.
        out_outro = await ponto.handler(db, None, OrqScope(tier="clt", employee_id=outro), mes=out["mes"], ano=out["ano"])
        batidas_outro = {(b["quando"], b["tipo"]) for b in out_outro["batidas"]}
        batidas_celiane = {(b["quando"], b["tipo"]) for b in out["batidas"]}
        assert not (batidas_outro & batidas_celiane), "vazamento: batida cruzada entre colaboradores"
        print(f"OK escopo do outro colaborador ({outro}) não contém nenhuma batida da Celiane, e vice-versa")

        # 5) meu_holerite — bruto/líquido reais, isolados por employee_id (colunas ajustadas:
        # hr_payslips não tem 'competencia'/'gross_salary'; usa reference_period/total_earnings,
        # mesmo cálculo do PayslipPortalService do portal clássico).
        n_holerites = (await db.execute(text(
            "SELECT count(*) FROM hr_payslips WHERE employee_id = :e"
        ), {"e": CELIANE_EMP})).scalar() or 0
        out_hol = await holerite.handler(db, None, OrqScope(tier="clt", employee_id=CELIANE_EMP))
        assert len(out_hol["holerites"]) == min(n_holerites, 12), out_hol
        if out_hol["holerites"]:
            assert all(h["competencia"] and h["liquido"] >= 0 for h in out_hol["holerites"]), out_hol
        print(f"OK meu_holerite: {len(out_hol['holerites'])} holerite(s) reais da Celiane ({n_holerites} no banco)")

        # 6) minha_escala — só a(s) alocação(ões) ATIVA(S) dela.
        n_aloc = (await db.execute(text(
            "SELECT count(*) FROM allocations WHERE employee_id = :e AND status ILIKE 'ACTIVE%'"
        ), {"e": CELIANE_EMP})).scalar() or 0
        out_esc = await escala.handler(db, None, OrqScope(tier="clt", employee_id=CELIANE_EMP))
        assert len(out_esc["alocacoes_ativas"]) == n_aloc, out_esc
        print(f"OK minha_escala: {len(out_esc['alocacoes_ativas'])} alocação(ões) ativa(s) da Celiane ({n_aloc} no banco)")
    print("TEST tools_self PASS")


if __name__ == "__main__":
    asyncio.run(main())
