"""Escopo das ferramentas do conector MCP — por ASSUNTO.

Por que existe: o Hermes manda o catálogo INTEIRO no prompt. Medido em 23/08/2026, isso
são 250 ferramentas e ~43 mil tokens de contexto para responder "ok". Para a DeepSeek dá
cerca de um centavo por chamada; para um modelo local de 4B, 43 mil tokens de catálogo é
inviável — e mesmo nos modelos grandes, listas enormes derrubam a precisão da escolha.

Nenhum assunto passa de 24% do catálogo: escopar corta de 76% a 95% do contexto.

Manutenção: ferramenta nova entra no grupo dela AQUI. Ferramenta fora de qualquer grupo
continua sendo servida (nunca some por esquecimento) — `escopos_da_tool` devolve "geral".
"""

ESCOPOS: dict[str, list[str]] = {
    # ⭐ PESSOAS (11/09/2026) — o escopo do HERMES para o problema do funcionário.
    #
    # Nasce da decisão do Jordan: *"quero o Hermes realmente inteligente... tudo funcione
    # para coleta e resolução de problemas"*. O que ele precisa enxergar é o TRABALHO de uma
    # pessoa — ponto, escala, posto, ocorrência, comunicado — e nada além disso.
    #
    # O que está DE FORA é a definição do escopo, e cada ausência é deliberada:
    #   · `fechar_folha`, `calcular_folha_todos`, `calcular_holerite`, `exportar_folha_dominio`,
    #     `calcular_verbas_rescisorias` — fechar o mês e calcular pagamento não é triagem.
    #   · `fechar_mes_ponto` — fecha a apuração; batida nova deixa de entrar.
    #   · `aprovar_ferias`, `solicitar_ferias`, `concluir_admissao` — decisão sobre a vida
    #     contratual de alguém.
    #   · nada de CRM, PIX, proposta, contrato ou nota: o assunto aqui é gente trabalhando.
    #
    # `revisar_justificativa_ponto` ENTRA de propósito, e entra como `propose` (subiu de
    # `read` em 11/09, ver tool_risk_manifest): o Hermes monta o caso — quem, que dia, o que a
    # pessoa disse, o que o espelho mostra — e o DP aprova na Central. É o desenho da casa:
    # quem aprova não é quem pede. `propor_comunicado` e `enviar_whatsapp` entram pela mesma
    # porta: viram pedido, nunca ação.
    "pessoas": [
        # ponto — o núcleo
        "ponto_dashboard",
        "justificativas_ponto_pendentes",
        "revisar_justificativa_ponto",
        "espelho_ponto",
        "painel_espelho_ponto",
        "baixar_espelho_ponto_pdf",
        "status_fechamento_ponto",
        "banco_horas",
        "presenca_ao_vivo",
        # quem é a pessoa e onde ela trabalha
        "buscar_funcionario",
        "buscar_funcionario_por_cpf",
        "obter_funcionario",
        "ficha_funcionario",
        "listar_funcionarios",
        "estatisticas_funcionarios",
        "listar_beneficios_funcionario",
        # escala, posto e cobertura
        "listar_escalas",
        "colaboradores_sem_escala",
        "grade_do_posto",
        "grade_postos",
        "listar_postos",
        "estatisticas_postos",
        "listar_alocacoes",
        "alocacoes_vigentes",
        "funcionarios_disponiveis_posto",
        "substituicoes_pendentes",
        "listar_substituicoes",
        "substitutos_disponiveis",
        "dashboard_operacional",
        "listar_ocorrencias",
        # saúde ocupacional e férias — leitura, para não pedir batida de quem está afastado
        "asos_vencendo",
        "funcionarios_sem_aso",
        "listar_ferias",
        "ferias_funcionario",
        "saldo_ferias",
        # falar com a pessoa: os dois viram PEDIDO na Central, nunca envio direto
        "comunicados_nao_lidos",
        "listar_comunicados",
        "propor_comunicado",
        "enviar_whatsapp",
        # como o próprio José Luís está indo
        "metricas_jose_luis",
        "status_whatsapp",
    ],
    "comercial": [
        # aceitar_proposta NÃO entra aqui: gera COMISSÃO e CONTRATO. Fica sem grupo, e
        # com o filtro fail-closed abaixo isso significa "não servida em conector
        # escopado" — sai do alcance do Hermes até a F1 ter aprovação de terceiro.
        "proposta_da_oportunidade",
        "recusar_proposta",
        "nova_versao_proposta",
        "adicionar_achados_visita",
        "anotar_cliente",
        "arquivar_deal",
        "assumir_negociacao",
        "atualizar_cliente",
        "atualizar_estagio_deal",
        "atualizar_proposta",
        "baixar_proposta_pdf",
        "baixar_relatorio_comercial_pdf",
        "briefing_executivo",
        "buscar_cliente_por_cnpj",
        "comunicados_nao_lidos",
        "confirmar_reuniao",
        "consultar_auditoria",
        "consultar_forecast",
        "consultar_funil",
        "consultar_parametros_precificacao",
        "consultar_pipeline",
        "consultar_viabilidade_contratacao",
        "consultor_ceo",
        "consultor_cfo",
        "consultor_comercial",
        "consultor_dp",
        "consultor_fiscal",
        "consultor_ged",
        "consultor_juridico",
        "consultor_operacional",
        "criar_cliente",
        "criar_lead",
        "criar_oportunidade",
        "criar_proposta",
        "criar_propostas_lote",
        "criar_relatorio_visita",
        "criar_tarefa",
        "definir_parametros_precificacao",
        "devolver_negociacao",
        "diagnostico_ciclo",
        "enviar_nps",
        "enviar_proposta",
        "enviar_proposta_completa",
        "enviar_proposta_whatsapp",
        "enviar_whatsapp",
        "excluir_proposta",
        "followup_em_lote",
        "followup_whatsapp",
        "gerar_atestado_pdf",
        "gerar_copy",
        "gerar_ordem_servico_pdf",
        "gerar_pdf_visita",
        "gerar_plano_estrategico",
        "gerar_recibo_pdf",
        "historico_followup",
        "inscrever_em_sequencia",
        "inscrever_lead_em_sequencia",
        "leads_frios",
        "listar_campanhas",
        "listar_clientes",
        "listar_comunicados",
        "listar_deals",
        "listar_documentos",
        "listar_followups_pendentes",
        "listar_leads",
        "listar_precos_funcao",
        "listar_propostas",
        "listar_relatorios_visita",
        "listar_reunioes",
        "listar_sequencias",
        "listar_substituicoes",
        "marcar_deal_perdido",
        "marcar_proposta_enviada",
        "margem_por_condominio",
        "metricas_jose_luis",
        "montar_relatorio_visita",
        "negociacoes_pendentes",
        "obter_cliente",
        "obter_deal",
        "obter_relatorio_visita",
        "painel_negociacoes",
        "presenca_ao_vivo",
        "propor_comunicado",
        "reativar_lead",
        "registrar_feedback",
        "registrar_lead_da_visita",
        "registrar_optout_whatsapp",
        "registrar_resposta_followup",
        "relatorio_comercial",
        "resumo_comercial",
        "resumo_executivo",
        "resumo_financeiro",
        "resumo_nps",
        "runway_ao_vivo",
        "simular_fechamento",
        "simular_preco",
        "status_dominio",
        "status_whatsapp",
        "substituicoes_pendentes",
        "substitutos_disponiveis",
        "sugerir_cross_sell",
        "sugerir_reuniao",
        "ver_ficha_cliente",
    ],
    "dp": [
        "aprovar_ferias",
        "asos_vencendo",
        "baixar_espelho_ponto_pdf",
        "baixar_holerite_pdf",
        "baixar_recibo_vt_vr_pdf",
        "banco_horas",
        "buscar_funcionario",
        "buscar_funcionario_por_cpf",
        "calcular_folha_todos",
        "calcular_holerite",
        "calcular_verbas_rescisorias",
        "concluir_admissao",
        "divergencias_folha_pagamentos",
        "esocial_timeline_funcionario",
        "espelho_ponto",
        "estatisticas_funcionarios",
        "exportar_folha_dominio",
        "fechar_folha",
        "fechar_mes_ponto",
        "ferias_funcionario",
        "ficha_funcionario",
        "folha_dashboard",
        "funcionarios_disponiveis_posto",
        "funcionarios_sem_aso",
        "justificativas_ponto_pendentes",
        "listar_admissoes",
        "listar_beneficios_funcionario",
        "listar_ferias",
        "listar_funcionarios",
        "listar_rescisoes",
        "listar_rubricas_folha",
        "obter_funcionario",
        "painel_espelho_ponto",
        "ponto_dashboard",
        "resumo_folha",
        "revisar_justificativa_ponto",
        "saldo_ferias",
        "solicitar_ferias",
        "status_fechamento_ponto",
    ],
    "financeiro": [
        "baixar_comprovante_pagamento_pdf",
        "cfo_panorama",
        "cfo_perguntar",
        "det_comunicacoes",
        "gerar_apresentacao",
        "gerar_lote_diarias_mes",
        "gerar_orcamento",
        "inter_extrato_resumo",
        "inter_saldo",
        "lancar_diaria",
        "listar_beneficiarios_pix",
        "listar_cobrancas_inter",
        "listar_pagamentos_inter",
        "listar_reembolsos",
        "lote_diaristas",
        "pix_recebidos",
        "previsao_custos_mensais",
        "propor_pagamento",
        "reembolsos_pendentes_aprovacao",
        "reembolsos_prontos_pagamento",
        "registrar_custo_recorrente",
        "resumo_diarias",
        "teto_diario_pagamentos",
    ],
    "fiscal": [
        "alertas_certificados",
        "alertas_obrigacoes",
        "cadastrar_whatsapp_cliente",
        "calendario_obrigacoes",
        "contabil_grupo",
        "dashboard_campo",
        "dashboard_clima",
        "dashboard_fiscal",
        "dashboard_fiscal_grupo",
        "dashboard_nfse",
        "dashboard_operacional",
        "dashboard_ordens_servico",
        "debitos_ecac",
        "diarias_cadastros",
        "diaristas_a_cadastrar",
        "esocial_espelho_resumo",
        "gaps_esocial",
        "guias_fgts",
        "listar_certidoes",
        "listar_empresas",
        "listar_eventos_esocial",
        "listar_nfse",
        "listar_nfse_entrada",
        "monitor_integracoes_gov",
        "pendencias_simples",
        "rentabilidade_grupo",
        "resumo_ecac",
        "resumo_nfse_entrada",
        "situacao_fiscal_ecac",
        "sst_dashboard",
        "status_certidoes",
        "status_dctfweb",
        "status_fgts_digital",
        "status_simples_nacional",
    ],
    "ged": [
        "buscar_documento",
        "consultar_kit",
        "consultar_kits",
        "cronograma_kit",
        "excluir_documento",
        "montar_kit_completo",
        "registrar_evento_kit",
        "status_coleta",
    ],
    "governanca": [
        "definir_meta_mensal",
        "excluir_campanha",
        "excluir_documento_crm",
        "expurgar_documentos_teste",
        "upload_asset",
    ],
    "juridico": [
        "abrir_assinatura_contrato",
        "analisar_processo_juridico",
        "arquivar_contrato",
        "assinar_contrato_empresa",
        "ativar_contrato",
        "atualizar_contrato",
        "baixar_contrato_pdf",
        "briefing_contrato_novo",
        "consultar_juridico",
        "criar_contrato",
        "criar_contrato_por_modelo",
        "definir_meta_contratos_mes",
        "dossie_juridico",
        "enviar_link_assinatura",
        "gerar_aditivo_pdf",
        "gerar_contrato_por_modelo",
        "gerar_parecer_juridico",
        "listar_contratos",
        "obter_contrato",
        "painel_juridico",
        "status_assinatura_contrato",
    ],
    "operacional": [
        "alocacoes_vigentes",
        "colaboradores_sem_escala",
        "estatisticas_postos",
        "grade_do_posto",
        "grade_postos",
        "listar_alocacoes",
        "listar_escalas",
        "listar_ocorrencias",
        "listar_ordens_servico",
        "listar_postos",
        "listar_visitas_campo",
        "relatorio_cobertura",
    ],
    "rh": [
        "beneficios_cct",
        "estoque_epi",
        "listar_candidatos",
        "listar_entrevistas",
        "listar_vagas",
        "status_pcmso",
        "status_ppra",
        "tabela_salarial_cct",
        "vagas_abertas",
    ],
}

def escopos_da_tool(nome: str) -> str:
    """Grupo de uma ferramenta. Sem grupo devolve "" — e, num conector ESCOPADO, isso
    significa NÃO SERVIDA.

    A versão anterior devolvia "geral" com a intenção de que ferramenta nova nunca sumisse
    por esquecimento. A intenção era boa e o efeito era o contrário do que um filtro de
    segurança deve fazer: em 23/08/2026 quatro tools recém-criadas — uma delas gerando
    COMISSÃO e CONTRATO — escaparam do filtro e chegaram ao agente porque ninguém as tinha
    mapeado ainda. Fail-open para o caso desconhecido é como se perde uma parede.

    Agora o esquecimento custa uma ausência visível (o log diz quantas ficaram de fora), não
    uma exposição silenciosa.
    """
    for g, tools in ESCOPOS.items():
        if nome in tools:
            return g
    return ""


def tools_do_escopo(escopo: str | None) -> set[str] | None:
    """Nomes servidos num escopo. `None`/"tudo" devolve None = catálogo inteiro.

    Aceita vários assuntos separados por vírgula (ex.: "dp,fiscal") — um bot de DP que
    também consulta guia precisa dos dois, e forçá-lo ao catálogo inteiro anularia o corte.
    """
    if not escopo or escopo.strip().lower() in ("", "tudo", "all", "*"):
        return None
    pedidos = {p.strip().lower() for p in escopo.split(",") if p.strip()}
    fora = pedidos - set(ESCOPOS) - {"geral"}
    if fora:
        raise ValueError(
            f"escopo(s) desconhecido(s): {', '.join(sorted(fora))}. "
            f"Disponíveis: {', '.join(sorted(ESCOPOS))}")
    nomes: set[str] = set()
    for p in pedidos:
        nomes |= set(ESCOPOS.get(p, []))
    return nomes
