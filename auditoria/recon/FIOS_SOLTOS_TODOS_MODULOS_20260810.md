# Inventário de fios soltos — TODOS os módulos (2026-08-10)

Medido com `conecta-backend-recon` v2 sobre as **rotas montadas** em `main_production:app`
cruzadas com a superfície do front (clássico + redesign). READ-ONLY: nenhuma rota foi chamada.

## ⚠️ Bug corrigido nesta medição — leia antes de usar números antigos

A primeira passada acusou **207** órfãs de escrita e **15 ações `/redesign/action/*` órfãs**.
Era bug meu na v2: `grep` **omite o nome do arquivo quando o alvo é UM arquivo**, então a linha
sai `732:token` em vez de `arq:732:token`; o parser exigia 3 campos e descartava tudo em
silêncio. Resultado: os **18.483 tokens de `redesign_data_controller.py` nunca entraram no
índice**. Corrigido com `-H`. As 15 ações do redesign estavam TODAS ligadas.

Números reais, depois do conserto:

- rotas montadas: **4191** · expostas: **3843** (91%)
- órfãs de ESCRITA: **191** · geradores de documento órfãos: **6**
- amostra de 5 verificadas à mão: 5/5 realmente sem referência no front

**Órfão ≠ bug.** Webhook do banco e `/integration/*` são chamados de fora — aparecem aqui e
estão certos assim. A lista é candidata, quem decide é humano.

## Por módulo

| Módulo | rotas | expostas | falso-órfão | ESCRITA órfã | geradores |
|---|---:|---:|---:|---:|---:|
| people-management | 698 | 609 | 18 | 54 | 0 |
| crm | 245 | 199 | 22 | 22 | 2 |
| financial | 592 | 553 | 20 | 19 | 0 |
| operacional | 304 | 281 | 13 | 10 | 0 |
| gedeon | 55 | 38 | 1 | 9 | 0 |
| juridico | 52 | 44 | 1 | 7 | 0 |
| bidding | 87 | 77 | 4 | 6 | 0 |
| ged | 200 | 187 | 7 | 4 | 2 |
| cct | 25 | 14 | 5 | 6 | 0 |
| webhooks | 10 | 4 | 0 | 6 | 0 |
| portal | 61 | 56 | 0 | 5 | 0 |
| ai | 8 | 0 | 2 | 5 | 0 |
| fiscal | 22 | 14 | 4 | 3 | 1 |
| consultores | 13 | 7 | 0 | 3 | 1 |
| justificativa | 7 | 3 | 0 | 3 | 0 |
| security | 29 | 21 | 5 | 3 | 0 |
| integrations | 78 | 74 | 1 | 3 | 0 |
| financeiro | 42 | 37 | 2 | 3 | 0 |
| mcp | 4 | 2 | 0 | 2 | 0 |
| empresas | 36 | 32 | 2 | 2 | 0 |
| government | 448 | 444 | 2 | 2 | 0 |
| onvio | 15 | 11 | 2 | 2 | 0 |
| comercial | 4 | 2 | 0 | 2 | 0 |
| rh | 4 | 1 | 1 | 2 | 0 |
| gestao | 4 | 0 | 2 | 2 | 0 |
| gdrive | 12 | 8 | 0 | 2 | 0 |
| marketing | 20 | 19 | 0 | 1 | 0 |
| analytics | 33 | 32 | 0 | 1 | 0 |
| whatsapp | 7 | 5 | 1 | 1 | 0 |
| signatures | 8 | 7 | 0 | 1 | 0 |

## Detalhe — as órfãs, por módulo

### people-management (54)

- `POST` `/api/v1/people-management/hr/discipline/medidas-administrativas` 
  - Criar medida disciplinar
- `POST` `/api/v1/people-management/hr/discipline/medidas-administrativas/gerar-documento` 
  - Gerar documento
- `POST` `/api/v1/people-management/hr/discipline/medidas-administrativas/templates` 
  - Criar template
- `PATCH` `/api/v1/people-management/hr/discipline/medidas-administrativas/templates/{template_id}` 
  - Atualizar template
- `DELETE` `/api/v1/people-management/hr/discipline/medidas-administrativas/templates/{template_id}` 
  - Remover template
- `POST` `/api/v1/people-management/hr/discipline/medidas-administrativas/ia/recomendar` 
  - Obter recomendacao de medida
- `POST` `/api/v1/people-management/hr/discipline/medidas-administrativas/ia/validar-conformidade` 
  - Validar conformidade legal
- `POST` `/api/v1/people-management/hr/discipline/medidas-administrativas/ia/verificar-proporcionalidade` 
  - Verificar proporcionalidade
- `PATCH` `/api/v1/people-management/hr/discipline/medidas-administrativas/{action_id}` 
  - Atualizar medida
- `DELETE` `/api/v1/people-management/hr/discipline/medidas-administrativas/{action_id}` 
  - Remover medida
- `POST` `/api/v1/people-management/hr/discipline/medidas-administrativas/{action_id}/submeter` 
  - Submeter para aprovacao
- `POST` `/api/v1/people-management/hr/discipline/medidas-administrativas/{action_id}/aprovar` 
  - Aprovar medida
- `POST` `/api/v1/people-management/hr/discipline/medidas-administrativas/{action_id}/rejeitar` 
  - Rejeitar medida
- `POST` `/api/v1/people-management/hr/discipline/medidas-administrativas/{action_id}/assinar` 
  - Assinar documento
- `POST` `/api/v1/people-management/hr/discipline/medidas-administrativas/{action_id}/recusar-assinatura` 
  - Registrar recusa de assinatura
- `POST` `/api/v1/people-management/hr/discipline/assinaturas/verificar` 
  - Verificar assinatura
- `POST` `/api/v1/people-management/hr/discipline/from-occurrence/{occurrence_id}` 
  - Criar Ação Disciplinar de Ocorrência
- `POST` `/api/v1/people-management/hr/esocial/s2299/gerar` 🏛️
  - Gerar XML S-2299 Desligamento
- `POST` `/api/v1/people-management/human-resources/training/enrollments/{enrollment_id}/certificate` 
  - Emitir certificado
- `POST` `/api/v1/people-management/human-resources/performance/review-cycle` 
  - Iniciar ciclo de avaliacao
- `PUT` `/api/v1/people-management/human-resources/career/plans/{plan_id}/milestones` 
  - Atualizar milestones do plano
- `POST` `/api/v1/people-management/human-resources/career/plans/{plan_id}/milestones/{milestone_index}/complete` 
  - Concluir milestone
- `POST` `/api/v1/people-management/human-resources/recruitment/resume/parse` 
  - Faz parsing de currículo PDF/DOCX usando IA.
- `POST` `/api/v1/people-management/human-resources/recruitment/resume/parse-text` 
  - Analisa texto de currículo já extraído (sem upload de arquivo).
- `POST` `/api/v1/people-management/portal/auth/reset-senha` 
  - Reset de senha do portal: redefine senha usando CPF + data de nascimento.
- `POST` `/api/v1/people-management/portal/my-notifications/test-trigger` 
  - Disparar notificacao de teste (apenas development, status_code=201)
- `POST` `/api/v1/people-management/portal/self-service/bater-ponto` 
  - Bater ponto (funcionário) — GPS geofence + selfie
- `POST` `/api/v1/people-management/portal/ouvidoria-admin/{manifestacao_id}/responder` 
  - Responde/atualiza o status de uma manifestação (a resposta fica visível ao autor
- `POST` `/api/v1/people-management/ged/clients/{client_id}/portal-access` 
  - Habilita ou desabilita o acesso ao portal do cliente.
- `POST` `/api/v1/people-management/ged/kits/{kit_id}/send-email` 
  - Envia kit por email para o cliente via EmailKitService (HTML + link Drive).
- `POST` `/api/v1/people-management/ged/documents/ingestao/historica` 
  - Processa todos os ZIPs historicos da pasta Google Drive e alimenta SOPHIA.
- `POST` `/api/v1/people-management/ged/config/drive/connect` 
  - Inicia conexão com Google Drive.
- `DELETE` `/api/v1/people-management/ged/config/drive/disconnect` 
  - Desconecta o Google Drive.
- `POST` `/api/v1/people-management/ged/config/schedule` 
  - Salva configuração de agendamento.
- `POST` `/api/v1/people-management/integration/ops-to-dp/shift-closed` 
  - Operacoes notifica DP sobre fechamento de turno.
- `POST` `/api/v1/people-management/integration/ops-to-dp/occurrence` 
  - Operacoes notifica DP sobre ocorrencia grave.
- `POST` `/api/v1/people-management/integration/dp-to-ops/vacation-approved` 
  - DP notifica Operacoes sobre ferias aprovadas.
- `POST` `/api/v1/people-management/integration/rh-to-dp/candidate-approved` 
  - RH notifica DP sobre aprovacao de candidato.
- `POST` `/api/v1/people-management/integration/rh-to-ops/mandatory-training-check` 
  - RH verifica treinamentos obrigatorios antes de alocacao.
- `POST` `/api/v1/people-management/integration/portal-to-dp/document-signed` 
  - Portal notifica DP sobre assinatura digital de documento.
- `POST` `/api/v1/people-management/integration/dp-to-ops/termination-notify` 
  - DP notifica Operacoes sobre rescisao.
- `POST` `/api/v1/people-management/integration/dp-to-rh/admission-completed` 
  - DP notifica RH sobre admissao concluida.
- `POST` `/api/v1/people-management/integration/ops-to-dp/check-availability` 
  - Operacoes verifica no DP se funcionario esta disponivel.
- `POST` `/api/v1/people-management/integration/ops-to-dp/payroll-data` 💰
  - Operacoes envia dados de turnos para calculo de folha.
- `POST` `/api/v1/people-management/ponto/sincronizar-solides` 
  - Sincronizar ponto com Solides Tangerino
- `POST` `/api/v1/people-management/folha/importar-alterdata` 💰
  - Importar folha do Alterdata (CSV, status_code=201)
- `POST` `/api/v1/people-management/sst/cipa/reunioes` 
  - Registra reuniao da CIPA.
- `POST` `/api/v1/people-management/admin/cct/convencoes/{convencao_id}/feriados` 
  - Adiciona feriado à convenção.
- `POST` `/api/v1/people-management/admin/cct/cache/invalidar` 
  - Invalida todo o cache CCT no Redis (usar após atualizações).
- `PATCH` `/api/v1/people-management/dp/payslips/{payslip_id}/publicar` 💰
  - Publica contracheque — torna visível no portal do funcionário.
- `POST` `/api/v1/people-management/dp/payslips/importar-lote` 💰
  - Importa múltiplos contracheques de uma vez. Máximo 100 por lote.
- `POST` `/api/v1/people-management/dp/payslips/folha/pagar-via-pix/{mes}/{ano}` 💰
  - Pagar folha completa via PIX Inter (exige OTP)
- `POST` `/api/v1/people-management/dp/payslips/folha/funcionario/{employee_id}/pix-key/gerar-otp` 💰
  - Gera OTP p/ liberar a troca de chave PIX (e-mail Jordan)
- `PUT` `/api/v1/people-management/dp/payslips/folha/funcionario/{employee_id}/pix-key` 💰
  - Cadastrar/atualizar chave PIX do funcionário (exige OTP)

### crm (24)

- `POST` `/api/v1/crm/docs/ordem-servico/pdf` 📄
  - Gera uma ORDEM DE SERVIÇO em PDF (com selo). salvar=true: registra + link de download.
- `POST` `/api/v1/crm/docs/orcamento/pdf` 📄
  - Gera um ORÇAMENTO / proposta de PAGAMENTO ÚNICO (material, serviço ou ambos) no padrão-ouro.
- `POST` `/api/v1/crm/proposals/{proposal_id}/marcar-enviada` 
  - Marca uma proposta como ENVIADA sem reenviar ao cliente (quando o envio foi feito por fora
- `POST` `/api/v1/crm/proposals/{proposal_id}/send-whatsapp` 
  - Envia a proposta pelo WhatsApp do José Luís: PDF + link de assinatura, com rastreio em
- `POST` `/api/v1/crm/proposals/{proposal_id}/send-completo` 
  - Envia a proposta por E-MAIL **e** por WhatsApp (José Luís), o WhatsApp citando o e-mail.
- `POST` `/api/v1/crm/docs/expurgar-teste` 
  - Arquiva (soft-delete) TODOS os documentos de teste (teste=true). confirmar=false só mostra a con
- `POST` `/api/v1/crm/assets/upload` 
  - Recebe um asset (logo/selo) em base64 e grava no volume PERSISTENTE /app/uploads/assets.
- `POST` `/api/v1/crm/whatsapp/cadastrar` 
  - Grava/normaliza (E.164) o WhatsApp de um cliente (por CNPJ ou id) ou lead (id).
- `POST` `/api/v1/crm/followups` 
  - Toque manual do José Luís. confirmar=false: preview (resolve número, sem enviar).
- `POST` `/api/v1/crm/followups/resposta` 
  - Registra manualmente o retorno do cliente (quando não veio pelo inbound automático).
- `POST` `/api/v1/crm/followups/optout` 
  - Marca um número como opt-out (não receber follow-ups).
- `POST` `/api/v1/crm/negociacoes/responsavel` 
  - Define quem conduz a negociação. 'jordan' pausa o acompanhamento do José Luís; 'jose_luis' reati
- `POST` `/api/v1/crm/simular-fechamento` 
  - What-if: se fechar estes deals (ou todos de um estágio), como fica ganho/meta.
- `POST` `/api/v1/crm/followups/lote` 
  - Toque em lote em todos os clientes com proposta pendente. confirmar=false = preview.
- `POST` `/api/v1/crm/visitas/achados` 
  - Anexa achados (análises de foto/áudio/vídeo ou notas) ao relatório.
- `POST` `/api/v1/crm/visitas/montar` 
  - Grava o relatório sintetizado (o LLM redige; aqui persiste).
- `POST` `/api/v1/crm/visitas/registrar-lead` 
  - Cria/atualiza lead + oportunidade a partir da visita.
- `POST` `/api/v1/crm/reunioes` 
  - Sugere uma reunião (status 'sugerido' — Jordan confirma).
- `POST` `/api/v1/crm/reunioes/confirmar` 
  - confirmar reuniao ep
- `POST` `/api/v1/crm/reunioes/cancelar` 
  - cancelar reuniao ep
- `POST` `/api/v1/crm/reativar-lead` 
  - Reengaja um lead frio por WhatsApp (envio real). confirmar=false = preview.
- `POST` `/api/v1/crm/nps/enviar` 
  - Envia pesquisa NPS (0-10) a um cliente por WhatsApp. confirmar=false = preview.
- `POST` `/api/v1/crm/clientes/anotar` 
  - Adiciona uma anotação à ficha viva do cliente (compartilhada com o José Luís).
- `POST` `/api/v1/crm/apresentacoes/gerar` 
  - Gera uma APRESENTAÇÃO no padrão Conecta PRO (mesma identidade dos documentos).

### financial (19)

- `POST` `/api/v1/financial/payables/auto-criar` 
  - Criar contas a pagar automaticamente de NFS-e e NF-e recebidas
- `POST` `/api/v1/financial/payables/auto-criar/{nota_id}` 
  - Criar conta a pagar para nota específica
- `POST` `/api/v1/financial/cashflow/sync` 
  - Sincronizar bank_transactions → cashflow_entries
- `POST` `/api/v1/financial/inventory/real/saida` 
  - Baixa de material vinculada a serviço/NFS-e: reduz saldo + posta COGS no razão.
- `POST` `/api/v1/financial/ai/pricing/calculate` 
  - Calcula precificação ótima para um contrato de segurança.
- `POST` `/api/v1/financial/ai/billing/contrato-ativado` 
  - Simula ativação de contrato CRM → cria conta a receber automaticamente.
- `POST` `/api/v1/financial/ai/costing/registrar` 
  - Registra um custo real para um tipo de serviço.
- `PUT` `/api/v1/financial/relatorios/orcamentos-kv` 
  - Salva/atualiza um valor de orçamento no servidor.
- `POST` `/api/v1/financial/nfse-entrada/auto-criar-payables` 🏛️
  - Cria contas a pagar automaticamente para NFS-e recebidas sem payable vinculado.
- `POST` `/api/v1/financial/payable/auto-criar` 
  - Processa todas as notas fiscais recebidas sem conta a pagar vinculada (NFS-e + NF-e).
- `POST` `/api/v1/financial/payable/auto-criar/{nota_id}` 
  - Cria conta a pagar para uma nota fiscal específica.
- `POST` `/api/v1/financial/bank-reconciliations/auto` 
  - Conciliacao inteligente — 4 estrategias em cascata.
- `POST` `/api/v1/financial/nfse/sync-prestador` 🏛️
  - Sincronizar NFS-e emitidas pelo Conecta Mais no Portal Nacional
- `POST` `/api/v1/financial/conciliar/auto` 
  - Conciliação automática — Inter extrato × contas a pagar/receber
- `POST` `/api/v1/financial/cfo/custos-recorrentes` 
  - Registra um custo recorrente (tributo, parcelamento, acordo, custo fixo)
- `DELETE` `/api/v1/financial/cfo/custos-recorrentes/{custo_id}` 
  - Remove (inativa) um custo recorrente
- `POST` `/api/v1/financial/cfo/perguntar` 
  - Pergunta ao CFO IA (ancorado nos números reais)
- `POST` `/api/v1/financial/cfo/perguntar-arquivo` 
  - Consulta ao CFO analisando um anexo (PDF/DOCX/planilha/TXT)
- `POST` `/api/v1/financial/beneficiarios/seed` 
  - Popula a agenda com o que já existe (pagamentos/fornecedores/funcionários/diaristas)

### operacional (10)

- `POST` `/api/v1/operacional/scales/{scale_id}/reject` 
  - Rejeita uma escala em aprovação.
- `PATCH` `/api/v1/operacional/shifts/bulk` 
  - Atualiza múltiplos turnos em lote.
- `DELETE` `/api/v1/operacional/allocations/bulk` 
  - Deleta múltiplas alocações em lote (soft delete).
- `PATCH` `/api/v1/operacional/allocations/bulk` 
  - Atualiza múltiplas alocações em lote.
- `POST` `/api/v1/operacional/unificado/alocar-diarista` 
  - Alocar diarista a condomínio
- `POST` `/api/v1/operacional/unificado/desalocar-diarista/{assignment_id}` 
  - Desalocar diarista
- `POST` `/api/v1/operacional/scale-optimizer/otimizar` 
  - Otimiza alocação de colaboradores para uma data específica.
- `POST` `/api/v1/operacional/scale-optimizer/otimizar-mes` 
  - Otimiza escalas para um mês inteiro.
- `POST` `/api/v1/operacional/consultor/perguntar` 
  - Pergunta ao Consultor Operacional (ancorado na operação real)
- `POST` `/api/v1/operacional/consultor/perguntar-arquivo` 
  - Consulta analisando um anexo (PDF/DOCX/TXT/CSV)

### gedeon (9)

- `POST` `/api/v1/gedeon/hermes/classificar` 
  - classificar documento
- `POST` `/api/v1/gedeon/sophia/perguntar` 
  - SOPHIA v2.0: pergunta em linguagem natural sobre o acervo.
- `POST` `/api/v1/gedeon/sophia/reindexar` 
  - SOPHIA v2.0: re-indexa acervo com embedding v2.
- `POST` `/api/v1/gedeon/sophia/indexar` 
  - SOPHIA v2.0: indexar/re-indexar acervo completo.
- `POST` `/api/v1/gedeon/consultor/perguntar` 
  - Pergunta ao Consultor GED (ancorado nos kits reais)
- `POST` `/api/v1/gedeon/consultor/perguntar-arquivo` 
  - Consulta analisando um anexo (PDF/DOCX/TXT/CSV)
- `POST` `/api/v1/gedeon/consultor/intercorrencias` 💰
  - Registra intercorrência do mês (contratação, demissão, falta...)
- `PATCH` `/api/v1/gedeon/consultor/intercorrencias/{intercorrencia_id}/tratar` 💰
  - Marca intercorrência como tratada
- `DELETE` `/api/v1/gedeon/consultor/intercorrencias/{intercorrencia_id}` 💰
  - Exclui intercorrência (registro errado)

### juridico (7)

- `POST` `/api/v1/juridico/consultor/perguntar` 
  - Faz uma pergunta jurídica fundamentada (trabalhista/cível/tributária)
- `POST` `/api/v1/juridico/consultor/perguntar-arquivo` 
  - Consulta jurídica analisando um arquivo anexado (PDF/DOCX/TXT)
- `POST` `/api/v1/juridico/conhecimento/seed` 
  - Semeia a base com os casos/procedimentos reais (idempotente).
- `POST` `/api/v1/juridico/det/ingest-robo` 
  - Endpoint INTERNO — o robô empurra as mensagens lidas do DET (auto-coleta periódica).
- `POST` `/api/v1/juridico/det/coletar` 
  - Dispara a coleta automática (estado honesto enquanto gov.br OAuth não habilitado).
- `POST` `/api/v1/juridico/det/robo/login` 
  - Inicia o login supervisionado do robô (sobe o navegador no noVNC).
- `POST` `/api/v1/juridico/det/robo/coletar` 
  - Coleta a caixa do DET (robô) e REGISTRA as mensagens no ERP.

### bidding (6)

- `POST` `/api/v1/bidding/sync/pncp/trigger` 
  - Dispara sincronizacao manual com o PNCP.
- `POST` `/api/v1/bidding/sync/precos/trigger` 
  - Dispara sincronizacao manual de precos referenciais.
- `POST` `/api/v1/bidding/erp/converter/{contract_id}` 
  - Converte contrato publico em entidades operacionais.
- `POST` `/api/v1/bidding/erp/medicao/{contract_id}` 
  - Gera medicao para um contrato em um periodo especifico.
- `POST` `/api/v1/bidding/erp/fatura/{medicao_id}` 
  - Gera fatura (conta a receber) a partir de medicao aprovada.
- `POST` `/api/v1/bidding/erp/crm/{contract_id}` 
  - Vincula contrato publico ao modulo CRM (Comercial).

### ged (6)

- `POST` `/api/v1/ged/kits/{kit_id}/generate-pdfs` 📄
  - Gera PDFs reais para todos os documentos de um kit.
- `POST` `/api/v1/ged/kits/generate-all-pdfs` 📄
  - Gera PDFs para todos os kits de um mes.
- `PUT` `/api/v1/ged/config/schedule` 
  - Salva configuração de agendamento.
- `POST` `/api/v1/ged/kits/montar` 
  - Monta kits para todos os clientes ativos que nao tem kit no mes atual.
- `POST` `/api/v1/ged/kits/{kit_id}/add-nfse` 🏛️
  - Adiciona NFS-e reais do cliente ao kit e gera PDFs.
- `POST` `/api/v1/ged/kit-real/gerar-todos` 
  - Gera PDFs reais para TODOS os kits do mes.

### cct (6)

- `POST` `/api/v1/cct/salarios/validar` 
  - Valida salario de um colaborador contra piso CCT.
- `POST` `/api/v1/cct/salarios/reajuste` 
  - Calcula reajuste salarial CCT (7,1% piso / 4,5% acima do piso).
- `POST` `/api/v1/cct/salarios/auditar` 
  - Valida salario e registra auditoria no banco.
- `POST` `/api/v1/cct/jornadas/hora-extra` 
  - Calcula horas extras conforme CCT (50% normal / 100% feriado).
- `POST` `/api/v1/cct/jornadas/adicional-noturno` 
  - Calcula adicional noturno com hora reduzida (52min30s).
- `POST` `/api/v1/cct/rescisao/decimo-terceiro` 
  - Calcula 13o salario conforme CCT (2a parcela ate 20/dez).

### webhooks (6)

- `POST` `/api/v1/webhooks/inter/configurar` 💰
  - Configurar webhooks no painel Inter
- `POST` `/api/v1/webhooks/inter/pagamento-pix` 💰
  - Webhook — PIX enviado confirmado
- `POST` `/api/v1/webhooks/inter/pagamento-boleto` 💰
  - Webhook — Boleto pago por você confirmado
- `POST` `/api/v1/webhooks/inter/cobranca-recorrente` 💰
  - Webhook — Cobrança Recorrente confirmada
- `POST` `/api/v1/webhooks/cora/` 
  - Recebe a notificação do Cora (corpo vazio; dados nos headers) e concilia
- `POST` `/api/v1/webhooks/cora` 
  - Recebe a notificação do Cora (corpo vazio; dados nos headers) e concilia

### portal (5)

- `POST` `/api/v1/portal/access-management/resumo-mensal/disparar` 
  - Disparar resumo mensal (admin)
- `POST` `/api/v1/portal/access-management/{client_id}/onboard` 
  - Onboarding: provisiona + entrega credenciais
- `POST` `/api/v1/portal/access-management/onboard/nao-logados` 
  - Onboarding em lote dos que nunca logaram
- `POST` `/api/v1/portal/notifications/register-device` 
  - Registra dispositivo para receber notificacoes push.
- `DELETE` `/api/v1/portal/notifications/register-device` 
  - Remove registro de dispositivo push.

### ai (5)

- `POST` `/api/v1/ai/consultor/feedback` 
  - 👍/👎 numa resposta do consultor (correção só vira memória permanente se diretoria)
- `POST` `/api/v1/ai/consultor/memorias/{memoria_id}/aprovar` 
  - Aprova memória pendente → entra no contexto compartilhado — diretoria
- `POST` `/api/v1/ai/consultor/memorias/{memoria_id}/rejeitar` 
  - Rejeita memória pendente (some de vez) — diretoria
- `POST` `/api/v1/ai/fraud/anomalias/{alerta_id}/confirmar` 
  - Confirma a suspeita como legítima (ação humana) — diretoria
- `POST` `/api/v1/ai/fraud/anomalias/{alerta_id}/descartar` 
  - Descarta a suspeita como falso positivo (ação humana) — diretoria

### fiscal (4)

- `POST` `/api/v1/fiscal/nfe-entrada/upload-xml` 🏛️📄
  - Upload XML de NF-e de compra — atualiza estoque
- `POST` `/api/v1/fiscal/nfse-multi/calcular-tributos` 🏛️
  - Calcular tributos NFS-e com liminares
- `POST` `/api/v1/fiscal/consultor/perguntar` 🏛️
  - Pergunta ao Consultor Fiscal (ancorado nos dados reais)
- `POST` `/api/v1/fiscal/consultor/perguntar-arquivo` 🏛️
  - Consulta analisando um anexo (PDF/DOCX/TXT/CSV)

### consultores (4)

- `GET` `/api/v1/consultores/mcp/executivo/margem-condominio` 💰📄
  - 🟢 READ — margem por contrato: receita (contracts.monthly_value) − folha alocada
- `POST` `/api/v1/consultores/mcp/executivo/viabilidade-contratacao` 
  - 🟢 READ — "posso contratar N do cargo X?": cruza CFO (saldo/runway) + COO (postos
- `POST` `/api/v1/consultores/mcp/propor-pagamento` 💰
  - 🟡 PROPOR (gated): grava PENDENTE (status='preparado' via server_default).
- `POST` `/api/v1/consultores/mcp/propor-comunicado` 
  - 🟡 PROPOR (gated): grava RASCUNHO pendente de aprovação humana.

### justificativa (3)

- `POST` `/api/v1/justificativa/registrar` 
  - Registrar justificativa para saída sem nota fiscal
- `POST` `/api/v1/justificativa/alertar` 
  - Disparar alerta Telegram sobre pendências
- `POST` `/api/v1/justificativa/classificar-auto` 
  - Classificar automaticamente saídas por categoria Lucro Real

### security (3)

- `POST` `/api/v1/security/lgpd/erasure/request` 
  - Solicita exclusao de dados (Art. 18 LGPD)
- `POST` `/api/v1/security/lgpd/erasure/{request_id}/processar` 
  - Processa solicitacao de exclusao (Art. 18 LGPD)
- `POST` `/api/v1/security/lgpd/pia/create` 
  - Cria avaliacao de impacto (PIA/DPIA)

### integrations (3)

- `POST` `/api/v1/integrations/solides/beneficios/vincular-kits` 
  - Vincula itens de pedidos Sólides ao kit GED de cada funcionário.
- `POST` `/api/v1/integrations/banking/ted/transfer` 
  - Realizar transferência TED
- `POST` `/api/v1/integrations/banking/pix/refund` 💰
  - Solicitar devolução de PIX

### financeiro (3)

- `POST` `/api/v1/financeiro/inter/cobrancas/sincronizar-status` 💰
  - Atualiza status de cobranças A_RECEBER consultando a API Inter (background).
- `POST` `/api/v1/financeiro/inter/hermes/linkar` 💰
  - HERMES bulk link — vincula inter_transactions ao slot ged_kit_documents correto.
- `POST` `/api/v1/financeiro/inter/payments/folha/verificar-chaves` 💰
  - VERIFICADOR DE CHAVE PIX — confirma que a chave de cada funcionário pertence MESMO àquela

### mcp (2)

- `POST` `/api/v1/mcp/financial/call/{tool_name}` 
  - Executa uma ferramenta MCP pelo nome
- `POST` `/api/v1/mcp/financial/request` 
  - Handler MCP protocol nativo (tools/list, tools/call)

### empresas (2)

- `POST` `/api/v1/empresas/{empresa_id}/simular-regime` 
  - Simular mudança de regime tributário
- `POST` `/api/v1/empresas/contabilidade/resumo-mensal` 
  - resumo mensal

### government (2)

- `POST` `/api/v1/government/esocial/transmitir-s1000` 🏛️
  - Transmite S-1000 real ao webservice do eSocial
- `POST` `/api/v1/government/esocial/transmitir-s1000` 🏛️
  - Transmite S-1000 real ao webservice do eSocial

### onvio (2)

- `POST` `/api/v1/onvio/reclassificar` 
  - Reaplica o parser v2 a TODOS os documentos já importados.
- `POST` `/api/v1/onvio/extrair-valores` 
  - Orquestra extração de valores dos PDFs fiscais.

### comercial (2)

- `POST` `/api/v1/comercial/consultor/perguntar` 
  - Pergunta ao Consultor Comercial (ancorado no CRM real)
- `POST` `/api/v1/comercial/consultor/perguntar-arquivo` 
  - Consulta analisando um anexo (PDF/DOCX/TXT/CSV)

### rh (2)

- `POST` `/api/v1/rh/consultor/perguntar` 
  - Pergunta ao Consultor de Pessoas (ancorado nos dados reais)
- `POST` `/api/v1/rh/consultor/perguntar-arquivo` 
  - Consulta analisando um anexo (PDF/DOCX/TXT/CSV)

### gestao (2)

- `POST` `/api/v1/gestao/consultor/perguntar` 
  - Pergunta ao Consultor Executivo (ancorado na fotografia cross-módulo)
- `POST` `/api/v1/gestao/consultor/perguntar-arquivo` 
  - Consulta executiva analisando um anexo (PDF/DOCX/planilha/TXT)

### gdrive (2)

- `POST` `/api/v1/gdrive/kits/{client_id}/{competencia}/enviar-email` 
  - Enviar kit por e-mail.
- `POST` `/api/v1/gdrive/kits/{client_id}/{competencia}/montar` 
  - Montar kit completo no Google Drive.

### marketing (1)

- `POST` `/api/v1/marketing/licitacao/convert-to-crm` 
  - Converte licitação vencida em lead CRM — fecha ciclo licitação→CRM.

### analytics (1)

- `POST` `/api/v1/analytics/executive/kpis/recalcular` 
  - Recalcular KPIs a partir do dado real

### whatsapp (1)

- `POST` `/api/v1/whatsapp/send/nfse-notification` 🏛️
  - Envia notificacao de NFS-e emitida via WhatsApp.

### signatures (1)

- `POST` `/api/v1/signatures/requests` 
  - Criar solicitação de assinatura
