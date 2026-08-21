"""Solicitação de contrato assistida — o que falta, e como completar.

Nasce de 21/08/2026: o contrato do Green Hills só existiu porque eu chamei a rota por
`curl`. Ninguém no jurídico, no chat ou no Cowork conseguia pedir "gera o contrato do
Green Hills" — e quando o render recusa por dado faltando, a mensagem morre no log.

Este módulo é a ponte. Ele NÃO renderiza: pergunta ao banco o que já existe, devolve em
forma de PERGUNTA o que falta, e sabe gravar as respostas nos lugares certos.

Por que perguntar em vez de assumir: cada campo que falta tem casa própria — o
representante legal vive em `crm_contacts`, a composição em `contract_items`, o dia de
vencimento em `contracts`. Preencher no lugar errado é o defeito que gerou o
`contract_render` (nome da Eletrônica ao lado do CNPJ da Patrimonial).

REGRA DE DINHEIRO: a soma dos itens tem de bater com `monthly_value`. Sem isso o contrato
sairia com uma composição que não fecha com o valor que o cliente aceitou — e é o valor
por extenso, no meio do instrumento, que vira disputa.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Só estes dois emitem contrato. Decisão do Jordan (21/08): vale para chat, jurídico e
# Cowork — a superfície muda, a parede é a mesma.
EMITENTES = {"jjesus@conectamais.pro", "pjesus@conectamais.pro"}


class NaoAutorizado(PermissionError):
    pass


def pode_emitir(user) -> bool:
    email = (getattr(user, "email", "") or "").strip().lower()
    return email in EMITENTES


def exigir_emitente(user) -> None:
    if not pode_emitir(user):
        raise NaoAutorizado(
            "Emitir contrato é restrito ao Jordan e à Pyetra. "
            "Consultar e listar contratos segue liberado.")


@dataclass
class Pendencia:
    campo: str
    pergunta: str      # o que o agente pergunta ao humano, em português
    onde: str          # onde o dado será gravado — some no relatório, não no contrato
    exemplo: str = ""


@dataclass
class Situacao:
    contrato: str
    cliente: str
    valor_mensal: Decimal
    modelo_id: str | None
    modelo_nome: str | None
    pendencias: list[Pendencia] = field(default_factory=list)

    @property
    def pronto(self) -> bool:
        return not self.pendencias


_SQL = """
SELECT c.id::text AS cid, c.contract_number, c.monthly_value, c.payment_day,
       c.grace_period_days, c.start_date, c.end_date, c.template_id::text AS template_id,
       c.tipo_servico::text AS tipo_servico,
       cl.name AS cliente, cl.id::text AS client_id,
       t.name AS modelo_nome,
       (SELECT count(*) FROM contract_items i
         WHERE i.contract_id = c.id AND coalesce(i.is_active, true)) AS n_itens,
       (SELECT k.name FROM crm_contacts k
         WHERE k.client_id = c.client_id
           AND (k.role ILIKE '%representante%' OR k.role ILIKE '%s%ndic%' OR k.role ILIKE '%legal%')
         ORDER BY k.is_primary DESC NULLS LAST LIMIT 1) AS representante,
       (SELECT k.notes FROM crm_contacts k
         WHERE k.client_id = c.client_id
           AND (k.role ILIKE '%representante%' OR k.role ILIKE '%s%ndic%' OR k.role ILIKE '%legal%')
         ORDER BY k.is_primary DESC NULLS LAST LIMIT 1) AS representante_cpf
FROM contracts c
LEFT JOIN clients cl ON cl.id = c.client_id
LEFT JOIN contract_templates t ON t.id = c.template_id
WHERE c.id::text = :k OR c.contract_number = :k
"""


async def diagnosticar(db: AsyncSession, chave: str) -> Situacao:
    """O que já existe e o que falta para este contrato virar instrumento."""
    r = (await db.execute(text(_SQL), {"k": chave})).mappings().first()
    if not r:
        raise LookupError(f"Contrato não encontrado: {chave}")

    s = Situacao(contrato=r["contract_number"], cliente=r["cliente"] or "—",
                 valor_mensal=Decimal(str(r["monthly_value"] or 0)),
                 modelo_id=r["template_id"], modelo_nome=r["modelo_nome"])

    if not r["template_id"]:
        s.pendencias.append(Pendencia(
            "template_id",
            "Qual modelo de contrato usar? (o contrato ainda não está vinculado a nenhum)",
            "contracts.template_id"))
    if not r["representante"]:
        s.pendencias.append(Pendencia(
            "representante",
            f"Quem assina pelo {r['cliente'] or 'cliente'}? Preciso do nome completo do "
            "representante legal (síndico).",
            "crm_contacts", "Hely Carvalho"))
    if not (r["representante_cpf"] or "").strip():
        s.pendencias.append(Pendencia(
            "representante_cpf", "Qual o CPF de quem assina?", "crm_contacts",
            "562.043.372-20"))
    if not r["payment_day"]:
        s.pendencias.append(Pendencia(
            "payment_day", "Em que dia do mês vence a mensalidade?", "contracts.payment_day", "8"))
    if not r["grace_period_days"]:
        s.pendencias.append(Pendencia(
            "grace_period_days",
            "Em quantos dias vence o PRIMEIRO pagamento, contados da assinatura?",
            "contracts.grace_period_days", "90"))
    if not r["n_itens"]:
        s.pendencias.append(Pendencia(
            "itens",
            "Como se compõe o valor mensal? Preciso da quantidade e do subtotal de cada "
            f"função — a soma tem de fechar em {r['monthly_value']}.",
            "contract_items", "AGP Diurno 2 = 10605.78 · AGP Noturno 2 = 11494.22"))
    if not r["start_date"] or not r["end_date"]:
        s.pendencias.append(Pendencia(
            "vigencia", "Qual o período de vigência (início e término)?",
            "contracts.start_date/end_date", "01/09/2026 a 31/08/2028"))
    return s


async def completar(db: AsyncSession, chave: str, **dados) -> list[str]:
    """Grava as respostas NO LUGAR CERTO de cada uma. Devolve o que foi feito."""
    r = (await db.execute(text(_SQL), {"k": chave})).mappings().first()
    if not r:
        raise LookupError(f"Contrato não encontrado: {chave}")
    feitos: list[str] = []

    if dados.get("template_id"):
        await db.execute(text("UPDATE contracts SET template_id=CAST(:t AS uuid), updated_at=now() "
                              "WHERE id::text=:c"), {"t": dados["template_id"], "c": r["cid"]})
        feitos.append("modelo vinculado ao contrato")

    if dados.get("representante"):
        existe = (await db.execute(text(
            "SELECT id::text FROM crm_contacts WHERE client_id::text=:c "
            "AND (role ILIKE '%representante%' OR role ILIKE '%s%ndic%') LIMIT 1"),
            {"c": r["client_id"]})).scalar()
        cpf = (dados.get("representante_cpf") or "").strip()
        if existe:
            await db.execute(text("UPDATE crm_contacts SET name=:n, notes=coalesce(nullif(:cpf,''), notes), "
                                  "updated_at=now() WHERE id::text=:i"),
                             {"n": dados["representante"], "cpf": cpf, "i": existe})
        else:
            await db.execute(text(
                "INSERT INTO crm_contacts (id, client_id, name, role, notes, is_primary, created_at, updated_at) "
                "VALUES (:i, CAST(:c AS uuid), :n, 'Representante legal', :cpf, false, now(), now())"),
                {"i": str(uuid.uuid4()), "c": r["client_id"], "n": dados["representante"], "cpf": cpf})
        feitos.append(f"representante legal: {dados['representante']}")
    elif dados.get("representante_cpf"):
        await db.execute(text(
            "UPDATE crm_contacts SET notes=:cpf, updated_at=now() WHERE client_id::text=:c "
            "AND (role ILIKE '%representante%' OR role ILIKE '%s%ndic%')"),
            {"cpf": dados["representante_cpf"], "c": r["client_id"]})
        feitos.append("CPF do representante gravado")

    campos = {"payment_day": "dia de vencimento", "grace_period_days": "carência do 1º pagamento"}
    for col, rot in campos.items():
        if dados.get(col) is not None:
            await db.execute(text(f"UPDATE contracts SET {col}=:v, updated_at=now() WHERE id::text=:c"),  # noqa: S608
                             {"v": int(dados[col]), "c": r["cid"]})
            feitos.append(f"{rot}: {dados[col]}")

    itens = dados.get("itens")
    if itens:
        # TRAVA DE DINHEIRO: a composição tem de fechar com o valor acordado. Um contrato
        # cuja tabela não soma o valor por extenso é convite a disputa.
        soma = sum(Decimal(str(i.get("total") or 0)) for i in itens)
        mensal = Decimal(str(r["monthly_value"] or 0))
        if soma != mensal:
            raise ValueError(
                f"A composição soma {soma} e o valor mensal do contrato é {mensal}. "
                "Ajuste os subtotais — o contrato não pode sair com tabela que não fecha.")
        await db.execute(text("DELETE FROM contract_items WHERE contract_id::text=:c"), {"c": r["cid"]})
        for i in itens:
            qtd = int(i.get("qtd") or 0)
            total = Decimal(str(i.get("total") or 0))
            await db.execute(text(
                "INSERT INTO contract_items (id, contract_id, service_type, service_name, description, "
                "quantity, unit_price, total_price, is_active, created_at) "
                "VALUES (:i, CAST(:c AS uuid), :st, :n, :d, :q, :u, :t, true, now())"),
                {"i": str(uuid.uuid4()), "c": r["cid"], "st": r["tipo_servico"] or "maodeobra",
                 "n": i.get("nome") or "—", "d": i.get("descricao") or "",
                 "q": qtd, "u": (total / qtd) if qtd else total, "t": total})
        feitos.append(f"composição gravada ({len(itens)} itens, soma {soma})")

    await db.commit()
    return feitos
