# DGX T2 — Apontamentos/Ponto: DGX exercitado por dentro, fechamento como ato e integração de batimentos

**Data:** 24/09/2026 · **Branch:** `dgx/t2-ponto` · **Módulo:** ponto (people_management) · **Agente:** T2
**Sandbox:** `conecta-pro-postgres-staging` / `conecta_pro_staging` · container HTTP `teste-dgx-t2` (porta 8222, parado ao fim)
**Lista de lacunas (Fase C, commit 4ab2f8015):** `docs/dgx/lacunas/ponto.md`

---

## 1. Estado ANTES, medido (staging, 24/09/2026)

| O quê | Medido |
|---|---|
| Mês "fechado" | `time_sheets`: 07/2026 = 1 fechado, 08 e 09/2026 = 0 (65 e 51 calculados); `gp_monthly_closings`: 50 fechados em 06/2026. Dois lugares, nenhum escritor de batida consultava |
| Ajuste do DP em mês fechado (`POST /ponto/ajuste`) | **gravava** (`dashboard_service.registrar_ajuste` insere direto; o `motivo` só ia para o log) |
| Lançamento manual em mês fechado (`POST /hr/time-records`) | **gravava** (`time_record_service.create_manual`) |
| Reabertura | `time_sheet_service.reopen_time_sheet` existe, **sem rota** (controller é stub de 13 linhas); `gp_monthly_closings` não tinha caminho de reabrir |
| Importar arquivo de relógio | `POST /hr/rep/afd/import` grava **só `afd_records`** (tipo 3, NSR único por device) — 0 batidas nascem daí; só leiaute 1510 (PIS); sem tela. 801 linhas de AFD (todas geradas pelo REP-P próprio, tipo 7, leiaute 671) |
| `gp_clock_punches` por `device_type` | tangerino 6.621 · mobile 2.862 · web 2.200 · contingência 116 · facial 6 · manual 2 · conecta_pro_app 1 · **relogio 0**; `chave_idempotente` preenchida em 2 linhas |
| Pessoas | 63 ativos, 47 com PIS, todos com CPF |
| Oráculo `test_oraculo_integracao_batimentos.py` | **VERMELHO** (ImportError — ver §4) |

## 2. O que o DGX tem (Fase A — o que foi de fato exercitado)

Tabela completa botão a botão em `docs/dgx/lacunas/ponto.md`. O essencial:

- **Modelo de escala** (dias trabalho/folga, horas/dia, dias/mês) × **turno** (código numérico + sequências E1/S1/E2/S2, folga, compensado, não paga VR, abater HE, HE 100%, *replicar × quantidade*) → **Aprovar** ativa e gera «1X1 - 07:00 ÀS 19:00». A escala chega à pessoa pela **vaga do contrato** + **movimentação** (7 motivos, sequência inicial).
- **Configuração de ponto** por escopo (pessoa/contrato/vaga/colaborador/função/modelo/escala, campo vazio = herdado) é o que o motor LÊ: tolerância, **tipo de cálculo** (ESCALA / BANCO DE HORAS / ESCALA COMPENSAÇÃO / CARGA DIÁRIA / CARGA MENSAL / JORNADA POR ESCALA / CARGA MENSAL PROPORCIONAL / FOLGA TRABALHADA), intrajornada, **mapa evento→rubrica** (atraso, HE, HE100, falta automática, noturna, noturna reduzida, hora trabalhada, falta dia compensado, adicional feriado), folga trabalhada (período/tipo/valor-hora), benefícios de ponto (café, descanso, diária, reembolsos, missão, prêmio noturno). Sem a linha do contrato, o cartão nem abre.
- **Ausência** = evento (com `Ausencia=SIM`, `TipoFalta`, `DescontarBeneficio`, `RemoverDiaria`, `BancoHoras`) lançado **por dia** (`diasponto.apontamentos`); regra `DiasAntesLancarAusencia = 3` («Data de Início menor do que o permitido»).
- **Fechamento** = período de referência `Aberto → (Calcular) Válido/Inválido → (Gerar Arquivo: Pontomatic, Domínio, TOTVS RM, Datamace, Sage, Protheus, GI, AlterData, Senior, RH3) → Fechado`; dias do período fechado ficam `bloqueado` no cartão; `ReaberturaColaborador`; `JustificarHoraExtra` (FATURADA / NÃO FATURADA / COBERTURA).
- **Integração de batimentos** = batidas que chegaram dos aparelhos (`ControleAcessoPontos`, tolerância 15 min) e **arquivo de relógio por aparelho** (`arquivosrelogioponto/upload` multipart, erros por CPF/PIS/RE).
- **Relógios**: Henry (URL/porta/login/último NSR) e Cronos (celular: IMEI, raio, vivacidade, exigir foto/localização/senha, bloquear fora da cerca, permitir em afastamento, facial). Carga de colaboradores/contratos para o aparelho. Senha do colaborador por tipo.
- **Achado que limitou a Fase A:** o motor `Digiexpress.CalculoPonto` responde `Base não encontrada` no trial — cartão clássico (302 → PaginaErro), banco de horas e Calcular do apontamento (fica **Inválido**) falham na própria UI. Cálculo de horas/extra/noturno e PDFs do cartão **não puderam ser vistos**.

## 3. O que foi feito

### Arquivos

| Arquivo | Papel |
|---|---|
| `backend/modules/people_management/ponto/fechamento.py` (novo) | `competencia_fechada(_sync)` — UMA pergunta para todo escritor de DP (lê `time_sheets` em fechado/aprovado/revisado/enviado_folha e `gp_monthly_closings.fechado`); `reabrir()` com motivo ≥ 5, recusa enviado_folha e recusa o que não estava fechado; DDL `ponto_reaberturas` |
| `backend/modules/people_management/ponto/integracao_batimentos.py` (novo) | parser dos leiautes 1510 (DDMMAAAA HHMM PIS) e 671 (ISO ±HHMM, CPF; hora convertida para Manaus), tipos 3 e 7; pessoa por CPF/PIS (11 dígitos); `chave_idempotente = afd:<origem>:<nsr>` + `ON CONFLICT DO NOTHING`; entrada/saída alternadas por pessoa-dia contando o que já existe no dia; mês fechado recusa; «só validar»; log `ponto_integracoes_batimentos` |
| `backend/modules/operacional/controllers/redesign_builders/_dgx_t2_ponto.py` (novo) | 4 telas + 2 ações; `telas(db, out)` anexa ao FIM de `g-ponto` |
| `.../redesign_builders/departamento_pessoal.py` | 2 + 1 linhas `# dgx t2` |
| `.../redesign_builders/_dp_grupos.py` | 4 abas no fim de `g-ponto` (documentação da composição) |
| `backend/modules/people_management/ponto/services/dashboard_service.py` | `registrar_ajuste`: trava antes do INSERT (diff mínimo) |
| `backend/modules/people_management/ponto/controllers/punch_controller.py` | `/ajuste`: `ValueError` → **409** (antes viraria 500) |
| `backend/modules/people_management/hr/services/time_record_service.py` | `create_manual`: trava antes do laço de INSERT |
| `backend/modules/people_management/hr/controllers/time_record_controller.py` | `POST /time-records`: `ValueError` → **409** com rollback |
| `backend/modules/people_management/hr/services/espelho_service.py` | `FONTES_MEDIDAS += ("relogio",)` — 0 linhas com esse `device_type` em 24/09: todo espelho já calculado é idêntico por construção (o oráculo afirma o 0 fora das fixtures) |
| `backend/scripts/orq/test_oraculo_integracao_batimentos.py` (novo) | oráculo a–g |

### DDL que `_ensure` aplica em produção no 1º acesso (idempotente)

```sql
CREATE TABLE IF NOT EXISTS ponto_reaberturas (
  id serial PRIMARY KEY, employee_id varchar(50) NOT NULL, mes integer NOT NULL, ano integer NOT NULL,
  motivo text NOT NULL, quem varchar(120), espelhos integer NOT NULL DEFAULT 0, fechamentos integer NOT NULL DEFAULT 0,
  status_anterior text, created_at timestamptz DEFAULT now());
CREATE INDEX IF NOT EXISTS ix_ponto_reaberturas_emp ON ponto_reaberturas (employee_id, ano, mes);
CREATE TABLE IF NOT EXISTS ponto_integracoes_batimentos (
  id serial PRIMARY KEY, origem varchar(80) NOT NULL, arquivo varchar(200), simulacao boolean NOT NULL DEFAULT false,
  linhas integer NOT NULL DEFAULT 0, marcacoes integer NOT NULL DEFAULT 0, importadas integer NOT NULL DEFAULT 0,
  duplicadas integer NOT NULL DEFAULT 0, sem_pessoa integer NOT NULL DEFAULT 0, mes_fechado integer NOT NULL DEFAULT 0,
  invalidas integer NOT NULL DEFAULT 0, erros jsonb, quem varchar(120), created_at timestamptz DEFAULT now());
```
Nenhuma semente. Nada é apagado nem alterado em dado existente. (No staging já aplicado pela rodada verde.)

### Telas (grupo `g-ponto` do DP, no fim) — deep-link `/redesign/departamento-pessoal?t=<id>`

| id | tipo | o que é |
|---|---|---|
| `integracao-batimentos` | table | histórico de importações (quando, origem, arquivo, modo, linhas/marcações, importadas, duplicadas, sem pessoa, mês fechado, inválidas, quem) + no subtítulo as batidas de relógio dos últimos 30 dias por origem |
| `integracao-batimentos-importar` | form **multipart** | origem, modo (Importar / Só validar), arquivo AFD (`type: file`) → `POST /action/integracao-batimentos-importar`; `showResult` com o resumo e a lista de erros (NSR + motivo) |
| `ponto-reaberturas` | table | histórico de reaberturas (quem, motivo, o que reabriu, status anterior) + no subtítulo «fechados hoje» por competência (espelhos + fechamentos mensais) |
| `ponto-reabrir-mes` | form | colaborador (só quem tem mês fechado — 51 opções no staging), mês, ano, motivo → `POST /action/ponto-reabrir-mes`; `confirm` avisa que invalida homologação/assinatura |

Ações gated `module:dp` (admin passa), mesmo `_require_dp` da F7.

### Medido por HTTP no `teste-dgx-t2` (8222)

```
GET data/departamento-pessoal 200 em 2.9 s — g-ponto tabs: [..., 'ausencias-dashboard',
  'integracao-batimentos', 'integracao-batimentos-importar', 'ponto-reaberturas', 'ponto-reabrir-mes']
importar sem origem → 400 "Informe a origem…"
importar simular (3 marcações 671 de ADAILSON, 11/2019) → "SIMULAÇÃO — nada gravado: 3 importada(s)…"; 0 linhas gravadas
importar grava → 3 importadas; gp_clock_punches: entrada 04/11 07:02 · saida 04/11 19:05 · entrada 06/11 07:00, device_type=relogio, device_id=FIXTURE-HTTP-T2
importar de novo → 0 importadas, 3 duplicadas (idempotente)
reabrir sem pessoa → 400 · motivo curto → 400 · nada fechado → 400 "não estava fechada — nada a reabrir"
POST /ponto/ajuste em 06/2026 (pessoa fechada) → 409 "Competência 06/2026 está FECHADA (fechamento mensal por sistema em 15/07/2026)…"
POST /hr/time-records em 06/2026 → 409 (mesma mensagem)
tela integracao-batimentos: 3 linhas após o teste
checar_tela_sem_porta (QA_API=8222): TOTAL 16 sem porta — nenhum dos 4 ids nem das 2 ações do T2 (os 16 são anteriores: mapa-ferias, rep-p-instrumento, marketing/*, grid-real-contratual, mapa-de-ponto, payable/receivable…)
```
Fixtures do teste HTTP apagadas por SQL (contagem 0 conferida).

## 4. Oráculo

`backend/scripts/orq/test_oraculo_integracao_batimentos.py` — (a) parser 671 e 1510 · (b) «só validar» não grava e conta igual · (c) 4 marcações de uma pessoa real em 12/2019 → 4 batidas, entrada/saída alternadas, `relogio`; CPF desconhecido → sem_pessoa; NSR repetido → duplicada; marcação em mês FECHADO de outra pessoa (06/2026) → mes_fechado, não grava · (d) reimportar = 0 · (e) `FONTES_MEDIDAS` contém `relogio` e há 0 batidas `relogio` fora das fixtures · (f) `competencia_fechada` responde/cala · (g) reabrir exige motivo, desfaz o fechamento mensal da fixture, registra, recusa o que não está fechado. Fixtures apagadas ao fim, mesmo em falha.

**Vermelho (código-base `/opt/conecta-pro/backend`, staging):**
```
File "/oraculo.py", line 60, in main
    from modules.people_management.ponto import fechamento
ImportError: cannot import name 'fechamento' from 'modules.people_management.ponto'
EXIT=1
```

**Verde (esta branch):**
```
pessoa: ADAILSON SERRA ALVES · fechado: 06/2026 · importadas 4 · reimportação 0 · reabertura #2
TOTAL desvios: 0
OK integração de batimentos: parser 1510/671, idempotente, mês fechado trava, reabrir é ato com motivo
EXIT=0
```
(A primeira rodada verde acusou 1 desvio real — PIS com 12 posições no arquivo × 11 dígitos no cadastro — corrigido normalizando para os 11 últimos, como já era feito no CPF.)

**Oráculos anteriores, mesma branch:** `test_oraculo_ponto_configuravel` → `TOTAL desvios: 0 · EXIT=0`; `test_oraculo_mapa_de_ponto_5_estados` → `EXIT=0`; `test_oraculo_espelho_falta` → `PASS · EXIT=0` (o único diff no espelho é a tupla `FONTES_MEDIDAS`).

## 5. O que NÃO foi feito, e por quê

- **Batida do app (`/batida`, `/batida/me`, offline) em mês fechado**: não passa pela trava. O mês fecha depois que acaba; a batida do app é de hoje. Pôr a trava ali é caminho ao vivo do colaborador (Hermes/triagem) e pede oráculo próprio — decisão do dono (§7).
- **Justificativa (`/justificativa`) em mês fechado**: idem — hoje justificar não grava batida, só `gp_justifications`; o espelho fechado não relê. Ficou de fora para não mudar o fluxo de aprovação.
- **Motivo do ajuste**: `registrar_ajuste` continua guardando o motivo só no log (não há coluna). Achado, não corrigido — é dívida anterior.
- **Mapa evento→rubrica e tipo de cálculo no espelho** (a configuração de ponto da DGX): é a decisão nº 1 do plano e é folha — paralelo cego obrigatório; G.
- **Diário de ocorrências próprio** (dias com batida faltante do mês sem passar pelo espelho): o espelho já aponta em `pending_issues` e o `fechamento-ponto` lista; M, baixo valor.
- **Justificar hora extra faturada / não faturada / cobertura**: é dinheiro do cliente; onde vive (contrato? espelho?) é decisão do dono.
- **Exportação por leiaute (Domínio/TOTVS/Sage…)**: não se aplica — a folha é interna e já exporta Domínio.
- **Carga de colaboradores para relógio, zerar banco de horas, relógio Henry/Cronos como cadastro**: não há relógio físico; o app já é o relógio.
- **Batidas da DGX (`ControleAcessoPontos`) via API do aparelho**: sem aparelho no trial, não exercitado.
- `ruff format` nos 7 arquivos pré-existentes editados: não aplicado (mesma razão da F7: `_dp_grupos.py` é lido por regex de linha; os 3 achados do `ruff check` são anteriores — imports não usados em `time_record_controller` e `N814` no espelho). `ruff` e `bandit -ll` limpos nos 4 arquivos novos.
- **No DGX**: turnos 2 e 3 e modelo 2 ficaram («em uso, não é permitida a exclusão» — turno aprovado não se apaga); turno 1 e modelo 1 ficam de propósito (a vaga 1 do contrato de outro agente aponta para o turno 1); o colaborador é compartilhado. Ausência, configuração de ponto, relógios, apontamento e eventos 9900–9905 foram apagados.
- `checar_regressao.py`: não editado (proibido). Sugestão de trava: `test_oraculo_integracao_batimentos.py` ao lado do `ponto_configuravel`.

## 6. Como o Jordan testa amanhã

1. DP → **Ponto & Jornada** → aba **Meses fechados / reaberturas**: subtítulo diz «06/2026 = 0 espelho(s) + 50 fechamento(s) mensal; 07/2026 = 1 espelho»; tabela vazia (nenhuma reabertura ainda).
2. Aba **Ajustar batida**: escolher alguém, data **10/06/2026**, qualquer hora, motivo → Ajustar → a tela mostra «Competência 06/2026 está FECHADA (fechamento mensal por sistema em 15/07/2026)…». Mesmo em **Lançamento manual** com `record_date` 2026-06-10.
3. Aba **Reabrir mês**: a mesma pessoa, 06/2026, motivo «teste do Jordan» → confirmar → «reaberta (#1): 0 espelho(s) e 1 fechamento(s) mensal». Voltar ao passo 2: agora grava. Aba **Meses fechados / reaberturas**: a linha com o motivo. Fechar de novo por **Fechar mês (ponto)**.
4. Aba **Importar arquivo do relógio**: origem `TESTE-JORDAN`, modo **Só validar**, um AFD (o do REP-P serve: DP → **AFD — arquivo fiscal** → linhas tipo 7, ou exporte por `GET /hr/rep/afd/rep-p/arquivo`) → o resultado diz quantas marcações, quantas pessoas, quantas em mês fechado — **sem gravar**. Trocar para **Importar** → grava; importar o mesmo arquivo de novo → «0 importada(s), N duplicada(s)». Aba **Integração de batimentos**: duas linhas; subtítulo «Batidas de relógio nos últimos 30 dias: TESTE-JORDAN = N».
5. Operacional → **Mapa de ponto** do dia importado: as batidas de relógio contam como fonte medida (igual ao app).

## 7. Decisões que só o dono pode tomar

1. **Trava também na batida do app e na justificativa em mês fechado?** Hoje só DP (ajuste, lançamento manual, importação). Se sim, mesmo `competencia_fechada` em `punch_service`/`offline_controller`/`/justificativa`, com oráculo da triagem.
2. **Quem reabre**: hoje `module:dp` (Eliziel/Orlailson) e admin, com motivo. Se for só o dono, trocar o gate — e decidir se reabrir deve avisar o colaborador (a homologação dele é invalidada).
3. **Origem do arquivo de relógio**: a chave de idempotência é `afd:<origem>:<NSR>`. Se um dia houver REP físico, a `origem` deve ser o número de série do aparelho (é o que a Portaria usa) — cadastrar em `rep_devices` e travar a origem ao serial.
4. **Reimportar o histórico do Tangerino por este caminho** (6.621 batidas `tangerino`, 1.375 jornadas duplicadas em 11/09): dá para exportar do Tangerino em AFD e importar com origem `TANGERINO` — mas os meses são fechados/homologados; exige reabrir e recalcular. Decisão de dono, não de agente.
5. **Motivo do ajuste como coluna** (`gp_clock_punches` não guarda; só o log): vale uma coluna `motivo`? É diff pequeno, mas mexe na tabela mais lida do sistema.
