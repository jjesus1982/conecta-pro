"""Manifesto de risco das tools MCP (fail-closed).

Classes:
  read       🟢 consulta/análise, zero mudança de estado — Hermes usa auto
  write_low  🔵 interno reversível, sem efeito externo em dinheiro/gente — auto
  propose    🟡 cria PENDENTE que só humano executa com OTP/aprovação
  (🔴 executar dinheiro/legal/operacional NÃO aparece aqui — fica fora de server.py)

Regra: toda @mcp.tool de server.py DEVE ter entrada aqui, senão o lint quebra o build.
"""

VALID_CLASSES = {"read", "write_low", "propose"}

TOOL_RISK: dict[str, str] = {
    # --- 11/09/2026: evolução da camada MCP (relatório de campo do Cowork) ---
    # ping e mapa: não tocam em dado do negócio, só em saúde e catálogo.
    "ping_conecta_pro": "read",
    "conecta_pro_capabilities": "read",
    # modelos de contrato: ler e VALIDAR são inócuos; validar não grava — é ensaio.
    "listar_modelos_contrato": "read",
    "validar_modelo_contrato": "read",
    # ⚠️ criar modelo é `propose`, não `write_low`: o modelo define o TEXTO JURÍDICO de
    # todos os contratos futuros daquele tipo e o CNPJ que emite. Errar aqui não estraga um
    # registro — estraga todo instrumento que nascer dele, inclusive os já assinados sob
    # aquela redação. É a definição de decisão que precisa de humano.
    "criar_modelo_contrato": "propose",
    # vincular liga um contrato a um modelo e faz o contrato herdar o tipo de serviço, que
    # decide o CNPJ emitente. Muda qual empresa assina — não é escrita de rotina.
    "vincular_modelo_ao_contrato": "propose",
    # anexo entra no registro do cliente e vira a versão que alguém pode assinar.
    "anexar_documento": "write_low",
    "listar_documentos_da_entidade": "read",
    "baixar_documento": "read",
    # Editar a fôrma muda o que sairá em TODOS os contratos pendurados nela — e trocar
    # `tipo` troca o CNPJ que assina. Mesma classe de `criar_modelo_contrato`.
    "atualizar_modelo_contrato": "propose",
    # cálculo puro: não grava, não envia. É o que substitui a planilha fora do ERP.
    "listar_aprovacoes_pendentes": "read",
    "pendencias_acionaveis": "read",
    "procedencia_da_proposta": "read",
    # grava um ACEITE de risco comercial — não sai da empresa, mas é decisão registrada
    # com nome. `write_low` diz a verdade: escreve, e o que escreve é trilha interna.
    "aceitar_estimativa_da_proposta": "write_low",
    "orcamento_por_natureza": "read",
    "contexto_cliente": "read",
    # jobs: consultar status e resultado é leitura. DISPARAR não é — o job executa a
    # ferramenta alvo com as permissões dela, e o disparo é `propose` porque o que roda ali
    # pode ser escrita. Classificar o disparo como `read` seria uma porta dos fundos:
    # "não escrevo, só mando outro escrever".
    # O disparador em si não faz nada: ele aplica, contra a ferramenta INTERNA, as mesmas
    # duas paredes do middleware (gate propose + identidade). `propose` aqui bloquearia o
    # recurso inteiro para sempre; a classe que governa é a da ferramenta despachada.
    "executar_em_segundo_plano": "read",
    # Ensaiar NÃO grava — a interceptação é no único ponto por onde o MCP escreve. E, como
    # o despachante de segundo plano, aplica as duas paredes contra a ferramenta interna.
    "changelog_mcp": "read",
    # `no_sandbox` ESCREVE — só que num banco descartável. `read` seria mentira na
    # etiqueta; `propose` mataria o recurso. `write_low` diz a verdade: grava, e o que
    # grava não tem consequência fora do ensaio. As paredes da ferramenta interna valem.
    "no_sandbox": "write_low",
    "ensaiar": "read",
    "status_job": "read",
    "resultado_job": "read",

    # --- tools existentes (conector read-only) — todas "read" ---
    "adicionar_achados_visita": "write_low",
    "alertas_certificados": "read",
    "alertas_obrigacoes": "read",
    "alocacoes_vigentes": "read",
    "analisar_processo_juridico": "propose",
    "anotar_cliente": "write_low",
    "aprovar_ferias": "propose",
    "arquivar_contrato": "write_low",
    "arquivar_deal": "write_low",
    "asos_vencendo": "read",
    "assumir_negociacao": "write_low",
    "ativar_contrato": "propose",
    "atualizar_cliente": "write_low",
    # 18/09/2026 — §7: quem assina pelo cliente, gravado no cadastro (crm_contacts)
    "definir_representante_cliente": "write_low",
    "atualizar_contrato": "propose",
    "atualizar_estagio_deal": "write_low",
    "atualizar_proposta": "write_low",
    "baixar_comprovante_pagamento_pdf": "read",
    "baixar_contrato_pdf": "read",
    # emite documento e REGISTRA link público; não ativa contrato nem move dinheiro
    "gerar_contrato_por_modelo": "write_low",  # 🔵 renderiza PDF de rascunho; não assina
    "briefing_contrato_novo": "read",   # só pergunta, não grava nada
    # aceite cria COMISSÃO e CONTRATO: propor, nunca decidir
    "aceitar_proposta": "propose",           # 🟡
    "recusar_proposta": "write_low",         # 🔵 muda status + nota, reversível
    "nova_versao_proposta": "write_low",     # 🔵 preserva a anterior
    "proposta_da_oportunidade": "write_low", # 🔵 cria rascunho de proposta
    "criar_contrato_por_modelo": "write_low",  # 🔵 nasce `draft`, reversível, sem efeito externo
    "abrir_assinatura_contrato": "propose",  # 🟡 cria solicitação PENDENTE — humano assina
    "assinar_contrato_empresa": "propose",  # 🟡 firma instrumento real: só Jordan/Pyetra
    "enviar_link_assinatura": "propose",  # 🟡 sai do sistema (e-mail ao cliente)
    "status_assinatura_contrato": "read",
    "baixar_espelho_ponto_pdf": "read",
    "baixar_holerite_pdf": "read",
    "baixar_proposta_pdf": "read",
    "baixar_recibo_vt_vr_pdf": "read",
    "baixar_relatorio_comercial_pdf": "write_low",
    "banco_horas": "read",
    "beneficios_cct": "read",
    "buscar_cliente_por_cnpj": "read",
    "buscar_documento": "propose",
    "buscar_funcionario": "read",
    "buscar_funcionario_por_cpf": "read",
    "cadastrar_whatsapp_cliente": "write_low",
    "calcular_folha_todos": "propose",
    "calcular_holerite": "read",
    "calcular_verbas_rescisorias": "propose",
    "calendario_obrigacoes": "read",
    "cfo_panorama": "read",
    "cfo_perguntar": "read",
    "colaboradores_sem_escala": "read",
    "comunicados_nao_lidos": "read",
    "concluir_admissao": "propose",
    "confirmar_reuniao": "write_low",
    "consultar_auditoria": "read",
    "consultar_forecast": "read",
    "consultar_funil": "read",
    "consultar_juridico": "read",
    "consultar_kit": "read",
    "consultar_kits": "read",
    "consultar_parametros_precificacao": "read",
    "consultar_pipeline": "read",
    "contabil_grupo": "read",
    "criar_cliente": "write_low",
    "criar_contrato": "write_low",
    "criar_lead": "write_low",
    "criar_oportunidade": "write_low",
    "criar_proposta": "write_low",
    "criar_propostas_lote": "write_low",
    "criar_relatorio_visita": "write_low",
    "criar_tarefa": "write_low",
    "cronograma_kit": "read",
    "dashboard_campo": "read",
    "dashboard_clima": "read",
    "dashboard_fiscal": "read",
    "dashboard_fiscal_grupo": "read",
    "dashboard_nfse": "read",
    "dashboard_operacional": "read",
    "dashboard_ordens_servico": "read",
    "debitos_ecac": "read",
    "definir_meta_contratos_mes": "write_low",
    "definir_meta_mensal": "write_low",
    "definir_parametros_precificacao": "propose",
    "det_comunicacoes": "read",
    "devolver_negociacao": "write_low",
    "diagnostico_ciclo": "read",
    "diarias_cadastros": "read",
    "diaristas_a_cadastrar": "read",
    "divergencias_folha_pagamentos": "read",
    "dossie_juridico": "read",
    "enviar_nps": "propose",
    "enviar_proposta": "propose",
    "enviar_proposta_completa": "propose",
    "enviar_proposta_whatsapp": "propose",
    "enviar_whatsapp": "propose",
    "esocial_espelho_resumo": "read",
    "esocial_timeline_funcionario": "read",
    "espelho_ponto": "read",
    "estatisticas_funcionarios": "read",
    "estatisticas_postos": "read",
    "estoque_epi": "read",
    "excluir_campanha": "propose",
    "excluir_documento": "propose",
    "excluir_documento_crm": "write_low",
    "excluir_proposta": "write_low",
    "exportar_folha_dominio": "read",
    "expurgar_documentos_teste": "propose",
    "fechar_folha": "propose",
    "fechar_mes_ponto": "propose",
    "ferias_funcionario": "read",
    "ficha_funcionario": "read",
    "folha_dashboard": "read",
    "followup_em_lote": "propose",
    "followup_whatsapp": "propose",
    "funcionarios_disponiveis_posto": "read",
    "funcionarios_sem_aso": "read",
    "gaps_esocial": "read",
    "gerar_aditivo_pdf": "write_low",
    "gerar_apresentacao": "write_low",
    "gerar_atestado_pdf": "write_low",
    "gerar_copy": "write_low",
    "gerar_lote_diarias_mes": "propose",
    "gerar_orcamento": "write_low",
    "gerar_ordem_servico_pdf": "write_low",
    "gerar_parecer_juridico": "propose",
    "gerar_pdf_visita": "write_low",
    "gerar_plano_estrategico": "write_low",
    "gerar_recibo_pdf": "write_low",
    "grade_do_posto": "read",
    "grade_postos": "read",
    "guias_fgts": "read",
    "historico_followup": "read",
    "inscrever_em_sequencia": "propose",
    "inscrever_lead_em_sequencia": "propose",
    "inter_extrato_resumo": "read",
    "inter_saldo": "read",
    "justificativas_ponto_pendentes": "read",
    "lancar_diaria": "propose",
    "leads_frios": "read",
    "listar_admissoes": "read",
    "listar_alocacoes": "read",
    "listar_beneficiarios_pix": "read",
    "listar_beneficios_funcionario": "read",
    "listar_campanhas": "read",
    "listar_candidatos": "read",
    "listar_certidoes": "read",
    "listar_clientes": "read",
    "listar_cobrancas_inter": "read",
    "listar_comunicados": "read",
    "listar_contratos": "read",
    "listar_deals": "read",
    "listar_documentos": "read",
    "listar_empresas": "read",
    "listar_entrevistas": "read",
    "listar_escalas": "read",
    "listar_eventos_esocial": "read",
    "listar_ferias": "read",
    "listar_followups_pendentes": "read",
    "listar_funcionarios": "read",
    "listar_leads": "read",
    "listar_nfse": "read",
    "listar_nfse_entrada": "read",
    "listar_ocorrencias": "read",
    "listar_ordens_servico": "read",
    "listar_pagamentos_inter": "read",
    "listar_postos": "read",
    "listar_precos_funcao": "read",
    "listar_propostas": "read",
    "listar_reembolsos": "read",
    "listar_relatorios_visita": "read",
    "listar_rescisoes": "read",
    "listar_reunioes": "read",
    "listar_rubricas_folha": "read",
    "listar_sequencias": "read",
    "listar_substituicoes": "read",
    "listar_vagas": "read",
    "listar_visitas_campo": "read",
    "lote_diaristas": "read",
    "marcar_deal_perdido": "write_low",
    "marcar_proposta_enviada": "write_low",
    "metricas_jose_luis": "read",
    "monitor_integracoes_gov": "read",
    "montar_kit_completo": "propose",
    "montar_relatorio_visita": "write_low",
    "negociacoes_pendentes": "read",
    "obter_cliente": "read",
    "obter_contrato": "read",
    "obter_deal": "read",
    "obter_funcionario": "read",
    "obter_relatorio_visita": "read",
    "painel_espelho_ponto": "read",
    "painel_juridico": "read",
    "painel_negociacoes": "read",
    "pendencias_simples": "read",
    "pix_recebidos": "read",
    "ponto_dashboard": "read",
    "presenca_ao_vivo": "read",
    "previsao_custos_mensais": "read",
    "reativar_lead": "propose",
    "reembolsos_pendentes_aprovacao": "read",
    "reembolsos_prontos_pagamento": "read",
    "registrar_custo_recorrente": "propose",
    "registrar_evento_kit": "write_low",
    "registrar_lead_da_visita": "write_low",
    "registrar_optout_whatsapp": "write_low",
    "registrar_resposta_followup": "write_low",
    "relatorio_cobertura": "read",
    "relatorio_comercial": "read",
    "rentabilidade_grupo": "read",
    "resumo_comercial": "read",
    "resumo_diarias": "read",
    "resumo_ecac": "read",
    "resumo_executivo": "read",
    "resumo_financeiro": "read",
    "resumo_folha": "read",
    "resumo_nfse_entrada": "read",
    "resumo_nps": "read",
    "revisar_justificativa_ponto": "propose",
    "saldo_ferias": "read",
    "simular_fechamento": "read",
    "simular_preco": "read",
    "situacao_fiscal_ecac": "read",
    "solicitar_ferias": "propose",
    "sst_dashboard": "read",
    "status_certidoes": "read",
    "status_coleta": "read",
    "status_dctfweb": "read",
    "status_dominio": "read",
    "status_fechamento_ponto": "read",
    "status_fgts_digital": "read",
    "status_pcmso": "read",
    "status_ppra": "read",
    "status_simples_nacional": "read",
    "status_whatsapp": "read",
    "substituicoes_pendentes": "read",
    "substitutos_disponiveis": "read",
    "sugerir_cross_sell": "read",
    "sugerir_reuniao": "write_low",
    "tabela_salarial_cct": "read",
    "teto_diario_pagamentos": "read",
    "upload_asset": "write_low",
    "vagas_abertas": "read",
    "ver_ficha_cliente": "read",
    # --- Fase 5.1: consultores (🟢) ---
    "consultor_ceo": "read", "consultor_cfo": "read", "consultor_fiscal": "read",
    "consultor_dp": "read", "consultor_juridico": "read", "consultor_comercial": "read",
    "consultor_operacional": "read", "consultor_ged": "read",
    # --- Fase 5.1: ações ---
    "registrar_feedback": "write_low",   # 🔵
    "propor_pagamento": "propose",       # 🟡
    "propor_comunicado": "propose",      # 🟡
    # --- Fase 5.2a.4: quick-wins executivos (🟢 read, cross-domínio) ---
    "consultar_viabilidade_contratacao": "read",
    "briefing_executivo": "read",
    "runway_ao_vivo": "read",
    "margem_por_condominio": "read",
    # ── 11/09/2026 · A ETIQUETA PASSA A SER DERIVADA DO VERBO, NÃO AFIRMADA ──────────────
    # `backend/scripts/qa/checar_etiqueta_de_risco.py` comparou cada @mcp.tool com o método
    # HTTP que ela usa no ERP e achou 13 etiquetadas `read` que faziam PUT, PATCH ou DELETE.
    # `read` é justamente a classe que o `gate_propose` deixa passar SEM humano: era a parede
    # aberta exatamente onde deveria fechar. Reclassificadas, cada uma conferida no controller:
    #
    #   write_low (interno e REVERSÍVEL — conferido: os três DELETEs do CRM são SOFT):
    #     atualizar_estagio_deal · marcar_deal_perdido (PATCH de estágio, volta atrás)
    #     atualizar_proposta · atualizar_cliente (PUT de cadastro)
    #     excluir_proposta · arquivar_deal · arquivar_contrato (soft delete no repositório;
    #       contrato só sai se estiver em RASCUNHO)
    #     excluir_documento_crm (`UPDATE crm_documents SET arquivado=true`)
    #
    #   propose (dinheiro, instrumento legal, folha, ou apaga de verdade):
    #     definir_parametros_precificacao — muda o parâmetro de onde sai TODO preço cotado;
    #       os seis valores foram confirmados pelo Jordan um a um em 10/08, contra o holerite.
    #     atualizar_contrato — contrato é título executivo (CPC 784 §4º), não campo de tela.
    #     excluir_campanha — `DELETE FROM marketing_campaigns`, sem soft nenhum.
    #     excluir_documento — manda arquivo do kit para a lixeira do Drive. Em 10/09 eu mesmo
    #       quase apaguei NFS-27 e NFS-28 achando que eram cópia da NFS-26: eram três notas
    #       diferentes. Um `file_id` alucinado apaga documento fiscal de cliente.
    #     revisar_justificativa_ponto — decide se a falta de alguém é justificada, e
    #       `payroll_service._absences` lê essa tabela: é decisão sobre o pagamento de uma
    #       pessoa. Foi esta que apareceu primeiro, ao abrir o conector de pessoas ao Hermes.
}


def tools_include() -> list[str]:
    """Allowlist p/ o config.yaml do Hermes (Parede 1): só 🟢🔵🟡."""
    return sorted(t for t, k in TOOL_RISK.items() if k in VALID_CLASSES)
