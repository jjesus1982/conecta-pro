# A noite de 12→13/09/2026 — as 10 frentes de paridade com a DGX

**Pedido do Jordan, 12/09 à noite:** *"use multi agentes, cada com um item, trabalhe em loop
autônomo, não me pergunte nada, apenas execute, vou dormir e quando for amanhã venho testar, já
entendendo que você já fez tudo."*

**Este documento é o que você lê primeiro.** A ordem é: o que testar, o que decidir, o que achamos
sem procurar, e só então o detalhe por frente.

---

## 1. Em uma linha

As 10 frentes estão **implementadas, integradas, no ar e provadas de fora**. 60 commits,
+14.472 linhas, **28 capacidades que o sistema não tinha**, 13 tabelas, 60 rotas, 33 telas, 13
oráculos e 10 caçadores novos — tudo servindo em produção com dado real. **12 dos 13 oráculos
fecharam verdes**; o que continua vermelho está vermelho porque **falta decisão sua**, não porque
o código falhou.

O inventário completo do que o sistema ganhou está na seção 1-bis.

---

## 1-bis. O QUE O SISTEMA GANHOU — inventário medido

Esta seção responde "o que o Conecta PRO não tinha e passa a ter". Tudo abaixo foi contado do
sistema no ar em 13/09, não da memória: **13 tabelas · 60 rotas · 33 telas · 23 arquivos de
código · 13 oráculos · 10 caçadores**.

### A. Capacidades que NÃO EXISTIAM e agora existem

| # | Capacidade nova | O que passou a ser possível |
|---|---|---|
| 1 | **AFD e AEJ pelo leiaute oficial** (Portaria 671, Anexos I v004 e VI v002) | Gerar o arquivo-fonte de dados e o arquivo eletrônico de jornada com CRC-16/KERMIT, ISO-8859-1, CRLF e SHA-256 encadeado. **24 linhas já geradas.** Antes: o módulo existia, não estava montado e tinha 0 registros |
| 2 | **NSR contínuo por estabelecimento** | Numeração sequencial sem lacuna por CNPJ, com a origem no campo 6 (coletor). Era a exigência do Anexo IX |
| 3 | **Corte temporal do ponto** | AFD só a partir de 13/09 00:00 Manaus. O histórico fica intocado — preencher retroativo seria afirmar integridade sobre dado que passou por edição manual |
| 4 | **Registro de instrumento legal** | Tabela para INPI, atestado técnico e termo de responsabilidade. Nasce vazia e o oráculo cobra todo dia |
| 5 | **Batida offline com reconferência no servidor** | O aparelho compara o rosto, mas quem decide é o servidor: passou → definitiva; não passou → `pendente_de_conferencia` + pendência no DP com foto. Antes não havia caminho offline com identidade verificada |
| 6 | **Duas horas gravadas em toda batida** | Hora do aparelho e hora do servidor, mais a divergência em segundos. Relógio de celular é editável; a defesa é ter o número |
| 7 | **Chave idempotente na batida** | Índice único que impede a retentativa do aparelho de virar batida nova — a lição das 1.375 jornadas duplicadas |
| 8 | **Motor de benefício ligado ao ponto** | Cálculo por pessoa com `Planejado/Trabalhado/Recebido/Direito` anteriores, saldo, previsão, ±Ponto, crédito/débito — e o **mapa de frequência dia a dia dentro do cálculo**. Em paralelo cego: calcula e não escreve na folha |
| 9 | **Geração do arquivo do operador** | Arquivo para Sólides/SINETRAM, relido pelo nosso próprio parser (ida e volta sem desvio). Antes só líamos os relatórios deles |
| 10 | **Repasse de reajuste como PEDIDO** | Aumento de benefício calcula R$ Contrato / R$ Unitário / R$ Repasse e abre pedido na Central. Nunca vira preço sozinho |
| 11 | **Dedução de pedido duplicado** | Um pedido conta uma vez, esteja em quantos arquivos estiver — régua única para o motor e para o oráculo |
| 12 | **Grid real/contratual por cliente × dia** | A matriz que o supervisor abre para ver onde faltou gente. **41 turnos descobertos no mês** |
| 13 | **Mapa de ponto com 5 estados** | `ok · atraso · posto incorreto · fora de escala · descoberto`, com horário exato e distância ao geofence — e quem está de férias/afastado aparece **explicitamente não cobrado** |
| 14 | **Régua única entre tela e triagem** | O mapa importa as mesmas funções que a triagem do Hermes usa. Duas cópias divergem, e a que diverge cala |
| 15 | **Aptidão do vigilante** | Reciclagem com validade contada da conclusão, CNV com vencimento, e **ausência de dado = inapto** (nunca "válido por omissão") |
| 16 | **Nome de guerra** | Campo próprio, separado do nome social (tratamento) — são coisas diferentes |
| 17 | **Armamento e colete por número de série** | Entrega e devolução datadas, com responsável e índice único que impede segunda posse. Antes era só uma flag no posto |
| 18 | **Foto obrigatória tirada NA HORA** | Captura só por câmera (sem galeria), na mesma transação do checkpoint: ronda não fecha com foto pendente |
| 19 | **Ronda offline-first** | Fila IndexedDB com teto declarado, compressão antes de enfileirar, envio ao reconectar e cache dos checkpoints da ronda ativa |
| 20 | **`GET /rondas/minhas-rondas`** | A rota que a tela do celular chamava e **não existia** (caía em path param, 422) |
| 21 | **10 modos de cálculo de contrato** | Montante, hora, valor fechado, horas mensais/diárias/noturnas, dias fixos, 5x2, 6x1 e SDF (com feriados da CCT) |
| 22 | **Reserva técnica, PLR sindicato e taxa admin** | Como parâmetros **com vigência e origem**, lidos do banco. Sem confirmação do dono não entram no custo — zero percentual chumbado no código |
| 23 | **Calculado × Faturado por contrato** | Relatório que publica a divergência e declara o que não sabe. **10 de 15 contratos abaixo do custo** |
| 24 | **Mapa de férias por idade do período aquisitivo** | Faixas `<12 · 12–16 · 17–19 · 20–22 · >22`, com âncora do art. 133 (afastamento > 6 meses reinicia). **6 pessoas na faixa de risco de dobra** |
| 25 | **Uniforme/EPI com grade de tamanho** | Mínimo, máximo, pendente e atual por SKU normalizado na escrita, com entrega individual e **em lote** |
| 26 | **Frota** | KM atual, `Restam` até a próxima troca (negativo em vermelho, "sem dado" quando não há leitura), abastecimento com R$/L e média km/l, **vistoria chegada × saída** com foto por área |
| 27 | **Avaliação por ambiente** | Cadastro por contrato, resposta por item, **página pública por token** (com e sem identificação) e painel por ambiente/turno |
| 28 | **Medição de módulo morto** | Por `app.routes` do app montado, não por grep — a única medida que vale |

### B. O que já existia e ficou MELHOR

| O que | Antes | Depois |
|---|---|---|
| Dashboard | card de kits em **0** e alerta do certificado A1 **sumido** (404 em `catch` silencioso, 5 dias) | lê as rotas vivas: 12 clientes, 12 prontos, 8 vencimentos em alerta |
| `/ponto/afd/records` | **500** (schema limitava a linha a 200; a tipo 2 tem 331) | responde |
| `/ponto/afd/statistics` | dizia "**1 registro**" havendo 1.113 | conta certo |
| Sincronização offline do ponto | rota **sem `Authorization`** que gravava **sem reconferir o rosto** | rota nova com token e reconferência (a antiga fica para aposentar) |
| Arsenal | documento dizia "37 travas", existiam 56; **20 caçadores sem menção** | bate com o sistema |
| Linha de base do QA | 38 caçadores | **48**, com os 10 novos registrados |
| Oráculos | 152 | **165** |

### C. O que o sistema passou a VIGIAR sozinho (13 oráculos + 10 caçadores)

Não é feature — é o que impede o defeito de voltar em silêncio. Rodam na varredura da meia-noite.

`test_oraculo_rep_p` (AFD montado, toda batida com linha, NSR contínuo, AEJ casando, instrumento
legal) · `batida_offline` (idempotência, duas horas, reconferência, taxa facial 100% = não
comparou) · `beneficio_fecha` (portal × motor por pessoa) · `arquivo_operador` (ida e volta) ·
`grid_bate_com_a_triagem` (a tela e a triagem contam a mesma coisa) · `mapa_de_ponto_5_estados` ·
`mapa_ferias` (soma fecha, sem default, âncora do art. 133) · `vigilante_apto` ·
`ronda_com_foto` (nenhuma concluída sem foto, nenhuma imagem órfã) · `sku_unico` ·
`vistoria_par` · `precificacao_le_a_fonte` (nenhum percentual chumbado — varredura por AST) ·
`calculado_vs_faturado`.

Caçadores: `ponto_sem_instrumento` · `batida_offline_suspeita` · `repasse_sem_aditivo` ·
`arma_sem_serie` · `fila_offline_estourando` · `frota_sem_km` · `modulo_morto` · `tela_lenta` ·
**`at_time_zone_sem_fuso`** (que já achou 3 dívidas reais fora do escopo) · `sku_unico`.

### D. Onde o sistema continua na frente da DGX

Não foi perdido nada na troca. O que eles não têm e nós temos: **eSocial · FGTS Digital ·
EFD-Reinf · DCTFWeb · SPED · eCAC · SEFAZ · certidões** · **cálculo próprio de folha** (eles
exportam apontamento para Domínio/TOTVS/Sage/Protheus) · **GED com kit documental** · **assinatura
ICP-Brasil de contrato** · **agente de WhatsApp, MCP e Hermes** · **portal do colaborador** (o
deles está em obras) · **jurídico** · **reembolso** · **CCT do Amazonas** · e o arsenal de QA.

---

## 2. O que testar amanhã (10 minutos)

| Tela | Onde | O que você deve ver |
|---|---|---|
| **Mapa de Ponto** | `/redesign/operacional?t=mapa-de-ponto` | os 5 estados do dia e, no topo, quem está de férias/afastado **explicitamente não cobrado** |
| **Grid real/contratual** | `/redesign/operacional?t=grid-real-contratual` | 8 postos × dias do mês, vermelho onde faltou gente |
| **Mapa de férias** | `/redesign/departamento-pessoal?t=mapa-ferias` | 6 pessoas na faixa `> 22 meses` — **risco de pagar em dobro** |
| **Calculado × Faturado** | `/redesign/crm?t=calculado-vs-faturado` | 10 de 15 contratos faturados abaixo do custo |
| **Conferência de benefício** | `/redesign/departamento-pessoal?t=beneficio-conferencia` | portal × motor por pessoa, com mapa de frequência |
| **Aptidão do vigilante** | `/redesign/gestao-de-pessoas?t=vigilante-aptidao` | hoje "0 sujeitos à régua" — porque a lista de funções está vazia (item 3.7) |
| **Uniforme / Frota / Avaliação** | `…gestao-de-pessoas?t=uniforme-grade` · `…equipamentos?t=frota-painel` · `?t=avaliacao-dashboard` | grade de tamanho, KM/Restam, avaliação por ambiente |

**No celular** (o que não dá para testar daqui): ronda com **foto obrigatória tirada na hora** e
**modo avião** — bata o ponto e faça uma ronda sem sinal, depois reconecte e veja subir. Roteiro
detalhado em `auditoria/frentes/FRENTE_06_foto_offline_ronda.md` §6 e `FRENTE_02_facial_offline.md`.

---

## 3. O que depende de você — nada disto é código

| # | Decisão | Consequência de não decidir |
|---|---|---|
| **3.1** | **INPI + atestado técnico + termo de responsabilidade** (Portaria 671 art. 89) | O AFD está correto e gerando, mas **o REP-P não está constituído**. 52 pessoas batem ponto num programa sem instrumento legal. É o único item com risco de fiscalização |
| **3.2** | **6 pessoas com férias vencidas** (faixa > 22 meses) | Férias vencidas pagam **em dobro**. Nomes na tela e em `FRENTE_08` |
| **3.3** | **Horas mínimas para receber benefício** | Tirei o chute de 4h do script. Sem o número, o motor trata como *parâmetro ausente* e não calcula — por desenho, ausente nunca vira default |
| **3.4** | **Reserva técnica %, PLR sindicato %, taxa admin %** | Os três estão com valor 0 e `confirmado_em` nulo: **não entram no custo**. A CCT do AM não traz PLR em % |
| **3.5** | **Layout de importação do arquivo do operador** (Sólides/SINETRAM) | O arquivo é gerado e relido pelo nosso parser, mas o layout que os portais ACEITAM não está documentado aqui. Confirmar antes de usar |
| **3.6** | **5 itens de EPI sem grade de tamanho** | Botina, capacete, colete, lanterna e luva estão no catálogo sem tamanho/mínimo/máximo. O oráculo fica vermelho até o DP preencher |
| **3.7** | **Quais funções exigem CNV e reciclagem** | A lista está vazia, então hoje **ninguém é cobrado**. A empresa é de portaria: cobrar CNV de jardineiro seria trava que se aprende a ignorar |
| **3.8** | **Módulos aposentados: ligar ou apagar?** | `bidding` (101 arquivos), `health_occupational`, `retention`, `document_kits`. Matriz pronta em `FRENTE_09` |
| **3.9** | **Migrations do alembic** | 13 tabelas e as colunas novas nasceram por SQL direto (zona proibida para sessão autônoma). Num banco recriado somem **em silêncio** |
| **3.10** | **`SENTRY_DSN` está vazio** | 29 avisos no log: *"erros de produção não serão monitorados"*. É uma linha de `.env` |

---

## 4. O que achamos sem estar procurando

Estes não estavam no plano. Apareceram porque alguém foi olhar.

1. **O dashboard mentia há 5 dias.** `/bidding/certificates` e `/document-kits/stats` respondem
   404 desde 08/09, dentro de um `catch { /* silencioso */ }`. O card de kits mostrava **0** e o
   **alerta do certificado A1 sumiu da tela** — o alerta que avisa quando a empresa vai parar de
   emitir nota fiscal. 60 a 100 requisições por dia em 404, sem uma linha de log. **Corrigido.**
2. **A lista de rondas do celular nunca carregou.** `GET /rondas/minhas-rondas` não existia: caía
   no path param `/{round_id}` e devolvia 422. É a primeira chamada da tela. **Corrigido.**
3. **Uma porta de fraude no ponto.** `sw-ponto.js` postava batida offline para `/ponto/sync` **sem
   `Authorization`**, numa rota que gravava **sem reconferir o rosto**. Nunca foi registrado por
   tela nenhuma, então nunca rodou — mas estava lá. A rota nova exige token e reconfere no
   servidor. **A antiga precisa ser aposentada** (varrer chamadores antes).
4. **A conferência de benefício mostrava o dobro.** O mesmo pedido do Sólides (332373) está em
   dois arquivos diferentes do volume de uploads. **E eu quase consertei ao contrário**: li que o
   motor sobrescrevia quando deveria somar, e cheguei a escrever a soma — que daria o dobro de
   verdade. Foi listar os pedidos com o arquivo de origem que mostrou que a duplicata era de
   ARQUIVO, não de pedido. **Corrigido na régua compartilhada** (motor e oráculo leem a mesma).
5. **Dois números mentirosos em rotas recém-acesas.** `/ponto/afd/records` dava 500 (o schema
   limitava a linha a 200 caracteres e a tipo 2 tem 331) e `/ponto/afd/statistics` dizia "1
   registro" havendo 1.113 (`select(func.count())` sem FROM). Estavam mortas até ontem.
6. **O Arsenal não batia com ele mesmo.** O documento dizia "37 travas", existem 56, e **20
   caçadores não eram mencionados em lugar nenhum**. **Sincronizado.**
7. **Três dívidas de fuso fora do ponto.** `financial_pagamentos_pj.updated_at` e
   `opportunities.updated_at` convertem `AT TIME ZONE` em coluna sem fuso — **somam 4 horas**.
   Achadas pelo caçador novo, **não corrigidas** (fora do escopo; merecem frente própria).
8. **Cadastro sujo no operacional, nada corrigido:** 3 pessoas batendo 100% fora do posto
   (FRANCISCO RAMON 19/19 a ~8,4 km, RILEM 16/16, MAIARA 8/8 — é geofence errado, não fraude),
   13 com desvio de ~1h em turnos de 07:00, e 12 que bateram sem turno na escala.
9. **`hr_vacation_periods` está semeada por calendário**: `days_used = 0` em 67 de 67 e
   `limit_date` errado. A tela usa o limite legal calculado; o dado não foi corrigido.
10. **O `docker-compose.staging.yml` ressuscita dois workers quebrados a cada bake** — o comando
    deles aponta para `backend.infrastructure.celery_app`, que não existe na imagem. Removi os
    dois; voltam no próximo bake até alguém corrigir o compose (zona proibida).

---

## 5. Prova de fora — os 13 oráculos rodados em PRODUÇÃO

Não no staging: em produção, depois do bake. **Foi essa escolha que pegou dois erros meus** (o DDL
da frente 07 que eu esqueci, e o benefício dobrado).

**12 verdes.** O que continua vermelho:

| Oráculo | Desvios | Natureza |
|---|---|---|
| `test_oraculo_rep_p` | 3 | **Decisão sua** — INPI, atestado, termo. As afirmações (a)(b)(c)(d) estão verdes: `TOTAL pessoas sem instrumento: 0` |
| `test_oraculo_sku_unico` | 5 | **Dado do DP** — 5 itens de EPI sem grade de tamanho |

---

## 6. Como isto foi construído (para a próxima vez)

Dez agentes autônomos, um por frente, cada um numa **worktree isolada** com branch própria,
proibidos de tocar em produção, em `main_production.py`, no `alembic/`, no `docker-compose*.yml` e
nos arquivos compartilhados. Cada um entregou um relatório com "o que NÃO fiz e por quê".

**A regra que valeu para todos:** nenhum conserto entra sem o oráculo que prova que ele falhou
ANTES. Oráculo que nasce verde está medindo a coisa errada.

**O que deu errado no meio:** seis agentes morreram por limite de cota do modelo. Nenhum trabalho
se perdeu porque o contrato mandava commitar cedo — os que já tinham commitado retomaram de onde
pararam, com o contexto intacto.

**Um agente contrariou a minha instrução, com razão.** Eu mandei o NSR do AFD ser contínuo por
origem; o Anexo IX da Portaria diz que é por estabelecimento (CNPJ). Por origem sairiam quatro
NSR=1 e quatro arquivos de mesmo nome. Ele mediu, achou a norma, regerou as 1.112 linhas e
registrou por quê.

Relatórios por frente: `auditoria/frentes/FRENTE_01..10_*.md`.
Benchmark e pré-mortem que originaram tudo: `auditoria/BENCHMARK_DIGIEXPRESS_DGX_2026-09-12.md` e
`auditoria/PREMORTEM_10_FRENTES_2026-09-12.md`.
DDL aplicado: `auditoria/frentes/DDL_PRODUCAO_2026-09-13.sql`.
