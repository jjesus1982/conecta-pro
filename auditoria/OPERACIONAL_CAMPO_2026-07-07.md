# Lapidação do Módulo Operacional — Campo + Hierarquia + Diaristas + Telegram — 2026-07-07

Missão: loop de feedback de campo, hierarquia por posto, elo diaristas→financeiro, Telegram útil.
Commits: `5d943a57` (fase 1 — módulo E2E real) e `<campo>` (esta fase). Deploy backend blue/green,
frontend build+docker cp. Migrations com rito backup→staging→prod (FORWARD/REVERSAO em auditoria/).

## A. HIERARQUIA — provada E2E por token de cada usuário

| Usuário | Papel | Prova E2E |
|---|---|---|
| jjesus@ / egonzaga@ / opaiva@ | veem TUDO | lista de ocorrências global; triagem 200 |
| awsilva@ (Antonio) | líder Ideal Flores | equipe = só Ideal; 201 ocorrência no seu posto; **403 no posto da Erika** |
| epereira@ (Erika) | líder Laranjeiras | ocorrência sem post_id → auto-preenchida Laranjeiras; 403 forçando Mirante |
| emarques@ (Ediwilson) | líder 2 posts Mirante | 422 pedindo post_id (ambíguo), 201 com post_id |

- `posts.leader_id` (FK employees) seedada pela palavra do Jordan; `users.employee_id` criada e seedada
  (e-mails de employees são pessoais gmail/outlook — não serviam de ponte).
- Escopo em `modules/operacional/scope.py`: líder de posto é SEMPRE escopado (mesmo role admin);
  admin/gerente_operacional/supervisor/inspetor sem liderança → veem tudo.
- Orlailson consolidado: opaiva@ = admin + permissions do egonzaga@ (`{module:dp,operacional,ged}`);
  epaiva@ desativado (já estava).

## B. LOOP DE FEEDBACK DE CAMPO

1. **Ocorrência rápida** (`/modulos/operacional/ocorrencia-rapida`, mobile): chips categoria→enum real
   (novos tipos: incidente, manutencao, conflito, elogio), severidade, funcionário opcional
   (occurrences.employee_id relaxada p/ NULL — FK real aponta employees, model corrigido), occurred_at
   auto. Escopo no create/list/stats (cache do /stats REMOVIDO — vazava dados entre escopos).
2. **Passagem de turno** (`/passagem-turno`): tabela `operacional_passagens_turno`; turno seguinte vê a
   anterior (`anterior` no GET); marcar lida (JSONB lida_por). Provado 201/422/403/vazio-honesto.
3. **Avaliação de equipe** (`/avaliacoes`): tabela `operacional_avaliacoes_equipe`; nota 1-5 só p/ quem
   tem alocação ativa no posto (422 senão); anti-duplicata por dia (2ª vez atualiza); consolidado com
   média/tendência (metades do período). Provado 201 + consolidado == SQL.
4. **Painel de triagem** (`/triagem`, gestores; líder → 403): ocorrências por severidade/posto + tratar
   (resolve) + comentar (rotas novas de `occurrence_comments`, tabela criada), passagens do dia,
   avaliações da semana, escalas sem vigência. Definição honesta de vigente = published/in_progress +
   data (≠ do consultor COO, que conta draft — NÃO alterado por proibição da missão; incoerência anotada).
5. **Escalas destravadas** — causa raiz dupla: (a) ninguém nunca clicou submit→approve→publish e quem
   clicava sem permissão levava 403 SILENCIOSO (agora: botões com gate + banner de erro); (b) as 3 drafts
   eram de ABRIL — publicá-las não cobriria julho. Feito: `filled_shifts` corrigido (fill_rate saía 0%),
   guard "publicar sem turnos" 422, bug slowapi (faltava `Response`) no auto-generate, **9 escalas de
   julho/2026 geradas das 45 alocações reais (558 turnos) e publicadas** → 9 vigentes hoje; painel:
   `sem_vigencia: []`. As 3 drafts de abril ficaram como estão (histórico; cancelar é decisão do Jordan).

## C. DIARISTAS

- **Cadastro pelo gerente** (tela diárias, mobile): CPF OBRIGATÓRIO validado (módulo 11; rejeita
  sequência repetida — provado: `11111111111` → 422 com mensagem acionável), PIX OBRIGATÓRIO (formato
  validado por tipo; JAMAIS fabricado — GET não expõe a chave; PATCH só altera se digitada), contato
  (telefone OU e-mail) obrigatório — colunas novas `telefone`/`email`. Editar/inativar (inativo some do
  dropdown de lançamento). Proibido limpar CPF/PIX (ficaria impagável).
- **Elo do dia**: `GET/POST /financial/pagamentos-diaristas/{lancados-dia,programar-lancados-dia}/{data}`
  — lê `diaria_lancamentos` do dia (fonte Gonzaga), programa VT/VR R$32/pessoa com origem `diarias_dia`
  (NUNCA mistura com origem `escala` do FLUXO 1; a UI rotula as duas fontes). Idempotente (2ª chamada:
  novos=0, ja=1 — provado). Prova real: CONCEIÇÃO LIMA (04/07) programada `sem_pix` == SQL (pendência
  real de cadastro, não mascarada).
- **Lote mensal**: card "Programar diárias do mês" na tela de pagamentos chama o endpoint pronto.
  Provado: julho/2026 → 1 diarista, R$70, pagamento 15/08, `sem_pix` honesto.

## D. TELEGRAM (1 bot, ruído desligado, informação útil)

- **Crontab** (backup em `auditoria/crontab_backup_2026-07-07.txt`; linhas comentadas com tag
  `[CAMPO 2026-07-07]`): context_builder */2 (720×/dia), heartbeat 0 */6, escaladas */5 e o
  briefing_jordan.sh QUEBRADO (chamava endpoint inexistente). Mantidos: ciclo rápido (só fala em
  falha), alerta_inadimplencia, relatório matinal do CTO, backup. Efeito colateral anotado: o
  assistente Telegram perde o system_context.json fresco (era o context_builder que alimentava).
- **Briefing Operacional 07:30 BRT seg-sex** (celery beat, fila gov.batch, TZ America/Sao_Paulo):
  postos cobertos, escalas vigentes/drafts, ocorrências abertas por severidade, diaristas de ontem,
  ASOs vencendo 30d (fonte gp_asos, mesma do SST). 100% banco. **Provado: enviado ao chat do Jordan**
  (`enviado_jordan: True`) com dados reais (9 postos, 9 vigentes, 0 sem cobertura).
- **Alertas de campo em tempo real**: ao criar ocorrência — grave → chat operacional; gravíssima →
  também Jordan; anti-spam 60s/(posto+severidade); fallback sem Markdown quando o texto quebra o parse.
  Provado: `enviado: True` + mensagem de teste real no chat.
- `TELEGRAM_CHAT_ID_OPERACIONAL` no `.env` (por ora = chat do Jordan).

## Correções colaterais descobertas no caminho
- `occurrences.employee_id`: FK real do banco aponta `employees` (model dizia `users`) — model alinhado;
  NOT NULL relaxado (ocorrência sem funcionário específico é válida).
- Frontend de escalas: erros de transição eram engolidos (string interna) — agora banner visível com
  detail do backend.
- auto-generate de escalas: 500 pré-existente do slowapi (endpoint dict sem `Response`).

## AÇÕES DO JORDAN (nada disso é código — decisões/dados seus)
1. **Divergência líder × alocação**: Antonio está ALOCADO no Laranjeiras (lidera Ideal Flores) e Erika
   ALOCADA no Mirante (lidera Laranjeiras). O escopo segue a sua palavra; se a alocação estiver errada,
   corrigir em Operacional→Alocações (ou me diga que eu ajusto).
2. **Grupo Telegram operacional**: criar grupo com Gonzaga+Orlailson, adicionar o bot
   @conecta_pro_monitor_bot, mandar /start, e capturar o chat_id (getUpdates) → trocar
   `TELEGRAM_CHAT_ID_OPERacional` no `.env` e recriar backend+celery-batch. Enquanto isso, alertas e
   briefing operacional caem no SEU chat.
3. **Senhas de primeiro acesso** dos líderes (awsilva@, epereira@, emarques@) e do opaiva@: os users
   existem e o escopo funciona (provado por token), mas não sei as senhas deles — defina/reset no admin
   para eles logarem nas telas novas.
4. **CPF/PIX pendentes de diaristas reais**: CONCEIÇÃO LIMA (e outros sem PIX) — completar cadastro para
   os pagamentos saírem do estado `sem_pix`. Diaristas-teste no cadastro ANTIGO (tabela `diarists`:
   "Ana Silva - Diarista Teste", "Maria Diarista Atualizada", CPF 12345678901) — expurgar ou completar.
5. **3 escalas draft de abril/2026**: obsoletas — cancelar? (não mexi).
6. **required_headcount dos postos** (pendência da fase 1): soma 11 vs 45 alocados → taxa de ocupação
   >100% com nota honesta. Cadastrar o headcount real por posto.
7. Posts de teste `ZZE2E_*` (2) e "Condomínio Villa dos Pássaros" duplicado na tabela posts — limpar?
8. Avaliar se o relatório matinal do CTO (10:00 UTC) continua — mantive.

## Registros de teste E2E — todos limpos
3 ocorrências TESTE → canceladas+inativas; 1 passagem e 1 avaliação de teste → inativas; diarista
ZZE2E → deletado. Ficaram (reais e intencionais): pagamentos programados da CONCEIÇÃO (sem_pix),
9 escalas de julho publicadas, mensagens de teste no Telegram do Jordan.

---

# RODADA 2 (mesma noite) — Presença ao vivo + rename + automações

Ordem do Jordan: continuar lapidando em modo autônomo; corrigir alocações; presença pelas batidas
(Sólides) com opção manual; renomear Operações→Operacional; inspirar nos melhores do segmento.

## Entregas
1. **Alocações corrigidas** (ordem explícita): Antonio→Ideal Flores, Erika→Laranjeiras Village
   (nota de auditoria no registro; headcount dos 3 postos recalculado). Obs: turnos de JULHO dos dois
   ainda apontam pros postos antigos (escalas geradas antes da correção) — agosto nasce certo; o quadro
   de presença trata a realidade via alocação.
2. **PRESENÇA AO VIVO** (`/operacional/presenca/hoje` + tela `/modulos/operacional/presenca`):
   turnos do dia × primeira batida real (`gp_clock_punches`, sync Sólides VIVO — batidas do próprio dia)
   com fallback check-in manual pelo líder (escopado; 409 se já presente). Status honesto por horário
   (TZ Manaus), flags facial/geofence, extras (batida sem turno → posto da alocação), sem_posto.
   **Provado == oráculo**: 7 batidas reais do dia → 1 presente no turno (MAURICIO, Villa Dei Fiori,
   00:51 noturno), 4 extras nos postos certos, 2 sem posto (JONILSON/ADEILSON — sem alocação ativa).
   Check-in manual: 200 → presente fonte manual → 409 repetido → revertido (teste limpo).
   **Insight exposto pelo quadro**: as escalas de julho auto-geradas NÃO refletem quem realmente
   trabalha (padrão 12x36 arbitrário) — plano × realidade agora é visível para a gestão ajustar.
3. **Automações novas (beat, fila gov.batch)**:
   - `operacional.vigia_ausencia` (*/30min, 8-23h SP = 7-22h Manaus): turno em andamento 30-60min sem
     batida/check-in → Telegram operacional (janela única por turno). Provado inline (0 na janela — honesto).
   - `operacional.gerar_escalas_proximo_mes` (dia 25, 08h): escalas do mês seguinte em RASCUNHO +
     aviso Telegram "revise e publique" — nunca publica sozinho.
   - Briefing 07:30 ganhou seção *Presença agora* (batidas/esperados/postos em andamento sem batida).
4. **Rename Operações→Operacional**: todos os labels visíveis (modules.ts, hub Gestão de Pessoas,
   origem de kits GED); ids/rotas/permissions intactos. Deixados de propósito: valores de dado
   "Operacoes" em dropdowns de departamento do DP (são dado do banco, não nome de módulo).
5. **Integração IA na triagem**: botão "Sugerir medida (IA)" nas ocorrências → advisor do módulo
   disciplinar (categoria pré-mapeada, descrição editável; resposta com medida/confiança/histórico/
   referências legais + aviso "decisão é humana"). Ocorrência sem funcionário → mensagem honesta.
6. Portão de qualidade final: sweep 217 rotas GET → **173×200, 26×404 honestos, 18×422 de parâmetro,
   ZERO 500**.

## Roadmap sugerido (inspiração TrackTik/Silvertrac — próximas lapidações)
- Rondas com checkpoint QR/NFC + geolocalização no celular (base inspection_rounds já existe).
- Post orders (instruções de posto) versionadas no GED, visíveis na tela do líder.
- Absenteísmo histórico por posto/funcionário no BI (base: presença × escala acumuladas).
- Espelho de ocorrências não-sensíveis no portal do cliente (área-cliente já tem operação).
- Reconciliar turnos de julho de Antonio/Erika (ou aguardar agosto).

## Decisões do Jordan registradas
- Grupo Telegram: "nem faço questão" → alertas e briefing seguem no chat dele (env aponta pro chat dele).
- Senhas dos líderes: ele providencia.

---

# RODADA 3 (manhã 08/07) — Escalas de julho = trabalho REAL + fuso das batidas

Ordem do Jordan: "ajuste as escalas de julho pra refletir quem realmente trabalha... apenas os AGPs
em 12x36, demais em 44h semanais comerciais... fidelidade por posto e quantidade de funcionários por posto".

## Descoberta crítica — batidas são UTC
Provado por sequência real: ADEMIR (ASG) entrada 11:02 UTC = **07:02 Manaus** (almoço 11-12 local,
saída 16:00) e ANILSON (AGP) 22:00 UTC = **noturno 18:00–06:00 Manaus com 1h pausa**. Meu módulo de
presença de ontem tratava como hora local → corrigido (conversão UTC→Manaus em presença, vigia e
briefing). Batida noturna de 20:51 Manaus era contada no dia errado — agora não é mais.

## Escalas de julho regeneradas do padrão real (script: auditoria/SCRIPT_regen_escalas_julho_2026-07-08.py)
- Fonte: batidas dos últimos 60 dias (turno = mediana da 1ª entrada; paridade de dias 12x36 =
  maioria ímpar/par dos dias trabalhados). **Todos os 21 AGPs tinham histórico — zero chute.**
- Resultado: **756 turnos** (substituíram os 558 fictícios do gerador padrão, backup
  `PRE_ESCALAS_REAIS_20260708` antes): 21 AGPs em 12x36 (**12 noturnos, 9 diurnos** — o quadro real
  pende pro noturno), 16 em 44h comercial (10 ASG + 2 artífices + 1 jardineiro + 3 líderes;
  seg-sex 8h com 1h almoço + sáb 4h, início pela mediana real de cada um).
- Fidelidade por posto == quadro alocado (ex.: Ideal Flores 8 AGP + 5 comerciais; Michelangelo só
  1 ASG; Portaria Principal Mirante 2 ASG). Zero duplo-turno no mês (validado por SQL).
- Nota honesta: Gelain tem 1 único AGP (diurno alternado) — cobertura de portaria tem buracos REAIS
  que agora ficam visíveis; Líder de Portaria ficou em 44h por ordem literal ("apenas os AGPs em 12x36").

## Quantidade de funcionários por posto (pendência antiga fechada)
`required_headcount`/`current_headcount` = quadro REAL por posto (Ideal 13, Mirante 5, Prime 5,
Villa Dei Fiori 4, Laranjeiras 4, Villa dos Pássaros 2, Portaria Mirante 2, Gelain 1, Michelangelo 1).
Taxa de ocupação: 409% → **121,6%** — o excedente é FATO: **8 alocações ativas de funcionários
não-ativos (afastados/suspensos/demitidos)** → decisão do Jordan (encerrar alocação ou manter vaga).

## Fidelidade do quadro de presença
- Novo campo `batidas_sincronizadas_ate` + aviso âmbar na tela quando o sync do Sólides está
  defasado (>90min) — às 08:19 de hoje a última batida sincronizada era de 05:58: os "atrasados"
  podem ser atraso do SYNC, não do funcionário, e a tela agora DIZ isso.

## AÇÕES DO JORDAN (novas desta rodada)
1. 8 alocações ativas de funcionários não-ativos — encerrar ou manter (taxa >100% até resolver).
2. Gelain com 1 AGP: portaria descoberta em dias alternados e à noite — contratar/realocar?
3. Frequência do sync de batidas do Sólides (últimas chegam com horas de atraso em certos períodos)
   — se quiser presença mais "ao vivo", aumentar a frequência do sync.
