"""F0 — composição dos 7 grupos do financeiro (fundação tabs). Mapeia TODA tela antiga
para (grupo, aba); o oráculo da fase acusa órfãos (tela fora de grupo) — nada se perde.
Prefixo _ = o discovery de builders pula este arquivo (é helper, não módulo)."""

from modules.operacional.controllers.redesign_data_controller import grp, moved

GRUPOS = [
    (
        "g-visao",
        "Visão Geral",
        "Resumo executivo do financeiro",
        [
            ("cockpit", "Cockpit"),
            ("dashboard", "Resumo"),
            ("fluxo-caixa", "Fluxo de Caixa"),
            ("fluxo-caixa-agenda", "Agenda de caixa (por dia)"),  # dgx t4
            ("projecao", "Projeção & Insights"),
            ("dre-inline", "DRE"),
            ("indicadores", "Indicadores DSO/DPO"),
            ("tendencias", "Tendências"),
            ("raio-x", "Raio-X"),
            ("cfo", "CFO IA"),
            ("cfo-perguntar", "Perguntar ao CFO"),
            ("cfo-perguntar-arquivo", "Perguntar com anexo"),
            ("cashflow-sync", "Sincronizar fluxo de caixa"),
            ("agentes", "Agentes"),
            ("relatorios", "Relatórios"),
            ("fluxo-resumo", "Resumo do período"),
            ("fluxo-tendencia", "Tendência mensal"),
            ("fluxo-categorias", "Saídas por categoria"),
            ("fluxo-fornecedores", "Saídas por fornecedor"),
            ("relatorio-financeiro", "Relatórios em PDF/Excel"),  # dgx v5
        ],
    ),
    (
        "g-receber",
        "Receber",
        "Contas a receber, cobrança e faturamento",
        [
            ("contas-receber", "Contas a Receber"),
            ("nfse-a-receber", "NFS-e × a receber"),
            ("gerar-contas-de-nfse", "Gerar das NFS-e"),
            ("cobrancas", "Cobranças"),
            ("regua", "Régua"),
            ("fila-cobranca", "Fila de cobrança"),
            ("registrar-cobranca", "Registrar cobrança"),
            ("cobranca-email", "Cobrança por e-mail"),  # dgx t4
            ("recorrencia", "Recorrência (MRR)"),
            ("gerar-cobrancas", "Gerar cobranças"),
            ("boletos", "Boletos"),
            ("emitir-boleto", "Emitir boleto"),
            ("cobrar-pix", "Cobrar PIX"),
            ("faturamento", "Faturamento"),
            ("clientes", "Clientes"),
            ("gerar-recebiveis", "Gerar do mês"),
            ("baixar-recebivel", "Dar baixa"),
            ("registrar-conta-receber", "Registrar"),
            ("billing-contrato-ativado", "Faturar contrato ativado"),
            ("recibos", "Recibos de venda"),  # dgx f11
            ("recibo-novo", "Emitir recibo"),  # dgx f11
            ("faturas", "Faturas"),  # dgx w2
            ("fatura-nova", "Nova fatura"),  # dgx w2
            ("fatura-itens", "Itens das faturas"),  # dgx w2
            ("faturas-copiar-lote", "Copiar faturas em lote"),  # dgx w2
        ],
    ),
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
    (
        "g-pagar",
        "Pagar",
        "O que a empresa deve. Diaristas, VT/VR e folha estão em «Pessoas & Folha» · boleto, PIX e impostos em «Contas & Impostos» · lotes e o que já saiu em «Ordens & Histórico».",
        [
            ("contas-pagar", "Contas a Pagar"),
            ("registrar-conta-pagar", "Registrar conta"),
            ("registrar-obrigacoes", "Gerar das NFS-e/folha/guias"),
            ("payables-auto-criar", "Criar pagáveis das NFS-e"),
            ("baixar-pagavel", "Dar baixa"),
            ("fila-aprovacao", "Aprovação"),
            ("pagaveis-recorrentes-gerar", "Gerar recorrentes"),
            ("parcelas-pendentes", "Parcelas pendentes"),
        ],
    ),
    (
        "g-pagar-pessoas",
        "Pessoas & Folha",
        "Diaristas, VT/VR e folha — quem recebe da empresa. Contas e impostos ficam em «Contas & Impostos»; a lista de dívidas, em «Pagar».",
        [
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
            ("pagamentos-pj", "Folha PJ"),
            ("pagar-folha-pj", "Pagar folha PJ"),
            ("pagar-folha-clt", "Pagar folha CLT"),
            ("documentos-diaristas", "Recibos dos diaristas"),
            ("diaristas-a-cadastrar", "Diaristas a cadastrar"),
            ("diarias-sobrepostas", "Sobrepostas à folha CLT"),
            ("folha-pj-programar", "Programar folha PJ"),
            ("pensionistas", "Pensionistas"),  # dgx f11
            ("pensionista-novo", "Cadastrar pensionista"),  # dgx f11
        ],
    ),
    (
        "g-pagar-contas",
        "Contas & Impostos",
        "Boleto, tributo e transferência avulsa (gate OTP). Pagar pessoas fica em «Pessoas & Folha».",
        [
            ("pagar-boleto", "Pagar boleto"),
            ("enviar-pix", "PIX / Transferir"),
            ("transferir-ted", "TED"),
            ("pagar-darf", "DARF"),
            ("pagar-gps", "GPS / INSS"),
            ("contas-fixas", "Contas fixas"),  # dgx f11
            ("conta-fixa-nova", "Nova conta fixa"),  # dgx f11
            ("contas-fixas-gerar", "Gerar títulos do mês"),  # dgx f11
        ],
    ),
    (
        "g-pagar-ordens",
        "Ordens & Histórico",
        "Lotes, o que já saiu e correção. A sequência da folha é: «1. Gerar parcelas 40/60» → «2. Conferir e ajustar» → «Montar ordem» → «Aprovar (OTP)» → «Executar no app».",
        [
            # ⭐ 21/09/2026 — `gerar-parcelas` ENTROU AQUI, e a falta dela era o defeito.
            # O Jordan foi pagar os 40% da folha e não achou o caminho, nem no Financeiro nem no
            # DP. Medido: das 150 telas que este módulo serve, 149 estão em alguma aba e UMA não
            # estava em nenhuma — exatamente `gerar-parcelas`, o PRIMEIRO passo, o que cria as
            # linhas de 40% e 60% a partir dos holerites. Montar, aprovar e executar tinham
            # porta; a entrada não tinha. Capacidade sem botão no lugar mais caro possível.
            # Fica como PRIMEIRA aba, com o número no rótulo, para a ordem do fluxo ser legível
            # sem ninguém precisar saber de cor.
            ("gerar-parcelas", "1. Gerar parcelas 40/60"),
            # ⭐ 22/09/2026 — a MESMA lição de novo, um degrau adiante. Gerar tinha porta;
            # CONFERIR e AJUSTAR o que foi gerado, não. Segurar uma pessoa do lote (o caso
            # do Geilson) só existia por UPDATE no banco — capacidade que vive no terminal
            # não existe para o dono. Entra logo depois de gerar, que é quando se confere.
            ("parcelas-folha", "2. Conferir e ajustar"),
            ("parcela-incluir", "Incluir pessoa"),
            ("ordens-pagamento", "Ordens de pagamento"),
            ("montar-ordem", "Montar ordem"),
            ("aprovar-ordem", "Aprovar ordem (OTP)"),
            ("executar-inter", "Executar pelo Inter"),
            ("relatorio-pago-pdf", "Relatório em PDF (timbrado)"),
            ("relatorio-pago", "Conferir na tela"),
            ("avisar-pagamento", "Avisar quem recebeu"),
            ("executar-no-app", "Executar no app (Cora)"),
            ("pagamentos-inter", "Pagamentos Inter"),
            ("marcar-pago-externo", "Pago por fora"),
            ("cancelar-pagamento", "Cancelar pagto"),
            ("audit-log", "Audit log"),
            ("pagamentos-auditoria", "Auditoria de pagamentos"),
        ],
    ),
    (
        "g-bancos",
        "Bancos & Conciliação",
        "Saldos, extratos e conciliação",
        [
            ("saldos", "Saldos"),
            ("contas-bancarias", "Contas"),
            ("inter", "Banco Inter"),
            ("cora", "Banco Cora"),
            ("banking", "Extrato"),
            ("pix-recebidos", "PIX recebidos"),
            ("sincronizar-pix", "Sincronizar PIX"),
            ("devolver-pix", "Devolver PIX"),
            ("ajustar-saldo", "Ajustar saldo"),
            ("conciliacao-bancaria", "Conciliação (extrato)"),
            ("conciliar-auto", "Rodar conciliação"),
            ("importar-ofx", "Importar OFX"),  # dgx t4
            ("conciliar-classificados", "2ª passada (classificados)"),
            ("classificar-saidas", "Classificar saídas"),
            ("corrigir-classificacao", "Corrigir classificação"),
            ("conciliacao-consolidada", "Consolidado por mês"),
            ("consolidacao-grupo", "Consolidação multi-CNPJ"),
            ("conciliacao-por-liquido", "Por líquido (NFS-e×banco)"),
            ("aplicar-conciliacao-liquido", "Aplicar conciliação"),
            ("conciliacao", "Conciliação de folha"),
            ("inter-pagamentos", "Inter (pagtos)"),
            ("just-registrar", "Justificar transação"),
            ("just-classificar", "Classificar transações"),
            ("just-alertar", "Alertar pendências"),
        ],
    ),
    (
        "g-fiscal",
        "Fiscal & Contábil",
        "Notas, guias e contabilidade",
        [
            ("fiscal", "Fiscal"),
            ("nfse-entrada", "NFS-e entrada"),
            ("plano-contas", "Plano de contas"),
            ("lancamentos", "Lançamentos"),
            ("balancete", "Balancete"),
            ("balanco-patrimonial", "Balanço Patrimonial"),
            ("indices-liquidez", "Liquidez & endividamento"),
            ("dre-caixa", "DRE por caixa"),
            ("dre-analise-vertical", "DRE — análise vertical"),
            ("apuracao-resultado", "Apuração IRPJ/CSLL"),
            ("lalur-revisao", "Revisão do LALUR"),
            ("provisoes-trabalhistas", "Provisões (férias/13º)"),
            ("postar-provisoes", "Postar provisões"),
            ("postar-inss", "Postar INSS"),
            ("pareamento-portte", "Pareamento Portte"),
            ("pareamento-tributos", "Pareamento tributos"),
            ("das-eletronica", "Tributos Eletrônica (LR)"),
            ("das-patrimonial", "DAS Patrimonial (Simples)"),
            ("contabilidade", "Extrato categorizado"),
            ("cancelar-boleto", "Cancelar boleto"),
            ("dre-consolidado", "DRE consolidado (grupo)"),
            ("codigos-servico", "Códigos de serviço (LC 116)"),  # dgx f11
            ("codigo-servico-novo", "Novo código de serviço"),  # dgx f11
            ("cfop-natureza", "CFOP / Natureza"),  # dgx f11
            ("cfop-novo", "Novo CFOP"),  # dgx f11
        ],
    ),
    (
        "g-custos",
        "Custos & Orçamento",
        "Custos, custeio, precificação e orçamento",
        [
            ("rentabilidade", "Rentabilidade por contrato"),
            ("resultado-cnpj", "Resultado por CNPJ"),
            ("custos", "Custos"),
            ("custeio-abc", "Custeio ABC"),
            ("custeio-contratos", "Margem por contrato"),
            ("custeio", "Simulador CCT"),
            ("custeio-cct", "Custeio CCT"),
            ("precificacao", "Precificação"),
            ("orcamentos", "Orçamentos"),
            ("orcado-realizado", "Orçado × Realizado"),
            ("pricing-calcular", "Calcular preço"),
            ("custo-registrar", "Registrar custo de contrato"),
            ("custo-recorrente-novo", "Novo custo recorrente"),
            ("custos-recorrentes-lista", "Custos recorrentes"),
            ("orcamento-kv", "Orçado do mês"),
            ("orcamento-vs-realizado", "Análise orçamentária (por centro)"),  # dgx f11
            ("orcamento-centro-novo", "Lançar orçamento"),  # dgx f11
            ("comissoes-fechamento", "Fechamento de comissões"),  # dgx f11
            ("comissoes-fechar", "Fechar período"),  # dgx f11
            ("comissoes-conta-gerada", "Comissões → conta a pagar"),  # dgx t4
            ("centros-custo", "Centros de custo (árvore)"),  # dgx v5
            ("centro-custo-novo", "Novo centro de custo"),  # dgx v5
            ("centro-custo-categoria", "Ligar categoria a um centro"),  # dgx v5
        ],
    ),
    (
        "g-cadastros",
        "Cadastros & Suprimentos",
        "Fornecedores, contratos, compras e estoque",
        [
            ("fornecedores", "Fornecedores"),
            ("fornecedores-categoria", "Fornecedores por categoria"),
            ("contratos", "Contratos"),
            ("compras-reais", "Compras"),
            ("compras", "Compras (NF-e)"),
            ("estoque-real", "Estoque"),
            ("estoque", "Estoque (NF-e)"),
            ("estoque-saida", "Registrar saída de estoque"),
            ("beneficiarios-seed", "Semear beneficiários"),
            ("estoque-movimentos", "Movimentos de estoque"),
            ("estoque-resumo", "Resumo do estoque"),
            ("condicoes-pagamento", "Condições de pagamento"),  # dgx f11
            ("condicao-pagamento-nova", "Nova condição"),  # dgx f11
            ("formas-pagamento", "Formas de pagamento"),  # dgx v5
            ("forma-pagamento-nova", "Nova forma de pagamento"),  # dgx v5
        ],
    ),
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
