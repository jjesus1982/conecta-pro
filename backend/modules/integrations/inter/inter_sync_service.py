"""D6.1 — InterSyncService: sincroniza extrato em inter_transactions."""

import json
import logging
import os
from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _build_adapter():
    from modules.integrations.banking.adapters.base import BankCredentials
    from modules.integrations.banking.adapters.inter import InterAdapter

    return InterAdapter(
        BankCredentials(
            client_id=os.getenv("INTER_CLIENT_ID", ""),
            client_secret=os.getenv("INTER_CLIENT_SECRET", ""),
            certificate_path=os.getenv("INTER_CERT_PATH", "/app/credentials/inter/Inter_API_Certificado.crt"),
            private_key_path=os.getenv("INTER_KEY_PATH", "/app/credentials/inter/Inter_API_Chave.key"),
            agency=os.getenv("INTER_AGENCY"),
            account=os.getenv("INTER_ACCOUNT"),
            environment=os.getenv("INTER_ENVIRONMENT", "production"),
        )
    )


class InterSyncService:
    """Sincroniza extrato Inter → inter_transactions (dedup por UNIQUE constraint)."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def sincronizar_extrato(self, dias: int = 7) -> dict[str, Any]:
        """Puxa extrato dos últimos N dias e persiste em inter_transactions.

        Returns:
            {sincronizadas, duplicadas, erros}
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=dias)

        adapter = _build_adapter()
        sincronizadas = 0
        duplicadas = 0
        erros: list[str] = []

        saldo_live = None
        try:
            statement = await adapter.get_statement(start_date, end_date)
            try:
                saldo_live = await adapter.get_balance()  # saldo LIVE p/ atualizar o cache
            except Exception as _e:  # noqa: BLE001
                logger.warning("D6.1 saldo live indisponível: %s", _e)
        except Exception as exc:
            logger.error("D6.1 falha ao buscar extrato Inter: %s", exc)
            return {"sincronizadas": 0, "duplicadas": 0, "erros": [str(exc)]}
        finally:
            await adapter.close()

        for tx in statement.transactions:
            try:
                # A DIREÇÃO vem do sinal que o adapter já derivou de `tipoOperacao`, o campo
                # de direção do próprio Inter. Aqui havia uma heurística que re-adivinhava
                # pela descrição, escrita quando o adapter ainda errava; o adapter foi
                # corrigido e a heurística virou a fonte do erro:
                #   "RECEBID" in "RECEBIMENTO TITULO" é FALSO (falta o D) → caía no
                #   fallback e virava saída. Os 21 recebimentos de boleto do ano estavam
                #   com o sinal invertido, R$35.055,93 numa única linha.
                # Adivinhar por texto o que o banco já informa é sempre o lado errado.
                tipo_op = "D" if float(tx.amount or 0) < 0 else "C"
                tipo_tx = str(tx.transaction_type.value) if tx.transaction_type else None
                valor = abs(float(tx.amount)) if tx.amount else 0
                desc = (tx.description or "")[:255]
                dt = tx.date.date() if hasattr(tx.date, "date") else tx.date

                raw_dict = {
                    "transaction_id": tx.transaction_id,
                    "date": str(dt),
                    "amount": float(tx.amount) if tx.amount else None,
                    "transaction_type": tipo_tx,
                    "description": tx.description,
                    "balance_after": float(tx.balance_after) if tx.balance_after else None,
                    "counterpart_name": tx.counterpart_name,
                    "counterpart_document": tx.counterpart_document,
                    "counterpart_bank": tx.counterpart_bank,
                    "counterpart_agency": tx.counterpart_agency,
                    "counterpart_account": tx.counterpart_account,
                    "category": tx.category,
                    "reference": tx.reference,
                }
                detalhes_dict = None
                if tx.counterpart_document or tx.counterpart_name:
                    detalhes_dict = {
                        "cpf_cnpj": tx.counterpart_document,
                        "nome": tx.counterpart_name,
                        "banco": tx.counterpart_bank,
                        "agencia": tx.counterpart_agency,
                        "conta": tx.counterpart_account,
                    }

                await self.db.execute(
                    text("""
                        INSERT INTO inter_transactions
                          (data_lancamento, tipo_operacao, tipo_transacao,
                           valor, descricao, raw_payload, detalhes_destinatario,
                           -- ⭐ IDENTIDADE VINDA DO BANCO. A chave antiga era
                           -- (data, tipo, valor, DESCRIÇÃO), e o Inter muda o texto entre
                           -- importações ("PAGAMENTO DE TITULO - BANCO TOYOTA…" virou
                           -- "BANCO TOYOTA DO BRASIL SA"): a mesma transação entrava duas
                           -- vezes e o saldo divergia R$1.999,34 do banco.
                           id_transacao)
                        -- SELECT ... WHERE em vez de VALUES: o Postgres só aceita UM
                        -- alvo de ON CONFLICT, e aqui há DUAS chaves únicas (a antiga por
                        -- descrição e a nova por id). Quando a transação já existe com o
                        -- mesmo id, o INSERT tentava mesmo assim e batia no índice novo —
                        -- erro que ABORTA a transação inteira e derruba as linhas
                        -- seguintes ("current transaction is aborted"). Perguntar antes
                        -- custa uma linha e evita o erro em vez de tratá-lo.
                        -- CAST explícito: o mesmo `:idtx` aparece como VALOR de coluna,
                        -- como operando de IS NULL e dentro de uma subconsulta. Sem dizer
                        -- o tipo, o asyncpg desiste ("inconsistent types deduced for
                        -- parameter") e o erro aborta a transação inteira — a mesma
                        -- armadilha que já custou o webhook da Asaas.
                        SELECT :dt, :op, :tipo, :valor, :desc,
                               CAST(:raw AS jsonb), CAST(:dest AS jsonb),
                               CAST(:idtx AS varchar)
                         WHERE CAST(:idtx AS varchar) IS NULL
                            OR NOT EXISTS (SELECT 1 FROM inter_transactions x
                                            WHERE x.id_transacao = CAST(:idtx AS varchar))
                        -- Duas chaves convivendo: `id_transacao` quando o banco manda id,
                        -- a antiga para quem ainda não tem. Enquanto o backfill não
                        -- termina, nenhuma linha fica sem alguma proteção.
                        -- 06/09/2026: a constraint `uq_inter_transactions_dedup` NÃO EXISTE
                        -- mais no banco (a migration 774dcd61a5fe trocou a chave pelo id do
                        -- Inter, índice único parcial `uq_inter_tx_id_transacao`). Citar o
                        -- nome antigo fazia TODO INSERT falhar com UndefinedObjectError —
                        -- engolido pela task, "succeeded" com 0 sincronizadas — e o extrato
                        -- parou em 23/08. Medido: R$ 5.260,83 de divergência = exatamente
                        -- a soma do extrato vivo entre 24/08 e 04/09. O alvo agora é o
                        -- índice que existe; linha sem id (as 572 herdadas) não conflita.
                        ON CONFLICT (id_transacao) WHERE id_transacao IS NOT NULL
                        DO UPDATE SET
                          raw_payload = EXCLUDED.raw_payload,
                          detalhes_destinatario = EXCLUDED.detalhes_destinatario,
                          -- a linha antiga ganha o id quando ele finalmente chega
                          id_transacao = COALESCE(inter_transactions.id_transacao,
                                                  EXCLUDED.id_transacao)
                        WHERE inter_transactions.raw_payload IS NULL
                           OR inter_transactions.id_transacao IS NULL
                    """),
                    {
                        "dt": dt,
                        "op": tipo_op,
                        "tipo": tipo_tx,
                        "valor": valor,
                        "desc": desc,
                        # `transaction_id` vem vazio no /extrato simples e preenchido no
                        # /extrato/completo. NULL em vez de "" de propósito: string vazia
                        # colidiria com ela mesma no índice único e barraria a 2ª linha.
                        "idtx": (tx.transaction_id or None),
                        "raw": json.dumps(raw_dict),
                        "dest": json.dumps(detalhes_dict) if detalhes_dict else None,
                    },
                )
                sincronizadas += 1
            except Exception as exc:
                logger.warning("D6.1 erro ao inserir tx: %s", exc)
                erros.append(str(exc))
                duplicadas += 1

        await self.db.commit()
        pontefeitas = await self.bridge_para_bank_transactions()
        casados = await self.casar_pagamentos_conecta()
        recebimentos = await self.casar_recebimentos_clientes()
        categorizadas = await self.auto_categorizar_vtvr()
        await self.tag_fornecedores()
        saldo_atualizado = await self.atualizar_saldo_inter(saldo_live)
        cashflow_novas = await self.sincronizar_cashflow_do_extrato()
        logger.info("D6.1 sync: sincronizadas=%d duplicadas=%d erros=%d ponte=%d conecta=%d receb=%s vtvr=%d saldo=%s cashflow=%d",
                    sincronizadas, duplicadas, len(erros), pontefeitas, casados, recebimentos, categorizadas,
                    saldo_atualizado, cashflow_novas)
        return {"sincronizadas": sincronizadas, "duplicadas": duplicadas, "erros": erros,
                "conciliacao_novas": pontefeitas, "pagamentos_conecta_casados": casados,
                "recebimentos_clientes": recebimentos,
                "vtvr_categorizadas": categorizadas,
                "saldo_atualizado": saldo_atualizado, "cashflow_novas": cashflow_novas}

    async def atualizar_saldo_inter(self, saldo) -> bool:
        """Atualiza o saldo ARMAZENADO (bank_accounts) com o saldo LIVE do Inter.

        As telas de Fluxo de Caixa/Conciliação/Agentes leem esse cache; sem atualizar, ficam
        com valor velho (divergindo da tela ao vivo). Não move dinheiro."""
        if saldo is None:
            return False
        try:
            total = float(getattr(saldo, "total", None) or getattr(saldo, "available", 0) or 0)
            avail = float(getattr(saldo, "available", None) or total)
            blocked = float(getattr(saldo, "blocked", 0) or 0)
            await self.db.execute(text("""
                UPDATE bank_accounts SET
                    current_balance = :bal, available_balance = :avail, blocked_balance = :blk,
                    last_balance_update = now(), updated_at = now()
                WHERE bank_name ILIKE '%inter%'
            """), {"bal": total, "avail": avail, "blk": blocked})
            await self.db.commit()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("D6.1 atualizar saldo falhou: %s", exc)
            await self.db.rollback()
            return False

    async def sincronizar_cashflow_do_extrato(self) -> int:
        """Popula cashflow_entries com os movimentos REALIZADOS do extrato Inter ainda não refletidos.

        O Fluxo de Caixa lê cashflow_entries; os dados paravam em 13/04 (a origem antiga não seguiu).
        Aqui espelhamos as inter_transactions (C=entrada, D=saída) como lançamentos realizados, com
        dedup por metadata.inter_tx_id e cutoff ancorado no fim dos dados pré-existentes. Não move dinheiro."""
        try:
            acc = (await self.db.execute(
                text("SELECT id FROM bank_accounts WHERE bank_name ILIKE '%inter%' LIMIT 1"))).scalar()
            r = await self.db.execute(text("""
                INSERT INTO cashflow_entries
                  (id, condominio_id, bank_account_id, entry_type, source_type, description, category,
                   entry_date, expected_amount, realized_date, realized_amount, status, ativo, is_recurring,
                   notes, metadata, created_at, updated_at)
                SELECT gen_random_uuid(), :cid, :acc,
                  (CASE WHEN it.tipo_operacao = 'C' THEN 'entrada' ELSE 'saida' END)::cashflowentrytype,
                  'manual'::cashflowsourcetype,
                  COALESCE(NULLIF(it.descricao, ''), 'Movimento Inter'),
                  COALESCE(NULLIF(it.tipo_transacao, ''), 'Outros'),
                  it.data_lancamento, it.valor, it.data_lancamento, it.valor,
                  'realizado'::cashflowentrystatus, true, false, 'Extrato Banco Inter',
                  jsonb_build_object('inter_tx_id', it.id::text, 'origem', 'inter_extrato'),
                  now(), now()
                FROM inter_transactions it
                WHERE it.data_lancamento > COALESCE(
                        (SELECT max(entry_date) FROM cashflow_entries WHERE metadata->>'inter_tx_id' IS NULL),
                        DATE '2026-04-13')
                  AND NOT EXISTS (
                        SELECT 1 FROM cashflow_entries ce WHERE ce.metadata->>'inter_tx_id' = it.id::text)
            """), {"cid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "acc": str(acc) if acc else None})
            await self.db.commit()
            return r.rowcount or 0
        except Exception as exc:  # noqa: BLE001
            logger.warning("D6.1 sincronizar cashflow falhou: %s", exc)
            await self.db.rollback()
            return 0

    async def casar_recebimentos_clientes(self) -> dict:
        """CONCILIAÇÃO INBOUND: categoriza os RECEBIMENTOS (entradas) pendentes como 'Recebimento de
        cliente', identificando o cliente pela descrição (PIX: nome após 'Cp :NNNN-'; boleto: número),
        e casa 1:1 com um recebível (receivable_accounts) por valor+data quando possível, marcando-o
        pago. Isso limpa o maior bolsão pendente da conciliação. Não move dinheiro."""
        from sqlalchemy import text as _text

        # (1) PIX recebido — extrai o nome do cliente da descrição
        r_pix = await self.db.execute(_text("""
            UPDATE bank_transactions SET
              reconciliation_status='justificado', category='Recebimento de cliente',
              counterparty_name = NULLIF(trim(regexp_replace(description, '^.*Cp :[0-9]+-', '')), ''),
              justificativa = 'Recebimento de cliente: ' || trim(regexp_replace(description, '^.*Cp :[0-9]+-', '')),
              justificativa_categoria='recebimento_cliente',
              justificativa_responsavel='sistema (conciliação de recebimentos)',
              justificativa_data=now(), updated_at=now()
            WHERE amount > 0 AND reconciliation_status='pendente'
              AND (transaction_type='pix_recebido' OR upper(description) LIKE '%PIX RECEBIDO%')
        """))

        # (2) Boleto recebido — recebimento de cliente via boleto (número no texto)
        r_bol = await self.db.execute(_text("""
            UPDATE bank_transactions SET
              reconciliation_status='justificado', category='Recebimento de cliente',
              justificativa = 'Recebimento via boleto ' || COALESCE(substring(description from '[0-9]{3}/[0-9]+'), ''),
              justificativa_categoria='recebimento_cliente',
              justificativa_responsavel='sistema (conciliação de recebimentos)',
              justificativa_data=now(), updated_at=now()
            WHERE amount > 0 AND reconciliation_status='pendente'
              AND (transaction_type='boleto_recebido' OR upper(description) LIKE '%BOLETO DE COBRANCA RECEBIDO%')
        """))
        await self.db.commit()

        # (3) Casar com recebíveis (receivable_accounts) por valor ~ + data, 1:1, conservador.
        #     Só casa quando há EXATAMENTE 1 recebível pendente compatível (evita erro).
        casados_recebiveis = 0
        try:
            creditos = (await self.db.execute(_text("""
                SELECT id, amount, transaction_date FROM bank_transactions
                WHERE amount > 0 AND justificativa_categoria='recebimento_cliente'
                ORDER BY transaction_date DESC LIMIT 500
            """))).mappings().all()
            tomados: set[str] = set()
            for c in creditos:
                val = float(c["amount"])
                cands = (await self.db.execute(_text("""
                    SELECT id FROM receivable_accounts
                    WHERE lower(status::text) IN ('pendente','pending','parcial','partial','em_aberto','open')
                      AND abs(COALESCE(net_value, gross_value, 0) - :v) < 0.02
                      AND due_date BETWEEN :d0 AND :d1
                    ORDER BY abs(due_date - :base) LIMIT 2
                """), {"v": val, "base": c["transaction_date"],
                       "d0": c["transaction_date"] - timedelta(days=40),
                       "d1": c["transaction_date"] + timedelta(days=15)})).mappings().all()
                livres = [x for x in cands if str(x["id"]) not in tomados]
                if len(livres) == 1:
                    rid = str(livres[0]["id"])
                    tomados.add(rid)
                    await self.db.execute(_text(
                        "UPDATE receivable_accounts SET status='pago', paid_value=COALESCE(net_value,gross_value), "
                        "remaining_value=0, updated_at=now() WHERE id=:id"), {"id": rid})
                    casados_recebiveis += 1
            await self.db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("casar recebíveis: %s", exc)
            await self.db.rollback()

        res = {"pix_recebido": r_pix.rowcount or 0, "boleto_recebido": r_bol.rowcount or 0,
               "recebiveis_casados": casados_recebiveis}
        if any(res.values()):
            logger.info("conciliação recebimentos: %s", res)
        return res

    # categoria do pagamento (inter_payments) → (category exibida, justificativa_categoria)
    _CATEGORIA_CONCILIACAO = {
        "pro_labore":    ("Pró-labore", "pro_labore"),
        "transferencia": ("Transferência entre contas", "transferencia"),
        "fornecedor":    ("Fornecedor", "fornecedor"),
        "imposto":       ("Impostos", "imposto"),
        "diarista":      ("Diaristas VT+VR", "diaristas_vtvr"),
        "folha":         ("Folha de pagamento", "folha"),
        "aluguel":       ("Aluguel", "aluguel"),
        "reembolso":     ("Reembolso", "reembolso"),
        "outro":         ("Outros", "outro"),
    }

    async def casar_pagamentos_conecta(self) -> int:
        """FECHA O LOOP: casa cada pagamento EXECUTADO pelo Conecta PRO (que já carrega a
        `categoria` escolhida pelo Jordan no ato do pagamento) com a saída correspondente do
        extrato, carimbando a conciliação como 'justificado' com aquela categoria.

        É a fonte MAIS confiável de categorização (o humano justificou a saída na hora de pagar),
        por isso roda antes das regras automáticas (VT+VR, fornecedores). Casamento 1:1 e
        reversível (grava inter_payments.reconciled_bank_tx_id). Não move dinheiro."""
        from datetime import timedelta as _td

        from sqlalchemy import text as _text

        # pagamentos executados/confirmados ainda não conciliados
        pend = (await self.db.execute(_text("""
            SELECT id, valor, data_pagamento, executed_at, categoria, observacoes
            FROM inter_payments
            WHERE status IN ('executado','confirmado') AND reconciled_bank_tx_id IS NULL
            ORDER BY COALESCE(executed_at, data_pagamento::timestamptz)
        """))).mappings().all()
        if not pend:
            return 0

        casados = 0
        tomados: set[str] = set()
        for p in pend:
            valor = float(p["valor"])
            base_dt = p["data_pagamento"]
            # candidatas: saídas pendentes com valor exato, na janela [-1, +3] dias, ainda livres
            cands = (await self.db.execute(_text("""
                SELECT id, transaction_date
                FROM bank_transactions
                WHERE reconciliation_status='pendente'
                  AND amount < 0 AND abs(amount + :val) < 0.005
                  AND transaction_date BETWEEN :d0 AND :d1
                ORDER BY abs((transaction_date - :base))
            """), {"val": round(valor, 2), "base": base_dt,
                   "d0": base_dt - _td(days=1), "d1": base_dt + _td(days=3)})).mappings().all()
            escolhido = next((c for c in cands if str(c["id"]) not in tomados), None)
            if not escolhido:
                continue
            tx_id = str(escolhido["id"])
            tomados.add(tx_id)
            cat = (p["categoria"] or "outro")
            label, jcat = self._CATEGORIA_CONCILIACAO.get(cat, ("Outros", "outro"))
            just = f"Pago pelo Conecta PRO (categoria: {label})"
            if p["observacoes"]:
                just += f" — {p['observacoes']}"
            await self.db.execute(_text("""
                UPDATE bank_transactions SET
                  reconciliation_status='justificado', category=:label,
                  justificativa=:just, justificativa_categoria=:jcat,
                  justificativa_responsavel='Conecta PRO (pagamento categorizado)',
                  justificativa_data=now(), updated_at=now()
                WHERE id=:txid
            """), {"label": label, "just": just, "jcat": jcat, "txid": tx_id})
            await self.db.execute(_text(
                "UPDATE inter_payments SET reconciled_bank_tx_id=:txid WHERE id=:pid"),
                {"txid": tx_id, "pid": str(p["id"])})
            casados += 1

        await self.db.commit()
        if casados:
            logger.info("casar pagamentos Conecta: %d saídas conciliadas com a categoria do pagamento", casados)
        return casados

    _FORNECEDORES_SEED = [
        ("PPA Amazonas", "PPA"), ("Wide", "WIDE"), ("Eletrônica Melo", "ELETRONICA MELO"),
        ("WMG", "WMG"), ("OCSEG", "OCSEG"), ("Hawkeye", "HAWKEYE"), ("Futura", "FUTURA"),
        ("Amazonas Energia", "AMAZONAS ENERGIA"), ("Ambar Energia", "AMBAR"),
        ("Águas de Manaus", "AGUAS DE MANAUS"), ("Águas do Amazonas", "AGUAS DO AMAZONAS"),
        ("Sólides", "SOLIDES"),
    ]

    async def tag_fornecedores(self) -> int:
        """Identifica e AGRUPA fornecedores nas saídas da conciliação (category='Fornecedor',
        counterparty_name=nome). MANTÉM 'pendente' de propósito: no Lucro Real, a saída só é
        JUSTIFICADA quando casar com a NF-e de entrada (trabalho do Fiscal). Aqui só organiza."""
        from sqlalchemy import text as _text
        await self.db.execute(_text(
            "CREATE TABLE IF NOT EXISTS financial_fornecedores ("
            "id SERIAL PRIMARY KEY, nome TEXT NOT NULL, padrao_match TEXT NOT NULL UNIQUE, "
            "cnpj VARCHAR(18), ativo BOOLEAN DEFAULT TRUE, created_at TIMESTAMPTZ DEFAULT now())"))
        if not (await self.db.execute(_text("SELECT 1 FROM financial_fornecedores LIMIT 1"))).first():
            for nome, pad in self._FORNECEDORES_SEED:
                await self.db.execute(_text(
                    "INSERT INTO financial_fornecedores (nome, padrao_match) VALUES (:n,:p) ON CONFLICT DO NOTHING"),
                    {"n": nome, "p": pad})
            await self.db.commit()
        total = 0
        rows = await self.db.execute(_text("SELECT nome, padrao_match FROM financial_fornecedores WHERE ativo"))
        for nome, pad in rows.all():
            r = await self.db.execute(_text("""
                UPDATE bank_transactions SET category='Fornecedor', counterparty_name=:nome, updated_at=now()
                WHERE reconciliation_status='pendente' AND amount<0
                  AND upper(description) LIKE '%'||upper(:pad)||'%'
                  AND (category IS DISTINCT FROM 'Fornecedor')
            """), {"nome": nome, "pad": pad})
            total += r.rowcount or 0
        await self.db.commit()
        if total:
            logger.info("tag fornecedores: %d saídas marcadas como Fornecedor (aguardando NF-e)", total)
        return total

    async def auto_categorizar_vtvr(self) -> int:
        """Auto-categoriza os PIX de VT+VR de diaristas como 'Diaristas VT+VR' na conciliação.

        (a) R$32 exatos = VT R$10 + VR R$22 (inconfundível — 1 diarista).
        (b) MÚLTIPLOS de R$32 (R$64, R$96…) SÓ quando o MESMO recebedor também recebeu R$32 alguma vez
            (= diarista confirmado — líder com N ajudantes). Assim empresas que por acaso pagam múltiplo
            de 32 (SOLIDES, PPA…) NÃO entram. Não move dinheiro (transação já ocorreu)."""
        from sqlalchemy import text as _text
        # (a) R$32 exatos
        r1 = await self.db.execute(_text("""
            UPDATE bank_transactions SET
              reconciliation_status='justificado', category='Diaristas VT+VR',
              justificativa='VT (R$10) + VR (R$22) — benefício diário pago a diarista/cobertura',
              justificativa_categoria='diaristas_vtvr',
              justificativa_responsavel='sistema (regra automática R$32)',
              justificativa_data=now(), updated_at=now()
            WHERE amount = -32.00 AND reconciliation_status='pendente'
        """))
        # (b) múltiplos de R$32 com recebedor confirmado (também recebeu R$32)
        r2 = await self.db.execute(_text("""
            UPDATE bank_transactions m SET
              reconciliation_status='justificado', category='Diaristas VT+VR',
              justificativa='VT+VR de vários ajudantes (líder recebe o benefício da equipe) — múltiplo de R$32',
              justificativa_categoria='diaristas_vtvr',
              justificativa_responsavel='sistema (regra R$32 x N + recebedor confirmado)',
              justificativa_data=now(), updated_at=now()
            WHERE m.reconciliation_status='pendente' AND m.amount<0 AND mod(m.amount,32)=0 AND m.amount<>-32
              AND length(trim(regexp_replace(m.description,'^.*-','')))>=6
              AND EXISTS (
                SELECT 1 FROM bank_transactions r WHERE r.amount=-32.00
                  AND upper(trim(regexp_replace(r.description,'^.*-',''))) = upper(trim(regexp_replace(m.description,'^.*-','')))
              )
        """))
        await self.db.commit()
        n = (r1.rowcount or 0) + (r2.rowcount or 0)
        if n:
            logger.info("auto-categorização VT+VR: %d (R$32=%d, múltiplos=%d)", n, r1.rowcount or 0, r2.rowcount or 0)
        return n

    async def bridge_para_bank_transactions(self) -> int:
        """PONTE (corrige o furo): leva as inter_transactions ainda ausentes de bank_transactions
        para a tabela de conciliação, como 'pendente'. Dedup por conta+data+valor+descrição.
        NÃO baixa contas — só torna o extrato do Inter VISÍVEL para a conciliação (revisável)."""
        from sqlalchemy import text as _text
        acc = await self.db.execute(_text(
            "SELECT id FROM bank_accounts WHERE bank_name ILIKE '%inter%' OR name ILIKE '%inter%' "
            "ORDER BY created_at LIMIT 1"))
        acc_id = acc.scalar()
        if not acc_id:
            logger.warning("ponte inter→bank: conta Inter não encontrada em bank_accounts")
            return 0
        res = await self.db.execute(_text("""
            INSERT INTO bank_transactions
              (id, bank_account_id, transaction_type, category, amount, description, transaction_date,
               -- `status` explícito: sem ele a coluna caía no DEFAULT 'pendente' e a escrituração
               -- do extrato PULA 'pendente' (regra de 14/08 p/ ordem da Cora não debitada).
               -- Linha de EXTRATO é liquidada por definição: set/2026 do Inter tinha 0 de 58
               -- linhas no razão e ago/2026 165 de 260 (achado 07/09).
               status, reconciliation_status, imported_from, raw_data, created_at, updated_at, ativo,
               -- O adapter já extrai o favorecido do Inter e grava em
               -- `detalhes_destinatario` (2.459 das 2.765 linhas têm nome). A ponte
               -- não copiava: o nome chegava ao banco só dentro do TEXTO da
               -- descrição, e "quanto saiu para o Fulano em agosto?" virava uma
               -- pergunta que não dava para fazer em SQL.
               counterparty_name, counterparty_document,
               -- ⭐ IDENTIFICADOR ESTÁVEL. Sem ele a garantia do banco fica DESLIGADA:
               -- `idx_bank_tx_external_id` é UNIQUE mas parcial (`WHERE external_id IS
               -- NOT NULL`), e em índice único NULO nunca colide com NULO. Resultado
               -- medido em 22/08/2026: 645 das 4.450 linhas do Inter (14,5%) sem id, e
               -- a mesma transação entrando de novo a cada reimportação. O Cora tem 0%.
               -- Foi assim que o saldo do Inter passou a divergir R$1.999,34 do banco.
               -- O id vem da linha de ORIGEM (`inter_transactions.id`): estável entre
               -- rodadas, diferente entre lançamentos gêmeos legítimos — que existem e
               -- não podem ser suprimidos (dois VT de R$32 no mesmo dia à mesma pessoa).
               external_id)
            SELECT gen_random_uuid(), :acc,
              CASE WHEN it.tipo_transacao='PIX' AND it.tipo_operacao='D' THEN 'pix_enviado'
                   WHEN it.tipo_transacao='PIX' AND it.tipo_operacao='C' THEN 'pix_recebido'
                   WHEN it.tipo_transacao='BOLETO' AND it.tipo_operacao='C' THEN 'boleto_recebido'
                   WHEN it.tipo_transacao='BOLETO' THEN 'boleto_pago'
                   WHEN it.tipo_operacao='C' THEN 'credit' ELSE 'debit' END,
              COALESCE(it.tipo_transacao,'OUTROS'),
              CASE WHEN it.tipo_operacao='C' THEN it.valor ELSE -it.valor END,
              LEFT(COALESCE(it.descricao, it.titulo, 'Transação Inter'), 500),
              it.data_lancamento, 'confirmado', 'pendente', 'inter_api_sync', it.raw_payload, now(), now(), true,
              LEFT(NULLIF(it.detalhes_destinatario->>'nome', ''), 255),
              LEFT(NULLIF(it.detalhes_destinatario->>'cpf_cnpj', ''), 40),
              -- ⚠️ O id do BANCO, não um inventado por nós. Escrevi
              -- `'inter_tx_' || it.id` primeiro e criei 187 duplicatas: outro caminho de
              -- importação JÁ gravava o `idTransacao` do Inter aqui (119 linhas de agosto
              -- começando com "MDAxXzAwMD..."), e duas convenções de identidade não se
              -- reconhecem — cada uma duplica a outra. Identidade só serve se for a MESMA
              -- para todo mundo. Fallback para o id da origem só quando o banco não mandou.
              COALESCE(it.id_transacao, 'inter_tx_' || it.id)
            FROM (
              -- ⚠️ DEDUP POR CONTAGEM — e foi ela que falhou em 20/08/2026, de um jeito
              -- que só se vê olhando o caso: a origem tinha 9 lançamentos de R$32,00 no
              -- dia e o extrato já tinha 9, então "nada a inserir". Só que dos nossos 9,
              -- DOIS eram a mesma pessoa duplicada — e faltavam o Alan e o Jair. Contagem
              -- sabe QUANTOS, nunca QUAIS: uma duplicata de um lado MASCARA duas
              -- ausências do outro.
              --
              -- A saída é identidade, não aritmética: quando a linha de origem tem
              -- `id_transacao` (o id do próprio Inter), o filtro abaixo usa ele e a
              -- contagem nem entra. Para as linhas herdadas sem id, a contagem continua
              -- valendo — remover antes do backfill terminar reinseriria o extrato todo.
              -- Dedup por CONTAGEM, não por texto. A condição antiga exigia que a
              -- descrição batesse caractere a caractere; a mesma transação vinda do
              -- CSV ("Pix enviado. Cp 123-Fulano") e da API ("PIX ENVIADO - Cp
              -- 123-Fulano") não casava, e a ponte recriava a linha TODO DIA.
              -- (exemplos sem dois-pontos de propósito: dentro de text() do
              --  SQLAlchemy, dois-pontos seguido de dígitos vira bind parameter
              --  MESMO EM COMENTÁRIO, e a query nem compila)
              -- Aqui cada (data, valor) só entra pelo que FALTA: se o Inter tem 3
              -- saques de R$1.000 no dia e o banco já tem 2, insere 1 — sem
              -- suprimir repetição legítima, sem duplicar por formatação.
              SELECT it.*, row_number() OVER (
                       PARTITION BY it.data_lancamento, it.valor ORDER BY it.id) AS rn
              FROM inter_transactions it
            ) it
            LEFT JOIN (
              SELECT transaction_date AS d, abs(amount) AS v, count(*) AS n
              FROM bank_transactions WHERE bank_account_id = :acc
              GROUP BY 1, 2
            ) ja ON ja.d = it.data_lancamento AND ja.v = it.valor
            WHERE CASE
                    -- com id do banco: pergunta EXATA — esta transação já atravessou?
                    WHEN it.id_transacao IS NOT NULL THEN NOT EXISTS (
                      SELECT 1 FROM bank_transactions b
                       WHERE b.bank_account_id = :acc
                         AND b.external_id = COALESCE(it.id_transacao,
                                                      'inter_tx_' || it.id))
                    -- sem id (herdadas): a aritmética de antes, até o backfill alcançar
                    ELSE it.rn > COALESCE(ja.n, 0)
                  END
            -- Cinto E suspensório: a contagem acima evita reinserir, e o índice único
            -- garante mesmo se a contagem falhar (foi ela que falhou). `DO NOTHING` em
            -- vez de erro porque reimportar é rotina, não incidente. A cláusula WHERE
            -- repete o predicado do índice PARCIAL — sem isso o Postgres não infere qual
            -- índice usar e recusa o comando.
            ON CONFLICT (external_id) WHERE external_id IS NOT NULL DO NOTHING
            """), {"acc": acc_id})
        await self.db.commit()
        n = res.rowcount or 0
        if n:
            logger.info("ponte inter→bank: %d transações do extrato Inter enviadas à conciliação", n)
        return n

    async def listar_transactions(
        self,
        inicio: date | None = None,
        fim: date | None = None,
        tipo_operacao: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Lista inter_transactions com filtros opcionais."""
        where = ["1=1"]
        params: dict[str, Any] = {"limit": limit}

        if inicio:
            where.append("data_lancamento >= :inicio")
            params["inicio"] = inicio
        if fim:
            where.append("data_lancamento <= :fim")
            params["fim"] = fim
        if tipo_operacao:
            where.append("tipo_operacao = :tipo_op")
            params["tipo_op"] = tipo_operacao.upper()

        rows = (
            (
                await self.db.execute(
                    text(f"""
                    SELECT id, data_lancamento, tipo_operacao, tipo_transacao,
                           valor, descricao, created_at
                    FROM inter_transactions
                    WHERE {" AND ".join(where)}
                    ORDER BY data_lancamento DESC
                    LIMIT :limit
                """),
                    params,
                )
            )
            .mappings()
            .all()
        )

        return [dict(r) for r in rows]

    async def resumo(self, dias: int = 30) -> dict:
        """Totais crédito/débito por tipo nos últimos N dias."""
        inicio = date.today() - timedelta(days=dias)
        rows = (
            (
                await self.db.execute(
                    text("""
                    SELECT tipo_operacao, tipo_transacao,
                           COUNT(*) AS qtd, SUM(valor) AS total
                    FROM inter_transactions
                    WHERE data_lancamento >= :inicio
                    GROUP BY tipo_operacao, tipo_transacao
                    ORDER BY tipo_operacao, total DESC
                """),
                    {"inicio": inicio},
                )
            )
            .mappings()
            .all()
        )

        return {
            "periodo_dias": dias,
            "resumo": [dict(r) for r in rows],
        }
