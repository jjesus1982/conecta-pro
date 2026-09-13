# FRENTE 02 — Facial offline com fallback, batida offline como PENDENTE DE CONFERÊNCIA

**Data:** 13/09/2026 · **Branch:** `frente/02-facial-offline` (base `bd96fa586`, com a frente 1 já mergeada)
**Sessão:** tmux-agente-02 · **Módulo declarado:** ponto
**Testado em:** staging (`conecta_pro_staging`, 105 funcionários / 53 com rosto cadastrado), em
**modo efêmero** — `docker run` com a worktree montada em `/app:ro`, porta 8202, com
`-e ENVIRONMENT=staging` (sem ele o loguru tenta abrir `/app/logs/app.log` dentro do bind `:ro`,
dá Errno 30 e o app morre no startup sem nunca responder ao `/health`).
**Produção:** nada foi tocado. Nem container, nem banco, nem imagem.

---

## 1. Estado ANTES, medido

| O que | Medida |
|---|---|
| Rotas com `offline` em `app.routes` | **0 de 2** |
| `gp_clock_punches.chave_idempotente` | **não existia** |
| `gp_clock_punches.divergencia_relogio_seg` | **não existia** |
| Batidas `is_offline = true` no banco | **0** (em 10.909 batidas) |
| Limiar do reconhecimento | **chumbado** em `FacialCapture.tsx` (`threshold = 0.68`) |
| `sw-ponto.js` registrado por alguma tela | **não** — `grep -rn "sw-ponto" frontend/src/` = zero |
| Modelos do face-api no cache do SW | **não** — offline a câmera abre e não reconhece ninguém |
| Destino da fila do SW | `POST /ponto/sync` **sem `Authorization`** → 401, e a rota **não reconfere** |

### Oráculo VERMELHO (nascimento, 13/09/2026 04:06)

```
rotas offline montadas: 0/2 · batidas offline: 0 (pendentes de conferência: 0) · sem chave: 0 ·
duplicatas na janela de 20min: 0 · dias com taxa facial 100%: 0
FALHOU: (a) rota /api/v1/people-management/ponto/offline/sync não está em app.routes — a fila do aparelho não tem onde subir reconferida
FALHOU: (a) rota /api/v1/people-management/ponto/offline/config não está em app.routes — a fila do aparelho não tem onde subir reconferida
FALHOU: (b) gp_clock_punches.chave_idempotente não existe — a retentativa do SW duplica
FALHOU: (c) gp_clock_punches.divergencia_relogio_seg não existe — a hora do aparelho não é confrontada
4 desvio(s) na batida offline          exit=1
```

> As afirmações (b)–(f) não tinham como falhar por **falta de dado** (zero batidas offline no
> banco). O vermelho nasceu em (a) e nas colunas ausentes — coluna que não existe conta como
> vermelho de propósito: afirmação não mensurável nunca passa por verde de omissão. As 3 batidas de
> prova só puderam ser criadas **depois** que a rota existiu, e é com elas que (b)–(f) passam a
> medir alguma coisa.

---

## 2. O que foi feito, arquivo por arquivo

| Arquivo | O quê |
|---|---|
| `backend/scripts/orq/test_oraculo_batida_offline.py` **(novo, 241 linhas)** | Seis afirmações (a)–(f). Escrito e rodado VERMELHO antes de qualquer linha de implementação. |
| `backend/scripts/qa/checar_batida_offline_suspeita.py` **(novo)** | Caçador. `TOTAL batidas offline suspeitas: N`, exit 1 se N>0. Conta relógio fora do limite, duplicata na janela, dia com taxa facial 100% e pendência esquecida há mais de 24h. |
| `backend/modules/people_management/ponto/services/reconferencia_facial.py` **(novo)** | Distância euclidiana entre o descriptor do aparelho e `employees.face_descriptor`, com o **mesmo limiar do online**, lido de `system_configs`. Incomparável devolve `None`, não 999. Tem `demo()` com asserts (roda com `python3 reconferencia_facial.py`). |
| `backend/modules/people_management/ponto/controllers/offline_controller.py` **(novo)** | `GET /ponto/offline/config` e `POST /ponto/offline/sync`. Lote de até 50, savepoint por item, resposta item a item. |
| `backend/modules/people_management/ponto/controllers/punch_controller.py` | `router.include_router(offline_router)` no **fim**, com comentário `# frente 02`, **depois** do bloco da frente 01 — que não foi tocado. Import guardado. |
| `backend/modules/people_management/ponto/models/clock_punch.py` | `status` varchar(20)→(30), `chave_idempotente`, `device_id`, `divergencia_relogio_seg`, `tentativas_offline`; enum ganhou `PENDENTE_DE_CONFERENCIA`. |
| `backend/modules/hr/rep_integration/services/rep_p.py` | **Uma linha** na varredura do AFD: `AND p.status <> 'pendente_de_conferencia'  -- frente 02` (+ docstring explicando). Ver §5. |
| `backend/modules/people_management/__init__.py` | `/ponto/offline` fora do gate `module:dp`, como já é o `/portal`. Ver §5. |
| `frontend/src/components/ponto/offlineBatida.ts` **(novo)** | A conversa da página com o service worker: salvar, ler fila, marcar sincronizada, cache do descriptor com validade, `deviceId()`, `chaveIdempotente()`, `ehFalhaDeRede()`. |
| `frontend/public/sw-ponto.js` | Reescrito. Cacheia os 7 arquivos de `/models` e a tela real da batida; guarda descriptor/foto/hora do aparelho/chave; **parou de sincronizar sozinho pela rota errada**; apaga biometria por validade, por troca de dono e ao aceitar a batida. |
| `frontend/src/app/modulos/meu-espaco/page.tsx` | Registro do SW, `GET /offline/config` (limiar vem do servidor), cache do descriptor, caminho offline na batida, fila visível com "Enviar agora", aviso âmbar "pendente de conferência", sincronização na volta do sinal. |
| `frontend/src/components/ponto/FacialCapture.tsx` | **NÃO foi tocado.** Ele já devolvia descriptor, imagem e hora, e já aceitava `threshold` por prop. |

> ⚠️ **A tela da batida não é a que o briefing supunha.** `frontend/src/app/modulos/gestao-pessoas/ponto/batida/page.tsx` **não** chama `FacialCapture`. Quem chama, e é a tela que o porteiro usa, é `frontend/src/app/modulos/meu-espaco/page.tsx` (aba Ponto). Foi essa que recebeu a mudança.

### As decisões que ficaram no código

1. **Batida offline NUNCA nasce definitiva.** Ela chega ao `/offline/sync`, o servidor recompara o
   rosto na mesma transação, e só então:
   passou **e** relógio dentro do limite → `status = 'pending'` (o ciclo normal de qualquer batida);
   não passou, não deu para comparar, ou relógio fora do limite → `status = 'pendente_de_conferencia'`
   + pendência no `agent_drafts` (via `pendencia_dp.abrir`, assunto `validar_batida`) com a foto, a
   distância medida no servidor e as duas horas.
2. **`facial_match = None` é bloqueio, não permissão.** Sem rosto cadastrado, ou descriptor de outra
   dimensão, não se sabe quem bateu — e "não sei" nunca vira "pode".
3. **`pendente_de_conferencia` NÃO entra no AFD.** O AFD é memória inalterável e o NSR não volta
   atrás: escrever nele um fato que o DP ainda pode recusar é afirmar integridade sobre o que não
   está confirmado. Quando a conferência aprova, a batida deixa de ser pendente e a **varredura
   seguinte** a numera — **sem lacuna de NSR**, porque a linha só é numerada no instante em que é
   escrita. Provado no §3.
4. **A origem no AFD é a que a frente 1 usa.** Não inventei `origem='offline'`: a frente 1 grava
   `afd_records.origem = device_type` e usa o **campo 7 do registro tipo 7** (on/off-line) para a
   distinção. A batida offline entra como `device_type='mobile'` + `is_offline=true`, o que produz
   `coletor='01'` e flag `'1'` — medido na linha do NSR 1114: `...011...`.
5. **As duas horas, sempre, e nenhuma corrigida.** `punch_timestamp` = hora do aparelho (a hora do
   fato), `server_timestamp` = hora do servidor, `divergencia_relogio_seg` = a diferença.
6. **Idempotência por `(employee_id, MINUTO da hora do aparelho, device_id)`**, `UNIQUE` no banco.
   Segundos ficaram de fora de propósito: a retentativa reenvia com carimbo próprio e o clique duplo
   cai no mesmo minuto. Não é verificar-e-depois-inserir — isso é promessa, e foi assim que 1.375
   jornadas duplicaram em 11/09 e três batidas do GERNANES caíram no mesmo segundo em 08/09.
7. **Rede caída ≠ servidor recusando.** O app só guarda offline quando **não houve resposta HTTP**.
   Se o servidor respondeu 4xx/5xx, guardar offline seria contornar a recusa por outro caminho.
8. **Menos chamadas à API** (o "otimização do número de chamadas" do Cronos 3.61.9): o descriptor e
   os modelos do face-api ficam em cache no aparelho; a página não repergunta a cada frame — quem
   compara a cada 550ms é o `FacialCapture`, localmente, como já era.

---

## 3. Estado DEPOIS, medido

### Rotas em `app.routes` (container efêmero, porta 8202)

```
rotas offline: ['/api/v1/people-management/ponto/offline/config',
                '/api/v1/people-management/ponto/offline/sync']
```

### Oráculo VERDE

```
rotas offline montadas: 2/2 · batidas offline: 3 (pendentes de conferência: 2) · sem chave: 0 ·
duplicatas na janela de 20min: 0 · dias com taxa facial 100%: 0
OK batida offline: sobe por rota que reconfere, tem chave idempotente, grava as duas horas com a
diferença, só vira definitiva com match do servidor e não entra no AFD enquanto pende
exit=0
```

### Caçador — 1 suspeita, e ela é a batida de prova do relógio torto

```
  relógio: ADAILSON SERRA ALVES 13/09 02:30 no aparelho CEL-RELOGIO-TORTO — 6267s de diferença
  para o servidor (limite 300s) · punch 6da45882-8ab0-4d1c-aa5a-2aabef3a1c55
TOTAL batidas offline suspeitas: 1          exit=1
```

### As 3 batidas de prova, criadas pela API numa única chamada

```
POST /api/v1/people-management/ponto/offline/sync
{"recebidas":3,"definitivas":1,"pendentes":1,"duplicadas":1,"erros":0,"itens":[
 {"resultado":"definitiva",              "facial_match":true,  "distancia_servidor":0.0,
  "limiar":0.68,"divergencia_relogio_seg":180,"relogio_suspeito":false,
  "hora_aparelho":"2026-09-13T04:10:53","hora_servidor":"2026-09-13T04:13:53.407972"},
 {"resultado":"pendente_de_conferencia", "facial_match":false, "distancia_servidor":0.7487,
  "limiar":0.68,"motivo":"nao_bateu"},                      ← descriptor de OUTRA pessoa
 {"resultado":"duplicada","punch_id":"66f23dd7-…","status":"pending"}]}  ← mesmo minuto/aparelho
```

**4ª prova — rosto CERTO, relógio do aparelho 1h44 atrasado:**

```
{"resultado":"pendente_de_conferencia","facial_match":true,"distancia_servidor":0.0,
 "divergencia_relogio_seg":6267,"relogio_suspeito":true,"motivo":"relogio_divergente"}
```

A batida **não** foi apagada nem corrigida: ficou registrada com a hora que o aparelho disse, com a
divergência gravada, e foi para a conferência do DP.

**Prova de idempotência — o MESMO lote enviado 2×:**

```
1ª chamada: {"recebidas":1,"definitivas":0,"pendentes":1,"duplicadas":0,"erros":0}
2ª chamada: {"recebidas":1,"definitivas":0,"pendentes":0,"duplicadas":1,"erros":0}
SELECT count(*) FROM gp_clock_punches WHERE is_offline  →  3  (era 3 antes do reenvio)
```

### No banco

```
 punch_id  | status                  | facial_match | punch_timestamp     | server_timestamp    | diverg | device_id         | AFD nsr | origem
 66f23dd7… | pending                 | t            | 2026-09-13 04:10:53 | 2026-09-13 04:13:53 |    180 | CEL-PROVA-02      | 1114    | mobile
 e6f8faa9… | pendente_de_conferencia | f            | 2026-09-13 04:11:53 | 2026-09-13 04:13:53 |    120 | CEL-PROVA-02      | (nenhum)| —
 6da45882… | pendente_de_conferencia | t            | 2026-09-13 02:30:00 | 2026-09-13 04:14:27 |   6267 | CEL-RELOGIO-TORTO | (nenhum)| —

chave_idempotente:
  2430761d-172e-44b8-a817-edfea166e321:2026-09-13T04:10:CEL-PROVA-02
  2430761d-172e-44b8-a817-edfea166e321:2026-09-13T04:11:CEL-PROVA-02
  2430761d-172e-44b8-a817-edfea166e321:2026-09-13T02:30:CEL-RELOGIO-TORTO

tentativas_offline da 1ª:
  {"limiar":0.68,"tentativas":[{"motivo":"nao_detectou","quando":"2026-09-13T04:10:53"}],
   "distancia_aparelho":0.0,"distancia_servidor":0.0}
```

**A linha AFD da definitiva** (NSR 1114, seguinte ao 1113 que a frente 1 deixou, sem lacuna):

```
afd_line posições 71-73 = "011"   → coletor 01 (mobile) + flag 1 (OFF-LINE), 137 posições
```

**A pendência do DP** (mesmo mecanismo da frente 1 / `pendencia_dp.py`):

```
agent_drafts: "ADAILSON SERRA ALVES: validar batida de contingência que ficou pendente"
              status=rascunho · 2026-09-13 08:13:53+00
```

### Tipos do frontend

`npx tsc --noEmit` **passou sem erro** nos arquivos tocados (`meu-espaco/page.tsx`,
`offlineBatida.ts`; `sw-ponto.js` é JS puro e não entra no tsc). O repositório tem **13 outros
arquivos com erro de tipo pré-existente** (`agendar/[slug]`, `candidato`, `homologacao`,
`ged/montar-kit`, `FloatingChat`, …) — nenhum deles foi tocado por esta frente, e nenhum é novo.
**Nenhum `npm run build`, nenhum `pm2`, nenhum deploy** — proibidos pelo contrato.

---

## 4. Parâmetros novos — **A CONFIRMAR PELO JORDAN**

Todos em `system_configs` (chave/valor), lidos em tempo de execução. **Nenhum está chumbado no
código**; o padrão do código só vale se a chave sumir do banco, e nunca é mais frouxo que o valor
proposto.

| Chave | Valor proposto | O que ele decide | Por que esse número |
|---|---|---|---|
| `ponto.facial.limiar_distancia` | **0.68** | Distância máxima para o rosto "bater", online e offline | É exatamente o que o app já usa hoje no navegador. **Não mexi.** Apertar ou afrouxar sem medir a taxa de falha real seria trocar um número por um palpite — e a taxa real de falha ainda não é conhecida porque até 11/09 a falha não saía do aparelho. |
| `ponto.offline.divergencia_relogio_max_seg` | **300** (5 min) | Acima disso a batida é suspeita e vai para o DP | 5 min cobre deriva normal de celular. Se o Jordan achar que a guarita tem celular muito fora, subir para 900 é uma linha de SQL — **mas atenção: quanto maior, maior a janela para fraude de relógio.** |
| `ponto.offline.validade_cache_horas` | **24** | Quanto tempo o descriptor biométrico pode ficar no aparelho | Cobre um plantão 12x36 inteiro com folga. É o número que vira a política de LGPD (§7). |
| `ponto.offline.janela_idempotencia_min` | **20** | Janela em que duas batidas offline iguais são consideradas a mesma | A **mesma régua** que o importador do Tangerino já usa. Régua única de propósito: duas cópias divergem e a que diverge cala. |

---

## 5. Fiação pendente para o integrador

### 5.1 `backend/scripts/qa/checar_regressao.py` (arquivo proibido para mim)

No dicionário `CACADORES` (roda no container):

```python
    "checar_batida_offline_suspeita.py": lambda s: _n(r"^TOTAL batidas offline suspeitas: (\d+)", s),
```

### 5.2 DDL de produção (aplicado no staging, nesta ordem)

```sql
-- status precisa caber 'pendente_de_conferencia' (23 caracteres); varchar(20) truncava.
-- Widening de varchar no Postgres não reescreve a tabela.
ALTER TABLE gp_clock_punches ALTER COLUMN status TYPE varchar(30);

ALTER TABLE gp_clock_punches ADD COLUMN IF NOT EXISTS chave_idempotente       varchar(120);
ALTER TABLE gp_clock_punches ADD COLUMN IF NOT EXISTS divergencia_relogio_seg integer;
ALTER TABLE gp_clock_punches ADD COLUMN IF NOT EXISTS tentativas_offline      jsonb;
ALTER TABLE gp_clock_punches ADD COLUMN IF NOT EXISTS device_id               varchar(64);

-- a trava que impede a retentativa do aparelho de virar batida nova.
-- Aceita vários NULL (toda batida online tem chave nula) — comportamento desejado no Postgres.
CREATE UNIQUE INDEX IF NOT EXISTS ux_gp_punch_chave_idem ON gp_clock_punches(chave_idempotente);

COMMENT ON COLUMN gp_clock_punches.chave_idempotente IS
  'frente 02: employee_id:minuto-da-hora-do-aparelho:device_id. Unique: a retentativa do SW nunca duplica.';
COMMENT ON COLUMN gp_clock_punches.divergencia_relogio_seg IS
  'frente 02: server_timestamp - punch_timestamp em segundos. Relogio de aparelho e editavel; a defesa e ter o numero.';
COMMENT ON COLUMN gp_clock_punches.tentativas_offline IS
  'frente 02: falhas de reconhecimento ocorridas NO APARELHO enquanto offline, para a estatistica nao sumir.';

-- parâmetros (§4). Trocar o valor aqui muda o comportamento sem tocar em código.
INSERT INTO system_configs (id, chave, nome, valor, valor_type, scope, priority, ativo, created_at, updated_at)
VALUES
 (gen_random_uuid(),'ponto.facial.limiar_distancia','Limiar de distancia do reconhecimento facial','0.68','float','global','normal',true,now(),now()),
 (gen_random_uuid(),'ponto.offline.divergencia_relogio_max_seg','Divergencia maxima entre relogio do aparelho e do servidor (s)','300','int','global','normal',true,now(),now()),
 (gen_random_uuid(),'ponto.offline.validade_cache_horas','Validade do cache do descriptor no aparelho (h)','24','int','global','normal',true,now(),now()),
 (gen_random_uuid(),'ponto.offline.janela_idempotencia_min','Janela de idempotencia da batida offline (min)','20','int','global','normal',true,now(),now());
```

### 5.3 Duas linhas fora do meu território que **eu escrevi** e o integrador deve revisar

Escrevi as duas porque sem elas a frente não é verdadeira — e não porque o território mudou. Estão
isoladas, comentadas com `# frente 02`, e são as únicas fora de `people_management/ponto/**`:

**(a) `backend/modules/hr/rep_integration/services/rep_p.py`** (arquivo da frente 1, já mergeada),
dentro do `WHERE` de `gerar_afd_desde_corte`:

```sql
        WHERE p.punch_timestamp >= :corte AND a.id IS NULL
          AND p.status <> 'pendente_de_conferencia'   -- frente 02
```

Sem ela, a varredura do AFD — que roda a **cada batida de qualquer pessoa** — daria NSR a uma batida
que o DP ainda pode recusar. Não havia como conseguir isso de dentro do meu território: um gatilho
de banco que pulasse a linha consumiria o NSR e abriria lacuna, que é pior.

**(b) `backend/modules/people_management/__init__.py`**, em `_gatear_rotas_por_modulo`, logo depois
da exceção do `/portal`:

```python
        # frente 02 — a fila de batidas offline sobe do celular do PORTEIRO, que não tem
        # `module:dp`. Mesma audiência de /portal/self-service/facial/batida: quem chama é o dono
        # da própria batida, e a rota resolve o employee_id pelo JWT (nunca pelo corpo do pedido).
        if path.startswith("/people-management/ponto/offline"):
            continue
```

Medido: sem ela o porteiro recebe `403 Acesso negado ao módulo 'dp'`. A rota **não** confia em
`employee_id` vindo do corpo — ela lê do JWT, exatamente como `/facial/batida`.

### 5.4 Uma linha que **eu não escrevi** e depende do integrador

`frontend/src/hooks/useAuth.ts`, dentro do `finally` do `logout`, depois do
`localStorage.removeItem('refresh_token')`:

```typescript
      // frente 02 — biometria não sobrevive ao logout (LGPD)
      void import('@/components/ponto/offlineBatida').then((m) => m.apagarBiometria());
```

Não escrevi porque `useAuth.ts` é compartilhado com as outras nove frentes e uma colisão ali
derruba o login inteiro. Até ela entrar, o descriptor some por **validade (24h)** e por **troca de
dono do aparelho** — ver §7.

### 5.5 `main_production.py` · `celery_app.py` · `_modules/*.json` · alembic

**Nada.** A montagem é sub-router dentro do `/ponto`, que já é montado. Não há task de Celery. Não
há tela do redesign nesta frente. **Sem migration** (zona proibida) — o DDL está em 5.2.

### 5.6 Bake

O backend é baked na imagem: **nada disto está servindo em produção** até o próximo
`deploy_backend_bluegreen.sh`, com `checar_bake_pendente = 0` e `checar_drift_workers` limpo
(risco 0.3 do pré-mortem). O frontend precisa de `./scripts/deploy/deploy_frontend.sh` — proibido
para mim, e o `sw-ponto.js` só chega ao celular depois dele.

---

## 6. O que NÃO foi feito, e por quê

1. **O limiar não foi mexido.** 0.68 é o que o app já usa. Trocá-lo sem medir a taxa real de falha
   seria trocar um número por um palpite — e a taxa real ainda não é conhecida, justamente porque
   até 11/09 a falha não saía do aparelho. Ficou como parâmetro, A CONFIRMAR.
2. **Tela de conferência da batida pendente.** A pendência cai na Central de rascunhos onde o DP já
   decide. Tela nova é outra frente, e o contrato proíbe deploy de frontend aqui.
3. **Wipe da biometria no logout** — precisa de `useAuth.ts`, compartilhado (§5.4).
4. **Background sync verdadeiro** (fila subindo com o app fechado) — exigiria o token dentro do
   IndexedDB. Num celular de guarita compartilhado isso é pior que o atraso. Decisão conservadora
   registrada: a fila sobe quando o app é aberto, quando o sinal volta com a aba viva, ou no botão
   "Enviar agora".
5. **Liveness / prova de vida** (foto de foto). O `liveness_check` que o app manda é literalmente
   `true` chumbado, e continua `NULL` na batida offline — **gravar `true` seria afirmar uma
   verificação que ninguém fez**. É a fraude que sobra: ver §8.
6. **Não apaguei a rota antiga `POST /ponto/sync`** (`PunchService.sync_offline_punches`), que grava
   batida offline **sem reconferir**. Ela deixou de ser chamada pelo SW, mas continua montada e
   continua sendo uma porta. Apagá-la é mudança em rota de terceiros dentro do mesmo controller e
   exige varrer importadores/chamadores no repositório inteiro (a lição do `my_*_controller`).
   **Recomendação ao integrador: aposentar `/ponto/sync` numa próxima passada.**
7. **Teste no navegador de verdade** (modo avião, celular) — é o §7, e é do Jordan.
8. **Senha de teste no staging.** Para provar a rota com a audiência certa, defini uma senha
   conhecida para `adailsona012@gmail.com` **no banco de staging** (`Frente02Teste!`). Nenhuma
   conta de produção foi tocada.

---

## 7. Como o Jordan testa amanhã

### 7.1 No servidor, sem celular (5 minutos)

```bash
WT=/opt/conecta-pro/.claude/worktrees/agent-a8e9b71798b4220ee   # ou o checkout da branch
docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | grep -E '^(DATABASE_URL|REDIS_URL)=' > /tmp/envs_f02.txt

docker run --rm -d --name teste-frente-02 --network conecta-staging-network \
  -p 127.0.0.1:8202:8080 -v "$WT/backend:/app:ro" -e PYTHONPATH=/app \
  -e PYTHONDONTWRITEBYTECODE=1 -e ENVIRONMENT=staging -e PORT=8080 \
  --env-file /opt/conecta-pro/.env --env-file /tmp/envs_f02.txt conecta-pro-backend:latest
until curl -sf http://127.0.0.1:8202/health >/dev/null; do sleep 3; done

# entra como FUNCIONÁRIO (a audiência certa — o admin não é quem bate ponto)
TOKEN=$(curl -sf -X POST http://127.0.0.1:8202/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=adailsona012@gmail.com&password=Frente02Teste!" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 1) os parâmetros que o aparelho vai obedecer
curl -s -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8202/api/v1/people-management/ponto/offline/config

# 2) o que já está no banco: uma definitiva com AFD, duas pendentes sem AFD
docker exec conecta-pro-postgres-staging psql -U postgres -d conecta_pro_staging -c "
  SELECT p.punch_id, p.status, p.facial_match, p.punch_timestamp AS hora_aparelho,
         p.server_timestamp AS hora_servidor, p.divergencia_relogio_seg, a.nsr
  FROM gp_clock_punches p LEFT JOIN afd_records a ON a.punch_id = p.punch_id
  WHERE p.is_offline ORDER BY p.id;"

docker stop teste-frente-02     # ⚠️ não deixe rodando: memória é compartilhada
```

**O oráculo e o caçador, sem servidor:**

```bash
docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" -e PYTHONPATH=/app \
  -e ENVIRONMENT=staging --env-file /opt/conecta-pro/.env --env-file /tmp/envs_f02.txt \
  conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_batida_offline.py
# esperado: exit 0, "OK batida offline: …"

docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" -e PYTHONPATH=/app \
  -e ENVIRONMENT=staging --env-file /opt/conecta-pro/.env --env-file /tmp/envs_f02.txt \
  conecta-pro-backend:latest python3 /app/scripts/qa/checar_batida_offline_suspeita.py
# esperado: TOTAL batidas offline suspeitas: 1 (a batida de prova do relógio torto)
```

### 7.2 No celular, em MODO AVIÃO — **só depois do deploy do frontend**

O `sw-ponto.js` mora no `public/` do Next: ele só chega ao celular depois de
`./scripts/deploy/deploy_frontend.sh` (proibido para mim). Feito isso:

1. **Com internet**, abrir `/modulos/meu-espaco` no celular e **bater o ponto normalmente uma vez**.
   Isso registra o service worker, baixa os modelos do face-api e guarda o seu rosto de referência
   no aparelho com validade de 24h. **Sem esse passo, o modo avião não vai funcionar** — e isso não
   é defeito, é a validade da biometria fazendo o que deve.
2. **Ligar o modo avião.** Recarregar a página (ela vem do cache).
3. Tocar em bater ponto. O GPS ainda responde em modo avião na maioria dos aparelhos; se ele negar,
   a tela avisa e o caminho é a contingência (botão de sempre).
4. A câmera deve abrir e **reconhecer o rosto** normalmente. Ao reconhecer, a tela mostra em
   **âmbar**: *"Batida registrada OFFLINE às HH:MM — pendente de conferência"*, e aparece o contador
   *"1 batida guardada no aparelho, aguardando sinal"*.
5. **Bater de novo, no mesmo minuto.** A segunda vai para a fila também — e quando subir, o servidor
   devolve `duplicada` e **não cria** uma segunda batida. É a prova da idempotência no caminho real.
6. **Desligar o modo avião.** Em segundos o contador deve zerar sozinho. (Se não zerar, tocar em
   "Enviar agora".)
7. **Conferir no ERP** que a batida apareceu, e **com que status**:
   - rosto reconhecido pelo servidor e relógio do celular certo → batida normal, no espelho;
   - qualquer outra coisa → `pendente_de_conferencia`, com uma pendência esperando você na Central
     de rascunhos, com a foto e a distância medida.
8. **O teste que mais interessa:** *mudar a hora do celular* (desligar a hora automática, atrasar
   30 min), bater offline e sincronizar. A batida deve entrar **pendente**, com `relogio_suspeito`,
   e aparecer no caçador. Ela **não** é apagada nem corrigida — o registro do que a pessoa fez
   continua lá, com o número da divergência do lado.

### 7.3 A política de LGPD que você está aprovando ao aprovar esta frente

| Dado | Onde fica | Por quanto tempo | Como some |
|---|---|---|---|
| Descriptor de referência (128 floats) | IndexedDB do celular, store `cached_employee`. **Nunca no localStorage, nunca em claro numa chave que qualquer script lê.** | `ponto.offline.validade_cache_horas` = **24h** (A CONFIRMAR) | vence sozinho; some se o aparelho trocar de dono (employee_id diferente); some no logout **assim que a linha do §5.4 entrar** |
| Descriptor capturado na batida offline | IndexedDB, junto da batida na fila | até a batida ser aceita pelo servidor | apagado no `MARK_SYNCED` — o rosto já cumpriu a função |
| Foto da batida offline | IndexedDB, junto da batida | idem | idem. No servidor vira `/uploads/ponto/<punch_id>.jpg`, como qualquer selfie de ponto |
| Token de acesso | **NÃO** entra no IndexedDB | — | é por isso que o SW não sincroniza sozinho (§6.4) |

---

## 8. Riscos residuais do pré-mortem que continuam

- **0.1 Sentry vazio.** Esta frente roda no celular do porteiro, às 06:00, na guarita. Uma exceção
  no caminho offline morre no console de um celular que ninguém abre — pior que o log de um
  container. O caçador cobre o **efeito** (batida suspeita, pendência esquecida), nunca a causa.
  **Continua sendo a linha de `.env` mais barata do projeto.**
- **0.3 `docker cp` não publica / bake pendente.** Nada desta frente serve em produção até o bake do
  backend **e** o deploy do frontend. A rota pode existir no disco e não estar de pé.
- **Risco 1 da frente — offline como porta de fraude: FECHADO PELA METADE.** O servidor agora
  reconfere *quem* está na foto. Ele **não** verifica se a foto é de uma pessoa viva: `liveness` é
  `true` chumbado no app e `NULL` na batida offline. **Uma foto impressa do colega, offline, passa
  na reconferência.** É a fraude que sobra, e ela é honesta no banco (o campo está nulo, não
  mentindo). Prova de vida é frente própria.
- **Risco 2 — hora do celular: MITIGADO, NÃO ELIMINADO.** Quem mexer no relógio por **menos** de 5
  minutos passa sem ser notado. Apertar o limite pega mais fraude e pega junto o celular velho com
  deriva legítima. O número é do dono (§4).
- **Risco 3 — duplicata na volta do sinal: FECHADO** por `UNIQUE`, provado com o mesmo lote enviado
  duas vezes. **Mas** o `/ponto/sync` antigo continua montado e não tem essa trava (§6.6).
- **Risco 4 — biometria no aparelho: MITIGADO.** Validade de 24h, IndexedDB, wipe por troca de dono.
  Falta o wipe no logout (§5.4).
- **Risco 5 — falha que não sai do aparelho: FECHADO para a batida que acontece.** As tentativas
  falhas sobem em `tentativas_offline`. **Mas** quem desiste sem nunca conseguir bater continua
  invisível offline: a tentativa fica no `sessionStorage` e morre quando a aba fecha. Estatística
  perdida não custa a jornada de ninguém — foi por isso que ficou assim.
- **Fuso (herdado da frente 1).** `punch_timestamp` é tratado como hora de parede de Manaus em todo
  o caminho offline. Se alguma origem passar a gravar UTC, a batida sai com 4h de erro e **nada
  acusa** — exceto, agora, o `divergencia_relogio_seg`, que passaria a marcar ~14.400s em todo
  mundo e cairia no caçador. Não é um oráculo, mas é o primeiro sinal que existe para isso.
- **A batida pendente depende de alguém olhar a Central.** O caçador conta a que passou de 24h sem
  conferência. Se ninguém rodar o caçador, a pessoa que trabalhou fica esperando.
