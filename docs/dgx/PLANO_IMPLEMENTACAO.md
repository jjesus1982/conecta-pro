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
| V1 | Defeito do motor de benefício: plantão 12x36 noturno com intervalo contado como 2 dias (ADAILSON 31 → 15) — corrigir na fonte única, Σ|Δ| diurnos = 0 | folha | em execução |
| V2 | Vaga do contrato → vaga de recrutamento (elo posto/contrato; candidato aprovado cai alocado no posto) + QR de abertura de chamado por setor com etiqueta em PDF | operacional | em execução |
| V3 | Frota como no APP Frotas: manutenção como entidade (aprovar, gera troca tipada e título, pede materiais), multa → conta/recurso, itens de vistoria configuráveis (impede locomoção), grupos hierárquicos de materiais | equipamentos | em execução |
| V4 | DP: fila de falhas de importação (todos os importadores gravam), exportar/imprimir colaboradores com contadores por status pela régua `identidade`, importar apontamentos CSV pelo escritor existente | dp | em execução |
| V5 | Fiscal/financeiro: códigos de serviço com NBS/CST/PIS-COFINS/IBS-CBS (NFS-e byte-idêntica), formas de pagamento como cadastro, limite por condição, centros de custo em árvore ligados às categorias, relatórios PDF/Excel | financeiro | em execução |

- 24/09 15:20 — V1 lançada durante o gate; V2–V5 lançadas com o bake 19 em curso (agentes em worktree não afetam o disco do build).
