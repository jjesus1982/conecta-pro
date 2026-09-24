# Plano geral — trazer para o Conecta PRO tudo que o DGX tem e funciona

**Aberto em:** 24/09/2026, 00:40 (Manaus) · **Mandato do Jordan:** autonomia total — inclusão,
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
| F1 | **Eventos/rubricas como dado** — `rubricas_folha` ganha os atributos do DGX que faltam (período, tipo de dia/falta, crédito/débito, soma ao evento, banco de horas, desconta benefício, exporta/código auxiliar, razão/razão noturna, base salário/mínimo, DSR, 13º, média 13º, vale, ausência). CRUD (incluir/editar/inativar) na aba Rubricas. Oráculo: as flags da tabela batem com o que `calculo_service` faz de fato (INSS/IRRF/FGTS/DSR) nos holerites de 09/2026 — paralelo cego, o cálculo NÃO muda | `rubricas_folha`, `folha-rubricas` | folha | 1 | pendente |
| F2 | **CCT como dado** — Sindicato (entidade) → Funções da CCT → Eventos por função → Benefícios por função → Municípios; seed a partir de `cct_convencoes/cct_cargos/cct_beneficios` (SINDECOMPRESTS) e das constantes de `calculo_service`; CRUD; `cct-conformidade` passa a apontar função sem evento/benefício | `cct_*`, `_cargo_cct` | folha | 1 | pendente |
| F3 | **Tipos de Benefício com regra** — tabela de tipos com `tipo_desconto` (7), coeficiente, faltas/justificadas/dias-mês, meses de afastamento, remover férias/afastados/atrasados, integração ponto (8 modos), desconto por saldo, meio período; benefício individual com linha/quantidade/unitário/anular outras fontes; o motor da frente 03 lê a regra da tabela | `folha_beneficio_conferencia`, `employee_benefits`, `cct_beneficios`, `_frente_03` | folha | 1 | pendente |
| F4 | **Parâmetros por CNPJ** — `system_configs` já existe (12 chaves, escopo global). Ganha escopo `empresa` (chave × CNPJ), leitor `param(db, chave, cnpj)`, seed dos parâmetros do DGX que fazem sentido aqui (folha/apontamento, fechamento, benefícios, ponto, e-mail, fiscal), tela Configurações com seções + editar | `system_configs`, `configuracoes-sistema` | config | 1 | pendente |
| F5 | **Movimentações** — `employee_alocacoes` ganha tipo (alocar/remover), motivo tipado (7 do DGX), origem/destino, vaga, quem pediu, aprovação; tela Movimentações (listar/incluir/encerrar) no Operacional; grid de planejamento reusa `grid-real-contratual` | `employee_alocacoes`, `allocation_controller`, `_frente_04` | operacional | 1 | pendente |
| F6 | DP complementos — dependentes (tabela própria, grau/instrução/deficiência), vales (adiantamento avulso com desconto em folha), eventos coletivos (lançar um evento para N pessoas numa competência), linhas de VT/itinerários por operadora, reajuste de benefício em lote, crachá (dados+foto → PDF), demissão em lote | `employee_dp`, `descontos`, `_frente_03` | dp | 2 | pendente |
| F7 | Ponto — configurações de ponto por empresa (tolerâncias, raio, facial obrigatória, arredondamento), banco de horas por colaborador (saldo, vencimento, extrato), relógios/aparelhos cadastrados, jornadas/turnos como cadastro, feriados com escopo (nacional/estadual/municipal/cliente), cartão de ponto modelos | `cct_feriados`, `_frente_01/02/04`, `punch_*` | ponto | 2 | pendente |
| F8 | Operacional — coberturas (quem cobriu quem, folga trabalhada), livro de ocorrências do posto, checklist de supervisão (setores/itens/execução), chamados, avisos/painel | `g-rondas`, `g-disciplina`, ocorrências | operacional | 3 | pendente |
| F9 | Suprimentos — solicitação → pedido de compra → NF de entrada; materiais com estoque mín/máx e movimentação; fornecedores; comunicações móveis/rastreadores como equipamentos controlados | `suprimentos`, `equipamentos`, `_frente_05/10` | suprimentos | 3 | pendente |
| F10 | Frotas — multas de trânsito (com condutor), locações, controle de saída/retorno, trocas (óleo/pneu/correia) como manutenção tipada, requisições de abastecimento/lavagem | `frota_*` (`_frente_10`) | frotas | 3 | pendente |
| F11 | Financeiro/Faturamento — contas fixas (recorrência gera título), condições de pagamento, análise orçamentária, fechamento de comissões, CFOP/natureza da operação, recibos de venda, pensionistas como beneficiários | financeiro | financeiro | 3 | pendente |
| F12 | SESMT + Demandas + Comercial — tipos de exame e médicos como cadastro do ASO; assuntos/atendimentos/feedbacks; fontes pagadoras, regiões, postos por cliente | saude_ocupacional, crm | diversos | 3 | pendente |

## Ciclo do orquestrador

1. Lança a onda (agentes em worktree, branch `dgx/<frente>`).
2. A cada agente concluído: lê o relatório, `git merge` na branch de trabalho, ruff +
   py_compile + oráculo da frente + `checar_tela_sem_porta`.
3. Fim da onda: bake blue/green (uma vez), deploy do frontend se houver JSON de menu,
   `checar_drift_workers`, arsenal.
4. Atualiza a tabela acima e o log abaixo. Próxima onda.

## Log

- 24/09 00:40 — plano aberto. Onda 1 (F1–F5) lançada.
