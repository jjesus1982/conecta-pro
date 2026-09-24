# A noite de 23→24/09/2026 — o DGX dentro do Conecta PRO

**Pedido do Jordan, 23/09 à noite:** *"cria um plano geral para implementar tudo o que ele já tem e
funciona no conecta pro, todos os módulos, multi agentes, em várias frentes, loop autônomo, vou
dormir agora, amanhã de manhã eu vejo, você tem total autonomia."*

**Este documento é o que você lê primeiro.** Ordem: uma linha, o que mudou de arquitetura, o que
testar (10 minutos), o que só você decide, e depois o detalhe por frente.

Plano vivo: `docs/dgx/PLANO_IMPLEMENTACAO.md`. Contrato dos agentes: `docs/dgx/CONTRATO_AGENTE.md`.
Relatórios por frente: `auditoria/frentes/DGX_F1..F12_*.md` (cada um com §6 «como testar» e §7
«decisões do dono»).

---

## 1. Em uma linha

**12 frentes planejadas, 12 mescladas e no ar** (F1–F7, F10, F11 no bake 16 às 00:35; F8, F9, F12 no
bake seguinte, 01:05 — os dois sem drift). **13 oráculos novos rodados no container de produção,
todos verdes.** Tudo foi provado num container efêmero contra uma cópia de produção antes de subir, e a
árvore mesclada foi provada de novo antes do bake (35 módulos do redesign abertos, 0 falhas).

Três bugs achados de passagem e corrigidos: o webhook da Cora nunca conseguia marcar transação
como efetivada/cancelada; a ativação de candidato em 12x36 estourava em mês de 31 dias; o
validador de CPF da consulta à Receita reprovava CPF válido.

## 2. O que mudou de arquitetura (é isto que o DGX tinha e nós não)

| Antes | Agora |
|---|---|
| Rubrica = 8 colunas; a regra vive em `calculo_service.py` | **`rubricas_folha` com os atributos do DGX** (período, tipo de dia, crédito, soma ao evento, banco de horas, desconta benefício, exporta, DSR, 13º, razão, base…), 35 rubricas com `origem_regra`, Editar/Inativar na tela. Oráculo: bases INSS/FGTS/IRRF recompostas pelas flags = holerite, Σ\|Δ\| R$ 0,00 em 51 holerites |
| CCT = constantes Python | **Sindicato → 51 funções → 459 eventos → 408 benefícios → municípios**, como dado, no menu «Sindicato & CCT» do DP. Conformidade CCT aponta função sem evento e ativo sem função |
| VT/VR = conta manual | **`beneficio_tipos` carrega a regra** (7 tipos de desconto, limite de faltas, remover férias/afastados, integração com ponto). O motor de benefício da frente 03 LÊ a tabela — paralelo cego, 208 linhas iguais ao motor anterior |
| Parâmetro = constante no código | **`system_configs` por CNPJ** (40 chaves em 8 grupos, valor global + Eletrônica + Patrimonial), tela Configurações → Parâmetros com histórico. Adiantamento 40% e tolerância de ponto já lidos do banco |
| Alocação sem motivo | **Movimentação com tipo, motivo (7 do DGX), origem, coberto, solicitante**; alocar por cima encerra a anterior em D−1 |
| Tolerância/raio de ponto chumbados | **Cascata colaborador > escala > função > posto > condomínio > empresa**; feriado com escopo (nacional/estadual/municipal/**cliente**) lido por uma função só no espelho e na precificação |

Mais: dependentes na fonte que a folha lê, vales, eventos coletivos, crachás em lote (PDF),
demissão em lote (rascunhos), relógios/aparelhos, cartão de ponto em lote (48 espelhos num PDF),
dashboard de ausências, frota completa (saída/retorno, multas com condutor sugerido, trocas,
locações, requisições), condições de pagamento gerando parcelas, contas fixas gerando título,
códigos de serviço/CFOP, recibos numerados, fechamento de comissões, orçado × realizado,
pensionistas.

## 3. O que testar amanhã (10 minutos)

| Tela | Onde | O que você deve ver |
|---|---|---|
| **Sindicato & CCT** | `/redesign/departamento-pessoal?t=g-cct` | 51 funções, botão Eventos/Benefícios por função; Conformidade CCT com «5 ativos sem função da CCT» |
| **Rubricas** | `…departamento-pessoal?t=folha-rubricas` | 35 rubricas, coluna «Uso 09/2026», Editar/Inativar; 4 linhas amarelas = colisão de código (§4.2) |
| **Tipos de benefício** | `…departamento-pessoal?t=beneficio-tipos` | VT «% sobre salário · 4% · rubrica 1010»; mude o limite de faltas do VR para 0 e recalcule: linhas «cortado faltas» sem mexer na folha |
| **Parâmetros do sistema** | `/redesign/configuracoes?t=parametros` | 40 parâmetros, `folha.adiantamento_percentual` = 40; Editar por empresa |
| **Movimentações** | `/redesign/operacional?t=movimentacoes` | 73 linhas com motivo «Alocação de vaga» (retroativas); Nova movimentação encerra a anterior |
| **Configurações de ponto / Feriados** | `…departamento-pessoal?t=ponto-configuracoes` · `?t=feriados` | «Empresa · 15/15/150»; 16 feriados com escopo |
| **Cartão de ponto em lote** | `…departamento-pessoal?t=cartao-ponto-lote` | 08/2026 → PDF com 48 espelhos |
| **Dependentes / Vales / Crachás** | `…departamento-pessoal?t=dependentes` · `?t=vales` · `?t=crachas-lote` | dependentes contando salário-família; vale entra na prévia da folha; crachás 8 por folha (sem foto — ninguém tem) |
| **Frota** | `/redesign/equipamentos?t=frota-saidas` | saída única por veículo, retorno com KM, multa sugere o condutor |
| **Coberturas / Livro do posto / Checklist / Chamados** | `/redesign/operacional?t=coberturas` · `?t=livro-ocorrencias` · `?t=checklist-executar` · `?t=chamados` | cobertura em folga detectada nos turnos; livro do dia em PDF timbrado; checklist com item reprovado gera ocorrência; chamado urgente com SLA 1h em vermelho |
| **Suprimentos** | `/redesign/suprimentos?t=estoque` · `?t=nf-entrada` | 147 materiais com os 6 status; 84 NF-e da SEFAZ com «Conferir recebimento» |
| **Exames por função / Atendimentos / Fontes pagadoras** | `/redesign/saude-ocupacional?t=exames-por-funcao` · `/redesign/crm?t=atendimentos` · `?t=fontes-pagadoras` | 57 de 63 ativos sem ASO válido, por função; 9 atendimentos (4 ouvidoria + 5 portal) com SLA; quem paga ≠ quem contrata |
| **Condições / Contas fixas / Recibos** | `/redesign/financeiro?t=condicoes-pagamento` · `?t=contas-fixas` · `?t=recibos` | 30/60 gera 2 parcelas; gerar mês duas vezes cria uma só; recibo 00001 em PDF |

## 4. O que só você decide — os números estão nos §7 de cada relatório

**Dinheiro/folha (F1, F2, F3):**
1. **Faltas não reduzem a base do INSS no motor** (09/2026: R$ 4.593,86 em 19 pessoas → INSS e
   FGTS a maior, FGTS R$ 367,51). Corrigir é mexer no motor; o cadastro hoje diz a verdade do motor.
2. **Colisão de códigos de rubrica** (chave do eSocial): 0040, 0050/0051, 0060/0061, 0070 e o 1002
   usado para IRRF e INSS Férias. Renumerar no motor ou renomear na tabela — qualquer um mexe no
   caminho do dinheiro.
3. **Insalubridade 10% paga a 11 pessoas** (Serviços Gerais, Artífice, Jardineiro) e **ronda 15% a
   15 agentes de portaria** sem cargo insalubre/ronda na CCT — laudo por posto? Marcar obrigatório
   na função? Parar? Lista nominal em `DGX_F2 §7`.
4. **5 ativos sem função da CCT** (ALAN, ALEXANDRE, KELLY, NAILSON, THIAGO): preencher o cargo.
5. **SINETRAM: 27 × R$ 10 ou 30 × R$ 9?** A linha carrega R$ 10/dia «confirmar com a Pyetra».
6. **Quando a tabela vira fonte da folha** (rubricas, CCT, benefício): sugestão — 2 competências
   com oráculo verde.

**Ponto/operação (F5, F7):**
7. **Unificar `allocations` (89) com `employee_alocacoes` (73)** — duas verdades; a `posto_id` é a ponte.
8. **3 pessoas com alocação ativa que não deviam** (1 demitido, 1 afastado INSS, 1 suspenso).
9. **Ligar os 5 campos guardados de ponto** (fora do raio, facial obrigatória, arredondamento,
   intervalo mínimo, tolerância de saída) aos motores — cada um pede paralelo cego.

**Cadastro (F4, F6, F10, F11):**
10. **16 parâmetros sem valor** (nenhum código lê ainda) — preencher ou deixar.
11. **33 dependentes do backfill Portte sem nome/data** pagam salário-família «sem prova».
12. **Foto de funcionário**: 0 de 63 têm — sem upload, crachá sai com moldura vazia.
13. **CNH dos supervisores**: 0 cadastradas — sem isso a lista de motoristas é todo mundo.
14. **Multa em folha**: parcela única ou parcelada (art. 462 CLT — confirmar com o contador).
15. **As 15 comissões «auto — proposta»** (R$ 5.110,62) são reais ou lixo de teste?
16. **`ItemListaServico` 17.19 fixo no emissor de Manaus vs 11.02 nas notas gravadas** — qual?

**Operação, suprimentos, SESMT (F8, F9, F12):**
17. **Folga trabalhada vira HE ou folga compensatória?** O resumo por pessoa/mês já existe; a folha não lê.
18. **21 colaboradores com 2 logins** em `users` — o «não lidos» do app é por usuário; qual vale?
19. **32 NF-e só em resumo** (R$ 13,4 mil): manifestar ciência para baixar o XML e entrar no estoque?
20. **Mínimo/máximo dos 147 materiais**: todos «Mínimo não informado» — quem preenche.
21. **Unificar fornecedores** (`suppliers` 60 × `financial_fornecedores` 12) e **aposentar `fin_stock_*`/`inventory_items`** (semente sem escritor).
22. **Apagar a família morta `health_asos`/`health_medical_exams`** (só `gp_asos` vive) — rito de apagar pacote.
23. **Códigos Tab. 27 em branco** (espirometria, RX, ECG, EEG) — confirmar com a MBS antes do S-2220.
24. **NFS-e apontar para a fonte pagadora** (tomador = administradora): muda XML e retenção — não feito.
25. **As 4 manifestações de ouvidoria de 07/2026** são texto de teste, abertas há 2 meses — responder ou expurgar?

## 5. O que o sistema passou a vigiar sozinho (13 oráculos novos + 1 caçador)

`rubricas_dizem_a_verdade` · `cct_como_dado` · `beneficio_regra_e_dado` · `parametros_por_cnpj` ·
`movimentacao_com_motivo` · `dp_complementos` · `ponto_configuravel` · `frota_operacional` ·
`financeiro_cadastros` · `operacional_dgx` · `suprimentos_cadeia` · `sesmt_demandas_comercial` · `validar_cpf` (+ os das frentes de 13/09 que continuam verdes: grid × triagem,
mapa 5 estados, benefício fecha, vistoria par). Caçador novo **`checar_parametro_ambiguo`** (trava 76):
o padrão `SET x = :p … CASE WHEN :p` que derrubou o lote Inter e o webhook da Cora não volta calado.
Todos entram na varredura da meia-noite por descoberta automática.

## 6. Estado final das frentes

| # | Frente | Estado | Relatório |
|---|---|---|---|
| F1 | Rubricas como dado | ✅ no ar (bake 16) | `DGX_F1_eventos_rubricas.md` |
| F2 | CCT como dado | ✅ no ar | `DGX_F2_cct_como_dado.md` |
| F3 | Tipos de benefício com regra | ✅ no ar | `DGX_F3_tipos_beneficio.md` |
| F4 | Parâmetros por CNPJ | ✅ no ar | `DGX_F4_parametros_cnpj.md` |
| F5 | Movimentações | ✅ no ar | `DGX_F5_movimentacoes.md` |
| F6 | DP complementos | ✅ no ar | `DGX_F6_dp_complementos.md` |
| F7 | Ponto configurável | ✅ no ar | `DGX_F7_ponto.md` |
| F8 | Operacional (coberturas, livro, checklist, chamados, avisos) | ✅ no ar | `DGX_F8_operacional.md` |
| F9 | Suprimentos (compras, estoque, fornecedores, rádios/rastreadores) | ✅ no ar | `DGX_F9_suprimentos.md` |
| F10 | Frotas | ✅ no ar | `DGX_F10_frotas.md` |
| F11 | Financeiro/Faturamento | ✅ no ar | `DGX_F11_financeiro.md` |
| F12 | SESMT + Demandas + Comercial | ✅ no ar | `DGX_F12_sesmt_demandas_comercial.md` |


## 7. O que NÃO foi feito, de propósito

- **Nenhum valor de folha mudou.** Tudo que toca dinheiro é paralelo cego: cadastro descreve, motor
  continua o mesmo, oráculo prova a igualdade. Ligar o motor ao cadastro é decisão sua (item 6).
- **Nenhum dado de produção foi corrigido** (cadastro sem CCT, alocações indevidas, dependentes sem
  nome, comissões suspeitas): aparecem nas telas; quem decide é gente.
- **Nada de Telegram.** Nenhum `alembic/versions/`, `docker-compose`, `.env`, `main_production.py`.
- **Frontend intocado**: as telas usam a DSL genérica (table/form/panels) e as portas vieram por
  `EXTRA_MENU`/grupos no backend — nenhum deploy de frontend foi necessário.
- **Dívida conhecida que continua:** 15 telas sem porta no menu (pré-existentes, lista em
  `checar_tela_sem_porta`); `payable`/`receivable` antigos ficaram sem tela porque a F11 trocou os
  forms para a versão com condição de pagamento (as rotas seguem vivas para API).

## 8. Como a noite foi conduzida (para a próxima)

12 agentes em worktrees isoladas, cada um testando num container efêmero contra o sandbox
(recopiado de produção às 23:40), commits por pathspec na própria branch, merge só pelo
orquestrador com compilação + ruff + trava de porta + oráculo da frente + oráculos vizinhos,
árvore mesclada provada antes do bake, dois bakes (o segundo saiu pelo deploy de outra sessão que pegou o disco já mesclado — o lock serializou, como deve). Os conflitos de merge foram sempre os mesmos
dois arquivos de plug (`departamento_pessoal.py`, `_dp_grupos.py`) e triviais (ambos os lados
somam). O que custou tempo: o container efêmero morrendo no boot por `/app/logs` (3 vezes) — está
no contrato agora.

---

# Rodada 2 (24/09, manhã) — o DGX testado por dentro, botão a botão

**Pergunta do Jordan:** *"tem alguma coisa a mais no DGX que não tem no nosso? testou todas as telas? botões? funções? recursos?"* Resposta honesta de manhã: não, eu tinha lido o DGX, não exercitado. Então: *"pode começar, testa tudo e implementa o que faltar."*

## 9. Como foi feito

Cinco agentes, cada um com navegador próprio no trial do DGX (`scripts/dgx/dgx_client.py`), criaram dado de teste `TESTE CP` lá (colaborador compartilhado **TESTE CP COLABORADOR 01**, RE TCP01, fica no trial), percorreram cada tela e fluxo do seu grupo registrando o que cada botão FAZ, compararam cavando o nosso código, commitaram a lista de lacunas **antes** de implementar, e implementaram o que vale (alto/médio valor, esforço P/M). Listas: `docs/dgx/lacunas/*.md`. Relatórios: `auditoria/frentes/DGX_T1..T5_*.md`.

**Limite do trial:** o motor de cálculo de ponto do DGX (`Digiexpress.CalculoPonto`) não está provisionado — cartão de ponto, banco de horas e «Calcular» falham na própria tela deles. Os apps de celular não puderam ser instalados.

## 10. O que a passagem achou e o que entrou (bake 18)

| Grupo | Recursos vistos | Já tínhamos | Implementado agora | Fica (G / baixo / não se aplica) |
|---|---|---|---|---|
| DP/RH | 24 | 10 (ontem) | **foto do colaborador** (individual + ZIP em lote; crachá sai com foto), ficha em 15 seções, certificados por vencimento, turnover, atributos do cargo (CBO, exige CNH/CNV/porte), termo disciplinar PDF, férias travadas por afastamento aberto + registrar retorno | recibo/conta de férias, entrega com apuração configurável, suspensão descontando na folha |
| Ponto | 14 | maioria | **integração de batimentos** (arquivo AFD 1510/671 → batidas com chave idempotente, «só validar»), **fechamento de competência como trava única** (ajuste/lançamento em mês fechado → 409; reabrir com motivo e trilha) | cartão/banco de horas do DGX não puderam ser vistos |
| Operacional + Comercial | 20 | 2 | **vagas do contrato** como entidade (função × escala × turno × qtd × salário), custo por vaga, **restrições do cliente** que recusam movimentação, **Cobrir/Alocar por linha no grid**, grid e mapa de ponto com aba, painel de alertas (393 vivos em 20 regras), Visualizado/Finalizar no livro, copiar contrato, visitas por cliente | movimentação em 2 passos, supervisão planejada com frequência |
| Faturamento + Financeiro | 24 | 11 | cobrança por e-mail lendo os parâmetros, **importar OFX** (o parser existia sem rota), agenda de caixa por dia, comissão fechada vira conta a pagar, recebível proporcional (cego) | CNAB (temos API do Inter, melhor), calendário visual |
| Suprimentos/Frotas/SESMT/Config | 16 | 7 | **log do sistema** como tela, solicitação de material (posto pede, almoxarifado atende, baixa estoque), exames do ASO com validade, **acessos temporários** (papel + expiração, expiram e revogam sozinhos, nunca Financeiro) | permissão por tela/ação (G) |

Oráculos novos: `dgx_t1_dp` · `integracao_batimentos` · `t3_operacional_comercial` · `t4_faturamento_financeiro` · `t5_log_materiais_exames_acessos` · `mailer_sandbox`. Trava de porta: 17 → 15 (grid e mapa de ponto ganharam aba).

## 11. INCIDENTE — um e-mail real saiu do sandbox

O teste HTTP da ação de cobrança por e-mail (T4), rodando no container efêmero com banco de staging mas o `.env` de **produção**, enviou de verdade **um** lembrete de cobrança para `presidencia@chacaramaiapolis.com.br` (fatura R$ 23.160,00 vencida em 09/09). A ação em si está certa (só dispara por clique humano); o erro foi o ambiente de teste herdar o SMTP real.

Feito na hora: a receita do container efêmero zera `SMTP_HOST/USERNAME/PASSWORD` (cobre os 7 remetentes do backend) e `core/mailer.py` recusa destinatário fora de `@conectamais.pro` quando o banco é staging/sandbox, com oráculo. **Decisão sua:** avisar o cliente que o lembrete foi automático, ou deixar (a fatura está mesmo vencida).

## 12. Decisões novas que só você toma (além das 25 da noite)

26. **Suspensão desconta na folha?** (DGX liga a um evento). Dinheiro.
27. **15 desligados sem data de demissão** — o turnover fica cego a eles.
28. **Foto obrigatória na admissão?** Agora existe upload; entrar em «cadastro incompleto»?
29. **Trava de mês fechado também na batida do app e na justificativa?** Hoje só no DP.
30. **Reimportar o histórico do Tangerino** por AFD (6.621 batidas, meses já homologados).
31. **Mirante das Flores e Villa dos Pássaros têm 2 contratos vivos cada** — qual posto serve qual (senão calculado × faturado soma os dois).
32. **5 postos da Conecta Village apontam para contrato inexistente.**
33. **Salário base por vaga**: nenhum preenchido — «custo por contrato» mostra R$ 0.
34. **295 leads sem contato** afogam o painel de alertas; **19 de 29 clientes sem visita há 30+ dias**.
35. **Cobrança por e-mail automática** (beat) ou só por clique? Hoje clique, de propósito.
36. **Recebível proporcional por dias**: ligar (`fiscal.nfse_valor_proporcional_dias` = 30)?
37. **Acesso temporário com Financeiro** para o contador? Hoje proibido.
38. **Permissão por tela/ação** como o DGX (frente G) ou seguir por módulo.

---

# Onda 3 (24/09, tarde) — "prosiga em loop"

Cinco frentes escolhidas por valor sem depender das suas decisões. Relatórios `auditoria/frentes/DGX_U1..U5_*.md`.

## 13. O que entrou (bake 19)

| Frente | O que o DGX faz | O que passou a existir aqui |
|---|---|---|
| **U1** Movimentação em dois passos | movimentação nasce pendente e alguém aprova | pedido em `op_movimentacao_pedidos` (uma linha pendente NÃO vaza para a folha por condomínio — 4 leitores juntam alocação só por data); Aprovar chama o `alocar` de ontem, respeita restrições do cliente; pendentes na Central de Aprovações; DP/admin seguem alocando direto |
| **U1** Supervisão planejada | Q-Watcher: plano por posto com frequência, mapa realizado × planejado | planos por posto (diário/semanal/quinzenal/mensal), ocorrências geradas todo dia às 00:30 (idempotente), checklist ou check-in do gerente marca realizada; telas «Planos», «Mapa» (mês × posto), «Hoje» |
| **U2** Férias completas | aviso em lote, recibo, conta a pagar, cobertura | Aprovar com substituto cria a cobertura (F8) e a movimentação (F5) na hora — sem substituto avisa «posto X ficará descoberto de A a B»; recibo e aviso em PDF timbrado com o cálculo que já existia (Δ R$ 0,00); aviso em lote (1 página por pessoa) com fila de assinatura; conta a pagar idempotente, vencimento início−2 (art. 145), não paga; ficha de férias por pessoa; «postos descobertos» no mapa de férias |
| **U3** Porta para toda tela | — | 13 telas órfãs há semanas: 6 ganharam aba, 4 do marketing já tinham botão (o caçador não via `ctaTo`), 1 virou botão, 2 ações antigas removidas. Telas sem porta: **15 → 1** (a que sobra é `crm.json` alterado no disco por outra sessão, sem commit). Oráculo novo «toda tela tem porta» |
| **U4** Rondas do Vigilância | modelos com pontos, alertas, pânico | modelos de ronda com pontos ordenados e raio; alertas por tipo (atrasada, ponto pulado, fora de sequência, pânico, sem movimento) com destinatários; motor a cada 5 min, um disparo por alerta × ronda; **pânico** pela API com foto → disparo + ocorrência grave + aviso; setores por contrato; chamado avisa o setor ao abrir e o solicitante ao resolver |
| **U5** Entrega de benefício | lote com período de apuração | entrega como lote (referência, previsão, apuração manual ou por apontamento, acerto contra as duas anteriores), itens pessoa a pessoa, arquivo do operador, conta idempotente; apuração provisória enquanto o mês não fecha |

Oráculos novos: `u1_movimentacao_supervisao` · `u2_ferias_completas` · `toda_tela_tem_porta` · `u4_rondas_chamados` · `u5_entrega_beneficio`. Beats novos: supervisão planejada 00:30, alertas de ronda a cada 5 min.

## 14. Defeito real achado de passagem (onda 4 já cuida)

O motor de benefício da frente 03 conta **dois dias trabalhados** num plantão 12x36 **noturno com intervalo** (19→02 · 03→07): o segmento depois da meia-noite vira "outro dia". ADAILSON: 31 dias em 08/2026 para 15 plantões. Até a correção entrar, **não aprove entrega de benefício por apontamento de escala noturna** (a manual continua certa).

## 15. Decisões novas (só você)

39. **Quem aprova movimentação** — hoje `module:dp` e admin; supervisor e aprovador podem ser a mesma pessoa.
40. **Folga trabalhada em cobertura vira HE ou folga compensatória** (a folha não lê nada disso ainda).
41. **Persistir o cálculo das férias na aprovação** (hoje o recibo recalcula a cada abertura) e **recibo na fila de assinatura**.
42. **Conta de benefício por operadora ou por entrega**; vencimento = 1º dia da previsão?
43. **Pânico sem alerta configurado**: para quem vai? Hoje só para os destinatários do alerta do posto.
44. **`crm.json` alterado no disco sem commit** por outra sessão (tira `atividades` do menu): commitar ou restaurar do HEAD — decide quem mexeu.

---

# Onda 4 (24/09, tarde) — o resto das listas de lacunas

Cinco frentes, escolhidas do que sobrou em `docs/dgx/lacunas/*.md` com esforço pequeno/médio e sem depender de decisão sua. Relatórios `auditoria/frentes/DGX_V1..V5_*.md`. No ar no bake 20.

## 16. O defeito de cálculo que a onda 3 achou — corrigido (V1)

O motor de benefício contava **dois dias trabalhados** num plantão 12x36 noturno com intervalo: as batidas depois da meia-noite viravam "outro dia". ADAILSON aparecia com 31 dias em agosto para 15 plantões.

A régua agora vive num lugar só (`ponto/services/horas_service.py`): o dia de um plantão é a data em que ele começa, e todas as batidas da janela pertencem a ele.

| Medida | Antes | Depois |
|---|---|---|
| ADAILSON, dias trabalhados em 08/2026 | 31 | 15 |
| Σ das diferenças contra a referência, 08/2026 | 226 | 41 |
| Σ das diferenças contra a referência, 09/2026 | 142 | 10 |

O que resta de diferença **não é o motor**: é escala lançada no dia errado (RILEM está marcado nos ímpares e bate nos pares) e férias da Eidy. É dado, a operação corrige.

**Folha, holerite e pagamento não passam por esse caminho** — para as 64 pessoas-mês que não trabalham à noite a diferença é zero. Em produção só a competência 08/2026 tem conferência guardada, e ela não muda; setembro nascerá certo no primeiro cálculo. A trava que a onda 3 pediu ("não aprovar entrega de benefício por apontamento noturno") pode sair.

## 17. O que mais entrou

| Frente | O que passou a existir |
|---|---|
| **V2** | Vaga do contrato vira **vaga de recrutamento** com um clique (o banco garante uma aberta por posto) e o candidato aprovado já cai alocado naquele posto. **QR** por setor: etiqueta em PDF, página pública sem login, e o chamado aberto por ali avisa o responsável |
| **V3** | **Manutenção de veículo** como entidade: aprovar gera a troca tipada (óleo, pneu, correia), o título a pagar e o pedido de material. **Multa** vira conta e tem recurso — deferido cancela o título sem pagar nada. **Itens de vistoria** configuráveis: item que impede locomoção bloqueia a saída do veículo. Grupos de material em árvore |
| **V4** | **Fila de falhas de importação**: os quatro importadores do DP (planilha, Sólides, Portte, arquivo de relógio) param de perder o erro no meio do caminho — cada pendência fica com dono, resolver ou ignorar. **Exportar e imprimir** colaboradores com contadores por status. **Apontamentos por CSV**, em paralelo cego |
| **V5** | Códigos de serviço com os campos fiscais que faltavam (NBS, CST, PIS/COFINS, IBS/CBS) — **o XML da nota continua byte a byte igual**, é cadastro para quando você decidir ligar. Formas de pagamento (a tabela existia vazia; faltava a porta), limite por condição de pagamento, centros de custo em árvore, e **relatórios financeiros em PDF e Excel** com 11 agrupamentos |

## 18. Três defeitos que o verde escondia e a prova por HTTP pegou

- Uma consulta com lista de identificadores quebrava de verdade (erro 500) no caminho do relatório — o oráculo passava.
- O "só validar" da importação por CSV dizia que nada tinha sido gravado, e deixava pendência na fila.
- O oráculo de rondas **mandava e-mail real** na varredura da meia-noite, que roda dentro da produção. Você receberia um alerta falso toda noite. Duas paredes: quem testa não notifica, e domínio reservado nunca recebe.

## 19. Decisões novas (só você)

45. **Recalcular a conferência de benefício de 09/2026** quando quiser — vai baixar R$ 1.386,00 (eram dias contados a mais).
46. **A escala de quatro pessoas está lançada no dia errado** (RILEM, ADEILSON, DANIEL, MAURÍCIO): bate nos pares, escala nos ímpares.
47. **O gêmeo do defeito** vive no campo informativo do holerite (86 dias a mais em agosto). Corrigir toca o cálculo da folha — ficou fora de propósito.
48. **Quais itens de vistoria devem bloquear a saída** do veículo: hoje nenhum dos cinco.
49. **Multa em folha**: parcela única (hoje) e o que fazer quando o recurso é deferido depois do título pago.
50. **Ligar os campos fiscais na emissão da NFS-e** muda o que vai ao fisco — não fiz.
51. **CSV de apontamento deve lançar na folha ou só apontar?** Hoje aponta.
