# Revisão de 11 módulos menores (agente só-leitura, 08/09/2026 ~10h)

| Módulo | Rotas | VIVA | LIGAR | INTERNA | MORTA |
|---|---|---|---|---|---|
| gedeon | 70 | 28 | 18 | 0 | 24 |
| campo | 77 | 2 | 13 | 0 | 62 |
| notifications | 76 | 4 | 2 | 0 | 70 |
| client_portal | 61 | 42 | 0 | 0 | 19 |
| juridico | 52 | 10 | 19 | 10 | 13 |
| config | 51 | 2 | 2 | 0 | 47 |
| health_occupational | 40 | 4 | 0 | 0 | 36 |
| empresas | 36 | 12 | 1 | 1 | 22 |
| security_lgpd | 29 | 0 | 5 | 0 | 24 |
| cct | 25 | 6 | 9 | 2 | 8 |
| ai | 23 | 9 | 1 | 9 | 4 |
| Total | 540 | 119 | 70 | 22 | 329 |

## Defeitos (mais grave primeiro)
1. [5 perda de dado] `gedeon/onvio/controllers/onvio_controller.py:233-258` — POST /onvio/reclassificar apaga fgts_guias/inss_guias e recria sem valor/vencimento/código de barras (38 guias, R$ 269.063,60); /extrair-valores não repõe (enrichment_service.py:73-74 filtra extraido_em IS NULL). Chamado pelo redesign (integracoes.py:67). :243 grava mes_ref="" (10 linhas vazias).
2. [auth] `juridico/contracts_controller.py:21,26,32,40` — /juridico/contratos, /dashboard, /alertas, /{id} sem usuário. Curl sem token → 200 com 16 contratos.
3. [5 sino cego] `notifications/services/alert_ingest.py:57-67` — enqueue_alert sem user_id; o sino filtra por user_id → 7 alertas de risco desde 21/07 nunca vistos. push_service.py:436-458 não filtra status → 460 "não lidas" incluindo 443 expired.
4. [1] `health_occupational/models/epi.py:150-179` — 14 colunas de health_epi_deliveries não existem; task sst.verificar_epis_vencendo falha todo dia 07:30 e é registrada como succeeded (except :267-269).
5. [2+1] push_controller 100% 500: current_user.tenant_id inexistente; 6 tabelas push_* inexistentes.
6. [1] client_portal: ticket_message ORM ≠ tabela (sender_type/message vs sender/content) → tickets quebrados; kit_approval usa client_portal_kit_approvals (não existe); mcp_controller UPDATE ged_clients SET extra_data (coluna não existe).
7. [5] `gedeon/controllers/cnd_controller.py:268` — /gedeon/cnd/pdf/{tipo} LIMIT 1 sem CNPJ → 404 com PDF existente; status_cnd :90-96 devolve 52 certidões de 25 CNPJs como "as 3 automáticas". Chamado por redesign fiscal.py:76/98/586.
8. [1] cct_compliance_checks não existe → POST /cct/compliance/verificar 500.
9. [1] campo/checklists: checklists_preenchidos não existe (5 rotas 500); checklist_itens/respostas com colunas a menos; campo_tecnicos não existe.
10. [1] health_occupational: health_control_measures, health_complementary_exams não existem; RiskMappingResponse.id str × UUID → 500; ASOResponse.exame_id NULL em 97/97 → GET /pcmso/aso/{id} 500.
11. [1] config: tenant_settings.nome não existe; enum tenantstatus × tenant_status → dashboard 0/0; templates codigo/nome × slug/name. GET /notifications/templates 500.
12. [seg/3] `juridico/det_controller.py:102` — DET_ROBO_TOKEN vazio → token default hardcoded conecta-det-robo-2026 ativo; det-robot paused; /det/coletar stub coletadas:0 (redesign juridico.py:277).
13. [8][5] `client_portal/services/portal_onboarding_service.py:145-164` — onboard_nao_logados regera senha e reenvia e-mail a todo cliente sem login, a cada chamada, sem dedupe; senha volta no JSON. Exposto em area_do_cliente.py:199.
14. [6] sombreadas: main_production.py:1271 vs 1279 (5 rotas onvio); POST /notifications/push/send duplicada; LGPD consent /purposes, /legal-bases atrás de /{titular_id}; pia /risk-categories; /empresas/sugerir/{tipo} duplicado.
15. [5] `redesign_builders/seguranca.py:83-101` — forms lgpd-pia e lgpd-apagamento com fields [] → 422 sempre.
16. [5] `empresas/controllers/obligations_controller.py:116-117,156-157`, dashboard_controller 185/321/500 — Query(default=date.today().month) congela o mês até restart.
17. [5] PCMSO dividido: agendar grava health_medical_exams; tela lê gp_asos; task lê tabela errada → "0 vencidos" (gp_asos 88/97). epi_service lê quantidade_disponivel e grava quantidade_atual → estoque sempre [].
18. [5] regras: cct termination abono (CLT 143); juridico riscos meses_ano; ASO vencimento emissão+365; ppra totais iguais; gedeon dashboard Redis "2 prontos"; empresas impostos receita*3/*12 rotulados reais; onvio ORDER BY mes_ref texto; portal_operacao sem client_id; access_management último acesso.
19. [5][6] MCP feedback no-op (consultor_mcp_controller.py:123-125).
20. [5] campo/visitas: avg() sobre varchar → dashboard 500; pendentes-confirmacao sempre [].
21. [6] mocks servidos como dado: empresas statements/bookkeeper/dominio; notifications channel_dispatcher (sendgrid/twilio/fcm "success" sem enviar); intelligent_notification em dicts; security_lgpd status fixo, encryption master_key por request; health_controller; campo monitoring; skills_controller /tmp/skills.
22. [3] except silenciosos (cnd, kit, notification, erasure, epi, pcmso, ppra, sst tasks, analytics do portal, processos).
23. [4] fuso (gedeon utcnow competência; kronos; campo visita/OS utcnow; pcmso; det/parecer PDF; anomalia; config; portal_resumo; timing_optimizer).
24. [7] INSERT em GET /preferences/me; kit_approval UPDATE em transação abortada; consultor_service CREATE TABLE por request; JWT em claro em client_portal_sessions.token; Session síncrona em async def.

## Vereditos (resumo)
- gedeon: sophia/hermes VIVA; orquestrador (montagem, upload, ficha, condominios, checklist, completude, cronograma, painel) VIVA via MCP/clássico; conferir/conferir-lote/dp-alinhamento/funcionarios/entrega/assinaturas/faturar LIGAR; cnd VIVA (defeito 7); onvio reclassificar/extrair/resumo VIVA; onvio documentos/historico/stats/guias LIGAR; context/dashboard/conformidade/atlas/sophia status|buscar|alertas|impacto-folha MORTA; kit_controller (3) MORTA; controllers/onvio_controller (5) MORTA (sombreadas).
- empresas: GET /, simular-regime, liminares GET/POST VIVA; migrador executar LIGAR; obligations calendario/grupo, alertas VIVA (MCP); dashboard VIVA; dominio status INTERNA, plano-contas VIVA; bookkeeper resumo-mensal VIVA; statements (4), dominio POSTs (3), bookkeeper lancamentos (2), migrador cálculos (5), POST/GET/PATCH empresa, sugerir, liminares/ativas, PATCH liminares MORTA.
- campo: GET /visitas VIVA (MCP+redesign); /campo/dashboard VIVA (MCP); visitas GET {id}/numero/responsavel/cliente/lead/pdf + POST/confirmar/checkin/checkout/resultado/cancelar/reagendar LIGAR; ordem_servico (22), checklist (18), monitoring (5), tickets/technicians (6), visitas dashboard/pendentes e 9 comerciais MORTA.
- notifications: GET /push, PATCH read, read-all, subscribe VIVA; queue, queue/stats LIGAR; 24 do notification_controller + intelligent (23) + push (23) MORTA.
- client_portal: kits, tickets GET, access_management, assistant send/greeting, analytics, financeiro, operacao, settings, avisos VIVA; auth refresh/logout, historico-drive, kit_approval, tickets POST/{id}/messages/close, assistant feedback, notifications (5), mcp (2), whatsapp (2) MORTA.
- config: consultor_ceo perguntar ×2 VIVA; panorama/historico LIGAR; config_controller (47) MORTA.
- juridico: contracts listar/dashboard/alertas/{id} VIVA (sem auth); consultor perguntar VIVA; pareceres POST INTERNA; riscos (3), escritorio (3), prazos GET, processos upload/{id}/enviar-cqb, conhecimento playbook/POST, det status/{id}/robo status/comunicacao/upload, analises POST, contratos/{id}/analise LIGAR; hub dashboard/prazos alertas, context ×4, processos POST, det comunicacoes/ingest INTERNA; skills (3), pareceres GET ×3, analises GET, consultor historico, context/pessoa, processos GET, conhecimento GET, hub POST prazos, det coletar MORTA.
- cct: gêmeo hardcoded de people_management/cct — tabela INTERNA; validar/reajuste/auditar, hora-extra/adicional-noturno, decimo-terceiro VIVA; taxa-negocial, permitidas/adicionais, compliance resumo/estabilidade, rescisao validar, holidays LIGAR; auditorias, beneficios validar/config, schedule validar, compliance verificar/metadata, rescisao ferias MORTA.
- ai: executivo ×4, consultor_mcp ×4, agente_aprovacao INTERNA; consultor_escopado executar ×2, voz, propor-esocial-sst, consultor_feedback feedback/aprovar/rejeitar, anomalia confirmar/descartar VIVA; placar LIGAR; executivo consultar, chat/consultar, memorias/pendentes, anomalia pendentes MORTA.
- health_occupational: candidato a aposentar inteiro (duplica /people-management/sst); pré-requisito: repontar MCP status_pcmso/status_ppra/estoque_epi e tirar 3 tasks do beat.
