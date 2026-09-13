# FRENTE 6 — Foto obrigatória tirada NO MOMENTO + offline-first na ronda

**Branch:** `frente/06-foto-offline-ronda` · **Commits:** `888521d97` (backend/oráculo/caçador), `d6bda4e53` (frontend)
**Módulo:** operacional · **Data:** 13/09/2026 · **Onde foi testado:** staging (banco `conecta_pro_staging`)
via container efêmero `teste-frente-06` na porta 127.0.0.1:8206, servindo o código desta worktree.

---

## 1. Estado ANTES (medido)

**O par de requisições que o pré-mortem 6.3 previu existia exatamente como descrito:**
`POST /rondas/{id}/checkpoints` (JSON) e, em requisição SEPARADA, `POST
/rondas/{id}/checkpoints/{cp}/fotos` (FormData, uma foto por chamada). Entre uma e outra cabia
tudo: checkpoint sem foto, foto órfã, ronda fechada no meio.

**A foto não era "do momento":** `frontend/.../ronda-mobile/page.tsx` usava
`<input type="file" accept="image/*" capture="environment">`. `capture` é dica do navegador, não
trava — em vários aparelhos a galeria continua disponível.

**O banco não sabia dizer que uma foto era obrigatória:** `inspection_checkpoints` não tinha
nenhuma das colunas da decisão (`foto_obrigatoria`, `hora_aparelho`, `hora_servidor`,
`device_id`, `chave_idempotente`, `origem_offline`), e não havia índice único que impedisse a
retentativa de um celular sem sinal de duplicar o registro.

**Sem sinal, o registro se perdia:** não havia fila local. Nenhuma linha de IndexedDB na página.

**Achado de terreno (não previsto no pré-mortem):** a rota `GET /rondas/minhas-rondas`, que a
ronda-mobile chama na primeira linha do carregamento (`page.tsx:353`), **não existia**. Caía no
path param `/{round_id}` e devolvia **422**. A lista de rondas do celular nunca carregou.

### Oráculo VERMELHO — `backend/scripts/orq/test_oraculo_ronda_com_foto.py`

Caso mínimo criado pela API do staging para o oráculo ter o que medir (não havia nenhuma ronda
com foto no staging: 15 checkpoints, **0** com foto): ronda `RON-2026-00084` criada, iniciada,
checkpoint `foto_evidencia` com `photos = []`, ronda **concluída com sucesso** — que é
precisamente o defeito.

```
colunas faltando: 6 · concluídas sem foto na hora: 1 · fotos no banco: 0 · em disco: 0 · chaves duplicadas: 0
FALHOU: coluna inspection_checkpoints.foto_obrigatoria não existe — o banco não sabe dizer isso
FALHOU: coluna inspection_checkpoints.hora_aparelho não existe — o banco não sabe dizer isso
FALHOU: coluna inspection_checkpoints.hora_servidor não existe — o banco não sabe dizer isso
FALHOU: coluna inspection_checkpoints.device_id não existe — o banco não sabe dizer isso
FALHOU: coluna inspection_checkpoints.chave_idempotente não existe — o banco não sabe dizer isso
FALHOU: coluna inspection_checkpoints.origem_offline não existe — o banco não sabe dizer isso
FALHOU: não há índice ÚNICO em chave_idempotente — a retentativa offline duplica checkpoint
FALHOU: ronda RON-2026-00084 CONCLUÍDA com checkpoint 6b0c08f0 (foto_evidencia, conforme) de foto obrigatória sem imagem capturada na hora
FALHOU: o serviço não tem foto_e_obrigatoria — a regra de foto obrigatória não existe no código
9 desvio(s) na ronda com foto
exit=1
```

**Produção, leitura apenas (SELECT), para dimensionar o legado:** 15 checkpoints, **0** com foto,
**0** casos de `foto_evidencia` concluído sem foto. Ou seja: a trava nova **não invalida nada do
que já existe** — a ronda com foto ainda não tinha começado a ser usada. É o melhor momento para
fechar a porta.

---

## 2. O que foi feito, arquivo por arquivo

### Backend (commit `888521d97`)

**`backend/modules/operacional/inspection_rounds/models/inspection_checkpoint.py`**
Seis colunas novas (`foto_obrigatoria`, `hora_aparelho` timestamptz, `hora_servidor` timestamptz
default now(), `device_id` varchar(80), `chave_idempotente` varchar(120) UNIQUE, `origem_offline`)
e um status novo `CheckpointStatus.PENDENTE_FOTO` — o estado de quem nasceu obrigatório e ainda
não tem imagem. `hora_servidor` é a oficial; `hora_aparelho` fica ao lado, para auditoria (nunca
só o EXIF, que é editável — pré-mortem 6.4).

**`.../schemas/inspection_round_schemas.py`** — os mesmos campos em `CheckpointCreate` (entrada)
e `CheckpointResponse` (saída).

**`.../repositories/inspection_round_repository.py`** — `get_checkpoint_by_chave(chave)`: a
consulta que torna a retentativa barata (sem ela, a idempotência dependeria de estourar o UNIQUE).

**`.../services/inspection_round_service.py`**
- `foto_e_obrigatoria(checkpoint_type, flag)` — **régua única**. `foto_evidencia` sempre exige
  foto; qualquer outro tipo exige quando o app marcar. É esta função que o oráculo afirma, para
  não existirem duas cópias da regra que divergem (a lição do 09/09).
- `create_checkpoint_completo(round_id, data, fotos, checkpoint_id)` — grava checkpoint e fotos
  na mesma unidade, com as duas horas, o device e a chave; devolve `(checkpoint, repetida)`.
  Chave repetida devolve o registro que já existe; corrida entre duas retentativas cai no
  `IntegrityError` e devolve o vencedor.
- **Folga de relógio:** online, a hora do aparelho tem de bater com a do servidor dentro de
  `TOLERANCIA_RELOGIO = 10 min`, senão a foto não conta como "da hora". Offline não se exige
  (pode ter ficado horas na fila, e é legítimo). O valor é um knob no topo do módulo — relógio de
  celular drifta, e 10 min é um palpite conservador que o Jordan pode mexer.
- `complete_round` **recusa** fechar a ronda com qualquer checkpoint `pendente_foto` ou
  obrigatório sem imagem `capturada_na_hora`, dizendo quais.

**`.../controllers/inspection_round_controller.py`**
- **`POST /rondas/{id}/checkpoints/completo`** (novo, multipart): `dados` = JSON do
  `CheckpointCreate`, `fotos` = imagens da CÂMERA (`capturada_na_hora=true`), `anexos` = galeria
  (`false`, não vale como prova). **Transação única:** qualquer erro apaga os arquivos já
  gravados — sem checkpoint, sem arquivo. Repetição da mesma chave devolve **200** com
  `repetida: true` e apaga os arquivos da repetição.
- `_gravar_foto(...)` — validação (JPEG/PNG/WebP, ≤10 MB, não vazio), nome saneado, **sha256** da
  imagem, `hora_servidor` (UTC) + `hora_aparelho` + `capturada_na_hora` no registro da foto.
- **`GET /rondas/minhas-rondas`** (novo) — a rota que o celular chamava e não existia. Declarada
  ANTES de `/{round_id}`, senão o path param a engole.
- Rota antiga `POST /.../fotos` **mantida e ensinada**: aceita `capturada_na_hora` e
  `hora_aparelho`, deduplica por hash (a mesma imagem reenviada não entra duas vezes) e
  **promove** `pendente_foto` → status pretendido quando a foto da hora chega. Se o banco
  recusar, o arquivo é apagado (duas órfãs foram medidas antes deste guarda existir).
- `FOTOS_DIR` passa a ler `UPLOADS_DIR` (produção `/app/uploads`; staging/efêmero `/tmp/uploads`).
  Antes era `/app/uploads` chumbado, que em staging é somente-leitura.

**`backend/scripts/orq/test_oraculo_ronda_com_foto.py`** (novo) — 5 afirmações: esquema capaz de
expressar a regra (+ UNIQUE), nenhuma ronda concluída com obrigatória sem imagem da hora, nenhuma
órfã (disco × banco **nas duas direções**), carimbo do servidor em toda foto (+ hora do aparelho
quando veio offline), nenhuma chave duplicada, e a régua única no serviço.

**`backend/scripts/qa/checar_fila_offline_estourando.py`** (novo) — linha canônica
`TOTAL itens offline atrasados: N`, sai 1 se N>0. Conta o RASTRO da fila do aparelho (o servidor
não enxerga a fila): item `origem_offline` que demorou mais de 24h entre a hora do aparelho e a
do servidor, e `pendente_foto` há mais de 24h em ronda ainda aberta. Agrupa por `device_id`.

### Frontend (commit `d6bda4e53`)

**`frontend/src/features/rondas/CameraCaptura.tsx`** (novo) — `getUserMedia` + `canvas`: quadro
congelado do vídeo, comprimido (≤1280 px, JPEG 0,7) antes de qualquer envio ou fila. **Não há
picker de galeria** para item obrigatório; onde a galeria é aceita (anexo de atividade) a foto sai
marcada `capturada_na_hora=false`, com selo "galeria" no preview. Permissão negada / navegador sem
câmera é dito em português.

**`frontend/src/features/rondas/filaOffline.ts`** (novo) — IndexedDB com **teto declarado: 50
itens / 100 MB**, com aviso ao agente quando enche. Chave idempotente
`ronda:posto:tipo:hora_aparelho:device` (≤120 chars, o tamanho da coluna). `enviarFila()` para no
primeiro erro de **rede** (o sinal caiu de novo) e **descarta com aviso** o que o **servidor**
recusou (4xx que não seja 401/408/429) — guardar uma recusa é fila que nunca esvazia. Cache de
leitura (postos, rondas, ronda ativa) em localStorage = o "download dos locais para uso offline"
do benchmark §8.4.

**`frontend/public/sw-rondas.js`** (novo, escopo `/modulos/operacional/ronda-mobile`) — guarda só
a **casca** (página, chunks, GETs) e devolve do cache quando a rede falha; não cacheia as fotos
(blobs autenticados e grandes). **Não toca** `sw.js` nem `sw-ponto.js`. A fila **não** mora no SW
de propósito: o envio precisa do token do `localStorage` da página.

**`frontend/src/app/modulos/operacional/ronda-mobile/page.tsx`** (editado cirurgicamente)
- checkpoint, check-in/out e atividade passam por `enviarOuEnfileirar` → uma requisição só;
- `nao_conforme` exige foto da câmera já na tela (o servidor confere de novo);
- sem sinal, o item vai para a fila e sobe sozinho no evento `online` (e na abertura da página);
- indicador no card da ronda: "Sem sinal — N no aparelho" / "N pendentes de envio" + "enviar
  agora"; linha do tempo mostra "Aguardando foto" para `pendente_foto`;
- os três carregamentos (postos, rondas, detalhe) caem no cache com aviso honesto
  ("Sem sinal — postos da última sincronização") em vez de erro vermelho.

---

## 3. Estado DEPOIS (medido)

### Oráculo VERDE (mesmo arquivo, mesmo comando)

Com os dados da prova no banco (3 checkpoints, 3 fotos):

```
colunas faltando: 0 · concluídas sem foto na hora: 0 · fotos no banco: 3 · em disco: 3 · chaves duplicadas: 0
OK ronda com foto: esquema expressa a regra, nenhuma concluída sem imagem na hora, nenhuma órfã,
toda foto carimbada pelo servidor, nenhuma chave repetida
exit=0
```

Depois de remover os dados de teste do staging (estado final em que fica):

```
colunas faltando: 0 · concluídas sem foto na hora: 0 · fotos no banco: 0 · em disco: 0 · chaves duplicadas: 0
OK ronda com foto: esquema expressa a regra, nenhuma concluída sem imagem na hora, nenhuma órfã,
toda foto carimbada pelo servidor, nenhuma chave repetida
exit=0
```

**O oráculo não é cego** — provado por acidente: ao apagar a ronda de teste do banco sem apagar os
arquivos, ele acusou na hora as três imagens órfãs em disco, uma a uma, com o caminho.

### Caçador — vermelho e verde

```
-- injetando 30h de atraso num item offline:
  dev-teste · ronda RON-2026-00084 · checkpoint d68c6819 · subiu_atrasado · 30h
aparelho dev-teste: 1 item(ns) atrasado(s)
TOTAL itens offline atrasados: 1          exit=1
-- desfeito:
TOTAL itens offline atrasados: 0          exit=0
```

### Rotas montadas (lidas de `app.routes` no efêmero)

```
['/api/v1/operacional/rondas/minhas-rondas',
 '/api/v1/operacional/rondas/{round_id}/checkpoints/completo']
```

### curl que prova, ponta a ponta (porta 8206, banco de staging)

```
== 1. GET /rondas/minhas-rondas (era 422, rota não existia)
HTTP 200
== 2. ronda nova + iniciar
ronda RON-2026-00084 em_andamento
== 3. rota ANTIGA (JSON, sem arquivo) com tipo foto_evidencia -> nasce pendente_foto
pendente_foto foto_obrigatoria=True
== 4. concluir com pendente_foto -> RECUSADO
{"detail":"1 checkpoint(s) aguardando foto obrigatória tirada na hora: Portao (rota antiga)"} [HTTP 400]
== 5. /checkpoints/completo obrigatorio SEM arquivo -> 422
{"detail":"Foto obrigatória: envie ao menos uma imagem capturada pela câmera na hora"} [HTTP 422]
== 6. /checkpoints/completo com foto da CAMERA -> 201 (checkpoint + foto na MESMA requisicao)
HTTP 201 | repetida False | status nao_conforme | id 3e5a219e
   hora_servidor 2026-09-13T07:43:43.578338Z | hora_aparelho 2026-09-13T07:43:43Z | device dev-teste
   foto capturada_na_hora = True | hash e8076d75251775a6 | 3000 bytes
== 7. IDEMPOTENCIA: a MESMA chamada duas vezes
   repeticao: HTTP 200 | repetida True | id 3e5a219e
   repeticao: HTTP 200 | repetida True | id 3e5a219e
   linhas no banco com a chave k1: 1
   arquivos em disco (nao pode ter sobra das repeticoes): 1
== 8. rota ANTIGA de foto no pendente_foto, capturada na hora -> vira valido
   HTTP 201 | repetida False | status do checkpoint agora: conforme | fotos 1
   a MESMA imagem de novo (dedupe por hash):
   repetida = True
== 9. relogio 1h fora: online -> 422 | offline -> 201
{"detail":"Hora do aparelho difere do servidor em 1:00:00.922609 — acima da folga de 0:10:00; a foto não conta como da hora"} [HTTP 422]
   HTTP 201 | origem_offline True | status conforme
== 10. concluir agora que nada esta pendente
   HTTP 201 | status concluida | checkpoints 3
== 11. o que ficou no banco
    id    | checkpoint_type   | status       | obrig | off_ | h_ap | h_srv | fotos | chave
 f7ec9b77 | foto_evidencia    | conforme     | t     | f    | t    | t     |     1 | -
 3e5a219e | verificacao_posto | nao_conforme | t     | f    | t    | t     |     1 | k1-c82d2287-
 d68c6819 | foto_evidencia    | conforme     | t     | t    | t    | t     |     1 | k3-c82d2287-
```

**A idempotência está provada no §7:** duas chamadas idênticas depois da primeira → **200
`repetida: true`, o MESMO id**, **1 linha** no banco e **1 arquivo** em disco. A segunda não
duplica nem deixa lixo.

---

## 4. Fiação pendente para o integrador

### 4.1 DDL de PRODUÇÃO (aplicado só no staging por mim)

```sql
ALTER TABLE inspection_checkpoints
  ADD COLUMN IF NOT EXISTS foto_obrigatoria  boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS hora_aparelho     timestamptz,
  ADD COLUMN IF NOT EXISTS hora_servidor     timestamptz DEFAULT now(),
  ADD COLUMN IF NOT EXISTS device_id         varchar(80),
  ADD COLUMN IF NOT EXISTS chave_idempotente varchar(120),
  ADD COLUMN IF NOT EXISTS origem_offline    boolean NOT NULL DEFAULT false;

CREATE UNIQUE INDEX IF NOT EXISTS ux_inspection_checkpoints_chave_idempotente
  ON inspection_checkpoints (chave_idempotente);
```

Sem risco de bloquear: `inspection_checkpoints` tem 15 linhas em produção. O `UNIQUE` sobre coluna
nova (toda NULL) não colide com nada — em Postgres, NULLs não conflitam entre si.

### 4.2 `backend/scripts/qa/checar_regressao.py` (arquivo proibido para mim)

Linha exata, no dicionário `CACADORES` (roda no container):

```python
    "fila_offline_estourando": "scripts/qa/checar_fila_offline_estourando.py",
```

O oráculo **não** precisa de registro: a varredura da meia-noite globa `scripts/orq/test_*.py`.

### 4.3 `main_production.py`, `celery_app.py`, `_modules/*.json`

**Nada.** As duas rotas novas entraram como métodos do `inspection_round_router`, que já é montado
em `/api/v1/operacional/rondas` (provado em `app.routes`, §3). Sem task nova, sem tela nova de
redesign — a ronda-mobile é página própria.

### 4.4 Deploy

Backend precisa de **bake** (as colunas e o endpoint novo). Frontend precisa de build pelo
`./scripts/deploy/deploy_frontend.sh` — **eu não rodei nenhum dos dois** (proibido pelo contrato).
Ordem obrigatória: **DDL → bake do backend → build do frontend**. O contrário (frontend primeiro)
faz o celular chamar `/checkpoints/completo` num backend que ainda não tem a rota.

---

## 5. O que NÃO foi feito, e por quê

- **Checklist**: a frente cita "ronda e checklist". O checklist operacional **não tem módulo
  próprio** neste repositório (só menções em `redesign_builders/documentos.py` e `rh.py`, que são
  outra coisa). Não inventei um: a mesma trava vale para ele quando existir, porque a régua é uma
  função (`foto_e_obrigatoria`) e o endpoint é genérico.
- **`nao_conforme` não é obrigatório no SERVIDOR**, só na tela. O servidor exige foto quando o
  tipo é `foto_evidencia` ou quando o cliente manda `foto_obrigatoria: true` — e o app manda em
  todo `nao_conforme`. Decisão conservadora: chumbar no servidor quebraria qualquer integração ou
  script que hoje registre não conformidade sem foto, e essa é decisão do dono, não minha. Se o
  Jordan disser "não conforme sem foto não existe", é **uma linha** em `foto_e_obrigatoria`.
- **Política "só no Wi-Fi"** (pré-mortem 6.5): não implementada. `navigator.connection` é
  incompleto no iOS e a decisão ("segurar a foto até ter Wi-Fi") muda o significado da ronda —
  a evidência atrasa de propósito. O que foi feito contra a franquia foi a **compressão** (a foto
  típica cai de vários MB para ~100–300 KB). Decisão do dono.
- **Política de descarte quando a fila enche**: a fila **recusa item novo** com aviso e **não
  apaga nada**. Apagar registro de ronda para caber mais é exatamente o que o pré-mortem 6.2 teme.
- **Purga de arquivo órfão**: o oráculo **acusa**, ninguém apaga automaticamente. Apagar imagem de
  evidência sem gente olhando é irreversível.
- **Migration Alembic**: `alembic/versions/` é zona proibida. O DDL está no §4.1.
- **Tipos do projeto inteiro**: `npx tsc --noEmit` no projeto completo **estoura 2 GB de heap**
  (OOM, morre em ~68 s). Validei com um `tsconfig` de escopo reduzido aos 3 arquivos desta frente,
  com os mesmos `compilerOptions`: **0 erros**. ESLint nos 3: **0 erros, 0 avisos**. **Não** rodei
  `npm run build` (proibido). O que fica sem validação: o build completo e o render real.
- **Render no navegador**: não testei a tela. Sem build de frontend, não há como. É o item 1 do §6.

---

## 6. Como o Jordan testa amanhã (no celular)

> Depende do deploy do §4.4 (DDL → bake backend → build frontend). Antes disso a tela chama uma
> rota que não existe em produção.

1. **No celular, em HTTPS** (a câmera só funciona em HTTPS): abra
   `https://erp.conectamais.pro/modulos/operacional/ronda-mobile` e faça login.
2. **Inicie uma ronda** escolhendo um ou dois postos. A lista de "minhas rondas" tem de aparecer —
   antes desta frente ela dava 422 e vinha vazia.
3. **REGISTRAR CHECKPOINT** → escolha o posto → mude a situação para **"Não conforme"**. A tela
   passa a exigir foto e o botão vira **"Abrir câmera"**. Repare que **não há opção de galeria**.
4. **Tente salvar sem foto**: a tela recusa ("Não conforme exige foto tirada pela câmera agora").
5. **Abra a câmera, tire a foto, salve.** Um toast confirma. Na linha do tempo a foto aparece já
   anexada ao checkpoint — **uma requisição só**, não duas.
6. **O teste que importa — modo avião:**
   a. Ligue o **modo avião** no celular (a página continua aberta).
   b. O card da ronda mostra **"Sem sinal — registros ficam no aparelho"**.
   c. Registre **dois ou três** checkpoints com foto, normalmente.
   d. Cada um avisa: *"Sem sinal — checkpoint guardado no aparelho; sobe sozinho quando o sinal
      voltar"*. O contador mostra **"N no aparelho"**.
   e. **Desligue o modo avião.** Em segundos o toast diz *"N registros pendentes enviados"*, o
      contador zera e os checkpoints aparecem na linha do tempo com as fotos.
   f. Se quiser forçar, há o link **"enviar agora"** ao lado do contador.
7. **Tente concluir a ronda** com algum checkpoint "Aguardando foto" (badge amarelo): o sistema
   **recusa** e diz qual é. Mande a foto e conclua.
8. **Checagem de servidor, se quiser ver o dado cru** (host):
   ```bash
   docker exec conecta-pro-postgres psql -U postgres -d conecta_pro -c \
     "select left(id::text,8), checkpoint_type, status, foto_obrigatoria, origem_offline,
             hora_aparelho, hora_servidor, jsonb_array_length(photos) fotos
        from inspection_checkpoints order by created_at desc limit 10"
   ```
   `hora_servidor` é a oficial; `hora_aparelho` é o que o celular disse. Se as duas divergirem
   muito num registro **online**, o servidor já terá recusado.
9. **As duas travas, rodando sozinhas depois do bake:**
   ```bash
   docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_ronda_com_foto.py
   docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/qa/checar_fila_offline_estourando.py
   ```

---

## 7. Riscos residuais do pré-mortem que continuam

- **0.1 — Sem Sentry (`SENTRY_DSN=` vazio).** Este é o risco mais sério **para esta frente
  especificamente**: o código novo roda no celular do porteiro, com câmera, IndexedDB e
  reconexão. Uma quebra lá é **invisível** — o `toast` avisa quem está segurando o aparelho, e mais
  ninguém. Continua sendo uma linha de `.env`.
- **0.3 — `docker cp` não publica.** Nada desta frente está em produção. Sem bake, o
  `/checkpoints/completo` não existe lá, e a página nova chamaria uma rota 404.
- **6.1 (parcialmente vivo)** — a galeria continua acessível no anexo de atividade, **de
  propósito** (ata de reunião, foto antiga do síndico). Só que o que vem de lá chega ao banco com
  `capturada_na_hora: false` e **não fecha** item obrigatório. A trava é o campo, não o botão.
- **6.2 — fila cheia.** O teto existe (50 itens / 100 MB) e avisa, mas quando enche o porteiro
  **não consegue registrar** até achar sinal. É o menor dos males comparado a apagar evidência,
  e continua sendo um limite real de um turno muito longo sem sinal.
- **6.5 — franquia de dados.** Mitigada por compressão, não resolvida: não há "só no Wi-Fi".
- **Novo, descoberto aqui:** apagar uma ronda **direto no banco** (DELETE, não o soft-delete da
  API) deixa as imagens órfãs em disco. O oráculo acusa; ninguém apaga sozinho. Não mexa em
  `inspection_rounds` por psql em produção.
- **Relógio do aparelho.** A folga é de 10 minutos (`TOLERANCIA_RELOGIO`). Um celular com o
  relógio muito errado **e** com sinal vai ver a foto recusada com a mensagem explicando. É de
  propósito: relógio errado é o que torna o EXIF inútil como prova.

---

## 8. Higiene

- Container efêmero `teste-frente-06` **parado e removido** ao fim do trabalho.
- Dados de teste **removidos** do staging (`RON-2026-00084` e as três imagens do
  diretório de uploads do teste).
- DDL aplicado **só** em `conecta_pro_staging`. Produção não foi tocada em nenhum momento
  (a única leitura de produção foi um `SELECT` de contagem, declarado no §1).
- `frontend/tsconfig.tsbuildinfo` restaurado; o `tsconfig` de escopo e o link de
  `node_modules` usados para o `tsc` foram apagados. `git status` limpo fora dos commits.
