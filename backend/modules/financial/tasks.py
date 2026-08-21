"""Celery Tasks - Módulo Financeiro.

Sync automático: bank_transactions → cashflow_entries
Executado a cada hora via Celery Beat.
"""

import logging

from celery_app import app

logger = logging.getLogger(__name__)


@app.task(
    name="financial.sincronizar_nfse_nacional",
    bind=True,
    max_retries=2,
    default_retry_delay=600,
)
def sincronizar_nfse_nacional_task(self):
    """Puxa NFS-e emitidas (receita) + tomadas (custo) do ADN nacional (gov.br) e fecha o razão.
    Diário: junho e meses futuros completam sozinhos quando o Ambiente Nacional recebe as notas.
    """
    try:
        from modules.financial.services.ledger_auto_service import LedgerAutoService
        from modules.financial.services.nfse_nacional_sync_service import NFSeNacionalSyncService

        svc = NFSeNacionalSyncService()
        # Multi-CNPJ E5: sync das emitidas em LOOP pelas empresas ativas com
        # certificado (cada CNPJ tem feed/NSU próprios no ADN). A falha de uma
        # empresa NÃO derruba o sync da outra.
        emit = svc.sincronizar()  # CNPJ1 (legado/env)
        try:
            emit_pat = svc.sincronizar(empresa_slug="conecta_patrimonial")
            logger.info(
                "NFS-e nacional sync PATRIMONIAL: %s notas vivas, ultimo_nsu=%s",
                emit_pat.get("validas_cStat100"), emit_pat.get("ultimo_nsu"),
            )
        except Exception as pat_exc:  # noqa: BLE001
            logger.warning("Sync NFS-e Patrimonial falhou (CNPJ1 segue normal): %s", pat_exc)
        # Tomadas (serviços recebidos) das DUAS empresas — cada uma com o próprio cert/CNPJ.
        tom = svc.sincronizar_tomadas(empresa_slug="conecta_eletronica")
        try:
            tom_pat = svc.sincronizar_tomadas(empresa_slug="conecta_patrimonial")
            logger.info("NFS-e tomadas PATRIMONIAL: %s recebidas", tom_pat.get("recebidas"))
        except Exception as tpe:  # noqa: BLE001
            logger.warning("Sync tomadas Patrimonial falhou (Eletrônica segue): %s", tpe)
        # Cadastra/atualiza os fornecedores REAIS a partir das notas + categoriza (best-effort).
        try:
            import asyncio as _asyncio

            from core.database import async_session_factory
            from modules.financial.services.fornecedor_categoria_service import sincronizar_fornecedores

            async def _forn():
                async with async_session_factory() as _db:
                    return await sincronizar_fornecedores(_db)
            _fr = _asyncio.run(_forn())
            logger.info("Fornecedores sync: %s", _fr)
        except Exception as fe2:  # noqa: BLE001
            logger.warning("Sync fornecedores falhou (segue): %s", fe2)
        fechar = LedgerAutoService().fechar_grupo()
        # Fecha o fluxo de caixa: corrige sinal dos recebidos + justifica cada saída
        try:
            from modules.financial.services.fluxo_caixa_service import FluxoCaixaService
            fc = FluxoCaixaService().recategorizar_saidas()
        except Exception as fce:
            logger.warning("recategorizacao fluxo caixa falhou (segue): %s", fce)
            fc = {"erro": str(fce)}
        logger.info("NFS-e nacional sync: emitidas=%s tomadas=%s fluxo=%s",
                    emit.get("validas_cStat100"), tom.get("recebidas"), fc.get("reclassificadas"))
        return {"emitidas": emit.get("por_competencia"), "tomadas": tom.get("por_competencia_2026"),
                "razao": {slug: r.get("novos_lancamentos") for slug, r in fechar.get("empresas", {}).items()},
                "fluxo_caixa": fc.get("por_categoria")}
    except Exception as exc:
        logger.error("Erro no sync NFS-e nacional: %s", exc)
        raise self.retry(exc=exc)


@app.task(
    name="financial.fechar_razao_auto",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
)
def fechar_razao_auto_task(self):
    """Contabilidade que fecha sozinha: posta folha (hr_payslips) + ISS (nfses) no razão
    accounting_entries, idempotente, com empresa_id. Alimenta balancete + DRE.
    Executado diariamente via Celery Beat.
    """
    try:
        from modules.financial.services.ledger_auto_service import LedgerAutoService

        result = LedgerAutoService().fechar_grupo()
        logger.info("Fechamento automático do razão: %s", result)
        return result
    except Exception as exc:
        logger.error("Erro no fechamento do razão: %s", exc)
        raise self.retry(exc=exc)


@app.task(
    name="financial.sync_cashflow_entries",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
)
def sync_cashflow_entries_task(self):
    """Sincroniza bank_transactions pendentes → cashflow_entries.

    Executado a cada hora via Celery Beat.
    Idempotente: ON CONFLICT (bank_transaction_id) DO NOTHING.
    """
    try:
        from modules.financial.services.auto_sync_service import run_full_sync

        result = run_full_sync(limit=500)
        logger.info(
            "[Financial Task] sync_cashflow: pending=%s synced=%s errors=%s",
            result["pending"],
            result["synced"],
            result["errors"],
        )
        return result
    except Exception as exc:
        logger.error("[Financial Task] sync_cashflow error: %s", exc)
        raise self.retry(exc=exc)


@app.task(
    name="financial.inter_reconciliacao_diaria",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
)
def inter_reconciliacao_diaria_task(self):
    """Conciliação bancária DIÁRIA: sincroniza o extrato do Banco Inter e organiza a conciliação.

    Puxa os últimos 7 dias do extrato via API → grava em inter_transactions → faz a PONTE para
    bank_transactions (conciliação) → auto-categoriza os PIX de VT+VR de diaristas (R$32 e múltiplos)
    e marca os fornecedores conhecidos. Idempotente. Não move dinheiro nem baixa contas.
    """
    try:
        async def _run(session):
            from modules.integrations.inter.inter_sync_service import InterSyncService
            svc = InterSyncService(session)
            return await svc.sincronizar_extrato(dias=7)

        result = _run_async(_run)
        logger.info("[Financial Task] inter_reconciliacao_diaria: %s", result)
        return result
    except Exception as exc:
        logger.error("[Financial Task] inter_reconciliacao_diaria error: %s", exc)
        raise self.retry(exc=exc)


@app.task(
    name="financial.auto_baixa_pagaveis",
    bind=True,
    max_retries=1,
)
def auto_baixa_pagaveis_task(self):
    """Auto-BAIXA de contas a pagar por conciliação — SÓ match EXATO (CNPJ+valor+data, ou valor+data
    com candidato ÚNICO). Bookkeeping: marca 'pago' quando o débito bancário bate exatamente com um
    pagável pendente. NÃO move dinheiro (pagar = fluxo OTP). Débitos sem match exato ficam p/ baixa
    manual. Idempotente (pula conciliado/justificado). Roda após o sync do extrato."""
    try:
        from modules.financial.services import reconciliation_service as _rec
        result = _rec.conciliar_saidas()
        # As ENTRADAS junto, no mesmo beat: sem isto a carteira acusava R$152.077,82
        # vencidos com o dinheiro já nas duas contas — o título é BRUTO, o cliente paga
        # LÍQUIDO, e o casamento exigia o centavo exato. Não é o mesmo laço porque a
        # seleção é outra (vínculo, não rótulo).
        result["recebiveis"] = _rec.conciliar_recebiveis()
        logger.info("[Financial Task] auto_baixa_pagaveis: %s", result)
        return result
    except Exception as exc:
        logger.error("[Financial Task] auto_baixa_pagaveis error: %s", exc)
        raise self.retry(exc=exc)


async def _propor_baixa_pendentes(session) -> dict:
    """Para cada conta a pagar VENCIDA há +30d e ainda pendente (>= R$500), cria um RASCUNHO na
    Central propondo a baixa (propor→aprovar). Resolve os grandes pendentes (folha/tributos/
    fornecedores sem match automático 1:1) SEM auto-baixa cega: o gestor aprova o que já foi pago.
    Idempotente (1 rascunho por pagável, via idempotency_key). NÃO move dinheiro."""
    from sqlalchemy import text

    from modules.ai.conversation.services.orquestrador.acoes.rascunho import criar_rascunho

    # A EVIDÊNCIA vai junto. Medido em 13/08/2026: das 69 contas pendentes, só 3
    # casariam com uma saída do extrato — mas 49 são de fornecedor a quem a empresa
    # JÁ PAGOU muitas vezes (SOLIDES: 89 pagamentos, R$169.945,89, e ainda "deve"
    # R$2.890 duas vezes). Isso não é dívida, é resíduo de registro. Um rascunho que
    # só diz "está pendente" devolve a pergunta ao Jordan; um que diz "você já pagou
    # 89 vezes a este fornecedor" devolve uma DECISÃO.
    import re as _re

    # O token tem que DISCRIMINAR. Usar a primeira palavra do nome dava `L` para
    # "L J GUERRA E CIA LTDA" e a evidência saiu "3300 pagamentos" — número que
    # casa com metade do extrato e destrói a confiança no rascunho inteiro.
    # Mesmo critério do resto do módulo: palavra mais longa que não seja tipo de
    # pessoa jurídica.
    _GEN = {"LTDA", "COMERCIO", "SERVICOS", "TECNOLOGIA", "INDUSTRIA", "PRODUTOS",
            "EMPRESA", "DIGITAL", "ARTIGOS", "PARA", "ESCRITORIO", "MATRIZ", "FILIAL"}

    def _tok(nome: str) -> str:
        ts = [w for w in _re.split(r"[^A-Za-zÀ-ÿ]+", nome or "") if len(w) >= 4]
        ts = [w for w in ts if w.upper() not in _GEN] or ts
        return max(ts, key=len) if ts else ""

    rows = (await session.execute(text("""
        SELECT p.id::text, coalesce(p.description,'conta a pagar'), p.net_value, p.due_date,
               coalesce(p.supplier_name, p.fornecedor_nome, '') AS forn
        FROM payable_accounts p
        WHERE p.status='pendente' AND p.due_date < current_date - interval '30 day'
          AND p.net_value >= 500
        ORDER BY p.net_value DESC LIMIT 40"""))).fetchall()
    criados = 0
    for pid, desc, val, due, forn in rows:
        _t = _tok(forn or desc)
        pagos = 0
        if len(_t) >= 4:
            pagos = int((await session.execute(text(
                "SELECT count(*) FROM bank_transactions WHERE amount < 0 AND "
                "(coalesce(counterparty_name,'') || ' ' || coalesce(description,'')) ILIKE :t"),
                {"t": f"%{_t}%"})).scalar() or 0)
        try:
            r = await criar_rascunho(
                session, None,
                tipo="financeiro_baixa_pagavel", modulo="financeiro",
                titulo=f"Dar baixa: {str(desc)[:48]} — R$ {float(val):,.2f}",
                resumo=(f"Conta vencida em {due} e ainda PENDENTE no sistema. Se ela JÁ foi paga, "
                        f"aprove para dar baixa (marca 'pago', NÃO move dinheiro). Se ainda não foi "
                        f"paga, dispense. (folha/tributo/fornecedor sem baixa automática.)\n\n"
                        + (f"EVIDÊNCIA: a empresa já fez {pagos} pagamento(s) a {forn[:40]} pelo "
                           f"extrato. Fornecedor recorrente com conta em aberto costuma ser baixa "
                           f"que faltou, não dívida."
                           if pagos else
                           f"EVIDÊNCIA: NENHUMA saída para {(forn or desc)[:40]} aparece no extrato "
                           f"das duas contas. Ou foi paga por outro meio (cartão pessoal), ou não "
                           f"foi paga mesmo.")),
                payload={"payable_id": pid, "valor": float(val),
                         "pagamentos_ao_fornecedor": int(pagos or 0),
                         "origem": "proposta_baixa_vencidos"},
                gate="🟡", requires_otp=False, roles_aprovador=("admin",),
                idempotency_key=f"baixa_pagavel:{pid}")
            if isinstance(r, dict) and r.get("status") == "rascunho" and not r.get("duplicado"):
                criados += 1
        except Exception as _e:  # noqa: BLE001 — um item nunca derruba o lote
            logger.warning("[Financial Task] propor_baixa %s: %s", pid, _e)
    return {"propostos": criados, "candidatos_vencidos": len(rows)}


@app.task(name="financial.propor_baixa_pendentes", bind=True, max_retries=1)
def propor_baixa_pendentes_task(self):
    """Propõe rascunho de baixa na Central para grandes pendentes vencidos (propor→aprovar).
    Bookkeeping: NÃO move dinheiro; o gestor aprova o que já foi pago. Idempotente."""
    try:
        result = _run_async(_propor_baixa_pendentes)
        logger.info("[Financial Task] propor_baixa_pendentes: %s", result)
        return result
    except Exception as exc:
        logger.error("[Financial Task] propor_baixa_pendentes error: %s", exc)
        raise self.retry(exc=exc)


async def _propor_cobranca_vencidos(session) -> dict:
    """Para cada recebível REALMENTE vencido, cria um rascunho com a mensagem de cobrança
    pronta — o humano aprova e envia pelo canal dele.

    A régua (`regua_cobranca_service`) existia completa e NINGUÉM a chamava: nenhuma task,
    nenhum beat. Inadimplência real era silêncio. Em 13/08/2026 sobravam R$4.500 de fato
    devidos (Hawk Eye e Green Hills, confirmados pelo Jordan) e o sistema não dizia nada.

    NÃO envia ao cliente: mensagem a cliente real é gate humano — é a mesma regra que faz
    o v1 da régua entregar o texto pronto em vez de disparar. Idempotente por título+nível:
    subir de 'lembrete' para 'notificação formal' gera rascunho novo; repetir o mesmo nível
    no dia seguinte, não.
    """
    from modules.ai.conversation.services.orquestrador.acoes.rascunho import criar_rascunho
    from modules.financial.services.regua_cobranca_service import montar_fila_cobranca

    fila = await montar_fila_cobranca(session)
    criados = 0
    for item in fila:
        try:
            r = await criar_rascunho(
                session, None,
                tipo="financeiro_cobranca", modulo="financeiro",
                titulo=f"Cobrar {item['cliente'][:40]} — R$ {item['valor']:,.2f} "
                       f"({item['dias']}d de atraso)",
                resumo=(f"Vencido em {item['vencimento']}, nível {item['nivel']}, canal sugerido "
                        f"{item['canal']}. Mensagem pronta abaixo — aprovar NÃO envia nada ao "
                        f"cliente: registra a tentativa e libera o texto para você mandar.\n\n"
                        f"{item['mensagem']}"),
                payload={"receivable_id": item["id"], "valor": item["valor"],
                         "nivel": item["nivel"], "canal": item["canal"],
                         "mensagem": item["mensagem"], "origem": "regua_cobranca"},
                gate="🟡", requires_otp=False, roles_aprovador=("admin",),
                idempotency_key=f"cobranca:{item['id']}:{item['nivel']}")
            if isinstance(r, dict) and r.get("status") == "rascunho" and not r.get("duplicado"):
                criados += 1
        except Exception as _e:  # noqa: BLE001 — um item nunca derruba o lote
            logger.warning("[Financial Task] propor_cobranca %s: %s", item.get("id"), _e)
    return {"propostos": criados, "vencidos_na_fila": len(fila),
            "total_vencido": round(sum(i["valor"] for i in fila), 2)}


async def _fechar_ordens_pelo_extrato(session) -> dict:
    """Fecha os itens de ordem de pagamento que já apareceram no extrato.

    O Cora não paga por API, então o pagamento é feito no app — mas a ordem foi
    aprovada aqui, com OTP e teto. Este beat é a outra ponta: encontra a saída no
    extrato e marca o item como pago, sem ninguém precisar voltar na tela.
    """
    from modules.financial.services.ordem_pagamento_service import fechar_pelo_extrato

    return await fechar_pelo_extrato(session)


async def _enriquecer_extrato_inter(session, dias: int = 10) -> dict:
    """Preenche a contraparte nas linhas do Inter que já foram sincronizadas.

    O sync usa `/extrato` (simples), que NÃO traz favorecido — e não dá para trocar
    pelo `/extrato/completo` porque a `descricao` dele tem outro formato e a descrição
    entra na chave de dedup: em 14/08/2026 a troca duplicou 47 linhas (R$1.497,79) e o
    oráculo do extrato pegou pelo saldo.

    Então: sincroniza pelo simples, enriquece pelo completo. Casa por (data, valor) e
    só quando a combinação é ÚNICA dos dois lados — PIX de R$32 repetido no mesmo dia
    fica intocado, porque ali adivinhar é amarrar pagamento na pessoa errada.
    """
    from datetime import date, timedelta
    from collections import defaultdict
    from sqlalchemy import text as _t
    from modules.integrations.inter.inter_sync_service import _build_adapter

    fim, ini = date.today(), date.today() - timedelta(days=dias)
    acc = (await session.execute(_t(
        "SELECT id::text FROM bank_accounts WHERE bank_code='077' LIMIT 1"))).scalar()
    if not acc:
        return {"erro": "conta Inter não encontrada"}

    ad = _build_adapter()
    try:
        completo = await ad.get_statement_completo(ini, fim)
    finally:
        await ad.close()

    por_api = defaultdict(list)
    for t in completo:
        por_api[(t.date.date(), float(t.amount))].append(t)

    ligados = ambiguos = 0
    for chave, lst in por_api.items():
        if len(lst) != 1:
            ambiguos += len(lst)
            continue
        t = lst[0]
        if not (t.counterpart_document or t.reference):
            continue
        linhas = (await session.execute(_t("""
            SELECT id::text FROM bank_transactions
             WHERE bank_account_id = CAST(:a AS uuid) AND transaction_date = :d AND amount = :v
               AND coalesce(counterparty_document,'') = ''
        """), {"a": acc, "d": chave[0], "v": chave[1]})).fetchall()
        if len(linhas) != 1:
            ambiguos += len(linhas)
            continue
        await session.execute(_t("""
            UPDATE bank_transactions SET
              counterparty_name     = coalesce(nullif(counterparty_name,''), :nm),
              counterparty_document = :dc,
              pix_end_to_end        = coalesce(nullif(pix_end_to_end,''), :e2e),
              pix_key               = coalesce(nullif(pix_key,''), :ch),
              -- external_id tem UNIQUE. Se o id ja esta em OUTRA linha, nao force:
              -- isso significa que um dos dois casamentos esta errado, e derrubar o
              -- beat todo dia por causa disso e pior do que ficar sem o identificador.
              external_id = CASE
                  WHEN coalesce(external_id,'') <> '' THEN external_id
                  WHEN EXISTS (SELECT 1 FROM bank_transactions x WHERE x.external_id = :ext)
                      THEN external_id
                  ELSE :ext END,
              updated_at = now()
            WHERE id = CAST(:i AS uuid)
        """), {"nm": t.counterpart_name, "dc": t.counterpart_document, "e2e": t.reference,
               "ch": t.counterpart_pix_key, "ext": t.transaction_id, "i": linhas[0][0]})
        ligados += 1
    await session.commit()
    return {"ligados": ligados, "ambiguos": ambiguos, "api": len(completo), "dias": dias}


@app.task(name="financial.enriquecer_extrato_inter", bind=True, max_retries=1)
def enriquecer_extrato_inter_task(self):
    """Preenche favorecido, endToEndId e chave PIX nas linhas do Inter. Só LÊ da API
    e atualiza local — não cria linha, não move dinheiro."""
    try:
        result = _run_async(_enriquecer_extrato_inter)
        logger.info("[Financial Task] enriquecer_extrato_inter: %s", result)
        return result
    except Exception as exc:
        logger.error("[Financial Task] enriquecer_extrato_inter error: %s", exc)
        raise self.retry(exc=exc)


@app.task(name="financial.fechar_ordens_pagamento", bind=True, max_retries=1)
def fechar_ordens_pagamento_task(self):
    """Fecha ordens de pagamento contra o extrato. NÃO paga nada — só reconhece
    o que já saiu. Roda depois do sync do extrato."""
    try:
        result = _run_async(_fechar_ordens_pelo_extrato)
        logger.info("[Financial Task] fechar_ordens_pagamento: %s", result)
        return result
    except Exception as exc:
        logger.error("[Financial Task] fechar_ordens_pagamento error: %s", exc)
        raise self.retry(exc=exc)


@app.task(name="financial.propor_cobranca_vencidos", bind=True, max_retries=1)
def propor_cobranca_vencidos_task(self):
    """Propõe cobrança dos recebíveis vencidos na Central (propor→aprovar).
    NÃO manda mensagem a cliente: entrega o texto pronto para o humano enviar."""
    try:
        result = _run_async(_propor_cobranca_vencidos)
        logger.info("[Financial Task] propor_cobranca_vencidos: %s", result)
        return result
    except Exception as exc:
        logger.error("[Financial Task] propor_cobranca_vencidos error: %s", exc)
        raise self.retry(exc=exc)


@app.task(name="financial.registrar_obrigacoes", bind=True, max_retries=1)
def registrar_obrigacoes_task(self):
    """Registra como PAGÁVEL o que a empresa deve, a partir das fontes reais
    (NFS-e tomadas, folha, guias). Idempotente por chave natural — rodar de novo
    não duplica. NÃO move dinheiro: registrar a obrigação ≠ pagar."""
    from modules.financial.services.payable_sources_service import gerar_pagaveis

    try:
        result = gerar_pagaveis(preview=False)
        logger.info("[Financial Task] registrar_obrigacoes: %s", result.get("total_criados"))
        return {k: v for k, v in result.items() if k != "fontes"}
    except Exception as exc:
        logger.error("[Financial Task] registrar_obrigacoes error: %s", exc)
        raise self.retry(exc=exc)


@app.task(name="financial.gerar_recebiveis_mes", bind=True, max_retries=1)
def gerar_recebiveis_mes_task(self):
    """Recebível por contrato/competência do mês CORRENTE. Sem isso o contas-a-receber
    fica vazio e aging/inadimplência/régua giram no vácuo. NÃO emite cobrança ao
    cliente (boleto/PIX é ato separado, com decisão humana). Idempotente."""
    from datetime import date as _date

    from modules.financial.services.receivable_contract_service import gerar_recebiveis

    try:
        hoje = _date.today()
        result = gerar_recebiveis(hoje.month, hoje.year, preview=False)
        logger.info("[Financial Task] gerar_recebiveis_mes: %s", result.get("criados"))
        return {k: v for k, v in result.items() if k != "itens"}
    except Exception as exc:
        logger.error("[Financial Task] gerar_recebiveis_mes error: %s", exc)
        raise self.retry(exc=exc)


@app.task(name="financial.apurar_competencia", bind=True, max_retries=1)
def apurar_competencia_task(self):
    """Encerra a competência ANTERIOR contra o PL, todo dia 5.

    Dia 5 e não dia 1: a escrituração do extrato roda 08:40 e a NFS-e do mês
    fechado ainda pode entrar nos primeiros dias. Apurar cedo demais encerraria
    uma competência incompleta, e apuração é idempotente mas não retroage.

    Idempotente por documento_ref = APURACAO-{competência}-{conta}. NÃO move
    dinheiro: é escrituração."""
    from datetime import date

    from modules.financial.services.apuracao_resultado import apurar, saldo_da_apuracao

    try:
        hoje = date.today()
        ant = date(hoje.year, hoje.month, 1).toordinal() - 1
        comp = f"{date.fromordinal(ant):%Y-%m}"
        r = apurar(comp, preview=False)
        # A conta de passagem tem que voltar a zero. Se sobrou, a apuração ficou
        # pela metade e o balanço fecharia mentindo — grita agora, não no mês que vem.
        sobra = saldo_da_apuracao()
        if abs(sobra) > 0.01:
            raise RuntimeError(
                f"apuração de {comp} ficou pela metade: 3.3.1.01 com saldo de R$ {sobra:,.2f}")
        logger.info("[Financial Task] apurar_competencia %s: %s contas, resultado %s",
                    comp, r.get("contas_encerradas"), r.get("resultado"))
        return {k: v for k, v in r.items() if k != "linhas"}
    except Exception as exc:
        logger.error("[Financial Task] apurar_competencia error: %s", exc)
        raise self.retry(exc=exc)


@app.task(name="financial.escriturar_extrato", bind=True, max_retries=1)
def escriturar_extrato_task(self):
    """Lança no razão a movimentação bancária que ainda não tem lançamento.
    Idempotente por bank_transaction_id. NÃO move dinheiro: é escrituração."""
    from modules.financial.services.extrato_para_razao import escriturar

    try:
        r = escriturar(preview=False)
        logger.info("[Financial Task] escriturar_extrato: %s lançados", r.get("lancados"))
        return {k: v for k, v in r.items() if k != "por_conta"}
    except Exception as exc:
        logger.error("[Financial Task] escriturar_extrato error: %s", exc)
        raise self.retry(exc=exc)


@app.task(
    name="financial.inter_monitorar_pendentes",
    bind=True,
    max_retries=1,
)
def inter_monitorar_pendentes_task(self):
    """MONITOR automático: verifica no Inter o status dos pagamentos que estão
    'aguardando_aprovacao' e atualiza para 'confirmado'/'erro' quando o Inter concluir/rejeitar.
    Assim o Jordan não precisa clicar em 'Status Inter' — o sistema acompanha em tempo real.
    Só leitura no Inter; não move dinheiro."""
    try:
        async def _run(session):
            from sqlalchemy import text

            from modules.integrations.inter.services.payment_service import InterPaymentService

            rows = (
                await session.execute(
                    text(
                        "SELECT id FROM inter_payments "
                        "WHERE status = 'aguardando_aprovacao' "
                        "AND created_at > now() - interval '10 days' "
                        "ORDER BY created_at DESC LIMIT 50"
                    )
                )
            ).fetchall()
            svc = InterPaymentService(session)
            atualizados = 0
            for r in rows:
                try:
                    res = await svc.atualizar_status_inter(str(r[0]))
                    if res.get("status") != "aguardando_aprovacao":
                        atualizados += 1
                except Exception as e:  # noqa: BLE001
                    logger.warning("monitor pendente %s: %s", r[0], e)
            return {"checados": len(rows), "concluidos_ou_alterados": atualizados}

        result = _run_async(_run)
        logger.info("[Financial Task] inter_monitorar_pendentes: %s", result)
        return result
    except Exception as exc:
        logger.error("[Financial Task] inter_monitorar_pendentes error: %s", exc)
        raise self.retry(exc=exc, countdown=120)


# ═══════════════════════════════════════
# GEDEON LAYER 2 — Execução automática dos agentes financeiros
# ═══════════════════════════════════════


def _run_async(coro):
    """Helper para rodar corrotinas async nas tasks Celery."""
    import asyncio
    import os

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    DATABASE_URL = os.getenv("DATABASE_URL", "").replace("postgresql://", "postgresql+asyncpg://")

    async def _inner():
        engine = create_async_engine(DATABASE_URL, echo=False)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as session:
            return await coro(session)

    return asyncio.run(_inner())


@app.task(name="gedeon.risk_monitor", bind=True, max_retries=3)
def gedeon_risk_monitor_task(self):
    """RiskMonitorAgent — executa a cada 5 minutos."""

    def run(session):
        from modules.financial.agents.gedeon_financial_orchestrator import GedeonFinancialOrchestrator

        orch = GedeonFinancialOrchestrator(db=session)
        return orch.run_risk_monitor()

    try:
        return _run_async(run)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@app.task(name="gedeon.daily_all", bind=True, max_retries=1)
def gedeon_daily_all_task(self):
    """Pipeline diário — todos os agentes (07:00)."""

    def run(session):
        from modules.financial.agents.gedeon_financial_orchestrator import GedeonFinancialOrchestrator

        orch = GedeonFinancialOrchestrator(db=session)
        return orch.run_all_daily()

    try:
        return _run_async(run)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=300)


@app.task(name="gedeon.cashflow_predictor", bind=True, max_retries=2)
def gedeon_cashflow_predictor_task(self):
    """CashflowPredictorAgent — diariamente às 07:00."""

    def run(session):
        from modules.financial.agents.gedeon_financial_orchestrator import GedeonFinancialOrchestrator

        orch = GedeonFinancialOrchestrator(db=session)
        return orch.run_cashflow_predictor()

    try:
        return _run_async(run)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=300)


@app.task(name="gedeon.collection_negotiator", bind=True, max_retries=2)
def gedeon_collection_negotiator_task(self):
    """CollectionNegotiatorAgent — diariamente às 09:00."""

    def run(session):
        from modules.financial.agents.gedeon_financial_orchestrator import GedeonFinancialOrchestrator

        orch = GedeonFinancialOrchestrator(db=session)
        return orch.run_collection_negotiator()

    try:
        return _run_async(run)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=300)


@app.task(
    bind=True,
    name="financial.cora_sync_extrato",
    max_retries=2,
    default_retry_delay=600,
)
def cora_sync_extrato_task(self):
    """Multi-CNPJ E4: extrato da conta Cora (Patrimonial) → bank_transactions,
    com conciliação automática líquido×NFS-e. Idempotente por external_id."""
    try:
        from modules.integrations.banking.services.cora_sync_service import (
            sincronizar_extrato_cora,
        )

        rel = sincronizar_extrato_cora(dias=60)
        logger.info("Cora extrato: %s", rel)
        return rel
    except Exception as exc:
        logger.error("Erro no sync do extrato Cora: %s", exc)
        raise self.retry(exc=exc)


@app.task(bind=True, name="financial.sync_bank_balances", max_retries=1, default_retry_delay=300)
def sync_bank_balances_task(self):
    """Atualiza SÓ o saldo (bank_accounts) de Inter e Cora com o valor REAL ao vivo
    (mTLS, READ-only). Roda no worker a cada 15 min, FORA do caminho de render das
    telas — I/O de banco no render derrubava o web (502). Não move dinheiro."""
    import asyncio

    from sqlalchemy import text

    from core.database.session import get_sync_db

    async def _inter():
        from modules.integrations.inter.client import InterClient
        async with InterClient() as cli:
            return await asyncio.wait_for(cli.consultar_saldo(), timeout=15)

    async def _cora():
        from modules.integrations.banking.adapters.cora import CoraAdapter
        ad = CoraAdapter()
        if not await asyncio.wait_for(ad.authenticate(), timeout=15):
            return None
        return await asyncio.wait_for(ad.get_balance(), timeout=15)

    out: dict = {}
    with get_sync_db() as db:
        for nome, coro, like in (("inter", _inter, "%inter%"), ("cora", _cora, "%cora%")):
            try:
                saldo = asyncio.run(coro())
                if saldo is None:
                    out[nome] = "sem saldo"
                    continue
                total = float(getattr(saldo, "total", None) or getattr(saldo, "available", 0) or 0)
                avail = float(getattr(saldo, "available", None) or total)
                blk = float(getattr(saldo, "blocked", 0) or 0)
                db.execute(text(
                    "UPDATE bank_accounts SET current_balance=:t, available_balance=:a, "
                    "blocked_balance=:b, last_balance_update=NOW(), updated_at=NOW() "
                    "WHERE ativo IS NOT FALSE AND bank_name ILIKE :like"),
                    {"t": total, "a": avail, "b": blk, "like": like})
                db.commit()
                out[nome] = total
            except Exception as exc:  # noqa: BLE001 — um banco falhar não derruba o outro
                db.rollback()
                out[nome] = f"erro: {exc}"
                logger.warning("sync_bank_balances %s falhou: %s", nome, exc)
    logger.info("sync_bank_balances: %s", out)
    return out


@app.task(name="financial.radar_fornecedores", bind=True, max_retries=1)
def radar_fornecedores_task(self):
    """Avisa no sino os fornecedores recorrentes que vão vencer SEM título cadastrado.

    O caso que motivou (19/08/2026): a Full Telecom era paga todo mês desde março e
    nunca teve conta a pagar. Sem título, nada avisa; o boleto venceu e o banco passou
    a exigir valor atualizado — R$4,48 de juros num boleto de R$149, e 30 dias sem
    saber que devia. O `registrar_obrigacoes` não pega esses: telecom, energia e água
    não emitem NFS-e.

    NÃO cria pagável. Inferir dívida a partir de histórico seria afirmar o que ninguém
    emitiu. Radar mostra; boleto real ou humano cria.

    Silêncio quando não há nada — verde não gera notificação, senão ninguém lê o sino.
    """
    import json
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from sqlalchemy import text as _text

    from core.database.session import SyncSessionLocal
    from modules.financial.services.radar_fornecedores_service import varrer

    try:
        with SyncSessionLocal() as db:
            r = varrer(db)
            achados = r["achados"]
            if not achados:
                logger.info("[Financial Task] radar_fornecedores: nada a avisar")
                return {"sem_titulo": 0}

            linhas = "\n".join(
                f"• {a['fornecedor']} — R$ {a['valor_tipico']:,.2f} "
                f"(~dia {a['vencimento_estimado'][8:10]}, {a['meses_pagos']} meses pagos)"
                for a in achados[:12]
            )
            corpo = (
                f"{len(achados)} fornecedor(es) com pagamento recorrente e SEM conta a "
                f"pagar para o próximo vencimento:\n\n{linhas}\n\n"
                "A data é ESTIMADA pelo histórico de PAGAMENTO, não é o vencimento "
                "oficial. Serve para pedir a segunda via antes de vencer."
            )
            dia = datetime.now(ZoneInfo("America/Manaus")).strftime("%Y-%m-%d")
            extra = json.dumps({
                "idempotency_key": f"radar_fornecedores:{dia}",
                "origem": "radar_fornecedores", "familia": "financeiro",
                "severidade": "atencao", "quantidade": len(achados),
            })
            destinatarios = [x[0] for x in db.execute(_text(
                "SELECT id::text FROM users WHERE lower(coalesce(role,''))='admin' "
                "AND coalesce(is_active,true)=true "
                "AND lower(coalesce(email,'')) NOT LIKE 'mcp-service%'"
            )).fetchall()]
            for uid in destinatarios:
                db.execute(_text(
                    "INSERT INTO communication_notifications "
                    "(id, tenant_id, user_id, title, body, type, reference_type, "
                    " action_url, extra_data, is_active, sent_at, created_at) "
                    "VALUES (gen_random_uuid(), :uid, :uid, :titulo, :corpo, 'alerta', "
                    " 'radar_fornecedores', '/redesign/financeiro', CAST(:extra AS jsonb), "
                    " true, NOW(), NOW()) ON CONFLICT DO NOTHING"
                ), {"uid": uid, "titulo": f"Radar: {len(achados)} fornecedor(es) sem título",
                    "corpo": corpo, "extra": extra})
            db.commit()
            logger.info("[Financial Task] radar_fornecedores: %s avisos, %s destinatários",
                        len(achados), len(destinatarios))
            return {"sem_titulo": len(achados), "destinatarios": len(destinatarios)}
    except Exception as exc:
        logger.error("[Financial Task] radar_fornecedores error: %s", exc)
        raise self.retry(exc=exc)


@app.task(name="financial.boletos_por_email", bind=True, max_retries=1)
def boletos_por_email_task(self):
    """Lê a caixa de e-mail e registra boleto recebido como conta a pagar.

    Fecha a cegueira do `radar_fornecedores`: aquele só vê quem a empresa JÁ pagou.
    Boleto de fornecedor novo não tem histórico e ninguém sabe que existe até vencer.

    Só registra código de barras VÁLIDO (dígitos verificadores conferem) e é idempotente
    pelo índice `uq_payable_boleto_email`. NÃO paga: registrar obrigação ≠ pagar.
    """
    import json
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from sqlalchemy import text as _text

    from core.database.session import SyncSessionLocal
    from modules.financial.services.boleto_email_service import varrer_e_registrar

    try:
        with SyncSessionLocal() as db:
            r = varrer_e_registrar(db)
            if r.get("erro"):
                # Erro de leitura vira exceção para virar alerta no sino via task_falha:
                # caixa inacessível em silêncio é o mesmo que radar desligado.
                raise RuntimeError(f"leitura da caixa {r['caixa']} falhou: {r['erro']}")

            novos = [b for b in r["boletos"] if b.get("situacao") == "criado"]
            if not novos:
                logger.info("[Financial Task] boletos_por_email: %s msg, nada novo",
                            r["mensagens"])
                return {"mensagens": r["mensagens"], "criados": 0}

            linhas = "\n".join(
                f"• {b['fornecedor']} — R$ {b['valor']:,.2f}"
                + (f", vence {b['vencimento'][8:10]}/{b['vencimento'][5:7]}"
                   if b["vencimento"] else ", VENCIMENTO A CONFERIR (convênio)")
                for b in novos[:12]
            )
            corpo = (
                f"{len(novos)} boleto(s) recebido(s) por e-mail viraram conta a pagar:\n\n"
                f"{linhas}\n\nCódigo de barras validado. Confira antes de pagar — "
                "o registro da obrigação não é autorização de pagamento."
            )
            dia = datetime.now(ZoneInfo("America/Manaus")).strftime("%Y-%m-%d")
            extra = json.dumps({
                "idempotency_key": f"boletos_email:{dia}",
                "origem": "boletos_por_email", "familia": "financeiro",
                "severidade": "atencao", "quantidade": len(novos),
            })
            for uid in [x[0] for x in db.execute(_text(
                "SELECT id::text FROM users WHERE lower(coalesce(role,''))='admin' "
                "AND coalesce(is_active,true)=true "
                "AND lower(coalesce(email,'')) NOT LIKE 'mcp-service%'")).fetchall()]:
                db.execute(_text(
                    "INSERT INTO communication_notifications "
                    "(id, tenant_id, user_id, title, body, type, reference_type, "
                    " action_url, extra_data, is_active, sent_at, created_at) "
                    "VALUES (gen_random_uuid(), :uid, :uid, :titulo, :corpo, 'alerta', "
                    " 'boletos_por_email', '/redesign/financeiro', CAST(:extra AS jsonb), "
                    " true, NOW(), NOW()) ON CONFLICT DO NOTHING"
                ), {"uid": uid, "titulo": f"{len(novos)} boleto(s) novo(s) por e-mail",
                    "corpo": corpo, "extra": extra})
            db.commit()
            logger.info("[Financial Task] boletos_por_email: %s criados de %s msg",
                        len(novos), r["mensagens"])
            return {"mensagens": r["mensagens"], "criados": len(novos)}
    except Exception as exc:
        logger.error("[Financial Task] boletos_por_email error: %s", exc)
        raise self.retry(exc=exc)
