"""Recebível por CONTRATO/competência — registra o que a empresa tem a receber.

Por que existe: `recurring_billing_service.gerar_cobrancas_mensais` acopla duas
coisas — criar o recebível E **emitir a cobrança** no banco (boleto Cora /
PIX cobv Inter). Emitir cobrança é ato EXTERNO, que chega ao condomínio. Registrar
a expectativa de recebimento é interno. Sem essa separação, o contas-a-receber só
existia quando alguém disparava cobrança: 21 registros para 14 contratos ativos e
R$269.700,06/mês. Sem recebível em aberto, aging, inadimplência e régua de cobrança
são maquinário girando no vácuo.

Diferenças deliberadas para o serviço de cobrança:
  • lê **contracts** (instrumento assinado, com o CNPJ credor em `empresa_id`),
    não `clients.mrr` — que diverge em 2 clientes e ignora 2 contratos novos;
  • **um recebível por contrato**, não por cliente: cada contrato pertence a uma
    empresa do grupo e é faturado pelo CNPJ dela;
  • **não chama banco nenhum**. Cobrança é outro ato, com outra decisão.

Paredes: idempotente por (contrato, competência); não emite; não baixa; competência
futura não vira recebível.
"""

from __future__ import annotations

import logging
from datetime import date

import psycopg2

from modules.financial.services.ledger_auto_service import _raw_db_url

logger = logging.getLogger(__name__)


def _conn():
    return psycopg2.connect(_raw_db_url())


def _fim_do_mes(ano: int, mes: int) -> date:
    import calendar
    return date(ano, mes, calendar.monthrange(ano, mes)[1])


def _condominio_padrao(cur) -> str:
    cur.execute(
        "SELECT condominio_id::text FROM receivable_accounts "
        "GROUP BY 1 ORDER BY count(*) DESC LIMIT 1"
    )
    r = cur.fetchone()
    return r[0] if r else "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


def gerar_recebiveis(mes: int, ano: int, preview: bool = True) -> dict:
    """Cria um recebível 'pendente' por contrato ativo na competência.

    NÃO emite cobrança (boleto/PIX) — só registra o que é devido à empresa.
    `preview=True` (padrão) não escreve nada.
    """
    if not 1 <= mes <= 12:
        return {"ok": False, "erro": "mes invalido"}
    hoje = date.today()
    if (ano, mes) > (hoje.year, hoje.month):
        return {"ok": False, "erro": "competencia futura: nao se fatura mes que nao comecou"}

    primeiro = date(ano, mes, 1)
    ultimo = _fim_do_mes(ano, mes)
    ref_month = f"{mes:02d}/{ano}"

    conn = _conn()
    try:
        with conn.cursor() as cur:
            cond_id = _condominio_padrao(cur)
            cur.execute(
                """
                SELECT c.id::text, c.monthly_value, c.client_id::text, c.empresa_id,
                       cl.name, cl.document_number, cl.billing_day, c.contract_number
                FROM contracts c
                LEFT JOIN clients cl ON cl.id = c.client_id
                WHERE c.status = 'active'
                  AND COALESCE(c.monthly_value, 0) > 0
                  AND c.start_date <= %s
                  AND (c.end_date IS NULL OR c.end_date >= %s)
                ORDER BY c.monthly_value DESC
                """,
                (ultimo, primeiro),
            )
            criados, valor_total, existentes = 0, 0.0, 0
            itens = []
            for cid, valor, client_id, empresa_id, nome, doc, billing_day, num in cur.fetchall():
                code = f"REC-{cid[:8]}-{ano}{mes:02d}"
                cur.execute("SELECT 1 FROM receivable_accounts WHERE code = %s LIMIT 1", (code,))
                if cur.fetchone():
                    existentes += 1
                    continue
                dia = min(int(billing_day or 10), 28)
                vencimento = date(ano, mes, dia)
                desc = f"Servicos {ref_month} - {nome or 'cliente'}"
                if num:
                    desc += f" (contrato {num})"
                criados += 1
                valor_total += float(valor)
                itens.append({"cliente": nome, "valor": float(valor),
                              "vencimento": vencimento.isoformat(), "code": code})
                if preview:
                    continue
                cur.execute(
                    """
                    INSERT INTO receivable_accounts (
                        id, condominio_id, code, customer_id, customer_name, customer_document,
                        description, gross_value, net_value,
                        issue_date, due_date, competence_date,
                        reference_month, competencia_mes, competencia_ano,
                        status, is_recurring, recurring_day, origem, empresa_id,
                        metadata, created_at, updated_at
                    ) VALUES (
                        gen_random_uuid(), %s, %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        'pendente', TRUE, %s, 'contrato', %s,
                        %s::jsonb, NOW(), NOW()
                    )
                    """,
                    (cond_id, code, client_id, (nome or "")[:150], (doc or "")[:20],
                     desc[:250], float(valor), float(valor),
                     primeiro, vencimento, primeiro,
                     ref_month, mes, ano,
                     dia, empresa_id,
                     f'{{"contract_id": "{cid}", "origem": "contrato"}}'),
                )
            if preview:
                conn.rollback()
            else:
                conn.commit()
        return {
            "ok": True,
            "modo": "preview" if preview else "aplicado",
            "competencia": ref_month,
            "criados": criados,
            "ja_existiam": existentes,
            "valor_total": round(valor_total, 2),
            "itens": itens,
            "aviso": "Recebivel registrado NAO emite cobranca ao cliente (boleto/PIX e ato separado).",
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
