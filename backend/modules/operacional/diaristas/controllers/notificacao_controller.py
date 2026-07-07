"""
Controller de Notificações para Diaristas.

Fornece endpoints para:
- Envio manual de notificações
- Consulta de notificações enviadas
- Processamento de lembretes em lote
- Estatísticas de envio
"""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.operacional.diaristas.services.notificacao_service import (
    CanalNotificacao,
    StatusNotificacao,
    TipoNotificacao,
    get_notificacao_service,
)

router = APIRouter()


# =============================================================================
# SCHEMAS
# =============================================================================


class EnviarNotificacaoRequest(BaseModel):
    """Request para enviar notificação."""

    diarist_id: UUID
    tipo: TipoNotificacao
    canal: CanalNotificacao = CanalNotificacao.WHATSAPP
    dados: dict[str, Any] | None = None
    mensagem_custom: str | None = Field(None, max_length=1000)
    titulo_custom: str | None = Field(None, max_length=100)
    agendar_para: datetime | None = None


class NotificacaoResponse(BaseModel):
    """Response de notificação."""

    id: str
    diarist_id: str
    tipo: str
    canal: str
    titulo: str
    mensagem: str
    status: str
    criado_em: str
    enviado_em: str | None
    erro: str | None


class EnviarConfirmacaoRequest(BaseModel):
    """Request para enviar confirmação de agendamento."""

    diarist_id: UUID
    schedule_id: UUID


class EnviarLembreteRequest(BaseModel):
    """Request para enviar lembrete."""

    diarist_id: UUID
    schedule_id: UUID


class EnviarAlertaAtrasoRequest(BaseModel):
    """Request para enviar alerta de atraso."""

    diarist_id: UUID
    schedule_id: UUID
    telefone_cliente: str | None = None


class EnviarNotificacaoPagamentoRequest(BaseModel):
    """Request para enviar notificação de pagamento."""

    diarist_id: UUID
    payment_id: UUID
    tipo: TipoNotificacao = TipoNotificacao.PAGAMENTO_APROVADO


class EstatisticasResponse(BaseModel):
    """Response de estatísticas."""

    total: int
    enviados: int
    falhas: int
    agendados: int
    taxa_sucesso: float
    por_tipo: dict[str, int]
    por_canal: dict[str, int]


# =============================================================================
# ENDPOINTS - ENVIO MANUAL
# =============================================================================


@router.post(
    "/enviar",
    response_model=NotificacaoResponse,
    summary="Enviar notificação",
    description="Envia uma notificação para um diarista",
    status_code=201,
)
async def enviar_notificacao(
    request: EnviarNotificacaoRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
):
    """
    Envia uma notificação para um diarista.

    Tipos disponíveis:
    - CONFIRMACAO_AGENDAMENTO
    - LEMBRETE_24H
    - LEMBRETE_1H
    - ALERTA_ATRASO
    - ALERTA_FALTA
    - PAGAMENTO_APROVADO
    - PAGAMENTO_REALIZADO
    - AVALIACAO_RECEBIDA
    - NOVO_AGENDAMENTO
    - CANCELAMENTO
    - REAGENDAMENTO
    - BOAS_VINDAS
    - DOCUMENTOS_PENDENTES
    - CUSTOM (requer mensagem_custom)
    """
    service = get_notificacao_service(db)

    try:
        resultado = await service.criar_notificacao(
            diarist_id=request.diarist_id,
            tipo=request.tipo,
            canal=request.canal,
            dados=request.dados,
            mensagem_custom=request.mensagem_custom,
            titulo_custom=request.titulo_custom,
            agendar_para=request.agendar_para,
        )
        return resultado
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao enviar notificação: {str(e)}"
        )


@router.post(
    "/confirmar-agendamento",
    response_model=NotificacaoResponse,
    summary="Enviar confirmação de agendamento",
    description="Envia notificação de confirmação de agendamento",
    status_code=201,
)
async def enviar_confirmacao_agendamento(
    request: EnviarConfirmacaoRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
):
    """Envia notificação de confirmação de agendamento."""
    service = get_notificacao_service(db)

    try:
        resultado = await service.enviar_confirmacao_agendamento(
            diarist_id=request.diarist_id,
            schedule_id=request.schedule_id,
        )
        return resultado
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/lembrete-24h",
    response_model=NotificacaoResponse,
    summary="Enviar lembrete 24h",
    description="Envia lembrete 24h antes do serviço",
    status_code=201,
)
async def enviar_lembrete_24h(
    request: EnviarLembreteRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
):
    """Envia lembrete 24h antes do serviço."""
    service = get_notificacao_service(db)

    try:
        resultado = await service.enviar_lembrete_24h(
            diarist_id=request.diarist_id,
            schedule_id=request.schedule_id,
        )
        return resultado
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/alerta-atraso",
    response_model=NotificacaoResponse,
    summary="Enviar alerta de atraso",
    description="Envia alerta quando diarista está atrasado",
    status_code=201,
)
async def enviar_alerta_atraso(
    request: EnviarAlertaAtrasoRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
):
    """Envia alerta de atraso para o diarista."""
    service = get_notificacao_service(db)

    try:
        resultado = await service.enviar_alerta_atraso(
            diarist_id=request.diarist_id,
            schedule_id=request.schedule_id,
            telefone_cliente=request.telefone_cliente,
        )
        return resultado
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/pagamento",
    response_model=NotificacaoResponse,
    summary="Enviar notificação de pagamento",
    description="Envia notificação de pagamento aprovado ou realizado",
    status_code=201,
)
async def enviar_notificacao_pagamento(
    request: EnviarNotificacaoPagamentoRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
):
    """Envia notificação de pagamento."""
    service = get_notificacao_service(db)

    try:
        resultado = await service.enviar_notificacao_pagamento(
            diarist_id=request.diarist_id,
            payment_id=request.payment_id,
            tipo=request.tipo,
        )
        return resultado
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# =============================================================================
# ENDPOINTS - PROCESSAMENTO EM LOTE
# =============================================================================


@router.post(
    "/processar-lembretes-24h",
    summary="Processar lembretes 24h",
    description="Processa e envia lembretes para todos os agendamentos de amanhã",
    status_code=201,
)
async def processar_lembretes_24h(
    background_tasks: BackgroundTasks,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
):
    """
    Processa lembretes 24h para todos os agendamentos de amanhã.

    Este endpoint deve ser chamado por um job/cron diário.
    """
    service = get_notificacao_service(db)

    # Executar em background para não bloquear (BackgroundTasks aceita callable async)
    background_tasks.add_task(service.processar_lembretes_24h)

    return {
        "message": "Processamento de lembretes iniciado em background",
        "status": "processing",
    }


@router.post(
    "/verificar-atrasos",
    summary="Verificar atrasos",
    description="Verifica diaristas atrasados e envia alertas",
    status_code=201,
)
async def verificar_atrasos(
    current_user: CurrentActiveUser,
    tolerancia_minutos: int = Query(15, ge=5, le=60, description="Tolerância em minutos"),
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Verifica diaristas atrasados e envia alertas.

    Este endpoint deve ser chamado periodicamente (ex: a cada 5 minutos).
    """
    service = get_notificacao_service(db)

    try:
        resultados = await service.verificar_atrasos(tolerancia_minutos=tolerancia_minutos)
        return {
            "message": "Verificação concluída",
            "atrasos_detectados": len(resultados),
            "alertas_enviados": resultados,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao verificar atrasos: {str(e)}"
        )


# =============================================================================
# ENDPOINTS - CONSULTAS
# =============================================================================


@router.get(
    "/",
    response_model=list[NotificacaoResponse],
    summary="Listar notificações",
    description="Lista notificações enviadas com filtros",
)
async def listar_notificacoes(
    current_user: CurrentActiveUser,
    diarist_id: UUID | None = Query(None, description="Filtrar por diarista"),
    tipo: TipoNotificacao | None = Query(None, description="Filtrar por tipo"),
    status_filter: StatusNotificacao | None = Query(None, alias="status", description="Filtrar por status"),
    limit: int = Query(50, ge=1, le=200, description="Limite de resultados"),
    db: AsyncSession = Depends(get_db),
):
    """Lista notificações enviadas."""
    service = get_notificacao_service(db)

    try:
        notificacoes = service.listar_notificacoes(
            diarist_id=diarist_id,
            tipo=tipo,
            status=status_filter,
            limit=limit,
        )
        return notificacoes
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao listar notificações: {str(e)}"
        )


@router.get(
    "/diarista/{diarist_id}",
    response_model=list[NotificacaoResponse],
    summary="Notificações do diarista",
    description="Lista notificações de um diarista específico",
)
async def listar_notificacoes_diarista(
    diarist_id: UUID,
    current_user: CurrentActiveUser,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Lista notificações de um diarista específico."""
    service = get_notificacao_service(db)

    try:
        notificacoes = service.listar_notificacoes(
            diarist_id=diarist_id,
            limit=limit,
        )
        return notificacoes
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao listar notificações: {str(e)}"
        )


# =============================================================================
# ENDPOINTS - ESTATÍSTICAS
# =============================================================================


@router.get(
    "/estatisticas",
    response_model=EstatisticasResponse,
    summary="Estatísticas de notificações",
    description="Retorna estatísticas de notificações enviadas",
)
async def get_estatisticas(
    current_user: CurrentActiveUser,
    data_inicio: date | None = Query(None, description="Data inicial"),
    data_fim: date | None = Query(None, description="Data final"),
    db: AsyncSession = Depends(get_db),
):
    """Retorna estatísticas de notificações."""
    service = get_notificacao_service(db)

    try:
        estatisticas = service.get_estatisticas(
            data_inicio=data_inicio,
            data_fim=data_fim,
        )
        return estatisticas
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao calcular estatísticas: {str(e)}"
        )


# =============================================================================
# ENDPOINTS - TEMPLATES
# =============================================================================


@router.get("/templates", summary="Listar templates", description="Lista templates de mensagens disponíveis")
async def listar_templates(current_user: CurrentActiveUser):
    """Lista todos os templates de mensagens disponíveis."""
    from modules.operacional.diaristas.services.notificacao_service import TEMPLATES_MENSAGENS

    templates = []
    for tipo, template in TEMPLATES_MENSAGENS.items():
        templates.append(
            {
                "tipo": tipo.value,
                "titulo": template.get("titulo"),
                "mensagem_preview": template.get("mensagem", "")[:200] + "...",
                "variaveis": _extrair_variaveis(template.get("mensagem", "")),
            }
        )

    return {"templates": templates, "total": len(templates)}


@router.get("/templates/{tipo}", summary="Obter template", description="Retorna um template específico")
async def get_template(current_user: CurrentActiveUser, tipo: TipoNotificacao):
    """Retorna um template específico."""
    from modules.operacional.diaristas.services.notificacao_service import TEMPLATES_MENSAGENS

    template = TEMPLATES_MENSAGENS.get(tipo)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Template '{tipo.value}' não encontrado")

    return {
        "tipo": tipo.value,
        "titulo": template.get("titulo"),
        "mensagem": template.get("mensagem"),
        "variaveis": _extrair_variaveis(template.get("mensagem", "")),
    }


def _extrair_variaveis(texto: str) -> list[str]:
    """Extrai variáveis de um template."""
    import re

    return list(set(re.findall(r"\{(\w+)\}", texto)))


# =============================================================================
# ENDPOINTS - CANAIS
# =============================================================================


@router.get("/canais", summary="Listar canais", description="Lista canais de notificação disponíveis")
async def listar_canais(current_user: CurrentActiveUser):
    """Lista canais de notificação disponíveis."""
    return {
        "canais": [
            {
                "id": CanalNotificacao.WHATSAPP.value,
                "nome": "WhatsApp",
                "descricao": "Mensagens via WhatsApp Business API",
                "disponivel": True,
            },
            {
                "id": CanalNotificacao.SMS.value,
                "nome": "SMS",
                "descricao": "Mensagens SMS via Twilio/Zenvia",
                "disponivel": True,
            },
            {
                "id": CanalNotificacao.EMAIL.value,
                "nome": "Email",
                "descricao": "Notificações por email",
                "disponivel": True,
            },
            {
                "id": CanalNotificacao.PUSH.value,
                "nome": "Push Notification",
                "descricao": "Notificações push para app mobile",
                "disponivel": False,
            },
            {
                "id": CanalNotificacao.INTERNO.value,
                "nome": "Interno",
                "descricao": "Apenas registro interno (sem envio)",
                "disponivel": True,
            },
        ]
    }


# =============================================================================
# ENDPOINTS - BOAS-VINDAS
# =============================================================================


@router.post(
    "/boas-vindas/{diarist_id}",
    response_model=NotificacaoResponse,
    summary="Enviar boas-vindas",
    description="Envia mensagem de boas-vindas para novo diarista",
    status_code=201,
)
async def enviar_boas_vindas(
    diarist_id: UUID,
    current_user: CurrentActiveUser,
    canal: CanalNotificacao = Query(CanalNotificacao.WHATSAPP),
    db: AsyncSession = Depends(get_db),
):
    """Envia mensagem de boas-vindas para um novo diarista."""
    service = get_notificacao_service(db)

    try:
        resultado = await service.criar_notificacao(
            diarist_id=diarist_id,
            tipo=TipoNotificacao.BOAS_VINDAS,
            canal=canal,
        )
        return resultado
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
