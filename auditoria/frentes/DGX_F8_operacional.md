# DGX F8 — Operacional: coberturas, livro do posto, checklist de supervisão, chamados, avisos (24/09/2026)

**Branch:** `dgx/f8-operacional` · **Módulo:** operacional · **Sandbox:** `conecta_pro_staging`, container `teste-dgx-f8` (8208, parado ao fim)

## 1. Estado antes (medido: staging e produção, 24/09 00:30 Manaus)

| Fonte | Produção | Staging | O que já existia |
|---|---|---|---|
| `substitutions` | 0 | 0 | tabela do fluxo falta → substituto (`falta_substituto_controller`): 1 linha por turno, `shift_id NOT NULL`, sem período, sem folga trabalhada, sem horas. Abas `substituicoes`, `registrar-falta`, `escalar-substituto` no g-escalas. `op_substituicao_propostas` 0 (universo paralelo, não tocado) |
| `occurrences` | 5 | 5 | todas de teste (E2E/QA); `occurrence_category_configs` 0; `occurrence_attachments` 0; a escrita real é `POST /redesign/action/occurrence` (repositório + `OccurrenceCreate` de `schemas/occurrence.py`, com employee_id/witnesses/occurred_at) |
| `checklist_templates/itens/preenchido/respostas` | 0 | 0 | tabelas do módulo **Campo** (checklist de OS): `checklist_preenchido.ordem_servico_id NOT NULL` + UNIQUE; sem tela nenhuma |
| `communication_announcements` | 13 | 13 | 10 publicadas (`todos`), 1 published, 2 cancelled; `comunicado-novo` só tinha título/conteúdo/prioridade/categoria — **sem vigência, sem público**; `comunicados-leituras` conta reads por comunicado, não por pessoa |
| `client_portal_tickets` | 5 | 5 | tickets do portal do cliente (ABERTO/EM_ANDAMENTO/RESPONDIDO/FECHADO), `PortalTicketService` só escopo do cliente; `client_tickets` 0 (duplicata morta) |
| `op_chamados` | não existia | não existia | — |
| `operacional_passagens_turno` 2 · `operacional_post_orders` 1 · `visitas` de acompanhamento (check-in do gerente) | | | as fontes que o livro une |
| `shifts` | | 4810 ativos, 40 `is_off_day` | 12x36: o dia de folga **não tem linha** — a folga é a ausência de turno com escala em volta |
| `users.employee_id` | | 21 colaboradores com **2 logins** | pegou o painel de avisos (ver §4) |

Oráculo no nascimento (contra o backend da branch base, `git archive`): **VERMELHO** —
`(a–f) serviços/builder da F8 não importam: ImportError: cannot import name '_dgx_f8_operacional'`.

## 2. O que o DGX tem

- `/frontend/coberturas/index`: Motivo (Volante · Férias · Falta · Afastamento · Atestado · Folga · Atividade Externa) · Início · Término · Colaborador (cobertura) · Coberto · Contrato · Vaga · Função · Escala · **Folga Trabalhada** (checkbox) · Tratativa.
- `/frontend/livroocorrencias`: Usuário · Cliente · Contrato · Data · Origem (Q-Watcher/Vigilância) · Descrição · Visualizado · Status (Pendente/Finalizado) · botão Finalizar.
- APP Q-Watcher: Chamados (`SetorChamados`: título, solicitante, contrato, setor, descrição), Dashboard Checklist/Supervisão, Setores/Equipamentos (`ContratoSetores`).
- `Avisos/PainelAvisos` (sem modal de inclusão exposto).

## 3. O que foi feito

| Arquivo | Papel |
|---|---|
| `backend/modules/operacional/services/cobertura_service.py` | regra da cobertura: `registrar()`, `folga_no_dia()`, `_ensure()` (DDL em `substitutions`), `MOTIVOS` (7 do DGX → `reason`), `CoberturaErro(status)` |
| `backend/modules/operacional/services/supervisao_service.py` | livro (união SQL), `criar_ocorrencia()` (mesmo repositório da ocorrência rápida), checklist (`criar_modelo`, `executar`, semente), chamados (`abrir/assumir/resolver`), avisos (`criar_aviso` pelo serviço de comunicados, `avisos()` painel), `_ensure()` (DDL checklist + `op_chamados`) |
| `backend/modules/operacional/services/livro_ocorrencias_pdf.py` | PDF do dia no timbrado padrão-ouro (`pdf_branding.header_footer`, A4 retrato) |
| `backend/modules/operacional/controllers/redesign_builders/_dgx_f8_operacional.py` | 13 telas + 9 ações + 1 GET de PDF (`router`) |
| `.../redesign_builders/operacional.py` | plug: import do `router` + `include_router` + `await _telas_f8(db, out)` antes de `montar_grupos` — `# dgx f8` |
| `.../redesign_builders/_op_grupos.py` | abas no FIM de g-escalas (2), g-postos (7), g-comunicacao (4) |
| `backend/scripts/orq/test_oraculo_operacional_dgx.py` | oráculo (a)–(f) |

**DDL que `_ensure` aplica em produção no 1º acesso** (idempotente; roda em `telas()` e em cada ação):
```sql
-- coberturas (substitutions)
ALTER TABLE substitutions ALTER COLUMN shift_id DROP NOT NULL;          -- férias: coberto pode não ter turno no dia
ALTER TABLE substitutions ADD COLUMN IF NOT EXISTS cobertura_id uuid;   -- amarra os dias de um período
ALTER TABLE substitutions ADD COLUMN IF NOT EXISTS folga_trabalhada boolean;
ALTER TABLE substitutions ADD COLUMN IF NOT EXISTS horas numeric(5,2);
ALTER TABLE substitutions ADD COLUMN IF NOT EXISTS shift_cobertura_id uuid;  -- turno espelho criado p/ o cobertura
ALTER TABLE substitutions ADD COLUMN IF NOT EXISTS alocacao_id uuid;         -- movimentação da F5 (férias/afastamento)
CREATE INDEX IF NOT EXISTS ix_substitutions_cobertura ON substitutions (cobertura_id);
-- checklist (tabelas do Campo, supervisão sem OS)
ALTER TABLE checklist_preenchido ALTER COLUMN ordem_servico_id DROP NOT NULL;  -- o UNIQUE aceita vários NULL
ALTER TABLE checklist_preenchido ADD COLUMN IF NOT EXISTS post_id uuid;
ALTER TABLE checklist_preenchido ADD COLUMN IF NOT EXISTS executado_por_nome varchar(200);
ALTER TABLE checklist_preenchido ADD COLUMN IF NOT EXISTS ocorrencia_id uuid;
CREATE INDEX IF NOT EXISTS ix_checklist_preenchido_post ON checklist_preenchido (post_id);
-- semente: 1 modelo 'Supervisão de posto' (CHK-SUP-001, categoria_equipamento='supervisao', tipo_servico='vistoria')
--          com 10 itens (uniforme, crachá, livro, rádio, iluminação, câmeras, portão, extintor, banheiro*, instruções=nota)
--          INSERT ... ON CONFLICT (codigo) DO NOTHING; itens só quando o modelo nasce
-- chamados
CREATE SEQUENCE IF NOT EXISTS op_chamados_numero_seq;
CREATE TABLE IF NOT EXISTS op_chamados (id uuid PK, numero int DEFAULT nextval, post_id, condominio_id, aberto_por, solicitante_nome,
  canal, categoria, prioridade, descricao, status, atribuido_a, aberto_em (Manaus), atendido_em, resolvido_em, sla_min, resolucao, created_by);
CREATE INDEX IF NOT EXISTS ix_op_chamados_status ON op_chamados (status, aberto_em);
```
Nada em `communication_announcements` nem em `occurrences`.

### 3.1 Coberturas (g-escalas)
- **Decisão de modelo — uma linha de `substitutions` por DIA**, amarradas por `cobertura_id`. É como o turno existe (`shifts` é diário) e é o que o fluxo falta → substituto já grava; a aba `substituicoes` antiga continua lendo tudo. Cada dia grava `folga_trabalhada`, `horas`, `shift_cobertura_id`.
- **Folga trabalhada é DERIVADA de `shifts`, não marcada** (o DGX tem um checkbox): no dia, o cobertura tinha linha `is_off_day`, OU não tinha turno nenhum mas tem escala na quinzena em volta (12x36). Quem não tem escala nenhuma (volante) fica `false`. Calculada ANTES de criar o turno espelho.
- Turno espelho para o cobertura no posto = o mesmo INSERT do `escalar_substituto` (grade, presença e mapa enxergam quem está lá). Referência de horário: turno do coberto no dia → turno mais próximo dele no posto → horário padrão do posto → **422** (nunca inventa).
- Regras: coberto ≠ cobertura; ativos; período ≤ 62 dias, dentro de ±60 dias; cobertura com turno no dia (ou noturno na véspera) → **409**; coberto já coberto nesse posto/dia → 409; falta/atestado marcam o turno do coberto `missed` (como `registrar_falta`).
- **Férias/afastamento → `movimentacao_service.alocar` (F5)** com `cobertura_de_ferias|afastamento`, `coberto_employee_id`, `data_fim` = término. A F5 valida (coberto com férias aprovadas / afastamento ativo) e é chamada ANTES das linhas do dia — o oráculo prova que a recusa não deixa linha para trás.
- Tela `/redesign/operacional?t=coberturas`: Período · Coberto · Cobertura · Posto · Motivo · Dias · **Folga trab. (N de M)** · Horas · Mov. (F5) · Registrou · Situação; filtros Mês e Posto; painéis **resumo por pessoa no mês** (mês atual e anterior: coberturas · em folga · horas) — a base para HE/folga compensatória.
- Form `cobertura-nova`: coberto, cobertura, posto, motivo (7), início, término (vazio = só o dia), observação; `confirm` + `showResult`.
- Ação: `POST /api/v1/redesign/action/cobertura-registrar`.

### 3.2 Livro de ocorrências do posto (g-postos)
- **Sem tabela nova**: união, por posto e dia (hora de Manaus; `occurred_at`/`checkin_at` são naive-UTC e viram Manaus no SQL), de `occurrences` + `operacional_passagens_turno` + `visitas` de acompanhamento interno (check-in do gerente; posto = 1º posto ativo do cliente da visita) + `operacional_post_orders` (instrução), com quem registrou. 30 dias, ordem cronológica.
- `livro-ocorrencias`: Quando · Posto · Tipo · Registro · Quem · Grau/ref.; filtros **Posto** e **Dia**; **PDF do dia por linha** (chip `docs`).
- `livro-ocorrencia-nova`: posto, tipo (14 do enum), gravidade, dia + hora, título, descrição, colaborador envolvido, envolvidos/testemunhas, foto (URL → `attachments`). Grava por `OccurrenceRepository.create` — o mesmo caminho da ocorrência rápida (código `OCO-AAAA-NNNNN`).
- `livro-ocorrencias-pdf` (form posto + dia → `doc`) e `GET /api/v1/redesign/livro-ocorrencias/{post_id}/{AAAA-MM-DD}/pdf` — padrão do `relatorio-pagamento-pdf`. Medido: HTTP 200, `application/pdf`, 37.790 bytes, `%PDF-`.

### 3.3 Checklist de supervisão (g-postos)
- Usa as tabelas do Campo. Tipo do DGX (posto|veiculo|ronda|supervisao) em `categoria_equipamento` (coluna livre que existia); `tipo_servico='vistoria'` (valor do enum do Campo, para a leitura de lá não quebrar); item: sim/não → `sim_nao`, nota → `numero`, texto, foto.
- `checklist-modelos` (código, nome, tipo, itens, obrigatórios, execuções, ativo) · `checklist-modelo-novo` (nome, tipo, **itens em textarea, uma linha por item: `pergunta | tipo | obrigatório`**) · `checklist-executar` · `checklist-execucoes` (quando, modelo, posto, quem, itens, conformes, % conforme, não conformes, ocorrência).
- **Form genérico com N itens, sem tocar o frontend**: `checklist-executar` gera um campo por item de TODOS os modelos ativos (com prefixo `[modelo]` quando há mais de um) + select do modelo; a ação só lê os itens do modelo escolhido. Sim/não = select Conforme / NÃO conforme / não avaliado; nota = number (≥ 7 conforme); texto/foto = texto (vazio = sem resposta). Obrigatório sem resposta conta como não conforme.
- **Item obrigatório reprovado → UMA ocorrência por execução** (`nao_conformidade_documental`, `grave` se ≥ 3, senão `moderada`; descrição lista os itens), ligada em `ocorrencia_id`. Nunca duas.
- Ações: `checklist-modelo-criar`, `checklist-executar`.

### 3.4 Chamados (g-comunicacao)
- `op_chamados` + **união só-leitura com `client_portal_tickets`** (prefixo `P-`, origem portal; status ABERTO→aberto, FECHADO→resolvido, resto→em atendimento). Não duplica: o cliente continua abrindo pelo portal.
- SLA por prioridade: urgente 60 min · alta 240 · normal 1440 · baixa 4320. Aberto/em atendimento além do prazo = **SLA VENCIDO** (vermelho); resolvido = no prazo / fora do prazo. Abertos primeiro.
- Ações por linha (só `op_chamados`): **Assumir** (aberto → em_atendimento, `atendido_em`, `atribuido_a` = eu ou quem escolher) e **Resolver** (ou cancelar; `resolvido_em`, `atendido_em = coalesce(atendido_em, agora)` → nunca resolvido antes de atendido). `chamado-novo`: posto, aberto por (cliente|supervisor|colaborador|sistema), canal (whatsapp|telefone|app|portal), nome, categoria (8), prioridade, descrição.
- Ações: `chamado-abrir`, `chamado-assumir?chamado_id=`, `chamado-resolver?chamado_id=`.

### 3.5 Avisos / painel (g-comunicacao)
- `comunicados` já existia mas **sem vigência e sem público** → `aviso-novo` grava pelo MESMO serviço (`create_announcement`) com **público** todos | posto (`destinatarios_postos`) | função (resolve os ativos do cargo em `destinatarios_funcionarios`, guarda `extra_data.funcao`), **vigência** (início ≤ hoje → `publish_announcement` na hora; futuro → agendado; fim → `data_expiracao`), prioridade, categoria, exige confirmação.
- `avisos-painel`: vigentes (publicados/agendados, não expirados) × Público · Vigência · Destinatários · **Lidos · Não lidos** · Confirmações · **Quem não leu** (nomes) · Status. Régua de destinatários = a do `AnnouncementService` (todos = ativos; posto = `employees.posto_atual_id`; função = lista); lido = `communication_announcement_reads` via `users.employee_id`, **agrupado por pessoa**; "sem usuário" = colaborador sem login.
- Ação: `aviso-novo`.

**HTTP no container efêmero (8208), sandbox, fixtures apagadas ao fim (0 sobrando):**
```
13 telas: redirect para o grupo certo e presentes na aba (g-escalas 2, g-postos 7, g-comunicacao 4) · Operacional: 122 telas
livro-ocorrencia-nova → {"ok":true,"code":"OCO-2026-00006"} · descrição curta → 400
livro-ocorrencias-pdf → doc {url:/api/v1/redesign/livro-ocorrencias/<posto>/2026-09-24/pdf, fmt:pdf} · GET → 200 application/pdf 37790 bytes
chamado-abrir (alta) → "#5 aberto (SLA 4 h)" · resolver sem assumir → "resolvido — dentro do SLA" · assumir depois → 409
checklist-modelo-criar → CHK-SUP-002 com 4 itens · tipo inválido → 400
aviso-novo (função, início amanhã) → "agendado para 2026-09-25" · público posto sem posto → 400
cobertura-registrar coberto = cobertura → 422
telas depois: livro 26 linhas (1 fixture, docs=1) · chamados 6 (1 fixture, "no prazo") · avisos 12 (1 fixture, 30 destinatários) · modelos 2
```

## 4. Oráculo

```bash
WT=$(git rev-parse --show-toplevel)
ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')
docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" --tmpfs /app/logs:rw,mode=1777 --tmpfs /app/uploads:rw,mode=1777 \
  -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env $ENVS conecta-pro-backend:latest \
  python3 /app/scripts/orq/test_oraculo_operacional_dgx.py
# em produção: docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_operacional_dgx.py
```
ANTES (24/09 00:48, backend da branch base via `git archive`):
```
  ✗ (a–f) serviços/builder da F8 não importam: ImportError: cannot import name '_dgx_f8_operacional' from 'modules.operacional.controllers.redesign_builders'
  ✓ fixtures apagadas ao fim: 0 sobrando
TOTAL falhas operacional DGX F8: 1
```
DEPOIS (24/09 00:56):
```
  ✓ (a) 1 dia de cobertura gravado em substitutions: 1
  ✓ (a) folga_trabalhada gravada=True == recontada em shifts=True (sem o espelho)
  ✓ (a) turno espelho do cobertura no posto no dia: 1
  ✓ (a) fixture escolhida estava de folga (escala na quinzena, sem turno no dia)
  ✓ (a) dia com turno próprio recusado com 409: ADEMIR SALUSTIANO DE SOUZA FILHO já tem turno em Condomínio Villa dos Pássaros em 29/09/2026 — nunca dois postos no mesmo dia.
  ✓ (a) férias sem férias aprovadas recusada com 422: O coberto não tem férias aprovadas em 02/10/2026.
  ✓ (a) recusa da F5 não deixou linha para trás: 1 → 1
  ✓ (b) livro do dia: tela 1 == união recontada 1
  ✓ (b) ocorrência recém-registrada OCO-2026-00006 está no livro
  ✓ (b) livro em ordem cronológica
  ✓ (c) modelo semente 'CHK-SUP-001' com 10 itens: 10
  ✓ (c) 1 obrigatório reprovado → delta de ocorrências = 1 (esperado 1)
  ✓ (c) ocorrência ligada em checklist_preenchido.ocorrencia_id e no posto certo: 1
  ✓ (c) % conforme gravado 90.0 == recontado 90.0
  ✓ (c) tudo conforme → 0 ocorrência, 100.0%
  ✓ (d) urgente → SLA 60 min: 60
  ✓ (d) atendido_em 2026-09-24 00:56:39.229065 ≤ resolvido_em 2026-09-24 00:56:39.254789
  ✓ (d) sla_cumprido devolvido True == recomputado True
  ✓ (d) chamado aberto há 2 h com SLA 1 h pintado como SLA VENCIDO: SLA VENCIDO
  ✓ (e) fixture nasce agendada (início amanhã) — ninguém é notificado
  ✓ (e) destinatários no painel 12 == ativos do posto 12
  ✓ (e) público do posto (12) é menor que a empresa (50)
  ✓ (f) 13 telas montadas sem FALHOU (faltam=[], falhou=[])
  ✓ fixtures apagadas ao fim: 0 sobrando
TOTAL falhas operacional DGX F8: 0
```
**O oráculo pegou dois defeitos meus antes de virar verde:** (1) o painel de avisos contava **14** destinatários num posto de **12** — 21 colaboradores têm 2 logins em `users` e o CTE agrupava por usuário; corrigido para agrupar por pessoa. (2) a fixture de 2 dias caiu num 12x36 que trabalha no D+1 → 409 correto do serviço; a fixture virou 1 dia. Fora do oráculo, o HTTP pegou o terceiro: `extra_data` do comunicado nasce como jsonb `null` (não SQL NULL) e `null || {}` virava ARRAY — corrigido com `jsonb_typeof`.

Rodados depois, verdes: `test_oraculo_movimentacao_com_motivo.py` (TOTAL 0; (e) 0 × 0 à 00:53 porque a régua conta turnos de hoje na hora de Manaus) e `test_oraculo_grid_bate_com_a_triagem.py` ("régua hoje: 29 · mapa: 29 · OK grade/mapa").

## 5. O que NÃO foi feito e por quê

- **Folga trabalhada como checkbox** (DGX) — não; é derivada de `shifts`. Se um dia a escala estiver errada, a folga também estará: o instrumento certo é corrigir a escala, não marcar na mão. Sem coluna de "tratativa".
- **Vaga/contrato/sequência** na cobertura — não (mesma razão da F5: aqui a vaga é posto + função).
- **Cobertura por diarista** — não; continua no fluxo `escalar-substituto` (que já lança a diária). A tela `coberturas` mostra essas linhas (substituto "— (sem substituto)" quando é diarista, porque `substitute_employee_id` fica nulo lá).
- **Encerrar/cancelar cobertura** — não (fora do brief). Para desfazer: `substitutions.is_active=false` + apagar o turno espelho; hoje é SQL do DP.
- **Livro: "Finalizar/Visualizado"** do DGX — não. As ocorrências já têm `resolver-ocorrencia` no g-rondas; passagem tem "Marcar lida". Não criei um terceiro estado.
- **Livro: check-in do gerente cai no 1º posto ativo do cliente** — `visitas` só tem `cliente_id`; Conecta Village (5 postos, 1 cliente) vai sempre para "Jardinagem — Conecta Village". Registrado; o certo é a visita guardar `post_id` (é do módulo Campo).
- **Foto no livro/checklist é URL**, não upload — o form genérico não tem campo de arquivo para N itens; `scr.attach` existe para 1 arquivo por tela, ficou de fora.
- **Checklist: setores/equipamentos por contrato** (`ContratoSetores`) e dashboards de supervisão — não. Itens condicionais, pesos e assinaturas das tabelas do Campo também não são usados.
- **Chamados do portal: Assumir/Resolver** — não; `PortalTicketService` é escopo do cliente e tem `client_portal_ticket_messages`; escrever de fora sem a mensagem de resposta seria fingir atendimento. Só leitura, com prefixo `P-`.
- **Aviso: público "função" grava a LISTA de pessoas** (`destinatarios_funcionarios`) — quem entrar no cargo depois não recebe. O serviço não tem alvo por cargo (`ROLE` é role de usuário, sem coluna).
- **`tenant_id` do comunicado = id do usuário** (`_get_tenant_id`): `get_for_user` filtra por tenant, então o "não lidos" do MCP/app só vê os comunicados criados pelo próprio criador. Defeito do serviço existente, não corrigido (fora do módulo desta frente no sentido estrito — é `communication/`), registrado em §7.
- **Frontend** — nada editado; sem JSON de menu (as abas vêm de `_op_grupos`). `checar_regressao.py` não registrado (orquestrador).
- **Oráculo (a) do F5** ("turno de hoje ⇒ alocação no condomínio"): uma cobertura de FALTA de hoje por alguém de outro condomínio cria turno espelho sem alocação — o mesmo que o `escalar-substituto` já fazia. A fixture usa D+3 de propósito; em produção esse oráculo pode ficar vermelho no dia de uma cobertura de falta cruzada (férias/afastamento não, porque alocam).

## 6. Como o Jordan testa amanhã

1. Operacional → **Escalas & Turnos** → **Nova cobertura**: coberto = alguém com turno amanhã, cobertura = alguém de FOLGA amanhã (12x36 no dia sem turno), posto, motivo *Falta*, início amanhã → Registrar. Em **Coberturas**: linha com "Folga trab. 1 de 1", horas do turno; painel "Resumo por pessoa — 09/2026" com 1 cobertura em folga. Tente com o cobertura num dia em que ele trabalha → 409. Tente *Férias* com coberto sem férias aprovadas → 422 e nada gravado.
2. **Postos & Presença** → **Registrar no livro**: posto, tipo, gravidade, descrição → Registrar. **Livro de ocorrências**: filtre o posto e o dia; a linha aparece com "Jordan Jesus"; clique **Abrir** no chip PDF → PDF timbrado do dia. **Livro do dia (PDF)** faz o mesmo por formulário.
3. **Checklist · executar**: modelo "Supervisão de posto", posto, marque tudo Conforme e o Extintor NÃO conforme, nota 9 → Concluir: "9 conforme(s), 1 não conforme — 90%. Ocorrência gerada". Em **Checklist · execuções** a linha mostra 90% e o código OCO-…; em Rondas & Ocorrências → Ocorrências ela está lá. Repita tudo conforme → 100%, sem ocorrência.
4. **Checklist · novo modelo**: nome "Viatura", tipo Veículo, itens `Pneus | sim_nao | s` / `Óleo | sim_nao | s` / `Km | texto | s` → o modelo aparece em Modelos e os campos em Executar com o prefixo `[Viatura]`.
5. **Comunicação** → **Novo chamado**: cliente, WhatsApp, síndico, prioridade *Urgente* → "#N aberto (SLA 1 h)". Em **Chamados**: linha vermelha no topo com "até HH:MM"; **Assumir** → em atendimento; **Resolver** → "no prazo". Os 5 do portal aparecem com `P-` sem botão.
6. **Novo aviso**: público *Posto* → escolha Ideal Flores, início hoje → Publicar. Em **Avisos · painel**: Destinatários 12, Lidos 0, "Quem não leu" com os 12 nomes. Peça a alguém do posto para abrir o comunicado no app → Lidos 1.

## 7. Decisões que só o dono pode tomar

- **Folga trabalhada vira HE ou folga compensatória?** O resumo por pessoa/mês já dá o número; a folha não lê nada disto ainda (paralelo cego). Decidir a rubrica e quem aprova.
- **Cobertura de falta cruzada entre condomínios** não gera alocação (F5) — só férias/afastamento. Manter assim (falta é do dia) ou alocar por 1 dia?
- **21 colaboradores com 2 logins** em `users` (mesmo `employee_id`): o painel já agrupa por pessoa, mas o sino/não-lidos do app é por usuário — qual login vale?
- **`tenant_id` do comunicado = id de quem criou**: o "não lidos" por pessoa só enxerga comunicados do mesmo criador. Corrigir no serviço de comunicação (outra frente) ou aceitar que só o Jordan cria avisos.
- **Chamados do portal**: dar Assumir/Resolver por aqui (respondendo com mensagem ao cliente) ou manter o atendimento só pelo portal?
- **Quem pode registrar cobertura/checklist/chamado**: hoje qualquer usuário autenticado do redesign (mesma parede das outras frentes). Restringir a supervisor/gerente?
- **Notificação ao publicar aviso**: `publish_announcement` dispara `send_bulk` para todos os destinatários — está ligado; confirmar que é o comportamento desejado para avisos por posto.
