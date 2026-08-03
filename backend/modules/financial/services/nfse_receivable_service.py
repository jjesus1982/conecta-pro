"""Ponte NFS-e emitida → conta a receber.

As duas pontas existiam e a ponte não: 97 NFS-e emitidas (R$ 1,99 M) contra 21 contas a
receber, todas já pagas. Sem título, não há aging, inadimplência nem DSO — os números
saem de uma base que não existe.

Não reescreve regra de conta a receber: monta a linha e insere. A BAIXA continua sendo da
conciliação por líquido (`conciliacao_liquido_service`), que já casa NFS-e × extrato.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Mesma sentinela que as 21 contas já existentes usam (condominio_id é NOT NULL e a
# NFS-e não carrega condomínio — o vínculo real é o cliente).
CONDOMINIO_SENTINELA = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


def _so_digitos(valor: str | None) -> str:
    return re.sub(r"\D", "", valor or "")


def _vencimento_de(competencia: str | None, dia: int) -> date | None:
    """'MM/AAAA' ou 'AAAA-MM' → dia `dia` do mês SEGUINTE.

    Regra do Jordan: nota emitida em julho é paga em agosto.
    """
    txt = (competencia or "").strip()
    m = re.match(r"^(\d{1,2})/(\d{4})$", txt)
    if m:
        mes, ano = int(m.group(1)), int(m.group(2))
    else:
        m = re.match(r"^(\d{4})-(\d{1,2})", txt)
        if not m:
            return None
        ano, mes = int(m.group(1)), int(m.group(2))
    if not 1 <= mes <= 12:
        return None
    mes2, ano2 = (mes + 1, ano) if mes < 12 else (1, ano + 1)
    return date(ano2, mes2, dia)


async def gerar_contas_de_nfse(
    db: AsyncSession,
    competencia: str | None = None,
    dia_vencimento: int = 10,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Gera uma conta a receber por NFS-e emitida não cancelada.

    Idempotente: `document_number = chave_acesso`; nota já convertida é pulada.
    `dry_run=True` (padrão) apenas relata — não escreve nada.
    """
    filtro = "AND n.competencia = :comp " if competencia else ""
    params: dict[str, Any] = {"comp": competencia} if competencia else {}

    linhas = (await db.execute(text(
        "SELECT n.chave_acesso, n.numero, n.competencia, n.data_emissao, n.tomador_nome, "
        "       n.tomador_cnpj, n.valor_servicos, n.valor_liquido, CAST(n.empresa_id AS TEXT), "
        "       CAST(c.id AS TEXT) AS client_id, "
        "       EXISTS (SELECT 1 FROM receivable_accounts r "
        "               WHERE r.document_number = n.chave_acesso) AS ja_existe "
        "FROM nfse_emitidas_nacional n "
        "LEFT JOIN clients c "
        "  ON regexp_replace(coalesce(c.document_number,''), '[^0-9]', '', 'g') "
        "   = regexp_replace(coalesce(n.tomador_cnpj,''), '[^0-9]', '', 'g') "
        "WHERE coalesce(n.cancelada, false) = false " + filtro
        + "ORDER BY n.data_emissao"), params)).fetchall()

    canceladas = (await db.execute(text(
        "SELECT count(*) FROM nfse_emitidas_nacional n "
        "WHERE coalesce(n.cancelada, false) = true " + filtro), params)).scalar() or 0

    criadas = ja_existiam = sem_cliente = sem_vencimento = 0
    total = 0.0
    itens: list[dict[str, Any]] = []

    for (chave, numero, comp, emissao, tomador, cnpj, bruto, liquido,
         empresa_id, client_id, ja_existe) in linhas:
        if ja_existe:
            ja_existiam += 1
            continue
        venc = _vencimento_de(comp, dia_vencimento)
        if venc is None and emissao:
            venc = emissao + timedelta(days=30)  # sem competência utilizável
        if venc is None or emissao is None:
            sem_vencimento += 1
            continue
        if not client_id:
            sem_cliente += 1

        bruto_f = float(bruto or 0)
        liquido_f = float(liquido or bruto or 0)
        desconto = round(max(bruto_f - liquido_f, 0.0), 2)
        total += liquido_f
        itens.append({
            "chave": chave, "numero": numero, "competencia": comp, "cliente": tomador,
            "tem_cliente": bool(client_id), "bruto": bruto_f, "liquido": liquido_f,
            "vencimento": venc.isoformat(),
        })
        if dry_run:
            continue

        await db.execute(text(
            "INSERT INTO receivable_accounts "
            "  (id, condominio_id, customer_id, customer_name, customer_document, description, "
            "   document_number, gross_value, discount_value, addition_value, net_value, "
            "   remaining_value, paid_value, issue_date, due_date, competence_date, status, "
            "   total_installments, current_installment, origem, empresa_id, ativo, "
            "   created_at, updated_at) "
            "VALUES (gen_random_uuid(), CAST(:cond AS uuid), CAST(:cli AS uuid), :cli_nome, :cli_doc, "
            "        :desc, :doc, :bruto, :desc_v, 0, :liq, :liq, 0, :emissao, :venc, :comp_d, "
            "        'pendente', 1, 1, 'nfse', CAST(:emp AS uuid), true, now(), now())"),
            {
                "cond": CONDOMINIO_SENTINELA, "cli": client_id, "cli_nome": tomador,
                "cli_doc": _so_digitos(cnpj) or None,
                "desc": f"NFS-e {numero or (chave or '')[:8]} — {comp or '—'}",
                "doc": chave, "bruto": bruto_f, "desc_v": desconto, "liq": liquido_f,
                "emissao": emissao, "venc": venc, "comp_d": venc.replace(day=1),
                "emp": empresa_id,
            })
        criadas += 1

    if not dry_run and criadas:
        await db.commit()

    return {
        "analisadas": len(linhas), "criadas": criadas, "ja_existiam": ja_existiam,
        "sem_cliente": sem_cliente, "sem_vencimento": sem_vencimento,
        "canceladas_ignoradas": int(canceladas), "total_valor": round(total, 2),
        "dry_run": dry_run, "itens": itens,
    }
