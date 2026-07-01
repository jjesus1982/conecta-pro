"""
My CCT Controller — Direitos do trabalhador conforme CCT 2026.

Endpoints:
- GET /portal/cct/direitos (direitos resumidos por funcao)
- POST /portal/cct/calculadora (simulador de verbas rescisorias)
- GET /portal/cct/feriados (calendario de feriados 2026)
- GET /portal/cct/adicional-noturno (explicacao e calculo)
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from modules.people_management.employee_portal.auth import CurrentEmployeeId

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cct", tags=["Portal - CCT Direitos"])


@router.get("/direitos")
async def get_meus_direitos(
    employee_id: CurrentEmployeeId,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna direitos do trabalhador conforme CCT 2026 e seu cargo."""
    from modules.cct.models.benefits import BENEFICIOS_OBRIGATORIOS_CCT
    from modules.cct.models.cct_metadata import CCT_METADATA
    from modules.cct.models.schedule import ADICIONAIS, JORNADAS_PERMITIDAS
    from modules.cct.validators.salary_validator import SalaryValidator

    # Buscar dados do colaborador
    nome = ""
    cargo = ""
    salario_base = 0.0
    data_admissao = ""
    jornada = ""
    piso_cct = 0.0
    cargo_cct_encontrado = False
    try:
        from sqlalchemy import select, text

        from modules.operacional.models.employee import Employee

        result = await db.execute(select(Employee).where(Employee.id == employee_id))
        emp = result.scalar_one_or_none()
        if emp:
            nome = getattr(emp, "nome", "") or ""
            cargo = getattr(emp, "cargo", "") or ""
            salario_base = float(getattr(emp, "salario_base", 0) or 0)
            data_admissao = str(getattr(emp, "data_admissao", ""))
            jornada = getattr(emp, "jornada_trabalho", "") or getattr(emp, "escala_padrao", "") or "12x36"
            # Fonte única: piso vem do cargo CCT vinculado (cct_cargo_id), não de match de string.
            cct_cargo_id = getattr(emp, "cct_cargo_id", None)
            if cct_cargo_id:
                row = (
                    await db.execute(
                        text("SELECT cargo_nome, piso_salarial FROM cct_cargos WHERE id = :cid"),
                        {"cid": str(cct_cargo_id)},
                    )
                ).mappings().first()
                if row:
                    piso_cct = float(row["piso_salarial"])
                    cargo = row["cargo_nome"] or cargo
                    cargo_cct_encontrado = True
    except ImportError:
        pass

    # Validar salario contra piso — via cargo CCT vinculado (fonte única); fallback ao validator antigo.
    if cargo_cct_encontrado:
        validacao_salario = {
            "conforme": salario_base >= piso_cct if salario_base else False,
            "piso_cct": piso_cct,
            "salario_atual": salario_base,
            "diferenca": round(salario_base - piso_cct, 2) if salario_base else None,
        }
    else:
        validacao_salario = SalaryValidator.validar_salario(cargo, salario_base) if cargo else {}

    # Beneficios obrigatorios
    beneficios_resumo = []
    for b in BENEFICIOS_OBRIGATORIOS_CCT:
        if b.obrigatorio:
            beneficios_resumo.append(
                {
                    "beneficio": b.tipo.value.replace("_", " ").title(),
                    "garantia_cct": b.observacao,
                }
            )

    # Adicionais aplicaveis
    adicionais_info = {
        "adicional_noturno": f"{ADICIONAIS.adicional_noturno_percentual}% sobre hora normal (22h-05h)",
        "hora_extra_normal": f"{ADICIONAIS.hora_extra_normal_percentual}% sobre hora normal",
        "hora_extra_feriado": f"{ADICIONAIS.hora_extra_feriado_percentual}% sobre hora normal",
        "hora_noturna_reduzida": f"{ADICIONAIS.hora_noturna_minutos} minutos (reduzida)",
    }

    return {
        "funcionario": {
            "nome": nome,
            "cargo": cargo,
            "salario_base": salario_base,
            "data_admissao": data_admissao,
            "jornada": jornada,
        },
        "cct": {
            "nome": CCT_METADATA.nome,
            "registro_mte": CCT_METADATA.registro_mte,
            "vigencia": f"{CCT_METADATA.vigencia_inicio} a {CCT_METADATA.vigencia_fim}",
            "sindicato_laboral": CCT_METADATA.sindicato_laboral,
            "sindicato_patronal": CCT_METADATA.sindicato_patronal,
            "data_base": CCT_METADATA.data_base,
        },
        "salario": {
            "conforme_cct": validacao_salario.get("conforme", True),
            "piso_cargo": validacao_salario.get("piso_cct", 0),
            "salario_atual": salario_base,
            "adicional_tipo": validacao_salario.get("adicional_tipo"),
            "adicional_valor": validacao_salario.get("adicional_valor"),
        },
        "beneficios_garantidos": beneficios_resumo,
        "adicionais": adicionais_info,
        "jornadas_permitidas": [{"tipo": j.tipo.value, "descricao": j.descricao} for j in JORNADAS_PERMITIDAS],
        "estabilidades": [
            "Pre-aposentadoria: 12 meses (minimo 5 anos na empresa)",
            "Acidente de trabalho: 12 meses apos alta INSS",
            "Gestante: ate 5 meses apos parto",
        ],
        "escala_proibida": "2x1 — Proibida (TAC MPT 11a Regiao)",
    }


@router.post("/calculadora", status_code=201)
async def calculadora_rescisoria(
    employee_id: CurrentEmployeeId,
    db: AsyncSession = Depends(get_db),
    motivo: str = Query(
        default="sem_justa_causa",
        description="Motivo: sem_justa_causa, justa_causa, pedido_demissao, acordo",
    ),
) -> Any:
    """Simulador de verbas rescisorias baseado no perfil do funcionario."""
    from datetime import date

    from modules.cct.validators.termination_validator import TerminationValidator

    # Buscar dados do colaborador
    salario_base = 0.0
    data_admissao = ""
    try:
        from sqlalchemy import select

        from modules.operacional.models.employee import Employee

        result = await db.execute(select(Employee).where(Employee.id == employee_id))
        emp = result.scalar_one_or_none()
        if emp:
            salario_base = float(getattr(emp, "salario_base", 0) or 0)
            dt_adm = getattr(emp, "data_admissao", None)
            data_admissao = str(dt_adm) if dt_adm else "2025-01-01"
    except ImportError:
        pass

    if not salario_base:
        salario_base = 1670.00
    if not data_admissao:
        data_admissao = "2025-01-01"

    data_demissao = date.today().isoformat()

    # Calcular rescisao
    rescisao = TerminationValidator.validar_rescisao(
        employee_id=employee_id,
        data_admissao=data_admissao,
        data_demissao=data_demissao,
        salario_base=salario_base,
        motivo=motivo,
    )

    # Calcular ferias proporcionais
    meses_trabalhados = max(1, min(12, int(rescisao["tempo_servico_anos"] * 12) % 12 or 12))
    ferias = TerminationValidator.calcular_ferias_proporcionais(
        salario_base=salario_base,
        faltas_periodo=0,
        meses_trabalhados=meses_trabalhados,
    )

    # 13o proporcional
    decimo_terceiro = TerminationValidator.calcular_decimo_terceiro(
        salario_base=salario_base,
        meses_trabalhados=meses_trabalhados,
    )

    return {
        "simulacao_data": data_demissao,
        "motivo": motivo,
        "salario_base": salario_base,
        "rescisao": rescisao,
        "ferias_proporcionais": ferias,
        "decimo_terceiro_proporcional": decimo_terceiro,
        "aviso": (
            "Esta e uma simulacao. Valores reais podem variar conforme adicionais, descontos e situacao individual."
        ),
    }


@router.get("/feriados")
async def get_feriados_2026(
    employee_id: CurrentEmployeeId,
    mes: int | None = Query(None, ge=1, le=12, description="Filtrar por mes"),
) -> Any:
    """Retorna calendario de feriados Manaus/AM 2026."""
    from modules.cct.models.holidays import FERIADOS_MANAUS_2026, get_feriados_mes

    if mes:
        feriados = get_feriados_mes(mes)
    else:
        feriados = list(FERIADOS_MANAUS_2026)

    return {
        "total": len(feriados),
        "ano": 2026,
        "municipio": "Manaus/AM",
        "feriados": [
            {
                "data": f.data.isoformat(),
                "nome": f.nome,
                "tipo": f.tipo,
                "dia_semana": f.data.strftime("%A"),
            }
            for f in feriados
        ],
    }


@router.get("/adicional-noturno")
async def get_adicional_noturno(
    employee_id: CurrentEmployeeId,
    db: AsyncSession = Depends(get_db),
    horas_noturnas: float = Query(default=7, ge=0, description="Horas noturnas trabalhadas"),
) -> Any:
    """Calcula adicional noturno do funcionario com hora reduzida (52min30s)."""
    from modules.cct.validators.schedule_validator import ScheduleValidator

    # Buscar salario
    salario_base = 0.0
    jornada = "12x36"
    try:
        from sqlalchemy import select

        from modules.operacional.models.employee import Employee

        result = await db.execute(select(Employee).where(Employee.id == employee_id))
        emp = result.scalar_one_or_none()
        if emp:
            salario_base = float(getattr(emp, "salario_base", 0) or 0)
            jornada = getattr(emp, "escala_padrao", "") or "12x36"
    except ImportError:
        pass

    if not salario_base:
        salario_base = 1670.00

    calculo = ScheduleValidator.calcular_adicional_noturno(
        salario_base=salario_base,
        jornada_tipo=jornada,
        horas_noturnas=horas_noturnas,
    )

    return {
        **calculo,
        "explicacao": (
            "O adicional noturno e de 20% sobre a hora normal. "
            "A hora noturna e reduzida para 52 minutos e 30 segundos "
            "(periodo das 22h as 05h), conforme CCT 2026 SINDECOMPRESTS/SINDICOND-AM."
        ),
    }
