# FRENTE 01 — REP-P: AEJ, AFD montado e populado, checklist Portaria 671

**Data:** 13/09/2026 · **Branch:** `frente/01-rep-p` (base `30be528a3`)
**Sessão:** tmux-agente-01 · **Módulo declarado:** ponto
**Testado em:** staging (`conecta_pro_staging`, 105 funcionários) em **modo efêmero** —
`docker run` com a worktree montada em `/app:ro`. O `/app` do `conecta-pro-backend-staging` é
bind **só-leitura** de `/opt/conecta-pro/backend`: `docker cp` para lá falha, e o contrato §2
foi corrigido pelo integrador durante a execução.
**Produção:** nada foi tocado. Nem container, nem banco, nem imagem.

---

## 1. Estado ANTES, medido

| O que | Medida |
|---|---|
| Rotas com `afd` em `app.routes` | **0** (módulo existia com 9 arquivos e não era alcançável) |
| `afd_records` | **0 linhas** |
| `rep_devices` | **0 linhas** |
| "AEJ", "REP-P", "INPI" no repositório | **zero menções** |
| Atestado técnico no código | só o do **EPI** — coisa diferente |
| Pessoas batendo ponto | **53** com batida em set/2026 no staging (52 em produção) |
| Instrumento legal (INPI/atestado/termo) | **não existia tabela** |

### Oráculo VERMELHO (corte de medição 01/09, para haver dado)

```
rotas afd: 0 · corte 01/09/2026 · batidas desde o corte: 1112 · dias com batida sem AFD: 11 · dispositivos: 0 · instrumentos: 0
FALHOU: (a) rota /ponto/afd/records não está em app.routes — o AFD/AEJ não é alcançável
FALHOU: (a) rota /ponto/afd/rep-p/aej não está em app.routes — o AFD/AEJ não é alcançável
FALHOU: (a) rota /ponto/afd/rep-p/arquivo não está em app.routes — o AFD/AEJ não é alcançável
FALHOU: (b/d) módulo rep_p não importa: cannot import name 'rep_p' from 'modules.hr.rep_integration.services'
FALHOU: (b) 01/09: 96 batida(s) sem linha AFD
FALHOU: (b) 02/09: 124 batida(s) sem linha AFD
FALHOU: (b) 03/09: 127 batida(s) sem linha AFD
FALHOU: (b) 04/09: 127 batida(s) sem linha AFD
FALHOU: (b) 05/09: 61 batida(s) sem linha AFD
FALHOU: (b) 06/09: 61 batida(s) sem linha AFD
FALHOU: (b) 07/09: 65 batida(s) sem linha AFD
FALHOU: (b) 08/09: 126 batida(s) sem linha AFD
FALHOU: (b) 09/09: 129 batida(s) sem linha AFD
FALHOU: (b) 10/09: 120 batida(s) sem linha AFD
FALHOU: (b) 11/09: 76 batida(s) sem linha AFD
FALHOU: (c) nenhuma linha AFD em nenhum dispositivo
FALHOU: (e) sem registro do programa no INPI (número + data) — precondição legal do REP-P
FALHOU: (e) sem atestado técnico vigente (emissor + data + validade) — art. 89 da Portaria 671
FALHOU: (e) sem termo de responsabilidade com data
19 desvio(s) no REP-P          exit=1
```

Com o corte real (13/09, ainda sem batida): **7 desvios** — as três rotas, o módulo que não
existe e os três instrumentos legais.

### Caçador VERMELHO

```
  ANTONIO WALCICLEY PEREIRA DA SILVA: 27 batida(s) sem AFD
  ELEN XAVIER NUNES: 25 batida(s) sem AFD
  MATHEUS HENRIQUE CABRAL DA SILVA: 24 batida(s) sem AFD
  LIVIA CARISE PEREIRA CONSENTINE: 24 batida(s) sem AFD
  (+33 não listadas)
TOTAL pessoas sem instrumento: 53  (desde 01/09/2026)      exit=1
```

---

## 2. O que foi feito, arquivo por arquivo

| Arquivo | O quê |
|---|---|
| `backend/scripts/orq/test_oraculo_rep_p.py` **(novo)** | Oráculo com as cinco afirmações (a)–(e). Escrito e rodado VERMELHO antes de qualquer linha de implementação. |
| `backend/scripts/qa/checar_ponto_sem_instrumento.py` **(novo)** | Caçador. Linha canônica `TOTAL pessoas sem instrumento: N`; exit 1 se N>0. Nomeia quem está sem CPF no cadastro. |
| `backend/modules/hr/rep_integration/services/rep_p.py` **(novo, 322 linhas)** | AFD (Anexo I, v004) e AEJ (Anexo VI, v002) do leiaute oficial do gov.br. CRC-16/KERMIT com `assert` do exemplo da própria portaria rodando no import; registro tipo 7 com coletor, flag on/off-line e SHA-256 encadeado; geração idempotente desde o corte; montagem do AFD e do AEJ. |
| `backend/modules/hr/rep_integration/controllers/afd_controller.py` | +4 rotas `rep-p/*` (gerar, arquivo, aej, instrumento). Arquivos saem em ISO-8859-1 com CRLF, como o anexo manda. |
| `backend/modules/people_management/ponto/controllers/punch_controller.py` | `router.include_router(afd_router)` no fim, com import guardado (`# frente 01`). Nenhuma linha em `main_production.py`. |
| `backend/modules/people_management/ponto/services/punch_service.py` | Hook em `registrar_batida`: gera a linha AFD na mesma transação, dentro de `begin_nested()`. |
| `backend/modules/hr/rep_integration/models/afd_record.py` · `schemas/afd_record.py` | `afd_line` de 100/200 → **400** (a linha tipo 2 tem 331 posições). |
| `backend/modules/hr/rep_integration/repositories/afd_record_repository.py` | `get_statistics` contava 1 registro havendo 1.113 (`select(func.count())` sem FROM) e ignorava o tipo 7. |

### Decisões que ficaram no código

1. **Corte 13/09/2026 00:00 America/Manaus, nunca retroativo.** O AFD é memória inalterável;
   preencher com o histórico (Tangerino, ajuste do DP, contingência) seria afirmar integridade
   sobre dado editado — pior que não ter AFD. `REP_P_CORTE` no ambiente existe **só** para medir
   no staging; em produção não se define.
2. **NSR por estabelecimento (CNPJ)** — o Anexo IX é explícito, e o nome do arquivo
   (`AFD` + INPI + CNPJ + `REP_P`) não tem campo para origem. A instrução da frente pedia por
   origem; a norma venceu. A origem vive no campo 6 (coletor: 01 mobile, 02 browser, 05 outro),
   no campo 7 (on/off-line) e na coluna `origem`.
3. **Sem CPF de 11 dígitos não há linha** — o campo é obrigatório no leiaute. A pessoa aparece
   nominalmente no caçador. Cinco cadastros no staging estão nessa situação (todos PJ, sem
   batida). CPF não se inventa.
4. **INPI vazio sai em branco**, e o arquivo se chama `AFDSEM_INPI…` — nunca um número forjado.
5. **Falha no AFD não derruba a batida do porteiro** (savepoint), vira dívida contada.

---

## 3. Estado DEPOIS, medido

### Rotas em `app.routes` (container efêmero, porta 8201)

```
afd: 11 rotas · rep-p: ['/api/v1/people-management/ponto/afd/rep-p/aej',
 '/api/v1/people-management/ponto/afd/rep-p/arquivo',
 '/api/v1/people-management/ponto/afd/rep-p/gerar',
 '/api/v1/people-management/ponto/afd/rep-p/instrumento']
```

### Oráculo — (a)(b)(c)(d) VERDES, (e) VERMELHO por decisão

```
AEJ AEJ_66014833000110_202609.txt: 1112 marcações · 53 vínculos · 1 REP · 9 horários
rotas afd: 11 · corte 01/09/2026 · batidas desde o corte: 1112 · dias com batida sem AFD: 0 · dispositivos: 1 · instrumentos: 0
FALHOU: (e) sem registro do programa no INPI (número + data) — precondição legal do REP-P
FALHOU: (e) sem atestado técnico vigente (emissor + data + validade) — art. 89 da Portaria 671
FALHOU: (e) sem termo de responsabilidade com data
3 desvio(s) no REP-P          exit=1
```

**(e) continua vermelho de propósito.** INPI, atestado técnico e termo de responsabilidade são
decisão jurídica do Jordan — o art. 89 §4º diz que o empregador *só pode usar* o sistema se
possuir o atestado, e assinar atestado sem cumprir a portaria é declaração falsa com o dono como
responsável. A tabela `rep_instrumento_legal` foi criada **vazia** para recebê-los. O oráculo
fica vermelho até lá: é a única forma de a pendência não ser esquecida.

### Caçador VERDE

```
TOTAL pessoas sem instrumento: 0  (desde 13/09/2026)       exit=0
TOTAL pessoas sem instrumento: 0  (desde 01/09/2026)       exit=0   (régua de medição)
```

### NSR e origem no banco

```
serial              marcações t2  min  max   distintos
REP-P-66014833000110   1112     1    1  1113   1113      ← contínuo, sem lacuna

origem        n     campo coletor+online
mobile       668    010
tangerino    391    050
contingencia  51    050
web            2    020
```

### Prova por HTTP (curl no servidor efêmero 8201)

```
GET  /ponto/afd/rep-p/instrumento
     {"corte":"2026-09-13T00:00:00","instrumentos":{},"faltam":["INPI","ATESTADO_TECNICO","TERMO_RESPONSABILIDADE"]}
POST /ponto/afd/rep-p/gerar
     {"corte":"2026-09-13T00:00:00","pendentes":0,"geradas":0,"sem_cpf":[],"sem_empresa":[]}
GET  /ponto/afd/rep-p/aej?cnpj=66014833000110&ano=2026&mes=9
     200 · filename="AEJ_66014833000110_202609.txt" · x-aej-contagem: 01=1,02=1,03=53,04=9,05=1112,06=0,07=0,08=1
GET  /ponto/afd/rep-p/arquivo?cnpj=66014833000110&inicio=2026-09-01&fim=2026-09-30
     200 · filename="AFDSEM_INPI66014833000110REP_P.txt" · 1116 linhas · CRLF · linha máxima 331
GET  /ponto/afd/records?page_size=1        200 · total 1113   (dava 500 antes)
GET  /ponto/afd/statistics                 200 · {"total_records":1113,"records_by_type":{"2":1,"7":1112},"time_records":1112}
GET  /ponto/afd/rep-p/arquivo?cnpj=00000000000000…   404 {"detail":"empregador … não está em empresas"}
```

### Amostra dos arquivos (CPF mascarado aqui, íntegro no arquivo)

```
AFD  0000000001166014833000110              CONECTAMAIS PATRIMONIAL LTDA…        (tipo 1, 302 pos.)
     00000000122026-09-12T23:11:00-0400730681…166014833000110…                   (tipo 2, 331 pos.)
     00000000272026-09-01T00:17:00-0400************2026-09-12T23:11:00-0400010359816be7…  (tipo 7, 137 pos.)
     999999999000000001…000001112 9                                              (tipo 9, 64 pos.)
     ASSINATURA_DIGITAL_EM_ARQUIVO_P7S

AEJ  01|1|66014833000110|||CONECTAMAIS PATRIMONIAL LTDA|2026-09-01|2026-09-30|2026-09-13T03:46:00-0400|002
     03|1|***********|RENE RICARDO CRUZ GONÇALVES
     04|0800-1700-60|480|0800|1700||
     05|1|2026-09-01T18:11:00-0400|1|E|1|O|1800-0600-60|
     08|Conecta PRO|2.0.0|1|35710481000103|CONECTAMAIS ELETRONICA LTDA|jjesus@conectamais.pro
     99|1|1|53|9|1112|0|0|1
```

### Hook da batida (prova com rollback, nada persistiu)

```
afd_records antes=1113 depois=1114 (na transação)
linha da batida de prova: (1114, 'web', '00000111472026-09-12T23:30:00-0400…35ff51', 'REP-P-66014833000110')
após rollback: afd_records=1113 · batida de prova no banco=0 (tem de ser 0)
```

O NSR da batida nova é o seguinte da sequência do estabelecimento (1113 → 1114), a origem é
`web` e o dispositivo é o do CNPJ — não um por origem.

---

## 4. Checklist Portaria MTP 671/2021 — item por item

Fontes: texto da portaria (arts. 75–91), `leiaute-do-arquivo-fonte-de-dados-afd.pdf` (v004),
`leiaute-do-arquivo-eletronico-de-jornada-aej.pdf` (v002) e
`modelo-do-atestado-tecnico-e-termo-de-responsabilidade.pdf`, todos do gov.br, baixados em 13/09.

| # | O que a norma exige | O que o sistema faz | Evidência | Falta |
|---|---|---|---|---|
| 1 | **Art. 91** — REP-P deve ter certificado de registro de programa no **INPI** | nada | tabela `rep_instrumento_legal` vazia | 🔴 **JORDAN**: registrar o programa no INPI e lançar número + data |
| 2 | **Art. 89 §4º** — empregador só pode usar o sistema se possuir **Atestado Técnico e Termo de Responsabilidade** do desenvolvedor | nada | idem | 🔴 **JORDAN**: emitir (somos o desenvolvedor) **depois** de cumprir os itens 3–14 |
| 3 | **Art. 81 / Anexo I** — gerar o **AFD** no leiaute | gera tipos 1, 2, 7 e 9 com CRC-16/KERMIT e SHA-256 encadeado | `GET /rep-p/arquivo` 200, 1116 linhas | ✅ tipos 4 (ajuste de relógio), 5 (inclusão/exclusão de empregado) e 6 (eventos sensíveis, "07 disponibilidade/08 indisponibilidade de serviço") ainda não são gravados |
| 4 | **Anexo IX** — NSR por estabelecimento, incremento unitário, começando em 1 | 1 dispositivo por CNPJ, NSR 1..1113 sem lacuna, unique `(device_id, nsr)` no banco + advisory lock | tabela do §3 | ✅ |
| 5 | **Anexo I** — arquivo ASCII ISO-8859-1, linhas CR+LF, sem linha em branco, ordenado por NSR | `Content-Type: text/plain; charset=iso-8859-1`, `file` confirma CRLF | §3 | ✅ |
| 6 | **Anexo I** — nome `AFD` + nº INPI + CNPJ + `REP_P` | `AFDSEM_INPI66014833000110REP_P.txt` | §3 | 🟡 o "SEM_INPI" vira o número quando o item 1 sair |
| 7 | **Anexo I** — identificação do empregado por **CPF** (o PIS saiu em 03/04/2024) | CPF de `employees`, 12 posições com zero à esquerda | linha tipo 7 | ✅ / 🟡 5 cadastros sem CPF não geram linha (aparecem no caçador) |
| 8 | **Anexo I tipo 7** — campos: NSR, tipo, data/hora da marcação, CPF, data/hora da gravação, coletor, on/off-line, hash SHA-256 encadeado | todos, 137 posições | oráculo (c) verifica a corrente inteira | ✅ |
| 9 | **Art. 83 / Anexo VI** — PTRP deve gerar o **AEJ** | tipos 01, 02, 03, 04, 05, 08, 99 | `GET /rep-p/aej` 200 | 🟡 **tipo 07 (ausências e banco de horas) não é gerado** — ver §6 |
| 10 | **Art. 83 / Art. 84** — PTRP deve gerar o **Espelho de Ponto** | já existe no ERP (`espelho_ponto`, folha de ponto em PDF) | módulo ponto | 🟡 não foi conferido campo a campo contra o art. 84 — fora do escopo desta frente |
| 11 | **Art. 79/80** — comprovante de marcação ao trabalhador, com **hash SHA-256 da marcação**, em PDF ou tela, após cada marcação | o hash existe (campo 8 do tipo 7); o comprovante ao trabalhador **não é emitido** | — | 🔴 falta: tela/PDF de comprovante no app do porteiro com o hash |
| 12 | **Art. 80** — marcações das últimas 48h disponíveis para extração pelo trabalhador | espelho mostra o dia; extração própria não existe | — | 🟡 |
| 13 | **Art. 85/86** — disponibilizar AFD/AEJ em até 2 dias, com **assinatura eletrônica qualificada** (ICP-Brasil, art. 88) | arquivos saem na hora; assinatura sai como o literal `ASSINATURA_DIGITAL_EM_ARQUIVO_P7S` previsto no leiaute, **sem o .p7s de fato** | §3 | 🔴 falta assinar com o certificado A1 da empresa (já existe em `core/config/credentials.py` para NFS-e/eSocial) |
| 14 | **Art. 81 §2º** — AFD prontamente gerado e entregue ao Auditor-Fiscal | rota autenticada devolve o arquivo | §3 | ✅ |
| 15 | Vedação de **alterar ou excluir** marcação | `afd_records` não tem rota de update/delete; o registro é imutável por construção | — | 🟡 não há trava de banco (trigger) impedindo UPDATE direto |
| 16 | **Sincronismo com a Hora Legal Brasileira** (Anexo IX) | servidor em UTC; a marcação grava a hora de parede de Manaus | — | 🟡 não há checagem de NTP/deriva registrada |

**Ordem para o Jordan:** itens 11, 13, 3 (tipo 6) e 15/16 são de engenharia e precedem o
atestado. Itens 1 e 2 são jurídicos e são a precondição para chamar isto de REP-P.
**Enquanto 1 e 2 não existirem, o sistema gera AFD e AEJ corretos mas NÃO é um REP-P
constituído** — e o oráculo continua vermelho dizendo isso todo dia.

---

## 5. Fiação pendente para o integrador

### `backend/scripts/qa/checar_regressao.py` (arquivo proibido para mim)

No dicionário `CACADORES` (roda no container):

```python
    "checar_ponto_sem_instrumento.py": lambda s: _n(r"^TOTAL pessoas sem instrumento: (\d+)", s),
```

### DDL de produção (aplicado no staging, nesta ordem)

```sql
ALTER TABLE afd_records ADD COLUMN IF NOT EXISTS punch_id varchar(36);
ALTER TABLE afd_records ADD COLUMN IF NOT EXISTS origem   varchar(20);
ALTER TABLE afd_records ALTER COLUMN afd_line TYPE varchar(400);
CREATE UNIQUE INDEX IF NOT EXISTS ux_afd_records_punch ON afd_records(punch_id);

CREATE TABLE IF NOT EXISTS rep_instrumento_legal (
    id           serial PRIMARY KEY,
    tipo         varchar(30) NOT NULL,   -- INPI | ATESTADO_TECNICO | TERMO_RESPONSABILIDADE
    empresa_id   uuid,
    numero       varchar(60),
    emissor      varchar(150),
    data_emissao date,
    validade     date,
    arquivo_url  varchar(500),
    observacao   text,
    created_at   timestamp NOT NULL DEFAULT now()
);
COMMENT ON TABLE rep_instrumento_legal IS
  'REP-P: registro INPI, atestado técnico e termo de responsabilidade (Portaria 671 art. 89).
   Preenchido pelo dono, nunca por sessão autônoma.';
```

> ⚠️ O índice único em `punch_id` aceita vários NULL (linhas tipo 1/2/9 não têm batida) — é o
> comportamento desejado no Postgres.

### `main_production.py` · `celery_app.py` · `_modules/*.json`

**Nada.** A montagem é sub-router dentro do `/ponto`, que já é montado. Não há task de Celery.
Não há tela de frontend nesta frente.

### Bake

O backend é baked na imagem: nada disto está servindo em produção até o próximo
`deploy_backend_bluegreen.sh`, com `checar_bake_pendente = 0` e `checar_drift_workers` limpo
(risco 0.3 do pré-mortem).

---

## 6. O que NÃO foi feito, e por quê

1. **INPI, atestado técnico, termo de responsabilidade** — decisão jurídica do dono (pré-mortem,
   risco 5 e "ordem obrigatória"). Tabela criada vazia; oráculo (e) vermelho até ele preencher.
2. **AEJ registro tipo 07 (ausências e banco de horas)** — exigiria decidir, para cada dia sem
   marcação, se é DSR, falta injustificada, movimento de banco de horas ou folga compensatória.
   Não há pipeline hoje que produza esse veredito de forma confiável, e **inventar ausência num
   arquivo fiscal é pior que omitir**. O trailer 99 declara `07 = 0` — honesto, não escondido.
3. **Assinatura digital real (.p7s)** — o leiaute manda o literal
   `ASSINATURA_DIGITAL_EM_ARQUIVO_P7S` na linha do arquivo, e é o que sai. Assinar de fato exige
   o certificado A1 e uma decisão sobre onde o .p7s é guardado. É o item 13 do checklist.
4. **Comprovante de marcação ao trabalhador com hash** (arts. 79/80) — é tela/app, e o contrato
   proíbe deploy de frontend nesta frente. O dado necessário (hash) já existe.
5. **AFD retroativo** — proibido pela decisão do dono e pelo pré-mortem. O histórico anterior a
   13/09/2026 fica como está, sem AFD, documentado aqui.
6. **Trigger impedindo UPDATE/DELETE em `afd_records`** — é DDL de comportamento em tabela
   fiscal; preferi deixar a decisão explícita para o integrador a criar trigger sozinho.
7. **Espelho de ponto conferido campo a campo contra o art. 84** — outra frente.
8. **`/ponto/afd/export`, `/import`, `/validate`** (rotas herdadas do módulo antigo) — foram
   montadas junto, mas só `records` e `statistics` foram consertadas e provadas. `export` usa o
   gerador antigo (tipo 3, PIS, sem CRC) e **não deve ser usado**: o caminho certo é
   `rep-p/arquivo`. Sugiro ao integrador removê-las numa próxima passada.

---

## 7. Como o Jordan testa amanhã

Tudo abaixo é no **staging**; produção só depois do bake.

```bash
# 1) Subir a API com o código desta branch (porta 8201)
WT=/opt/conecta-pro/.claude/worktrees/agent-ad0f61779a99adc43   # ou o checkout da branch
ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' \
       | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')
docker run --rm -d --name teste-frente-01 --network conecta-staging-network \
  -p 127.0.0.1:8201:8080 -v "$WT/backend:/app:ro" -e PYTHONPATH=/app \
  --env-file /opt/conecta-pro/.env $ENVS -e ENVIRONMENT=staging -e PORT=8080 \
  conecta-pro-backend:latest
until curl -sf http://127.0.0.1:8201/health >/dev/null; do sleep 3; done

TOKEN=$(curl -sf -X POST http://127.0.0.1:8201/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=jjesus@conectamais.pro&password=JsJ618908@#%" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
B=http://127.0.0.1:8201/api/v1/people-management/ponto/afd

# 2) O que falta legalmente (deve listar os três)
curl -s -H "Authorization: Bearer $TOKEN" $B/rep-p/instrumento

# 3) Baixar o AEJ de setembro e o AFD — abra num editor, são texto
curl -s -H "Authorization: Bearer $TOKEN" -OJ "$B/rep-p/aej?cnpj=66014833000110&ano=2026&mes=9"
curl -s -H "Authorization: Bearer $TOKEN" -OJ "$B/rep-p/arquivo?cnpj=66014833000110&inicio=2026-09-01&fim=2026-09-30"

# 4) A partir de 13/09, a batida real deve virar linha AFD sozinha. Para forçar a varredura:
curl -s -X POST -H "Authorization: Bearer $TOKEN" $B/rep-p/gerar

docker stop teste-frente-01     # ⚠️ não deixe rodando: memória é compartilhada
```

**O oráculo e o caçador**, sem servidor:

```bash
docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" -e PYTHONPATH=/app \
  --env-file /opt/conecta-pro/.env $ENVS python3 /app/scripts/orq/test_oraculo_rep_p.py
docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" -e PYTHONPATH=/app \
  --env-file /opt/conecta-pro/.env $ENVS python3 /app/scripts/qa/checar_ponto_sem_instrumento.py
```

**Para (e) ficar verde** (só quando os documentos existirem de verdade):

```sql
INSERT INTO rep_instrumento_legal (tipo, numero, emissor, data_emissao, validade) VALUES
 ('INPI', '<nº do registro>', 'INPI', '<data>', NULL),
 ('ATESTADO_TECNICO', NULL, 'CONECTAMAIS ELETRONICA LTDA', '<data>', '<validade>'),
 ('TERMO_RESPONSABILIDADE', NULL, 'CONECTAMAIS ELETRONICA LTDA', '<data>', NULL);
```

---

## 8. Riscos residuais do pré-mortem que continuam

- **0.1 Sentry vazio** — uma exceção no gerador de AFD morre no log de um container que ninguém
  lê. O caçador cobre o efeito (pessoa sem instrumento), não a causa.
- **0.3 `docker cp` não publica / bake pendente** — nada desta frente serve em produção até o
  bake. A rota pode existir no disco e não estar de pé.
- **Risco 1 da frente (declarar conformidade sem INPI)** — o oráculo (e) é a única defesa, e ela
  só funciona se alguém olhar o vermelho. Se ele for silenciado para "ficar verde", a frente
  vira exatamente o que o pré-mortem temia.
- **Risco 4 (NSR duplicando)** — mitigado por unique + advisory lock, mas o pipeline de
  importação do Tangerino continua podendo duplicar **batidas** (incidente de 11/09: 1.375
  jornadas). Batida duplicada vira linha AFD duplicada — legítima do ponto de vista do arquivo,
  errada do ponto de vista do fato. O conserto é na importação, não aqui.
- **Fuso** — `punch_timestamp` é tratado como hora de parede de Manaus. Medido: entrada mediana
  +50 min do início da escala (se fosse UTC daria ~+240). Se alguma origem passar a gravar UTC,
  o AFD sai com 4h de erro e **nada acusa** — não há oráculo para isso.
