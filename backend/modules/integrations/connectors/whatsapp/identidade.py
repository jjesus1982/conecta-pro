"""Quem está do outro lado: FUNCIONÁRIO, dono, cliente ou lead (11/09/2026).

Por que existe. Medido nas 2.074 mensagens do José Luís entre 16/06 e 11/09: dos 98 números que
falaram com ele, **64 são de funcionários** — e 25 deles viraram LEAD, porque o único caminho de
identidade na entrada era `_match_or_create_lead`, que ou casa um lead ou cria um. O
`agent_service.py` tem 7.379 linhas e ZERO consultas à tabela `employees`: para ele, funcionário
não existe.

O retrato do defeito, na conversa do Rene em 10/09:

    21:45  (saída)  "Seu turno no Condomínio Villa Dei Fiori começa às 18:00. Bata o ponto…"
    17:27  (ele)    "já entrei no link e não tem documentos para ser assinados"
    17:27  (agente) "…provavelmente os  Ah, e pra eu já te registrar certinho aqui,
                     me confirma o CNPJ do condomínio/empresa, por favor? 🙏"

A automação de SAÍDA sabia o turno e o condomínio dele. A de ENTRADA pediu o CNPJ de um porteiro.

Casamento por telefone: os 8 últimos dígitos, mesma régua do `find_duplicate` do CRM — o mesmo
número chega com e sem o nono dígito, com e sem DDI, e exigir igualdade exata já fez o CRM criar
lead duplicado (lição de 09/08).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

Tipo = Literal["dono", "funcionario", "cliente", "lead", "desconhecido"]


@dataclass
class Identidade:
    tipo: Tipo
    nome: str | None = None
    employee_id: str | None = None
    cpf: str | None = None
    cargo: str | None = None
    posto: str | None = None
    condominio: str | None = None
    client_id: str | None = None

    @property
    def e_da_casa(self) -> bool:
        """Funcionário ou dono — quem NUNCA deve ouvir 'me confirma o CNPJ'."""
        return self.tipo in ("funcionario", "dono")


def so_digitos(v: str | None) -> str:
    return re.sub(r"\D", "", v or "")


def chave(telefone: str | None) -> str:
    """Últimos 8 dígitos — a mesma chave que o CRM usa para deduplicar contato."""
    return so_digitos(telefone)[-8:]


_SQL_FUNCIONARIO = """
    SELECT e.id::text, e.nome, e.cpf, e.cargo,
           p.name  AS posto,
           g.name  AS condominio
      FROM employees e
      LEFT JOIN allocations a ON a.employee_id = e.id AND a.status = 'active' AND a.is_active
      LEFT JOIN posts p       ON p.id = a.post_id
      LEFT JOIN ged_clients g ON g.id = p.ged_client_id
     WHERE right(regexp_replace(coalesce(e.celular, e.telefone, ''), '[^0-9]', '', 'g'), 8) = :k
       AND length(regexp_replace(coalesce(e.celular, e.telefone, ''), '[^0-9]', '', 'g')) >= 8
       AND coalesce(e.status, 'ativo') <> 'inativo'
     ORDER BY (a.id IS NOT NULL) DESC, e.updated_at DESC NULLS LAST
     LIMIT 1
"""

_SQL_CLIENTE = """
    SELECT c.id::text, c.name
      FROM clients c
     WHERE right(regexp_replace(coalesce(c.phone, ''), '[^0-9]', '', 'g'), 8) = :k
       AND length(regexp_replace(coalesce(c.phone, ''), '[^0-9]', '', 'g')) >= 8
     LIMIT 1
"""


async def quem_e(db, telefone: str | None, *, e_dono: bool = False) -> Identidade:
    """Resolve a identidade de quem escreveu. Nunca levanta: na dúvida devolve 'desconhecido'.

    A ordem é deliberada — DONO, FUNCIONÁRIO, CLIENTE, LEAD. Quem é da casa é resolvido antes de
    qualquer coisa que possa criar cadastro: um porteiro perguntando do ponto não pode virar
    oportunidade no funil.
    """
    from sqlalchemy import text as sql

    k = chave(telefone)
    if e_dono:
        return Identidade(tipo="dono", nome="Jordan")
    if len(k) < 8:
        return Identidade(tipo="desconhecido")
    try:
        row = (await db.execute(sql(_SQL_FUNCIONARIO), {"k": k})).first()
        if row:
            return Identidade(tipo="funcionario", employee_id=row[0], nome=row[1], cpf=row[2],
                              cargo=row[3], posto=row[4], condominio=row[5])
        row = (await db.execute(sql(_SQL_CLIENTE), {"k": k})).first()
        if row:
            return Identidade(tipo="cliente", client_id=row[0], nome=row[1])
    except Exception as exc:  # noqa: BLE001 — identidade é acessório; a mensagem não pode se perder
        logger.warning("identidade: falhei ao resolver %s — sigo como desconhecido (%s)", k, exc)
        return Identidade(tipo="desconhecido")
    return Identidade(tipo="lead")
