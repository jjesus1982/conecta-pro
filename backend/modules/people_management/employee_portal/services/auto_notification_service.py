"""
Auto Notification Service — Disparos automaticos de notificacoes no Portal do Funcionario.

Cada metodo representa um evento de negocio que deve notificar o funcionario.
Os metodos sao chamados por outros services/controllers apos eventos relevantes.

Eventos suportados:
- Contracheque publicado pelo DP
- Escala publicada pelo supervisor
- Documento aguardando assinatura
- Ferias aprovadas
- Alerta de banco de horas negativo
"""

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from modules.people_management.employee_portal.models.notification import (
    PortalNotification,
    PortalNotificationType,
)
from modules.people_management.employee_portal.utils.portal_cache import portal_cache_invalidate

logger = logging.getLogger(__name__)

# Limiar (em horas) para alerta de banco de horas negativo
SALDO_NEGATIVO_LIMIAR = -4.0


class AutoNotificationService:
    """Dispara notificacoes automaticas no Portal do Funcionario.

    Deve ser instanciado com uma sessao de banco e chamado por
    controllers ou outros services apos eventos relevantes.

    Attributes:
        db: Sessao async do banco de dados.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Inicializa o servico.

        Args:
            db: Sessao async do SQLAlchemy.
        """
        self.db = db

    # ------------------------------------------------------------------
    # Metodo interno de criacao
    # ------------------------------------------------------------------

    async def _create(
        self,
        employee_id: str | UUID,
        title: str,
        message: str,
        notification_type: PortalNotificationType,
    ) -> int | None:
        """Cria uma notificacao no banco e invalida o cache do funcionario.

        Args:
            employee_id: UUID do funcionario (str ou UUID).
            title: Titulo da notificacao (max 255 chars).
            message: Corpo da mensagem.
            notification_type: Tipo enum da notificacao.

        Returns:
            ID da notificacao criada ou None em caso de erro.
        """
        try:
            notif = PortalNotification(
                employee_id=str(employee_id) if not isinstance(employee_id, UUID) else employee_id,
                title=title[:255],
                message=message,
                notification_type=notification_type,
                is_read=False,
                created_at=datetime.utcnow(),
            )
            self.db.add(notif)
            await self.db.commit()
            await self.db.refresh(notif)

            # Invalida cache de notificacoes para forcar reload
            await portal_cache_invalidate(str(employee_id), "notificacoes")

            logger.info(
                "AutoNotificacao criada: employee_id=%s tipo=%s titulo=%r",
                employee_id,
                notification_type.value,
                title,
            )
            return notif.id

        except Exception as exc:
            await self.db.rollback()
            logger.error(
                "Erro ao criar auto-notificacao: employee_id=%s tipo=%s erro=%s",
                employee_id,
                notification_type.value,
                exc,
                exc_info=True,
            )
            return None

    # ------------------------------------------------------------------
    # Eventos de negocio
    # ------------------------------------------------------------------

    async def notify_payslip_published(
        self,
        employee_id: str | UUID,
        mes: int,
        ano: int,
    ) -> int | None:
        """Notifica o funcionario quando o DP publica o contracheque.

        Args:
            employee_id: UUID do funcionario.
            mes: Mes de competencia (1-12).
            ano: Ano de competencia.

        Returns:
            ID da notificacao criada ou None em caso de erro.
        """
        meses_pt = [
            "janeiro",
            "fevereiro",
            "marco",
            "abril",
            "maio",
            "junho",
            "julho",
            "agosto",
            "setembro",
            "outubro",
            "novembro",
            "dezembro",
        ]
        nome_mes = meses_pt[mes - 1] if 1 <= mes <= 12 else str(mes)

        return await self._create(
            employee_id=employee_id,
            title="Contracheque disponivel",
            message=(
                f"Seu contracheque de {nome_mes}/{ano} foi publicado e esta "
                "disponivel para consulta na secao 'Contracheques' do portal."
            ),
            notification_type=PortalNotificationType.PAYSLIP_AVAILABLE,
        )

    async def notify_schedule_published(
        self,
        employee_id: str | UUID,
        mes: int,
        ano: int,
    ) -> int | None:
        """Notifica o funcionario quando o supervisor publica a escala.

        Args:
            employee_id: UUID do funcionario.
            mes: Mes de referencia da escala (1-12).
            ano: Ano de referencia.

        Returns:
            ID da notificacao criada ou None em caso de erro.
        """
        meses_pt = [
            "janeiro",
            "fevereiro",
            "marco",
            "abril",
            "maio",
            "junho",
            "julho",
            "agosto",
            "setembro",
            "outubro",
            "novembro",
            "dezembro",
        ]
        nome_mes = meses_pt[mes - 1] if 1 <= mes <= 12 else str(mes)

        return await self._create(
            employee_id=employee_id,
            title="Escala publicada",
            message=(
                f"A escala de {nome_mes}/{ano} foi publicada. Consulte seus turnos na secao 'Minha Escala' do portal."
            ),
            notification_type=PortalNotificationType.SCHEDULE_UPDATE,
        )

    async def notify_document_pending_signature(
        self,
        employee_id: str | UUID,
        doc_id: str,
        doc_nome: str,
    ) -> int | None:
        """Notifica o funcionario sobre documento aguardando assinatura.

        Args:
            employee_id: UUID do funcionario.
            doc_id: ID do documento (para referencia).
            doc_nome: Nome/descricao do documento.

        Returns:
            ID da notificacao criada ou None em caso de erro.
        """
        return await self._create(
            employee_id=employee_id,
            title="Documento aguardando sua assinatura",
            message=(
                f"O documento '{doc_nome}' (ref: {doc_id}) requer sua assinatura. "
                "Acesse a secao 'Documentos' do portal para assinar."
            ),
            notification_type=PortalNotificationType.DOCUMENT_PENDING,
        )

    async def notify_signature_pending(
        self,
        employee_id: str | UUID,
        doc_title: str,
        *,
        dedupe: bool = True,
    ) -> int | None:
        """Notifica o funcionario que ha um documento aguardando a assinatura dele.

        Disparada pelo motor de assinaturas (modules/signatures) sempre que uma
        solicitacao com signatario EMPLOYEE e criada. Usa o tipo DOCUMENT_PENDING
        (categoria de assinatura no portal).

        ANTI-SPAM (dedupe=True, padrao): se o funcionario JA possui uma notificacao
        de assinatura NAO LIDA, nao cria outra — o sino ja o avisa que ha documento
        pendente, e o badge "documentos a assinar (N)" reflete o total real. Assim,
        gerar N documentos em rajada (ex.: um kit inteiro) NAO gera N notificacoes.

        Args:
            employee_id: UUID do funcionario (signer_id da solicitacao).
            doc_title: Titulo/nome do documento (ex.: "Contrato de Trabalho").
            dedupe: Se True, pula a criacao quando ja ha alerta de assinatura nao lido.

        Returns:
            ID da notificacao criada; 0 se pulada por dedupe; None em caso de erro.
        """
        try:
            if dedupe:
                from sqlalchemy import select

                existente = await self.db.execute(
                    select(PortalNotification.id)
                    .where(
                        PortalNotification.employee_id
                        == (str(employee_id) if not isinstance(employee_id, UUID) else employee_id),
                        PortalNotification.notification_type
                        == PortalNotificationType.DOCUMENT_PENDING,
                        PortalNotification.is_read.is_(False),
                    )
                    .limit(1)
                )
                if existente.first() is not None:
                    logger.info(
                        "Assinatura pendente NAO notificada (dedupe): employee_id=%s ja tem alerta nao lido",
                        employee_id,
                    )
                    return 0
        except Exception as exc:  # noqa: BLE001
            # Falha no dedupe nunca impede o alerta nem quebra o chamador.
            logger.warning("Falha no dedupe de assinatura pendente (segue criando): %s", exc)

        nome = (doc_title or "documento").strip()
        return await self._create(
            employee_id=employee_id,
            title=f"Voce tem um documento para assinar: {nome}",
            message=(
                f"O documento '{nome}' requer a sua assinatura. Acesse a aba "
                "'Documentos a assinar' do Meu Espaco para assinar."
            ),
            notification_type=PortalNotificationType.DOCUMENT_PENDING,
        )

    async def notify_vacation_approved(
        self,
        employee_id: str | UUID,
        data_inicio: str,
        dias: int,
    ) -> int | None:
        """Notifica o funcionario quando as ferias sao aprovadas.

        Args:
            employee_id: UUID do funcionario.
            data_inicio: Data de inicio das ferias (formato legivel, ex: '01/07/2026').
            dias: Quantidade de dias de ferias aprovados.

        Returns:
            ID da notificacao criada ou None em caso de erro.
        """
        return await self._create(
            employee_id=employee_id,
            title="Ferias aprovadas",
            message=(
                f"Suas ferias foram aprovadas: {dias} dias a partir de {data_inicio}. "
                "Consulte os detalhes na secao 'Ferias' do portal."
            ),
            notification_type=PortalNotificationType.GENERAL,
        )

    async def notify_overtime_balance_alert(
        self,
        employee_id: str | UUID,
        saldo_horas: float,
    ) -> int | None:
        """Notifica o funcionario quando o banco de horas fica negativo.

        Apenas dispara quando ``saldo_horas`` for menor ou igual a
        ``SALDO_NEGATIVO_LIMIAR`` (-4h por padrao) para evitar spam.

        Args:
            employee_id: UUID do funcionario.
            saldo_horas: Saldo atual do banco de horas (pode ser negativo).

        Returns:
            ID da notificacao criada ou None se limiar nao atingido / erro.
        """
        if saldo_horas > SALDO_NEGATIVO_LIMIAR:
            logger.debug(
                "Saldo %.2f nao atingiu limiar %.2f — notificacao nao disparada",
                saldo_horas,
                SALDO_NEGATIVO_LIMIAR,
            )
            return None

        saldo_fmt = f"{abs(saldo_horas):.1f}h"

        return await self._create(
            employee_id=employee_id,
            title="Atencao: banco de horas negativo",
            message=(
                f"Seu banco de horas esta com saldo negativo de -{saldo_fmt}. "
                "Entre em contato com o seu supervisor para regularizacao."
            ),
            notification_type=PortalNotificationType.WARNING_ISSUED,
        )

    async def notify_warning_issued(
        self,
        employee_id: str | UUID,
        motivo: str,
    ) -> int | None:
        """Notifica o funcionario sobre advertencia ou ocorrencia registrada.

        Args:
            employee_id: UUID do funcionario.
            motivo: Descricao resumida da advertencia.

        Returns:
            ID da notificacao criada ou None em caso de erro.
        """
        return await self._create(
            employee_id=employee_id,
            title="Ocorrencia registrada",
            message=(f"Uma ocorrencia foi registrada em seu historico: {motivo}. Consulte o RH para mais informacoes."),
            notification_type=PortalNotificationType.WARNING_ISSUED,
        )
