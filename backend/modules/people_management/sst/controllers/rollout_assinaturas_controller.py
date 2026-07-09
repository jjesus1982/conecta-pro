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
  PRÓPRIA senha. Tela: /portal-funcionario/primeiro-acesso.

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
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assinaturas", tags=["SST — Rollout de Assinaturas (Fichas de EPI)"])

LINK_PRIMEIRO_ACESSO = "/portal-funcionario/primeiro-acesso"
LINK_LOGIN_PORTAL = "/portal-funcionario/login"

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


@router.get("/rollout")
async def rollout_assinaturas(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Rollout das assinaturas de fichas de EPI, por funcionário ativo.

    Tudo por FATO no banco:
    - tem_acesso_portal: employees.portal_password_hash definido (senha própria).
    - ja_logou: evento 'login' em portal_access_logs OU senha definida via
      primeiro acesso (que exige autenticação CPF+data de nascimento e emite
      token) — proxy honesto, explicado em `notas`.
    - fichas_pendentes: sst_fichas_epi com status 'pendente_assinatura'.
    - pronto_para_assinar: tem acesso E tem ficha pendente.
    """
    rows = (await db.execute(text(_ROLLOUT_SQL))).mappings().all()

    funcionarios: list[dict[str, Any]] = []
    for r in rows:
        senha_definida = bool(r["senha_definida"])
        ja_logou = r["logins_registrados"] > 0 or senha_definida
        fichas_pendentes = int(r["fichas_pendentes"])
        funcionarios.append(
            {
                "employee_id": r["employee_id"],
                "nome": r["nome"],
                "cargo": r["cargo"],
                "posto": r["posto"],
                "cpf_mascarado": _mask_cpf(r["cpf"]),
                "tem_acesso_portal": senha_definida,
                "ja_logou": ja_logou,
                "logins_registrados": int(r["logins_registrados"]),
                "ultimo_login": r["ultimo_login"].isoformat() if r["ultimo_login"] else None,
                "acesso_liberado_em": (
                    r["provisionado_em"].isoformat() if r["provisionado_em"] else None
                ),
                "senha_definida_em": (
                    r["portal_password_set_at"].isoformat()
                    if r["portal_password_set_at"]
                    else None
                ),
                "pre_requisitos_ok": bool(r["tem_cpf"]) and bool(r["tem_data_nascimento"]),
                "fichas_pendentes": fichas_pendentes,
                "fichas_assinadas": int(r["fichas_assinadas"]),
                "entregas_sem_ficha": int(r["entregas_sem_ficha"]),
                "pronto_para_assinar": senha_definida and fichas_pendentes > 0,
            }
        )

    total = len(funcionarios)
    com_acesso = sum(1 for f in funcionarios if f["tem_acesso_portal"])
    return {
        "resumo": {
            "total_ativos": total,
            "com_acesso_portal": com_acesso,
            "sem_acesso_portal": total - com_acesso,
            "ja_logaram": sum(1 for f in funcionarios if f["ja_logou"]),
            "com_fichas_pendentes": sum(1 for f in funcionarios if f["fichas_pendentes"] > 0),
            "prontos_para_assinar": sum(1 for f in funcionarios if f["pronto_para_assinar"]),
            "total_fichas_pendentes": sum(f["fichas_pendentes"] for f in funcionarios),
            "total_entregas_sem_ficha": sum(f["entregas_sem_ficha"] for f in funcionarios),
        },
        "notas": [
            "tem_acesso_portal = senha do Portal definida (employees.portal_password_hash).",
            (
                "ja_logou = evento 'login' em portal_access_logs OU senha definida no "
                "primeiro acesso (autentica por CPF+data de nascimento e emite token). "
                "O log de login foi religado agora — histórico anterior não existe."
            ),
            "entregas_sem_ficha = entregas de EPI ainda sem ficha gerada (gerar na aba Entregas & Fichas).",
        ],
        "funcionarios": funcionarios,
    }


@router.post("/ativar-acessos", status_code=201)
async def ativar_acessos_portal(
    data: AtivarAcessosRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Ativação em massa do acesso ao Portal do Funcionário (REUSA o fluxo existente).

    O Portal NÃO tem senha provisionada por admin: o mecanismo existente é o
    PRIMEIRO ACESSO (CPF + data de nascimento → funcionário define a própria
    senha). Aqui nós:
    1) validamos os pré-requisitos de cada funcionário (ativo, CPF e data de
       nascimento no cadastro — sem isso o primeiro acesso é impossível);
    2) registramos a liberação em portal_access_logs (action='provision');
    3) devolvemos a credencial inicial + link para o gestor entregar em mãos.

    NENHUMA senha temporária/fraca é criada — princípio: reusar, não inventar.
    """
    if len(data.employee_ids) > 200:
        raise HTTPException(status_code=400, detail="Máximo de 200 funcionários por lote.")

    resultados: list[dict[str, Any]] = []
    ativados = 0

    for eid in data.employee_ids:
        row = (
            await db.execute(
                text(
                    "SELECT id::text AS id, nome, cpf, cargo, status, data_nascimento, "
                    "portal_password_hash "
                    "FROM employees WHERE id::text = :eid"
                ),
                {"eid": str(eid)},
            )
        ).mappings().first()

        if not row:
            resultados.append(
                {
                    "employee_id": str(eid),
                    "nome": None,
                    "situacao": "erro",
                    "detalhe": "Funcionário não encontrado.",
                }
            )
            continue

        base = {
            "employee_id": row["id"],
            "nome": row["nome"],
            "cargo": row["cargo"],
            "cpf_mascarado": _mask_cpf(row["cpf"]),
        }

        if row["status"] != "ativo":
            resultados.append(
                {**base, "situacao": "erro", "detalhe": f"Status '{row['status']}' — só ativos."}
            )
            continue

        pendencias: list[str] = []
        if not (row["cpf"] or "").strip():
            pendencias.append("sem CPF no cadastro (login é por CPF)")
        if not row["data_nascimento"]:
            pendencias.append(
                "sem data de nascimento no cadastro (obrigatória para validar o primeiro acesso)"
            )
        if pendencias:
            resultados.append(
                {
                    **base,
                    "situacao": "pendencia_cadastro",
                    "detalhe": "Corrigir no DP antes de ativar: " + "; ".join(pendencias),
                }
            )
            continue

        ja_tinha_senha = row["portal_password_hash"] is not None

        # Registro auditável da liberação (enum nativo do PG: cast explícito;
        # o Enum do SQLAlchemy grava o NAME maiúsculo e não bate com os labels)
        await db.execute(
            text(
                "INSERT INTO portal_access_logs (employee_id, action, details, created_at) "
                "VALUES (CAST(:eid AS uuid), CAST('provision' AS portal_access_action_enum), "
                ":det, now())"
            ),
            {
                "eid": row["id"],
                "det": (
                    f"Rollout assinaturas EPI: acesso ao Portal liberado por "
                    f"{getattr(current_user, 'email', None) or getattr(current_user, 'username', 'admin')}. "
                    f"Credencial inicial: CPF + data de nascimento."
                ),
            },
        )
        ativados += 1

        resultados.append(
            {
                **base,
                "situacao": "ja_tinha_senha" if ja_tinha_senha else "ativado",
                "credencial_inicial": CREDENCIAL_INICIAL,
                "link_primeiro_acesso": LINK_PRIMEIRO_ACESSO,
                "link_login": LINK_LOGIN_PORTAL,
                "instrucoes_funcionario": (
                    "1) Abrir o Portal do Funcionário e tocar em 'Primeiro acesso'; "
                    "2) Informar CPF e data de nascimento; 3) Criar a própria senha; "
                    "4) Menu 'Minhas Fichas de EPI' → conferir os itens → 'Assinar'."
                )
                if not ja_tinha_senha
                else (
                    "Já tem senha definida: 1) Login com CPF + senha; "
                    "2) 'Minhas Fichas de EPI' → conferir os itens → 'Assinar'. "
                    "Esqueceu a senha? Usar 'Redefinir senha' (CPF + data de nascimento)."
                ),
            }
        )

    await db.commit()
    logger.info(
        "Rollout assinaturas EPI: %d/%d acessos liberados por %s",
        ativados,
        len(data.employee_ids),
        getattr(current_user, "email", "admin"),
    )

    return {
        "solicitados": len(data.employee_ids),
        "ativados": ativados,
        "resultados": resultados,
        "nota": (
            "Nenhuma senha foi gerada: o Portal usa o fluxo EXISTENTE de primeiro "
            "acesso (CPF + data de nascimento → funcionário cria a própria senha). "
            "Entregar as instruções em mãos nos postos."
        ),
    }
