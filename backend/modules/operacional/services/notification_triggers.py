"""Notification Triggers - Triggers automáticos de notificações do módulo operacional.

Sprint: Módulo Operacional - Sistema de Notificações Push
"""

import json
import logging
from datetime import date, datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from core.database import get_db
from modules.config.models.tenant import Tenant
from modules.notifications.models import QueuePriority
from modules.notifications.services.push_service import PushNotificationService
from modules.operacional.models.employee import Employee
from modules.operacional.models.post import Post
from modules.operacional.models.scale import Scale
from modules.operacional.models.shift import Shift, ShiftStatus
from modules.operacional.models.substitution import Substitution, SubstitutionStatus

logger = logging.getLogger(__name__)

# Tolerância de atraso em minutos
LATE_TOLERANCE_MINUTES = 15
# Tempo limite para aprovações pendentes (horas)
PENDING_APPROVAL_HOURS = 24


def _get_active_tenants(db: Session) -> list[UUID]:
    """Busca todos os tenant_ids ativos.

    Returns:
        Lista de UUIDs dos tenants ativos.
    """
    rows = (
        db.query(Tenant.id)
        .filter(
            Tenant.status == "active",
            Tenant.ativo.is_(True),
        )
        .all()
    )
    return [row[0] for row in rows]


class OperacionalNotificationTriggers:
    """Triggers de notificações automáticas para o módulo operacional."""

    def __init__(self, db: Session, tenant_id: UUID):
        """Inicializa triggers.

        Args:
            db: Sessão do banco de dados
            tenant_id: ID do tenant
        """
        self.db = db
        self.tenant_id = tenant_id
        self.push_service = PushNotificationService(db, tenant_id)

    def _destinatarios_operacionais(self) -> list[UUID]:
        """Quem recebe os alertas de cobertura: gerentes operacionais + supervisores
        (Gonzaga/Paiva). Por ROLE (sobrevive a troca de pessoa), não por gestor_id
        individual — que os funcionários não têm setado."""
        from sqlalchemy import text as _t

        # 1 conta por PESSOA (Gonzaga tem 2 contas ativas): prefere @conectamais.pro.
        # Inclui o supervisor Paiva (que usa @gmail) — por isso NÃO filtra domínio.
        rows = self.db.execute(
            _t(
                "SELECT DISTINCT ON (lower(name)) id::text FROM users "
                "WHERE lower(coalesce(role,'')) IN ('gerente_operacional','supervisor') "
                "  AND coalesce(is_active, true) = true "
                "ORDER BY lower(name), (lower(coalesce(email,'')) LIKE '%@conectamais.pro') DESC"
            )
        ).fetchall()
        return [UUID(r[0]) for r in rows]

    def _enviar_alerta(self, uid: UUID, title: str, body: str, extra: dict, ref: str) -> None:
        """Grava o alerta no SINO (in-app) e tenta o push (best-effort).

        SINO é a fonte da verdade do alerta e do dedup. O sino filtra por
        tenant_id == user.id (users não tem coluna tenant_id → _get_tenant_id cai no
        fallback str(user.id)), então tenant_id = uid.
        """
        from sqlalchemy import text as _t

        self.db.execute(
            _t(
                "INSERT INTO communication_notifications "
                "(id, tenant_id, user_id, title, body, type, reference_type, "
                " reference_id, action_url, extra_data, is_active, sent_at, created_at) "
                "VALUES (gen_random_uuid(), :tid, :uid, :title, :body, 'late_employee', "
                " 'shift', :ref, '/modulos/operacional/presenca', "
                " CAST(:extra AS jsonb), true, "
                " (now() AT TIME ZONE 'America/Manaus'), (now() AT TIME ZONE 'America/Manaus'))"
            ),
            {"tid": str(uid), "uid": str(uid), "title": title, "body": body,
             "ref": ref, "extra": json.dumps(extra)},
        )
        try:
            self.push_service.send_push_notification(
                user_id=uid, title=title, body=body, data=extra,
                priority=QueuePriority.HIGH,
                action_url="/modulos/operacional/presenca",
            )
        except Exception:
            pass

    def check_late_employees(self) -> dict:
        """Alerta de COBERTURA para os gerentes operacionais (Gonzaga/Paiva).

        Compara a ESCALA do dia (shifts) com as BATIDAS REAIS (gp_clock_punches,
        fuso Manaus, com cauda noturna) — mesma fonte do quadro de presença. Um
        turno cujo início + tolerância já passou e que NÃO tem batida na janela =
        atrasado/ausente → notifica os destinatários operacionais (sino/push).

        Correções vs. versão antiga (que mandava ZERO alerta): usava
        shifts.actual_start_time (0/3464 populados) e employee.gestor_id (0/50).
        Dedup: não repete o alerta do mesmo shift no mesmo dia.
        """
        from sqlalchemy import text as _t

        try:
            destinatarios = self._destinatarios_operacionais()
            if not destinatarios:
                return {"success": True, "late_employees": 0, "notifications_sent": 0,
                        "details": [], "obs": "sem destinatários operacionais (role)"}

            # Escala esperada de hoje SEM batida na janela do turno (tolerância aplicada),
            # já em fuso Manaus. A cauda noturna (D+1 até 07:00) cobre turnos que viram o dia.
            late_rows = self.db.execute(
                _t(
                    """
                    SELECT sh.id::text AS shift_id, e.nome, p.name AS post_nome,
                           sh.planned_start_time,
                           lu.id::text AS leader_user_id,
                           EXTRACT(EPOCH FROM (
                             now() AT TIME ZONE 'America/Manaus'
                             - (CURRENT_DATE + sh.planned_start_time)
                           ))/60 AS minutes_late
                    FROM shifts sh
                    JOIN posts p ON p.id = sh.post_id
                    JOIN employees e ON e.id = sh.employee_id
                    -- líder do POSTO (Walcicley/Erika/Ediwilson): recebe só do seu posto
                    LEFT JOIN users lu ON lu.employee_id = p.leader_id
                                      AND coalesce(lu.is_active, true) = true
                    WHERE sh.shift_date = (now() AT TIME ZONE 'America/Manaus')::date
                      AND sh.is_active = TRUE
                      AND lower(coalesce(sh.status,'')) IN ('scheduled','agendado','ativo')
                      AND (CURRENT_DATE + sh.planned_start_time)
                          <= (now() AT TIME ZONE 'America/Manaus') - (:tol || ' minutes')::interval
                      AND NOT EXISTS (
                        SELECT 1 FROM gp_clock_punches cp
                        WHERE cp.employee_id = e.id
                          AND (cp.punch_timestamp)
                              BETWEEN (CURRENT_DATE + sh.planned_start_time - interval '1 hour')
                                  AND (CURRENT_DATE + sh.planned_start_time + interval '12 hours')
                      )
                      -- dedup: já notificamos este shift hoje?
                      AND NOT EXISTS (
                        SELECT 1 FROM communication_notifications n
                        WHERE n.extra_data->>'shift_id' = sh.id::text
                          AND n.type = 'late_employee'
                          AND n.created_at::date = (now() AT TIME ZONE 'America/Manaus')::date
                      )
                    ORDER BY p.name, e.nome
                    """
                ),
                {"tol": str(LATE_TOLERANCE_MINUTES)},
            ).fetchall()

            notifications_sent = 0
            details = []
            for r in late_rows:
                mins = int(r.minutes_late or 0)
                title = "⚠ Cobertura de posto"
                body = f"{r.nome} sem batida — {mins}min de atraso no posto {r.post_nome}."
                extra = {"type": "late_employee", "shift_id": r.shift_id,
                         "post": r.post_nome, "colaborador": r.nome, "minutes_late": mins}
                # Destinatários deste turno: gerentes globais (Gonzaga/Paiva) + o LÍDER
                # do posto (só do posto dele). Dedup por id (líder pode não estar no global).
                recipients = list(destinatarios)
                if r.leader_user_id:
                    lid = UUID(r.leader_user_id)
                    if lid not in recipients:
                        recipients.append(lid)
                for uid in recipients:
                    self._enviar_alerta(uid, title, body, extra, r.shift_id)
                    notifications_sent += 1
                details.append({"colaborador": r.nome, "post": r.post_nome,
                                "minutes_late": mins, "leader_alertado": bool(r.leader_user_id)})
            self.db.commit()

            logger.info(
                "Cobertura tenant %s: %d atrasos/ausências, %d alertas enviados a %d gerentes",
                self.tenant_id, len(late_rows), notifications_sent, len(destinatarios),
            )
            return {"success": True, "late_employees": len(late_rows),
                    "notifications_sent": notifications_sent, "details": details}

        except Exception as e:
            logger.error("Erro ao verificar cobertura (tenant %s): %s", self.tenant_id, e)
            return {"success": False, "error": str(e)}

    def check_pending_approvals(self) -> dict:
        """Verifica aprovações de substituição pendentes e envia notificações.

        Busca substituições com status PENDING há mais de 24 horas
        e notifica quem solicitou.

        Returns:
            Dicionário com resultado da verificação
        """
        try:
            logger.info(f"Verificando aprovações pendentes para tenant {self.tenant_id}...")

            cutoff = datetime.now() - timedelta(hours=PENDING_APPROVAL_HOURS)

            # Busca substituições pendentes há mais de 24h
            pending_subs = (
                self.db.query(Substitution, Post)
                .join(Post, Substitution.post_id == Post.id)
                .filter(
                    Post.client_id == str(self.tenant_id),
                    Substitution.status == SubstitutionStatus.PENDING.value,
                    Substitution.requested_at <= cutoff,
                    Substitution.is_active.is_(True),
                )
                .all()
            )

            notifications_sent = 0
            details = []

            for sub, post in pending_subs:
                if not sub.requested_by:
                    continue

                hours_pending = int((datetime.now() - sub.requested_at).total_seconds() / 3600)

                result = self.push_service.send_push_notification(
                    user_id=UUID(str(sub.requested_by)),
                    title="Substituição Pendente",
                    body=(f"Sua solicitação de substituição no posto {post.name} está pendente há {hours_pending}h"),
                    data={
                        "type": "pending_substitution",
                        "substitution_id": str(sub.id),
                        "post_id": str(post.id),
                        "hours_pending": hours_pending,
                    },
                    priority=QueuePriority.NORMAL,
                    action_url=f"/modulos/operacional/substituicoes?id={sub.id}",
                )

                if result.get("success"):
                    notifications_sent += 1

                details.append(
                    {
                        "substitution_id": str(sub.id),
                        "post": post.name,
                        "hours_pending": hours_pending,
                        "requested_by": str(sub.requested_by),
                    }
                )

            logger.info(
                f"Tenant {self.tenant_id}: {len(pending_subs)} pendentes, {notifications_sent} notificações enviadas"
            )

            return {
                "success": True,
                "pending_approvals": len(pending_subs),
                "notifications_sent": notifications_sent,
                "details": details,
            }

        except Exception as e:
            logger.error(f"Erro ao verificar aprovações (tenant {self.tenant_id}): {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def notify_scale_change(
        self,
        scale_id: UUID,
        change_type: str,
        user_id: UUID,
    ) -> dict:
        """Notifica sobre alteração em escala.

        Args:
            scale_id: ID da escala
            change_type: Tipo de alteração (created, updated, cancelled)
            user_id: ID do usuário para notificar

        Returns:
            Dicionário com resultado
        """
        try:
            messages = {
                "created": {
                    "title": "Nova Escala",
                    "body": "Uma nova escala foi criada",
                },
                "updated": {
                    "title": "Escala Alterada",
                    "body": "Uma escala foi alterada",
                },
                "cancelled": {
                    "title": "Escala Cancelada",
                    "body": "Uma escala foi cancelada",
                },
            }

            message = messages.get(change_type, messages["updated"])

            result = self.push_service.send_push_notification(
                user_id=user_id,
                title=message["title"],
                body=message["body"],
                data={
                    "type": "scale_change",
                    "change_type": change_type,
                    "scale_id": str(scale_id),
                },
                priority=QueuePriority.HIGH,
                action_url=f"/modulos/operacional/escalas/{scale_id}",
            )

            return result

        except Exception as e:
            logger.error(f"Erro ao notificar alteração de escala: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def notify_emergency(
        self,
        post_id: UUID,
        emergency_type: str,
        description: str,
        user_id: UUID,
    ) -> dict:
        """Notifica sobre emergência em posto.

        Args:
            post_id: ID do posto
            emergency_type: Tipo de emergência
            description: Descrição da emergência
            user_id: ID do usuário para notificar

        Returns:
            Dicionário com resultado
        """
        try:
            result = self.push_service.send_push_notification(
                user_id=user_id,
                title=f"EMERGÊNCIA: {emergency_type}",
                body=description,
                data={
                    "type": "emergency",
                    "emergency_type": emergency_type,
                    "post_id": str(post_id),
                },
                priority=QueuePriority.CRITICAL,
                action_url=f"/modulos/operacional/postos/{post_id}",
            )

            return result

        except Exception as e:
            logger.error(f"Erro ao notificar emergência: {e}")
            return {
                "success": False,
                "error": str(e),
            }


def run_late_employees_check():
    """Executa verificação de colaboradores atrasados para todos os tenants (cronjob)."""
    db = next(get_db())
    try:
        tenant_ids = _get_active_tenants(db)
        logger.info(f"Cronjob atrasos: processando {len(tenant_ids)} tenants")

        results = []
        for tenant_id in tenant_ids:
            try:
                triggers = OperacionalNotificationTriggers(db, tenant_id)
                result = triggers.check_late_employees()
                results.append({"tenant_id": str(tenant_id), **result})
            except Exception as e:
                logger.error(f"Cronjob atrasos falhou para tenant {tenant_id}: {e}")
                results.append({"tenant_id": str(tenant_id), "success": False, "error": str(e)})

        logger.info(f"Cronjob atrasos concluído: {len(results)} tenants processados")
    finally:
        db.close()


def run_pending_approvals_check():
    """Executa verificação de aprovações pendentes para todos os tenants (cronjob)."""
    db = next(get_db())
    try:
        tenant_ids = _get_active_tenants(db)
        logger.info(f"Cronjob aprovações: processando {len(tenant_ids)} tenants")

        results = []
        for tenant_id in tenant_ids:
            try:
                triggers = OperacionalNotificationTriggers(db, tenant_id)
                result = triggers.check_pending_approvals()
                results.append({"tenant_id": str(tenant_id), **result})
            except Exception as e:
                logger.error(f"Cronjob aprovações falhou para tenant {tenant_id}: {e}")
                results.append({"tenant_id": str(tenant_id), "success": False, "error": str(e)})

        logger.info(f"Cronjob aprovações concluído: {len(results)} tenants processados")
    finally:
        db.close()
