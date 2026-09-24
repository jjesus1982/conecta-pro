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

import json
import logging
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

import psycopg2

from modules.financial.services.ledger_auto_service import _raw_db_url

logger = logging.getLogger(__name__)


def _conn():
    return psycopg2.connect(_raw_db_url())


def _fim_do_mes(ano: int, mes: int) -> date:
    import calendar

    return date(ano, mes, calendar.monthrange(ano, mes)[1])


def _condominio_padrao(cur) -> str:
    cur.execute("SELECT condominio_id::text FROM receivable_accounts GROUP BY 1 ORDER BY count(*) DESC LIMIT 1")
    r = cur.fetchone()
    return r[0] if r else "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


def valor_proporcional(
    valor, inicio: date | None, fim: date | None, primeiro: date, ultimo: date, base_dias
) -> Decimal:
    """Pró-rata por dias do DGX (`NotaServicoContratoValorProporcional` + `Dias`, 24/09/2026 — T4).

    Contrato que começa ou termina dentro da competência paga só os dias cobertos, sobre uma base
    fixa de dias (o DGX usa 30). `base_dias` vazio/0 = regra desligada → valor cheio (é o estado de
    produção hoje; o oráculo `test_oraculo_t4_faturamento_financeiro` prova que nada muda).
    Mês inteiro coberto → valor cheio, mesmo em mês de 31 dias com base 30.
    """
    valor = Decimal(str(valor or 0))
    try:
        base = int(base_dias or 0)
    except (TypeError, ValueError):
        base = 0
    de = max(inicio or primeiro, primeiro)
    ate = min(fim or ultimo, ultimo)
    cobertos = (ate - de).days + 1
    if base <= 0 or cobertos >= (ultimo - primeiro).days + 1:
        return valor
    if cobertos <= 0:
        return Decimal("0.00")
    return (valor * Decimal(min(cobertos, base)) / Decimal(base)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _base_proporcional(cur) -> int | None:
    """Lê `fiscal.nfse_valor_proporcional_dias` (semeado pela F4) — escopo global; vazio = desligado."""
    try:
        cur.execute(
            "SELECT nullif(trim(valor),'') FROM system_configs WHERE chave = 'fiscal.nfse_valor_proporcional_dias' AND ativo"
        )
        r = cur.fetchone()
        return int(r[0]) if r and r[0] else None
    except Exception:  # noqa: BLE001 — tabela/coluna ausente = regra desligada
        return None


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
            base_dias = _base_proporcional(cur)  # dgx t4 — None = valor cheio (comportamento de sempre)
            cur.execute(
                """
                SELECT c.id::text, c.monthly_value, c.client_id::text, c.empresa_id,
                       cl.name, cl.document_number, cl.billing_day, c.contract_number,
                       c.start_date, c.end_date
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
            for cid, valor, client_id, empresa_id, nome, doc, billing_day, num, c_ini, c_fim in cur.fetchall():
                valor = valor_proporcional(valor, c_ini, c_fim, primeiro, ultimo, base_dias)  # dgx t4
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
                itens.append(
                    {"cliente": nome, "valor": float(valor), "vencimento": vencimento.isoformat(), "code": code}
                )
                if preview:
                    continue
                cur.execute(
                    """
                    INSERT INTO receivable_accounts (
                        id, condominio_id, code, customer_name, customer_document,
                        description, gross_value, net_value,
                        issue_date, due_date, competence_date,
                        reference_month, competencia_mes, competencia_ano,
                        status, is_recurring, recurring_day, origem, empresa_id,
                        metadata, created_at, updated_at
                    ) VALUES (
                        gen_random_uuid(), %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        'pendente', TRUE, %s, 'contrato', %s,
                        %s::jsonb, NOW(), NOW()
                    )
                    """,
                    # customer_id fica NULO de propósito: a FK aponta para `customers`,
                    # e o contrato referencia `clients` — entidades distintas. A
                    # identidade do cliente vai em customer_name/document + metadata.
                    (
                        cond_id,
                        code,
                        (nome or "")[:150],
                        (doc or "")[:20],
                        desc[:250],
                        float(valor),
                        float(valor),
                        primeiro,
                        vencimento,
                        primeiro,
                        ref_month,
                        mes,
                        ano,
                        dia,
                        empresa_id,
                        f'{{"contract_id": "{cid}", "client_id": "{client_id}", "origem": "contrato"}}',
                    ),
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


# ─────────────────────────────────────────────────────────────────────────────
# A ponte que faltava: contrato de VALOR ÚNICO → contas a receber
# ─────────────────────────────────────────────────────────────────────────────
#
# Origem: 17/09/2026. `checar_contrato_sem_cobranca` acusou o CTR-2026-00022 (Chácaras
# Maiápolis, R$ 46.320,00 em 4 parcelas) ATIVO desde 09/09 e sem UMA linha no contas a
# receber. Não era dado corrompido — era caminho que nunca existiu:
#
#   recurring   contrato ativo → client_contracts (MRR) → `gerar_recebiveis` acima. Funciona.
#   one_time    contrato ativo → NADA. `_bridge_contract_to_billing` recusa tudo que não é
#               recorrente — e está certo, valor único não é MRR. Só que o outro caminho
#               não foi construído: o cronograma vive em `contract_items` e ninguém o lia.
#
# A trava passava verde porque nenhum contrato de valor único estava ativo. Este é o
# primeiro, e ficou vermelha na hora certa.

#: Quanto vale cada linha do cronograma, e QUANDO vence.
#:   entrada  vence na assinatura (start_date do contrato)
#:   parcela  vence em N dias após a assinatura — o N está em `notes` ("30 dias", "60 dias")
#:   retida   NÃO TEM DATA. É retenção contra o Termo de Entrega, um marco e não um prazo.
_TIPOS_DO_CRONOGRAMA = ("entrada", "parcela", "retida")

#: A retida nasce `suspensa`, não `pendente`. Ela É devida e precisa aparecer no total do
#: contrato, mas dar-lhe uma data inventada a faria vencer sozinha e entrar no aging como
#: inadimplência que não existe — estragando o indicador que justifica o contas a receber.
#: `suspensa` é o estado que o modelo já tem para exatamente isto ("suspensa temporariamente").
_STATUS_RETIDA = "suspensa"


def _dias_de(notes: str | None) -> int | None:
    """Extrai o prazo de `notes` ("30 dias" → 30). Sem número, devolve None e quem chama decide."""
    import re

    m = re.search(r"(\d+)\s*dias?", str(notes or ""), re.I)
    return int(m.group(1)) if m else None


def gerar_recebiveis_valor_unico(preview: bool = True) -> dict:
    """Cria um recebível por PARCELA do cronograma de cada contrato `one_time` ativo.

    Igual ao irmão recorrente nas paredes que importam: idempotente por `code`, **não emite
    cobrança** (boleto/PIX é outro ato, com outra decisão) e `preview=True` não escreve nada.

    Diferença de fundo: o recorrente gera UMA linha por competência, para sempre. Este gera
    N linhas UMA vez — o cronograma inteiro, porque valor único tem fim.
    """
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cond_id = _condominio_padrao(cur)
            cur.execute(
                """
                SELECT c.id::text, c.contract_number, c.client_id::text, c.empresa_id,
                       c.start_date, cl.name, cl.document_number
                  FROM contracts c
                  LEFT JOIN clients cl ON cl.id = c.client_id
                 WHERE c.status = 'active' AND c.contract_type = 'one_time'
                 ORDER BY c.created_at
                """
            )
            contratos = cur.fetchall()
            criados, existentes, valor_total = 0, 0, 0.0
            itens: list[dict] = []
            sem_cronograma: list[str] = []

            for cid, num, client_id, empresa_id, inicio, nome, doc in contratos:
                cur.execute(
                    """
                    SELECT service_type, service_name, total_price, notes
                      FROM contract_items
                     WHERE contract_id = %s AND COALESCE(is_active, TRUE)
                       AND service_type = ANY(%s)
                     ORDER BY created_at, unit_price DESC
                    """,
                    (cid, list(_TIPOS_DO_CRONOGRAMA)),
                )
                linhas = cur.fetchall()
                if not linhas:
                    # Contrato de valor único SEM cronograma não vira recebível chutado: o
                    # valor total existe, mas em quantas vezes e quando é decisão comercial.
                    # Dizer que não deu é melhor que inventar uma parcela única.
                    sem_cronograma.append(num)
                    continue

                base = inicio or date.today()
                total_parcelas = len(linhas)
                for i, (stipo, snome, valor, notes) in enumerate(linhas, start=1):
                    code = f"REC-{cid[:8]}-U{i:02d}"
                    cur.execute("SELECT 1 FROM receivable_accounts WHERE code = %s LIMIT 1", (code,))
                    if cur.fetchone():
                        existentes += 1
                        continue

                    if stipo == "entrada":
                        vencimento, status = base, "pendente"
                    elif stipo == "retida":
                        # Sem data real: fica na data do início só para a coluna NOT NULL, e
                        # `suspensa` a mantém fora do aging até alguém liberar contra o Termo.
                        vencimento, status = base, _STATUS_RETIDA
                    else:
                        dias = _dias_de(notes)
                        if dias is None:
                            # Parcela sem prazo escrito é cronograma incompleto, não "vence
                            # hoje". Suspensa também: aparece no total, não cobra sozinha.
                            vencimento, status = base, _STATUS_RETIDA
                        else:
                            vencimento = base + timedelta(days=dias)
                            status = "pendente"

                    desc = f"{snome or stipo} - {nome or 'cliente'} (contrato {num})"
                    criados += 1
                    valor_total += float(valor or 0)
                    itens.append(
                        {
                            "contrato": num,
                            "parcela": snome or stipo,
                            "valor": float(valor or 0),
                            "vencimento": vencimento.isoformat(),
                            "status": status,
                            "code": code,
                        }
                    )
                    if preview:
                        continue
                    cur.execute(
                        """
                        INSERT INTO receivable_accounts (
                            id, condominio_id, code, customer_name, customer_document,
                            description, gross_value, net_value,
                            issue_date, due_date, competence_date,
                            total_installments, current_installment,
                            status, is_recurring, origem, empresa_id,
                            metadata, created_at, updated_at
                        ) VALUES (
                            gen_random_uuid(), %s, %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s,
                            %s, %s,
                            %s, FALSE, 'contrato', %s,
                            %s::jsonb, NOW(), NOW()
                        )
                        """,
                        # customer_id NULO pelo mesmo motivo do irmão recorrente: a FK aponta
                        # para `customers` e o contrato referencia `clients`.
                        (
                            cond_id,
                            code,
                            (nome or "")[:150],
                            (doc or "")[:20],
                            desc[:250],
                            float(valor or 0),
                            float(valor or 0),
                            base,
                            vencimento,
                            base,
                            total_parcelas,
                            i,
                            status,
                            empresa_id,
                            json.dumps(
                                {
                                    "contract_id": cid,
                                    "client_id": client_id,
                                    "origem": "contrato",
                                    "tipo": stipo,
                                    "valor_unico": True,
                                }
                            ),
                        ),
                    )
            if preview:
                conn.rollback()
            else:
                conn.commit()
        return {
            "ok": True,
            "modo": "preview" if preview else "aplicado",
            "contratos_avaliados": len(contratos),
            "criados": criados,
            "ja_existiam": existentes,
            "sem_cronograma": sem_cronograma,
            "valor_total": round(valor_total, 2),
            "itens": itens,
            "aviso": "Recebivel registrado NAO emite cobranca ao cliente (boleto/PIX e ato separado). "
            "Parcela retida nasce 'suspensa': aparece no total e fica fora do aging ate "
            "o Termo de Entrega.",
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
