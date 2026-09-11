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

⚠️ `coalesce(nullif(celular,''), telefone)` e não `coalesce(celular, telefone)`: o segundo NÃO
cai para o telefone quando `celular` é string VAZIA — só quando é NULL. Medido em 11/09: o
NAILSON, ativo, com o número no campo `telefone` e `celular` em branco, era invisível para esta
função e teria sido tratado como LEAD. Um registro hoje; o defeito, permanente.

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

#: Status de `employees` que NÃO representam vínculo — quem está aqui não é "gente da casa".
#: Exportado de propósito: o oráculo que vigia esta regra IMPORTA daqui em vez de repetir a
#: lista. Duas cópias da mesma régua divergem, e a que diverge cala — aconteceu duas vezes em
#: 11/09, nas duas direções (o oráculo media `= 'ativo'`, depois `<> 'inativo'`, e o código
#: media outra coisa das duas vezes).
#: DEMITIDO fica FORA desta lista de propósito: ele ainda pergunta de rescisão e de espelho, e
#: virar lead nessa hora seria pior que não saber quem é.
SEM_VINCULO = ("inativo", "candidato", "pj_pendente")


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


#: ⚠️ `DISTINCT ON (e.id)`, e essa linha é a diferença entre contar PESSOAS e contar LINHAS.
#: A primeira versão do teste de ambiguidade lia `len(linhas) > 1` sobre este SELECT e acusou
#: o EULER FELIPE como "dois funcionários" — é um só, com DUAS alocações ativas, e o LEFT JOIN
#: multiplica a pessoa por posto. Ele teria perdido as ferramentas de ponto por causa da
#: própria trava que eu tinha acabado de escrever contra esse mesmo tipo de erro.
#: A subconsulta colapsa em uma linha por pessoa; só então o LIMIT 2 significa "duas PESSOAS".
_SQL_FUNCIONARIO = """
    SELECT q.id, q.nome, q.cpf, q.cargo, q.posto, q.condominio
      FROM (
        SELECT DISTINCT ON (e.id)
               e.id::text AS id, e.nome, e.cpf, e.cargo,
               p.name AS posto, g.name AS condominio,
               (a.id IS NOT NULL) AS tem_alocacao, e.updated_at
          FROM employees e
          LEFT JOIN allocations a ON a.employee_id = e.id AND a.status = 'active' AND a.is_active
          LEFT JOIN posts p       ON p.id = a.post_id
          LEFT JOIN ged_clients g ON g.id = p.ged_client_id
         WHERE right(regexp_replace(coalesce(nullif(e.celular, ''), e.telefone, ''), '[^0-9]', '', 'g'), 8) = :k
           AND length(regexp_replace(coalesce(nullif(e.celular, ''), e.telefone, ''), '[^0-9]', '', 'g')) >= 8
           -- 11/09/2026: `<> 'inativo'` deixava entrar CANDIDATO e PJ_PENDENTE, que não têm
       -- vínculo — e foi assim que o NAILSON virou "outra pessoa": o registro de candidato
       -- dele sobreviveu à contratação (mesmo CPF) e era o único que o telefone alcançava.
       -- Quem já foi DEMITIDO continua sendo gente da casa aqui de propósito: ele ainda
       -- pergunta de rescisão e de espelho, e virar lead nessa hora seria pior.
       AND lower(coalesce(e.status, 'ativo')) <> ALL(:sem_vinculo)
         ORDER BY e.id, (a.id IS NOT NULL) DESC, a.start_date DESC NULLS LAST
      ) q
     ORDER BY q.tem_alocacao DESC, q.updated_at DESC NULLS LAST
     LIMIT 2
"""

_SQL_CLIENTE = """
    SELECT c.id::text, c.name
      FROM clients c
     WHERE right(regexp_replace(coalesce(c.phone, ''), '[^0-9]', '', 'g'), 8) = :k
       AND length(regexp_replace(coalesce(c.phone, ''), '[^0-9]', '', 'g')) >= 8
     LIMIT 2
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
        # ⚠️ LIMIT 2, e o motivo é a razão de existir deste bloco (11/09/2026). `LIMIT 1` sobre
        # uma chave que PODE repetir é amostra respondendo como se fosse o conjunto: hoje
        # nenhum par de funcionários compartilha os 8 últimos dígitos, então ele acerta — e no
        # dia em que compartilhar, escolhe um em silêncio pelo `ORDER BY`. A consequência aqui
        # não é uma resposta errada: é registrar batida de contingência no ponto de OUTRA
        # pessoa. Medir o conjunto custa uma linha; supor que ele é único custa a jornada de
        # alguém. (O `find_duplicate` do CRM já tinha essa lição: "dedup ambíguo, não escolho".)
        # uma linha por PESSOA (o DISTINCT ON acima garante), então duas linhas = duas pessoas
        linhas = (await db.execute(sql(_SQL_FUNCIONARIO),
                                   {"k": k, "sem_vinculo": list(SEM_VINCULO)})).fetchall()
        if len({r[0] for r in linhas}) > 1:
            # Da casa, sim — mas não sei QUEM. Os dois estados importam e são diferentes:
            # `e_da_casa` continua verdadeiro (ninguém vira lead nem ouve "me confirma o
            # CNPJ") e `employee_id` fica vazio, então as ferramentas de ponto recusam e a
            # conversa vai para gente. Silenciar isso seria o pior dos três caminhos.
            logger.warning("identidade AMBÍGUA: %s casa com %s funcionários (%s) — trato como "
                           "da casa sem identidade; ninguém mexe em ponto assim",
                           k, len(linhas), ", ".join(str(r[1]) for r in linhas))
            return Identidade(tipo="funcionario", nome=None)
        if linhas:
            row = linhas[0]
            return Identidade(tipo="funcionario", employee_id=row[0], nome=row[1], cpf=row[2],
                              cargo=row[3], posto=row[4], condominio=row[5])
        linhas = (await db.execute(sql(_SQL_CLIENTE), {"k": k})).fetchall()
        if len(linhas) > 1:
            logger.warning("identidade AMBÍGUA: %s casa com %s clientes — não escolho", k, len(linhas))
            return Identidade(tipo="desconhecido")
        if linhas:
            return Identidade(tipo="cliente", client_id=linhas[0][0], nome=linhas[0][1])
    except Exception as exc:  # noqa: BLE001 — identidade é acessório; a mensagem não pode se perder
        logger.warning("identidade: falhei ao resolver %s — sigo como desconhecido (%s)", k, exc)
        return Identidade(tipo="desconhecido")
    return Identidade(tipo="lead")
