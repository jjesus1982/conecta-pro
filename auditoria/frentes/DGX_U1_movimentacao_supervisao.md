# DGX U1 — Movimentação em dois passos + Supervisão planejada (realizado × planejado) (24/09/2026)

**Branch:** `dgx/u1-movimentacao-supervisao` · **Módulo:** operacional · **Sandbox:** `conecta_pro_staging`, container `teste-dgx-u1` (8231, parado ao fim)

## 1. Estado antes (medido no staging, 24/09 06:00 Manaus)

- `employee_alocacoes`: 73 linhas, 51 ativas, 20 colunas (F5). `aprovado_por/aprovado_em` existem, mas **quem registra aprova** —
  `alocar()` grava `aprovado_por = user_id` na mesma linha. Não havia estado "pendente"; `op_movimentacao_pedidos` não existia.
- Quem lê `employee_alocacoes` **só por data, sem `ativo`** (medido por grep): `financeiro.py:669` (folha × alocação por competência),
  `departamento_pessoal.py:431`, `:2609`, `:2793` (custo por condomínio). Os outros 14 leitores filtram `ativo`. É por isso que um
  pedido pendente NÃO pode ser uma linha nessa tabela (ver §3).
- Restrição por cliente (T3): `restricao_cliente.exigir_livre()` levanta **422** (não 409) e já é chamada dentro de `alocar()`.
- Supervisão: checklist da F8 (`checklist_preenchido.post_id`, 0 execuções no staging), `gerente-checkin` grava `visitas`
  (24 com check-in) — sem frequência, sem denominador planejado. `op_supervisao_planos`/`op_supervisao_ocorrencias` não existiam.
- Supervisores no staging: **nenhum** colaborador com cargo GERENTE/SUPERVIS; os gerentes operacionais são usuários
  (`gerente_operacional`: Eliziel, Paiva; `admin`: Pyetra) com `users.employee_id`. Ambos têm `module:dp`.
- Oráculo no nascimento (backend da branch base via `git archive`): **VERMELHO** —
  `(a–g) serviços da U1 não importam: ImportError: cannot import name 'supervisao_planejada'`.

## 2. O que o DGX tem

- `/Movimentacoes/IncluirMovimentacao` grava **pendente** (`Status=0`); a lista tem Aprovar / Editar / Excluir; ao aprovar o servidor
  recusa «Colaborador tem restrição nesse cliente» (T3 §5/§7). Depois de aprovar o grid passa de `0 / 2` para `1 / 2`.
- `ContratoSetores` → planejamentos (título, frequência diário…bienal, início/término, hora, usuários) e `Frontend/periodicidade` =
  **mapa de supervisão realizado × planejado** por diário/semanal/quinzenal/mensal; dashboards Checklist e Supervisão.

## 3. O que foi feito

| Arquivo | Papel |
|---|---|
| `backend/modules/operacional/services/movimentacao_service.py` | `pedir()`, `aprovar()`, `recusar()`, `_checar_entrada()` (extraída de `alocar`, mesma checagem), DDL de `op_movimentacao_pedidos` em `_ensure` |
| `backend/modules/operacional/services/supervisao_planejada.py` | **novo**: `deve_ocorrer()` (regra de frequência, pura), `gerar_ocorrencias()` (idempotente), `marcar_realizada()` (hook), `criar_plano()`, `ativar_plano()`, `_ensure()` |
| `backend/modules/operacional/controllers/redesign_builders/_dgx_u1_movimentacao_supervisao.py` | **novo**: 4 telas + `linhas_pedidos()` (ledger F5) + `linhas_central()` (Central) + 4 ações (`router`) + `e_dp()` |
| `.../redesign_builders/_dgx_f5_movimentacoes.py` | filtro **Situação** (pendente/ativa/recusada/encerrada), linhas de pedido no ledger, campo «Pedir aprovação do DP?» no form, ramo `pedir` na ação `movimentacao-alocar` — `# dgx u1` |
| `.../redesign_builders/aprovacoes.py` | bloco de 12 linhas: pendentes de movimentação na **Central de Aprovações** (só para `module:dp`/admin), sem linha em `agent_drafts` |
| `.../services/supervisao_service.py` · `.../redesign_builders/operacional.py` | hooks de 6 linhas (`# dgx u1`): `executar()` do checklist e `gerente-checkin` chamam `marcar_realizada` |
| `.../redesign_builders/operacional.py` · `.../redesign_builders/_op_grupos.py` | plug (import + include_router + `telas`) e 4 abas no FIM de **g-postos** |
| `backend/scripts/orq/test_oraculo_u1_movimentacao_supervisao.py` | oráculo (a)–(g) |

**Decisão de modelo — o pedido mora em `op_movimentacao_pedidos`, não em `employee_alocacoes.status`.** O brief pedia a coluna. Medido
antes de escrever: 4 leitores (§1) juntam `employee_alocacoes` **só por `data_inicio`/`data_fim`**, sem `ativo` — a folha por
condomínio (`financeiro.py:669`) somaria o salário do colaborador no condomínio de destino no dia em que o supervisor *pedisse*, antes de
qualquer aprovação; nenhum sentinela de data (`data_fim = data_inicio − 1`) engana os 4 ao mesmo tempo (`:2793` não olha `data_inicio`).
Tabela própria custa zero edição em leitor de folha e mantém UMA fonte: o pedido é um pedido; a alocação só nasce em `aprovar()`, pelo
`alocar()` de sempre, e o pedido guarda `alocacao_id`. `agent_drafts` não é tocado.

**DDL que `_ensure` aplica em produção no 1º acesso** (idempotente; roda em `telas()`, em cada ação e nos hooks):
```sql
CREATE TABLE IF NOT EXISTS op_movimentacao_pedidos (id uuid PK, employee_id, condominio_id, posto_id, funcao, data_inicio, motivo,
  coberto_employee_id, solicitado_por, solicitante_nome, observacao, status DEFAULT 'pendente' (pendente|aprovada|recusada),
  pedido_por, pedido_em (Manaus), decidido_por, decidido_em, decisao_motivo, alocacao_id);
CREATE INDEX IF NOT EXISTS ix_op_mov_pedidos_status ON op_movimentacao_pedidos (status, pedido_em);
CREATE TABLE IF NOT EXISTS op_supervisao_planos (id uuid PK, posto_id, condominio_id, supervisor_employee_id NOT NULL, checklist_template_id,
  frequencia (diaria|semanal|quinzenal|mensal), dias_semana jsonb (ISO 1=seg…7=dom), hora_inicio time, hora_fim time,
  vigencia_inicio NOT NULL, vigencia_fim, ativo DEFAULT true, observacao, created_by, created_at);
CREATE TABLE IF NOT EXISTS op_supervisao_ocorrencias (id uuid PK, plano_id REFERENCES planos ON DELETE CASCADE, data, status DEFAULT 'planejada'
  (planejada|realizada|atrasada|nao_realizada), checklist_preenchido_id, checkin_visita_id, realizada_em, realizado_por, UNIQUE (plano_id, data));
CREATE INDEX IF NOT EXISTS ix_op_sup_ocorr_data ON op_supervisao_ocorrencias (data, status);
```
Nada em `employee_alocacoes` (as 20 colunas da F5 ficam como estão). Nenhuma semente.

### 3.1 Movimentação em dois passos
- **Regra de quem faz o quê**: `e_dp(user)` = `user_has_module(user, "dp")` (admin/`all` passam; Eliziel/Paiva/Pyetra passam; `staff`
  só-operacional não). Form `movimentacao-nova`, campo «Pedir aprovação do DP?»: **Automático** (vazio) = DP/admin aloca direto, o
  resto pede; **Sim** = sempre pede; **Não** = direto só para DP/admin, senão **403**. Caminho direto do DP é o `alocar()` de ontem,
  byte a byte (oráculo da F5 verde depois, §4).
- `pedir()`: mesma checagem de entrada do `alocar` (400/422: motivo, solicitado por, ≤ 60 dias, coberto, posto ∈ condomínio), NÃO
  toca em `employee_alocacoes`; 409 se já há pendente igual. `aprovar()`: `alocar()` (encerra a anterior em D−1, restrição por cliente
  → 422, duplicada/mesma data → 409) + marca `aprovada` com `alocacao_id`; se `alocar` recusa, o pedido continua pendente.
  `recusar()`: só marca (`recusada`, `decisao_motivo`, quem/quando); 409 se não está pendente.
- `movimentacoes` (g-escalas): linhas de pedido (badge **Pedido**, De = alocação ativa atual → Para) com Situação `pendente` (ações
  **Aprovar** / **Recusar**, gate DP) ou `recusada dd/mm` (por quem e por quê, 90 dias); filtro **Situação** novo em todas as linhas.
  Subtítulo conta «N pedido(s) aguardando o DP».
- **Central de Aprovações** (`/redesign/aprovacoes?t=pendentes`): as pendentes aparecem no topo, Área *Operacional* · Tipo
  *Movimentação* · Risco *Médio*, com os mesmos Aprovar/Recusar — só para quem tem `module:dp`/admin (quem não pode decidir não vê).
  Fonte única: `op_movimentacao_pedidos`; nenhum `agent_draft` é criado.
- Ações: `POST /api/v1/redesign/action/movimentacao-aprovar?pedido_id=` · `movimentacao-recusar?pedido_id=` (payload `motivo`).

### 3.2 Supervisão planejada (g-postos, no fim)
- `supervisao-planos`: Posto/condomínio · Supervisor · Checklist · Frequência (com dias) · Horário · Vigência · **Mês** (realizadas /
  planejadas) · Situação; filtros Supervisor e Situação; ação **Desativar/Reativar** por linha (desativar apaga só as `planejada`
  futuras; o passado fica).
- `supervisao-plano-novo`: supervisor (colaboradores com cargo GERENTE/SUPERVIS **ou** `employee_id` de usuário admin/gerente_operacional —
  os que conseguem fazer check-in), posto **ou** condomínio, checklist (modelos de supervisão da F8, opcional), frequência, dias da
  semana (multiselect), hora início/fim (HH:MM), vigência. Cria e já gera a ocorrência de hoje.
- `supervisao-mapa`: **mês × posto** (3 meses): Planejadas · Realizadas · Atrasadas · Não realizadas · A vencer · **%** (verde ≥ 90,
  âmbar ≥ 60, vermelho); filtros Mês e Posto. Painéis = **dia a dia do mês atual por posto** (`01✓ 02✗ 03· …`, `realizadas/total`).
- `supervisao-hoje`: o que cada supervisor tem para hoje — Supervisor · Posto · Horário · Checklist · Status · Realizada em (via
  checklist / check-in); filtros Supervisor e Status. Abrir a tela chama `gerar_ocorrencias(hoje)` (idempotente).
- **Regra de fechamento** (`marcar_realizada`): um checklist executado (`supervisao_service.executar`) ou um `gerente-checkin` no posto
  marca a ocorrência do dia dos planos daquele posto (ou do condomínio dele). Se o executor tem plano próprio ali, só o dele; senão qualquer
  plano do posto (a visita aconteceu). Garante a ocorrência do dia antes (chama `gerar` — não depende da beat).
- Status: `planejada` → `realizada`; **`atrasada`** = hoje, passou de `hora_fim` e ninguém foi; **`nao_realizada`** = o dia passou.
  Frequência: diária · semanal (dias ISO) · quinzenal (dias nas semanas pares desde a vigência) · mensal (dia do mês da vigência; mês
  curto → último dia).
- Ações: `supervisao-plano-criar` · `supervisao-plano-toggle?plano_id=&ativo=0|1`.

**HTTP no container efêmero (8231), sandbox, admin (jjesus), fixtures apagadas ao fim (0 sobrando):**
```
GET /redesign/data/operacional → 200 · 132 telas · supervisao-planos/plano-novo/mapa/hoje presentes na aba g-postos
  movimentacoes filtros: [mes, condominio, status] · sub: "51 ativa(s) · 0 pedido(s) aguardando o DP · 73 no histórico" · form tem pedir_aprovacao
1. alocar direto (admin, Automático, D−3) → 200 "Alocado (não havia alocação anterior)"
2. pedir (Sim, outro condomínio, hoje) → 200 "Pedido registrado — fica pendente até o DP aprovar (nada mudou ainda)" · alocações ativas do emp: 1
3. pedir igual de novo → 409 "Já existe pedido pendente igual"
4. ledger: 1 linha pendente · ações [Ver, Aprovar, Recusar]
5. Central de Aprovações → 200 · sub "1 movimentação(ões) aguardando o DP · 63 rascunho(s) do agente…" · 1 linha Tipo=Movimentação
6. recusar → 200 "Pedido recusado. A alocação atual não mudou."
7. pedir de novo → 200 pendente
8. aprovar → 200 "Aprovado e alocado. 1 anterior encerrada no dia anterior" · SQL: anterior ativo=false data_fim=23/09 · nova ativo=true
9. aprovar de novo → 409 "Esse pedido já está aprovada"
10. plano semanal seg/qua/sex 08–12 → 200 · 11. semanal sem dias → 400 · 12. plano diário por condomínio → 200
13. supervisao-planos 2 linhas ("2 plano(s) ativo(s)") · supervisao-hoje "0 de 1" [Pyetra · ESCRITÓRIO · planejada] · mapa 1 linha, painel "ESCRITÓRIO — 09/2026"
14. desativar plano → 200 · ocorrências planejadas futuras do plano: 0
check-in (hook): plano diário Pyetra × Gelain → ocorrência "planejada -" → POST gerente-checkin (_silencio) → 200 →
  ocorrência "realizada <visita_id> 06:29" e checkin_visita_id == visita criada
(1ª tentativa de plano-criar deu 500: asyncpg exige `time`, não "08:00" — corrigido em `criar_plano`, 400 "Hora inválida (use HH:MM)".)
```

## 4. Oráculo

```bash
WT=$(git rev-parse --show-toplevel)
ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')
docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" --tmpfs /app/logs:rw,mode=1777 --tmpfs /app/uploads:rw,mode=1777 \
  -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \
  conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_u1_movimentacao_supervisao.py
# em produção: docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_u1_movimentacao_supervisao.py
```
ANTES (24/09 06:23, backend da branch base via `git archive`):
```
  ✗ (a–g) serviços da U1 não importam: ImportError: cannot import name 'supervisao_planejada' from 'modules.operacional.services'
TOTAL falhas U1 movimentação/supervisão: 1
```
DEPOIS (24/09 06:25):
```
  ✓ (a) pedido não mexeu na alocação: 1 linha(s), ativo=True, data_fim=None
  ✓ (a) pedido gravado como pendente: pendente
  ✓ (d) caminho direto do DP: linha nasce com aprovado_por = quem alocou (True)
  ✓ (b) recusar: pedido=recusada, alocações=1, anterior ativa=True
  ✓ (b) aprovar pedido recusado recusado com 409: Esse pedido já está recusada.
  ✓ (c) aprovar com restrição recusado com 422: ALAN VIEIRA DA SILVA tem restrição em CONDOMINIO RESIDENCIAL GREEN HILLS: FIXTURE DGX U1 s
  ✓ (c) depois da recusa por restrição: pedido=pendente, alocações=1, anterior ativa=True
  ✓ (c) anterior encerrada em D−1: ativo=False data_fim=2026-09-23 (esperado 2026-09-23)
  ✓ (c) nova ativa, aprovado_por = aprovador, origem = anterior: (True, True, True)
  ✓ (c) pedido aprovada com alocacao_id = nova: ('aprovada', '1d19318b-…')
  ✓ (e) plano diário 7 dias: geradas 7 == generate_series 7 == 7
  ✓ (e) plano semanal seg/qua 14 dias: geradas 4 == isodow∈(1,3) 4
  ✓ (g) gerar duas vezes: 7→7, 4→4
  ✓ (f) checklist no posto → realizadas na fixture = 1 (esperado 1), ligada à execução: True
  ✓ (f) ocorrência de hoje do plano diário: [('realizada',)]
  ✓ fixtures apagadas ao fim: 0 sobrando
TOTAL falhas U1 movimentação/supervisão: 0
```
Rodados depois, no mesmo backend: `test_oraculo_movimentacao_com_motivo.py` (F5) → `TOTAL falhas movimentação com motivo: 0`
(11 ✓, caminho direto idêntico); `test_oraculo_operacional_dgx.py` (F8, o `executar` ganhou o hook) → `TOTAL falhas operacional DGX F8: 0`.

## 5. O que NÃO foi feito e por quê

- **`employee_alocacoes.status`** — não (decisão em §3: 4 leitores por data sem `ativo` vazariam a linha pendente para a folha por condomínio).
  O filtro «Situação» da tela cobre os 4 estados do brief lendo as duas tabelas.
- **Restrição → 409** — não: a parede da T3 levanta **422** e o oráculo da T3 afirma 422; mudar quebraria aquele oráculo. `aprovar()` repassa o status da parede.
- **Beat diária 00:30** — a função está pronta (`supervisao_planejada.gerar_ocorrencias(db)`), a tela chama ao abrir e `marcar_realizada` garante
  o dia; **não registrei em `celery_app.py`** (é do orquestrador). Registro sugerido: task `operacional.supervisao_gerar_ocorrencias` na
  fila `operacional`, `crontab(hour=4, minute=30)` UTC (= 00:30 Manaus), corpo `async with async_session_factory() as db: await gerar_ocorrencias(db)`.
  Sem a beat, o mapa de dias futuros só se preenche quando alguém abre a tela — e "não realizada" de ontem só é marcada no próximo acesso.
- **Editar pedido / editar plano** — não (o DGX tem Editar na movimentação). Recusar + pedir de novo cobre; plano se desativa e cria outro.
- **Notificar o DP** quando nasce um pedido — não (sem Telegram por decisão de 11/08; a Central é a mesa). E-mail/WhatsApp é decisão do dono (§7).
- **Quinzenal por semana ISO par/ímpar** — usei semanas contadas a partir da vigência (determinístico e recontável); anual/bienal do DGX não.
- **Frontend** — nada editado (table/form/multiselect/filtros/panels/actions genéricos). `checar_regressao.py` não registrado (orquestrador): oráculo órfão com dono até lá.
- **Commit com `SKIP=ruff-format`** só para `operacional.py`, `aprovacoes.py`, `_op_grupos.py` (já fora do formato; um `ruff format` reformataria
  milhares de linhas alheias). Os arquivos novos e `movimentacao_service.py`/`_dgx_f5_movimentacoes.py`/`supervisao_service.py` passam `ruff check` + `format`.

## 6. Como o Jordan testa amanhã

1. Entre como alguém **sem** `module:dp` (ex.: Ruan, `staff`) → Operacional → Escalas & Turnos → **Nova movimentação**: escolha um colaborador
   alocado, outro condomínio, data amanhã, motivo *A pedido do cliente*, deixe «Pedir aprovação» em Automático → Registrar. Mensagem: «Pedido
   registrado — fica pendente». Em **Movimentações**, filtre Situação = *pendente*: a linha aparece com badge Pedido; a alocação antiga continua *ativa*.
2. Tente o mesmo com «Não — alocar agora» → recusa 403.
3. Entre como você (admin) → **Central de Aprovações**: a movimentação está no topo (Área Operacional). **Recusar** com motivo → some da Central;
   em Movimentações, Situação = *recusada* mostra quem e por quê.
4. Peça de novo (passo 1) e, antes de aprovar, crie uma **Restrição por cliente** para esse colaborador nesse condomínio → **Aprovar** → recusa com o
   motivo da restrição; o pedido continua pendente. Encerre a restrição → Aprovar → a antiga fica *encerrada* (ontem da nova), a nova *ativa*,
   coluna Aprovado = você · hoje.
5. Postos & Presença → **Supervisão · novo plano**: supervisor Eliziel, posto Michelangelo, semanal seg/qua/sex, 08:00–12:00, vigência hoje → Criar.
   **Supervisão · hoje** mostra a linha (se hoje for seg/qua/sex) como *planejada*.
6. Faça **Cheguei no posto** (check-in) nesse posto como o Eliziel (ou «registrar em nome de») → **Supervisão · hoje** vira *realizada … via check-in*.
   Ou execute **Checklist · executar** nesse posto → *via checklist*.
7. **Supervisão · realizado × planejado**: linha do mês com 1/1 e 100 %; painel do posto com `24✓`.

## 7. Decisões que só o dono pode tomar

1. **Quem aprova**: hoje `module:dp` (inclui Eliziel e Paiva, gerentes operacionais — decisão de 07/09 «gerentes com mesmo perfil»). Se o supervisor
   pede e o gerente aprova, é a mesma pessoa em dois papéis. Restringir aprovação a admin + DP de fato (Eliziel/Orlailson)?
2. **Avisar o DP** quando nasce um pedido (e-mail/WhatsApp)? Hoje só a Central e o subtítulo da tela.
3. **Planos reais**: quantas vezes por semana cada gerente deve ir a cada condomínio? Nenhum plano foi semeado — nasce pela tela.
4. **Beat 00:30**: registrar no `celery_app.py` (orquestrador) ou deixar a tela gerar ao abrir?
5. **Check-in de qualquer pessoa fecha o plano de outra**: quando o executor não tem plano próprio no posto, a ocorrência de quem tem é marcada
   realizada (a visita aconteceu). Preferir "só o supervisor do plano fecha"?
