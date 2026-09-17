"""Rollout de Assinaturas das Fichas de EPI — acesso ao Portal do Funcionário.

MISSÃO: as fichas de EPI (sst_fichas_epi) só saem de 'pendente_assinatura'
quando o PRÓPRIO funcionário loga no Portal e assina digitalmente
(portal_digital_signatures). Este controller dá ao gestor a visão de quem
está pronto e a ativação em massa dos acessos.

COMO O PORTAL AUTENTICA (mecanismo EXISTENTE — nada novo foi inventado):
- Credenciais moram em employees: portal_password_hash (bcrypt),
  portal_password_set_at, portal_first_access. NÃO existe tabela de usuários
  separada para funcionários.
- Login: POST /people-management/portal/auth/login — CPF + senha OU
  CPF + data de nascimento.
- Primeiro acesso: POST /people-management/portal/auth/primeiro-acesso —
  CPF + data de nascimento (validação de identidade) → funcionário define a
  PRÓPRIA senha. Tela: /forgot-password.

Portanto "ativar acesso" NÃO cria senha (nenhuma senha fraca é gerada):
valida os pré-requisitos (CPF + data de nascimento no cadastro), registra a
liberação em portal_access_logs (action='provision') e devolve a credencial
inicial = "CPF + data de nascimento" + link do primeiro acesso, para o
gestor entregar em mãos nos postos.

Endpoints:
- GET  /sst/assinaturas/rollout        (visão por funcionário ativo + resumo)
- POST /sst/assinaturas/ativar-acessos {employee_ids[]} (ativação em massa)
"""

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assinaturas", tags=["SST — Rollout de Assinaturas (Fichas de EPI)"])

# Portal antigo desligado em 17/09/2026 — ver aviso_assinatura_service.
LINK_PRIMEIRO_ACESSO = "/forgot-password"
LINK_LOGIN_PORTAL = "/modulos/meu-espaco?t=assinar"

# Instrução única (mesma para todos): o funcionário usa dados que SÓ ele tem.
CREDENCIAL_INICIAL = (
    "CPF + data de nascimento — no primeiro acesso o funcionário valida a "
    "identidade e define a PRÓPRIA senha (nenhuma senha temporária é gerada)"
)

_ROLLOUT_SQL = """
WITH posto_atual AS (
    SELECT DISTINCT ON (al.employee_id)
           al.employee_id, p.name AS posto_nome
    FROM allocations al
    JOIN posts p ON p.id = al.post_id
    WHERE al.is_active = true AND al.status = 'active'
      AND (al.end_date IS NULL OR al.end_date >= CURRENT_DATE)
    ORDER BY al.employee_id, al.is_primary DESC, al.start_date DESC
),
fichas AS (
    SELECT employee_id,
           count(*) FILTER (WHERE status = 'pendente_assinatura') AS pendentes,
           count(*) FILTER (WHERE status = 'assinada') AS assinadas
    FROM sst_fichas_epi
    GROUP BY employee_id
),
entregas AS (
    SELECT employee_id, count(*) AS sem_ficha
    FROM gp_epi_deliveries
    WHERE ficha_epi_id IS NULL
    GROUP BY employee_id
),
logins AS (
    SELECT employee_id, count(*) AS total, max(created_at) AS ultimo
    FROM portal_access_logs
    WHERE action = 'login' AND employee_id IS NOT NULL
    GROUP BY employee_id
),
provisoes AS (
    SELECT employee_id, max(created_at) AS provisionado_em
    FROM portal_access_logs
    WHERE action = 'provision' AND employee_id IS NOT NULL
    GROUP BY employee_id
)
SELECT e.id::text                                   AS employee_id,
       e.nome,
       e.cargo,
       e.cpf,
       COALESCE(pa.posto_nome, e.posto_atual_nome)  AS posto,
       (e.portal_password_hash IS NOT NULL)         AS senha_definida,
       e.portal_password_set_at,
       (e.cpf IS NOT NULL AND e.cpf <> '')          AS tem_cpf,
       (e.data_nascimento IS NOT NULL)              AS tem_data_nascimento,
       COALESCE(lg.total, 0)                        AS logins_registrados,
       lg.ultimo                                    AS ultimo_login,
       pr.provisionado_em,
       COALESCE(f.pendentes, 0)                     AS fichas_pendentes,
       COALESCE(f.assinadas, 0)                     AS fichas_assinadas,
       COALESCE(en.sem_ficha, 0)                    AS entregas_sem_ficha
FROM employees e
LEFT JOIN posto_atual pa ON pa.employee_id = e.id
LEFT JOIN fichas f       ON f.employee_id = e.id
LEFT JOIN entregas en    ON en.employee_id = e.id
LEFT JOIN logins lg      ON lg.employee_id = e.id
LEFT JOIN provisoes pr   ON pr.employee_id = e.id
WHERE e.status = 'ativo'
ORDER BY e.nome
"""


def _mask_cpf(cpf: str | None) -> str | None:
    """035.***.***-38 — identifica sem expor o CPF inteiro na lista impressa."""
    if not cpf:
        return None
    clean = cpf.replace(".", "").replace("-", "").strip()
    if len(clean) != 11:
        return cpf
    return f"{clean[:3]}.***.***-{clean[9:]}"


class AtivarAcessosRequest(BaseModel):
    """Lote de funcionários para liberar o acesso ao Portal."""

    employee_ids: list[str] = Field(..., min_length=1, description="UUIDs de employees ativos")
