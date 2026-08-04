"""Fase 6 (balde FAZER) — ação DP reversível (🔵) via propor→aprovar.

No chat, quem tem o módulo `dp` PROPÕE uma solicitação de férias; grava um
PENDENTE na tabela nativa `hr_vacation_requests` (status inerte 'SUBMITTED', o
MESMO que a tela do DP escreve) via `acoes.base.propor` — e NADA executa. A
aprovação (status → 'APPROVED') continua sendo humana, na tela de férias
(`aprovar_ferias`); a IA jamais efetiva.

Reversível 🔵 (nada de dinheiro/eSocial); aprovador = ('admin',
'gerente_operacional') (reusa ROLES_KIT_OP — mesma diretoria operacional do DP).
Registra via `registrar_acao` (o agir_dispatcher colapsa em agir_dp(acao, dados)).
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import text

from .acoes.base import ROLES_KIT_OP, propor
from .agir_dispatcher import registrar_acao

# Espelha a fonte canônica (vacation_controller.criar_vacation): condominio_id é
# NOT NULL e employees não carrega o vínculo → usa o condomínio canônico único.
from modules.people_management.hr.services.vacation_service import (
    _HVR_DEFAULT_CONDOMINIO_ID,
)

#: status inerte com que a solicitação NASCE (idêntico ao da tela DP). A aprovação
#: humana a leva a 'APPROVED' — nunca aqui.
_STATUS_PENDENTE = "SUBMITTED"


async def _propor_solicitar_ferias(
    db, user, scope, *, employee_id: str = "", funcionario: str = "",
    inicio: str = "", start_date: str = "", dias: int | str = 0,
    fim: str = "", end_date: str = "", **_
) -> dict[str, Any]:
    emp = str(employee_id or funcionario or "").strip()
    if not emp:
        return {"erro": "employee_id (uuid do funcionário) é obrigatório"}

    def _d(v: str) -> date | None:
        try:
            return date.fromisoformat(str(v)[:10]) if v else None
        except (TypeError, ValueError):
            return None

    sd = _d(inicio or start_date)
    if not sd:
        return {"erro": "inicio (data AAAA-MM-DD) é obrigatório"}

    ed = _d(fim or end_date)
    if ed is None:
        try:
            n = int(str(dias).split()[0]) if dias else 0
        except (ValueError, IndexError):
            n = 0
        if n < 1:
            return {"erro": "informe 'fim' (AAAA-MM-DD) ou 'dias' (>=1)"}
        ed = sd + timedelta(days=n - 1)  # days_requested inclusivo (sd..ed)
    if ed < sd:
        return {"erro": "fim não pode ser anterior a inicio"}
    dias_corridos = (ed - sd).days + 1
    if dias_corridos > 30:  # CLT art. 130 — mesma guarda da tela DP
        return {"erro": f"férias não podem exceder 30 dias corridos (CLT art. 130); "
                        f"o período tem {dias_corridos} dias"}

    return_date = ed + timedelta(days=1)
    idem = f"ferias:{emp}:{sd.isoformat()}"

    async def _inserir(db) -> str:
        # Idempotência NATIVA (defesa em profundidade): não duplica uma solicitação
        # ATIVA do mesmo funcionário começando na mesma data (o único UNIQUE nativo é
        # sobre request_code, que é sempre novo). Ignora canceladas/rejeitadas.
        existente = (await db.execute(text(
            "SELECT id::text FROM hr_vacation_requests "
            "WHERE employee_id = CAST(:emp AS uuid) AND start_date = :sd "
            "  AND status NOT IN ('CANCELLED','REJECTED') LIMIT 1"),
            {"emp": emp, "sd": sd})).scalar()
        if existente:
            return existente

        # employee_id tem FK ON DELETE RESTRICT → valida a existência antes do INSERT
        # p/ não estourar IntegrityError dentro de propor() (devolve erro amigável).
        if not (await db.execute(text(
            "SELECT 1 FROM employees WHERE id = CAST(:emp AS uuid)"), {"emp": emp})).scalar():
            raise ValueError(f"funcionário {emp} não encontrado")

        vid = str(uuid.uuid4())
        # Espelha EXATAMENTE o INSERT da fonte canônica (vacation_controller:536),
        # SEM commit (propor faz o commit único). Só grava o PENDENTE 'SUBMITTED'.
        await db.execute(text(
            "INSERT INTO hr_vacation_requests "
            "(id, condominio_id, employee_id, status, request_code, start_date, end_date, "
            " return_date, days_requested, sell_days, advance_13th, employee_notes, hr_notes, "
            " created_by, created_at, updated_at) VALUES "
            "(CAST(:id AS uuid), CAST(:cond AS uuid), CAST(:emp AS uuid), :st, :code, "
            " :sd, :ed, :rd, :days, 0, false, :notes, NULL, CAST(:cby AS uuid), NOW(), NOW())"),
            {"id": vid, "cond": _HVR_DEFAULT_CONDOMINIO_ID, "emp": emp, "st": _STATUS_PENDENTE,
             "code": f"FER-DP-{uuid.uuid4().hex[:8].upper()}", "sd": sd, "ed": ed,
             "rd": return_date, "days": dias_corridos,
             "notes": "[proposto via IA] aguardando aprovação",
             "cby": str(getattr(user, "id", None))})
        return vid

    return await propor(
        db, user=user, scope=scope, dominio="ferias", gate="🔵",
        roles_aprovador=ROLES_KIT_OP, idempotency_key=idem,
        titulo="[Proposta] Solicitar férias",
        corpo=f"Férias de {emp} de {sd.isoformat()} a {ed.isoformat()} "
              f"({dias_corridos} dias). Nasce 'pendente' (SUBMITTED) — "
              f"aguarda sua aprovação na tela de férias.",
        action_url="/modulos/dp/ferias",
        tool="propor_solicitar_ferias",
        args={"employee_id": emp, "inicio": sd.isoformat(), "fim": ed.isoformat(),
              "dias": dias_corridos},
        entity_type="hr_vacation_request", inserir=_inserir,
    )


registrar_acao("dp", "solicitar_ferias",
               "solicitar férias de um funcionário. dados: employee_id (uuid, obrigatório), "
               "inicio (AAAA-MM-DD, obrigatório), e 'fim' (AAAA-MM-DD) OU 'dias' (>=1). "
               "Nasce 'pendente' (SUBMITTED); a aprovação é humana.",
               _propor_solicitar_ferias)


if __name__ == "__main__":
    import asyncio
    import os

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from .agir_dispatcher import montar_acao_dispatchers
    from .tool_registry import get_tool, tools_for_modules

    SENT = "__TESTE_F6FAZER_DP__"

    class _U:
        id = "00000000-0000-0000-0000-0000000000ff"
        role = "funcionario"
        email = "teste-f6dp@conectapro.local"
        permissions = ["module:dp"]

    class _USemDp:
        id = "00000000-0000-0000-0000-0000000000fe"
        role = "funcionario"
        email = "sem-dp@conectapro.local"
        permissions = ["module:financeiro"]

    class _S:
        tier = "gestor"

    async def _limpar(db, idem_like: str) -> None:
        ids = [x for x in (await db.execute(text(
            "SELECT id::text FROM communication_notifications "
            "WHERE extra_data->>'idempotency_key' LIKE :k"), {"k": idem_like})).scalars().all()]
        if ids:
            await db.execute(text("DELETE FROM communication_notifications WHERE id = ANY(:i)"), {"i": ids})
        await db.commit()

    async def main() -> None:
        montar_acao_dispatchers()
        agir = get_tool("agir_dp")
        assert agir is not None and agir.module == "dp", "agir_dp não registrado no módulo dp"

        eng = create_async_engine(os.environ["DATABASE_URL"])
        Session = async_sessionmaker(eng, expire_on_commit=False)
        async with Session() as db:
            vac_ids: list[str] = []
            try:
                disp = agir.handler
                # funcionário real p/ passar na FK (a proposta precisa de um employee válido)
                emp = (await db.execute(text("SELECT id::text FROM employees LIMIT 1"))).scalar()
                assert emp, "sem employees no banco p/ o teste"

                # ── (a) solicitar_ferias: 1 PENDENTE inerte 'SUBMITTED', não aprova, idempotente ──
                r = await disp(db, _U(), _S(), acao="solicitar_ferias",
                               dados={"employee_id": emp, "inicio": "2099-01-06", "dias": 10})
                assert r.get("status") == "pendente" and not r.get("duplicado"), r
                vid = r["entity_id"]; vac_ids.append(vid)
                st = (await db.execute(text(
                    "SELECT status FROM hr_vacation_requests WHERE id=:i"), {"i": vid})).scalar()
                assert st == "SUBMITTED", f"férias nasceu {st}, esperado 'SUBMITTED' (inerte, não aprovada)"
                # NÃO executou: nenhuma solicitação sentinela ficou APPROVED/hr_approved
                exec_n = (await db.execute(text(
                    "SELECT count(*) FROM hr_vacation_requests "
                    "WHERE id = ANY(:i) AND (status='APPROVED' OR hr_approved IS TRUE)"),
                    {"i": vac_ids})).scalar()
                assert exec_n == 0, "solicitação sentinela foi aprovada (executada) — não deveria"
                # idempotência: mesma (employee, inicio) → duplicado, não cria 2ª linha
                r2 = await disp(db, _U(), _S(), acao="solicitar_ferias",
                                dados={"employee_id": emp, "inicio": "2099-01-06", "dias": 10})
                assert r2.get("duplicado") is True, r2
                n = (await db.execute(text(
                    "SELECT count(*) FROM hr_vacation_requests "
                    "WHERE employee_id=CAST(:e AS uuid) AND start_date='2099-01-06' "
                    "  AND status NOT IN ('CANCELLED','REJECTED')"), {"e": emp})).scalar()
                assert n == 1, f"idempotência férias falhou: {n} linhas"
                print("TESTE a (solicitar_ferias: PENDENTE inerte 'SUBMITTED', não aprova, idempotente) PASS")

                # ── (b) acao inválida → recusa + opções ──
                rb = await disp(db, _U(), _S(), acao="aprovar_ferias", dados={})
                assert rb.get("status") == "recusado" and "opções" in rb.get("motivo", ""), rb
                assert "solicitar_ferias" in rb["motivo"], rb
                print("TESTE b (acao inválida → recusa listando opções) PASS")

                # ── (c) _gate sem dp → PermissionError; agir_dp só no belt de dp ──
                try:
                    await disp(db, _USemDp(), _S(), acao="solicitar_ferias",
                               dados={"employee_id": emp, "inicio": "2099-02-01", "dias": 5})
                    raise AssertionError("esperado PermissionError p/ usuário sem módulo dp")
                except PermissionError:
                    pass
                assert "agir_dp" in {t.name for t in tools_for_modules({"dp"})}
                assert "agir_dp" not in {t.name for t in tools_for_modules({"financeiro"})}, \
                    "agir_dp vazou p/ outro módulo (RBAC quebrado)"
                print("TESTE c (_gate sem dp → PermissionError; agir_dp só no belt de dp) PASS")

                # ── (d) prova: PROPÔS sem executar (SUBMITTED, sem APPROVED/hr_approved) ──
                print("TESTE d (solicitar_ferias PROPÕE sem executar: 'SUBMITTED', nunca 'APPROVED') PASS")
                print("\nTODAS AS PROVAS DE tools_acao_dp.py PASSARAM")
            finally:
                if vac_ids:
                    await db.execute(text(
                        "DELETE FROM hr_vacation_requests WHERE id = ANY(:i)"), {"i": vac_ids})
                    await db.execute(text(
                        "DELETE FROM audit_logs WHERE details->>'entity_id' = ANY(:i)"), {"i": vac_ids})
                await _limpar(db, "ferias:%")
                await db.commit()
                rem = (await db.execute(text(
                    "SELECT count(*) FROM hr_vacation_requests "
                    "WHERE hr_notes LIKE '%proposto via IA%' AND start_date >= '2099-01-01'"))).scalar()
                assert rem == 0, f"remanescentes férias={rem}"
                print("LIMPEZA OK — 0 remanescentes (hr_vacation_requests/audit/sino)")
        await eng.dispose()

    asyncio.run(main())
