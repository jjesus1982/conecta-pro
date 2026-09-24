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
| F7 | Ponto — configurações de ponto por empresa (tolerâncias, raio, facial obrigatória, arredondamento), banco de horas por colaborador (saldo, vencimento, extrato), relógios/aparelhos cadastrados, jornadas/turnos como cadastro, feriados com escopo (nacional/estadual/municipal/cliente), cartão de ponto modelos | `cct_feriados`, `_frente_01/02/04`, `punch_*` | ponto | 2 | em execução |
| F8 | Operacional — coberturas (quem cobriu quem, folga trabalhada), livro de ocorrências do posto, checklist de supervisão (setores/itens/execução), chamados, avisos/painel | `g-rondas`, `g-disciplina`, ocorrências | operacional | 3 | pendente |
| F9 | Suprimentos — solicitação → pedido de compra → NF de entrada; materiais com estoque mín/máx e movimentação; fornecedores; comunicações móveis/rastreadores como equipamentos controlados | `suprimentos`, `equipamentos`, `_frente_05/10` | suprimentos | 3 | pendente |
| F10 | Frotas — multas de trânsito (com condutor), locações, controle de saída/retorno, trocas (óleo/pneu/correia) como manutenção tipada, requisições de abastecimento/lavagem | `frota_*` (`_frente_10`) | frotas | 3 | mesclada · oráculo verde |
| F11 | Financeiro/Faturamento — contas fixas (recorrência gera título), condições de pagamento, análise orçamentária, fechamento de comissões, CFOP/natureza da operação, recibos de venda, pensionistas como beneficiários | financeiro | financeiro | 3 | em execução |
| F12 | SESMT + Demandas + Comercial — tipos de exame e médicos como cadastro do ASO; assuntos/atendimentos/feedbacks; fontes pagadoras, regiões, postos por cliente | saude_ocupacional, crm | diversos | 3 | pendente |

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
