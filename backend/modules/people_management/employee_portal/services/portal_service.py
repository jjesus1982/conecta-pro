"""
Portal Service — Autenticacao e dashboard do portal do funcionario.

Gerencia login por CPF, geracao de tokens e dados do dashboard.
"""

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.people_management.employee_portal.models.portal_access import (
    PortalAccess,
    PortalAccessAction,
)

logger = logging.getLogger(__name__)


class PortalService:
    """Servico principal do portal do funcionario.

    Responsavel por autenticacao, dashboard e registro de acessos.

    Attributes:
        db: Sessao async do banco de dados.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Inicializa o servico com sessao de banco.

        Args:
            db: Sessao async do SQLAlchemy.
        """
        self.db = db

    async def authenticate_employee(
        self,
        cpf: str,
        password: str | None = None,
        data_nascimento: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any] | None:
        """Autentica funcionario por CPF + senha ou CPF + data de nascimento.

        Dois modos de login:
        1. CPF + senha (padrao)
        2. CPF + data de nascimento (primeiro acesso ou esqueceu senha)

        Args:
            cpf: CPF do funcionario (com ou sem formatacao).
            password: Senha do portal (modo 1).
            data_nascimento: Data de nascimento YYYY-MM-DD (modo 2).
            ip_address: IP do acesso (para log).
            user_agent: User agent do navegador (para log).

        Returns:
            Dict com employee_id, nome, cargo, cpf, escala se autenticado,
            ou None se credenciais invalidas.
        """
        try:
            from modules.operacional.models.employee import Employee

            cpf_clean = cpf.replace(".", "").replace("-", "").strip()

            query = select(Employee).where(
                Employee.cpf == cpf_clean,
                Employee.status == "ativo",
            )
            result = await self.db.execute(query)
            employee = result.scalar_one_or_none()

            if not employee:
                logger.warning("Tentativa de login com CPF nao encontrado: %s***", cpf_clean[:3])
                return None

            # Buscar portal_password_hash (nao esta no ORM model)
            from sqlalchemy import text

            hash_result = await self.db.execute(
                text("SELECT portal_password_hash FROM employees WHERE id = :eid"),
                {"eid": str(employee.id)},
            )
            portal_hash = hash_result.scalar()

            # Validar credenciais (senha ou data de nascimento)
            if not self._validate_credentials(employee, password, data_nascimento, portal_hash):
                return None

            # log_access desabilitado temporariamente (enum mismatch no DB)
            logger.info("Portal login OK: employee_id=%s", employee.id)

            return {
                "employee_id": str(employee.id),
                "nome": employee.nome,
                "cargo": getattr(employee, "cargo", "") or "",
                "cpf": cpf_clean,
                "escala": getattr(employee, "escala_padrao", "") or "",
            }

        except ImportError:
            logger.error("Modelo Employee nao disponivel.")
            return None
        except Exception as e:
            logger.error("Erro na autenticacao: %s", e, exc_info=True)
            return None

    @staticmethod
    def _validate_credentials(
        employee: Any,
        password: str | None,
        data_nascimento: str | None,
        portal_hash: str | None = None,
    ) -> bool:
        """Valida credenciais do funcionario.

        Args:
            employee: Objeto Employee do banco.
            password: Senha fornecida (modo 1).
            data_nascimento: Data de nascimento YYYY-MM-DD (modo 2).
            portal_hash: Hash bcrypt da senha do portal (buscado previamente).

        Returns:
            True se credenciais validas, False caso contrario.
        """
        if password:
            if portal_hash:
                try:
                    from passlib.hash import bcrypt

                    if not bcrypt.verify(password, portal_hash):
                        logger.warning("Senha incorreta para employee_id=%s", employee.id)
                        return False
                    return True
                except Exception:
                    logger.warning("Erro ao verificar hash para employee_id=%s", employee.id)
                    return False
            # Sem hash definido — primeiro acesso necessario
            logger.info("Funcionario %s sem senha definida (primeiro acesso)", employee.id)
            return False

        if data_nascimento:
            dt_nasc = getattr(employee, "data_nascimento", None)
            # SEGURANÇA: sem data de nascimento cadastrada → NÃO autentica. Antes, dt_nasc=None
            # caía no `return True`, deixando qualquer um entrar só com o CPF + qualquer data.
            if not dt_nasc or str(dt_nasc)[:10] != str(data_nascimento)[:10]:
                logger.warning("Data nascimento ausente/incorreta para employee_id=%s", employee.id)
                return False
            return True

        logger.warning("Nenhuma credencial fornecida para employee_id=%s", employee.id)
        return False

    async def get_dashboard(self, employee_id: UUID) -> dict[str, Any]:
        """Retorna dados do dashboard do funcionario.

        Agrega informacoes de nome, cargo, posto, proximo turno,
        documentos pendentes e notificacoes nao lidas.

        Args:
            employee_id: UUID do funcionario.

        Returns:
            Dict com dados do dashboard.
        """
        dashboard: dict[str, Any] = {
            "name": "",
            "position": None,
            "workplace": None,
            "next_shift": None,
            "pending_documents": 0,
            "unread_notifications": 0,
        }

        try:
            from modules.operacional.models.employee import Employee

            query = select(Employee).where(Employee.id == employee_id)
            result = await self.db.execute(query)
            employee = result.scalar_one_or_none()

            if employee:
                dashboard["name"] = employee.nome
                dashboard["position"] = getattr(employee, "cargo", None)
                # [Veracidade] workplace/next_shift eram null hardcoded — ler do employee (real)
                dashboard["workplace"] = getattr(employee, "cliente_nome", None) or getattr(
                    employee, "posto_atual_nome", None
                )
                dashboard["next_shift"] = getattr(employee, "escala_padrao", None)

        except ImportError:
            logger.warning("Modelo Employee nao disponivel para dashboard.")

        # Contar notificacoes nao lidas
        try:
            from modules.people_management.employee_portal.models.notification import (
                PortalNotification,
            )

            notif_query = select(func.count(PortalNotification.id)).where(
                PortalNotification.employee_id == employee_id,
                PortalNotification.is_read.is_(False),
            )
            notif_result = await self.db.execute(notif_query)
            dashboard["unread_notifications"] = notif_result.scalar() or 0

        except ImportError:
            pass

        # [Veracidade] documentos pendentes = docs do funcionario ainda NAO assinados em ged_kit_documents.
        # Era max(0, 0 - signed) -> sempre 0 (formula quebrada/placeholder).
        try:
            from sqlalchemy import text as _sqltext

            pend = (
                await self.db.execute(
                    _sqltext(
                        "SELECT count(*) FROM ged_kit_documents "
                        "WHERE CAST(employee_id AS TEXT) = :e AND is_signed = false"
                    ),
                    {"e": str(employee_id)},
                )
            ).scalar() or 0
            dashboard["pending_documents"] = pend
        except Exception:
            pass

        return dashboard

    async def log_access(
        self,
        employee_id: UUID,
        action: PortalAccessAction,
        ip_address: str | None = None,
        user_agent: str | None = None,
        device_fingerprint: str | None = None,
        geolocation: dict[str, Any] | None = None,
    ) -> None:
        """Registra um acesso/acao no portal.

        Args:
            employee_id: UUID do funcionario.
            action: Tipo de acao realizada.
            ip_address: IP do acesso.
            user_agent: User agent do navegador.
            device_fingerprint: Fingerprint do dispositivo.
            geolocation: Dados de geolocalizacao.
        """
        try:
            access_log = PortalAccess(
                employee_id=employee_id,
                action=action,
                ip_address=ip_address,
                user_agent=user_agent,
                device_fingerprint=device_fingerprint,
                geolocation=geolocation,
                created_at=datetime.utcnow(),
            )
            self.db.add(access_log)
            await self.db.commit()
        except Exception as e:
            logger.error("Erro ao registrar acesso: %s", e)
            await self.db.rollback()
