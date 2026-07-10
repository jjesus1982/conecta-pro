"""
Controller eSocial — Geração de eventos XML (S-2200, S-2299).

Endpoints para gerar XMLs de eventos eSocial para transmissão ao governo.
"""

import asyncio
import logging
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_async_session
from modules.people_management.hr.publishers import publish_esocial_gerado
from modules.people_management.hr.services.esocial_service import ESocialEventService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/esocial", tags=["DP - eSocial"])

EMPRESA_CNPJ = "35710481000103"
EMPRESA_RAZAO = "CONECTAMAIS ELETRONICA LTDA"


class AdmissaoESocialRequest(BaseModel):
    """Dados para geração do evento S-2200 (Admissão)."""

    cpf: str = Field(..., description="CPF do trabalhador")
    nome: str = Field(..., description="Nome completo")
    data_nascimento: str | None = Field(None, description="Data de nascimento YYYY-MM-DD")
    sexo: str = Field("M", description="M ou F")
    data_admissao: str = Field(..., description="Data de admissão YYYY-MM-DD")
    cargo: str = Field("", description="Cargo")
    salario: float = Field(..., description="Salário base")
    matricula: str = Field(..., description="Matrícula eSocial")
    cbo: str = Field("", description="Código CBO")
    categoria: str = Field("101", description="Categoria do trabalhador")
    tipo_contrato: str = Field("1", description="1=Indeterminado, 2=Determinado")
    dados_complementares: dict[str, Any] | None = None


class DesligamentoESocialRequest(BaseModel):
    """Dados para geração do evento S-2299 (Desligamento)."""

    cpf: str = Field(..., description="CPF do trabalhador")
    matricula: str = Field(..., description="Matrícula eSocial")
    data_desligamento: date = Field(..., description="Data do desligamento")
    motivo: str = Field("02", description="Código do motivo (02=Sem justa causa)")
    verbas_rescisorias: list[dict[str, Any]] | None = None


@router.post(
    "/s2200/gerar",
    summary="Gerar XML S-2200 Admissao",
    description="Gera XML do evento eSocial S-2200 (Cadastramento Inicial / Admissão) para transmissão.",
    status_code=201,
)
async def gerar_s2200(
    request: AdmissaoESocialRequest,
    current_user: CurrentActiveUser,
) -> Response:
    """Gera XML do evento S-2200 (Cadastramento Inicial / Admissão).

    Retorna XML para download.
    """
    trabalhador = {
        "cpf": request.cpf,
        "nome": request.nome,
        "data_nascimento": request.data_nascimento,
        "sexo": request.sexo,
    }
    if request.dados_complementares:
        trabalhador.update(request.dados_complementares)

    contrato = {
        "data_admissao": request.data_admissao,
        "salario": request.salario,
        "matricula": request.matricula,
        "cod_cargo": request.cbo,
        "categoria": request.categoria,
        "tipo_contrato": request.tipo_contrato,
    }

    xml = ESocialEventService.gerar_s2200(
        empregador_cnpj=EMPRESA_CNPJ,
        empregador_razao=EMPRESA_RAZAO,
        trabalhador=trabalhador,
        contrato=contrato,
    )

    # Validar
    validacao = ESocialEventService.validar_xml(xml)
    if not validacao["valid"]:
        raise HTTPException(400, f"XML inválido: {validacao['errors']}")

    asyncio.create_task(publish_esocial_gerado(cpf=request.cpf, matricula=request.matricula, evento_tipo="S2200"))
    return Response(
        content=xml,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="S2200_{request.matricula}.xml"'},
    )


@router.post(
    "/s2299/gerar",
    summary="Gerar XML S-2299 Desligamento",
    description="Gera XML do evento eSocial S-2299 (Desligamento) com verbas rescisórias.",
    status_code=201,
)
async def gerar_s2299(
    request: DesligamentoESocialRequest,
    current_user: CurrentActiveUser,
) -> Response:
    """Gera XML do evento S-2299 (Desligamento).

    Retorna XML para download.
    """
    xml = ESocialEventService.gerar_s2299(
        empregador_cnpj=EMPRESA_CNPJ,
        trabalhador_cpf=request.cpf,
        matricula=request.matricula,
        data_desligamento=request.data_desligamento,
        motivo_desligamento=request.motivo,
        verbas_rescisorias=request.verbas_rescisorias,
    )

    validacao = ESocialEventService.validar_xml(xml)
    if not validacao["valid"]:
        raise HTTPException(400, f"XML inválido: {validacao['errors']}")

    asyncio.create_task(publish_esocial_gerado(cpf=request.cpf, matricula=request.matricula, evento_tipo="S2299"))
    return Response(
        content=xml,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="S2299_{request.matricula}.xml"'},
    )


@router.post(
    "/validar",
    summary="Validar XML eSocial",
    status_code=201,
    description="Valida a estrutura de um XML eSocial antes da transmissão.",
)
async def validar_xml_esocial(
    xml_content: str,
    current_user: CurrentActiveUser,
) -> Any:
    """Valida estrutura de um XML eSocial."""
    return ESocialEventService.validar_xml(xml_content)


# Descrição amigável dos leiautes (rótulo apenas; a fonte é sempre o banco).
_TIPO_DESC = {
    "S-1200": "Remuneração do Trabalhador",
    "S-1210": "Pagamentos de Rendimentos",
    "S-2200": "Cadastramento Inicial / Admissão",
    "S-2205": "Alteração de Dados Cadastrais",
    "S-2206": "Alteração de Contrato",
    "S-2210": "Comunicação de Acidente (CAT)",
    "S-2220": "Monitoramento da Saúde (ASO)",
    "S-2230": "Afastamento Temporário",
    "S-2240": "Condições Ambientais do Trabalho",
    "S-2299": "Desligamento",
    "S-3000": "Exclusão de Eventos",
}

# Normaliza os status crus (nossos + do espelho) para os 4 baldes da tela DP.
_STATUS_MAP = {
    "transmitida": "enviado",
    "enfileirada": "enviado",
    "processando": "enviado",
    "aceita": "aceito",
    "aceito": "aceito",
    "rejeitada": "rejeitado",
    "rejeitado": "rejeitado",
    "erro": "rejeitado",
    "nao_transmitida": "pendente",
    "pendente": "pendente",
}


@router.get(
    "/events",
    summary="Listar Eventos eSocial",
    description=(
        "Lista UNIFICADA e REAL dos eventos eSocial: nossas transmissões "
        "(gp_asos S-2220, sst_afastamentos S-2230, gp_cats S-2210, "
        "sst_s2240_transmissoes S-2240 — com protocolo/recibo reais) e o "
        "espelho oficial baixado do governo (esocial_eventos_espelho). "
        "Nada é fabricado: protocolo e recibo vêm sempre do próprio banco."
    ),
)
async def listar_eventos_esocial(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_async_session),
    limit: int = Query(500, ge=1, le=2000),
) -> Any:
    """Devolve a lista real de eventos eSocial (transmissões próprias + espelho).

    Fonte 1 (nossas transmissões): colunas esocial_* de gp_asos/sst_afastamentos/
    gp_cats/sst_s2240_transmissoes. Recibo preenchido = aceito; protocolo sem
    recibo = enviado (aguardando recibo do beat esocial-pull-recibos 2h).

    Fonte 2 (espelho oficial): esocial_eventos_espelho — eventos já no governo,
    baixados via webservice read-only. Todos com nr_recibo => status 'aceito'.
    Nome do trabalhador vem do JOIN por CPF com employees (pode faltar).
    """
    itens: list[dict[str, Any]] = []

    # --- Fonte 1: NOSSAS transmissões (mesma união do transmissao_central_service) ---
    nossas = (
        await db.execute(
            text(
                "SELECT * FROM ("
                " SELECT 'S-2220' AS tipo, a.aso_id::text AS ref_id, e.nome AS funcionario, "
                "  regexp_replace(e.cpf, '\\D', '', 'g') AS cpf, "
                "  a.esocial_status, a.esocial_protocolo, a.recibo_s2220 AS recibo, a.updated_at "
                " FROM gp_asos a JOIN employees e ON e.id = a.employee_id "
                " WHERE a.esocial_status IS NOT NULL AND a.esocial_status <> 'nao_transmitida' "
                " UNION ALL "
                " SELECT 'S-2230', f.id::text, e.nome, regexp_replace(e.cpf, '\\D', '', 'g'), "
                "  f.esocial_status, f.esocial_protocolo, f.recibo_s2230, f.updated_at "
                " FROM sst_afastamentos f JOIN employees e ON e.id = f.employee_id "
                " WHERE f.esocial_status IS NOT NULL AND f.esocial_status <> 'nao_transmitida' "
                " UNION ALL "
                " SELECT 'S-2210', c.cat_id::text, e.nome, regexp_replace(e.cpf, '\\D', '', 'g'), "
                "  c.esocial_status, c.esocial_protocolo, c.numero_recibo_esocial, c.updated_at "
                " FROM gp_cats c JOIN employees e ON e.id::text = c.employee_id "
                " WHERE c.esocial_status IS NOT NULL AND c.esocial_status <> 'nao_transmitida' "
                " UNION ALL "
                " SELECT 'S-2240', t.employee_id::text, e.nome, regexp_replace(e.cpf, '\\D', '', 'g'), "
                "  t.esocial_status, t.esocial_protocolo, t.recibo_s2240, t.atualizado_em "
                " FROM sst_s2240_transmissoes t JOIN employees e ON e.id = t.employee_id "
                " WHERE t.esocial_status IS NOT NULL AND t.esocial_status <> 'nao_transmitida' "
                ") u ORDER BY u.updated_at DESC NULLS LAST"
            )
        )
    ).mappings().all()

    refs_nossas: set[tuple[str, str]] = set()
    for r in nossas:
        recibo = r["recibo"]
        protocolo = r["esocial_protocolo"]
        cru = (r["esocial_status"] or "").lower()
        if recibo:
            status_norm = "aceito"
        else:
            status_norm = _STATUS_MAP.get(cru, "enviado" if protocolo else "pendente")
        tipo = r["tipo"]
        desc = _TIPO_DESC.get(tipo, tipo)
        itens.append(
            {
                "id": f"{tipo}:{r['ref_id']}",
                "evento": f"{desc} — {r['funcionario'] or 'N/A'}",
                "tipo": tipo,
                "colaborador": r["funcionario"] or "N/A",
                "cpf": r["cpf"] or "",
                "status": status_norm,
                "data": r["updated_at"].isoformat() if r.get("updated_at") else None,
                "protocolo": protocolo or "",
                "recibo": recibo or "",
                "origem": "transmissao_propria",
                "mensagem_retorno": (
                    "Recibo oficial casado pelo governo." if recibo
                    else "Transmitido — aguardando recibo (beat esocial-pull-recibos 2h)."
                    if protocolo else "Aguardando transmissão."
                ),
            }
        )
        if r["cpf"]:
            refs_nossas.add((tipo, r["cpf"], protocolo or recibo or ""))

    # --- Fonte 2: ESPELHO oficial (eventos já no governo) ---
    espelho = (
        await db.execute(
            text(
                "SELECT esp.tipo, esp.cpf_trabalhador, esp.nr_recibo, "
                "  esp.dt_evento, esp.dt_recepcao, esp.transmissor_cnpj, e.nome "
                "FROM esocial_eventos_espelho esp "
                "LEFT JOIN employees e "
                "  ON regexp_replace(e.cpf, '\\D', '', 'g') = esp.cpf_trabalhador "
                "ORDER BY COALESCE(esp.dt_recepcao, esp.created_at) DESC NULLS LAST"
            )
        )
    ).mappings().all()

    for r in espelho:
        tipo = r["tipo"] or "?"
        desc = _TIPO_DESC.get(tipo, "Evento eSocial")
        nome = r["nome"] or "(sem cadastro local)"
        data = None
        if r.get("dt_recepcao"):
            data = r["dt_recepcao"].isoformat()
        elif r.get("dt_evento"):
            data = r["dt_evento"].isoformat()
        # Espelho = veio do governo. Com recibo => aceito; sem => enviado.
        status_norm = "aceito" if r["nr_recibo"] else "enviado"
        itens.append(
            {
                "id": f"espelho:{r['nr_recibo'] or (r['cpf_trabalhador'] or '') + ':' + tipo}",
                "evento": f"{desc} — {nome}",
                "tipo": tipo,
                "colaborador": nome,
                "cpf": r["cpf_trabalhador"] or "",
                "status": status_norm,
                "data": data,
                "protocolo": r["nr_recibo"] or "",
                "recibo": r["nr_recibo"] or "",
                "origem": "espelho_governo",
                "mensagem_retorno": (
                    "Evento oficial no governo (espelho read-only), "
                    f"transmissor {r['transmissor_cnpj'] or 'N/A'}."
                ),
            }
        )

    itens = itens[:limit]

    pendentes = sum(1 for i in itens if i["status"] == "pendente")
    enviados = sum(1 for i in itens if i["status"] == "enviado")
    aceitos = sum(1 for i in itens if i["status"] == "aceito")
    rejeitados = sum(1 for i in itens if i["status"] == "rejeitado")

    return {
        "items": itens,
        "total": len(itens),
        "resumo": {
            "pendentes": pendentes,
            "enviados": enviados,
            "aceitos": aceitos,
            "rejeitados": rejeitados,
        },
        "message": (
            "Eventos eSocial reais — transmissões próprias (protocolo/recibo do governo) "
            "e espelho oficial baixado. Nada fabricado."
        )
        if itens
        else "Nenhum evento eSocial registrado ainda (vazio-real honesto).",
    }
