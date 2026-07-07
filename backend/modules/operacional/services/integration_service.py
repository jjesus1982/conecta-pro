"""
Serviço de Integração Diaristas-Operacional.

Fornece funcionalidades para:
- Alocar diaristas a postos de trabalho
- Vincular schedules de diaristas a shifts
- Dashboard unificado de ocupação
- Métricas consolidadas
"""

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.operacional.diaristas.models import (
    Diarist,
    DiaristAssignment,
    DiaristStatus,
)

logger = logging.getLogger(__name__)


class IntegrationService:
    """Serviço de integração entre Diaristas e módulo Operacional."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # =========================================================================
    # ALOCAÇÃO DE DIARISTAS A POSTOS
    # =========================================================================

    # Valores REAIS dos ENUMs do PostgreSQL (fonte: \d diarist_assignments).
    # ATENÇÃO: os StrEnums em diaristas/models/diarist.py (AssignmentStatus/
    # AssignmentType/RecurrenceType) estão DESALINHADOS do banco — usar os
    # literais abaixo em escrita, senão o INSERT falha com
    # "invalid input value for enum".
    _PG_ASSIGNMENT_STATUS_ATIVO = "ATIVO"  # assignment_status: ATIVO|PAUSADO|ENCERRADO|CANCELADO
    _PG_ASSIGNMENT_STATUS_ENCERRADO = "ENCERRADO"
    _PG_ASSIGNMENT_STATUS_OCUPANTES = ("ATIVO", "PAUSADO")  # bloqueiam nova alocação
    _PG_ASSIGNMENT_TIPO_CONDOMINIO = "CONDOMINIO"  # assignment_type: CONDOMINIO|UNIDADE|AREA_COMUM
    _PG_ASSIGNMENT_TIPO_UNIDADE = "UNIDADE"
    _PG_RECORRENCIA_AVULSO = "AVULSO"  # recurrence_type: AVULSO|SEMANAL|QUINZENAL|MENSAL

    async def alocar_diarista_posto(
        self,
        diarista_id: UUID,
        condominio_id: UUID,
        data_inicio: date,
        data_fim: date | None = None,
        unidade_id: UUID | None = None,
        valor_acordado: Decimal | None = None,
        observacoes: str | None = None,
    ) -> DiaristAssignment:
        """
        Aloca um diarista a um condomínio (schema atual de diarist_assignments).

        REWRITE (Ciclo 3, item 15): o schema antigo (post_id, shift_id,
        cliente_id, contrato_id, client_name, location, start_date, end_date,
        notes, created_by) NÃO EXISTE MAIS. O schema atual usa
        condominio_id/unidade_id/data_inicio/data_fim/observacoes.
        Parâmetros antigos SEM equivalente foram removidos:
        - post_id      → substituído por condominio_id (tabela condominios)
        - shift_id     → sem coluna equivalente (turno agora é hora_inicio/hora_fim)
        - cliente_id   → sem coluna equivalente
        - contrato_id  → sem coluna equivalente
        - created_by   → sem coluna equivalente

        Args:
            diarista_id: ID do diarista (tabela diarists)
            condominio_id: ID do condomínio (tabela condominios) — NOT NULL no banco
            data_inicio: Data de início da alocação
            data_fim: Data de fim (opcional, para alocações temporárias)
            unidade_id: ID da unidade dentro do condomínio (opcional)
            valor_acordado: Valor acordado; se None, usa diarists.valor_diaria do cadastro
            observacoes: Observações adicionais

        Returns:
            DiaristAssignment criado
        """
        # Verificar diarista existe e está ativo (diarists.ativo boolean + status varchar)
        # AsyncSession (o controller injeta async) — select()/await, não .query()
        diarista = (
            await self.db.execute(select(Diarist).where(Diarist.id == diarista_id, Diarist.ativo.is_(True)))
        ).scalar_one_or_none()

        if not diarista:
            raise ValueError(f"Diarista {diarista_id} não encontrado ou inativo")

        if diarista.status != DiaristStatus.ATIVO.value:
            raise ValueError(f"Diarista não está disponível. Status: {diarista.status}")

        # Verificar condomínio existe (tabela condominios não tem model ORM neste módulo;
        # diarist_assignments.condominio_id também não tem FK no banco — validar via SQL)
        condominio_existe = (
            await self.db.execute(text("SELECT 1 FROM condominios WHERE id = :cid"), {"cid": str(condominio_id)})
        ).first()

        if not condominio_existe:
            raise ValueError(f"Condomínio {condominio_id} não encontrado")

        # Verificar se não há conflito de alocação vigente no período.
        # status é ENUM NATIVO do PG (assignment_status) — asyncpg não compara
        # enum = varchar sem cast; usar status::text (mesma razão nos INSERT/UPDATE).
        conflito = (
            await self.db.execute(
                text(
                    "SELECT id FROM diarist_assignments "
                    "WHERE diarist_id = :did AND status::text IN ('ATIVO','PAUSADO') "
                    "AND (data_fim IS NULL OR data_fim >= :di) "
                    "AND (CAST(:df AS date) IS NULL OR data_inicio <= :df) "
                    "LIMIT 1"
                ),
                {"did": str(diarista_id), "di": data_inicio, "df": data_fim},
            )
        ).first()

        if conflito:
            raise ValueError(f"Diarista já possui alocação ativa no período: Assignment {conflito.id}")

        # Criar assignment via SQL com CASTs explícitos: tipo/recorrencia/status
        # são ENUMs nativos do PG e os StrEnums do model estão desalinhados
        # ("avulso"/"rascunho"), então ORM insert falharia de duas formas.
        valor_final = valor_acordado if valor_acordado is not None else diarista.valor_diaria
        assignment_id = (
            await self.db.execute(
                text(
                    "INSERT INTO diarist_assignments "
                    "(id, created_at, updated_at, ativo, diarist_id, condominio_id, unidade_id, "
                    " tipo, data_inicio, data_fim, recorrencia, valor_acordado, status, observacoes) "
                    "VALUES (gen_random_uuid(), now(), now(), true, :did, :cid, :uid, "
                    " CAST(:tipo AS assignment_type), :di, :df, CAST('AVULSO' AS recurrence_type), "
                    " :va, CAST('ATIVO' AS assignment_status), :obs) "
                    "RETURNING id"
                ),
                {
                    "did": str(diarista_id),
                    "cid": str(condominio_id),
                    "uid": str(unidade_id) if unidade_id else None,
                    "tipo": self._PG_ASSIGNMENT_TIPO_UNIDADE if unidade_id else self._PG_ASSIGNMENT_TIPO_CONDOMINIO,
                    "di": data_inicio,
                    "df": data_fim,
                    "va": valor_final,
                    "obs": observacoes,
                },
            )
        ).scalar_one()

        # NOTA: DiaristStatus atual (ativo/inativo/suspenso/...) não tem valor
        # "em serviço" (antigo ON_ASSIGNMENT não existe mais) — o status do
        # diarista NÃO é alterado; "em serviço" deriva das alocações ATIVO.

        await self.db.commit()
        assignment = (
            await self.db.execute(select(DiaristAssignment).where(DiaristAssignment.id == assignment_id))
        ).scalar_one()

        logger.info(
            f"Diarista {diarista_id} alocado ao condomínio {condominio_id} "
            f"de {data_inicio} até {data_fim or 'indefinido'}"
        )

        return assignment

    async def desalocar_diarista_posto(
        self,
        assignment_id: UUID,
        motivo: str | None = None,
    ) -> DiaristAssignment:
        """
        Encerra a alocação de um diarista (schema atual de diarist_assignments).

        REWRITE (Ciclo 3, item 15): encerrar = status ENCERRADO + data_fim=hoje.
        Parâmetro antigo removido sem equivalente:
        - updated_by → sem coluna equivalente no schema atual

        Args:
            assignment_id: ID da alocação
            motivo: Motivo da desalocação (anexado em observacoes)

        Returns:
            DiaristAssignment atualizado
        """
        atual = (
            await self.db.execute(
                text("SELECT id, status::text AS status FROM diarist_assignments WHERE id = :aid"),
                {"aid": str(assignment_id)},
            )
        ).first()

        if not atual:
            raise ValueError(f"Assignment {assignment_id} não encontrado")

        if atual.status == self._PG_ASSIGNMENT_STATUS_ENCERRADO:
            raise ValueError(f"Assignment {assignment_id} já está encerrado")

        # UPDATE via SQL com CAST (status é ENUM nativo do PG — ver alocar acima)
        await self.db.execute(
            text(
                "UPDATE diarist_assignments SET "
                " status = CAST('ENCERRADO' AS assignment_status), data_fim = CURRENT_DATE, updated_at = now(), "
                " observacoes = CASE WHEN CAST(:motivo AS text) IS NULL THEN observacoes "
                "   ELSE btrim(coalesce(observacoes,'') || E'\\nDesalocação: ' || CAST(:motivo AS text)) END "
                "WHERE id = :aid"
            ),
            {"aid": str(assignment_id), "motivo": motivo},
        )

        # NOTA: sem equivalente para o antigo "voltar diarista para ACTIVE" —
        # DiaristStatus atual não tem ON_ASSIGNMENT; o status do diarista não
        # é alterado na alocação, portanto nada a reverter aqui.

        await self.db.commit()
        assignment = (
            await self.db.execute(select(DiaristAssignment).where(DiaristAssignment.id == assignment_id))
        ).scalar_one()

        logger.info(f"Assignment {assignment_id} encerrado (data_fim={assignment.data_fim})")

        return assignment

    # =========================================================================
    # DASHBOARD UNIFICADO
    # =========================================================================

    async def get_dashboard_unificado(
        self,
        data_referencia: date | None = None,
        cliente_id: UUID | None = None,
    ) -> dict[str, Any]:
        """
        Retorna dashboard unificado com métricas de operacional e diaristas.

        REWRITE (2026-07-07): reescrito async com SQL raw sobre o SCHEMA REAL
        (o código antigo usava .query() síncrono sobre AsyncSession e colunas/
        enums defuntos: Shift.start_time, Diarist.is_active, DiaristStatus.
        ON_ASSIGNMENT, DiaristSchedule.date, ScaleStatus.ACTIVE, etc.).

        Args:
            data_referencia: Data de referência (default: hoje)
            cliente_id: Filtrar por cliente específico (aplica-se só a postos)

        Returns:
            Dict com métricas consolidadas
        """
        data_ref = data_referencia or date.today()
        cid = str(cliente_id) if cliente_id else None

        # Métricas de Postos (posts.status é varchar: active/inactive/temporary/suspended)
        # + capacidade REAL = SUM(required_headcount) dos postos ativos (fim da
        # heurística chumbada "postos_ativos * 3 turnos").
        postos = (
            await self.db.execute(
                text(
                    "SELECT count(*) AS total, "
                    " count(*) FILTER (WHERE status = 'active') AS ativos, "
                    " count(*) FILTER (WHERE status = 'inactive') AS inativos, "
                    " COALESCE(SUM(required_headcount) FILTER (WHERE status = 'active'), 0) AS capacidade "
                    "FROM posts "
                    "WHERE CAST(:cid AS uuid) IS NULL OR client_id = CAST(:cid AS uuid)"
                ),
                {"cid": cid},
            )
        ).one()

        # Métricas de Escalas — scales NÃO tem start_date/end_date; a vigência
        # é month/year. ScaleStatus não tem "ACTIVE": ativas = approved/
        # published/in_progress; em execução = in_progress. Filtrar is_active.
        escalas = (
            await self.db.execute(
                text(
                    "SELECT "
                    " count(*) FILTER (WHERE status IN ('approved','published','in_progress')) AS ativas, "
                    " count(*) FILTER (WHERE status = 'in_progress') AS em_execucao "
                    "FROM scales WHERE is_active = true AND month = :m AND year = :y"
                ),
                {"m": data_ref.month, "y": data_ref.year},
            )
        ).one()

        # Métricas de Turnos do dia (shifts.shift_date; NÃO existe start_time)
        turnos = (
            await self.db.execute(
                text(
                    "SELECT count(*) AS hoje, "
                    " count(*) FILTER (WHERE status = 'in_progress') AS em_andamento "
                    "FROM shifts WHERE shift_date = :d"
                ),
                {"d": data_ref},
            )
        ).one()

        # Métricas de Alocações (funcionários fixos) — allocations.status varchar
        alocacoes_ativas = (
            await self.db.execute(text("SELECT count(*) FROM allocations WHERE status = 'active' AND is_active = true"))
        ).scalar_one()

        # Métricas de Diaristas — diarists.ativo (bool) + status varchar minúsculo.
        # NÃO existe DiaristStatus.ON_ASSIGNMENT: "em serviço" deriva de
        # diarist_schedules com status EM_ANDAMENTO na data (ENUM PG → ::text).
        diaristas = (
            await self.db.execute(
                text(
                    "SELECT count(*) AS total, "
                    " count(*) FILTER (WHERE status = 'ativo') AS disponiveis, "
                    " count(*) FILTER (WHERE status = 'suspenso') AS suspensos "
                    "FROM diarists WHERE ativo = true"
                )
            )
        ).one()

        # Assignments vigentes na data (enum nativo PG → status::text)
        assignments_hoje = (
            await self.db.execute(
                text(
                    "SELECT count(*) FROM diarist_assignments "
                    "WHERE status::text = 'ATIVO' AND data_inicio <= :d "
                    "AND (data_fim IS NULL OR data_fim >= :d)"
                ),
                {"d": data_ref},
            )
        ).scalar_one()

        # Schedules do dia (data_trabalho/checkin_real; enum schedule_status → ::text)
        schedules = (
            await self.db.execute(
                text(
                    "SELECT count(*) AS hoje, "
                    " count(*) FILTER (WHERE status::text = 'CONFIRMADO') AS confirmados, "
                    " count(*) FILTER (WHERE checkin_real IS NOT NULL) AS com_checkin, "
                    " count(DISTINCT diarist_id) FILTER (WHERE status::text = 'EM_ANDAMENTO') AS em_servico "
                    "FROM diarist_schedules WHERE data_trabalho = :d"
                ),
                {"d": data_ref},
            )
        ).one()

        # Taxa de ocupação sobre capacidade REAL (SUM(required_headcount) dos
        # postos ativos). Se a soma for 0/NULL, taxa = None honesto (sem chute).
        capacidade_postos = int(postos.capacidade or 0)
        ocupacao_funcionarios = alocacoes_ativas
        ocupacao_diaristas = assignments_hoje
        ocupacao_total = ocupacao_funcionarios + ocupacao_diaristas
        taxa_ocupacao = round(ocupacao_total / capacidade_postos * 100, 2) if capacidade_postos > 0 else None

        ocupacao: dict[str, Any] = {
            "capacidade_estimada": capacidade_postos,
            "funcionarios_alocados": ocupacao_funcionarios,
            "diaristas_alocados": ocupacao_diaristas,
            "total_alocado": ocupacao_total,
            "taxa_ocupacao_percentual": taxa_ocupacao,
        }
        if taxa_ocupacao is not None and taxa_ocupacao > 100:
            ocupacao["nota"] = (
                "Taxa > 100%: required_headcount cadastrado nos postos "
                f"({capacidade_postos}) esta abaixo das alocacoes ativas reais ({ocupacao_total}) — "
                "pendencia de cadastro, nao de calculo."
            )
        if capacidade_postos == 0:
            ocupacao["nota"] = "Capacidade não informada (required_headcount zerado nos postos ativos)"

        return {
            "data_referencia": data_ref.isoformat(),
            "postos": {
                "total": postos.total,
                "ativos": postos.ativos,
                "inativos": postos.inativos,
            },
            "escalas": {
                "ativas": escalas.ativas,
                "em_execucao": escalas.em_execucao,
            },
            "turnos": {
                "hoje": turnos.hoje,
                "em_andamento": turnos.em_andamento,
            },
            "funcionarios": {
                "alocacoes_ativas": alocacoes_ativas,
            },
            "diaristas": {
                "total": diaristas.total,
                "disponiveis": diaristas.disponiveis,
                "em_servico": schedules.em_servico,
                "suspensos": diaristas.suspensos,
                "assignments_hoje": assignments_hoje,
                "schedules_hoje": schedules.hoje,
                "schedules_confirmados": schedules.confirmados,
                "com_checkin": schedules.com_checkin,
            },
            "ocupacao": ocupacao,
            "alertas": await self._gerar_alertas(data_ref),
        }

    async def _gerar_alertas(self, data_referencia: date) -> list[dict[str, Any]]:
        """Gera alertas automáticos baseados na situação atual (schema real)."""
        alertas: list[dict[str, Any]] = []

        # Alerta: Postos ativos sem funcionário fixo alocado (allocations.post_id)
        postos_sem_cobertura = (
            await self.db.execute(
                text(
                    "SELECT count(*) FROM posts p "
                    "WHERE p.status = 'active' AND NOT EXISTS ("
                    " SELECT 1 FROM allocations a WHERE a.post_id = p.id AND a.status = 'active' AND a.is_active = true)"
                )
            )
        ).scalar_one()

        if postos_sem_cobertura > 0:
            alertas.append(
                {
                    "tipo": "warning",
                    "categoria": "cobertura",
                    "mensagem": f"{postos_sem_cobertura} posto(s) sem funcionário fixo alocado",
                    "acao_sugerida": "Alocar funcionário ou diarista aos postos descobertos",
                }
            )

        # Alerta: Diaristas com check-in atrasado (schedule CONFIRMADO na data,
        # hora_inicio já passou e checkin_real ausente)
        agora = datetime.now()
        if agora.hour >= 8:  # Após 8h
            schedules_atrasados = (
                await self.db.execute(
                    text(
                        "SELECT count(*) FROM diarist_schedules "
                        "WHERE data_trabalho = :d AND status::text = 'CONFIRMADO' "
                        "AND checkin_real IS NULL AND hora_inicio <= CAST(:agora AS time)"
                    ),
                    {"d": data_referencia, "agora": agora.time().replace(microsecond=0)},
                )
            ).scalar_one()

            if schedules_atrasados > 0:
                alertas.append(
                    {
                        "tipo": "error",
                        "categoria": "presenca",
                        "mensagem": f"{schedules_atrasados} diarista(s) com check-in atrasado",
                        "acao_sugerida": "Entrar em contato para verificar situação",
                    }
                )

        # Alerta: Poucos diaristas disponíveis (ativo=true + status='ativo')
        diaristas_disponiveis = (
            await self.db.execute(text("SELECT count(*) FROM diarists WHERE ativo = true AND status = 'ativo'"))
        ).scalar_one()

        if diaristas_disponiveis < 5:
            alertas.append(
                {
                    "tipo": "info",
                    "categoria": "disponibilidade",
                    "mensagem": f"Apenas {diaristas_disponiveis} diarista(s) disponível(is)",
                    "acao_sugerida": "Considerar recrutar mais diaristas",
                }
            )

        return alertas

    # =========================================================================
    # MÉTRICAS E RELATÓRIOS
    # =========================================================================

    async def get_metricas_periodo(
        self,
        data_inicio: date,
        data_fim: date,
        cliente_id: UUID | None = None,
    ) -> dict[str, Any]:
        """
        Retorna métricas consolidadas para um período.

        REWRITE (2026-07-07): async + SQL raw sobre o schema real
        (data_trabalho/checkin_real/checkout_real; enum schedule_status em
        MAIÚSCULO via ::text; shifts.shift_date — NÃO existe Shift.start_time).

        NOTA DE HONESTIDADE: não existe coluna hours_worked — horas trabalhadas
        = checkout_real - checkin_real quando AMBOS presentes; senão conta 0.
        cliente_id é aceito por compatibilidade mas NÃO é aplicável:
        diarist_schedules e shifts não têm vínculo direto com cliente.

        Args:
            data_inicio: Data inicial do período
            data_fim: Data final do período
            cliente_id: Filtrar por cliente (não aplicável — ver nota)

        Returns:
            Dict com métricas do período
        """
        # Total de dias no período
        dias_periodo = (data_fim - data_inicio).days + 1

        # Schedules de diaristas no período (uma query agregada)
        sched = (
            await self.db.execute(
                text(
                    "SELECT count(*) AS total, "
                    " count(*) FILTER (WHERE status::text = 'CONCLUIDO') AS realizados, "
                    " count(*) FILTER (WHERE status::text = 'CANCELADO') AS cancelados, "
                    " count(*) FILTER (WHERE status::text = 'NAO_COMPARECEU') AS faltas, "
                    " COALESCE(SUM(EXTRACT(EPOCH FROM (checkout_real - checkin_real)) / 3600.0) "
                    "   FILTER (WHERE status::text = 'CONCLUIDO' "
                    "     AND checkin_real IS NOT NULL AND checkout_real IS NOT NULL), 0) AS horas "
                    "FROM diarist_schedules "
                    "WHERE data_trabalho >= :di AND data_trabalho <= :df"
                ),
                {"di": data_inicio, "df": data_fim},
            )
        ).one()

        total_schedules = sched.total
        schedules_realizados = sched.realizados
        schedules_cancelados = sched.cancelados
        schedules_faltas = sched.faltas
        horas_trabalhadas = sched.horas or Decimal("0")

        # Taxa de comparecimento
        taxa_comparecimento = schedules_realizados / total_schedules * 100 if total_schedules > 0 else 0

        # Turnos do período (funcionários fixos) — shifts.shift_date
        turnos = (
            await self.db.execute(
                text(
                    "SELECT count(*) AS total, "
                    " count(*) FILTER (WHERE status = 'completed') AS concluidos "
                    "FROM shifts WHERE shift_date >= :di AND shift_date <= :df"
                ),
                {"di": data_inicio, "df": data_fim},
            )
        ).one()

        turnos_periodo = turnos.total
        turnos_concluidos = turnos.concluidos

        return {
            "periodo": {
                "inicio": data_inicio.isoformat(),
                "fim": data_fim.isoformat(),
                "dias": dias_periodo,
            },
            "diaristas": {
                "total_schedules": total_schedules,
                "realizados": schedules_realizados,
                "cancelados": schedules_cancelados,
                "faltas": schedules_faltas,
                "taxa_comparecimento": round(taxa_comparecimento, 2),
                "horas_trabalhadas": float(horas_trabalhadas),
            },
            "funcionarios": {
                "total_turnos": turnos_periodo,
                "turnos_concluidos": turnos_concluidos,
                "taxa_conclusao": round(turnos_concluidos / turnos_periodo * 100 if turnos_periodo > 0 else 0, 2),
            },
            "consolidado": {
                "total_servicos": total_schedules + turnos_periodo,
                "servicos_concluidos": schedules_realizados + turnos_concluidos,
            },
        }

    async def get_ocupacao_postos(
        self,
        data_referencia: date | None = None,
    ) -> list[dict[str, Any]]:
        """
        Retorna ocupação detalhada de cada posto.

        REWRITE (2026-07-07): async + SQL raw sobre o schema real.

        NOTA DE HONESTIDADE: diarist_assignments NÃO tem post_id (só
        condominio_id) — "diaristas por posto" NÃO é derivável do banco.
        diaristas_alocados retorna 0 com nota em detalhes; a cobertura por
        posto considera apenas funcionários fixos (allocations.post_id).

        Args:
            data_referencia: Data de referência (mantida por compatibilidade;
                allocations são filtradas por status='active', como antes)

        Returns:
            Lista com status de ocupação de cada posto
        """
        postos = (
            await self.db.execute(
                text("SELECT id, name, post_type FROM posts WHERE status = 'active' ORDER BY name")
            )
        ).all()

        if not postos:
            return []

        # Alocações ativas de funcionários fixos, agrupadas por posto em Python
        alocacoes = (
            await self.db.execute(
                text("SELECT id, post_id, employee_id FROM allocations WHERE status = 'active' AND is_active = true")
            )
        ).all()

        alocacoes_por_posto: dict[str, list[Any]] = {}
        for a in alocacoes:
            alocacoes_por_posto.setdefault(str(a.post_id), []).append(a)

        resultado = []
        for posto in postos:
            alocs = alocacoes_por_posto.get(str(posto.id), [])

            resultado.append(
                {
                    "posto_id": str(posto.id),
                    "posto_nome": posto.name,
                    "posto_tipo": str(posto.post_type),
                    "funcionarios_alocados": len(alocs),
                    # NÃO derivável: assignments de diaristas são por condomínio,
                    # não por posto — 0 honesto (nunca inventar vínculo).
                    "diaristas_alocados": 0,
                    "total_alocados": len(alocs),
                    "status": "coberto" if alocs else "descoberto",
                    "detalhes": {
                        "funcionarios": [
                            {"allocation_id": str(a.id), "employee_id": str(a.employee_id)} for a in alocs
                        ],
                        "diaristas": [],
                        "nota_diaristas": (
                            "Alocação de diarista não é vinculada a posto "
                            "(diarist_assignments usa condominio_id) — contagem por posto indisponível"
                        ),
                    },
                }
            )

        return resultado

    async def sugerir_diarista_posto(
        self,
        post_id: UUID,
        data: date,
        habilidades_requeridas: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Sugere diaristas disponíveis para uma data.

        REWRITE (2026-07-07): async + SQL raw sobre o schema real
        (diarists.ativo/status/avaliacao_media/total_servicos/especialidades/
        tipos_servico; NÃO existem is_active/full_name/average_rating/skills/
        total_assignments). Disponível = ativo=true + status='ativo', SEM
        schedule (AGENDADO/CONFIRMADO/EM_ANDAMENTO) na data e SEM assignment
        (ATIVO/PAUSADO) vigente na data.

        NOTA: post_id é mantido para compatibilidade de rota, mas não filtra
        nada — diaristas não têm vínculo com posto no schema atual.

        Args:
            post_id: ID do posto (informativo apenas — ver nota)
            data: Data desejada
            habilidades_requeridas: Habilidades desejadas (comparadas com
                especialidades + tipos_servico do cadastro)

        Returns:
            Lista de diaristas sugeridos ordenados por adequação
        """
        candidatos = (
            await self.db.execute(
                text(
                    "SELECT d.id, d.nome, d.avaliacao_media, d.total_servicos, "
                    " d.especialidades, d.tipos_servico "
                    "FROM diarists d "
                    "WHERE d.ativo = true AND d.status = 'ativo' "
                    "AND NOT EXISTS ("
                    " SELECT 1 FROM diarist_schedules s "
                    " WHERE s.diarist_id = d.id AND s.data_trabalho = :d "
                    " AND s.status::text IN ('AGENDADO','CONFIRMADO','EM_ANDAMENTO')) "
                    "AND NOT EXISTS ("
                    " SELECT 1 FROM diarist_assignments a "
                    " WHERE a.diarist_id = d.id AND a.status::text IN ('ATIVO','PAUSADO') "
                    " AND a.data_inicio <= :d AND (a.data_fim IS NULL OR a.data_fim >= :d)) "
                    "ORDER BY d.avaliacao_media DESC NULLS LAST, d.total_servicos DESC NULLS LAST"
                ),
                {"d": data},
            )
        ).all()

        sugestoes = []
        for diarista in candidatos:
            score = 100
            motivos: list[str] = []

            # Habilidades: comparar com colunas reais (especialidades + tipos_servico)
            if habilidades_requeridas:
                habilidades_diarista = {
                    h.strip().lower()
                    for h in list(diarista.especialidades or []) + list(diarista.tipos_servico or [])
                    if h
                }
                requeridas = {h.strip().lower() for h in habilidades_requeridas if h and h.strip()}
                faltantes = len(requeridas - habilidades_diarista)
                if faltantes > 0:
                    score -= faltantes * 10
                    motivos.append(f"Faltam {faltantes} habilidade(s)")

            # Avaliação média (coluna real: avaliacao_media)
            avaliacao = float(diarista.avaliacao_media) if diarista.avaliacao_media is not None else None
            if avaliacao is not None and avaliacao > 0:
                if avaliacao >= 4.5:
                    score += 10
                    motivos.append("Avaliação excelente")
                elif avaliacao < 3.5:
                    score -= 20
                    motivos.append("Avaliação baixa")

            sugestoes.append(
                {
                    "diarist_id": str(diarista.id),
                    "nome": diarista.nome,
                    "score": score,
                    "motivos": motivos,
                    "avaliacao": avaliacao,
                    "total_servicos": int(diarista.total_servicos or 0),
                }
            )

        # Ordenar por score (desempate: avaliação e experiência reais)
        sugestoes.sort(
            key=lambda x: (x["score"], x["avaliacao"] or 0, x["total_servicos"]),
            reverse=True,
        )

        return sugestoes[:10]  # Top 10


# Singleton para uso global
def get_integration_service(db: AsyncSession) -> IntegrationService:
    """Factory function para obter instância do serviço."""
    return IntegrationService(db)
