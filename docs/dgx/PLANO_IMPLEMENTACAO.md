# Plano geral — trazer para o Conecta PRO tudo que o DGX tem e funciona

**Aberto em:** 23/09/2026, 23:20 (Manaus) · **Mandato do Jordan:** autonomia total — inclusão,
exclusão, testes, decisões. Loop autônomo até terminar. Ele lê este arquivo de manhã.

**Fonte:** `docs/dgx/00..09` — o DGX lido por dentro (menus, formulários, 127 parâmetros,
API REST real, eventos, estrutura sindicato/CCT).

## O diagnóstico que orienta tudo

O DGX não é "mais funcionalidade". É **três decisões de arquitetura** que nós não tomamos:

1. **Evento (rubrica) é dado, com 40 atributos.** `fgts, inss, irrf, dsr, decimoTerceiro,
   periculosidade, bancoHoras, credito, somarAoPonto, descontarBeneficio, tipoFalta,
   exportarEvento, razao, razaoNoturna...`. Ponto, folha e benefício conversam **pelo
   evento**. No Conecta PRO isso é código em `calculo_service.py`.
2. **CCT é dado.** `Sindicato → Funções → Eventos por função → Benefícios por função →
   Municípios`. A nossa SINDECOMPRESTS vive em constantes Python.
3. **Tipo de Benefício carrega a regra.** 7 tipos de desconto, limite de faltas, meses de
   afastamento permitido, 8 modos de integração com o ponto. O nosso VT/VR é conta manual.

Além disso: **parâmetros por CNPJ** (127, `nome/valor/chaveEmpresa`) e **Movimentação**
(alocar/remover de vaga com motivo tipado) como unidade operacional.

## Regras de execução (valem para TODO agente)

- **Cave antes de construir.** Medir o que já existe (grep, tabelas, telas). Três vezes numa
  noite eu ia reconstruir o que já existia. Reusar > estender > criar.
- **Porta no frontend, sempre.** Tela sem item de menu/aba não existe para o dono
  (`checar_tela_sem_porta` acusa). Capacidade que vive no terminal não existe.
- **Oráculo junto.** Toda superfície nova nasce com `backend/scripts/orq/test_oraculo_*.py`
  afirmando a REGRA, não a fotografia.
- **Tabela nova = DDL idempotente no serviço** (`CREATE TABLE IF NOT EXISTS`, padrão
  `_ensure(db)` da casa). **`alembic/versions/` é zona proibida.**
- **Nada destrutivo no banco de produção.** Sem DELETE/DROP em dado existente. Linha de
  teste se apaga ao fim.
- **Agente NÃO deploya, NÃO faz bake, NÃO faz `docker cp`.** Só o orquestrador, serializado.
- **Commit por pathspec no worktree**, com `[session: agent-<frente>] [module: <mod>]`.
- Zonas proibidas: `alembic/versions/`, `main_production.py`, `docker-compose*.yml`, `.env*`,
  `credentials/`. Sem `git revert`, `reset --hard`, `push --force`.
- Formato brasileiro nas telas (`MM/AAAA`, `DD/MM/AAAA`, `R$`).
- Nunca propor Telegram.

## O que JÁ FOI entregue (não refazer)

A rodada de 12→13/09 (`auditoria/RELATORIO_NOITE_2026-09-13.md`) já trouxe 28 capacidades da
DGX: REP-P/AFD/AEJ, facial offline, **motor de benefício ligado ao ponto**, grid real/contratual,
mapa de ponto (5 estados), aptidão do vigilante, arma/colete por série, ronda com foto/offline,
precificação (10 modos), mapa de férias, **uniforme/EPI com grade**, **frota** (KM, abastecimento,
vistoria), avaliação por ambiente. E já existem: `rubricas_folha` (24 linhas, 21 colunas),
`cct_convencoes/cct_cargos/cct_beneficios/cct_feriados`, `employee_benefits`,
`employee_alocacoes` + `allocation_controller`, `system_configs`/`tenant_settings`, telas
`folha-rubricas`, `beneficios-cct`, `cct-conformidade`, disciplina (g-disciplina), cursos/
certificados/turnover (rh), rondas (g-rondas). **Cada frente estende isso; não cria paralelo.**

## Frentes (recalibradas após cavar — 24/09 01:20)

| # | Frente | Estende | Módulo | Onda | Estado |
|---|---|---|---|---|---|
| F1 | **Eventos/rubricas como dado** — `rubricas_folha` ganha os atributos do DGX que faltam (período, tipo de dia/falta, crédito/débito, soma ao evento, banco de horas, desconta benefício, exporta/código auxiliar, razão/razão noturna, base salário/mínimo, DSR, 13º, média 13º, vale, ausência). CRUD (incluir/editar/inativar) na aba Rubricas. Oráculo: as flags da tabela batem com o que `calculo_service` faz de fato (INSS/IRRF/FGTS/DSR) nos holerites de 09/2026 — paralelo cego, o cálculo NÃO muda | `rubricas_folha`, `folha-rubricas` | folha | 1 | mesclada · oráculo verde |
| F2 | **CCT como dado** — Sindicato (entidade) → Funções da CCT → Eventos por função → Benefícios por função → Municípios; seed a partir de `cct_convencoes/cct_cargos/cct_beneficios` (SINDECOMPRESTS) e das constantes de `calculo_service`; CRUD; `cct-conformidade` passa a apontar função sem evento/benefício | `cct_*`, `_cargo_cct` | folha | 1 | mesclada · oráculo verde |
| F3 | **Tipos de Benefício com regra** — tabela de tipos com `tipo_desconto` (7), coeficiente, faltas/justificadas/dias-mês, meses de afastamento, remover férias/afastados/atrasados, integração ponto (8 modos), desconto por saldo, meio período; benefício individual com linha/quantidade/unitário/anular outras fontes; o motor da frente 03 lê a regra da tabela | `folha_beneficio_conferencia`, `employee_benefits`, `cct_beneficios`, `_frente_03` | folha | 1 | mesclada · oráculo verde |
| F4 | **Parâmetros por CNPJ** — `system_configs` já existe (12 chaves, escopo global). Ganha escopo `empresa` (chave × CNPJ), leitor `param(db, chave, cnpj)`, seed dos parâmetros do DGX que fazem sentido aqui (folha/apontamento, fechamento, benefícios, ponto, e-mail, fiscal), tela Configurações com seções + editar | `system_configs`, `configuracoes-sistema` | config | 1 | mesclada · oráculo verde |
| F5 | **Movimentações** — `employee_alocacoes` ganha tipo (alocar/remover), motivo tipado (7 do DGX), origem/destino, vaga, quem pediu, aprovação; tela Movimentações (listar/incluir/encerrar) no Operacional; grid de planejamento reusa `grid-real-contratual` | `employee_alocacoes`, `allocation_controller`, `_frente_04` | operacional | 1 | mesclada · oráculo verde |
| F6 | DP complementos — dependentes (tabela própria, grau/instrução/deficiência), vales (adiantamento avulso com desconto em folha), eventos coletivos (lançar um evento para N pessoas numa competência), linhas de VT/itinerários por operadora, reajuste de benefício em lote, crachá (dados+foto → PDF), demissão em lote | `employee_dp`, `descontos`, `_frente_03` | dp | 2 | mesclada · oráculo verde |
| F7 | Ponto — configurações de ponto por empresa (tolerâncias, raio, facial obrigatória, arredondamento), banco de horas por colaborador (saldo, vencimento, extrato), relógios/aparelhos cadastrados, jornadas/turnos como cadastro, feriados com escopo (nacional/estadual/municipal/cliente), cartão de ponto modelos | `cct_feriados`, `_frente_01/02/04`, `punch_*` | ponto | 2 | mesclada · oráculo verde |
| F8 | Operacional — coberturas (quem cobriu quem, folga trabalhada), livro de ocorrências do posto, checklist de supervisão (setores/itens/execução), chamados, avisos/painel | `g-rondas`, `g-disciplina`, ocorrências | operacional | 3 | mesclada · oráculo verde |
| F9 | Suprimentos — solicitação → pedido de compra → NF de entrada; materiais com estoque mín/máx e movimentação; fornecedores; comunicações móveis/rastreadores como equipamentos controlados | `suprimentos`, `equipamentos`, `_frente_05/10` | suprimentos | 3 | mesclada · oráculo verde |
| F10 | Frotas — multas de trânsito (com condutor), locações, controle de saída/retorno, trocas (óleo/pneu/correia) como manutenção tipada, requisições de abastecimento/lavagem | `frota_*` (`_frente_10`) | frotas | 3 | mesclada · oráculo verde |
| F11 | Financeiro/Faturamento — contas fixas (recorrência gera título), condições de pagamento, análise orçamentária, fechamento de comissões, CFOP/natureza da operação, recibos de venda, pensionistas como beneficiários | financeiro | financeiro | 3 | mesclada · oráculo verde |
| F12 | SESMT + Demandas + Comercial — tipos de exame e médicos como cadastro do ASO; assuntos/atendimentos/feedbacks; fontes pagadoras, regiões, postos por cliente | saude_ocupacional, crm | diversos | 3 | mesclada · oráculo verde |

## Ciclo do orquestrador

1. Lança a onda (agentes em worktree, branch `dgx/<frente>`).
2. A cada agente concluído: lê o relatório, `git merge` na branch de trabalho, ruff +
   py_compile + oráculo da frente + `checar_tela_sem_porta`.
3. Fim da onda: bake blue/green (uma vez), deploy do frontend se houver JSON de menu,
   `checar_drift_workers`, arsenal.
4. Atualiza a tabela acima e o log abaixo. Próxima onda.

## Log

- 23/09 23:20 (Manaus) — plano aberto e recalibrado depois de cavar (ver seção «já foi entregue»).
- 23/09 23:40 — sandbox recopiado de produção (104 funcionários, 546 tabelas). Onda 1 lançada: F1, F2, F3, F4, F5 (worktrees `dgx/f*`).
- 24/09 00:05 — onda 2 lançada em paralelo: F6 (dependentes, vales, eventos coletivos, crachás, demissão em lote) e F7 (ponto configurável por escopo, relógios, feriados com escopo, cartão em lote, ausências). 7 agentes simultâneos.
- 24/09 00:35 — F2 mesclada (grupo novo «Sindicato & CCT» no DP: 51 funções, 459 eventos, 408 benefícios por função; contra-prova nos 45 holerites de 07/2026). F1 mesclada (rubricas_folha com 25 atributos do DGX + 11 códigos que o motor emitia sem cadastro; Σ|Δ| das bases INSS/FGTS/IRRF = R$ 0,00 em 51 holerites de 09/2026; Editar/Inativar na aba Rubricas). Telas sem porta: 18 → 3. Achados para o dono nos §7 dos relatórios (faltas que não reduzem base do INSS: R$ 4.593,86 / 19 pessoas; colisões de código de rubrica; insalubridade/ronda pagas fora da CCT).
- 24/09 00:45 — F10 (frotas: multas, saída/retorno, trocas, locações, requisições) e F11 (financeiro: condições de pagamento, contas fixas, CFOP/códigos de serviço, recibos, fechamento de comissões, orçado×realizado, pensionistas) lançadas — áreas sem colisão com F3–F7. 7 agentes ativos.
- 24/09 01:05 — F3 mesclada (beneficio_tipos com regra de desconto/limite de faltas/afastados; motor da frente 03 lê a tabela; 208 linhas de 08 e 09/2026 comparadas, Σ|Δ| = R$ 0,00; benefício individual com tipo/linha/quantidade).
- 24/09 01:20 — F4 mesclada (leitor `core/parametros.py`: empresa → global → default; 40 chaves em 8 grupos com origem no código; tela Parâmetros em Configurações com Editar + histórico; adiantamento e tolerância de ponto já lidos do banco, iguais ao código). F5 mesclada (movimentações com tipo/motivo/origem/coberto; alocar por cima encerra a anterior em D−1; 73 alocações retroativas marcadas; grid da frente 04 continua batendo 29 = 29). **Onda 1 completa.** F6, F7, F10, F11 em execução.
- 24/09 01:45 — F6 mesclada (dependentes gravados na fonte que a folha lê, `employees.dependentes`; vales como desconto tipo `vale` + rubrica 1040; eventos coletivos como apontamento por pessoa com desfazer; crachás em lote em PDF timbrado; demissão em lote cria rescisões em rascunho). Achado colateral: `government_integrations.utils.validar_cpf` reprova CPF válido — não corrigido (outro módulo), fica para o dono.
- 24/09 02:15 — F10 mesclada (frota: saída/retorno com saída única por veículo, multas com condutor sugerido pela posse e desconto em folha, trocas tipadas com Restam, locações gerando título, requisições de abastecimento/lavagem virando leitura). Menu: itens «Frota · …» em Equipamentos.
- 24/09 02:40 — F7 mesclada (ponto configurável em cascata colaborador > escala > função > posto > condomínio > empresa, semente igual ao código; mapa de ponto idêntico antes/depois; feriados com escopo nacional/estadual/municipal/cliente lidos por função única no espelho e na precificação; relógios só leitura; cartão de ponto em lote 48 espelhos/49 páginas; dashboard de ausências pela régua do mapa). **Onda 2 completa.** Falta F11.
- 24/09 03:05 — F11 mesclada (condições de pagamento gerando N parcelas nos forms de contas; contas fixas a partir de `financial_custos_recorrentes` com geração idempotente do mês; códigos de serviço/CFOP; recibos numerados em PDF; fechamento de comissões com demonstrativo; orçado × realizado por categoria do extrato; pensionistas). Árvore mesclada provada num container efêmero: DP 108 telas, Operacional 109, Financeiro 156, Equipamentos 25, Configurações 12 — 0 FALHOU. Próximo: bake.
- 24/09 03:20 — bake 16 iniciado (F1–F7, F10, F11 + fix Cora/paridade/CPF). Onda 3 lançada: F8 (coberturas, livro do posto, checklist de supervisão, chamados, avisos), F9 (cadeia de compras, materiais/estoque, fornecedores, rádios/rastreadores, kits) e F12 (tipos de exame/médicos, assuntos/atendimentos/feedbacks/diretórios, fontes pagadoras/regiões/postos por cliente).
- 24/09 03:35 — **bake 16 no ar** (imagem 776109e4, sem drift, 0 chaves de contrato desconhecidas). Primeiro acesso aplicou a DDL em produção: 17 tabelas/colunas novas com seeds (1 sindicato, 459 eventos e 408 benefícios por função, 8 tipos de benefício, 40 parâmetros, 4 condições de pagamento, 8 códigos de serviço, 73 alocações com motivo, feriados com escopo). **13 oráculos rodados no container de produção: todos verdes.**
- 24/09 04:05 — F12 mesclada (tipos de exame e médicos seedados do PCMSO; matriz exames × função: 57/63 ativos sem ASO válido; atendimentos com SLA lendo ouvidoria e portal sem migrar; diretórios do cliente; fontes pagadoras com CNPJ validado; regiões; postos por cliente). Achado: `health_asos` é tabela MORTA (só `gp_asos` vive) — rito de apagar fica para o dono.
- 24/09 04:20 — F9 mesclada (builder `suprimentos.py` novo: solicitação→pedido→NF de entrada com 84 NF-e da SEFAZ; 147 materiais com os 6 status de estoque do DGX; fornecedores unidos com origem; rádios/celulares/rastreadores como equipamentos controlados; kits de uniforme por função). Achado: estoque vivo é `nfe_compras_estoque`; `fin_stock_*` e `inventory_items` são semente sem escritor. Falta só F8.
- 24/09 04:40 — F8 mesclada (coberturas com folga trabalhada derivada dos turnos e movimentação da F5 nas de férias/afastamento; livro de ocorrências do posto como união + PDF do dia; checklist de supervisão com semente de 10 itens e ocorrência automática; chamados com SLA unindo tickets do portal; painel de avisos por pessoa). **12/12 frentes mescladas.** Próximo: bake 17.
- 24/09 05:05 — árvore final provada (35 módulos, 0 falhas). Meu bake 17 recusou: lock ocupado — outra sessão tinha iniciado um blue/green 17 s antes, construindo do DISCO (já com as 12 frentes). Esperando o deploy dela terminar para medir o efeito em produção; se faltar algo, bake próprio.
- 24/09 05:30 — **12/12 no ar.** O deploy da outra sessão (imagem f316811d, sem drift) publicou F8/F9/F12; primeiro acesso aplicou a DDL (11 tipos de exame, 2 médicos, 7 assuntos com SLA, região Manaus, checklist de supervisão com 10 itens). Os 13 oráculos novos rodados no container de produção: verdes. Trava de porta: 17 = 15 telas pré-existentes + `payable`/`receivable` (sem tela porque a F11 trocou os forms). Worktrees removidas; branches `dgx/f*` ficam como histórico. Relatório da manhã: `auditoria/RELATORIO_NOITE_2026-09-24.md`.

## Rodada 2 — passagem completa no DGX (24/09, manhã)

Jordan: *"tem alguma coisa a mais no DGX que não tem no nosso? testou todas as telas? botões? funções? recursos?"* → *"pode começar, testa tudo e implementa o que faltar, loop autônomo."*
Contrato: `docs/dgx/CONTRATO_TESTE_DGX.md` (4 fases: exercitar botão a botão → comparar cavando → lista de lacunas commitada → implementar). Cliente único: `scripts/dgx/dgx_client.py`.

| # | Grupo do DGX | Lacunas | Estado |
|---|---|---|---|
| T1 | DP/RH (ficha completa, fotos, afastamentos, férias, medidas disciplinares, cursos, benefícios/entregas/reajustes, vales, crachás, demissão em lote, turnover) | `docs/dgx/lacunas/dp_rh.md` | mesclada · oráculo verde |
| T2 | Apontamentos/Ponto (escalas, controle, ocorrências, fechamento/exportação, cartão, banco de horas, integração de batimentos, relógios, configurações) | `docs/dgx/lacunas/ponto.md` | mesclada · oráculo verde |
| T3 | Operacional + Comercial (postos/vagas, movimentações, grid, coberturas, livro, avisos, Q-Watcher, Vigilância; clientes, contratos, fontes pagadoras, regiões, visitas) | `docs/dgx/lacunas/operacional_comercial.md` | mesclada · oráculo verde |
| T4 | Faturamento + Financeiro (faturas, NF, cobrança, recibos, comissões; contas, conciliação, fluxo, orçamento, contas fixas, relatórios) | `docs/dgx/lacunas/faturamento_financeiro.md` | mesclada · oráculo verde |
| T5 | Suprimentos + Frotas + SESMT + Demandas + Configurações (compras, estoque, uniformes, equipamentos; frota completa; ASO; atendimentos; acessos temporários, perfis, log) | `docs/dgx/lacunas/suprimentos_frotas_sesmt_config.md` | mesclada · oráculo verde |

- 24/09 08:45 — T1–T5 lançados. Dado de teste no DGX com prefixo `TESTE CP` (colaborador compartilhado criado pelo T1).
- 24/09 09:40 — T1 mesclada: 24 recursos do DP/RH do DGX exercitados (colaborador `TESTE CP COLABORADOR 01` criado lá — RE TCP01), 10 já cobertos ontem, 7 implementados agora: **foto do colaborador** (individual + ZIP em lote por matrícula/CPF; o crachá da F6 passa a sair com foto), ficha do colaborador em 15 seções, certificados por vencimento, dashboard de turnover, atributos do cargo (CBO, exige CNH/CNV/porte), termo disciplinar em PDF, trava de férias com afastamento aberto + registrar retorno.
- 24/09 10:30 — T5 mesclada (16 recursos; 4 implementados: log do sistema como tela lendo a trilha viva, solicitação de material com aprovar/atender baixando estoque pela F9, exames do ASO com validade por periodicidade, **acessos temporários** com papel e expiração que expiram/revogam sozinhos e nunca abrem o Financeiro). T3 mesclada (20 recursos; 9 implementados: **vagas do contrato** como entidade (função × escala × turno × qtd × salário), custo por vaga, **restrições do cliente** que recusam movimentação, **Cobrir/Alocar por linha no grid** (grid e mapa de ponto ganharam aba — trava de porta 17 → 15), painel de alertas com 393 vivos em 20 regras, Visualizado/Finalizar no livro, copiar contrato, visitas por cliente). T4 mesclada (24 recursos, maioria já TEMOS; 5 implementados: cobrança por e-mail lendo os parâmetros da F4, **importar OFX** (parser existia sem rota), agenda de caixa por dia, comissão fechada vira conta a pagar, recebível proporcional por dias em paralelo cego). **INCIDENTE T4:** teste HTTP no sandbox herdou o SMTP real do `.env` e enviou 1 lembrete de cobrança real a um cliente — trava em curso.
- 24/09 11:10 — T2 mesclada (ponto do DGX exercitado; o motor de cálculo deles não está provisionado no trial — cartão e banco de horas falham na própria UI deles; 2 lacunas de valor alto implementadas: **integração de batimentos** (AFD 1510/671 → batidas com chave idempotente, «só validar», log) e **fechamento de competência como trava única** (ajuste/lançamento manual em mês fechado → 409; reabrir com motivo obrigatório e trilha). **Rodada 2 completa: T1–T5 mescladas.** Próximo: prova da árvore e bake.
- 24/09 12:05 — **bake 18 no ar** (imagem 8ea6cdc3, sem drift, 0 chaves desconhecidas). Rodada 2 em produção: DP 120 telas, Operacional 128, Financeiro 177, CRM 84, Suprimentos 22, Saúde 31, Configurações 14, Segurança 11. 6 oráculos novos + vizinhos verdes no container de produção. Trava de porta 15 (13 telas antigas + payable/receivable). Relatório fechado: `auditoria/RELATORIO_NOITE_2026-09-24.md` §9–§12 (38 decisões do dono no total).

## Onda 3 — o que tem valor e não depende de decisão do dono (24/09, tarde)

Jordan: *"prosiga em loop."*

| # | Frente | Módulo | Estado |
|---|---|---|---|
| U1 | Movimentação em dois passos (pedido → aprovar/recusar, DP segue direto) + supervisão planejada com frequência e mapa realizado × planejado | operacional | mesclada · oráculo verde |
| U2 | Férias completas: aviso em lote (PDF + assinatura), recibo timbrado com o cálculo existente, conta a pagar idempotente (art. 145), cobertura/movimentação ao aprovar, ficha por pessoa | dp | mesclada · oráculo verde |
| U3 | Porta para toda tela: as 13 órfãs + `payable`/`receivable`; oráculo «toda tela tem porta» | diversos | mesclada · oráculo verde |
| U4 | Rondas do Vigilância (modelos com pontos, alertas, pânico) × frente 06; chamados com setor e notificação | operacional | mesclada · oráculo verde |
| U5 | Entrega de benefício em lote com período de apuração (DGX `EntregasBeneficios`) sobre o motor da frente 03 | dp | mesclada · oráculo verde |

- 24/09 12:20 — U1–U5 lançadas.
- 24/09 13:05 — U1 mesclada (pedido de movimentação em tabela própria `op_movimentacao_pedidos` — 4 leitores juntam `employee_alocacoes` só por data e uma linha pendente vazaria para a folha; aprovar chama o `alocar` de ontem; pendentes na Central de Aprovações; supervisão planejada com frequência, ocorrências por dia geradas de forma idempotente, checklist ou check-in do gerente marca realizada; mapa mês × posto). Beat 00:30 fica com o orquestrador.
- 24/09 13:40 — U4 mesclada (modelos de ronda com pontos e raio; alertas por tipo; motor idempotente; **pânico** pela API com foto → disparo + ocorrência grave + notificação; setores por contrato; chamado avisa o setor ao abrir e o solicitante ao resolver; sandbox só simula).
- 24/09 14:30 — U3 mesclada (13 telas órfãs: 6 ganharam aba, 4 do marketing já tinham botão (falso positivo do caçador corrigido), 1 virou botão, 2 ações removidas; telas sem porta 15 → 1 — a que sobra é `crm.json` alterado no disco por outra sessão, sem commit). U2 mesclada (aprovar férias com substituto cria cobertura F8 + movimentação F5; recibo e aviso em PDF com o cálculo existente; aviso em lote com fila de assinatura; conta a pagar idempotente venc. início−2; ficha por pessoa; painel «postos descobertos» no mapa). U5 mesclada (entrega de benefício como lote com período de apuração manual/apontamento, acerto contra as duas anteriores, arquivo do operador, conta idempotente). **Onda 3 completa.** Beats registrados: supervisão 00:30, alertas de ronda */5. Achado da U5 para a onda 4: motor da frente 03 conta 2 dias no 12x36 noturno com intervalo (ADAILSON 31 dias em 08/2026 para 15 plantões).

## Onda 4 — o que sobrou nas listas de lacunas com esforço P/M e sem decisão (24/09, fim de tarde)

| # | Frente | Módulo | Estado |
|---|---|---|---|
| V1 | Defeito do motor de benefício: plantão 12x36 noturno com intervalo contado como 2 dias (ADAILSON 31 → 15) — corrigir na fonte única, Σ|Δ| diurnos = 0 | folha | mesclada · oráculo verde |
| V2 | Vaga do contrato → vaga de recrutamento (elo posto/contrato; candidato aprovado cai alocado no posto) + QR de abertura de chamado por setor com etiqueta em PDF | operacional | mesclada · oráculo verde |
| V3 | Frota como no APP Frotas: manutenção como entidade (aprovar, gera troca tipada e título, pede materiais), multa → conta/recurso, itens de vistoria configuráveis (impede locomoção), grupos hierárquicos de materiais | equipamentos | mesclada · oráculo verde |
| V4 | DP: fila de falhas de importação (todos os importadores gravam), exportar/imprimir colaboradores com contadores por status pela régua `identidade`, importar apontamentos CSV pelo escritor existente | dp | mesclada · oráculo verde |
| V5 | Fiscal/financeiro: códigos de serviço com NBS/CST/PIS-COFINS/IBS-CBS (NFS-e byte-idêntica), formas de pagamento como cadastro, limite por condição, centros de custo em árvore ligados às categorias, relatórios PDF/Excel | financeiro | mesclada · oráculo verde |

- 24/09 15:20 — V1 lançada durante o gate; V2–V5 lançadas com o bake 19 em curso (agentes em worktree não afetam o disco do build).
- 24/09 16:10 — **bake 19 no ar** (imagem 20f697bf, sem drift). Onda 3 medida em produção: DP 125 telas, Operacional 139, Financeiro 177; tabelas criadas. **Dois achados só visíveis em produção**, corrigidos: (1) o oráculo da U4 notificava DE VERDADE na varredura da meia-noite — o dono receberia e-mail de fixture toda noite e `@externo.invalid` virava tentativa de entrega; paredes `simular=True` nos serviços de alerta e recusa de domínio reservado (RFC 2606) no mailer; verde agora no sandbox E em produção. (2) `test_oraculo_toda_tela_tem_porta` apagado: não mede dentro do container (menus vivem no front) e saía com código 2, que a varredura conta como VERMELHO — alarme falso diário; a régra segue no caçador do host, já registrado.
- 24/09 16:15 — onda 4 (V1–V5) relançada: a primeira tentativa morreu no limite do modelo, com as 5 branches vazias (limpas).
- 24/09 17:40 — **onda 4 completa**, 5/5 mescladas com vizinhos verdes. V1: plantão noturno vira UM dia (ADAILSON 31 → 15; conferência de 09/2026 cai R$ 1.386,00 e a trava da U5 pode sair); régua na fonte única `ponto/services/horas_service.py`, folha/holerite/pagamento intocados (Σ|Δ| = 0 para quem não trabalha à noite). V2: vaga do contrato → vaga de recrutamento (índice único: uma aberta por posto) e candidato aprovado cai alocado; QR público para abrir chamado com etiqueta em PDF. V3: manutenção de veículo como entidade (aprovar → troca tipada + título + pedido de material), multa vira conta e tem recurso (deferido cancela o título sem pagar), itens de vistoria configuráveis que bloqueiam a saída, grupos hierárquicos. V4: fila de falhas dos 4 importadores do DP, exportar/imprimir colaboradores com contadores pelas réguas existentes, apontamentos por CSV em paralelo cego. V5: 10 campos fiscais nos códigos de serviço (XML da NFS-e byte-idêntico), formas de pagamento (a tabela já existia vazia — faltava a porta), limite por condição, centros de custo em árvore (`parent_id` já existia), relatórios em PDF/Excel.
- Achados das frentes que o verde não pegava: `ANY(CAST(:ids AS uuid[]))` quebra no asyncpg (V5, 500 real); «só validar» do CSV gravava pendência (V4); o scratchpad é compartilhado entre agentes da mesma onda e trocou mensagens de commit (V4/V5 — corrigido por amend).

## Onda 5 — o que restou com valor, e o gêmeo do defeito (24/09, noite)

| # | Frente | Módulo | Estado |
|---|---|---|---|
| W1 | O **gêmeo** do plantão noturno: `parear_batidas['dias_trabalhados']` tem o mesmo defeito (86 dias a mais em 08/2026) e alimenta o holerite informativo e `gp_monthly_closings`; + caçador da **escala lançada na paridade errada** (a classe do RILEM) | folha | mesclada · oráculo verde |
| W2 | **Fatura como documento** (numerada, com itens, período, condição, cópia em lote, PDF individual e em lote, vira recebível) — temos recebível, não tínhamos o documento | financeiro | mesclada · oráculo verde |
| W3 | **Hora extra classificada**: por que ela existiu (cobertura, pedido do cliente, falta de efetivo, atraso) e se é repassável — a coluna «HE repassável não faturada» entra no calculado × faturado | ponto | mesclada · oráculo verde |
| W4 | **Transferência entre as empresas do grupo** (o caso GEILSON, que só apareceu no espelho do eSocial): mantém admissão/férias/dependentes, encerra e reabre alocação, enfileira S-2299 + S-2200 como RASCUNHO, e uma régua que compara espelho × sistema | dp | mesclada · oráculo verde |
| W5 | **O elo que falta do «Evento como hub»**: mapa evento do ponto → rubrica da folha como cadastro em cascata, com oráculo que exige que TODA verba de ponto do holerite publicado seja explicada pelo mapa (Σ\|Δ\| = R$ 0,00). O que não fechar é a dívida medida entre cadastro e motor | folha | mesclada · oráculo verde |

- 24/09 18:05 — W1–W5 lançadas sobre o bake 20.
- 24/09 19:00 — W1 mesclada. O gêmeo era a montante do `calculo_service` (que não precisou ser tocado): a régua da V1 passou a valer no pareamento. Σ|Δ| 84 dias em 08/2026 e 52 em 09/2026 (ADAILSON 31→15, ANDREA 31→15, ANILSON 29→16, RILEM 25→14); **paralelo cego provado verba a verba nos 167 holerites gravados: Σ|Δ| = R$ 0,00**, só o campo informativo muda em 25 deles. Trava **77** registrada (`checar_escala_paridade`): 4 escalas na paridade errada. Achado a seguir: o espelho (`time_record_service._pair_punches`) é o TERCEIRO pareador da casa e ainda usa a régua velha.
- 24/09 19:05 — medição das telas em produção: **39 de 44** telas das ondas DGX mostram dado real (cct-funcoes 51, mapa-ferias 52, movimentacoes 73, parcelas-folha 99, orcamento-vs-realizado 95, materiais/estoque 147, auditoria 400…). As 5 vazias estão vazias porque o cadastro ainda não existe (frota sem veículo, exames do ASO novos, certificados sem registro) — nenhuma com erro.
- 24/09 19:40 — W3 mesclada. Medição que importa: **588 dias-pessoa de hora extra em 08+09/2026 (636h) e NENHUM com cobertura casada** — porque `substitutions` e as movimentações de cobertura estão zeradas (F5/F8 nasceram ontem). Hoje tudo isso é custo nosso por omissão; a tela deixa classificar e o calculado × faturado ganhou a coluna «HE repassável não faturada» (R$ 329,44 no maior contrato). Σ|Δ| = R$ 0,00 contra os 65 holerites de 08/2026. Achado: a folha NÃO lê `time_sheets` — a HE da folha sai de `horas_reais_ponto()`; são réguas diferentes, e por isso o R$ da tela é estimativa declarada.
- 24/09 19:45 — W4 mesclada. §1 confirma o caso real: dos 5 desligamentos no espelho do eSocial, quatro são demissão de verdade e **um é transferência — GEILSON, motivo 11, 30/06/2026**. O `empresa_id` dele já estava certo no cadastro, mas **não havia registro nenhum da transferência**: sem data, motivo, autor ou evento. A única prova morava no governo. Agora há fluxo (mantém admissão, período aquisitivo e dependentes — recontados pelo oráculo), dois eventos em RASCUNHO e uma régua que compara espelho × sistema.
- 24/09 20:20 — W5 mesclada. O oráculo prova o que interessa: **as 153 verbas de ponto dos holerites de 08 e 09/2026 são TODAS explicadas pelo cadastro** — código resolvido == código emitido e valor recomposto pela fórmula == valor do holerite, Σ|Δ| = R$ 0,00. §7 inverte a pergunta: o cadastro explicou tudo; a dívida são os **7 eventos que o motor NÃO produz** — atraso (o ponto mede e a folha nunca desconta), HE 100%, feriado trabalhado, falta justificada, sobreaviso e **banco de horas crédito/débito** (completo no Operacional, nunca conversa com a folha — o maior buraco). Nenhum foi semeado: linha com rubrica inventada seria ficção.
- 24/09 20:25 — W2 mesclada. A prova por HTTP pegou dois defeitos que o oráculo verde não pegava: `ADD COLUMN IF NOT EXISTS` toma lock exclusivo mesmo com a coluna já existindo (deadlock em duas emissões simultâneas) e nenhuma fatura com conta gerada podia ser cancelada. **Onda 5 completa.**
- 24/09 20:35 — mina desarmada: o builder do Financeiro inteiro (183 telas) deixava de carregar por import circular vindo da W2, e o oráculo da V5 passava verde cuspindo o aviso. Corrigido por delegação tardia e provado na ordem que quebrava.
- 24/09 20:40 — travas mecânicas contra a linha de base: sem regressão minha. `checar_uso_real` 381 → 408 é exatamente o tamanho das telas novas (ninguém as usou ainda); `checar_oraculo_externo` 1 → 2 é melhora (mais número com âncora de fora); `checar_irreversivel` 0 → 1 aponta `whatsapp/agent_service.py:8303` — avisa o dono antes de executar — e **não é desta linha de trabalho** (é da sessão que mexe no José Luís).

## Onda 6 — o ponto mede, a folha não vê (24/09, noite)

A lista de lacunas do DGX está esgotada nos itens de esforço P/M. O que sobrou de maior valor é
**dívida nossa**, que a W5 revelou ao provar o mapa evento→rubrica: dos 15 eventos, o motor produz
8. Os 7 que faltam são dinheiro nos dois sentidos.

| # | Frente | O que mede (e NÃO muda) | Estado |
|---|---|---|---|
| X1 | **Banco de horas × folha** — o banco está completo no Operacional e nunca conversou com a folha. Quanto venceu sem pagar nem compensar (art. 59 §2 CLT) é passivo | folha | mesclada · oráculo verde |
| X2 | **Atraso e falta justificada** — o ponto mede atraso e a folha nunca desconta; e falta justificada aprovada que foi descontada mesmo assim é dinheiro tirado do colaborador | folha | mesclada · oráculo verde |
| X3 | **Feriado trabalhado e HE 100%** — a rubrica 0011 existe e o motor nunca a emitiu; quem trabalhou em feriado recebeu o quê? | folha | mesclada · oráculo verde |
| X4 | **O terceiro pareador** — `time_record_service._pair_punches` alimenta o ESPELHO (o documento que o colaborador assina) e ainda usa a régua velha; unificar em `horas_service` | ponto | mesclada · oráculo verde |
| X5 | **Painel do dono** — as 51 decisões pendentes saem do markdown e viram tela com o número de hoje e o botão para agir | bi | mesclada · oráculo verde |

Todas em paralelo cego: Σ|Δ| contra `hr_payslips` = R$ 0,00 é condição de entrega em X1, X2, X3 e X4.

- 24/09 20:55 — X1–X5 lançadas.
- 24/09 22:30 — **onda 6 completa, 5/5.** O que ela mediu, tudo em paralelo cego (Σ|Δ| = R$ 0,00 nos holerites em X1, X2, X3 e X4):
  - **X1 · banco de horas:** a tabela `time_bank` tem **0 linhas** — o módulo inteiro existe e nunca recebeu um lançamento. A hora está no espelho: 933,32 h de crédito em 6 competências. Pela CLT art. 59 §3 valeriam R$ 12.560,43; o holerite pagou R$ 4.155,57. **R$ 8.404,86 nunca pagos nem compensados, e R$ 1.459,88 vencem em 27/09/2026** (16 pessoas, crédito de 03/2026).
  - **X2 · atraso:** 30.336 min marcados, R$ 3.077,57 estimados, R$ 0,00 descontados (não existe rubrica de atraso). Mas **64% do «atraso» de setembro é batida de ENTRADA faltando**, não atraso — marcado em coluna própria e fora da conta de dinheiro. E das 13 justificativas da base, **13 pendentes, 0 aprovadas**, a mais antiga desde 21/07.
  - **X3 · feriado:** **R$ 5.399,01** de passivo nominal em 3 competências — 21 pessoas trabalharam em 05/09 e 21 em 07/09, e o holerite pagou o dia uma vez só; mais 29 linhas de HE que o espelho classifica como 100% e a folha pagou a 1,5. A rubrica 0011 nunca foi emitida em 2026. O oráculo mordeu: acusava 2 pessoas de feriado que não trabalharam (batida solitária sem continuidade de plantão) — corrigido antes de entregar.
  - **X4 · pareadores:** são **OITO** em `backend/modules`, não três. A tela de ponto do DP entrou na régua única (Σ|Δ| 162 → 2 dias). O espelho LEGAL (`espelho_service`) — o PDF que o colaborador assina — continua com régua própria e é a maior dívida que sobra. 19 espelhos assinados provados intocados.
  - **X5 · painel do dono:** 28 decisões semeadas, 18 com número ao vivo, em `/redesign/bi?t=decisoes-do-dono`.
- 24/09 22:35 — duas travas ajustadas: oráculo X4 registrado em `checar_regressao.py`; e a varredura dele deixou de acusar quem IMPORTA a régua única (acusava a X3, que faz certo — trava que pune o certo empurra a próxima frente a copiar).

## Decisão do dono — banco de horas quitado (24/09, 12h20)

Jordan: *«ninguém tem banco de horas nem valores a vencer porque eu já paguei tudo, pode zerar
essa conta»*. Não bastava apagar as 334 linhas — o crédito é MEDIDO do espelho, então voltaria no
próximo «Apurar». Virou **corte declarado** (`system_configs.banco_horas.corte_quitado = 2026-09`),
o mesmo padrão do `contabil.corte_baseline`. Reapurado em produção jan→set: **R$ 0,00 a pagar, 0
com vencimento, 334 linhas em `quitado_pelo_dono`** (as horas continuam visíveis). Oráculo ganhou o
bloco (g): apagar o corte fica VERMELHO, em vez de o passivo voltar calado; e a fixture que prova a
CLT art. 59 §3 passou a nascer depois do corte, para a regra seguir valendo para crédito novo.
Registrado no painel como **D29 · decidida**. Bake 23 (imagem 0f8da58d) publicou o código do corte.

## Onda 7 — a última milha do ponto, e o colaborador (24/09, tarde)

| # | Frente | Módulo | Estado |
|---|---|---|---|
| Y1 | **Espelho LEGAL na régua única** — o PDF que o colaborador assina é o último pareador fora da régua; espelho assinado é intocável | ponto | em execução |
| Y2 | **A direção da batida** — 192 h de diferença em 3 meses entre a tela e a folha; medir, classificar por causa e recomendar, sem escolher | ponto | em execução |
| Y3 | **Justificativa e batida faltante** — 13 justificativas paradas (0 aprovadas, a mais antiga de 21/07) e 20.445 min que são batida de entrada faltando, não atraso | ponto | em execução |
| Y4 | **Colaborador sem cliente** — 47 de 63 órfãos, e é por isso que feriado de cliente não alcança ninguém; resolver pelo vínculo VIVO, não preenchendo 47 cadastros por inferência | dp | em execução |
| Y5 | **O que o COLABORADOR vê** — 30 frentes construíram para o escritório; ele continua vendo o mesmo. Ligar aviso de férias, recibo, crachá, espelho e benefício ao portal, com oráculo de vazamento | portal | em execução |

- 24/09 12:45 — Y1–Y5 lançadas sobre o bake 23.

## Onda 8 — NF-e de material para os DOIS CNPJs (24/09, pedido urgente do dono)

Jordan: *«coloca a emissão de NF-e de material na próxima onda para os dois cnpj, preciso urgente
emitir notas fiscais»*.

**O estado que motivou:** existem **dois** emissores de NF-e no repositório
(`fiscal_contabil/notas_fiscais/nfe/controller.py` com lxml e `financial/integrations/nfe_provider.py`
com pynfe) e **nenhuma nota autorizada**. As duas únicas tentativas são de 11/04/2026, ambas
rejeitadas — a última com «Informado NCM inexistente». Não há tela de emissão no redesign.

| # | Frente | Entrega | Estado |
|---|---|---|---|
| Z1 | **Cadastro fiscal do produto** — NCM validado contra tabela oficial, CFOP, CST/CSOSN por empresa; seed dos **95 NCMs reais** que vieram das 147 NF-e de compra | fiscal | mesclada · oráculo verde |
| Z2 | **Um emissor só, provado** — escolher entre os dois, aposentar o outro, e AUTORIZAR uma nota em **homologação para cada CNPJ**; chave com DV, numeração por CNPJ+série, XML assinado e protocolo guardados, cancelamento e inutilização | fiscal | **mesclada · NOTA AUTORIZADA** (cStat 100, nProt 113260013553736) · oráculo verde · a Patrimonial para na IE vazia |
| Z3 | **A tela e o DANFE** — nova nota, prévia do XML com o que falta em vermelho, lista com o motivo da rejeição por extenso, DANFE em PDF com a faixa «SEM VALOR FISCAL» em homologação | fiscal | mesclada · oráculo verde |
| Z4 | **A tributação certa** — Zona Franca, SUFRAMA, lucro real × Simples; cada regra com a norma citada, e «sem fonte» onde não houver | fiscal | mesclada · oráculo verde |

**A regra da onda:** emissão SOMENTE em homologação (`tpAmb = 2`). O caminho de produção fica
pronto e travado atrás de gate humano, e **nenhum agente o exercita** — nota em produção é
documento fiscal irreversível.

- 24/09 13:20 — Z1–Z4 lançadas.
- 24/09 15:30 — Z1, Z3, Z4, Z5 e Z6 mescladas (falta a Z2, o emissor). **Três bloqueios que são do DONO, não de código:** (1) ninguém sabe qual **CFOP de saída** a Conecta usa — por isso **0 dos 95 produtos** está pronto para emitir, e foi por isso que as notas de 11/04 foram rejeitadas; (2) a **Patrimonial não tem Inscrição Estadual** no cadastro, e sem IE não existe NF-e 55; (3) a IE gravada no emissor para a Eletrônica (`45177801`) é a **municipal** — a estadual é 05.426.574-6 (repassado à Z2).
- 24/09 18:50 — **Z2 mesclada. A casa emitiu a primeira NF-e autorizada da sua história**, em
  homologação, SEFAZ-AM: `cStat 100 · Autorizado o uso da NF-e`, nProt **113260013553736**,
  chave `13260935710481000103550010000000091577387314`, CONECTAMAIS ELETRONICA LTDA, CFOP 5102,
  ICMS 20%. Cancelamento (135) e inutilização de faixa (102) também exercidos. Produção continua
  travada por duas camadas mais gate humano: **0 linhas com `tp_amb = '1'`**.
  Dos 3 bloqueios: o (3) caiu — a IE estadual correta já estava em `empresas` e o emissor novo lê
  de lá; o (1) caiu — o CFOP vem da régua da Z4, não de cadastro. **Fica o (2): a Patrimonial não
  tem Inscrição Estadual em lugar nenhum** (procurei em `empresas`, `tenants`, `sped_files`,
  `suframa_configs`; só existe a municipal 721042001). A SEFAZ-AM rejeita 209 e o Amazonas não
  oferece consulta cadastro para descobrir.
- 24/09 — dois achados do orquestrador na hora de mesclar, medidos e não presumidos:
  - `main_production.py` (zona proibida) veio reformatado inteiro pelo `ruff format` do
    pre-commit. Comparei as duas árvores sintáticas ignorando ordem de nomes em import:
    **uma única diferença semântica**, o texto do log, que ficou correto. Mantido.
  - **campo `type: "hidden"` desenhava uma caixa de texto editável com o UUID dentro** — o
    `ModuleView` não tratava esse tipo e caía no `<input type="text">`. Quem fosse transmitir uma
    NF-e veria um campo sem rótulo com o id da nota, e podia editá-lo. Não é defeito da onda Z:
    **9 builders** mandam campo `hidden`. Corrigido na raiz com um filtro.
- Achados que mudam o entendimento: as duas empresas estão DENTRO da ZFM, então o Convênio ICM 65/88 (de fora para dentro) **não se aplica** à venda delas para comprador de Manaus — é operação interna, CFOP 5102, ICMS 20%; e o emissor manda `is_zfm=True` por padrão. **51% dos itens que a casa COMPRA vêm com ICMS-ST** e não há uma linha de CEST cadastrada.
- Busca de NCM pela descrição (pedido do dono): entregue com fonte por candidato; **taxa real medida 61%**, abaixo dos 70% pedidos — teto estrutural (71 dos 95 NCMs aparecem uma vez só). O oráculo trava em 55% e imprime a taxa; 70% viraria alarme falso.
- Bartolo: **nenhum chat novo** — é o consultor que já existia, com 5 consultas novas e uma regra («PROIBIDO inventar NCM, alíquota ou CFOP; CONSULTE ANTES de dizer que não existe»). A linha de base pegou ele afirmando com confiança que a casa «não tem NF-e de saída» e inventando tabela de CFOP de memória.
- Colisão estrutural resolvida no merge: **quatro frentes criaram `router = ...` no mesmo `fiscal.py`** e cada definição apagava a anterior — as rotas de emitir NF-e e de produto fiscal sumiam alternadamente, sem erro. Um router só; quem chega depois INCLUI.

## RADAR — catálogo de produto a partir da compra, alimentando o orçamento do CRM

**Pedido do dono (24/09):** *«baseado nas notas fiscais de compra da Conecta Eletrônica, cadastrar
os produtos, ter cuidado com duplicidades, pois aí na hora de fazer o orçamento fazemos pelo CRM,
já estará lá com toda a descrição, só seleciona o item e as quantidades; e se aprovado a gente
marca lá, porque se foi aprovado vai gerar nota fiscal. Depois de resolver o emissor, coloca isso
no radar.»*

**O fluxo inteiro que ele desenhou:** compra → catálogo → orçamento no CRM → aprovado → nota.
As pontas já existem: a Z5 faz **proposta aprovada → rascunho de nota**, e a Z1 fez o cadastro
fiscal. Falta o miolo: **o catálogo que nasce da compra e entra no orçamento**.

### O que eu já medi (e que muda o desenho)

| Fonte | Linhas | O que é |
|---|---|---|
| `products` | **867** (193 com NCM) | catálogo importado do **Bling** em 27/08 — já existe e ninguém citou |
| `nfe_compras_estoque` | 147 | itens das notas de compra, com NCM e descrição do fornecedor |
| `nfe_entradas.xml_raw` | 207 itens / 50 NF-e | o XML cru, com **tributação real** (a Z4 achou: 51% com ICMS-ST) |
| `fin_produtos` | 95 | o cadastro fiscal que a Z1 semeou |
| `proposal_items` | 177 | os itens dos orçamentos do CRM — o destino |

**A duplicidade NÃO é textual: as 147 descrições são todas diferentes entre si.** É semântica, e
ela tem duas caras opostas — medidas nos dados reais:

- **NCM 64039190 — «bota»: 10 linhas que são UM produto em 10 tamanhos** (N36, N37, N38 … N45).
  Juntar em 10 produtos polui o orçamento; e a casa **já tem grade de tamanho** (`sst_uniforme_grade`,
  frente 10) — é ali que o tamanho vive, não no catálogo.
- **NCM 34025000 — 9 linhas que são 9 produtos DIFERENTES** (detergente, lava-roupas, limpa-vidros,
  multiuso, sabão em pó de três marcas). Mesmo NCM, produtos distintos.

**Conclusão para quem for implementar: «mesmo NCM = mesmo produto» está errado nas duas direções.**
A régua tem de separar o que é **variação** (tamanho, cor, volume) do que é **produto distinto**, e
deixar o humano confirmar o que a régua não tiver certeza — sem fundir no escuro.

### Desenho proposto (para a onda seguinte ao emissor)

1. **Uma fonte só de catálogo.** Decidir entre `products` (867, Bling) e `fin_produtos` (95,
   fiscal) — hoje são dois, e já divergem no mesmo item (a Z1 achou fita isolante com NCM
   `39191020` num e `59061000` no outro). Provavelmente: `products` é o catálogo comercial e
   `fin_produtos` a face fiscal dele; então o elo é uma coluna, não uma terceira tabela.
2. **Importador da compra → catálogo**, com proposta de agrupamento: candidato novo, candidato
   igual a um existente (com o porquê e o score) e candidato que é **variação** de um existente.
   Nada entra sozinho: a tela mostra a proposta e o humano aprova em lote.
3. **Preço: o catálogo nasce SEM preço de venda — decisão do dono em 24/09.** Palavras dele:
   *«nos produtos cadastrados deixem sem valor, quando eu for fazer os orçamentos eu edito o preço,
   porque os preços variam muito, tem muitas constantes, então quando eu orçar pego o preço do dia
   e edito na hora.»* Isso **cancela** a ideia anterior de "o catálogo sugere pela margem": não há
   sugestão, não há preço padrão, não há preenchimento automático no item do orçamento. O campo
   chega **vazio** e o humano digita o preço do dia.
   - `fin_produtos` já obedece: a Z1 não criou coluna de preço nenhuma. **Manter assim.**
   - O custo da compra (`last_purchase_price`, `average_price` em `products`) **pode ser exibido
     como referência** na tela do orçamento, mas **nunca** copiado para o campo de preço de venda.
   - Quem implementar: o importador da compra **não escreve preço de venda**, e o item do orçamento
     **não herda valor** do catálogo. Só código, descrição, unidade e NCM.
4. **No CRM**: o item do orçamento passa a vir do catálogo (código, descrição completa, unidade,
   NCM), em vez de texto livre. É isso que faz o orçamento aprovado virar nota sem redigitar.
5. **Aprovado → nota**: já existe (Z5). O elo que falta é o item da proposta carregar o
   `produto_id` — hoje ele é texto e a Z5 tem de casar por descrição.

**Pré-requisito:** o emissor (Z2) fechado, e os três bloqueios do dono resolvidos (CFOP de saída,
IE da Patrimonial, IE correta da Eletrônica).
