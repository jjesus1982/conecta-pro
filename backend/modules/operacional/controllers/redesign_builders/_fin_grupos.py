"""F0 — composição dos 7 grupos do financeiro (fundação tabs). Mapeia TODA tela antiga
para (grupo, aba); o oráculo da fase acusa órfãos (tela fora de grupo) — nada se perde.
Prefixo _ = o discovery de builders pula este arquivo (é helper, não módulo)."""
from modules.operacional.controllers.redesign_data_controller import grp, moved

GRUPOS = [
    ("g-visao", "Visão Geral", "Resumo executivo do financeiro", [
        ("cockpit", "Cockpit"), ("dashboard", "Resumo"), ("fluxo-caixa", "Fluxo de Caixa"),
        ("projecao", "Projeção & Insights"), ("dre-inline", "DRE"), ("indicadores", "Indicadores DSO/DPO"), ("tendencias", "Tendências"),
        ("raio-x", "Raio-X"), ("cfo", "CFO IA"), ("cfo-perguntar", "Perguntar ao CFO"), ("cfo-perguntar-arquivo", "Perguntar com anexo"), ("cashflow-sync", "Sincronizar fluxo de caixa"), ("fluxo-resumo", "Resumo do período"), ("fluxo-tendencia", "Tendência mensal"), ("fluxo-categorias", "Saídas por categoria"), ("fluxo-fornecedores", "Saídas por fornecedor"), ("agentes", "Agentes"), ("relatorios", "Relatórios")]),
    ("g-receber", "Receber", "Contas a receber, cobrança e faturamento", [
        ("contas-receber", "Contas a Receber"),
        ("nfse-a-receber", "NFS-e × a receber"), ("gerar-contas-de-nfse", "Gerar das NFS-e"), ("cobrancas", "Cobranças"),
        ("regua", "Régua"), ("fila-cobranca", "Fila de cobrança"), ("registrar-cobranca", "Registrar cobrança"),
        ("recorrencia", "Recorrência (MRR)"), ("gerar-cobrancas", "Gerar cobranças"), ("boletos", "Boletos"),
        ("emitir-boleto", "Emitir boleto"), ("cobrar-pix", "Cobrar PIX"),
        ("faturamento", "Faturamento"), ("clientes", "Clientes"),
        ("gerar-recebiveis", "Gerar do mês"), ("baixar-recebivel", "Dar baixa"), ("registrar-conta-receber", "Registrar"), ("billing-contrato-ativado", "Faturar contrato ativado")]),
    # ── "Pagar" tinha 29 ABAS num grupo só, e o Jordan disse o que isso é na prática:
    # "tem tantos botões que confunde, não consigo ver". Não era falta de recurso — era
    # tudo empilhado no mesmo lugar. Dividido em quatro, pela PERGUNTA que ele tem na
    # cabeça ao abrir, não pelo tipo técnico da tela:
    #   "o que eu devo?" · "vou pagar as pessoas" · "vou pagar uma conta/imposto"
    #   · "o que já saiu?"
    # A primeira aba de cada grupo é a que abre — então é a mais usada, não a mais antiga.
    # Os ids das abas NÃO mudam: `moved()` mantém os links antigos vivos.
    #
    # ⚠️ O `sub` de cada grupo é PLACA, não decoração: quem tinha o link antigo
    # (?t=g-pagar) cai em "Pagar" e não encontra mais os diaristas — eles mudaram de
    # grupo. Aconteceu com o Jordan: "não vi porra nenhuma, acho que ficou pior". Mudar
    # o mapa sem deixar placa é pior que não mudar.
    ("g-pagar", "Pagar", "O que a empresa deve. Diaristas, VT/VR e folha estão em «Pessoas & Folha» · boleto, PIX e impostos em «Contas & Impostos» · lotes e o que já saiu em «Ordens & Histórico».", [
        ("contas-pagar", "Contas a Pagar"), ("registrar-conta-pagar", "Registrar conta"),
        ("registrar-obrigacoes", "Gerar das NFS-e/folha/guias"), ("payables-auto-criar", "Criar pagáveis das NFS-e"),
        ("baixar-pagavel", "Dar baixa"), ("fila-aprovacao", "Aprovação"), ("pagaveis-recorrentes-gerar", "Gerar recorrentes"), ("parcelas-pendentes", "Parcelas pendentes")]),
    ("g-pagar-pessoas", "Pessoas & Folha", "Diaristas, VT/VR e folha — quem recebe da empresa. Contas e impostos ficam em «Contas & Impostos»; a lista de dívidas, em «Pagar».", [
        ("folha-pj-programar", "Programar folha PJ"),
        # ⚠️ Nome de aba tem de dizer O QUE SAI. "Pagar diaristas" foi lido pelo Jordan
        # como "pagar o dia trabalhado do profissional" — e a tela paga VT+VR, diária, ou
        # os dois. Rótulo ambíguo em tela de dinheiro é convite a pagar a coisa errada.
        ("pagamentos-diaristas", "A pagar — VT+VR e diárias"),
        ("pagar-diaristas", "Pagar VT+VR ou diárias"),
        # Programar virou automático (beat 7h-21h); esta aba fica como saída manual para
        # quem não quer esperar a hora cheia. O rótulo diz isso.
        ("programar-vtvr-dia", "Programar VT+VR agora (manual)"),
        ("adicionar-vtvr-avulso", "VT+VR avulso (líder/cobertura)"),
        ("programar-diarias-mes", "Programar diárias do mês"),
        ("pagamentos-pj", "Folha PJ"), ("pagar-folha-pj", "Pagar folha PJ"),
        ("pagar-folha-clt", "Pagar folha CLT"),
        ("documentos-diaristas", "Recibos dos diaristas"),
        ("diaristas-a-cadastrar", "Diaristas a cadastrar"),
        ("diarias-sobrepostas", "Sobrepostas à folha CLT")]),
    ("g-pagar-contas", "Contas & Impostos", "Boleto, tributo e transferência avulsa (gate OTP). Pagar pessoas fica em «Pessoas & Folha».", [
        ("pagar-boleto", "Pagar boleto"), ("enviar-pix", "PIX / Transferir"),
        ("transferir-ted", "TED"), ("pagar-darf", "DARF"), ("pagar-gps", "GPS / INSS")]),
    ("g-pagar-ordens", "Ordens & Histórico", "Lotes, o que já saiu e correção. Para PAGAR, use «Pessoas & Folha» ou «Contas & Impostos».", [
        ("pagamentos-auditoria", "Auditoria de pagamentos"),
        ("ordens-pagamento", "Ordens de pagamento"), ("montar-ordem", "Montar ordem"),
        ("aprovar-ordem", "Aprovar ordem (OTP)"), ("executar-no-app", "Executar no app"),
        ("pagamentos-inter", "Pagamentos Inter"), ("marcar-pago-externo", "Pago por fora"),
        ("cancelar-pagamento", "Cancelar pagto"), ("audit-log", "Audit log")]),
    ("g-bancos", "Bancos & Conciliação", "Saldos, extratos e conciliação", [
        ("saldos", "Saldos"), ("contas-bancarias", "Contas"), ("inter", "Banco Inter"),
        ("cora", "Banco Cora"), ("banking", "Extrato"), ("pix-recebidos", "PIX recebidos"),
        ("sincronizar-pix", "Sincronizar PIX"), ("devolver-pix", "Devolver PIX"),
        ("ajustar-saldo", "Ajustar saldo"),
        ("conciliacao-bancaria", "Conciliação (extrato)"), ("conciliar-auto", "Rodar conciliação"), ("conciliar-classificados", "2ª passada (classificados)"), ("classificar-saidas", "Classificar saídas"), ("corrigir-classificacao", "Corrigir classificação"),
        ("conciliacao-consolidada", "Consolidado por mês"), ("consolidacao-grupo", "Consolidação multi-CNPJ"),
        ("conciliacao-por-liquido", "Por líquido (NFS-e×banco)"), ("aplicar-conciliacao-liquido", "Aplicar conciliação"),
        ("conciliacao", "Conciliação de folha"), ("inter-pagamentos", "Inter (pagtos)"), ("just-registrar", "Justificar transação"), ("just-classificar", "Classificar transações"), ("just-alertar", "Alertar pendências")]),
    ("g-fiscal", "Fiscal & Contábil", "Notas, guias e contabilidade", [
        ("fiscal", "Fiscal"), ("nfse-entrada", "NFS-e entrada"),
        ("plano-contas", "Plano de contas"), ("lancamentos", "Lançamentos"),
        ("balancete", "Balancete"), ("balanco-patrimonial", "Balanço Patrimonial"),
        ("indices-liquidez", "Liquidez & endividamento"), ("dre-caixa", "DRE por caixa"),
        ("dre-analise-vertical", "DRE — análise vertical"), ("dre-consolidado", "DRE consolidado (grupo)"),
        ("apuracao-resultado", "Apuração IRPJ/CSLL"), ("provisoes-trabalhistas", "Provisões (férias/13º)"),
        ("postar-provisoes", "Postar provisões"), ("postar-inss", "Postar INSS"),
        ("pareamento-portte", "Pareamento Portte"), ("pareamento-tributos", "Pareamento tributos"), ("das-eletronica", "Tributos Eletrônica (LR)"), ("das-patrimonial", "DAS Patrimonial (Simples)"),
        ("contabilidade", "Extrato categorizado"), ("cancelar-boleto", "Cancelar boleto"),]),
    ("g-custos", "Custos & Orçamento", "Custos, custeio, precificação e orçamento", [
        ("rentabilidade", "Rentabilidade por contrato"), ("resultado-cnpj", "Resultado por CNPJ"),
        ("custos", "Custos"), ("custeio-abc", "Custeio ABC"),
        ("custeio-contratos", "Margem por contrato"), ("custeio", "Simulador CCT"), ("custeio-cct", "Custeio CCT"),
        ("precificacao", "Precificação"), ("orcamentos", "Orçamentos"),
        ("orcado-realizado", "Orçado × Realizado"), ("pricing-calcular", "Calcular preço"), ("custo-registrar", "Registrar custo de contrato"), ("custo-recorrente-novo", "Novo custo recorrente"), ("custos-recorrentes-lista", "Custos recorrentes"), ("orcamento-kv", "Orçado do mês")]),
    ("g-cadastros", "Cadastros & Suprimentos", "Fornecedores, contratos, compras e estoque", [
        ("fornecedores", "Fornecedores"), ("fornecedores-categoria", "Fornecedores por categoria"), ("contratos", "Contratos"),
        ("compras-reais", "Compras"), ("compras", "Compras (NF-e)"),
        ("estoque-real", "Estoque"), ("estoque", "Estoque (NF-e)"), ("estoque-saida", "Registrar saída de estoque"), ("estoque-movimentos", "Movimentos de estoque"), ("estoque-resumo", "Resumo do estoque"), ("beneficiarios-seed", "Semear beneficiários")]),
]


def montar_grupos(out: dict) -> None:
    """Compõe os grupos a partir das telas JÁ montadas em out e stub-a as antigas (redirect).
    Ordem importa: capturar as referências ANTES de stubar."""
    novos = {}
    for gid, titulo, sub, tabs in GRUPOS:
        novos[gid] = grp(titulo, sub, [(tid, lbl, out.get(tid)) for tid, lbl in tabs])
    for gid, _t, _s, tabs in GRUPOS:
        for tid, _l in tabs:
            if tid in out:
                out[tid] = moved(gid, tid)
    out.update(novos)
