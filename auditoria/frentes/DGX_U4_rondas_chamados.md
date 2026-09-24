# DGX U4 — Rondas do APP Vigilância (modelos com pontos, alertas, pânico) e chamados com setor

**Branch:** `dgx/u4-rondas-chamados` (worktree sobre `fase5-hermes-camada-cognitiva` @ `7e297d134`)
**Módulo:** operacional · **Data:** 24/09/2026 · **Testado em:** sandbox `conecta_pro_staging` via container
efêmero `teste-dgx-u4` (porta 127.0.0.1:8234, parado e removido ao fim). Produção não foi tocada.

---

## 1. Estado ANTES (medido)

- `inspection_rounds` (frente 06) tinha `posts_to_visit` = lista de ids de posto. **Nenhuma** tabela de
  modelo/rota com pontos ordenados (grep `ronda|modelo|rota` em `inspection_rounds/*`: zero). Logo não havia
  o que estender — `ronda_modelos` nasce nova e a ronda ganha `inspection_rounds.modelo_id`.
- Sem "ronda atrasada", sem "ponto pulado", sem pânico: `select relname ... ilike '%ronda%|%panic%'` no
  sandbox → nenhuma tabela. `communication_alerts` existe (alerta com aceite) mas é de comunicado, não de ronda.
- `op_chamados` (F8): 18 colunas, **sem** `setor_id`, sem contato do solicitante, sem rastro de aviso. A T3
  **não** criou setores (grep `setor` em `_dgx_t3_*`: zero) → `op_setores` nasce aqui.
- Tempo (medido em 4 rondas do sandbox): `scheduled_date` é **Manaus naive** (12:29), `started_at`/
  `completed_at`/`created_at` são **UTC naive** (16:29). O motor trabalha em UTC naive e soma 4h ao agendado.
- Sandbox: 83 rondas (4 em andamento, 75 concluídas, 4 agendadas), 0 chamados, 15 postos ativos.

**Oráculo VERMELHO** (`test_oraculo_u4_rondas_chamados.py` contra o backend do repositório principal, sem U4,
depois de eu apagar os objetos U4 que a 1ª rodada verde tinha criado no sandbox):
```
  ✗ serviço ronda_alertas importa: cannot import name 'ronda_alertas' from 'modules.operacional.services'
TOTAL falhas DGX U4: 1
  fixtures apagadas (sobra: tabela inexistente)
exit=1
```

## 2. O que o DGX tem (02_OUTROS_MODULOS_MODELO §RondaLojas/ModelosRondas/RondaAlertas/ContratoSetores/SetorChamados; T3 §Vigilância)

- **ModelosRondas**: nome + cliente; horários (dom…sáb, feriado, replicar a cada N); **locais** (lojas com nº VD,
  setor, região, endereço); tipo de intervalo, intervalo mínimo, total de realizações, **telefone de pânico**.
- **RondaAlertas**: tipo pânico/vigia, aparelho, disparo, `Aceitar → ConfirmarAceitacao`, respostas.
- **ContratoSetores**: setor por contrato (código, nome), bloquear chamados, QR de abertura, e-mails de manutenção.
- **SetorChamados**: título, solicitante, contrato, **setor** ("Setor não informado."), `statusEmail`, SMTP por contrato.

## 3. O que foi feito

### Arquivos
| Arquivo | O quê |
|---|---|
| `backend/modules/operacional/services/ronda_alertas.py` (novo, 430 l.) | DDL idempotente (`_ensure`), `notificar` (e-mail via `core.mailer`, WhatsApp via `send_text_message`; sandbox = `simulado`), régua `ponto_do_checkpoint` (nome → posto → GPS/raio), regra pura `avaliar_ronda`, motor `avaliar_rondas(db, agora)`, `disparar_panico`, `mudar_status_disparo`, `parse_pontos`, `criar_modelo/alerta/setor`, `agendar_ronda_do_modelo`, `desativar` |
| `.../redesign_builders/_dgx_u4_rondas_chamados.py` (novo, 500 l.) | 8 telas + 10 ações; injeta `setor_id` e `solicitante_contato` no form `chamado-novo` da F8 |
| `.../services/supervisao_service.py` | `_DDL` += 3 colunas em `op_chamados`; `abrir_chamado(setor_id, solicitante_contato)` valida o setor e avisa o responsável; `resolver_chamado` avisa o solicitante; ambos gravam `notificado` |
| `.../redesign_builders/_dgx_f8_operacional.py` | `rd_chamado_abrir` repassa `setor_id`/`solicitante_contato` e mostra o status do aviso (2 linhas) |
| `.../inspection_rounds/controllers/inspection_round_controller.py` | `POST /panico` (multipart, foto opcional) e `GET /fotos/panico/{nome}` — **antes** de `/{round_id}` |
| `.../redesign_builders/operacional.py` | import do `router` + `telas(db, out)` antes de `montar_grupos` (2+1 linhas, `# dgx u4`) |
| `.../redesign_builders/_op_grupos.py` | 6 abas no FIM de `g-rondas`, 2 no FIM de `g-comunicacao` (só acrescenta) |
| `backend/scripts/orq/test_oraculo_u4_rondas_chamados.py` (novo) | 30 afirmações |

### DDL que `_ensure` aplica em produção no 1º acesso (todo `IF NOT EXISTS`; nenhum DROP/UPDATE)
```sql
CREATE TABLE ronda_modelos (id uuid PK, nome, post_id, client_id, pontos jsonb, intervalo_min int, tolerancia_min int, ativo, created_by, created_at);
CREATE TABLE ronda_alertas (id uuid PK, modelo_id → ronda_modelos ON DELETE CASCADE, tipo varchar(30), minutos int, destinatarios jsonb, ativo, created_at);
CREATE TABLE ronda_alertas_disparados (id uuid PK, alerta_id → ronda_alertas, tipo, ronda_id, modelo_id, post_id, employee_id, employee_nome,
   latitude, longitude, foto_url, mensagem, detalhe jsonb, occurrence_id, disparado_em, notificado jsonb, status, reconhecido_em/por, encerrado_em/por);
CREATE UNIQUE INDEX ux_ronda_disp_alerta_ronda ON ronda_alertas_disparados (alerta_id, ronda_id) WHERE alerta_id IS NOT NULL AND ronda_id IS NOT NULL;
CREATE INDEX ix_ronda_disp_tipo_status ON ronda_alertas_disparados (tipo, status, disparado_em);
ALTER TABLE inspection_rounds ADD COLUMN modelo_id uuid;
CREATE TABLE op_setores (id uuid PK, client_id, contract_id, nome, responsavel, email, whatsapp, ativo, created_at);
ALTER TABLE op_chamados ADD COLUMN setor_id uuid, ADD COLUMN solicitante_contato varchar(160), ADD COLUMN notificado jsonb DEFAULT '[]';
```
Sem risco de lock: `inspection_rounds` tem 83 linhas no sandbox, `op_chamados` 0–18.

### Telas (deep-link `/redesign/operacional?t=<id>`)
| id | grupo | o quê |
|---|---|---|
| `ronda-modelos` | g-rondas | modelo × posto × cliente × pontos em ordem × intervalo × tolerância × nº alertas/rondas; ações **Agendar ronda** (nasce `inspection_rounds` agendada com `modelo_id`) e Desativar |
| `ronda-modelo-novo` | g-rondas | form: nome, posto/cliente, intervalo, tolerância, pontos (uma linha por ponto `nome; lat; lng; raio_m; foto`) |
| `ronda-alertas` | g-rondas | alerta × tipo × limite × destinatários × disparos/abertos; painel «últimos disparos» com quem foi avisado e o status |
| `ronda-alerta-novo` | g-rondas | form: modelo, tipo (5), minutos, e-mails, colaborador p/ WhatsApp |
| `ronda-mapa` | g-rondas | **tabela** por ronda (24 h): agendada/início/fim, batidos n/m, `✓/✗ ponto` na ordem, pulados, atraso (min + motivo), fora de ordem; botão **Avaliar agora** (motor) |
| `panicos` | g-rondas | quando × quem × posto × GPS × mensagem (📷) × ocorrência × avisados × situação; **Reconhecer** / **Encerrar** |
| `setores` | g-comunicacao | setor × cliente × contrato × responsável × e-mail × WhatsApp × chamados/vivos; Desativar |
| `setor-novo` | g-comunicacao | form |
| `chamado-novo` (F8) | g-comunicacao | ganhou **Setor** (avisa o responsável) e **Contato de quem pediu** (avisado ao resolver) |

### Regras do motor (`avaliar_ronda`, pura — o oráculo a confere)
- `ronda_atrasada`: agendada e `agora > agendado(UTC) + tolerância` (não iniciada); ou em andamento e `agora > início + intervalo + tolerância`.
- `ponto_pulado`: só ronda **concluída**; pontos do modelo sem checkpoint casado → detalhe `{pulados: [nomes]}`.
- `fora_de_sequencia`: índices batidos não são não-decrescentes.
- `sem_movimento`: em andamento e último checkpoint (ou início) há mais de `minutos` (ou intervalo).
- `minutos` do alerta sobrepõe a tolerância/intervalo do modelo. Um disparo por (alerta, ronda) — `ON CONFLICT DO NOTHING`; só o que nasce agora notifica.
- Ponto batido: `extra_data->>'ponto'` = nome (case-insensitive) → `post_id` do ponto → GPS a ≤ `raio_m` (padrão 50 m).

### Pânico
`POST /api/v1/operacional/rondas/panico` (multipart: `lat`, `lng`, `post_id?`, `ronda_id?`, `mensagem?`, `foto?` JPEG/PNG/WebP ≤10 MB).
Posto = `post_id` → 1º posto da ronda → `employees.posto_atual_id`; sem posto → 422. Grava o disparo, cria a ocorrência
**grave/incidente/operacional** pelo `ss.criar_ocorrencia` (mesmo caminho do livro da F8), liga `occurrence_id`, avisa a união dos
destinatários dos alertas tipo `panico` do posto/cliente, tudo no mesmo commit. Foto em `UPLOADS_DIR/rondas/panico/`, servida por
`GET /api/v1/operacional/rondas/fotos/panico/{nome}`. Ação cancelada apaga o arquivo.

## 4. Oráculo

Comando (contrato): `run` do container efêmero com `-e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD=` e
`--tmpfs /app/logs:rw,mode=1777 --tmpfs /app/uploads:rw,mode=1777` (**`mode=1777` é necessário**: o processo é o usuário
`erp` e o tmpfs nasce root → `PermissionError: /app/logs/app.log`, exit 3 — o contrato diz só `:rw`).

**VERMELHO**: §1. **VERDE** (worktree, sandbox):
```
  ✓ esquema: ronda_modelos.pontos · ronda_alertas.destinatarios · ronda_alertas_disparados.notificado · inspection_rounds.modelo_id
  ✓ esquema: op_setores.email · op_chamados.setor_id · op_chamados.notificado · op_chamados.solicitante_contato
  ✓ esquema: índice ÚNICO (alerta_id, ronda_id) — a trava da idempotência
  ✓ motor: 1ª rodada gerou 2 (esperado 2), 2ª rodada gerou 0 (esperado 0)
  ✓ ponto_pulado: exatamente 1 disparo, para a ronda concluída · detalhe nomeia o ponto pulado (Garagem)
  ✓ ronda_atrasada: exatamente 1 disparo, para a ronda 45 min atrasada; a de 5 min não · dentro da tolerância não dispara
  ✓ notificação: 2 destinos registrados e o externo ficou SIMULADO — [('jjesus@conectamais.pro','simulado'), ('sindico@externo.invalid','simulado')]
  ✓ idempotência global: nenhum (alerta, ronda) repetido na tabela
  ✓ pânico: disparo aberto · ocorrência GRAVE aberta no posto · 3 destinatários simulados · nenhum panico sem ocorrência · Reconhecer muda o status
  ✓ chamado: setor_id gravado · responsável do setor avisado (simulado) · resolver avisou o solicitante (evento=resolucao)
  ✓ régua: casa por nome · casa por GPS dentro do raio · NÃO casa a 230 m (raio 40)
  fixtures apagadas (sobra: 0)
TOTAL falhas DGX U4: 0            exit=0
```
Vizinhos: `test_oraculo_ronda_com_foto.py` → `OK ... exit=0`; `test_oraculo_operacional_dgx.py` → `TOTAL falhas operacional DGX F8: 0`.

**Prova HTTP (8234)**: 9 telas no grupo certo; `setor-novo` 200; `ronda-modelo-novo` 200 (3 pontos) e 400 com lat inválida;
3 alertas 200; `ronda-modelo-agendar` 1 h atrás → `RON-2026-00084`; `ronda-avaliar` #1 = 1 disparo `ronda_atrasada` (2 e-mails
simulados), #2 = 0; `ronda-mapa` mostra a ronda com «1 atrasada»; `POST /rondas/panico` com PNG → 201, `OCO-2026-00006`, foto em
disco (69 b) e `GET /fotos/panico/…` 200 image/png; foto `text/plain` → 422; `panico-reconhecer` 200, `panico-encerrar` 200,
reconhecer de novo 409; `chamado-abrir` com setor → «#18 aberto · email simulado»; `chamado-resolver` → notificado ganha
`whatsapp simulado evento=resolucao`; desativar setor/modelo 200. Fixtures apagadas (sobra 0). **Nenhum e-mail nem WhatsApp real saiu**
(SMTP zerado + `destinatario_permitido` + `_em_sandbox`).

## 5. O que NÃO foi feito e por quê

- **`channel_dispatcher`** não foi usado: é motor **síncrono** de fila (`NotificationQueue` + `NotificationChannel` por tenant, ORM
  `Session`). Usá-lo daqui exigiria enfileirar, configurar canal e despachar em outra thread. Reusei o que as outras frentes usam:
  `core.mailer.send_email` (já tem a parede de sandbox) e `send_text_message`. A simulação em sandbox está em `ra.notificar`.
- **Motor sem agendamento**: `avaliar_rondas` roda pelo botão «Avaliar agora» e pela função. A entrada no beat é do orquestrador
  (`celery_app.py`/`operacional/tasks.py`): uma task de ~6 linhas chamando `asyncio.run(avaliar_rondas(db))` a cada 5 min, fila `operacional`.
- **Botão de pânico no app** (`frontend/` intocado): `ronda-mobile/page.tsx` precisa de um botão vermelho que faça
  `POST /api/v1/operacional/rondas/panico` (multipart) com `lat/lng` do `navigator.geolocation`, `ronda_id` da ronda ativa e,
  opcionalmente, a foto do `CameraCaptura`. Resposta: `{message, occurrence_code, notificado}`. Offline: enfileirar no `filaOffline`
  como item `panico` (a rota é idempotente por conteúdo? **não** — se for para a fila, adicionar `chave_idempotente` na tabela; deixei fora).
- **Ponto batido pelo app**: o app hoje manda `post_id` e GPS no checkpoint; para casar por nome deve enviar `extra_data.ponto = <nome do ponto>`.
  Sem isso o casamento é por GPS (raio) ou por posto — e um modelo com 3 pontos no mesmo posto casa **todos** no índice do 1º ponto por posto.
  Por isso a régua tenta nome antes de posto. Fica no §7.
- **Horários do modelo DGX** (dom…sáb, feriado, "replicar a cada N", total de realizações) e **QR/NFC** por ponto: não implementados —
  `pontos` jsonb aceita `qr` livre, ninguém lê. Ronda nasce só por «Agendar ronda» ou pelo app.
- **Editar modelo/alerta/setor**: só criar/desativar (ponytail). Editar = desativar + criar.
- **`fora_de_sequencia` e `sem_movimento`** têm regra e oráculo de régua, mas **não** têm caso de banco no oráculo (só `ponto_pulado` e
  `ronda_atrasada`). Estão cobertos pela mesma função pura.
- **SMTP por contrato** (DGX): não. É multi-tenant de escolta; um remetente basta.
- **Aceite do pânico pelo app** (DGX `ConfirmarAceitacao`): o aceite é pela tela `panicos` (Reconhecer). Sem push para o celular.
- **`checar_regressao.py`**: não editei. O oráculo entra pela varredura `scripts/orq/test_*.py`.

## 6. Como o Jordan testa amanhã (depois do bake)

1. Operacional → **Rondas & Ocorrências → Novo modelo**: nome «Ronda noturna», posto, intervalo 30, tolerância 5, pontos
   (3 linhas: `Portaria; -3.1019; -60.0250; 40; sim` / `Garagem; -3.1021; -60.0248` / `Piscina`). Salvar.
2. **Novo alerta**: modelo acima, tipo «Ronda atrasada», e-mail `jjesus@conectamais.pro`. Repita com «Ponto pulado» e «Pânico».
3. **Modelos de ronda** → na linha, **Agendar ronda** com «Quando» = 1 hora atrás. Vá em **Mapa da ronda**: a ronda aparece
   com «Atraso: 6x min (não iniciada)». Clique **Avaliar agora** → «1 disparo novo». Clique de novo → «0». Em **Alertas de
   ronda** o painel mostra o disparo e «jjesus@conectamais.pro · enviado» (em produção o e-mail chega de verdade).
4. No celular (ou curl): `POST /api/v1/operacional/rondas/panico` com `lat`, `lng`, `post_id`. Em **Pânicos** aparece a linha
   aberta com a ocorrência `OCO-…`; **Reconhecer** → **Encerrar**. No **Livro de ocorrências** do posto a ocorrência grave está lá.
5. **Comunicação → Novo setor**: «Manutenção», e-mail do zelador. **Novo chamado** com esse setor e «Contato de quem pediu» =
   seu e-mail. A mensagem de retorno diz «email enviado». **Chamados** → Resolver → você recebe o e-mail de resolução.
6. Trava, no container: `docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_u4_rondas_chamados.py`.

## 7. Decisões que só o dono pode tomar

1. **Quem recebe o pânico quando não há alerta configurado?** Hoje: ninguém (fica só a ocorrência + a tela). Alternativa:
   cair para `posts.supervisor_phone`/`emergency_phone` (uma linha em `disparar_panico`).
2. **Ronda atrasada notifica o inspetor também?** Hoje só os destinatários do alerta.
3. **Agendamento do motor** (5 min? 1 min?) e **janela** (48 h): o Jordan decide; o orquestrador liga no beat.
4. **Nome do ponto no app**: pedir ao front que mande `extra_data.ponto` (o select dos pontos do modelo). Sem isso, modelo com
   vários pontos no mesmo posto só casa por GPS — e a portaria de um condomínio tem raio de 50 m sobre a garagem.
5. **Pânico offline**: vale enfileirar (e aí a rota ganha chave idempotente) ou pânico sem sinal é telefone?
6. **WhatsApp em produção**: `notificar` chama `send_text_message` de verdade fora do sandbox. Confirmar que o número do
   responsável do setor e o `employees.celular` são discáveis (lição de 11/09: JID ≠ número).
