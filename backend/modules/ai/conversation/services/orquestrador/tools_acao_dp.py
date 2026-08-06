"""Fase 6 (balde FAZER) — ações DP via propor→aprovar.

No chat, quem tem o módulo `dp` PROPÕE. A `propor()` NUNCA executa: grava só um
PENDENTE + entrega no sino ao aprovador + audita. A execução real fica sempre na
TELA humana (com o gate/OTP da tela).

Duas naturezas convivem aqui:

1. REVERSÍVEL 🔵 — `solicitar_ferias`: grava um PENDENTE na tabela nativa
   `hr_vacation_requests` (status inerte 'SUBMITTED', o MESMO que a tela escreve);
   a aprovação (→'APPROVED') é humana na tela de férias. Aprovador =
   ROLES_KIT_OP ('admin','gerente_operacional').

2. PESADAS (diretoria) — `calcular_folha` (🟡), `fechar_folha` (🔴 IRREVERSÍVEL,
   habilita pagamento/eSocial) e `concluir_admissao` (🔴 cria vínculo/eSocial).
   Não há tabela de proposta nativa onde encaixar um PENDENTE inerte — o pendente
   vive INTEIRAMENTE no sino+auditoria (idempotência nativa do `propor`, como o
   GED faz com o kit JSON). `_inserir` só devolve um id sintético e NÃO toca a
   folha/admissão: a IA NUNCA chama PayrollService/AdmissionService. Aprovador =
   ROLES_MONEY (diretoria). action_url → a tela onde o humano executa (gate/OTP).
   # ponytail: o gate 🟠 do brief não existe no set de `base.GATES` (🔴/🟡/🔵);
   # mapeado p/ o gate válido mais honesto (fechar/admissão=🔴, calcular=🟡).

Registra via `registrar_acao` (o agir_dispatcher colapsa em agir_dp(acao, dados)).
"""
from __future__ import annotations

import re
import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import text

from .acoes.base import ROLES_KIT_OP, ROLES_MONEY, propor
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


# ──────────────────────────────────────────────────────────────────────────────
# Ações PESADAS (diretoria): folha (calcular/fechar) e admissão. propor() só cria
# o PENDENTE no sino+audit; a EXECUÇÃO real fica na tela (gate/OTP). A IA NUNCA
# chama PayrollService/AdmissionService — `_inserir` só devolve um id sintético.
# ──────────────────────────────────────────────────────────────────────────────

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def _periodo(mes, ano) -> tuple[int, int] | None:
    try:
        m = int(str(mes).split()[0])
        a = int(str(ano).split()[0])
    except (TypeError, ValueError, IndexError):
        return None
    if not (1 <= m <= 12) or not (2000 <= a <= 2100):
        return None
    return m, a


async def _noop_ref(db) -> str:
    """PENDENTE sem tabela nativa: só devolve id sintético (pendente vive no
    sino+audit). NÃO escreve na folha/admissão — a IA nunca executa."""
    return str(uuid.uuid4())


async def _propor_calcular_folha(
    db, user, scope, *, mes="", ano="", month="", year="", **_
) -> dict[str, Any]:
    per = _periodo(mes or month, ano or year)
    if not per:
        return {"erro": "mes (1-12) e ano (AAAA) são obrigatórios"}
    m, a = per
    return await propor(
        db, user=user, scope=scope, dominio="folha_calcular", gate="🟡",
        roles_aprovador=ROLES_MONEY, idempotency_key=f"folha_calc:{a}-{m:02d}",
        titulo="[Proposta] Calcular folha",
        corpo=f"Aprovar DISPARA o CÁLCULO da folha de {m:02d}/{a} na tela de folha — "
              f"revise proventos/descontos antes. Nada é calculado até você aprovar.",
        action_url="/modulos/dp/folha",
        tool="propor_calcular_folha", args={"mes": m, "ano": a},
        entity_type="hr_folha_calculo", inserir=_noop_ref,
    )


async def _propor_fechar_folha(
    db, user, scope, *, mes="", ano="", month="", year="", **_
) -> dict[str, Any]:
    per = _periodo(mes or month, ano or year)
    if not per:
        return {"erro": "mes (1-12) e ano (AAAA) são obrigatórios"}
    m, a = per
    return await propor(
        db, user=user, scope=scope, dominio="folha_fechar", gate="🔴",
        roles_aprovador=ROLES_MONEY, idempotency_key=f"folha_fecha:{a}-{m:02d}",
        titulo="[Proposta] FECHAR folha (irreversível)",
        corpo=f"Aprovar FECHA a folha de {m:02d}/{a} na tela — operação IRREVERSÍVEL "
              f"que habilita PAGAMENTO e a transmissão eSocial (S-1200). Confira TUDO "
              f"antes; nada é fechado até você aprovar (gate/OTP na tela).",
        action_url="/modulos/dp/folha",
        tool="propor_fechar_folha", args={"mes": m, "ano": a},
        entity_type="hr_folha_fechamento", inserir=_noop_ref,
    )


async def _propor_concluir_admissao(
    db, user, scope, *, admission_id="", admissao="", candidato="", **_
) -> dict[str, Any]:
    aid = str(admission_id or admissao or candidato or "").strip()
    if not _UUID_RE.match(aid):
        return {"erro": "admission_id (uuid do processo de admissão) é obrigatório"}
    return await propor(
        db, user=user, scope=scope, dominio="admissao_concluir", gate="🔴",
        roles_aprovador=ROLES_MONEY, idempotency_key=f"admissao_concluir:{aid}",
        titulo="[Proposta] Concluir admissão",
        corpo=f"Aprovar CONCLUI a admissão {aid} na tela — cria o VÍNCULO do funcionário "
              f"e habilita eventos eSocial (S-2200)/folha. Nada é concluído até você "
              f"aprovar na tela de admissão.",
        action_url="/modulos/dp/admissao",
        tool="propor_concluir_admissao", args={"admission_id": aid},
        entity_type="admission_process", inserir=_noop_ref,
    )


registrar_acao("dp", "calcular_folha",
               "PROPOR o cálculo da folha de um período (aprovação = diretoria). dados: "
               "mes (1-12, obrig.), ano (AAAA, obrig.). NÃO calcula — a execução é humana "
               "na tela de folha.",
               _propor_calcular_folha)
registrar_acao("dp", "fechar_folha",
               "PROPOR o FECHAMENTO (IRREVERSÍVEL) da folha de um período — habilita "
               "pagamento/eSocial (aprovação = diretoria). dados: mes (1-12, obrig.), "
               "ano (AAAA, obrig.). NÃO fecha — a execução é humana na tela (gate/OTP).",
               _propor_fechar_folha)
registrar_acao("dp", "concluir_admissao",
               "PROPOR a conclusão de um processo de admissão — cria vínculo/eSocial "
               "(aprovação = diretoria). dados: admission_id (uuid, obrig.). NÃO conclui — "
               "a execução é humana na tela de admissão.",
               _propor_concluir_admissao)


# ═════════════════ CAPTURA (F1) — propor REGISTRAR o que caiu fora ═════════════════
# LEI: captura ≥ vigília. O watcher `dp_desligamento_sem_processo` achou 9 pessoas com
# data de desligamento no cadastro e SEM processo de rescisão — o caso Keyson: o
# desligamento existia no mundo (e no quadro da parede) e não no sistema, então não havia
# aviso prévio para vigiar. Estas ações fecham o buraco de NASCIMENTO do dado, sempre
# pela porta oficial (TerminationService.create_termination, a mesma da tela).

async def _propor_registrar_desligamento(
    db, user, scope, *, employee_id: str = "", funcionario: str = "",
    tipo: str = "", aviso_dias: int | str = 0, **_
) -> dict[str, Any]:
    """PROPÕE abrir o processo de rescisão de quem já tem desligamento no cadastro.

    Evidência ESPECÍFICA (nunca genérica): a data vem de `employees.data_desligamento`,
    o fato de não haver processo vem de um NOT EXISTS em `termination_processes`.
    Honestidade do não-derivável: o TIPO da rescisão (sem justa causa / pedido de demissão
    / justa causa) e os dias de aviso NÃO são deriváveis do cadastro — o rascunho nasce
    com o campo em aberto e pede confirmação, em vez de chutar.
    """
    emp = str(employee_id or funcionario or "").strip()
    if not emp:
        return {"erro": "employee_id (uuid do funcionário) é obrigatório"}
    try:
        uuid.UUID(emp)
    except (ValueError, AttributeError, TypeError):
        return {"erro": "employee_id inválido (esperado uuid)"}

    row = (await db.execute(text(
        "SELECT e.nome, coalesce(e.data_desligamento, e.data_demissao) AS dt, "
        "       EXISTS (SELECT 1 FROM termination_processes t WHERE t.employee_id = e.id) AS tem "
        "FROM employees e WHERE CAST(e.id AS TEXT) = :e"
    ), {"e": emp})).mappings().first()
    if not row:
        return {"erro": "funcionário não encontrado"}
    if not row["dt"]:
        return {"erro": "esse funcionário não tem data de desligamento no cadastro — "
                        "nada a capturar (não invento desligamento)"}
    if row["tem"]:
        return {"erro": "já existe processo de rescisão para esse funcionário"}

    # tipo é do DP, não do agente: sem valor confiável o rascunho pede confirmação
    tipo_norm = (tipo or "").strip().lower() or None
    try:
        dias = int(str(aviso_dias).split()[0]) if aviso_dias else 0
    except (ValueError, IndexError):
        dias = 0

    async def _inserir(_db) -> str:
        from modules.people_management.hr.services.termination_service import TerminationService

        svc = TerminationService(_db)
        proc = await svc.create_termination(
            {"employee_id": emp,
             "type": tipo_norm or "sem_justa_causa",
             "termination_date": str(row["dt"]),
             **({"notice_period_days": dias, "notice_start_date": str(row["dt"])} if dias else {})},
            created_by_id=getattr(user, "id", None),
        )
        return str(proc.id)

    falta = [] if tipo_norm else ["tipo da rescisão"]
    if not dias:
        falta.append("dias de aviso prévio")
    aviso = (f" ⚠️ CONFIRME antes de aprovar: {', e '.join(falta)} — não é derivável do "
             f"cadastro e eu não chuto.") if falta else ""

    return await propor(
        db, user=user, scope=scope, dominio="rescisao_registrar", gate="🔴",
        roles_aprovador=ROLES_MONEY,  # rescisão gera verba: aprovação de diretoria
        idempotency_key=f"dp:registrar_desligamento:{emp}",
        titulo=f"Registrar rescisão: {row['nome']}",
        corpo=(f"{row['nome']} tem desligamento em {row['dt']} no cadastro, mas NÃO há "
               f"processo de rescisão no sistema — por isso o aviso prévio dele não está "
               f"sendo vigiado, e o TRCT e o eSocial S-2299 não nascem.{aviso}"),
        action_url="/redesign/aprovacoes",
        tool="propor_registrar_desligamento",
        args={"employee_id": emp, "tipo": tipo_norm, "aviso_dias": dias},
        entity_type="termination_process",
        inserir=_inserir,
    )


registrar_acao("dp", "registrar_desligamento",
               "PROPOR abrir o processo de rescisão de quem JÁ tem data de desligamento no "
               "cadastro e não tem processo (fecha o buraco que deixou o aviso prévio sem "
               "vigia). dados: employee_id (uuid, obrig.), tipo (opcional), aviso_dias "
               "(opcional). NÃO abre — a execução é a aprovação humana.",
               _propor_registrar_desligamento)



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

        # PROVA "não executa" (ações pesadas): se o caminho tocar QUALQUER executor
        # real (calcular/fechar folha, concluir admissão), estoura. Nunca é chamado.
        from modules.notifications.proativo import entrega
        import modules.people_management.hr.services.payroll_service as _pay
        import modules.people_management.hr.services.admission_service as _adm
        executou = {"n": 0}

        def _boom(nome):
            async def _b(*a, **k):
                executou["n"] += 1
                raise AssertionError(f"executor real {nome} NÃO pode ser chamado pela IA")
            return _b
        _orig = (_pay.PayrollService.close_payroll,
                 _pay.PayrollService.calculate_employee_payroll,
                 _adm.AdmissionService.complete_admission)
        _pay.PayrollService.close_payroll = _boom("close_payroll")
        _pay.PayrollService.calculate_employee_payroll = _boom("calculate_employee_payroll")
        _adm.AdmissionService.complete_admission = _boom("complete_admission")

        eng = create_async_engine(os.environ["DATABASE_URL"])
        Session = async_sessionmaker(eng, expire_on_commit=False)
        async with Session() as db:
            vac_ids: list[str] = []
            heavy_ids: list[str] = []
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

                # ── (a-pesadas) calcular/fechar folha + concluir admissão: PENDENTE p/
                #    DIRETORIA (ROLES_MONEY), pendente vive no sino, executor nunca roda,
                #    idempotente por período/admissão. Sentinela 2099 → não colide c/ dado real.
                admins = set(await entrega.resolver_usuarios_por_roles(db, ("admin",)))
                assert admins, "esperado >=1 admin (diretoria) no banco"
                pesadas = [
                    ("calcular_folha", {"mes": 1, "ano": 2099}, "folha_calc:2099-01"),
                    ("fechar_folha", {"mes": 1, "ano": 2099}, "folha_fecha:2099-01"),
                    ("concluir_admissao",
                     {"admission_id": "00000000-0000-0000-0000-00000000a099"},
                     "admissao_concluir:00000000-0000-0000-0000-00000000a099"),
                ]
                for acao, dados, idem in pesadas:
                    r = await disp(db, _U(), _S(), acao=acao, dados=dados)
                    assert r.get("status") == "pendente" and not r.get("duplicado"), (acao, r)
                    # aprovador = diretoria (admins), propositor (0xff, não-admin) preservados
                    assert set(r.get("aprovadores") or []) == admins, (acao, r.get("aprovadores"), admins)
                    heavy_ids.append(r["entity_id"])
                    # pendente vive no sino como proposta_acao (não há tabela nativa)
                    rt = (await db.execute(text(
                        "SELECT reference_type FROM communication_notifications "
                        "WHERE extra_data->>'idempotency_key' = :k LIMIT 1"), {"k": idem})).scalar()
                    assert rt == "proposta_acao", (acao, rt)
                    # idempotência por período/admissão: 2ª chamada idêntica → duplicado
                    r2 = await disp(db, _U(), _S(), acao=acao, dados=dados)
                    assert r2.get("duplicado") is True, (acao, r2)
                    n = (await db.execute(text(
                        "SELECT count(*) FROM communication_notifications "
                        "WHERE extra_data->>'idempotency_key' = :k"), {"k": idem})).scalar()
                    assert n == len(admins), (acao, n, len(admins))
                assert executou["n"] == 0, "algum executor real da folha/admissão foi chamado"
                print("TESTE a-pesadas (calcular/fechar folha + concluir admissão: PENDENTE "
                      "p/ DIRETORIA, executor NUNCA roda, idempotente) PASS")

                # dados inválidos das pesadas → recusa (não vira pendente)
                assert "erro" in await disp(db, _U(), _S(), acao="calcular_folha", dados={"mes": 13, "ano": 2099})
                assert "erro" in await disp(db, _U(), _S(), acao="concluir_admissao", dados={"admission_id": "nao-uuid"})
                print("TESTE a-pesadas2 (mes/uuid inválido → recusa, sem pendente) PASS")

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

                # ── (d) prova: PROPÔS sem executar (ferias 'SUBMITTED' sem APPROVED;
                #    pesadas: nenhum executor de folha/admissão foi chamado) ──
                assert executou["n"] == 0, "executor real rodou (a IA executou algo pesado)"
                print("TESTE d (PROPÕE sem executar: férias 'SUBMITTED' nunca 'APPROVED'; "
                      "folha/admissão nunca calculada/fechada/concluída) PASS")
                print("\nTODAS AS PROVAS DE tools_acao_dp.py PASSARAM")
            finally:
                _pay.PayrollService.close_payroll = _orig[0]
                _pay.PayrollService.calculate_employee_payroll = _orig[1]
                _adm.AdmissionService.complete_admission = _orig[2]
                if vac_ids:
                    await db.execute(text(
                        "DELETE FROM hr_vacation_requests WHERE id = ANY(:i)"), {"i": vac_ids})
                    await db.execute(text(
                        "DELETE FROM audit_logs WHERE details->>'entity_id' = ANY(:i)"), {"i": vac_ids})
                if heavy_ids:  # pesadas só deixam rastro em sino+audit (sem tabela nativa)
                    await db.execute(text(
                        "DELETE FROM audit_logs WHERE details->>'entity_id' = ANY(:i)"), {"i": heavy_ids})
                await _limpar(db, "ferias:%")
                for k in ("folha_calc:%", "folha_fecha:%", "admissao_concluir:%"):
                    await _limpar(db, k)
                await db.commit()
                rem = (await db.execute(text(
                    "SELECT count(*) FROM hr_vacation_requests "
                    "WHERE hr_notes LIKE '%proposto via IA%' AND start_date >= '2099-01-01'"))).scalar()
                rem_h = (await db.execute(text(
                    "SELECT count(*) FROM communication_notifications WHERE "
                    "extra_data->>'idempotency_key' LIKE 'folha_%' "
                    "OR extra_data->>'idempotency_key' LIKE 'admissao_concluir:%'"))).scalar()
                assert rem == 0 and rem_h == 0, f"remanescentes férias={rem} pesadas={rem_h}"
                print("LIMPEZA OK — 0 remanescentes (hr_vacation_requests/audit/sino/pesadas)")
        await eng.dispose()

    asyncio.run(main())
