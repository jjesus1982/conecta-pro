"""Redesign builder — Departamento Pessoal.

Estende o `_build_dp` do monólito (base: visão, funcionários, folha, rubricas,
férias, benefícios, rescisão + ferramentas) e LIGA as 10 telas que estavam
sem wiring, lendo SEMPRE as MESMAS tabelas clássicas (dado real; vazio-real =
"aguardando dado", nunca mock).

Telas novas: admissao · aviso-previo · ponto · fechamento-ponto · licencas ·
reembolsos · contratos · documentos · certificacao · esocial.
"""

from fastapi import APIRouter, Body, Depends, HTTPException

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from core.database.session import get_sync_db_dependency
from modules.operacional.controllers.redesign_data_controller import (
    _build_dp,
    _helpers,
    b,
    brl,
    doc,
    initials,
    t,
)

SLUG = "departamento-pessoal"

router = APIRouter()


@router.post("/action/ponto-ajuste")
async def rd_action_ponto_ajuste(
    current_user: CurrentActiveUser,
    eid: str,
    dia: str,
    payload: dict = Body(...),
    db=Depends(get_sync_db_dependency),
) -> dict:
    """Ajuste de ponto do DP — grava batida REAL via o serviço existente (POST /ponto/ajuste).

    `ajustado_por` é a identidade REAL do usuário logado, nunca um rótulo chumbado.
    `eid`/`dia` vêm da LINHA da tabela (não do usuário) — o operador só informa tipo, hora
    e motivo. Valida antes de chamar o service (evita 500 por payload incompleto).
    """
    punch_type = (payload.get("punch_type") or "").strip().lower()
    hora = (payload.get("hora") or "").strip()
    motivo = (payload.get("motivo") or "").strip()
    if punch_type not in ("entrada", "saida"):
        raise HTTPException(status_code=422, detail="Tipo deve ser 'entrada' ou 'saida'.")
    if len(motivo) < 5:
        raise HTTPException(status_code=422, detail="O motivo precisa de ao menos 5 caracteres.")
    if not (len(hora) == 5 and hora[2] == ":" and hora[:2].isdigit() and hora[3:].isdigit()):
        raise HTTPException(status_code=422, detail="Hora inválida — use HH:MM.")

    from modules.people_management.ponto.services import dashboard_service as _ponto_svc

    # Mesmo payload que o controller real monta (AjusteRequest.model_dump()).
    res = _ponto_svc.registrar_ajuste(db, {
        "employee_id": eid,
        "data": dia,
        "punch_type": punch_type,
        "timestamp": f"{dia}T{hora}:00",
        "motivo": motivo,
        "ajustado_por": str(current_user.id),  # identidade real do usuário logado
    })
    return {"ok": True, "resultado": res, "message": "Ajuste de ponto registrado"}


def _cpf_valido(d: str) -> bool:
    """Dígitos verificadores do CPF. Desambigua 11 dígitos: CPF e celular com DDD têm o
    MESMO tamanho (92991934389 é telefone, 02368354247 é CPF) — só o DV separa."""
    if len(d) != 11 or d == d[0] * 11:
        return False
    for corte in (9, 10):
        soma = sum(int(d[i]) * (corte + 1 - i) for i in range(corte))
        dv = (soma * 10) % 11
        if dv == 10:
            dv = 0
        if dv != int(d[corte]):
            return False
    return True


def _tipo_pix(chave: str | None, guardado: str | None = None) -> str:
    """Tipo REAL da chave, pelo formato. O tipo guardado no cadastro mente (o Ediney tem
    pix_key_type='CPF' sem chave nenhuma), então o formato manda e o guardado só desempata."""
    c = (chave or "").strip()
    if not c:
        return "—"
    if "@" in c:
        return "E-mail"
    if "-" in c and len(c) >= 32:
        return "Aleatória"
    d = "".join(ch for ch in c if ch.isdigit())
    if c.startswith("+") or (len(d) in (12, 13) and d.startswith("55")):
        return "Telefone"
    if len(d) == 14:
        return "CNPJ"
    if len(d) == 11:
        return "CPF" if _cpf_valido(d) else "Telefone"
    if len(d) == 10:
        return "Telefone"
    g = (guardado or "").strip().upper()
    if g in ("CPF", "CNPJ", "EMAIL", "E-MAIL", "TELEFONE", "EVP"):
        return {"EMAIL": "E-mail", "E-MAIL": "E-mail", "EVP": "Aleatória"}.get(g, g.capitalize()
                if g in ("CPF", "CNPJ") else g.title())
    return "Outro"


def _require_dp_dep(current_user: CurrentActiveUser) -> None:
    """Trava de cargo p/ GERAR folha: salário é dado sensível (LGPD) e a folha alimenta
    pagamento. Só quem tem module:people-management / financeiro (ou admin/all)."""
    from core.auth.module_scope import user_has_module
    if not (user_has_module(current_user, "people-management") or user_has_module(current_user, "financeiro")):
        raise HTTPException(status_code=403, detail="Gerar folha é restrito ao DP/Financeiro.")


@router.post("/action/cadastrar-pix-key", dependencies=[Depends(_require_dp_dep)])
async def rd_action_cadastrar_pix_key(
    current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db),
) -> dict:
    """Cadastra/atualiza a chave PIX do funcionário — DESTINO DO SALÁRIO, gate OTP humano.

    Não existia caminho nenhum no redesign: o form de Funcionários não tem campo de chave e
    o PATCH de employees não aceita pix_key. Resultado: era impossível cadastrar chave pela
    tela, e o Jordan ficou tentando num campo que eu disse existir e não existia.

    2 fases, mesmo padrão do resto do money-gated: sem otp_code → gera o código (e-mail ao
    Jordan) e devolve otp_required; com otp_code → grava. Delega aos endpoints provados, que
    validam e CONSOMEM o OTP — não reimplemento validação de código.
    """
    from modules.people_management.employee_portal.controllers.dp_payslips_controller import (
        cadastrar_pix_key, gerar_otp_pix_key,
    )

    eid = (payload.get("employee_id") or "").strip()
    if not eid:
        raise HTTPException(status_code=422, detail="Selecione o colaborador.")
    chave = (payload.get("pix_key") or "").strip()
    if len(chave) < 5:
        raise HTTPException(status_code=422, detail="Informe a chave PIX.")
    tipo = (payload.get("pix_key_type") or "").strip().upper() or _tipo_pix(chave).upper()
    tipo = {"E-MAIL": "EMAIL", "ALEATÓRIA": "ALEATORIA", "TELEFONE": "TELEFONE",
            "CPF": "CPF", "CNPJ": "CNPJ"}.get(tipo, tipo)

    otp_code = (payload.get("otp_code") or "").strip()
    lote_id = (payload.get("_gate_ref") or "").strip()
    if not otp_code:
        r = await gerar_otp_pix_key(eid, db=db, _user=current_user)
        if not r.get("ok"):
            raise HTTPException(status_code=400, detail=r.get("mensagem") or "Não foi possível gerar o código.")
        return {"otp_required": True, "ref": r.get("lote_id", ""),
                "message": (f"Chave {chave} ({tipo}) — trocar a chave redireciona o SALÁRIO. "
                            "Confirme com o código enviado ao e-mail do Jordan.")}

    r = await cadastrar_pix_key(eid, pix_key=chave, pix_key_type=tipo, otp_code=otp_code,
                                lote_id=lote_id or None, db=db, _user=current_user)
    if r.get("otp_invalido") or r.get("otp_requerido"):
        raise HTTPException(status_code=400, detail=r.get("mensagem") or "Código inválido ou obrigatório.")
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=r.get("mensagem") or "Não foi possível cadastrar a chave.")
    return {"ok": True, "message": f"Chave PIX cadastrada: {chave} ({tipo}). Recarregue a tela."}


@router.post("/action/folha-gerar", dependencies=[Depends(_require_dp_dep)])
async def rd_action_folha_gerar(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db=Depends(get_sync_db_dependency),
) -> dict:
    """GERA a folha do mês no Conecta PRO e GRAVA em hr_payslips (source_system='conecta').

    O `close_payroll` do hr NÃO persistia nada (calculava, publicava evento e devolvia
    "closed" — nenhuma linha gravada), então não havia caminho real de gerar folha aqui.
    Esta ação usa o MESMO motor da tela de folha (`calcular_folha_batch`, que lê ponto REAL
    do Sólides via horas_reais_ponto) e persiste o resultado.

    INTOCÁVEL: só mexe nas linhas source_system='conecta'. As linhas 'portte' (espelho
    jan-jun, fonte da verdade no pareamento de 6 meses) nunca são lidas para escrita nem
    apagadas. Regerar a mesma competência é idempotente: apaga a versão 'conecta' anterior
    daquele mês e reescreve.

    Grava em status='draft': gerar != pagar. O pagamento continua no Financeiro com OTP.
    """
    from datetime import date

    from sqlalchemy import text as _sql

    try:
        mes = int(str(payload.get("mes") or "").strip())
        ano = int(str(payload.get("ano") or "").strip())
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Informe mês (1-12) e ano (AAAA).")
    if not (1 <= mes <= 12) or not (2020 <= ano <= 2100):
        raise HTTPException(status_code=422, detail="Mês (1-12) ou ano (AAAA) fora do intervalo.")
    cond_sel = (payload.get("condominio_id") or "").strip() or None

    from modules.people_management.folha.services.calculo_service import calcular_folha_batch

    batch = calcular_folha_batch(db, mes, ano)
    holerites = batch.get("holerites") or []
    if not holerites:
        raise HTTPException(status_code=400, detail=f"Nenhum holerite calculado para {mes:02d}/{ano}.")

    # condomínio vigente na competência + empresa, por funcionário (1 query, não N)
    comp_ini = date(ano, mes, 1)
    comp_fim = date(ano + (mes // 12), (mes % 12) + 1, 1) - __import__("datetime").timedelta(days=1)
    vinc = {
        str(r[0]): (str(r[1]) if r[1] else None, str(r[2]) if r[2] else None)
        for r in db.execute(_sql(
            "SELECT CAST(e.id AS TEXT), "
            "  (SELECT a.condominio_id FROM employee_alocacoes a WHERE a.employee_id = e.id "
            "     AND a.data_inicio <= :fim AND (a.data_fim IS NULL OR a.data_fim >= :ini) "
            "   ORDER BY a.data_inicio DESC LIMIT 1), e.empresa_id "
            "FROM employees e"), {"ini": comp_ini, "fim": comp_fim}).fetchall()
    }
    # sentinela usada pelo espelho Portte quando não há alocação (condominio_id é NOT NULL)
    SEM_COND = "00000000-0000-0000-0000-000000000001"

    def _verba(lista, *chaves):
        for it in lista or []:
            d = (it.get("descricao") or "").upper()
            if any(k in d for k in chaves):
                return float(it.get("valor") or 0)
        return 0.0

    # Escopo por condomínio: o Jordan fecha a folha condomínio a condomínio (formato Portte).
    # O motor calcula todo mundo (é ele que sabe ler o ponto); aqui recortamos QUEM entra.
    cond_nome = ""
    if cond_sel:
        row = db.execute(_sql("SELECT nome FROM condominios WHERE CAST(id AS TEXT) = :c"),
                         {"c": cond_sel}).first()
        if not row:
            raise HTTPException(status_code=422, detail="Condomínio não encontrado.")
        cond_nome = row[0]
        holerites = [h for h in holerites if (vinc.get(str(h["employee_id"])) or (None, None))[0] == cond_sel]
        if not holerites:
            raise HTTPException(
                status_code=400,
                detail=f"Nenhum colaborador alocado em {cond_nome} na competência {mes:02d}/{ano}.")

    # idempotente: só a versão 'conecta' da competência (jamais a 'portte'); com condomínio
    # selecionado apaga SÓ o daquele condomínio — senão fechar um posto zeraria os outros.
    _del = ("DELETE FROM hr_payslips WHERE source_system = 'conecta' "
            "AND reference_year = :a AND reference_month = :m")
    _par = {"a": ano, "m": mes}
    if cond_sel:
        _del += " AND CAST(condominio_id AS TEXT) = :c"
        _par["c"] = cond_sel
    apagados = db.execute(_sql(_del), _par).rowcount or 0

    gravados = 0
    for h in holerites:
        eid = str(h["employee_id"])
        cond, emp = vinc.get(eid, (None, None))
        db.execute(_sql(
            "INSERT INTO hr_payslips (id, condominio_id, employee_id, empresa_id, payslip_code, "
            " payslip_type, status, reference_year, reference_month, reference_period, "
            " competence_start, competence_end, base_salary, total_earnings, total_deductions, "
            " net_salary, earnings, deductions, informative, inss_base, inss_value, irrf_base, "
            " irrf_value, fgts_base, fgts_value, source_system) "
            "VALUES (gen_random_uuid(), CAST(:cond AS uuid), CAST(:eid AS uuid), CAST(:emp AS uuid), :code, "
            " 'mensal', 'draft', :ano, :mes, :per, :ini, :fim, :base, :prov, :desc, :liq, "
            " CAST(:earn AS jsonb), CAST(:ded AS jsonb), CAST(:info AS jsonb), :ibase, :ival, "
            " :rbase, :rval, :fbase, :fval, 'conecta')"),
            {
                "cond": cond or SEM_COND, "eid": eid, "emp": emp,
                "code": f"CONECTA-{ano}-{mes:02d}-{eid[:8]}",
                "ano": ano, "mes": mes, "per": f"{ano}-{mes:02d}",
                "ini": comp_ini, "fim": comp_fim,
                "base": float(h.get("salario_base") or 0),
                "prov": float(h.get("total_proventos") or 0),
                "desc": float(h.get("total_descontos") or 0),
                "liq": float(h.get("liquido") or 0),
                "earn": __import__("json").dumps(h.get("proventos") or []),
                "ded": __import__("json").dumps(h.get("descontos") or []),
                "info": __import__("json").dumps({
                    "escala": h.get("escala"), "dias_trabalhados": h.get("dias_trabalhados"),
                    "horas_ponto": h.get("horas_trabalhadas_ponto"),
                    "fonte_horas_noturnas": h.get("fonte_horas_noturnas"),
                    "gerado_por": str(current_user.id)}),
                "ibase": float(h.get("base_inss") or 0), "ival": _verba(h.get("descontos"), "INSS"),
                "rbase": float(h.get("base_irrf") or 0), "rval": _verba(h.get("descontos"), "IRRF", "IMPOSTO DE RENDA"),
                "fbase": float(h.get("base_fgts") or 0), "fval": float(h.get("fgts_empresa") or 0),
            })
        gravados += 1
    db.commit()

    # ALERTA DE GENTE NAO PAGA: holerite com liquido <= 0 quase sempre e cadastro incompleto
    # (salario_base nulo em admissao recente). Sem isto o holerite de R$ 0,00 passa em silencio
    # e a pessoa nao recebe. Nunca preencher salario por conta propria — e dado do DP.
    zerados = [h.get("employee_nome") or h.get("employee_id") for h in holerites
               if float(h.get("liquido") or 0) <= 0]
    alerta = ""
    if zerados:
        alerta = (f" ATENÇÃO — {len(zerados)} holerite(s) com líquido R$ 0,00, provável salário-base "
                  f"não cadastrado: {', '.join(str(n) for n in zerados[:8])}"
                  + ("…" if len(zerados) > 8 else "")
                  + ". Essas pessoas NÃO seriam pagas. Cadastre o salário e gere a folha de novo.")

    liq = (sum(float(h.get("liquido") or 0) for h in holerites) if cond_sel
           else float(batch.get("total_liquido") or 0))
    fgts = (sum(float(h.get("fgts_empresa") or 0) for h in holerites) if cond_sel
            else float(batch.get("total_fgts") or 0))
    ref = db.execute(_sql(
        "SELECT count(*), coalesce(round(sum(net_salary)::numeric,2),0) FROM hr_payslips "
        "WHERE source_system='portte' AND reference_year=:a AND reference_month=:m"),
        {"a": ano, "m": mes}).first()
    par = ""
    if ref and ref[0] and not cond_sel:
        par = (f" Portte na mesma competência: {ref[0]} holerite(s), {brl(float(ref[1]))} — "
               f"diferença {brl(liq - float(ref[1]))}. Confira em DP → Folha: Conecta × Portte.")
    # Gancho de documento: a ModuleView abre d.doc assim que o form volta OK. Sem isto o
    # Jordan gera a folha e fica sem nada na mão — tem que sair da tela, achar a linha e
    # clicar. O PDF sai do que ACABOU de ser gravado.
    _doc = {
        "label": f"Folha {mes:02d}/{ano}" + (f" — {cond_nome}" if cond_nome else ""),
        "url": f"/api/v1/people-management/folha/{mes}/{ano}/pdf"
               + (f"?condominio={cond_sel}" if cond_sel else ""),
        "fmt": "pdf", "mode": "blob", "gate": "financeiro",
    }
    return {"ok": True, "doc": _doc, "message": (
        f"Folha {mes:02d}/{ano}{' — ' + cond_nome if cond_nome else ' (todos os condomínios)'} "
        f"GERADA no Conecta PRO: {gravados} holerite(s), "
        f"líquido {brl(liq)}, FGTS {brl(fgts)}. "
        f"Status rascunho — gerar não paga; o pagamento segue no Financeiro com OTP."
        + (f" (Substituiu {apagados} holerite(s) 'conecta' da geração anterior.)" if apagados else "")
        + alerta + par)}


@router.post("/action/folha-apontamento")
async def rd_action_folha_apontamento(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db=Depends(get_sync_db_dependency),
) -> dict:
    """Apontamento de NÃO CONFORMIDADE numa folha (pré-fechamento). NÃO fecha nem paga —
    só registra o motivo (com a identidade real do autor) em `contest_reason`+`contested_at`,
    SEM mudar o status (não interfere no fechamento do Jordan/Pyetra). Reutiliza os campos de
    contestação da folha. Quem fecha (Jordan/Pyetra) vê o apontamento e resolve antes."""
    from sqlalchemy import text as _t
    pid = (payload.get("payslip_id") or "").strip()
    motivo = (payload.get("motivo") or "").strip()
    if not pid:
        raise HTTPException(status_code=422, detail="Selecione a folha (colaborador/competência).")
    if len(motivo) < 5:
        raise HTTPException(status_code=422, detail="O apontamento precisa de ao menos 5 caracteres.")
    autor = getattr(current_user, "name", None) or getattr(current_user, "email", None) or str(current_user.id)
    r = db.execute(_t(
        "UPDATE hr_payslips SET contest_reason = :m, contested_at = now() "
        "WHERE id::text = :i AND status::text IN ('draft','published')"),
        {"m": f"[{autor}] {motivo}", "i": pid})
    db.commit()
    if getattr(r, "rowcount", 0) == 0:
        raise HTTPException(status_code=400, detail="Folha não encontrada ou não elegível para apontamento.")
    return {"ok": True, "message": "Apontamento registrado na folha (não conformidade)"}


@router.post("/action/ferias-aprovar")
async def rd_action_ferias_aprovar(current_user: CurrentActiveUser, vid: str, db=Depends(get_db)) -> dict:
    """Aprovar férias ESCOPADO à equipe operacional. Supervisor/gerente só aprova férias de
    colaborador alocado a posto ativo; admin (Jordan/Pyetra) aprova qualquer um. Reusa o
    controller real approve_vacation após a parede de escopo."""
    from sqlalchemy import text as _t

    from modules.operacional.controllers.redesign_builders.operacional import _exige_escopo_operacional
    from modules.people_management.hr.controllers.vacation_controller import approve_vacation
    v = (await db.execute(_t(
        "SELECT CAST(employee_id AS TEXT) FROM hr_vacation_requests WHERE id::text=:i"), {"i": vid})).first()
    if not v or not v[0]:
        raise HTTPException(status_code=404, detail="Solicitação de férias não encontrada.")
    await _exige_escopo_operacional(db, current_user, v[0],
                                    "aprovar férias de colaborador da sua equipe operacional")
    return await approve_vacation(vacation_id=vid, current_user=current_user, db=db)


def _require_modulo_dp(current_user: CurrentActiveUser) -> None:
    """Gate module:dp p/ decisão de reembolso — AGORA no REDESIGN (o endpoint clássico
    /api/v1/reimbursements/* foi mantido intocado a pedido do Jordan: nossa parede vive só
    aqui). admin/all passam; Eliziel/Orlailson (module:dp) passam; celiane (self:portal)→403."""
    from core.auth.module_scope import user_has_module
    if not user_has_module(current_user, "dp"):
        raise HTTPException(status_code=403, detail="Decidir reembolso é restrito ao DP.")


def _rid_uuid(rid: str):
    from uuid import UUID
    try:
        return UUID(str(rid))
    except Exception:
        raise HTTPException(status_code=400, detail="Reembolso inválido.")


@router.post("/action/reembolso-aprovar", dependencies=[Depends(_require_modulo_dp)])
async def rd_action_reembolso_aprovar(current_user: CurrentActiveUser, rid: str, db=Depends(get_db)) -> dict:
    """Aprovar reembolso — gate module:dp no redesign; reusa ApprovalService (serviço provado)."""
    from modules.reimbursement.services import ApprovalService
    try:
        req = await ApprovalService(db).approve_request(
            request_id=_rid_uuid(rid), user_id=current_user.id, comments=None, approved_items=None)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not req:
        raise HTTPException(status_code=404, detail="Reembolso não encontrado.")
    return {"ok": True, "message": "Reembolso aprovado."}


@router.post("/action/reembolso-analisar", dependencies=[Depends(_require_modulo_dp)])
async def rd_action_reembolso_analisar(current_user: CurrentActiveUser, rid: str, db=Depends(get_db)) -> dict:
    """Mover reembolso p/ análise — gate module:dp no redesign."""
    from modules.reimbursement.services import ApprovalService
    try:
        req = await ApprovalService(db).start_analysis(_rid_uuid(rid), current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not req:
        raise HTTPException(status_code=404, detail="Reembolso não encontrado.")
    return {"ok": True, "message": "Reembolso em análise."}


@router.post("/action/reembolso-rejeitar", dependencies=[Depends(_require_modulo_dp)])
async def rd_action_reembolso_rejeitar(current_user: CurrentActiveUser, rid: str,
                                       payload: dict = Body(default={}), db=Depends(get_db)) -> dict:
    """Rejeitar reembolso (motivo obrigatório) — gate module:dp no redesign."""
    from modules.reimbursement.services import ApprovalService
    reason = (payload.get("reason") or "").strip()
    if len(reason) < 3:
        raise HTTPException(status_code=400, detail="Informe o motivo da rejeição (mín. 3 caracteres).")
    try:
        req = await ApprovalService(db).reject_request(_rid_uuid(rid), current_user.id, reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not req:
        raise HTTPException(status_code=404, detail="Reembolso não encontrado.")
    return {"ok": True, "message": "Reembolso rejeitado."}
# F0 — menu extra ZERADO (idêntico ao financeiro): as 24 entradas soltas viram ABAS dos 8
# grupos (_dp_grupos.py) e o menu do módulo passa a ser só os grupos, declarado no pacote
# `_modules/departamento-pessoal.json`. As telas continuam TODAS montadas no build; só saem
# da navegação de topo. Menu em UM lugar só — o front soma pacote + EXTRA_MENU, então
# declarar nos dois duplicaria cada aba.
EXTRA_MENU: list[dict] = []

# datas: as tabelas usam date/timestamp; formatador defensivo local
_ND = "#0F1B3A"


def _d(v, fmt="%d/%m/%Y"):
    try:
        return v.strftime(fmt) if v else "—"
    except Exception:
        return "—"


def _badge_status(v):
    s = (v or "").lower()
    if s in ("ativo", "active", "concluido", "concluida", "fechado", "fechada",
             "aprovado", "aprovada", "paga", "processed", "processada",
             "transmitida", "publicado", "published", "assinado"):
        return b(v or "—", "ok")
    if s in ("pendente", "em_andamento", "aguardando", "em_analise", "submitted",
             "nao_transmitida", "rascunho", "draft", "aberto"):
        return b(v or "—", "warn")
    if s in ("rejeitado", "reprovado", "cancelado", "erro", "vencido", "rejected"):
        return b(v or "—", "bad")
    return b(v or "—", "info")


def _badge_bool(v, sim="Sim", nao="Não", tone_sim="ok", tone_nao="mut"):
    return b(sim, tone_sim) if v else b(nao, tone_nao)


# Completude do cadastro (S-2200) — MESMA fórmula do clássico (dp/funcionarios/page.tsx):
# 15 campos eSocial; % = preenchidos/15; mostra os campos faltantes (fidelidade).
_ESOCIAL_15 = 15


async def _scalar_dp(db):
    from sqlalchemy import text as _sqltext
    try:
        r = await db.execute(_sqltext("SELECT count(*) FROM employees WHERE status='ativo'"))
        return r.scalar() or 0
    except Exception:
        return 0


_BEN_ST = {"active": ("Ativo", "ok"), "ativo": ("Ativo", "ok"), "cancelled": ("Cancelado", "mut"),
           "canceled": ("Cancelado", "mut"), "cancelado": ("Cancelado", "mut"),
           "inactive": ("Inativo", "mut"), "suspended": ("Suspenso", "warn")}


def _ben_status(v):
    lbl, tone = _BEN_ST.get((v or "").lower(), (v or "—", "info"))
    return b(lbl, tone)


_BEN_TYPE = {"vale_refeicao": "Vale Refeição", "vale_transporte": "Vale Transporte",
             "vr": "Vale Refeição", "vt": "Vale Transporte", "plano_saude": "Plano de Saúde",
             "plano_odontologico": "Plano Odontológico", "seguro_vida": "Seguro de Vida",
             "emprestimo_consignado": "Empréstimo Consignado"}


def _ben_type(v):
    return _BEN_TYPE.get((v or "").lower(), (v or "—").replace("_", " ").capitalize() if "_" in (v or "") else (v or "—"))


# Folha — espelha statusConfig do clássico (dp/folha/page.tsx): published→Calculada
_FOLHA_ST = {"published": ("Calculada", "ok"), "calculada": ("Calculada", "ok"),
             "calculated": ("Calculada", "ok"), "contested": ("Contestada", "warn"),
             "processing": ("Processando", "info"), "paid": ("Pago", "ok"),
             "draft": ("Rascunho", "mut"), "closed": ("Fechada", "ok")}


def _folha_status(v):
    lbl, tone = _FOLHA_ST.get((v or "").lower(), (v or "—", "info"))
    return b(lbl, tone)


def _fer_status(status, cancelled_at):
    """Status de férias em PT, mesma derivação do clássico (enum é SUBMITTED/APPROVED)."""
    if cancelled_at:
        return b("Cancelado", "mut")
    s = (status or "").upper()
    if s == "APPROVED":
        return b("Aprovado", "ok")
    if s == "REJECTED":
        return b("Rejeitado", "bad")
    if s == "CANCELLED":
        return b("Cancelado", "mut")
    return b("Pendente", "warn")


# Rescisão — espelham tipoConfig/statusConfig do clássico (dp/rescisao/page.tsx)
_TERM_TYPE = {"voluntary": "Voluntária", "involuntary": "Involuntária", "just_cause": "Justa Causa",
              "mutual_agreement": "Acordo Mútuo", "contract_end": "Fim de Contrato",
              "retirement": "Aposentadoria"}
_TERM_ST = {"initiated": ("Iniciado", "info"), "notice_period": ("Aviso Prévio", "warn"),
            "calculating": ("Calculando", "warn"), "pending_payment": ("Pgto Pendente", "warn"),
            "completed": ("Concluída", "ok"), "cancelled": ("Cancelada", "mut")}


def _term_status(v):
    lbl, tone = _TERM_ST.get((v or "").lower(), (v or "—", "info"))
    return b(lbl, tone)


# Admissão/Onboarding — espelha statusConfig do clássico (dp/admissao/page.tsx)
_ADM_ST = {"documents_pending": ("Documentos Pendentes", "warn"), "medical_exam": ("Exame Médico", "info"),
           "contract_signing": ("Assinatura de Contrato", "warn"), "in_progress": ("Em Andamento", "info"),
           "completed": ("Concluída", "ok"), "cancelled": ("Cancelada", "mut")}


def _adm_status(v):
    lbl, tone = _ADM_ST.get((v or "").lower(), (v or "—", "info"))
    return b(lbl, tone)


def _cpf_fmt(v):
    d = "".join(ch for ch in (v or "") if ch.isdigit())
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:11]}" if len(d) == 11 else (v or "—")


# Contratos — espelha contractTypeLabels do clássico (dp/contratos/page.tsx)
_CONTRACT_TYPE = {"clt_indeterminate": "CLT Indeterminado", "clt_determinate": "CLT Determinado",
                  "temporary": "Temporário", "internship": "Estágio", "apprentice": "Aprendiz",
                  "clt": "CLT"}


def _contract_type(v):
    return _CONTRACT_TYPE.get((v or "").lower(), v or "—")


# Documentos — espelha statusConfig do clássico (dp/documentos/page.tsx)
_DOC_ST = {"draft": ("Rascunho", "warn"), "active": ("Ativo", "ok"), "ativo": ("Ativo", "ok"),
           "valid": ("Válido", "ok"), "valido": ("Válido", "ok"), "expired": ("Vencido", "bad"),
           "vencido": ("Vencido", "bad"), "pending": ("Pendente", "warn"), "pendente": ("Pendente", "warn"),
           "archived": ("Arquivado", "mut")}


def _doc_status(v):
    lbl, tone = _DOC_ST.get((v or "").lower(), (v or "—", "info"))
    return b(lbl, tone)


# Reembolsos — espelha statusConfig do clássico (dp/reembolsos/page.tsx, PT + sinônimos EN)
_REI_ST = {"rascunho": ("Rascunho", "mut"), "pendente": ("Pendente", "warn"), "aprovado": ("Aprovado", "ok"),
           "rejeitado": ("Rejeitado", "bad"), "pago": ("Pago", "info"),
           "submitted": ("Pendente", "warn"), "pending": ("Pendente", "warn"), "approved": ("Aprovado", "ok"),
           "rejected": ("Rejeitado", "bad"), "paid": ("Pago", "info")}


def _rei_status(v):
    lbl, tone = _REI_ST.get((v or "").lower(), (v or "—", "info"))
    return b(lbl, tone)


# Certificação — espelha statusBadge do clássico (dp/certificacao/page.tsx)
_CERT_ST = {"pendente": ("Pendente", "warn"), "certificado": ("Certificado", "ok"),
            "rejeitado": ("Rejeitado", "bad")}


def _cert_status(v):
    lbl, tone = _CERT_ST.get((v or "").lower(), (v or "—", "info"))
    return b(lbl, tone)


# Prestadores PJ — status do autocadastro (gerador de link). pj_ativo = autocadastro concluído
# pela pessoa; qualquer outro (pj_pendente etc.) = link ainda aguardando preenchimento.
def _pj_status(v):
    return b("Concluído", "ok") if (v or "").lower() == "pj_ativo" else b("Aguardando", "warn")


# Licenças — espelha statusConfig + synonyms EN do clássico (dp/licencas/page.tsx)
_LIC_ST = {"ativo": ("Ativo", "info"), "ativa": ("Ativo", "info"), "active": ("Ativo", "info"),
           "em_andamento": ("Em Andamento", "warn"), "in_progress": ("Em Andamento", "warn"),
           "ongoing": ("Em Andamento", "warn"),
           "encerrado": ("Encerrado", "mut"), "encerrada": ("Encerrado", "mut"),
           "ended": ("Encerrado", "mut"), "closed": ("Encerrado", "mut"),
           "cancelado": ("Cancelado", "bad"), "cancelada": ("Cancelado", "bad"),
           "cancelled": ("Cancelado", "bad"), "canceled": ("Cancelado", "bad")}


def _lic_status(v):
    lbl, tone = _LIC_ST.get((v or "").lower(), (v or "—", "info"))
    return b(lbl, tone)


# Fechamento de ponto — MESMA derivação do painel do clássico (espelho_ponto_service.painel_fechamento):
# status fechado = enum ∈ STATUS_FECHADO; assinatura via sig_signature_requests.
_STATUS_FECHADO = {"fechado", "aprovado", "revisado", "enviado_folha"}


def _hm(minutes):
    m = int(minutes or 0)
    return f"{m // 60:02d}:{m % 60:02d}"


def _fech_status(status, anomalias, approved, sig_status, sig_signed):
    """Deriva o badge igual ao clássico: Homologado / Aguardando assinatura / Fechado / N anomalia(s) / Calculado."""
    fechado = (status or "").lower() in _STATUS_FECHADO
    assinado = bool(approved) or (str(sig_status or "").lower() in ("signed", "completed")) or bool(sig_signed)
    if fechado and assinado:
        return b("Homologado", "ok")
    if fechado and sig_status is not None:
        return b("Aguardando assinatura", "info")
    if fechado:
        return b("Fechado", "info")
    if (anomalias or 0) > 0:
        return b(f"{anomalias} anomalia(s)", "warn")
    return b("Calculado", "mut")


def _completude_cell(faltantes):
    """faltantes = array (do SQL) com os rótulos dos campos vazios."""
    fal = [x for x in (faltantes or []) if x]
    pct = round((_ESOCIAL_15 - len(fal)) / _ESOCIAL_15 * 100)
    if not fal:
        return t("100% · completo", 600, "#0E7C57")
    lbl = ", ".join(fal[:3]) + (f" +{len(fal) - 3}" if len(fal) > 3 else "")
    cor = "#0E7C57" if pct >= 80 else "#B4690E" if pct >= 50 else "#DC2626"
    return t(f"{pct}% · {lbl}", 600, cor)


# SQL que devolve os rótulos faltantes (ordem/nomes iguais ao FIELD_LABELS do clássico)
_FALTANTES_SQL = (
    "array_remove(ARRAY["
    "CASE WHEN nullif(trim(coalesce(nome,'')),'') IS NULL THEN 'Nome' END,"
    "CASE WHEN nullif(trim(coalesce(cpf,'')),'') IS NULL THEN 'CPF' END,"
    "CASE WHEN data_nascimento IS NULL THEN 'Data de Nascimento' END,"
    "CASE WHEN nullif(trim(coalesce(sexo,'')),'') IS NULL THEN 'Sexo' END,"
    "CASE WHEN nullif(trim(coalesce(estado_civil,'')),'') IS NULL THEN 'Estado Civil' END,"
    "CASE WHEN nullif(trim(coalesce(nome_mae,'')),'') IS NULL THEN 'Nome da Mãe' END,"
    "CASE WHEN nullif(trim(coalesce(rg,'')),'') IS NULL THEN 'RG' END,"
    "CASE WHEN nullif(trim(coalesce(pis,'')),'') IS NULL THEN 'PIS/PASEP' END,"
    "CASE WHEN nullif(trim(coalesce(ctps_numero,'')),'') IS NULL THEN 'CTPS Número' END,"
    "CASE WHEN nullif(trim(coalesce(nacionalidade,'')),'') IS NULL THEN 'Nacionalidade' END,"
    "CASE WHEN nullif(trim(coalesce(naturalidade,'')),'') IS NULL THEN 'Naturalidade' END,"
    "CASE WHEN nullif(trim(coalesce(cep,'')),'') IS NULL THEN 'CEP' END,"
    "CASE WHEN nullif(trim(coalesce(logradouro,'')),'') IS NULL THEN 'Logradouro' END,"
    "CASE WHEN nullif(trim(coalesce(cidade,'')),'') IS NULL THEN 'Cidade' END,"
    "CASE WHEN nullif(trim(coalesce(uf,'')),'') IS NULL THEN 'UF' END"
    "], NULL)"
)


async def _rescisao_screen(db):
    """Rescisão — MESMA fonte (termination_processes) e MESMO cálculo do clássico:
    quando total_amount é NULL (todos hoje), o clássico computa ao vivo via
    service.calculate_severance. Replico isso (senão exibia R$ 0,00 = NULL como zero)."""
    from sqlalchemy import text as _sqltext
    rows = (await db.execute(_sqltext(
        "SELECT CAST(tp.employee_id AS TEXT), e.nome, tp.type::text, tp.status::text, "
        "tp.last_working_day, tp.total_amount, CAST(tp.id AS TEXT) "
        "FROM termination_processes tp LEFT JOIN employees e ON e.id=tp.employee_id "
        "ORDER BY tp.last_working_day DESC NULLS LAST, tp.created_at DESC LIMIT 200"))).all()
    svc = TT = None
    try:
        from modules.people_management.hr.services.termination_service import TerminationService
        from modules.people_management.hr.models.termination import TerminationType as _TT
        svc, TT = TerminationService(db), _TT
    except Exception:
        pass
    out_rows = []
    for emp_id, nome, tp_type, tp_status, lwd, total, tid in rows:
        val = float(total) if total not in (None,) else None
        if (val is None or val == 0) and svc and emp_id and lwd:
            try:
                try:
                    _tp = TT(tp_type)
                except Exception:
                    _tp = TT.INVOLUNTARY
                calc = await svc.calculate_severance(employee_id=emp_id, termination_type=_tp, last_working_day=lwd)
                v = calc.get("total_liquido") or calc.get("total_proventos")
                val = float(v) if v is not None else None
            except Exception:
                val = None
        _term_actions = ([
            {"title": f"Calcular verbas — {nome or '—'}",
             "endpoint": f"/api/v1/people-management/hr/terminations/{tid}/calculate",
             "method": "POST", "btnLabel": "Calcular verbas", "btnStyle": "outline",
             "submitLabel": "Calcular", "okMsg": "Verbas rescisórias calculadas. Recarregue a tela.", "fields": []},
            {"title": f"Concluir rescisão — {nome or '—'}",
             "endpoint": f"/api/v1/people-management/hr/terminations/{tid}/complete",
             "method": "POST", "btnLabel": "Concluir", "btnStyle": "primary",
             "submitLabel": "Concluir rescisão",
             "okMsg": "Rescisão concluída. Recarregue a tela.", "fields": []},
        ] if (tp_status or "").lower() not in ("completed", "concluida", "concluída", "cancelled", "cancelada") else [])
        out_rows.append({"cells": [
            t(nome or "—", 600, _ND, initials(nome or "")),
            t(_TERM_TYPE.get((tp_type or "").lower(), tp_type or "—")),
            _term_status(tp_status), t(_d(lwd)),
            t(brl(val) if val is not None else "a calcular", 600)],
            "docs": [
                doc("TRCT", f"/api/v1/people-management/hr/terminations/{tid}/trct/pdf", fmt="pdf", gate="dp"),
                doc("Aviso prévio", f"/api/v1/people-management/hr/terminations/{tid}/aviso-previo/pdf", fmt="pdf", gate="dp"),
            ],
            **({"actions": _term_actions} if _term_actions else {})})
    return {"title": "Rescisão", "sub": "Processos de desligamento — tipo, status e verbas",
            "cta": "Nova rescisão", "type": "table", "searchHint": "Buscar…",
            "grid": "2fr 1.2fr 1fr 1fr 1.1fr",
            "cols": ["Colaborador", "Tipo", "Status", "Último Dia", "Valor Total"],
            "rows": out_rows}



# ─── PORTAS MANUAIS (lei "uma operação, duas portas") ─────────────────────────
# Cada ação que o agente PROPÕE precisa existir também como formulário, senão a Pyetra
# depende do agente para operar — o oposto do combinado ("o chat é braço direito, não a
# única porta"). Estas 3 faltavam; fechar-mês, aviso-de-férias e contracheques-em-lote já
# existiam. Os endpoints são os MESMOS que os executores chamam.

def _tela_registrar_licenca(_emp_opts) -> dict:
    return {
        "title": "Registrar licença/afastamento",
        "sub": "Mesma porta que o agente usa ao propor — grava em sst_afastamentos e deriva "
               "estabilidade acidentária (art. 118) quando o tipo/CID indicam.",
        "cta": "Registrar", "type": "form",
        "submit": {"endpoint": "/api/v1/people-management/hr/leaves",
                   "okMsg": "Licença registrada"},
        "fields": [
            {"key": "employee_id", "label": "Colaborador*", "type": "select", "span": "span 2",
             "ph": "Selecione", "options": _emp_opts},
            {"key": "leave_type", "label": "Tipo*", "type": "select", "span": "span 1",
             "ph": "Selecione", "options": [
                 {"value": "licenca", "label": "Licença"},
                 {"value": "doenca", "label": "Doença (atestado)"},
                 {"value": "acidente", "label": "Acidente de trabalho"},
                 {"value": "maternidade", "label": "Maternidade"},
                 {"value": "inss", "label": "Afastamento INSS (+15 dias)"}]},
            {"key": "cid", "label": "CID", "type": "text", "span": "span 1",
             "ph": "define estabilidade em acidente"},
            {"key": "start_date", "label": "Início*", "type": "date", "span": "span 1"},
            {"key": "end_date", "label": "Fim previsto", "type": "date", "span": "span 1"},
            {"key": "notes", "label": "Motivo/observação", "type": "text", "span": "span 2"},
        ],
    }


def _tela_renovar_aso(_emp_opts) -> dict:
    return {
        "title": "Agendar/renovar ASO",
        "sub": "Sem ASO válido o colaborador não pode trabalhar (NR-7). Mesma porta que o "
               "agente usa ao propor a renovação.",
        "cta": "Agendar", "type": "form",
        "submit": {"endpoint": "/api/v1/people-management/sst/aso", "okMsg": "ASO agendado"},
        "fields": [
            {"key": "employee_id", "label": "Colaborador*", "type": "select", "span": "span 2",
             "ph": "Selecione", "options": _emp_opts},
            {"key": "tipo", "label": "Tipo*", "type": "select", "span": "span 1",
             "ph": "Selecione", "options": [
                 {"value": "periodico", "label": "Periódico"},
                 {"value": "admissional", "label": "Admissional"},
                 {"value": "demissional", "label": "Demissional"},
                 {"value": "retorno", "label": "Retorno ao trabalho"},
                 {"value": "mudanca_funcao", "label": "Mudança de função"}]},
            {"key": "data_agendamento", "label": "Data do exame*", "type": "date", "span": "span 1"},
            {"key": "clinica", "label": "Clínica", "type": "text", "span": "span 2"},
        ],
    }


async def _tela_revisar_justificativa(db, current_user=None) -> dict:
    from sqlalchemy import text as _sql

    rows = (await db.execute(_sql(
        "SELECT CAST(j.justification_id AS TEXT), coalesce(e.nome,'—'), "
        "       coalesce(j.reason, j.justification_type, ''), j.created_at "
        "FROM gp_justifications j "
        "LEFT JOIN employees e ON CAST(e.id AS TEXT) = CAST(j.employee_id AS TEXT) "
        "WHERE lower(coalesce(j.status,'')) IN ('pendente','pending','em_analise') "
        "ORDER BY j.created_at LIMIT 100"))).fetchall()
    # a rota oficial leva o ID NO PATH (/ponto/justificativa/{id}/revisar), então cada
    # linha tem a própria ação — não dá para usar um form único com select.
    # A rota é **PUT** (não POST) e o schema `JustificationReview` exige `reviewer_id`:
    # com POST dá 405 e sem reviewer_id dá 422. Quem revisa é quem está na tela, então o
    # id sai do current_user injetado pelo dispatcher — não é campo que a Pyetra digita.
    _rev = str(getattr(current_user, "id", "") or "")

    def _linha(r):
        jid = r[0]
        acao = lambda dec, lbl, estilo: {  # noqa: E731
            "title": f"{lbl}: {r[1]}",
            "endpoint": f"/api/v1/people-management/ponto/justificativa/{jid}/revisar",
            "method": "PUT", "btnLabel": lbl, "submitLabel": lbl, "btnStyle": estilo,
            "okMsg": f"Justificativa {lbl.lower()}a.",
            # `fixed` e não `type:"hidden"`: o ModuleView não conhece campo hidden — ele cairia
            # no ramo <input type="text">, virando duas caixas editáveis (uma com "aprovar",
            # outra com o UUID do revisor). Editável significa que dava para transformar um
            # deferir em indeferir digitando na caixa. `fixed` vai no body e não é renderizado.
            "fixed": {"action": dec, "reviewer_id": _rev},
            "fields": [{"key": "notes", "label": "Observação (opcional)", "type": "text"}],
        }
        return {"cells": [
            {"isText": True, "v": r[1][:28], "w": 600, "tc": "#0F1B3A", "ini": ""},
            {"isText": True, "v": (r[2] or "")[:60], "w": 500, "tc": "#334155", "ini": ""},
            {"isText": True, "v": r[3].strftime("%d/%m") if r[3] else "—", "w": 500,
             "tc": "#64748B", "ini": ""},
        ], "actions": [acao("aprovar", "Deferir", "primary"),
                       acao("rejeitar", "Indeferir", "danger")]}

    return {
        "title": "Revisar justificativa de ponto",
        "sub": (f"{len(rows)} justificativa(s) pendente(s). Deferir ou indeferir é juízo "
                f"humano — o agente propõe, quem decide é você."
                if rows else "Nenhuma justificativa pendente."),
        "cta": "Atualizar", "type": "table", "searchHint": "Buscar…",
        "grid": "1.4fr 2.6fr 0.6fr",
        "cols": ["Colaborador", "Motivo", "Desde"],
        "rows": [_linha(r) for r in rows],
    }


async def build(db, current_user=None) -> dict:
    # Base = tudo que o _build_dp já entrega (telas VIVAS + ferramentas).
    out = await _build_dp(db)
    # tbl é apenas um construtor query→dict ligado a este db; safe local grava no `out` base.
    _out2, _safe2, tbl = _helpers(db)

    async def _emp_opts_ativos():
        from sqlalchemy import text as _sqlt

        rs = (await db.execute(_sqlt(
            "SELECT CAST(id AS TEXT), nome FROM employees WHERE status='ativo' ORDER BY nome"
        ))).fetchall()
        return [{"value": r[0], "label": r[1]} for r in rs]

    async def safe(key, coro):
        try:
            out[key] = await coro
        except Exception:
            try:
                await db.rollback()
            except Exception:
                pass

    # 0) Funcionários — SOBRESCREVE a tela base p/ trazer a COMPLETUDE do cadastro (%/faltantes),
    #    que o clássico mostra e o redesign não (fidelidade). Mesma fórmula: 15 campos S-2200.
    await safe("funcionarios", tbl(
        "Funcionários", f"{await _scalar_dp(db)} ativos", "Nova admissão",
        ["Colaborador", "Cargo", "Admissão", "Cadastro (eSocial)", "Status"],
        "2fr 1.3fr 1fr 1.7fr 0.9fr",
        "SELECT nome, coalesce(cargo,'—'), data_admissao, status::text, " + _FALTANTES_SQL + " AS faltantes, "
        "CAST(id AS TEXT), coalesce(cpf,''), coalesce(email,''), coalesce(celular,''), coalesce(departamento,''), salario_base "
        "FROM employees WHERE status='ativo' ORDER BY nome LIMIT 300",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(r[1]), t(_d(r[2])),
                   _completude_cell(r[4]), _badge_status(r[3])],
        editfn=lambda r: {
            "title": f"Editar — {r[0]}",
            "endpoint": f"/api/v1/people-management/hr/employees/{r[5]}", "method": "PATCH",
            "fields": [
                {"key": "nome", "label": "Nome", "type": "text", "span": "span 2", "value": r[0] or ""},
                {"key": "cpf", "label": "CPF", "type": "text", "value": r[6] or ""},
                {"key": "cargo", "label": "Cargo", "type": "text", "value": (r[1] if r[1] != "—" else "")},
                {"key": "departamento", "label": "Departamento", "type": "text", "value": r[9] or ""},
                {"key": "email", "label": "E-mail", "type": "text", "value": r[7] or ""},
                {"key": "celular", "label": "Celular", "type": "text", "value": r[8] or ""},
                {"key": "salario_base", "label": "Salário base", "type": "text", "value": (str(r[10]) if r[10] is not None else "")},
            ],
        }))

    # 0b) Folha — SOBRESCREVE a base p/ trazer o BREAKDOWN do clássico (INSS/FGTS/Descontos),
    #     que o redesign perdeu (só mostrava base+líquido). Mesmas colunas do clássico.
    # Folha: TODAS as competências (ordenadas desc) + seletor de competência (filterCol=0).
    # r[12]=competência 'MM/YYYY'; a coluna 0 vira o filtro; per-linha Holerite/Recibo p/ qualquer mês.
    await safe("folha", tbl(
        "Folha de pagamento", "Proventos, encargos e descontos — selecione a competência", "—",
        ["Competência", "Colaborador", "Cargo", "Salário base", "INSS", "FGTS 8%", "Descontos", "Líquido", "Status"],
        "0.9fr 1.8fr 1.2fr 1fr 0.9fr 0.9fr 1fr 1fr 0.9fr",
        "SELECT e.nome, coalesce(e.cargo,'—'), p.base_salary, p.inss_value, p.fgts_value, "
        "p.total_deductions, p.net_salary, p.status::text, "
        "CAST(p.id AS TEXT), CAST(p.employee_id AS TEXT), p.reference_month, p.reference_year, "
        "to_char(make_date(p.reference_year, p.reference_month, 1),'MM/YYYY') "
        "FROM hr_payslips p LEFT JOIN employees e ON e.id=p.employee_id "
        "ORDER BY p.reference_year DESC, p.reference_month DESC, e.nome LIMIT 500",
        lambda r: [t(r[12], 600, _ND), t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(r[1]), t(brl(r[2])),
                   t(brl(r[3])), t(brl(r[4])), t(brl(r[5])), t(brl(r[6]), 600), _folha_status(r[7])],
        docsfn=lambda r: [
            doc("Holerite", f"/api/v1/people-management/dp/payslips/{r[8]}/pdf", fmt="pdf", gate="financeiro"),
            doc("Recibo VT/VR", f"/api/v1/people-management/folha/recibo-vt-vr/{r[9]}/{r[10]}/{r[11]}/pdf", fmt="pdf", gate="financeiro"),
        ]))
    # marca o seletor de competência (coluna 0) — o ModuleView renderiza o dropdown e filtra client-side
    if out.get("folha"):
        out["folha"]["filterCol"] = 0
        out["folha"]["filterLabel"] = "Competência"
        # Botao de GERAR na propria tela de Folha: o item de nav cai no fim de uma barra com
        # 44 telas + 19 acoes e ninguem acha. A ModuleView so renderiza o CTA se ctaTo apontar
        # p/ uma tela existente (e o rotulo nao pode ficar "—", que e o default do tbl()).
        out["folha"]["cta"] = "Gerar folha (Conecta PRO)"
        out["folha"]["ctaTo"] = "folha-gerar"

    # ---- FOLHA POR CONDOMÍNIO (fechamento no formato que o Jordan usa com a Portte) --------
    # Uma GERAL (painéis no topo) + uma linha por condomínio, com VILLA DOS PÁSSAROS primeiro
    # (é assim que ele confere). Liga o holerite ao condomínio pela alocação VIGENTE na
    # competência; quem não tem alocação no período cai em "(sem alocação)" — nunca some.
    await safe("folha-por-condominio", tbl(
        "Folha por condomínio",
        "Fechamento no formato do relatório da Portte: TOTAL GERAL primeiro, depois Villa dos Pássaros "
        "e os demais condomínios. Vínculo pela alocação vigente na competência. Filtre a competência.",
        "—", ["Competência", "Condomínio", "Pessoas", "Bruto", "Descontos", "Líquido"],
        "1fr 1.8fr 0.8fr 1.1fr 1.1fr 1.1fr",
        # GROUPING SETS = a linha "TOTAL GERAL" sai na MESMA consulta (sobrevive ao filtro de
        # competência, que é client-side). LATERAL ... LIMIT 1 é obrigatório: com LEFT JOIN direto,
        # quem tem 2 alocações no mês soma o holerite 2x e o bruto de 06/2026 inflava
        # 111.388,40 -> 132.165,17. Oráculo: TOTAL GERAL == folha conciliada do mês.
        """
        SELECT to_char(p.competence_start,'MM/YYYY') AS comp,
               CASE WHEN grouping(coalesce(a.nome,'(sem alocação)')) = 1 THEN 'TOTAL GERAL'
                    ELSE coalesce(a.nome,'(sem alocação)') END AS condominio,
               count(*) AS pessoas,
               round(sum(p.total_earnings)::numeric,2) AS bruto,
               round(sum(p.total_deductions)::numeric,2) AS descontos,
               round(sum(p.net_salary)::numeric,2) AS liquido,
               max(a.cid) AS cond_id
        FROM hr_payslips p
        JOIN employees e ON e.id = p.employee_id AND coalesce(e.is_homologacao,false) = false
        LEFT JOIN LATERAL (
            SELECT co.nome, CAST(co.id AS TEXT) AS cid
            FROM employee_alocacoes al JOIN condominios co ON co.id = al.condominio_id
            WHERE al.employee_id = p.employee_id
              AND al.data_inicio <= (date_trunc('month', p.competence_start) + interval '1 month -1 day')::date
              AND (al.data_fim IS NULL OR al.data_fim >= date_trunc('month', p.competence_start)::date)
            ORDER BY al.data_inicio DESC LIMIT 1
        ) a ON true
        WHERE p.competence_start IS NOT NULL
        GROUP BY GROUPING SETS ((to_char(p.competence_start,'MM/YYYY')),
                                (to_char(p.competence_start,'MM/YYYY'), coalesce(a.nome,'(sem alocação)')))
        ORDER BY 1 DESC,
                 grouping(coalesce(a.nome,'(sem alocação)')) DESC,
                 (upper(coalesce(a.nome,'(sem alocação)')) LIKE '%PASSAROS%'
                  OR upper(coalesce(a.nome,'(sem alocação)')) LIKE '%PÁSSAROS%') DESC,
                 2
        """,
        lambda r: [t(r[0] or "—", 600),
                   t(r[1], 700 if r[1] == "TOTAL GERAL" else 600,
                     "#16277D" if r[1] == "TOTAL GERAL" else "#0F1B3A"),
                   t(str(r[2])),
                   t(brl(float(r[3] or 0)), 600),
                   t(brl(float(r[4] or 0)), 600, "#C2410C"),
                   t(brl(float(r[5] or 0)), 700, "#16A34A")],
        docsfn=lambda r: ([] if not r[0] else [
            doc("Folha (PDF)",
                f"/api/v1/people-management/folha/{int(str(r[0])[:2])}/{int(str(r[0])[3:7])}/pdf"
                + (f"?condominio={r[6]}" if r[1] != "TOTAL GERAL" and r[6] else ""),
                fmt="pdf", gate="financeiro")])))
    if isinstance(out.get("folha-por-condominio"), dict):
        out["folha-por-condominio"]["filterCol"] = 0
        out["folha-por-condominio"]["filterLabel"] = "Competência"
        out["folha-por-condominio"]["cta"] = "Gerar folha (Conecta PRO)"
        out["folha-por-condominio"]["ctaTo"] = "folha-gerar"

    # ---- CADASTRAR CHAVE PIX (não existia caminho nenhum na tela) ----------------------
    # Quem está SEM chave vem primeiro na lista — é o que trava pagamento.
    _pix_opts: list[dict] = []
    try:
        from sqlalchemy import text as _pt
        _pix_opts = [
            {"value": str(r[0]),
             "label": f"{r[1]} — {r[2]}" + (f" · atual: {r[3]}" if r[3] else " · SEM CHAVE")}
            for r in (await db.execute(_pt(
                "SELECT CAST(id AS TEXT), nome, coalesce(cargo,'—'), nullif(pix_key,'') "
                "FROM employees "
                "WHERE coalesce(is_homologacao,false) = false "
                "  AND (status = 'ativo' OR lower(coalesce(tipo_contrato,'')) = 'pj') "
                "ORDER BY (nullif(pix_key,'') IS NOT NULL), nome"))).fetchall()]
    except Exception:  # noqa: BLE001
        _pix_opts = []

    out["cadastrar-pix-key"] = {
        "title": "Cadastrar chave PIX",
        "sub": "A chave define PARA ONDE VAI O SALÁRIO — por isso exige o código OTP enviado ao "
               "e-mail do Jordan. Quem está sem chave aparece no topo da lista. Confira o tipo: "
               "nem toda chave é CPF (há telefone, e-mail, CNPJ e aleatória).",
        "cta": "Gerar código de confirmação", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/cadastrar-pix-key", "gated": True,
                   "okMsg": "Chave PIX cadastrada"},
        "fields": [
            {"key": "employee_id", "label": "Colaborador*", "type": "select", "span": "span 2",
             "ph": "Selecione (os sem chave vêm primeiro)", "options": _pix_opts},
            {"key": "pix_key", "label": "Chave PIX*", "type": "text", "span": "span 1",
             "ph": "CPF, telefone (+55...), e-mail ou aleatória"},
            {"key": "pix_key_type", "label": "Tipo da chave*", "type": "select", "span": "span 1",
             "ph": "Detecta pelo formato se deixar em branco", "options": [
                 {"value": "CPF", "label": "CPF"}, {"value": "TELEFONE", "label": "Telefone"},
                 {"value": "EMAIL", "label": "E-mail"}, {"value": "CNPJ", "label": "CNPJ"},
                 {"value": "ALEATORIA", "label": "Aleatória"}]},
        ],
    }

    # ---- CHAVES PIX — TODA PESSOA CADASTRADA, DE TODAS AS FONTES ----------------------
    # As chaves moram em 4 lugares (CLT/PJ em employees, diaristas em diaria_diaristas,
    # agenda em financial_beneficiarios) e ninguém via o conjunto. Quem está SEM chave vem
    # primeiro: é a linha que trava pagamento. Caso real: Kelly e Alexandre viraram CLT e a
    # chave ficou só no cadastro de diarista — aqui as duas linhas aparecem lado a lado.
    await safe("chaves-pix", tbl(
        "Chaves PIX — pessoas cadastradas",
        "Todas as pessoas e suas chaves, de todas as origens (CLT, PJ, diaristas, agenda de "
        "beneficiários). Sem chave aparece no topo — é o que impede o pagamento. Use a busca "
        "para achar a mesma pessoa em outra origem.",
        "—", ["Pessoa", "Vínculo", "Documento", "Chave PIX", "Tipo", "Situação"],
        "1.9fr 1.1fr 1.2fr 1.7fr 0.8fr 0.9fr",
        """
        SELECT nome, vinculo, doc, chave, ordem, tipo_guardado FROM (
            SELECT e.nome AS nome, 'CLT' AS vinculo, coalesce(e.cpf,'—') AS doc,
                   coalesce(nullif(e.pix_key,''), nullif(e.pix,'')) AS chave,
                   CASE WHEN coalesce(nullif(e.pix_key,''), nullif(e.pix,'')) IS NULL THEN 0 ELSE 1 END AS ordem,
                   e.pix_key_type AS tipo_guardado
            FROM employees e
            WHERE e.status = 'ativo' AND coalesce(e.is_homologacao,false) = false
              AND coalesce(lower(e.tipo_contrato),'') <> 'pj'
            UNION ALL
            SELECT e.nome, 'PJ — ' || coalesce(e.papel_pj,'prestador'),
                   coalesce(nullif(e.cnpj,''), e.cpf, '—'),
                   coalesce(nullif(e.pix_key,''), nullif(e.pix,'')),
                   CASE WHEN coalesce(nullif(e.pix_key,''), nullif(e.pix,'')) IS NULL THEN 0 ELSE 1 END,
                   e.pix_key_type
            FROM employees e
            WHERE lower(coalesce(e.tipo_contrato,'')) = 'pj' AND coalesce(e.is_homologacao,false) = false
            UNION ALL
            SELECT d.nome, 'Diarista', coalesce(d.cpf,'—'), nullif(d.pix,''),
                   CASE WHEN nullif(d.pix,'') IS NULL THEN 0 ELSE 1 END, NULL
            FROM diaria_diaristas d WHERE coalesce(d.ativo,true) = true
            UNION ALL
            SELECT b.nome, 'Beneficiário' || coalesce(' — ' || nullif(b.categoria,''), ''),
                   coalesce(b.cpf_cnpj,'—'), nullif(b.chave_pix,''),
                   CASE WHEN nullif(b.chave_pix,'') IS NULL THEN 0 ELSE 1 END, b.tipo_chave
            FROM financial_beneficiarios b WHERE coalesce(b.ativo,true) = true
        ) u
        ORDER BY ordem, nome
        """,
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")),
                   t(r[1]), t(r[2] or "—"),
                   t(r[3] or "SEM CHAVE", 700 if not r[3] else 600,
                     "#DC2626" if not r[3] else _ND),
                   t(_tipo_pix(r[3], r[5]), 600, "#16277D"),
                   b("sem chave", "warn") if not r[3] else b("ok", "ok")]))
    if isinstance(out.get("chaves-pix"), dict):
        out["chaves-pix"]["filterCol"] = 1
        out["chaves-pix"]["filterLabel"] = "Vínculo"

    # ---- GERAR FOLHA NO CONECTA PRO (o que faltava: close_payroll nao persistia nada) ----
    # Opcoes = condominios que TEM gente alocada hoje (nao o cadastro inteiro), Villa dos
    # Passaros primeiro — e a ordem em que o Jordan fecha. Vazio => so a opcao "todos".
    _cond_opts: list[dict] = []
    try:
        from sqlalchemy import text as _ct
        _cond_opts = [
            {"value": str(r[0]), "label": f"{r[1]} ({r[2]} pessoa{'s' if r[2] != 1 else ''})"}
            for r in (await db.execute(_ct(
                "SELECT CAST(co.id AS TEXT), co.nome, count(DISTINCT a.employee_id) AS n "
                "FROM condominios co "
                "JOIN employee_alocacoes a ON a.condominio_id = co.id "
                "  AND (a.data_fim IS NULL OR a.data_fim >= CURRENT_DATE) "
                "JOIN employees e ON e.id = a.employee_id AND e.status = 'ativo' "
                "  AND coalesce(e.is_homologacao, false) = false "
                "GROUP BY 1, 2 "
                "ORDER BY (upper(co.nome) LIKE '%PASSAROS%' OR upper(co.nome) LIKE '%PÁSSAROS%') DESC, co.nome"
            ))).fetchall()]
    except Exception:  # noqa: BLE001 — sem opções o form ainda gera a folha geral
        _cond_opts = []

    out["folha-gerar"] = {
        "title": "Gerar folha (Conecta PRO)",
        "sub": "Escolha o condomínio para fechar posto a posto (formato Portte) ou deixe em branco para a folha geral. Calcula com o motor do Conecta PRO — lendo o ponto REAL "
               "sincronizado do Sólides — e GRAVA como rascunho. Não paga: o pagamento segue no "
               "Financeiro com OTP. Regerar o mesmo mês substitui a geração anterior; a folha da "
               "Portte nunca é tocada.",
        "cta": "Gerar folha", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/folha-gerar",
                   "okMsg": "Folha gerada",
                   "confirm": "Isto calcula e GRAVA a folha de todos os CLT ativos da competência "
                              "(rascunho). Regerar substitui a geração anterior. Confirmar?"},
        "fields": [
            {"key": "condominio_id", "label": "Condomínio", "type": "select", "span": "span 2",
             "ph": "Todos os condomínios (folha geral)", "options": _cond_opts},
            {"key": "mes", "label": "Mês*", "type": "select", "span": "span 1",
             "ph": "Selecione o mês", "options": [
                     {"value": "1", "label": "Janeiro"},
                     {"value": "2", "label": "Fevereiro"},
                     {"value": "3", "label": "Março"},
                     {"value": "4", "label": "Abril"},
                     {"value": "5", "label": "Maio"},
                     {"value": "6", "label": "Junho"},
                     {"value": "7", "label": "Julho"},
                     {"value": "8", "label": "Agosto"},
                     {"value": "9", "label": "Setembro"},
                     {"value": "10", "label": "Outubro"},
                     {"value": "11", "label": "Novembro"},
                     {"value": "12", "label": "Dezembro"}]},
            {"key": "ano", "label": "Ano*", "type": "select", "span": "span 1",
             "ph": "Selecione o ano", "options": [
                 {"value": "2026", "label": "2026"}, {"value": "2025", "label": "2025"}]},
        ],
    }

    # ---- PAREAMENTO Conecta x Portte (6 meses de operação em paralelo) ------------------
    # Comparacao pessoa a pessoa por competencia. So aparece quem existe em ALGUM dos dois
    # lados: FULL OUTER JOIN — quem so a Portte tem (rescisao, que o motor nao ve por filtrar
    # status='ativo') e quem so nos temos ficam VISIVEIS, que e justamente onde mora o erro.
    await safe("pareamento-folha", tbl(
        "Folha: Conecta × Portte",
        "Pareamento mês a mês da operação em paralelo. Δ verde = pagamos igual; vermelho = divergência "
        "a investigar. '(só Portte)' costuma ser rescisão — o motor do Conecta só calcula quem está ativo.",
        "—", ["Competência", "Colaborador", "Portte", "Conecta", "Δ", "Situação"],
        "0.9fr 1.9fr 1.1fr 1.1fr 1.1fr 1.2fr",
        """
        SELECT coalesce(pt.per, cn.per) AS comp,
               coalesce(e1.nome, e2.nome, '—') AS nome,
               pt.liq AS portte, cn.liq AS conecta,
               coalesce(cn.liq,0) - coalesce(pt.liq,0) AS delta,
               CASE WHEN pt.liq IS NULL THEN 'só Conecta'
                    WHEN cn.liq IS NULL THEN 'só Portte'
                    WHEN abs(coalesce(cn.liq,0) - coalesce(pt.liq,0)) <= 0.01 THEN 'igual'
                    ELSE 'divergente' END AS situacao
        FROM (SELECT employee_id, to_char(make_date(reference_year,reference_month,1),'MM/YYYY') AS per,
                     round(sum(net_salary)::numeric,2) AS liq
              FROM hr_payslips WHERE source_system='portte' GROUP BY 1,2) pt
        FULL OUTER JOIN
             (SELECT employee_id, to_char(make_date(reference_year,reference_month,1),'MM/YYYY') AS per,
                     round(sum(net_salary)::numeric,2) AS liq
              FROM hr_payslips WHERE source_system='conecta' GROUP BY 1,2) cn
          ON cn.employee_id = pt.employee_id AND cn.per = pt.per
        LEFT JOIN employees e1 ON e1.id = pt.employee_id
        LEFT JOIN employees e2 ON e2.id = cn.employee_id
        ORDER BY to_date(coalesce(pt.per, cn.per),'MM/YYYY') DESC,
                 abs(coalesce(cn.liq,0) - coalesce(pt.liq,0)) DESC,
                 2
        """,
        lambda r: [t(r[0] or "—", 600),
                   t(r[1], 600, _ND, initials(r[1] or "")),
                   t(brl(float(r[2])) if r[2] is not None else "—"),
                   t(brl(float(r[3])) if r[3] is not None else "—"),
                   t(brl(float(r[4] or 0)), 700,
                     "#16A34A" if abs(float(r[4] or 0)) <= 0.01 else "#DC2626"),
                   b(r[5], "ok" if r[5] == "igual" else ("warn" if r[5] == "divergente" else "info"))]))
    if isinstance(out.get("pareamento-folha"), dict):
        out["pareamento-folha"]["filterCol"] = 0
        out["pareamento-folha"]["filterLabel"] = "Competência"
        out["pareamento-folha"]["cta"] = "Gerar folha (Conecta PRO)"
        out["pareamento-folha"]["ctaTo"] = "folha-gerar"
    # Folha — docs de TELA (consolidada do mês + export Domínio), na última competência real
    try:
        from sqlalchemy import text as _sqltext
        _cmp = (await db.execute(_sqltext(
            "SELECT reference_month, reference_year FROM hr_payslips "
            "ORDER BY reference_year DESC, reference_month DESC LIMIT 1"))).first()
        if _cmp and out.get("folha"):
            _m, _a = int(_cmp[0]), int(_cmp[1])
            out["folha"]["docs"] = [
                doc("Folha consolidada (PDF)", f"/api/v1/people-management/folha/{_m}/{_a}/pdf", fmt="pdf", gate="financeiro"),
                doc("Export Domínio (TXT)", f"/api/v1/people-management/hr/payroll-export/dominio/{_a}-{_m:02d}", fmt="txt", gate="financeiro"),
            ]
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass

    # Não conformidades da folha — folhas com apontamento (contest_reason). Pré-fechamento; leitura.
    await safe("folha-nao-conformidades", tbl(
        "Não conformidades da folha", "Apontamentos pré-fechamento — quem fecha (Jordan/Pyetra) resolve antes", "—",
        ["Competência", "Colaborador", "Líquido", "Status", "Apontamento", "Registrado"],
        "0.9fr 1.7fr 1fr 0.9fr 2.4fr 1fr",
        "SELECT to_char(make_date(p.reference_year,p.reference_month,1),'MM/YYYY'), coalesce(e.nome,'—'), "
        "p.net_salary, p.status::text, p.contest_reason, p.contested_at "
        "FROM hr_payslips p LEFT JOIN employees e ON e.id=p.employee_id "
        "WHERE p.contest_reason IS NOT NULL ORDER BY p.contested_at DESC NULLS LAST LIMIT 300",
        lambda r: [t(r[0], 600, _ND), t(r[1] or "—", 600, _ND, initials(r[1] or "")), t(brl(r[2])),
                   _folha_status(r[3]), t((r[4] or "—")[:120]), t(str(r[5])[:16] if r[5] else "—")]))

    # Form "Apontar folha" — seleciona folha (draft/published) + motivo → /action/folha-apontamento
    try:
        from sqlalchemy import text as _sqltext_ap
        _ps = (await db.execute(_sqltext_ap(
            "SELECT CAST(p.id AS TEXT), to_char(make_date(p.reference_year,p.reference_month,1),'MM/YYYY'), "
            "coalesce(e.nome,'—'), p.net_salary FROM hr_payslips p LEFT JOIN employees e ON e.id=p.employee_id "
            "WHERE p.status::text IN ('draft','published') ORDER BY p.reference_year DESC, p.reference_month DESC, e.nome LIMIT 500"))).fetchall()
        out["folha-apontamento"] = {
            "title": "Apontar folha (não conformidade)", "sub": "Registra um apontamento pré-fechamento — não fecha nem paga",
            "cta": "Registrar apontamento", "type": "form",
            "submit": {"endpoint": "/api/v1/redesign/action/folha-apontamento", "okMsg": "Apontamento registrado"},
            "fields": [
                {"key": "payslip_id", "label": "Folha (competência · colaborador)*", "type": "select", "span": "span 2", "ph": "Selecione",
                 "options": [{"value": i, "label": f"{c} · {n} · {brl(v)}"} for i, c, n, v in _ps]},
                {"key": "motivo", "label": "Apontamento (não conformidade)*", "type": "textarea", "span": "span 2",
                 "ph": "Descreva a divergência (mín. 5 caracteres)…"}]}
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass

    # 0c) Férias — SOBRESCREVE p/ traduzir o status (redesign mostrava cru SUBMITTED/APPROVED)
    #     e trazer a data de solicitação, como o clássico. Status derivado igual ao clássico:
    #     cancelled_at→Cancelado; APPROVED→Aprovado; senão Pendente.
    # MESMA fonte do clássico (/hr/vacations = hr_vacation_requests), NÃO employee_vacation_requests
    # (que a base usava e tem outro dataset). Tipo constante "Férias"; status via _fer_status (APPROVED→Aprovado).
    await safe("ferias", tbl(
        "Gestão de Férias", "Solicitações de férias dos colaboradores", "—",
        ["Colaborador", "Tipo", "Período", "Dias", "Status", "Criado em"],
        "1.8fr 0.9fr 1.6fr 0.6fr 1fr 1.1fr",
        "SELECT e.nome, h.start_date, h.end_date, h.days_requested, h.status::text, h.cancelled_at, "
        "to_char(h.created_at AT TIME ZONE 'America/Manaus','DD/MM/YYYY HH24:MI') AS criado "
        "FROM hr_vacation_requests h LEFT JOIN employees e ON e.id=h.employee_id "
        "ORDER BY h.created_at DESC LIMIT 300",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t("Férias"),
                   t(f"{_d(r[1])} – {_d(r[2])}"), t(str(r[3] or "—")),
                   _fer_status(r[4], r[5]), t(r[6] or "—")]))

    # 0d) Benefícios — SOBRESCREVE p/ trazer operadora + valores (empresa/desconto) + vigência,
    #     que o clássico mostra e o redesign resumia (só tipo/plano/status). employee_benefits.
    # AÇÃO por-linha "Gerir" = altera SÓ o status do benefício (PATCH /benefits/{id} {status})
    # — Ativo/Suspenso/Cancelado. Single-field (sem risco de clobber/422 de data/float vazios).
    await safe("beneficios", tbl(
        "Gestão de Benefícios", "Benefícios por colaborador — operadora, valores e vigência", "—",
        ["Colaborador", "Tipo", "Operadora", "Plano", "Empresa", "Desconto", "Vigência", "Status"],
        "1.7fr 1.1fr 1.1fr 1.1fr 0.8fr 0.8fr 1.2fr 0.9fr",
        "SELECT e.nome, coalesce(bf.type,'—'), coalesce(bf.provider,'—'), coalesce(bf.plan_name,'—'), "
        "bf.company_contribution, bf.employee_contribution, bf.start_date, bf.end_date, "
        "coalesce(bf.status,'—'), CAST(bf.id AS TEXT) "
        "FROM employee_benefits bf LEFT JOIN employees e ON e.id=bf.employee_id ORDER BY e.nome, bf.type LIMIT 400",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(_ben_type(r[1])), t(r[2]), t(r[3]),
                   t(brl(r[4])), t(brl(r[5])),
                   t(f"{_d(r[6])} – {'Indeterminado' if not r[7] else _d(r[7])}"), _ben_status(r[8])],
        actionsfn=lambda r: [
            {
                "title": f"Benefício — {r[0] or '—'} ({_ben_type(r[1])})",
                "endpoint": f"/api/v1/people-management/hr/benefits/{r[9]}",
                "method": "PATCH", "btnLabel": "Gerir", "submitLabel": "Salvar status",
                "okMsg": "Benefício atualizado. Recarregue a tela.",
                "fields": [
                    {"key": "status", "label": "Status do benefício", "type": "select", "span": "span 2",
                     "value": (r[8] or "active"), "options": [
                         {"value": "active", "label": "Ativo"},
                         {"value": "suspended", "label": "Suspenso"},
                         {"value": "cancelled", "label": "Cancelado"}]},
                ]},
            {
                "title": f"Remover benefício — {r[0] or '—'}",
                "endpoint": f"/api/v1/people-management/hr/benefits/{r[9]}",
                "method": "DELETE", "btnLabel": "Remover", "btnStyle": "outline",
                "submitLabel": "Remover", "okMsg": "Benefício removido. Recarregue a tela.",
                "fields": []},
        ]))

    # 0e) Rescisão — SOBRESCREVE p/ ler de termination_processes (MESMA fonte do clássico
    #     /terminations), com Tipo/Status/Valor. A base lia employees WHERE status='demitido'
    #     (fonte errada, sem valores). Colunas iguais ao clássico: Colaborador/Tipo/Status/Último Dia/Valor.
    await safe("rescisao", _rescisao_screen(db))

    # 1) Admissão — admission_processes
    # AÇÃO por-linha "Concluir" (POST /admissions/{id}/complete) — CRIA o Employee e dispara
    # onboarding/GEDEON. Só p/ status ≠ cancelada/concluída. Form pré-preenchido do candidato
    # (nome/cpf/depto do processo); cargo/salário/datas o backend deriva da admissão + CCT.
    await safe("admissao", tbl(
        "Admissão", "Processos de admissão", "Nova admissão",
        ["Candidato", "CPF", "Cargo", "Departamento", "Início previsto", "Status"],
        "1.8fr 1.1fr 1.3fr 1.1fr 1fr 0.9fr",
        "SELECT coalesce(candidate_name,'—'), cpf, coalesce(position,'—'), "
        "coalesce(department,'—'), expected_start_date, coalesce(status,'—'), CAST(id AS TEXT) "
        "FROM admission_processes ORDER BY created_at DESC LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(_cpf_fmt(r[1])),
                   t(r[2]), t(r[3]), t(_d(r[4])), _adm_status(r[5])],
        editfn=lambda r: ({"title": f"Concluir admissão — {r[0] or '—'}",
                           "endpoint": f"/api/v1/people-management/hr/admissions/{r[6]}/complete",
                           "method": "POST", "btnLabel": "Concluir", "submitLabel": "Concluir admissão",
                           "btnStyle": "primary", "okMsg": "Admissão concluída — colaborador criado. Recarregue.",
                           "fields": [
                               {"key": "nome", "label": "Nome*", "type": "text", "span": "span 2", "value": r[0] or ""},
                               {"key": "cpf", "label": "CPF*", "type": "text", "span": "span 1", "value": r[1] or ""},
                               {"key": "departamento", "label": "Departamento", "type": "text", "span": "span 1",
                                "value": (r[3] if r[3] not in (None, "—") else "")},
                               {"key": "email", "label": "E-mail", "type": "text", "span": "span 1", "value": ""},
                               {"key": "telefone", "label": "Telefone", "type": "text", "span": "span 1", "value": ""},
                               {"key": "matricula", "label": "Matrícula", "type": "text", "span": "span 1", "value": ""},
                           ]}
                          if (r[5] or "").lower() not in ("cancelled", "cancelada", "completed", "concluida", "concluída") else None)))

    # 2) Aviso prévio — employees em aviso (query real; hoje 0 = honesto "nenhum")
    await safe("aviso-previo", tbl(
        "Aviso prévio", "Colaboradores em aviso prévio", "—",
        ["Colaborador", "Cargo", "Admissão", "Situação"],
        "2fr 1.4fr 1fr 0.9fr",
        "SELECT nome, coalesce(cargo,'—'), data_admissao, status::text "
        "FROM employees WHERE status IN ('aviso_previo','aviso') ORDER BY nome LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(r[1]),
                   t(_d(r[2])), _badge_status(r[3])]))

    # 3) Ponto — gp_clock_punches
    # Ponto — registro DIÁRIO como o clássico (/hr/time-records): batidas de gp_clock_punches
    # pareadas por (colaborador, dia) → Entrada/Saída/Total. Não 1 linha por batida. Exclui homologação.
    # punch_timestamp é Manaus-local naive (writers usam now()) → NÃO converter fuso.
    _ENT = "lower(coalesce(punch_type,'')) LIKE 'entrada%'"
    _SAI = "(lower(coalesce(punch_type,'')) LIKE 'saida%' OR lower(coalesce(punch_type,'')) LIKE 'saída%')"
    await safe("ponto", tbl(
        "Ponto", "Registros diários — entrada, saída e total", "—",
        ["Colaborador", "Data", "Entrada", "Saída", "Total Horas"],
        "2fr 1fr 0.9fr 0.9fr 1fr",
        # Pareamento por JORNADA, não por data de calendário. O 12x36 NOTURNO entra ~19h do
        # dia D e sai ~07h do dia D+1; agrupar por `punch_timestamp::date` PARTIA a jornada em
        # dois "dias furados" (medido: só 9% dos dias do noturno apareciam pareados, e a coluna
        # Saída mostrava "--:--"). Parear batidas alternadas (1ª→2ª, 3ª→4ª) atravessa a
        # meia-noite: os furos reais caem de ~840 batidas para 29.
        "SELECT e.nome, d.dia, d.entrada, d.saida, d.total_min, CAST(d.employee_id AS TEXT) FROM ("
        "  SELECT employee_id, (min(ts))::date AS dia, min(ts) AS entrada, "
        "         CASE WHEN count(*) > 1 THEN max(ts) END AS saida, "
        "         CASE WHEN count(*) > 1 THEN (extract(epoch FROM (max(ts)-min(ts)))/60)::int END AS total_min "
        "  FROM ("
        "    SELECT employee_id, punch_timestamp AS ts, "
        "           row_number() OVER (PARTITION BY employee_id ORDER BY punch_timestamp) AS rn "
        "    FROM gp_clock_punches "
        "    WHERE employee_id NOT IN (SELECT id FROM employees WHERE coalesce(is_homologacao,false)=true)"
        "  ) o GROUP BY employee_id, (rn+1)/2"
        ") d LEFT JOIN employees e ON e.id = d.employee_id "
        "ORDER BY d.entrada DESC, e.nome LIMIT 300",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(_d(r[1])),
                   t(r[2].strftime("%H:%M") if r[2] else "--:--"),
                   t(r[3].strftime("%H:%M") if r[3] else "--:--"),
                   t(_hm(r[4]) if (r[4] is not None and r[4] > 0) else "--:--")],
        # AÇÃO por-linha: ajuste de ponto do DP. Grava batida REAL em gp_clock_punches
        # (device_type='ajuste_dp') — a MESMA tabela que esta tela lê. Vai pelo proxy
        # /redesign/action/ponto-ajuste porque `ajustado_por` tem que ser a identidade
        # REAL do usuário logado (nunca chumbada no builder).
        editfn=lambda r: {
            "title": f"Ajustar ponto — {r[0] or '—'} ({_d(r[1])})",
            "endpoint": f"/api/v1/redesign/action/ponto-ajuste?eid={r[5]}&dia={r[1]}",
            "method": "POST", "btnLabel": "Ajustar", "submitLabel": "Registrar ajuste",
            "okMsg": "Ajuste registrado. Recarregue a tela.",
            "fields": [
                {"key": "punch_type", "label": "Tipo*", "type": "select", "span": "span 1",
                 "ph": "Selecione", "options": [{"value": "entrada", "label": "Entrada"},
                                                {"value": "saida", "label": "Saída"}]},
                {"key": "hora", "label": "Hora (HH:MM)*", "type": "text", "span": "span 1", "value": ""},
                {"key": "motivo", "label": "Motivo (mín. 5 caracteres)*", "type": "textarea",
                 "span": "span 2", "value": ""},
            ],
        }))

    # 4) Fechamento de ponto — MESMA fonte do clássico (time_sheets via painel_fechamento), NÃO
    #    gp_monthly_closings. Última competência com dado; status derivado (Homologado/Aguardando
    #    assinatura/Fechado/N anomalia(s)/Calculado). Assinatura via sig_signature_requests. Exclui homologação.
    await safe("fechamento-ponto", tbl(
        "Fechamento de ponto", "Espelhos mensais — última competência", "—",
        ["Colaborador", "Posto", "Horas", "Extras", "Faltas", "Status"],
        "1.8fr 1.4fr 1fr 1fr 0.8fr 1.3fr",
        "SELECT ts.employee_name, coalesce(ts.condominium_name,'—'), ts.reference_year, ts.status, "
        "ts.hours_worked_minutes, ts.overtime_total_minutes, ts.absent_days, "
        "greatest(coalesce(ts.anomaly_count,0)-coalesce(ts.anomaly_resolved_count,0),0) AS anomalias, "
        "ts.approved_by_employee, sig.status AS sig_status, sig.signed_at AS sig_signed, "
        "CAST(ts.employee_id AS TEXT) AS emp, ts.reference_month AS mes, "
        # has_punches: só oferece a Folha de ponto (batidas) quando há batida na competência
        # (o endpoint folha-pdf 404 se vazio) — botão honesto, nunca quebrado.
        "EXISTS(SELECT 1 FROM gp_clock_punches gcp WHERE CAST(gcp.employee_id AS TEXT)=CAST(ts.employee_id AS TEXT) "
        "  AND to_char(gcp.punch_timestamp,'MM.YYYY')=to_char(make_date(ts.reference_year::int, ts.reference_month::int, 1),'MM.YYYY')) AS has_punches "
        "FROM time_sheets ts "
        "LEFT JOIN LATERAL (SELECT status, signed_at FROM sig_signature_requests s "
        "  WHERE s.document_type='espelho_ponto' AND s.signer_type='employee' "
        "  AND (CAST(s.document_id AS TEXT)=CAST(ts.id AS TEXT) "
        "       OR s.custom_fields->>'document_id_raw'=CAST(ts.id AS TEXT)) "
        "  ORDER BY s.created_at DESC LIMIT 1) sig ON true "
        "WHERE coalesce(ts.is_deleted,false)=false "
        "  AND (ts.reference_year, ts.reference_month) = (SELECT reference_year, reference_month "
        "       FROM time_sheets WHERE coalesce(is_deleted,false)=false "
        "       ORDER BY reference_year DESC, reference_month DESC LIMIT 1) "
        "  AND ts.employee_id NOT IN (SELECT CAST(id AS TEXT) FROM employees WHERE coalesce(is_homologacao,false)=true) "
        "ORDER BY ts.employee_name LIMIT 300",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")),
                   t(r[1] or "—"), t(_hm(r[4])), t(_hm(r[5])),
                   t(str(r[6] or 0)), _fech_status(r[3], r[7], r[8], r[9], r[10])],
        docsfn=lambda r: [doc("Espelho de ponto (671)", f"/api/v1/people-management/hr/ponto/espelho/{r[11]}/{r[12]}/{r[2]}/pdf", fmt="pdf", gate="dp")]
        + ([doc("Folha de ponto (batidas)", f"/api/v1/people-management/ponto/folha-pdf/{r[11]}/download?mes_ref={int(r[12]):02d}.{int(r[2])}", fmt="html", gate="dp")] if r[13] else [])))

    # 5) Licenças / afastamentos — sst_afastamentos (nome/cargo denormalizados)
    # AÇÃO por-linha "Propor transmissão eSocial (S-2230)": afastamento = fonte do S-2230.
    # Chama o hook do T1 (propor→sino→humano aprova+OTP+transmite no fluxo SST). SÓ PROPÕE,
    # NUNCA transmite. referencia = id do afastamento (idempotência c/ tipo_evento); empresa
    # derivada do colaborador (só mostra o botão se houver empresa). Gate=T3/T1 (Fase 5.4).
    await safe("licencas", tbl(
        "Licenças", "Afastamentos e licenças", "—",
        ["Colaborador", "Tipo", "CID", "Início", "Status"],
        "2fr 1.2fr 0.8fr 1fr 0.9fr",
        "SELECT coalesce(a.employee_nome,'—'), coalesce(a.tipo,'—'), coalesce(a.cid,'—'), "
        "a.data_inicio, coalesce(a.status,'—'), CAST(a.id AS TEXT), CAST(e.empresa_id AS TEXT), "
        "CAST(a.employee_id AS TEXT) FROM sst_afastamentos a "
        "LEFT JOIN employees e ON e.id = a.employee_id "
        "ORDER BY a.data_inicio DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")),
                   t((r[1] or "—").replace("_", " ")), t(r[2]), t(_d(r[3])),
                   _lic_status(r[4])],
        actionsfn=lambda r: ([{
            "title": f"Propor transmissão eSocial (S-2230) — {r[0] or '—'}",
            "endpoint": "/api/v1/consultores/mcp/propor-esocial-sst",
            "method": "POST", "btnLabel": "Propor eSocial", "btnStyle": "outline",
            "submitLabel": "Propor transmissão",
            "okMsg": "Proposta enviada ao sino — aguardando aprovação humana. Nada foi transmitido ao governo.",
            "fixed": {"tipo_evento": "S-2230", "referencia": f"afast-{r[5]}",
                      "empresa_id": r[6], "employee_id": r[7]},
            "fields": []}] if r[6] else None)))

    # 6) Reembolsos — reimbursement_requests
    # Reembolsos — reimbursement_requests. AÇÕES por-linha "Aprovar" + "Analisar" só p/ status 'pendente'
    # (POST /reimbursements/{id}/approve → move p/ 'aprovado'; POST /reimbursements/{id}/analyze → move p/ 'em_analise';
    # NÃO paga — pagamento é passo separado, OTP-gated, T1). Mesma tabela do display e do endpoint (id bate, sem mismatch).
    # Anexos (attachments) deferred — reimbursement_attachments vazio (0 rows); docsfn/upload adiam para T4 refine.
    await safe("reembolsos", tbl(
        "Reembolsos", "Solicitações de reembolso", "Solicitar reembolso",
        ["Código", "Título", "Valor", "Enviado", "Status"],
        "0.9fr 2fr 1fr 1fr 0.9fr",
        "SELECT coalesce(code,'—'), coalesce(title,'—'), coalesce(total_amount,0), "
        "submitted_at, coalesce(status,'—'), CAST(id AS TEXT) FROM reimbursement_requests "
        "WHERE coalesce(is_active,true) ORDER BY created_at DESC LIMIT 200",
        lambda r: [t(r[0]), t(r[1] or "—", 600, _ND), t(brl(r[2]), 600),
                   t(_d(r[3])), _rei_status(r[4])],
        actionsfn=lambda r: (
            [
                {"title": f"Aprovar reembolso {r[0]}",
                 "endpoint": f"/api/v1/redesign/action/reembolso-aprovar?rid={r[5]}",
                 "method": "POST", "btnLabel": "Aprovar", "submitLabel": "Aprovar",
                 "btnStyle": "primary", "okMsg": "Reembolso aprovado. Recarregue a tela.",
                 "fields": []},
                {"title": f"Analisar reembolso {r[0]}",
                 "endpoint": f"/api/v1/redesign/action/reembolso-analisar?rid={r[5]}",
                 "method": "POST", "btnLabel": "Analisar", "btnStyle": "outline",
                 "submitLabel": "Analisar", "okMsg": "Reembolso em análise. Recarregue a tela.",
                 "fields": []},
                {"title": f"Rejeitar reembolso {r[0]}",
                 "endpoint": f"/api/v1/redesign/action/reembolso-rejeitar?rid={r[5]}",
                 "method": "POST", "btnLabel": "Rejeitar", "btnStyle": "outline",
                 "submitLabel": "Rejeitar", "okMsg": "Reembolso rejeitado. Recarregue a tela.",
                 "fields": [{"key": "reason", "label": "Motivo (obrigatório)", "type": "textarea", "span": "span 2", "value": ""}]},
            ] if (r[4] or "").lower() == "pendente" else None)))

    # 7) Contratos — employment_contracts
    # AÇÕES por-linha "Gerar contrato" + "Gerar aviso-prévio de férias": geradores de documento
    # (POST /contracts/employee/{employee_id}/gerar-*-html → salva HTML em /uploads e devolve ref).
    # O doc gerado fica disponível no fluxo de download; sucesso confirma. employee_id = r[7].
    await safe("contratos", tbl(
        "Contratos", "Contratos de trabalho", "—",
        ["Colaborador", "Tipo", "Cargo", "Início", "Salário base", "Vigente"],
        "1.8fr 1fr 1.3fr 1fr 1fr 0.8fr",
        "SELECT coalesce(e.nome,'—'), coalesce(c.type,'—'), coalesce(c.job_title,'—'), "
        "c.start_date, coalesce(c.base_salary,0), coalesce(c.is_current,false), CAST(c.id AS TEXT), "
        "CAST(c.employee_id AS TEXT) "
        "FROM employment_contracts c LEFT JOIN employees e ON e.id = c.employee_id "
        "ORDER BY c.start_date DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(_contract_type(r[1])), t(r[2]),
                   t(_d(r[3])), t(brl(r[4])),
                   _badge_bool(r[5], "Vigente", "Encerrado", "ok", "mut")],
        docsfn=lambda r: [doc("Contrato CLT", f"/api/v1/people-management/hr/contracts/{r[6]}/pdf", fmt="pdf", gate="dp")],
        actionsfn=lambda r: ([
            {"title": f"Gerar contrato de trabalho — {r[0] or '—'}",
             "endpoint": f"/api/v1/people-management/hr/contracts/employee/{r[7]}/gerar-contrato-html",
             "method": "POST", "btnLabel": "Gerar contrato", "btnStyle": "outline",
             "submitLabel": "Gerar contrato", "okMsg": "Contrato gerado — disponível no download/GED.", "fields": []},
            {"title": f"Gerar aviso-prévio de férias — {r[0] or '—'}",
             "endpoint": f"/api/v1/people-management/hr/contracts/employee/{r[7]}/gerar-aviso-previo-ferias-html",
             "method": "POST", "btnLabel": "Gerar aviso férias", "btnStyle": "outline",
             "submitLabel": "Gerar aviso", "okMsg": "Aviso-prévio de férias gerado.", "fields": []},
        ] if r[7] else None)))

    # 8) Documentos — hr_employee_documents
    await safe("documentos", tbl(
        "Documentos", "Documentos dos colaboradores", "—",
        ["Colaborador", "Documento", "Tipo", "Status", "Publicado"],
        "1.6fr 1.8fr 1fr 0.9fr 0.8fr",
        "SELECT coalesce(e.nome,'—'), coalesce(d.title, d.file_name, '—'), "
        "coalesce(d.document_type,'—'), coalesce(d.status,'—'), coalesce(d.is_published,false), "
        "CAST(d.id AS TEXT), nullif(trim(coalesce(d.file_path,'')),'') "
        "FROM hr_employee_documents d LEFT JOIN employees e ON e.id = d.employee_id "
        "ORDER BY d.created_at DESC LIMIT 300",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(r[1]),
                   t((r[2] or "—").replace("_", " ")), _doc_status(r[3]),
                   _badge_bool(r[4], "Sim", "Não", "ok", "mut")],
        docsfn=lambda r: ([doc("Documento", f"/api/v1/people-management/hr/documents/{r[5]}/download", fmt="pdf", gate="dp")]
                          if r[6] else [])))

    # 9) Certificação — hr_certifications (certificação de cálculos DP)
    # AÇÃO por-linha "Certificar" (PATCH /certifications/{id}/certify) só p/ status 'pendente'.
    # Assinatura humana (rastreável: quem/quando/hash). RBAC CERTIFIER_ROLES é imposto no backend.
    await safe("certificacao", tbl(
        "Certificação", "Certificação de cálculos", "—",
        ["Competência", "Tipo de cálculo", "Valor", "Divergência", "Status"],
        "1fr 1.6fr 1fr 1fr 0.9fr",
        "SELECT coalesce(competencia,'—'), coalesce(tipo_calculo,'—'), "
        "coalesce(calculado_valor,0), coalesce(divergencia,false), coalesce(status,'—'), CAST(id AS TEXT) "
        "FROM hr_certifications ORDER BY competencia DESC NULLS LAST, created_at DESC LIMIT 300",
        lambda r: [t(r[0]), t((r[1] or "—").replace("_", " ")), t(brl(r[2])),
                   _badge_bool(r[3], "Sim", "Não", "bad", "ok"), _cert_status(r[4])],
        actionsfn=lambda r: (
            [
                {"title": f"Certificar — {r[0]} · {(r[1] or '').replace('_', ' ')}",
                 "endpoint": f"/api/v1/people-management/certifications/{r[5]}/certify",
                 "method": "PATCH", "btnLabel": "Certificar", "submitLabel": "Assinar certificação",
                 "btnStyle": "primary", "okMsg": "Certificação assinada. Recarregue a tela.",
                 "fields": [{"key": "observacao", "label": "Observação (opcional)",
                             "type": "textarea", "span": "span 2", "value": ""}]},
                {"title": f"Rejeitar certificação — {r[0]}",
                 "endpoint": f"/api/v1/people-management/certifications/{r[5]}/reject",
                 "method": "PATCH", "btnLabel": "Rejeitar", "btnStyle": "outline",
                 "submitLabel": "Rejeitar", "okMsg": "Certificação rejeitada. Recarregue a tela.",
                 "fields": [{"key": "observacao", "label": "Motivo (obrigatório)", "type": "textarea",
                             "span": "span 2", "value": ""}]}
            ] if (r[4] or "").lower() == "pendente" else None)))

    # 10) eSocial — esocial_eventos_espelho (espelho do ambiente nacional)
    await safe("esocial", tbl(
        "eSocial", "Eventos transmitidos (espelho)", "Sincronizar espelho",
        ["Evento", "Tipo", "Colaborador", "CPF", "Data evento", "Recibo"],
        "1.2fr 0.8fr 1.6fr 1.1fr 1fr 1.4fr",
        "SELECT coalesce(ev.id_evento,'—'), coalesce(ev.tipo,'—'), e.nome, ev.cpf_trabalhador, "
        "ev.dt_evento, coalesce(ev.nr_recibo,'—') FROM esocial_eventos_espelho ev "
        "LEFT JOIN employees e ON regexp_replace(coalesce(e.cpf,''),'\\D','','g') "
        "= regexp_replace(coalesce(ev.cpf_trabalhador,''),'\\D','','g') "
        "ORDER BY ev.dt_evento DESC NULLS LAST, ev.dt_recepcao DESC NULLS LAST LIMIT 300",
        lambda r: [t(r[0], 600, _ND), t(r[1]),
                   t(r[2] or "—", 600, _ND, initials(r[2] or "")), t(_cpf_fmt(r[3])),
                   t(_d(r[4])), t(r[5])]))
    # eSocial — XML transmitido, mas SEM rota de preview/download no backend (só POST evento).
    # Honesto: botão desabilitado até o backend expor GET do XML (sinalizado ao orquestrador).
    if out.get("esocial"):
        out["esocial"]["docs"] = [doc("XML do evento", disabled=True,
                                      motivo="XML transmitido, sem rota de preview no backend — pendente criar GET do XML do evento")]
        # CTA real: sincroniza o espelho do ambiente nacional — repovoa ESTA MESMA tabela
        # (esocial_eventos_espelho). Enfileira Celery em gov.esocial; não transmite nada ao gov.
        out["esocial"]["ctaTo"] = "sincronizar-esocial"
    # beneficios-cct — a tela base (monólito) é read-only. Ganha CTA de CRIAR benefício:
    # POST /admin/cct/convencoes/{id}/beneficios grava em cct_beneficios (a MESMA tabela lida).
    # convencao_id resolvido do banco (vigente), nunca chumbado — sobrevive à troca de CCT.
    # NÃO há PUT/PATCH/DELETE de benefício no backend → sem ação por-linha (seria inventar rota).
    from sqlalchemy import text as _sqltext_cct

    _conv = (await db.execute(_sqltext_cct(
        "SELECT CAST(id AS TEXT), sindicato_trabalhadores, registro_mte FROM cct_convencoes "
        "WHERE coalesce(is_vigente,false) AND coalesce(is_active,false) "
        "ORDER BY data_inicio DESC LIMIT 1"
    ))).first()
    if _conv and out.get("beneficios-cct"):
        out["beneficios-cct"]["ctaTo"] = "novo-beneficio-cct"
        out["beneficios-cct"]["cta"] = "Adicionar benefício"
        out["novo-beneficio-cct"] = {
            "title": "Adicionar benefício da CCT", "type": "form",
            "sub": f"Convenção vigente: {_conv[1]} · {_conv[2]}",
            "cta": "Adicionar",
            "submit": {"endpoint": f"/api/v1/people-management/admin/cct/convencoes/{_conv[0]}/beneficios",
                       "okMsg": "Benefício adicionado à CCT"},
            "fields": [
                {"key": "tipo_beneficio", "label": "Tipo de benefício*", "type": "text", "span": "span 2",
                 "value": "", "ph": "ex.: Vale alimentação"},
                {"key": "valor_minimo", "label": "Valor mínimo (R$)", "type": "text", "span": "span 1", "value": ""},
                {"key": "valor_empresa", "label": "Valor empresa (R$)", "type": "text", "span": "span 1", "value": ""},
                {"key": "desconto_maximo_percentual", "label": "Desconto máx. (%)", "type": "text",
                 "span": "span 1", "value": ""},
                {"key": "obrigatorio", "label": "Obrigatório", "type": "select", "span": "span 1",
                 "options": [{"value": "true", "label": "Sim"}, {"value": "false", "label": "Não"}]},
                {"key": "observacao", "label": "Observação", "type": "textarea", "span": "span 2", "value": ""},
            ],
        }

    out["sincronizar-esocial"] = {
        "title": "Sincronizar espelho eSocial", "type": "form",
        "sub": "Baixa do ambiente nacional os eventos já transmitidos e repovoa a tela de eSocial. "
               "Leitura apenas — não transmite nada ao governo.",
        "cta": "Sincronizar",
        "submit": {"endpoint": "/api/v1/government/esocial/espelho/sincronizar",
                   "okMsg": "Sincronização enfileirada — recarregue a tela em alguns minutos"},
        "fields": [
            {"key": "periodo", "label": "Período (AAAA ou AAAA-MM)", "type": "text", "span": "span 1",
             "value": str(__import__("datetime").date.today().year)},
            {"key": "max_acessos", "label": "Máx. acessos simultâneos (1-10)", "type": "text",
             "span": "span 1", "value": "8"},
        ],
    }

    # ── Task 7: Prestadores PJ — GERADOR de link de autocadastro (RH/admin). Lê a MESMA fonte do
    #    endpoint clássico (GET /prestadores-pj): employees tipo_contrato='pj' com token gerado.
    #    AÇÃO por-linha "Regenerar link" (POST .../{id}/regenerar-link, sem body) — útil se o link
    #    vazou; o backend recusa se já concluído (pj_ativo), então a ação some pra esses (honesto,
    #    evita 409 óbvio). CTA da tela abre o form de cadastro (ctaTo="novo-prestador-pj").
    await safe("prestadores-pj", tbl(
        "Prestadores PJ", "Prestadores PJ com link de autocadastro gerado", "Novo prestador",
        ["Prestador", "Papel", "Empresa", "Status", "CNPJ", "Cadastro"],
        "2fr 1.1fr 1.3fr 1fr 1.1fr 1fr",
        "SELECT e.id::text, e.nome, coalesce(e.papel_pj,'—'), coalesce(e.status,'—'), "
        "coalesce(e.cnpj, case when e.cnpj_pendente then 'pendente' else '—' end), "
        "e.autocadastro_token, coalesce(emp.nome_fantasia,'—'), e.created_at "
        "FROM employees e LEFT JOIN empresas emp ON emp.id=e.empresa_id "
        "WHERE e.tipo_contrato='pj' AND e.autocadastro_token IS NOT NULL "
        "ORDER BY e.created_at DESC NULLS LAST LIMIT 300",
        lambda r: [t(r[1] or "—", 600, _ND, initials(r[1] or "")), t(r[2]), t(r[6]),
                   _pj_status(r[3]), t(r[4]), t(_d(r[7]))],
        actionsfn=lambda r: (
            [{"title": f"Regenerar link — {r[1] or '—'}",
              "endpoint": f"/api/v1/people-management/human-resources/prestadores-pj/{r[0]}/regenerar-link",
              "method": "POST", "btnLabel": "Regenerar link", "btnStyle": "outline",
              "submitLabel": "Regenerar link",
              "okMsg": "Link regenerado. Recarregue a tela.", "fields": []}]
            if (r[3] or "").lower() != "pj_ativo" else None)))
    if out.get("prestadores-pj"):
        out["prestadores-pj"]["ctaTo"] = "novo-prestador-pj"

    # Novo prestador PJ — form (POST /prestadores-pj, NovoPrestadorBody: nome*/empresa*/papel/cpf).
    # empresa = slug fixo (_EMPRESAS no controller) — 2 opções reais (Eletrônica/Patrimonial), o
    # backend seta empresa_id EXPLÍCITO (nunca o DEFAULT cego). Devolve o link pronto (gerado no
    # backend); a tela recarrega e o prestador aparece na tabela acima com o link pra recopiar.
    out["novo-prestador-pj"] = {
        "title": "Novo prestador PJ", "type": "form",
        "sub": "Cadastra um prestador PJ e gera o link de autocadastro",
        "cta": "Cadastrar",
        "submit": {"endpoint": "/api/v1/people-management/human-resources/prestadores-pj",
                   "okMsg": "Prestador cadastrado"},
        "fields": [
            {"key": "nome", "label": "Nome*", "type": "text", "span": "span 2", "ph": "Nome completo"},
            {"key": "empresa", "label": "Empresa*", "type": "select", "span": "span 1", "ph": "Selecione",
             "options": [
                 {"value": "eletronica", "label": "Conecta Mais Eletrônica"},
                 {"value": "patrimonial", "label": "Conecta Mais Patrimonial"},
             ]},
            {"key": "papel", "label": "Papel/Função", "type": "text", "span": "span 1", "ph": "Opcional"},
            {"key": "cpf", "label": "CPF", "type": "text", "span": "span 1", "ph": "Opcional"},
        ],
    }

    # Aviso prévio de férias (form → gera doc). Só férias FUTURAS aprovadas/submetidas (o gerador
    # recusa data no passado). Select value = 'empId|YYYY-MM-DD|dias' → POST /redesign/action/aviso-
    # ferias → retorna {doc} p/ o FormScreen abrir (gancho d.doc). Sem digitação livre: dados reais
    # de hr_vacation_requests. Se não há férias futura, o select fica vazio (honesto, não fabrica).
    try:
        from sqlalchemy import text as _sqltext
        # Janela: férias recentes (últimos 120 dias) + futuras, aprovadas/submetidas. O gerador
        # aceita data passada (registro formal), então incluímos as já iniciadas (ex.: Francisco).
        _avf = (await db.execute(_sqltext(
            "SELECT v.employee_id, coalesce(e.nome,'—'), v.start_date, coalesce(v.days_requested,30) "
            "FROM hr_vacation_requests v LEFT JOIN employees e ON e.id=v.employee_id "
            "WHERE v.start_date IS NOT NULL "
            "AND v.start_date >= (now() AT TIME ZONE 'America/Manaus')::date - INTERVAL '120 days' "
            "AND upper(coalesce(v.status,'')) IN ('APPROVED','SUBMITTED') "
            "ORDER BY v.start_date DESC LIMIT 200"))).fetchall()
        _opts = [{"value": f"{r[0]}|{r[2].strftime('%Y-%m-%d')}|{int(r[3])}",
                  "label": f"{r[1]} · início {r[2].strftime('%d/%m/%Y')} · {int(r[3])}d"} for r in _avf]
        out["aviso-ferias"] = {
            "title": "Aviso prévio de férias",
            "sub": "Gera o Aviso Prévio de Férias (HTML) de uma férias aprovada — dados reais, abre ao gerar",
            "cta": "Gerar aviso", "type": "form",
            "submit": {"endpoint": "/api/v1/redesign/action/aviso-ferias", "okMsg": "Aviso prévio de férias gerado"},
            "fields": [
                {"key": "ferias", "label": "Férias (recentes e próximas)*", "type": "select", "span": "span 2",
                 "ph": "Selecione a férias" if _opts else "Nenhuma férias aprovada/submetida nos últimos 120 dias",
                 "options": _opts},
            ],
        }
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass

    # Contracheques em lote (AÇÃO de efeito em massa: gera PDF de todos os ativos + arquiva GED +
    # publica eventos). Vai atrás de CONFIRMAÇÃO humana (submit.confirm). Competências = as que têm
    # folha (hr_payslips). Ligado ao fix do filtro status (case-insensitive) no payroll_export.
    try:
        from sqlalchemy import text as _sqltext
        _comps = (await db.execute(_sqltext(
            "SELECT DISTINCT reference_year, reference_month FROM hr_payslips "
            "WHERE reference_year IS NOT NULL "
            "ORDER BY reference_year DESC, reference_month DESC LIMIT 12"))).fetchall()
        _copts = [{"value": f"{int(r[0])}-{int(r[1]):02d}", "label": f"{int(r[1]):02d}/{int(r[0])}"} for r in _comps]
        out["contracheques-lote"] = {
            "title": "Contracheques em lote",
            "sub": "Gera o contracheque (PDF) de TODOS os funcionários ativos da competência e arquiva no GED",
            "cta": "Gerar contracheques", "type": "form",
            "submit": {"endpoint": "/api/v1/redesign/action/contracheques-batch",
                       "okMsg": "Contracheques gerados",
                       "confirm": "Isto gera o contracheque de TODOS os ativos da competência e arquiva no GED"},
            "fields": [
                {"key": "competencia", "label": "Competência*", "type": "select", "span": "span 2",
                 "ph": "Selecione a competência" if _copts else "Sem competência com folha registrada",
                 "options": _copts},
            ],
        }

        # ── Task 8: Fechar mês de ponto (AÇÃO de efeito em massa, irreversível).
        # Closes the timekeeping month for all active employees. Requires confirmation before firing.
        # Mês/ano são selects fixos (NÃO usa _copts) — a competência de ponto independe da folha.
        out["fechar-mes-ponto"] = {
            "title": "Fechar mês (ponto)",
            "sub": "Fecha o ponto de TODOS os colaboradores ativos na competência — ação de efeito em massa, praticamente irreversível. Horários no fuso de Manaus (UTC no banco).",
            "cta": "Fechar mês", "type": "form",
            "submit": {"endpoint": "/api/v1/people-management/ponto/fechamento-mes",
                       "okMsg": "Mês de ponto fechado",
                       "confirm": "Isto FECHA o ponto de TODOS os ativos na competência selecionada. Confirme para prosseguir."},
            "fields": [
                {"key": "mes", "label": "Mês*", "type": "select", "span": "span 1",
                 "ph": "Selecione o mês", "options": [
                     {"value": "1", "label": "Janeiro"}, {"value": "2", "label": "Fevereiro"},
                     {"value": "3", "label": "Março"}, {"value": "4", "label": "Abril"},
                     {"value": "5", "label": "Maio"}, {"value": "6", "label": "Junho"},
                     {"value": "7", "label": "Julho"}, {"value": "8", "label": "Agosto"},
                     {"value": "9", "label": "Setembro"}, {"value": "10", "label": "Outubro"},
                     {"value": "11", "label": "Novembro"}, {"value": "12", "label": "Dezembro"}]},
                {"key": "ano", "label": "Ano*", "type": "select", "span": "span 1",
                 "ph": "Selecione o ano", "options": [
                     {"value": "2026", "label": "2026"}, {"value": "2025", "label": "2025"}]},
            ],
        }

        # Gerar certificações em lote (fila hr_certifications de TODOS os holerites da competência,
        # idempotente). Mesma lista de competências com folha (_copts, já buscada acima). AÇÃO de
        # efeito em massa → confirmação humana (submit.confirm), handler fino rd_action_cert_gerar_folha.
        out["gerar-certificacoes"] = {
            "title": "Gerar certificações",
            "sub": "Gera a fila de certificações da folha de uma competência (idempotente)",
            "cta": "Gerar", "type": "form",
            "submit": {"endpoint": "/api/v1/redesign/action/cert-gerar-folha",
                       "okMsg": "Certificações geradas",
                       "confirm": "Isto gera a fila de certificações de TODOS os holerites da competência"},
            "fields": [
                {"key": "competencia", "label": "Competência*", "type": "select", "span": "span 2",
                 "ph": "Selecione a competência" if _copts else "Sem competência com folha registrada",
                 "options": _copts},
            ],
        }
        # Nova certificação avulsa (C5) — cria uma certificação de um cálculo p/ a fila de assinatura.
        out["nova-certificacao"] = {
            "title": "Nova certificação", "type": "form",
            "sub": "Cria uma certificação avulsa de um cálculo (entra na fila de assinatura humana)",
            "cta": "Criar certificação",
            "submit": {"endpoint": "/api/v1/people-management/certifications", "okMsg": "Certificação criada"},
            "fields": [
                {"key": "tipo_calculo", "label": "Tipo de cálculo*", "type": "select", "span": "span 2", "ph": "Selecione",
                 "options": [
                     {"value": "folha_mensal", "label": "Folha mensal"},
                     {"value": "rescisao", "label": "Rescisão"},
                     {"value": "ferias", "label": "Férias"},
                     {"value": "decimo_terceiro", "label": "13º salário"},
                     {"value": "esocial_s2210", "label": "eSocial S-2210"}]},
                {"key": "competencia", "label": "Competência (YYYY-MM)", "type": "text", "span": "span 1", "ph": "Ex.: 2026-07"},
                {"key": "employee_id", "label": "Colaborador (UUID, opcional)", "type": "text", "span": "span 1", "ph": "Opcional"},
                {"key": "referencia_id", "label": "Referência (id, opcional)", "type": "text", "span": "span 2", "ph": "Opcional"},
            ],
        }
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass

    # Religa o CTA da tela "fechamento-ponto" (estava "—") → aponta p/ o form fechar-mes-ponto.
    # Só religa se o form-alvo existir (se o try acima abortou, não cria CTA morto).
    if out.get("fechamento-ponto") and not out["fechamento-ponto"].get("ctaTo") and out.get("fechar-mes-ponto"):
        out["fechamento-ponto"]["cta"] = "Fechar mês"
        out["fechamento-ponto"]["ctaTo"] = "fechar-mes-ponto"

    # Religa o CTA da tela "certificacao" (estava "—") → aponta p/ o form gerar-certificacoes.
    if out.get("certificacao") and not out["certificacao"].get("ctaTo") and out.get("gerar-certificacoes"):
        out["certificacao"]["cta"] = "Gerar certificações"
        out["certificacao"]["ctaTo"] = "gerar-certificacoes"

    # Sincronizar férias do Sólides (gatilho direto, sem params — o endpoint real aceita
    # periodo_inicio/periodo_fim opcionais via query; fields=[] = form de confirmação só).
    out["sync-ferias-solides"] = {
        "title": "Sincronizar férias do Sólides",
        "sub": "Importa/atualiza as solicitações de férias a partir do Sólides",
        "cta": "Sincronizar", "type": "form",
        "submit": {"endpoint": "/api/v1/people-management/hr/vacations/sync-solides",
                   "okMsg": "Férias sincronizadas",
                   "confirm": "Isto busca e atualiza as férias a partir do Sólides"},
        "fields": [],
    }

    # Nova admissão — FORM que abre processo de admissão (POST /hr/admissions, dados básicos do
    # candidato). O restante do fluxo (documentos, exames, completar) segue na tela de admissão.
    out["nova-admissao"] = {
        "title": "Nova admissão", "type": "form",
        "sub": "Abrir processo de admissão — dados do candidato (documentos e exames no fluxo seguinte)",
        "cta": "Abrir admissão",
        "submit": {"endpoint": "/api/v1/people-management/hr/admissions", "okMsg": "Processo de admissão aberto"},
        "fields": [
            {"key": "candidate_name", "label": "Nome do candidato*", "type": "text", "span": "span 2", "ph": "Nome completo"},
            {"key": "cpf", "label": "CPF*", "type": "text", "span": "span 1", "ph": "000.000.000-00"},
            {"key": "birth_date", "label": "Nascimento", "type": "date", "span": "span 1"},
            {"key": "position", "label": "Cargo*", "type": "text", "span": "span 1", "ph": "Ex.: Agente de portaria"},
            {"key": "department", "label": "Departamento", "type": "text", "span": "span 1", "ph": "Opcional"},
            {"key": "salary_proposed", "label": "Salário proposto", "type": "text", "span": "span 1", "ph": "Ex.: 1670.00"},
            {"key": "expected_start_date", "label": "Início previsto", "type": "date", "span": "span 1"},
            {"key": "contract_type", "label": "Tipo de contrato", "type": "select", "span": "span 1",
             "ph": "CLT", "options": [{"value": "CLT", "label": "CLT"}, {"value": "PJ", "label": "PJ"},
                                      {"value": "Estágio", "label": "Estágio"}, {"value": "Temporário", "label": "Temporário"}]},
            {"key": "pis_pasep", "label": "PIS/PASEP", "type": "text", "span": "span 1", "ph": "Opcional"},
            {"key": "notes", "label": "Observações", "type": "textarea", "span": "span 2", "ph": "Opcional"},
        ],
    }
    # Religa os CTAs "Nova admissão" (estavam mortos, ctaTo=None) → apontam p/ o form nova-admissao.
    for _k in ("visao", "funcionarios", "admissao"):
        if out.get(_k) and (out[_k].get("cta") or "").lower().startswith("nova admiss"):
            out[_k]["ctaTo"] = "nova-admissao"

    # ── Task 4: religar os CTAs mortos restantes ─────────────────────────────
    # reembolsos: CTA "Solicitar reembolso" → form registrar-reembolso (JÁ existe no menu).
    if out.get("reembolsos") and not out["reembolsos"].get("ctaTo") and out.get("registrar-reembolso"):
        out["reembolsos"]["ctaTo"] = "registrar-reembolso"

    # rescisao: CTA "Nova rescisão" → novo form nova-rescisao (POST /hr/terminations, dado real).
    # employee_id = select de colaboradores ATIVOS (sem base de homologação). Verbas/TRCT/aviso
    # seguem no fluxo seguinte (docs por-linha já existem na tela de rescisão).
    try:
        from sqlalchemy import text as _sqltext
        _emp = (await db.execute(_sqltext(
            "SELECT id, nome FROM employees WHERE status='ativo' "
            "AND coalesce(is_homologacao,false)=false ORDER BY nome LIMIT 300"))).fetchall()
        _eopts = [{"value": str(r[0]), "label": r[1] or "—"} for r in _emp]
        out["nova-rescisao"] = {
            "title": "Nova rescisão", "type": "form",
            "sub": "Abrir processo de rescisão — verbas, TRCT e aviso prévio seguem no fluxo",
            "cta": "Abrir rescisão",
            "submit": {"endpoint": "/api/v1/people-management/hr/terminations",
                       "okMsg": "Processo de rescisão aberto",
                       "confirm": "Isto abre um processo FORMAL de rescisão para o colaborador selecionado"},
            "fields": [
                {"key": "employee_id", "label": "Colaborador*", "type": "select", "span": "span 2",
                 "ph": "Selecione o colaborador" if _eopts else "Nenhum colaborador ativo",
                 "options": _eopts},
                {"key": "type", "label": "Tipo de rescisão*", "type": "select", "span": "span 1",
                 "ph": "Selecione", "options": [
                     {"value": "involuntary", "label": "Dispensa sem justa causa"},
                     {"value": "voluntary", "label": "Pedido de demissão"},
                     {"value": "just_cause", "label": "Dispensa por justa causa"},
                     {"value": "mutual_agreement", "label": "Acordo mútuo (comum acordo)"},
                     {"value": "contract_end", "label": "Fim de contrato"},
                     {"value": "retirement", "label": "Aposentadoria"},
                 ]},
                {"key": "notice_type", "label": "Aviso prévio", "type": "select", "span": "span 1",
                 "ph": "—", "options": [
                     {"value": "trabalhado", "label": "Trabalhado"},
                     {"value": "indenizado", "label": "Indenizado"},
                 ]},
                {"key": "notice_period_days", "label": "Dias de aviso", "type": "text", "span": "span 1", "ph": "Ex.: 30"},
                {"key": "notice_start_date", "label": "Início do aviso", "type": "date", "span": "span 1"},
                {"key": "last_working_day", "label": "Último dia trabalhado", "type": "date", "span": "span 1"},
                {"key": "reason", "label": "Motivo", "type": "text", "span": "span 1", "ph": "Opcional"},
                {"key": "notes", "label": "Observações", "type": "textarea", "span": "span 2", "ph": "Opcional"},
            ],
        }
        if out.get("rescisao") and not out["rescisao"].get("ctaTo"):
            out["rescisao"]["ctaTo"] = "nova-rescisao"

        # ── Task 3: beneficios — form "Adicionar benefício" (POST /hr/benefits, BenefitCreate).
        # employee_id = mesmo select de colaboradores ativos (_eopts). type = BenefitType enum.
        out["nova-beneficio"] = {
            "title": "Adicionar benefício", "type": "form",
            "sub": "Cadastra um benefício para o colaborador",
            "cta": "Adicionar benefício",
            "submit": {"endpoint": "/api/v1/people-management/hr/benefits",
                       "okMsg": "Benefício adicionado"},
            "fields": [
                {"key": "employee_id", "label": "Colaborador*", "type": "select", "span": "span 2",
                 "ph": "Selecione o colaborador" if _eopts else "Nenhum colaborador ativo",
                 "options": _eopts},
                {"key": "type", "label": "Tipo de benefício*", "type": "select", "span": "span 1",
                 "ph": "Selecione", "options": [
                     {"value": "vale_transporte", "label": "Vale-transporte"},
                     {"value": "vale_refeicao", "label": "Vale-refeição"},
                     {"value": "vale_alimentacao", "label": "Vale-alimentação"},
                     {"value": "plano_saude", "label": "Plano de saúde"},
                     {"value": "plano_odontologico", "label": "Plano odontológico"},
                     {"value": "seguro_vida", "label": "Seguro de vida"},
                     {"value": "auxilio_creche", "label": "Auxílio-creche"},
                     {"value": "gym_pass", "label": "Gympass"},
                     {"value": "other", "label": "Outro"},
                 ]},
                {"key": "provider", "label": "Operadora", "type": "text", "span": "span 1", "ph": "Opcional"},
                {"key": "plan_name", "label": "Plano", "type": "text", "span": "span 1", "ph": "Opcional"},
                {"key": "company_contribution", "label": "Valor empresa", "type": "text", "span": "span 1", "ph": "Ex.: 150.00"},
                {"key": "employee_contribution", "label": "Valor desconto", "type": "text", "span": "span 1", "ph": "Ex.: 50.00"},
                {"key": "start_date", "label": "Início", "type": "date", "span": "span 1"},
                {"key": "end_date", "label": "Fim (vigência)", "type": "date", "span": "span 1"},
                {"key": "notes", "label": "Observações", "type": "textarea", "span": "span 2", "ph": "Opcional"},
            ],
        }
        if out.get("beneficios") and not out["beneficios"].get("ctaTo"):
            out["beneficios"]["cta"] = "Adicionar benefício"
            out["beneficios"]["ctaTo"] = "nova-beneficio"

        # ── Task 5: licencas — form "Registrar afastamento" (POST /hr/leaves, dado real).
        # Grava em sst_afastamentos (estabilidade acidentária derivada no backend). Tipos = enum
        # TipoAfastamento; reusa o mesmo select de colaboradores ativos (_eopts).
        out["nova-licenca"] = {
            "title": "Registrar afastamento", "type": "form",
            "sub": "Registra licença/afastamento do colaborador — estabilidade acidentária é derivada automaticamente",
            "cta": "Registrar afastamento",
            "submit": {"endpoint": "/api/v1/people-management/hr/leaves",
                       "okMsg": "Afastamento registrado"},
            "fields": [
                {"key": "employee_id", "label": "Colaborador*", "type": "select", "span": "span 2",
                 "ph": "Selecione o colaborador" if _eopts else "Nenhum colaborador ativo",
                 "options": _eopts},
                {"key": "leave_type", "label": "Tipo de afastamento*", "type": "select", "span": "span 1",
                 "ph": "Selecione", "options": [
                     {"value": "doenca", "label": "Doença (auxílio-doença)"},
                     {"value": "acidente_trabalho", "label": "Acidente de trabalho"},
                     {"value": "acidente_trajeto", "label": "Acidente de trajeto"},
                     {"value": "licenca_maternidade", "label": "Licença-maternidade"},
                     {"value": "licenca_paternidade", "label": "Licença-paternidade"},
                     {"value": "outro", "label": "Outro"},
                 ]},
                {"key": "cid", "label": "CID", "type": "text", "span": "span 1", "ph": "Ex.: S82 (opcional)"},
                {"key": "start_date", "label": "Início*", "type": "date", "span": "span 1"},
                {"key": "end_date", "label": "Fim previsto", "type": "date", "span": "span 1"},
                {"key": "motivo", "label": "Motivo/observação", "type": "textarea", "span": "span 2", "ph": "Opcional"},
            ],
        }
        if out.get("licencas") and not out["licencas"].get("ctaTo"):
            out["licencas"]["cta"] = "Registrar afastamento"
            out["licencas"]["ctaTo"] = "nova-licenca"

        # ── Task 5: ferias — reconcilia p/ tabela CANÔNICA hr_vacation_requests. A base lia a
        # legada employee_vacation_requests, cujo id NÃO bate com /vacations/{id}/approve (approve
        # grava hr_vacation_requests) → aprovar por ali erraria o registro. Aqui LÊ a canônica e
        # liga a AÇÃO por-linha "Aprovar" (POST /vacations/{id}/approve) só p/ SUBMITTED.
        # Aprovar dispara kit GEDEON no backend → happy-path NÃO testado (provado por 404 em id fake).
        _FER_ST = {"submitted": ("Pendente", "warn"), "approved": ("Aprovada", "ok"),
                   "rejected": ("Rejeitada", "bad"), "cancelled": ("Cancelada", "mut"),
                   "canceled": ("Cancelada", "mut")}

        def _fer_row(r):
            lbl, tone = _FER_ST.get((r[5] or "").lower(), (r[5] or "—", "info"))
            return [t(r[1] or "—", 600, _ND, initials(r[1] or "")), t(_d(r[2])), t(_d(r[3])),
                    t(str(r[4]) if r[4] is not None else "—"), b(lbl, tone)]

        # Task 1: Aprovar + Rejeitar por-linha (actionsfn substitui editfn — mesma condição SUBMITTED,
        # 2 botões em vez de 1). Rejeitar chama o handler fino rd_action_vacation_reject (id vai na
        # query ?vid= do endpoint, motivo vai no body {reason} preenchido pelo modal).
        def _fer_acts(r):
            if (r[5] or "").upper() != "SUBMITTED":
                return None
            aprovar = {"title": f"Aprovar férias de {r[1] or '—'}",
                       "endpoint": f"/api/v1/redesign/action/ferias-aprovar?vid={r[0]}",
                       "method": "POST", "btnLabel": "Aprovar", "submitLabel": "Aprovar",
                       "btnStyle": "primary", "okMsg": "Férias aprovadas. Recarregue a tela.",
                       "fields": []}
            rejeitar = {"title": f"Rejeitar férias de {r[1] or '—'}",
                        "endpoint": f"/api/v1/redesign/action/vacation-reject?vid={r[0]}",
                        "method": "POST", "btnLabel": "Rejeitar", "submitLabel": "Rejeitar",
                        "btnStyle": "outline", "okMsg": "Férias rejeitada",
                        "fields": [
                            {"key": "reason", "label": "Motivo (obrigatório)", "type": "textarea",
                             "span": "span 2", "value": ""},
                        ]}
            return [aprovar, rejeitar]

        _n_fer = (await db.execute(_sqltext("SELECT count(*) FROM hr_vacation_requests"))).scalar() or 0
        await safe("ferias", tbl(
            "Férias", f"{_n_fer} solicitações (fonte canônica)", "Solicitar férias",
            ["Colaborador", "Início", "Fim", "Dias", "Status"], "2fr 1fr 1fr 0.6fr 1fr",
            "SELECT v.id, coalesce(e.nome,'—'), v.start_date, v.end_date, v.days_requested, "
            "coalesce(v.status::text,'—') FROM hr_vacation_requests v "
            "LEFT JOIN employees e ON e.id=v.employee_id ORDER BY v.start_date DESC NULLS LAST LIMIT 200",
            _fer_row, actionsfn=_fer_acts))
        if out.get("ferias") and not out["ferias"].get("ctaTo"):
            out["ferias"]["ctaTo"] = "solicitar-ferias"

        # ── Task 5: documentos — form de UPLOAD multipart → GED (mesmo endpoint/pasta do clássico:
        # /ged/documents/upload, folder Funcionários, category 'rh'). DP anexa doc de qualquer
        # colaborador ativo. document_type = valores REAIS do enum DocumentType (sem rg/cpf).
        out["nova-documento"] = {
            "title": "Enviar documento", "type": "form",
            "sub": "Anexa um documento ao colaborador — arquiva no GED (pasta Funcionários)",
            "cta": "Enviar documento",
            "submit": {"endpoint": "/api/v1/ged/documents/upload", "okMsg": "Documento enviado",
                       "multipart": True, "titleFromFile": True,
                       "fixed": {"folder_id": "abcbebd2-88af-419e-8907-43b11f38f90b", "category": "rh"}},
            "fields": [
                {"key": "employee_id", "label": "Colaborador*", "type": "select", "span": "span 2",
                 "ph": "Selecione o colaborador" if _eopts else "Nenhum colaborador ativo", "options": _eopts},
                {"key": "document_type", "label": "Tipo*", "type": "select", "span": "span 1", "ph": "Selecione",
                 "options": [
                     {"value": "comprovante", "label": "Comprovante (RG/CPF/residência)"},
                     {"value": "contrato", "label": "Contrato"},
                     {"value": "certidao", "label": "Certidão"},
                     {"value": "laudo", "label": "Laudo/ASO"},
                     {"value": "outro", "label": "Outro"}]},
                {"key": "valid_until", "label": "Validade", "type": "date", "span": "span 1"},
                {"key": "file", "label": "Arquivo*", "type": "file", "span": "span 2", "accept": ".pdf,.jpg,.jpeg,.png"},
                {"key": "description", "label": "Observação", "type": "textarea", "span": "span 2", "ph": "Opcional"},
            ],
        }
        if out.get("documentos") and not out["documentos"].get("ctaTo"):
            out["documentos"]["cta"] = "Enviar documento"
            out["documentos"]["ctaTo"] = "nova-documento"

        # ── Task 6: funcionarios — form "Importar cadastro" (multipart CSV upload).
        # POST /api/v1/people-management/hr/employees/import-cadastro — arquivo CSV do contador/Onvio.
        # Reusa FormScreen type:file + submit.multipart (já baked). Sem campos fixos.
        out["importar-cadastro"] = {
            "title": "Importar cadastro",
            "type": "form",
            "sub": "Importa colaboradores a partir de uma planilha CSV (contador/Onvio)",
            "cta": "Importar",
            "submit": {
                "endpoint": "/api/v1/people-management/hr/employees/import-cadastro",
                "okMsg": "Cadastro importado",
                "multipart": True,
                "confirm": "Isto importa/atualiza colaboradores a partir da planilha"
            },
            "fields": [
                {"key": "file", "label": "Planilha CSV*", "type": "file", "span": "span 2", "accept": ".csv"}
            ],
        }

        # ── Task 5: visao drilldown — KPIs viram clicáveis → tela de detalhe (frontend DashScreen
        # navega com k.to). Aditivo: KPI sem 'to' continua não-clicável.
        _kpi_to = {"colaboradores ativos": "funcionarios", "folha líquida": "folha",
                   "solicitações de férias": "ferias", "admissões em processo": "admissao"}
        _v = out.get("visao")
        if _v and isinstance(_v.get("kpis"), list):
            for _k in _v["kpis"]:
                _lbl = (_k.get("l") or "").lower()
                for _pref, _dest in _kpi_to.items():
                    if _lbl.startswith(_pref) and out.get(_dest):
                        _k["to"] = _dest
                        break
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass

    # portas manuais (uma operação, duas portas) — mesmas rotas dos executores do agente
    try:
        _eo = await _emp_opts_ativos()
        out["registrar-licenca"] = _tela_registrar_licenca(_eo)
        out["renovar-aso"] = _tela_renovar_aso(_eo)
        out["revisar-justificativa"] = await _tela_revisar_justificativa(db, current_user)
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass

    # F0 — agrupa as 49 telas em 8 grupos com abas (mesma fundação do financeiro).
    # POR ÚLTIMO, sempre: `montar_grupos` captura as telas já montadas e troca as antigas por
    # stubs de redirect. Qualquer tela adicionada DEPOIS desta linha ficaria fora de grupo —
    # montada, mas sem entrada no menu e sem aba: invisível.
    from modules.operacional.controllers.redesign_builders._dp_grupos import montar_grupos

    montar_grupos(out)

    return out
