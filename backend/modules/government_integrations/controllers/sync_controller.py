"""
Controller REST para sincronização de dados governamentais.

Endpoints para:
- Execução manual de sincronizações
- Consulta de status e histórico
- Configuração de agendamentos
- Monitoramento de jobs ativos
"""

import logging
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

from ..sync.sync_manager import ServicoGov, SyncManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sync", tags=["Sincronização Governamental"])


# =============================================================================
# SCHEMAS
# =============================================================================


class ServicoEnum(StrEnum):
    """Serviços disponíveis para sincronização."""

    ESOCIAL = "esocial"
    RECEITA_FEDERAL = "receita_federal"
    NFE = "nfe"
    CTE = "cte"
    MDFE = "mdfe"
    NFSE = "nfse"
    SPED = "sped"
    FGTS = "fgts"
    INSS = "inss"
    GOVBR = "govbr"


class TipoSyncEnum(StrEnum):
    """Tipos de sincronização."""

    INCREMENTAL = "incremental"
    COMPLETA = "completa"


class SyncRequest(BaseModel):
    """Request para executar sincronização."""

    cnpj_empresa: str = Field(..., min_length=14, max_length=14, description="CNPJ da empresa (apenas números)")
    tipo_sync: TipoSyncEnum = Field(default=TipoSyncEnum.INCREMENTAL)
    data_inicial: date | None = Field(None, description="Data inicial para extração")
    data_final: date | None = Field(None, description="Data final para extração")
    parametros_extras: dict[str, Any] | None = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "cnpj_empresa": "12345678000190",
                "tipo_sync": "incremental",
                "data_inicial": "2024-01-01",
                "data_final": "2024-12-31",
            }
        }


class SyncAllRequest(BaseModel):
    """Request para sincronizar todos os serviços."""

    cnpj_empresa: str = Field(..., min_length=14, max_length=14)
    servicos: list[ServicoEnum] | None = Field(None, description="Serviços específicos (None = todos)")
    tipo_sync: TipoSyncEnum = Field(default=TipoSyncEnum.INCREMENTAL)


class AgendamentoRequest(BaseModel):
    """Request para configurar agendamento."""

    cnpj_empresa: str = Field(..., min_length=14, max_length=14)
    servico: ServicoEnum
    intervalo_minutos: int = Field(ge=5, le=1440, description="Intervalo entre execuções (5-1440 min)")
    ativo: bool = Field(default=True)
    horario_inicio: str | None = Field(None, description="Horário de início (HH:MM)")
    horario_fim: str | None = Field(None, description="Horário de fim (HH:MM)")


class ConfiguracaoEmpresaRequest(BaseModel):
    """Request para configurar integração de empresa."""

    cnpj_empresa: str = Field(..., min_length=14, max_length=14)
    certificate_id: str | None = None
    govbr_cpf: str | None = None
    govbr_token: str | None = None
    uf_empresa: str | None = Field(None, max_length=2)
    codigo_municipio: str | None = None
    ambiente: str = Field(default="producao", pattern="^(producao|homologacao)$")


class SyncResultResponse(BaseModel):
    """Response com resultado de sincronização."""

    sucesso: bool
    job_id: str | None = None
    servico: str
    registros_processados: int = 0
    registros_novos: int = 0
    registros_atualizados: int = 0
    registros_erro: int = 0
    mensagem: str = ""
    duracao_segundos: float = 0
    erros: list[dict[str, Any]] = []

    class Config:
        from_attributes = True


class JobStatusResponse(BaseModel):
    """Response com status de job."""

    job_id: str
    servico: str
    cnpj: str
    status: str
    inicio: datetime
    fim: datetime | None = None
    resultado: SyncResultResponse | None = None


class HistoricoResponse(BaseModel):
    """Response com histórico de sincronizações."""

    id: str
    cnpj_empresa: str
    servico: str
    tipo_sync: str
    status: str
    inicio_execucao: datetime
    fim_execucao: datetime | None
    registros_processados: int
    registros_novos: int
    registros_erro: int
    mensagem: str | None
    duracao_segundos: float | None


class StatusSyncResponse(BaseModel):
    """Response com status geral de sincronização."""

    cnpj_empresa: str
    servicos: dict[str, dict[str, Any]]
    jobs_ativos: int
    ultima_sincronizacao: datetime | None


# =============================================================================
# DEPENDENCY
# =============================================================================

_sync_manager: SyncManager | None = None


def get_sync_manager(db: AsyncSession = Depends(get_db)) -> SyncManager:  # type: ignore[arg-type]
    """Obtém instância do SyncManager."""
    global _sync_manager
    if _sync_manager is None:
        _sync_manager = SyncManager(db)
    else:
        _sync_manager.db = db
    return _sync_manager


# =============================================================================
# ENDPOINTS DE EXECUÇÃO
# =============================================================================


@router.post(
    "/{servico}",
    response_model=SyncResultResponse,
    summary="Executar sincronização de serviço",
    description="Executa sincronização manual de um serviço específico",
    status_code=201,
)
async def executar_sync(
    servico: ServicoEnum,
    request: SyncRequest,
    background_tasks: BackgroundTasks,
    current_user: CurrentActiveUser,
    sync_manager: SyncManager = Depends(get_sync_manager),
):
    """
    Executa sincronização de um serviço governamental.

    - **servico**: Serviço a sincronizar (esocial, nfe, receita_federal, etc)
    - **cnpj_empresa**: CNPJ da empresa (14 dígitos)
    - **tipo_sync**: incremental ou completa
    - **data_inicial/final**: Período para extração
    """
    try:
        # Mapear enum
        servico_gov = ServicoGov(servico.value)

        logger.info(
            f"[Sync API] Iniciando sync {servico.value} - CNPJ: {request.cnpj_empresa}, Tipo: {request.tipo_sync}"
        )

        # Executar sincronização
        result = await sync_manager.sincronizar_servico(
            servico=servico_gov,
            cnpj_empresa=request.cnpj_empresa,
            tipo_sync=request.tipo_sync.value,
            data_inicial=request.data_inicial,
            data_final=request.data_final,
            parametros_extras=request.parametros_extras or {},
        )

        return SyncResultResponse(
            sucesso=result.sucesso,
            servico=servico.value,
            registros_processados=result.registros_processados,
            registros_novos=result.registros_novos,
            registros_atualizados=result.registros_atualizados,
            registros_erro=result.registros_erro,
            mensagem=result.mensagem,
            duracao_segundos=result.duracao_segundos,
            erros=result.erros[:10],  # Limitar erros retornados
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception(f"[Sync API] Erro executando sync {servico.value}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro na sincronização: {str(e)}"
        )


@router.post(
    "/todos",
    response_model=dict[str, SyncResultResponse],
    summary="Sincronizar todos os serviços",
    description="Executa sincronização de todos os serviços configurados",
    status_code=201,
)
async def sincronizar_todos(
    request: SyncAllRequest,
    current_user: CurrentActiveUser,
    sync_manager: SyncManager = Depends(get_sync_manager),
):
    """
    Sincroniza múltiplos serviços governamentais.

    - Se **servicos** for None, sincroniza todos os configurados
    - Retorna resultado individual de cada serviço
    """
    try:
        # Determinar serviços
        if request.servicos:
            servicos = [ServicoGov(s.value) for s in request.servicos]
        else:
            servicos = None  # Todos

        logger.info(f"[Sync API] Sincronizando múltiplos serviços - CNPJ: {request.cnpj_empresa}")

        # Executar
        resultados = await sync_manager.sincronizar_todos(
            cnpj_empresa=request.cnpj_empresa,
            servicos=servicos,
        )

        # Formatar resposta
        response = {}
        for servico, result in resultados.items():
            response[servico] = SyncResultResponse(
                sucesso=result.sucesso,
                servico=servico,
                registros_processados=result.registros_processados,
                registros_novos=result.registros_novos,
                registros_atualizados=result.registros_atualizados,
                registros_erro=result.registros_erro,
                mensagem=result.mensagem,
                duracao_segundos=result.duracao_segundos,
                erros=result.erros[:5],
            )

        return response

    except Exception as e:
        logger.exception("[Sync API] Erro sincronizando todos")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro na sincronização: {str(e)}"
        )


@router.post(
    "/{servico}/background",
    response_model=dict[str, str],
    summary="Executar sincronização em background",
    description="Inicia sincronização assíncrona e retorna imediatamente",
    status_code=201,
)
async def executar_sync_background(
    servico: ServicoEnum,
    request: SyncRequest,
    background_tasks: BackgroundTasks,
    current_user: CurrentActiveUser,
    sync_manager: SyncManager = Depends(get_sync_manager),
):
    """
    Inicia sincronização em background.

    Retorna job_id para acompanhamento posterior via GET /sync/jobs/{job_id}
    """
    try:
        servico_gov = ServicoGov(servico.value)

        # Criar job em background
        async def run_sync():
            await sync_manager.sincronizar_servico(
                servico=servico_gov,
                cnpj_empresa=request.cnpj_empresa,
                tipo_sync=request.tipo_sync.value,
                data_inicial=request.data_inicial,
                data_final=request.data_final,
            )

        # Adicionar à fila
        background_tasks.add_task(run_sync)

        # Gerar job_id (simplificado - em produção usar UUID real)
        import uuid

        job_id = str(uuid.uuid4())[:8]

        return {
            "job_id": job_id,
            "status": "iniciado",
            "servico": servico.value,
            "mensagem": "Sincronização iniciada em background. Use GET /sync/jobs para acompanhar.",
        }

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# =============================================================================
# ENDPOINTS DE CONSULTA
# =============================================================================


@router.get(
    "/status/{cnpj}",
    response_model=StatusSyncResponse,
    summary="Status de sincronização",
    description="Retorna status geral de sincronização para uma empresa",
)
async def obter_status(
    cnpj: str,
    current_user: CurrentActiveUser,
    sync_manager: SyncManager = Depends(get_sync_manager),
):
    """
    Obtém status de sincronização de todos os serviços para uma empresa.

    Inclui:
    - Última sincronização de cada serviço
    - Status atual (idle, running, error)
    - Quantidade de jobs ativos
    """
    try:
        # Obter status dos sincronizadores
        servicos_status = {}

        for servico in ServicoGov:
            sync = sync_manager._synchronizers.get(servico.value)
            if sync:
                servicos_status[servico.value] = {
                    "status": sync.status.value,
                    "ultima_sync": sync._obter_ultima_sincronizacao(cnpj),
                    "configurado": True,
                }
            else:
                servicos_status[servico.value] = {
                    "status": "nao_configurado",
                    "ultima_sync": None,
                    "configurado": False,
                }

        # Contar jobs ativos
        jobs_ativos = len(sync_manager.obter_jobs_ativos(cnpj))

        # Última sincronização geral
        ultima_sync = None
        for info in servicos_status.values():
            if info.get("ultima_sync"):
                if not ultima_sync or info["ultima_sync"] > ultima_sync:
                    ultima_sync = info["ultima_sync"]

        return StatusSyncResponse(
            cnpj_empresa=cnpj,
            servicos=servicos_status,
            jobs_ativos=jobs_ativos,
            ultima_sincronizacao=ultima_sync,
        )

    except Exception as e:
        logger.exception(f"[Sync API] Erro obtendo status para {cnpj}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/historico/{cnpj}",
    response_model=list[HistoricoResponse],
    summary="Histórico de sincronizações",
    description="Retorna histórico de sincronizações de uma empresa",
)
async def obter_historico(
    cnpj: str,
    current_user: CurrentActiveUser,
    servico: ServicoEnum | None = None,
    limite: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    Obtém histórico de sincronizações.

    - **servico**: Filtrar por serviço específico
    - **limite**: Quantidade máxima de registros
    - **offset**: Paginação
    """
    try:
        from sqlalchemy import select as _select

        from ..models.sync_models import SyncLog

        # AsyncSession não tem .query() — esta rota devolvia 500 sempre
        stmt = _select(SyncLog).where(SyncLog.cnpj_empresa == cnpj)
        if servico:
            stmt = stmt.where(SyncLog.servico == servico.value)
        logs = (
            (await db.execute(stmt.order_by(SyncLog.inicio_execucao.desc()).offset(offset).limit(limite)))
            .scalars()
            .all()
        )

        return [
            HistoricoResponse(
                id=str(log.id),
                cnpj_empresa=log.cnpj_empresa,
                servico=log.servico,
                tipo_sync=log.tipo_sync.value if hasattr(log.tipo_sync, "value") else str(log.tipo_sync),
                status=log.status.value if hasattr(log.status, "value") else str(log.status),
                inicio_execucao=log.inicio_execucao,
                fim_execucao=log.fim_execucao,
                registros_processados=log.registros_processados or 0,
                registros_novos=log.registros_novos or 0,
                registros_erro=log.registros_erro or 0,
                mensagem=log.mensagem,
                duracao_segundos=(
                    (log.fim_execucao - log.inicio_execucao).total_seconds()
                    if log.fim_execucao and log.inicio_execucao
                    else None
                ),
            )
            for log in logs
        ]

    except Exception as e:
        logger.exception(f"[Sync API] Erro obtendo histórico para {cnpj}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/jobs",
    response_model=list[JobStatusResponse],
    summary="Jobs ativos",
    description="Lista todos os jobs de sincronização ativos",
)
async def listar_jobs(
    current_user: CurrentActiveUser,
    cnpj: str | None = None,
    sync_manager: SyncManager = Depends(get_sync_manager),
):
    """Lista jobs de sincronização em execução."""
    try:
        jobs_data = sync_manager.obter_jobs_ativos(cnpj)

        jobs = [
            JobStatusResponse(
                job_id=j["id"],
                servico=j.get("servico", "unknown"),
                cnpj=j.get("cnpj", ""),
                status=j.get("status", "unknown"),
                inicio=datetime.fromisoformat(j["inicio"]) if j.get("inicio") else datetime.utcnow(),
                fim=None,
                resultado=None,
            )
            for j in jobs_data
        ]

        return jobs

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/jobs/{job_id}", summary="Cancelar job", description="Solicita cancelamento de um job em execução")
async def cancelar_job(
    job_id: str,
    current_user: CurrentActiveUser,
    sync_manager: SyncManager = Depends(get_sync_manager),
):
    """Solicita cancelamento de job de sincronização."""
    try:
        with sync_manager._jobs_lock:
            if job_id not in sync_manager._jobs:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job {job_id} não encontrado")

            job = sync_manager._jobs[job_id]
            servico = job.servico.value if hasattr(job.servico, "value") else job.servico

        if servico and servico in sync_manager._synchronizers:
            sync_manager._synchronizers[servico].cancelar()

        return {
            "job_id": job_id,
            "status": "cancelamento_solicitado",
            "mensagem": "Cancelamento solicitado. O job será interrompido em breve.",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# =============================================================================
# ENDPOINTS DE CONFIGURAÇÃO
# =============================================================================


@router.post(
    "/agendamento",
    summary="Configurar agendamento",
    description="Configura agendamento automático de sincronização",
    status_code=201,
)
async def configurar_agendamento(
    request: AgendamentoRequest,
    current_user: CurrentActiveUser,
    sync_manager: SyncManager = Depends(get_sync_manager),
    db: AsyncSession = Depends(get_db),
):
    """
    Configura agendamento automático para um serviço.

    - **intervalo_minutos**: Tempo entre execuções (mínimo 5 min)
    - **horario_inicio/fim**: Janela de execução (opcional)
    """
    try:
        from sqlalchemy import select as _select

        from ..models.sync_models import SyncAgendamento, TipoSincronizacao

        servico_gov = ServicoGov(request.servico.value)

        # Buscar ou criar agendamento (AsyncSession: select/await, não .query)
        agendamento = (
            await db.execute(
                _select(SyncAgendamento).where(
                    SyncAgendamento.cnpj_empresa == request.cnpj_empresa,
                    SyncAgendamento.servico == request.servico.value,
                )
            )
        ).scalar_one_or_none()

        if agendamento:
            agendamento.intervalo_minutos = request.intervalo_minutos
            agendamento.ativo = request.ativo
            agendamento.horario_inicio = request.horario_inicio
            agendamento.horario_fim = request.horario_fim
            agendamento.updated_at = datetime.utcnow()
        else:
            agendamento = SyncAgendamento(
                cnpj_empresa=request.cnpj_empresa,
                servico=request.servico.value,
                tipo_sync=TipoSincronizacao.INCREMENTAL,
                intervalo_minutos=request.intervalo_minutos,
                ativo=request.ativo,
                horario_inicio=request.horario_inicio,
                horario_fim=request.horario_fim,
            )
            db.add(agendamento)

        await db.commit()

        # Atualizar no manager
        sync_manager.configurar_agendamento(
            cnpj=request.cnpj_empresa,
            servico=servico_gov,
            intervalo_minutos=request.intervalo_minutos,
            ativo=request.ativo,
        )

        return {
            "status": "configurado",
            "cnpj": request.cnpj_empresa,
            "servico": request.servico.value,
            "intervalo_minutos": request.intervalo_minutos,
            "ativo": request.ativo,
        }

    except Exception as e:
        await db.rollback()
        logger.exception("[Sync API] Erro configurando agendamento")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/agendamentos/{cnpj}",
    summary="Listar agendamentos",
    description="Lista agendamentos configurados para uma empresa",
)
async def listar_agendamentos(
    cnpj: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
):
    """Lista todos os agendamentos de sincronização."""
    try:
        from sqlalchemy import select as _select

        from ..models.sync_models import SyncAgendamento

        agendamentos = (
            (await db.execute(_select(SyncAgendamento).where(SyncAgendamento.cnpj_empresa == cnpj)))
            .scalars()
            .all()
        )

        return [
            {
                "id": str(a.id),
                "servico": a.servico,
                "tipo_sync": a.tipo_sync.value if hasattr(a.tipo_sync, "value") else str(a.tipo_sync),
                "intervalo_minutos": a.intervalo_minutos,
                "ativo": a.ativo,
                "horario_inicio": a.horario_inicio,
                "horario_fim": a.horario_fim,
                "ultima_execucao": a.ultima_execucao,
                "proxima_execucao": a.proxima_execucao,
            }
            for a in agendamentos
        ]

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete(
    "/agendamento/{cnpj}/{servico}", summary="Remover agendamento", description="Remove agendamento de sincronização"
)
async def remover_agendamento(
    cnpj: str,
    servico: ServicoEnum,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    sync_manager: SyncManager = Depends(get_sync_manager),
):
    """Remove agendamento de sincronização."""
    try:
        from sqlalchemy import select as _select

        from ..models.sync_models import SyncAgendamento

        agendamento = (
            await db.execute(
                _select(SyncAgendamento).where(
                    SyncAgendamento.cnpj_empresa == cnpj,
                    SyncAgendamento.servico == servico.value,
                )
            )
        ).scalar_one_or_none()

        if not agendamento:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agendamento não encontrado")

        await db.delete(agendamento)
        await db.commit()

        # Remover do manager
        if cnpj in sync_manager._schedules:
            servico_gov = ServicoGov(servico.value)
            sync_manager._schedules[cnpj].pop(servico_gov, None)

        return {"status": "removido", "servico": servico.value}

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/configuracao",
    summary="Configurar integração",
    description="Configura dados de integração para uma empresa",
    status_code=201,
)
async def configurar_integracao(
    request: ConfiguracaoEmpresaRequest,
    current_user: CurrentActiveUser,
    sync_manager: SyncManager = Depends(get_sync_manager),
    db: AsyncSession = Depends(get_db),
):
    """
    Configura integração governamental para uma empresa.

    - **certificate_id**: ID do certificado digital
    - **govbr_cpf/token**: Credenciais Gov.br
    - **uf_empresa**: UF para SEFAZ estadual
    - **ambiente**: producao ou homologacao
    """
    try:
        from sqlalchemy import select as _select

        from ..models.sync_models import ConfiguracaoIntegracao

        # Buscar ou criar configuração (AsyncSession: select/await, não .query)
        config = (
            await db.execute(
                _select(ConfiguracaoIntegracao).where(ConfiguracaoIntegracao.cnpj_empresa == request.cnpj_empresa)
            )
        ).scalar_one_or_none()

        if config:
            if request.certificate_id:
                config.certificate_id = request.certificate_id
            if request.govbr_cpf:
                config.govbr_cpf = request.govbr_cpf
            if request.govbr_token:
                config.govbr_token = request.govbr_token
            if request.uf_empresa:
                config.uf_empresa = request.uf_empresa
            if request.codigo_municipio:
                config.codigo_municipio = request.codigo_municipio
            config.ambiente = request.ambiente
            config.updated_at = datetime.utcnow()
        else:
            config = ConfiguracaoIntegracao(
                cnpj_empresa=request.cnpj_empresa,
                certificate_id=request.certificate_id,
                govbr_cpf=request.govbr_cpf,
                govbr_token=request.govbr_token,
                uf_empresa=request.uf_empresa,
                codigo_municipio=request.codigo_municipio,
                ambiente=request.ambiente,
            )
            db.add(config)

        await db.commit()

        # Configurar no manager
        await sync_manager.configurar_empresa(
            cnpj=request.cnpj_empresa,
            certificate_id=request.certificate_id,
            govbr_token=request.govbr_token,
        )

        return {
            "status": "configurado",
            "cnpj": request.cnpj_empresa,
            "ambiente": request.ambiente,
        }

    except Exception as e:
        await db.rollback()
        logger.exception("[Sync API] Erro configurando integração")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/configuracao/{cnpj}",
    summary="Obter configuração",
    description="Retorna configuração de integração de uma empresa",
)
async def obter_configuracao(
    cnpj: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
):
    """Obtém configuração de integração."""
    try:
        from sqlalchemy import select

        from ..models.sync_models import ConfiguracaoIntegracao

        # AWAIT obrigatório (AsyncSession): sem ele o except engolia e devolvia
        # "configurado: False" mesmo com configuração existente.
        try:
            result = await db.execute(select(ConfiguracaoIntegracao).where(ConfiguracaoIntegracao.cnpj_empresa == cnpj))
            config = result.scalars().first()
        except Exception:
            # Fallback: tabela pode não existir (migration sprint56 não aplicada)
            config = None

        if not config:
            return {
                "cnpj_empresa": cnpj,
                "configurado": False,
            }

        return {
            "cnpj_empresa": config.cnpj_empresa,
            "configurado": True,
            "certificate_id": config.certificate_id,
            "govbr_cpf": config.govbr_cpf[:3] + "***" if config.govbr_cpf else None,
            "uf_empresa": config.uf_empresa,
            "codigo_municipio": config.codigo_municipio,
            "ambiente": config.ambiente,
            "created_at": config.created_at,
            "updated_at": config.updated_at,
        }

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# =============================================================================
# ENDPOINTS DE DADOS SINCRONIZADOS
# =============================================================================


@router.get(
    "/dados/documentos/{cnpj}",
    summary="Listar documentos fiscais",
    description="Lista documentos fiscais sincronizados",
)
async def listar_documentos(
    cnpj: str,
    current_user: CurrentActiveUser,
    tipo: str | None = None,
    data_inicial: date | None = None,
    data_final: date | None = None,
    limite: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Lista documentos fiscais (NF-e, CT-e, NFS-e, etc)."""
    try:
        from sqlalchemy import func as _func
        from sqlalchemy import select as _select

        from ..models.sync_models import DocumentoFiscal

        # AsyncSession não tem .query() — esta rota devolvia 500 sempre
        conds = [DocumentoFiscal.cnpj_empresa == cnpj]
        if tipo:
            conds.append(DocumentoFiscal.tipo_documento == tipo)
        if data_inicial:
            conds.append(DocumentoFiscal.data_emissao >= data_inicial)
        if data_final:
            conds.append(DocumentoFiscal.data_emissao <= data_final)

        total = (await db.execute(_select(_func.count()).select_from(DocumentoFiscal).where(*conds))).scalar() or 0
        documentos = (
            (
                await db.execute(
                    _select(DocumentoFiscal)
                    .where(*conds)
                    .order_by(DocumentoFiscal.data_emissao.desc())
                    .offset(offset)
                    .limit(limite)
                )
            )
            .scalars()
            .all()
        )

        return {
            "total": total,
            "limite": limite,
            "offset": offset,
            "documentos": [
                {
                    "id": str(d.id),
                    "tipo": d.tipo_documento.value if hasattr(d.tipo_documento, "value") else str(d.tipo_documento),
                    "chave": d.chave_acesso,
                    "numero": d.numero,
                    "serie": d.serie,
                    "data_emissao": d.data_emissao,
                    "cnpj_emitente": d.cnpj_emitente,
                    "nome_emitente": d.nome_emitente,
                    "valor_total": float(d.valor_total) if d.valor_total else 0,
                    "status": d.status.value if hasattr(d.status, "value") else str(d.status),
                }
                for d in documentos
            ],
        }

    except Exception as e:
        logger.exception(f"[Sync API] Erro listando documentos para {cnpj}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/dados/eventos-esocial/{cnpj}", summary="Listar eventos eSocial", description="Lista eventos eSocial sincronizados"
)
async def listar_eventos_esocial(
    cnpj: str,
    current_user: CurrentActiveUser,
    tipo_evento: str | None = None,
    periodo: str | None = None,
    limite: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Lista eventos eSocial."""
    try:
        from sqlalchemy import func as _func
        from sqlalchemy import select as _select

        from ..models.sync_models import EventoESocial

        # AsyncSession não tem .query() — esta rota devolvia 500 sempre
        conds = [EventoESocial.cnpj_empresa == cnpj]
        if tipo_evento:
            conds.append(EventoESocial.tipo_evento == tipo_evento)
        if periodo:
            conds.append(EventoESocial.periodo_apuracao == periodo)

        total = (await db.execute(_select(_func.count()).select_from(EventoESocial).where(*conds))).scalar() or 0
        eventos = (
            (
                await db.execute(
                    _select(EventoESocial)
                    .where(*conds)
                    .order_by(EventoESocial.data_evento.desc())
                    .offset(offset)
                    .limit(limite)
                )
            )
            .scalars()
            .all()
        )

        return {
            "total": total,
            "limite": limite,
            "offset": offset,
            "eventos": [
                {
                    "id": str(e.id),
                    "tipo_evento": e.tipo_evento.value if hasattr(e.tipo_evento, "value") else str(e.tipo_evento),
                    "id_evento": e.id_evento,
                    "data_evento": e.data_evento,
                    "periodo_apuracao": e.periodo_apuracao,
                    "cpf_funcionario": e.cpf_funcionario,
                    "matricula": e.matricula,
                    "status": e.status.value if hasattr(e.status, "value") else str(e.status),
                    "recibo": e.recibo,
                }
                for e in eventos
            ],
        }

    except Exception as e:
        logger.exception(f"[Sync API] Erro listando eventos eSocial para {cnpj}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/dados/certidoes/{cnpj}", summary="Listar certidões", description="Lista certidões sincronizadas")
async def listar_certidoes(
    cnpj: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
):
    """Lista certidões (CND, CNDT, CRF, etc)."""
    try:
        from sqlalchemy import select

        from ..models.sync_models import Certidao

        try:
            # AWAIT obrigatório: sem ele o db.execute devolvia coroutine, o .scalars()
            # explodia e o except engolia → certidões SEMPRE vazias em silêncio.
            result = await db.execute(
                select(Certidao).where(Certidao.cnpj_empresa == cnpj).order_by(Certidao.data_emissao.desc())
            )
            certidoes = result.scalars().all()
        except Exception:
            # Tabela pode não existir (migration sprint56 não aplicada)
            return []

        return [
            {
                "id": str(c.id),
                "tipo": c.tipo_certidao,
                "orgao": c.orgao_emissor,
                "numero": c.numero_certidao,
                "data_emissao": c.data_emissao,
                "data_validade": c.data_validade,
                "situacao": c.situacao,
                "valida": c.data_validade >= date.today() if c.data_validade else False,
            }
            for c in certidoes
        ]

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/dados/guias/{cnpj}",
    summary="Listar guias de recolhimento",
    description="Lista guias (DARF, GPS, FGTS) sincronizadas",
)
async def listar_guias(
    cnpj: str,
    current_user: CurrentActiveUser,
    tipo: str | None = None,
    data_inicial: date | None = None,
    data_final: date | None = None,
    limite: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Lista guias de recolhimento."""
    try:
        from sqlalchemy import select as _select

        from ..models.sync_models import GuiaRecolhimento

        # AsyncSession não tem .query() — esta rota devolvia 500 sempre
        conds = [GuiaRecolhimento.cnpj_empresa == cnpj]
        if tipo:
            conds.append(GuiaRecolhimento.tipo_guia == tipo)
        if data_inicial:
            conds.append(GuiaRecolhimento.data_vencimento >= data_inicial)
        if data_final:
            conds.append(GuiaRecolhimento.data_vencimento <= data_final)

        guias = (
            (
                await db.execute(
                    _select(GuiaRecolhimento)
                    .where(*conds)
                    .order_by(GuiaRecolhimento.data_vencimento.desc())
                    .limit(limite)
                )
            )
            .scalars()
            .all()
        )

        return [
            {
                "id": str(g.id),
                "tipo": g.tipo_guia.value if hasattr(g.tipo_guia, "value") else str(g.tipo_guia),
                "codigo_receita": g.codigo_receita,
                "competencia": g.competencia,
                "data_vencimento": g.data_vencimento,
                "valor_principal": float(g.valor_principal) if g.valor_principal else 0,
                "valor_total": float(g.valor_total) if g.valor_total else 0,
                "status": g.status.value if hasattr(g.status, "value") else str(g.status),
                "codigo_barras": g.codigo_barras,
            }
            for g in guias
        ]

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
