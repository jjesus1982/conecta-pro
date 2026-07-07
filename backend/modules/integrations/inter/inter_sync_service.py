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

        try:
            statement = await adapter.get_statement(start_date, end_date)
        except Exception as exc:
            logger.error("D6.1 falha ao buscar extrato Inter: %s", exc)
            return {"sincronizadas": 0, "duplicadas": 0, "erros": [str(exc)]}
        finally:
            await adapter.close()

        for tx in statement.transactions:
            try:
                # Sinal robusto: a descrição do Inter é a fonte da verdade (o adapter às vezes
                # rotula 'PIX RECEBIDO' como débito). RECEBIDO=entrada(C), ENVIADO/PAGAMENTO=saída(D).
                _du = (tx.description or "").upper()
                if "RECEBID" in _du:
                    tipo_op = "C"
                elif ("ENVIAD" in _du) or ("PAGAMENTO" in _du) or ("DEBITO" in _du) or ("DÉBITO" in _du):
                    tipo_op = "D"
                else:
                    tipo_op = "C" if (tx.transaction_type and "credit" in str(tx.transaction_type).lower()) else "D"
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
                           valor, descricao, raw_payload, detalhes_destinatario)
                        VALUES
                          (:dt, :op, :tipo, :valor, :desc,
                           CAST(:raw AS jsonb), CAST(:dest AS jsonb))
                        ON CONFLICT ON CONSTRAINT uq_inter_transactions_dedup
                        DO UPDATE SET
                          raw_payload = EXCLUDED.raw_payload,
                          detalhes_destinatario = EXCLUDED.detalhes_destinatario
                        WHERE inter_transactions.raw_payload IS NULL
                    """),
                    {
                        "dt": dt,
                        "op": tipo_op,
                        "tipo": tipo_tx,
                        "valor": valor,
                        "desc": desc,
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
        logger.info("D6.1 sync: sincronizadas=%d duplicadas=%d erros=%d ponte=%d conecta=%d receb=%s vtvr=%d",
                    sincronizadas, duplicadas, len(erros), pontefeitas, casados, recebimentos, categorizadas)
        return {"sincronizadas": sincronizadas, "duplicadas": duplicadas, "erros": erros,
                "conciliacao_novas": pontefeitas, "pagamentos_conecta_casados": casados,
                "recebimentos_clientes": recebimentos,
                "vtvr_categorizadas": categorizadas}

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
               reconciliation_status, imported_from, raw_data, created_at, updated_at, ativo)
            SELECT gen_random_uuid(), :acc,
              CASE WHEN it.tipo_transacao='PIX' AND it.tipo_operacao='D' THEN 'pix_enviado'
                   WHEN it.tipo_transacao='PIX' AND it.tipo_operacao='C' THEN 'pix_recebido'
                   WHEN it.tipo_transacao='BOLETO' AND it.tipo_operacao='C' THEN 'boleto_recebido'
                   WHEN it.tipo_transacao='BOLETO' THEN 'boleto_pago'
                   WHEN it.tipo_operacao='C' THEN 'credit' ELSE 'debit' END,
              COALESCE(it.tipo_transacao,'OUTROS'),
              CASE WHEN it.tipo_operacao='C' THEN it.valor ELSE -it.valor END,
              LEFT(COALESCE(it.descricao, it.titulo, 'Transação Inter'), 500),
              it.data_lancamento, 'pendente', 'inter_api_sync', it.raw_payload, now(), now(), true
            FROM inter_transactions it
            WHERE NOT EXISTS (
              SELECT 1 FROM bank_transactions bt
              WHERE bt.bank_account_id = :acc
                AND bt.transaction_date = it.data_lancamento
                AND abs(bt.amount) = it.valor
                AND COALESCE(bt.description,'') = LEFT(COALESCE(it.descricao, it.titulo, ''), 500))
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
