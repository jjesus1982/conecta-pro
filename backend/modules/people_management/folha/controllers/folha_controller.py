"""Controller da Folha de Pagamento — CCT 2026 SINDECOMPRESTS."""

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from core.auth.dependencies import get_current_user
from core.database.session import get_sync_db_dependency

from ..schemas.folha_schemas import (
    DashboardFolhaResponse,
    FolhaBatchResponse,
    HoleriteResponse,
    ResumoFolhaResponse,
    RubricaResponse,
)
from ..services import calculo_service

router = APIRouter(prefix="/folha", tags=["Folha de Pagamento"])


@router.get(
    "/dashboard",
    response_model=DashboardFolhaResponse,
    summary="Dashboard gerencial da folha",
)
async def folha_dashboard(
    current_user=Depends(get_current_user),
    mes: int = Query(default=None, ge=1, le=12),
    ano: int = Query(default=None, ge=2020),
    db: Session = Depends(get_sync_db_dependency),
) -> DashboardFolhaResponse:
    """Visao gerencial da folha do mes com totais por cargo."""
    hoje = date.today()
    mes = mes or hoje.month
    ano = ano or hoje.year
    data = calculo_service.get_dashboard_folha(db, mes, ano)
    return DashboardFolhaResponse(**data)


@router.get(
    "/calcular/{employee_id}/{mes}/{ano}",
    response_model=HoleriteResponse,
    summary="Calcular holerite de um colaborador",
)
async def calcular_holerite(
    employee_id: str,
    mes: int,
    ano: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_sync_db_dependency),
) -> HoleriteResponse:
    """Calcula holerite completo com base na CCT 2026."""
    result = calculo_service.calcular_folha_colaborador(db, employee_id, mes, ano)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return HoleriteResponse(**result)


@router.get(
    "/holerite/{employee_id}/{mes}/{ano}/pdf",
    summary="Baixar holerite em PDF (padrão-ouro Conecta Mais, 1 folha A4)",
)
def baixar_holerite_pdf(
    employee_id: str,
    mes: int,
    ano: int,
    db: Session = Depends(get_sync_db_dependency),
):
    """Gera o PDF completo e branded do holerite (proventos, descontos, bases, FGTS, assinaturas)."""
    from fastapi.responses import Response
    from sqlalchemy import text

    from ..services.holerite_pdf import montar_holerite_pdf

    result = calculo_service.calcular_folha_colaborador(db, employee_id, mes, ano)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    # dados do funcionário para o cabeçalho (tolerante a colunas ausentes)
    fdad: dict[str, Any] = {}
    try:
        row = db.execute(
            text("SELECT cpf, pis, matricula, data_admissao FROM employees WHERE CAST(id AS TEXT) = :e"),
            {"e": str(employee_id)},
        ).first()
        if row:
            adm = row[3]
            fdad = {
                "cpf": row[0],
                "pis": row[1] or "—",
                "matricula": row[2] or "—",
                "data_admissao": adm.strftime("%d/%m/%Y") if hasattr(adm, "strftime") else (adm or "—"),
                "posto": result.get("posto") or result.get("condominio") or "—",
            }
    except Exception:
        fdad = {}

    # Data de PAGAMENTO real: do fechamento/lote (payroll_periods) da competência.
    # Preferir o período JÁ PAGO/aprovado; sem data confirmada → holerite deixa campo em branco.
    try:
        dp = db.execute(
            text(
                "SELECT payment_date FROM payroll_periods "
                "WHERE reference_month = :m AND reference_year = :y AND payment_date IS NOT NULL "
                "ORDER BY (status IN ('paid','closed','approved')) DESC, payment_date DESC LIMIT 1"
            ),
            {"m": mes, "y": ano},
        ).scalar()
        if dp:
            fdad["data_pagamento"] = dp.strftime("%d/%m/%Y") if hasattr(dp, "strftime") else str(dp)
    except Exception:
        pass

    pdf = montar_holerite_pdf(result, fdad)

    # Assinatura universal do HOLERITE → só EMPLOYEE (recibo de salário, memória do
    # Jordan: incluir_empresa=False). Idempotente por (employee_id × competência) —
    # mesma chave usada em qualquer endpoint que gere este holerite. À prova de falha.
    _doc_id_holerite = f"{employee_id}:{ano}-{mes:02d}"
    try:
        import logging as _logging

        from modules.signatures.helpers import (
            document_hash_sha256 as _dhash,
        )
        from modules.signatures.helpers import (
            garantir_solicitacao_assinatura_sync,
        )

        garantir_solicitacao_assinatura_sync(
            document_type="payslip",
            document_id=_doc_id_holerite,
            title=f"Holerite {mes:02d}/{ano} - {result.get('employee_nome') or 'colaborador'}",
            document_hash=_dhash(pdf),
            employee_id=employee_id,
            employee_name=result.get("employee_nome"),
            employee_document=fdad.get("cpf"),
        )
    except Exception as _sig_exc:  # noqa: BLE001
        _logging.getLogger(__name__).warning("Assinatura do holerite não criada: %s", _sig_exc)

    nome = (result.get("employee_nome") or "colaborador").split()[0].lower()
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="holerite_{nome}_{mes:02d}_{ano}.pdf"'},
    )


def _cnpj_da_competencia(db, mes: int, ano: int, condominio: str | None = None) -> str:
    """CNPJ do empregador na competência, lido do PRÓPRIO holerite (empresa_id).

    O branding padrão dos PDFs é o CNPJ1 (Eletrônica); a folha CLT é da Patrimonial.
    Deixar o default sairia com o CNPJ errado no papel — exatamente o que a separação
    por CNPJ existe p/ evitar. CNPJs misturados na competência => "" (não adivinha).
    """
    from sqlalchemy import text as _sqltext

    sql = (
        "SELECT DISTINCT em.cnpj FROM hr_payslips p JOIN empresas em ON em.id = p.empresa_id "
        "WHERE p.reference_year = :a AND p.reference_month = :m"
    )
    par: dict = {"a": ano, "m": mes}
    if condominio:
        sql += " AND CAST(p.condominio_id AS TEXT) = :c"
        par["c"] = condominio
    try:
        rows = db.execute(_sqltext(sql), par).fetchall()
    except Exception:  # noqa: BLE001 — timbrado nunca derruba o PDF
        return ""
    return str(rows[0][0]) if len(rows) == 1 else ""


@router.get(
    "/{mes:int}/{ano:int}/pdf",
    summary="Exportar FOLHA CONSOLIDADA em PDF (resumo + detalhamento por colaborador)",
)
def exportar_folha_pdf(
    mes: int,
    ano: int,
    condominio: str | None = Query(None, description="UUID do condomínio — folha daquele posto"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_sync_db_dependency),
):
    """Gera o PDF da folha inteira do período (padrão-ouro Conecta Mais).

    Mesmos números da tela dp/folha (fonte: ``get_resumo_folha``): resumo com
    totais (bruto/descontos/líquido/INSS/FGTS/IRRF/custo) + tabela de
    detalhamento por colaborador. Não recalcula: só formata em PDF.
    """
    from fastapi.responses import Response

    from ..services.folha_pdf import montar_folha_pdf

    if not (1 <= mes <= 12):
        raise HTTPException(status_code=422, detail="Mês inválido (1-12).")

    if condominio:
        # Folha DE UM CONDOMÍNIO: lê a folha PERSISTIDA (a que o Jordan gerou em
        # DP → Gerar folha), não recalcula — o PDF tem que ser o espelho do que foi
        # gravado, senão o papel diverge da tela. Sem linha gravada = erro explícito.
        from sqlalchemy import text as _sqltext

        _nome = db.execute(
            _sqltext("SELECT nome FROM condominios WHERE CAST(id AS TEXT) = :c"), {"c": condominio}
        ).first()
        if not _nome:
            raise HTTPException(status_code=404, detail="Condomínio não encontrado.")
        _rows = db.execute(
            _sqltext(
                "SELECT coalesce(e.nome,'—'), coalesce(e.cargo,'—'), p.base_salary, p.inss_value, "
                "       p.fgts_value, p.total_deductions, p.net_salary, p.total_earnings, p.irrf_value "
                "FROM hr_payslips p JOIN employees e ON e.id = p.employee_id "
                "WHERE p.reference_year = :a AND p.reference_month = :m "
                "  AND CAST(p.condominio_id AS TEXT) = :c AND p.source_system = 'conecta' "
                "ORDER BY e.nome"
            ),
            {"a": ano, "m": mes, "c": condominio},
        ).fetchall()
        if not _rows:
            raise HTTPException(
                status_code=404,
                detail=f"Folha de {_nome[0]} em {mes:02d}/{ano} ainda não foi gerada. "
                "Use DP → Gerar folha (Conecta PRO).",
            )

        def _f(v) -> float:
            return float(v or 0)

        _bruto = sum(_f(r[7]) for r in _rows)
        _fgts = sum(_f(r[4]) for r in _rows)
        resumo = {
            "mes": mes,
            "ano": ano,
            "escopo": _nome[0],
            "total_colaboradores": len(_rows),
            "total_proventos": _bruto,
            "total_descontos": sum(_f(r[5]) for r in _rows),
            "total_liquido": sum(_f(r[6]) for r in _rows),
            "total_fgts": _fgts,
            "total_inss": sum(_f(r[3]) for r in _rows),
            "total_irrf": sum(_f(r[8]) for r in _rows),
            "custo_total_empresa": _bruto + _fgts,
            "fonte": "conecta",
            "empresa_cnpj": _cnpj_da_competencia(db, mes, ano, condominio),
            "funcionarios": [
                {
                    "nome": r[0],
                    "cargo": r[1],
                    "salario_base": _f(r[2]),
                    "inss_value": _f(r[3]),
                    "fgts_value": _f(r[4]),
                    "total_descontos": _f(r[5]),
                    "salario_liquido": _f(r[6]),
                }
                for r in _rows
            ],
        }
        _slug = "".join(ch if ch.isalnum() else "_" for ch in _nome[0]).strip("_").lower()
        return Response(
            content=montar_folha_pdf(resumo),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="folha_{_slug}_{ano}_{mes:02d}.pdf"',
                "Cache-Control": "no-store",
            },
        )

    resumo = calculo_service.get_resumo_folha(db, mes, ano)
    resumo["empresa_cnpj"] = _cnpj_da_competencia(db, mes, ano)
    pdf = montar_folha_pdf(resumo)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="folha_{ano}_{mes:02d}.pdf"',
            "Cache-Control": "no-store",
        },
    )


@router.get(
    "/recibo-vt-vr/{employee_id}/{mes}/{ano}/pdf",
    summary="Baixar Recibo de VT e VR em PDF (padrão-ouro Conecta Mais)",
)
def baixar_recibo_vt_vr_pdf(
    employee_id: str,
    mes: int,
    ano: int,
    vt_concedido: float | None = Query(default=None, description="Valor do crédito de VT concedido (tarifa × dias)"),
    db: Session = Depends(get_sync_db_dependency),
):
    """Gera o PDF do Recibo de Vale-Transporte e Vale-Refeição da competência."""
    from fastapi.responses import Response
    from sqlalchemy import text

    from ..services.recibo_vt_vr_pdf import montar_recibo_vt_vr_pdf

    # PJ não passa pelo cálculo da folha CLT — ele não tem folha. Origem: 17/09/2026: sete
    # prestadores receberam VT/VR no lote e o `calcular_folha_colaborador` devolvia
    # "Colaborador não encontrado ou inativo", deixando os sete sem recibo nenhum. Para eles o
    # recibo é montado a partir do que foi PAGO, que é o único fato que existe.
    _pj = db.execute(
        text(
            "SELECT nome, cargo, coalesce(cnpj,''), coalesce(razao_social,''), coalesce(cpf,'') "
            "FROM employees WHERE CAST(id AS TEXT) = :e AND coalesce(status,'') LIKE 'pj_%'"
        ),
        {"e": str(employee_id)},
    ).first()

    if _pj:
        result = {"employee_nome": _pj[0], "cargo": _pj[1] or "—", "mes": mes, "ano": ano}
    else:
        result = calculo_service.calcular_folha_colaborador(db, employee_id, mes, ano)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])

    fdad: dict[str, Any] = {}
    if _pj:
        # Documento do prestador: CNPJ quando existe, CPF quando o PJ ainda não tem.
        fdad = {
            "e_pj": True,
            "cpf": _pj[2] or _pj[4],
            # O CPF de verdade resolve QUAL empresa pagou (employees.cpf → empresas.slug).
            # Sem ele o branding cai no default e o recibo sai com o CNPJ errado.
            "cpf_vinculo": _pj[4],
            "razao_social": _pj[3] or _pj[0],
            "pis": "—",
            "matricula": "—",
            "posto": "ESCRITÓRIO",
        }
    try:
        row = (
            None
            if _pj
            else db.execute(
                text("SELECT cpf, pis, matricula FROM employees WHERE CAST(id AS TEXT) = :e"),
                {"e": str(employee_id)},
            ).first()
        )
        if row:
            fdad = {
                "cpf": row[0],
                "pis": row[1] or "—",
                "matricula": row[2] or "—",
                "posto": result.get("posto") or result.get("condominio") or "—",
            }
    except Exception:
        fdad = {}

    # data de pagamento real (mesmo do holerite): fechamento/lote da competência
    try:
        dp = db.execute(
            text(
                "SELECT payment_date FROM payroll_periods "
                "WHERE reference_month = :m AND reference_year = :y AND payment_date IS NOT NULL "
                "ORDER BY (status IN ('paid','closed','approved')) DESC, payment_date DESC LIMIT 1"
            ),
            {"m": mes, "y": ano},
        ).scalar()
        if dp:
            fdad["data_pagamento"] = dp.strftime("%d/%m/%Y") if hasattr(dp, "strftime") else str(dp)
    except Exception:
        pass

    # ── O QUE FOI PAGO DE VERDADE nesta competência ─────────────────────────────────────
    # Origem: 16/09/2026. O recibo era montado só com o cálculo da folha (dias-padrão × valor
    # unitário) e divergia do que entrou na conta: ADAILSON com R$ 330 + R$ 150 no papel contra
    # R$ 308 + R$ 116 no extrato. Mesmo defeito do espelho de ponto resolvido hoje — dois
    # motores para o mesmo número. Aqui o pagamento é a fonte, e a folha só entra quando não
    # houve pagamento registrado (competência ainda em aberto).
    try:
        _pg = db.execute(
            text(
                "SELECT valor, descricao, updated_at::date FROM financial_pagamentos_diaristas "
                "WHERE tipo = 'vt_vr' AND status = 'pago' AND competencia = :c "
                "  AND upper(btrim(beneficiario)) = ("
                "      SELECT upper(btrim(nome)) FROM employees WHERE CAST(id AS TEXT) = :e) "
                "ORDER BY updated_at DESC LIMIT 1"
            ),
            {"c": f"{mes:02d}/{ano}", "e": str(employee_id)},
        ).first()
    except Exception:  # noqa: BLE001
        _pg = None

    if _pg:
        import re as _re

        _m = _re.search(r"VT R\$ ([\d.]+) \+ VR R\$ ([\d.]+)", str(_pg[1] or ""))
        if _m:
            result["vt_pago"] = float(_m.group(1))
            result["vr_pago"] = float(_m.group(2))
            # VT zero = quem recebe pela carteirinha do SINETRAM; a declaração precisa dizer isso.
            fdad["vt_pelo_sinetran"] = float(_m.group(1)) == 0.0
        fdad["pago_via_pix"] = True
        if _pg[2]:
            fdad["data_pagamento"] = _pg[2].strftime("%d/%m/%Y")

    _doc_id_recibo = f"{employee_id}:{ano}-{mes:02d}"

    # Assinatura universal (recibo VT/VR → só EMPLOYEE). Consulta status p/ carimbar
    # o bloco branded de autenticidade, e garante a solicitação. À prova de falha.
    _signatarios = None
    try:
        import logging as _logging

        from modules.signatures.helpers import (
            document_hash_sha256 as _dhash,
        )
        from modules.signatures.helpers import (
            garantir_solicitacao_assinatura_sync,
            status_documento_sync,
        )

        _st = status_documento_sync("recibo_vt_vr", _doc_id_recibo)
        _signatarios = (_st or {}).get("signatarios")
    except Exception:  # noqa: BLE001
        _signatarios = None

    pdf = montar_recibo_vt_vr_pdf(result, fdad, vt_concedido=vt_concedido, signatarios=_signatarios)

    try:
        garantir_solicitacao_assinatura_sync(
            document_type="recibo_vt_vr",
            document_id=_doc_id_recibo,
            title=f"Recibo VT/VR {mes:02d}/{ano} - {result.get('employee_nome') or 'colaborador'}",
            document_hash=_dhash(pdf),
            employee_id=employee_id,
            employee_name=result.get("employee_nome"),
            employee_document=fdad.get("cpf"),
        )
    except Exception as _sig_exc:  # noqa: BLE001
        _logging.getLogger(__name__).warning("Assinatura do recibo VT/VR não criada: %s", _sig_exc)

    nome = (result.get("employee_nome") or "colaborador").split()[0].lower()
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="recibo_vt_vr_{nome}_{mes:02d}_{ano}.pdf"'},
    )


@router.post(
    "/calcular/todos/{mes}/{ano}",
    response_model=FolhaBatchResponse,
    summary="Calcular folha de todos os colaboradores",
    status_code=201,
)
async def calcular_batch(
    mes: int,
    ano: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_sync_db_dependency),
) -> FolhaBatchResponse:
    """Calcula folha completa para todos os colaboradores ativos.

    Prioriza dados importados do Domínio Sistemas (fonte de verdade).
    Engine interna é usada apenas como fallback quando não há dados importados.
    """
    result = calculo_service.calcular_folha_batch_com_guard(db, mes, ano)
    return FolhaBatchResponse(**result)


@router.get(
    "/holerite/{employee_id}/{mes}/{ano}",
    response_model=HoleriteResponse,
    summary="Obter holerite final",
)
def get_holerite(
    employee_id: str,
    mes: int,
    ano: int,
    db: Session = Depends(get_sync_db_dependency),
) -> HoleriteResponse:
    """Retorna holerite calculado (mesmo que calcular, para consulta)."""
    result = calculo_service.calcular_folha_colaborador(db, employee_id, mes, ano)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return HoleriteResponse(**result)


@router.get(
    "/resumo/{mes}/{ano}",
    response_model=ResumoFolhaResponse,
    summary="Resumo totalizador da folha",
)
def resumo_folha(
    mes: int,
    ano: int,
    db: Session = Depends(get_sync_db_dependency),
) -> ResumoFolhaResponse:
    """Retorna totais consolidados da folha do mes."""
    data = calculo_service.get_resumo_folha(db, mes, ano)
    return ResumoFolhaResponse(**data)


@router.get(
    "/rubricas",
    response_model=list[RubricaResponse],
    summary="Listar rubricas cadastradas",
)
def listar_rubricas(
    db: Session = Depends(get_sync_db_dependency),
) -> list[RubricaResponse]:
    """Lista as 24 rubricas ativas da CCT 2026."""
    items = calculo_service.get_rubricas(db)
    return [RubricaResponse(**i) for i in items]
