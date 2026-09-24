# DGX F10 — Frotas: saída/retorno, multas com condutor, trocas tipadas, locações, requisições

**Data:** 24/09/2026 (00:00–00:20 Manaus) · **Branch:** `dgx/f10-frotas` · **Módulo:** `equipamentos`
**Sessão:** agent-f10 · **Sandbox:** `conecta_pro_staging` (container efêmero `teste-dgx-f10`, porta 8210 — parado ao fim)

## 1. Estado antes (medido)

| O que | Medido em 24/09 00:40 |
|---|---|
| `frota_veiculos` / `frota_leituras` / `frota_vistorias` (frente 10, 12/09) | existem, **0 linhas** cada — a frota nunca foi cadastrada |
| `frota_leituras.tipo` | CHECK só aceita `km` e `abastecimento` |
| Tabelas de saída, multa, locação, requisição | **não existem** |
| Motoristas com CNH em `employees` | **0 de 63 ativos** têm `cnh_numero` preenchido |
| `manutencoes` do builder `equipamentos` | lê `equipment_maintenances` (patrimônio, não veículo) — não toquei |
| Contas a pagar | `payable_accounts` (369 linhas no tenant "empresa"); `rd_action_payable` já cria título pelo `PayableService` |
| Desconto em folha | `employee_deductions` (tipo `outros` permitido); `create_deduction` no `employee_controller` |
| Oráculo `test_oraculo_frota_operacional.py` | **VERMELHO** — `builder _dgx_f10_frotas não importa` (não existia) |

A frente 10 tinha decidido: *"multa: sem tabela de posse datada não se aponta condutor"*. Não havia posse datada.

## 2. O que o DGX tem (docs/dgx/00, 06, 07)

Frotas: Abastecimentos · Requisições Abastecimento · Requisições de Lavagem · Controle de Saída · Locações ·
Manutenções · Multas de Trânsito · Troca de Correia · Trocas de Óleo · Trocas de Pneu · Veículos · Vistorias
(grid: Status do Checklist, Status de Chegada, Placa, Condutor, Km, Data, Manutenção Pendente). Rótulos do bundle:
Placa, Chassi, Marca, Modelo, Ano, Cor, KM Inicio/Final, Motorista, Tipo de Saída, Total KM.

## 3. O que foi feito

**Arquivos**
- `backend/modules/operacional/controllers/redesign_builders/_dgx_f10_frotas.py` (novo) — 10 telas + 11 ações + `_ensure`.
- `backend/modules/operacional/controllers/redesign_builders/equipamentos.py` — plug: `telas(db, out)` no fim do
  `build()`, `router` combinado (frente 10 + F10), `EXTRA_MENU` com os 10 itens (`# dgx f10`).
- `backend/scripts/orq/test_oraculo_frota_operacional.py` (novo).

**Reuso (não copiado):** `frota_leitura` da frente 10 grava a leitura de KM do retorno e a de abastecimento da
requisição realizada (hodômetro não recua, R$/L e km/l saem no painel dela); `create_deduction` do DP cria o
desconto da multa; `rd_action_payable` do redesign cria o título da locação; `PERIODO_KM_DIAS`, `JANELA_VISTORIA_HORAS`,
`_form/_opts/_int/_dec/_dt/_quem/_SQL_VEICULOS` importados de `_frente_10` (módulo inteiro, para não fechar ciclo de import).

**DDL que `_ensure` aplica no 1º acesso (idempotente)**
```
CREATE TABLE IF NOT EXISTS frota_saidas (…, km_retorno CHECK (km_retorno IS NULL OR km_retorno >= km_saida), …)
CREATE UNIQUE INDEX IF NOT EXISTS ux_frota_saidas_aberta ON frota_saidas (veiculo_id) WHERE data_retorno IS NULL
CREATE INDEX IF NOT EXISTS ix_frota_saidas_veiculo …
CREATE TABLE IF NOT EXISTS frota_multas (… condutor_sugerido_id, condutor_employee_id, indicado_em, status, desconto_folha, deduction_id …)
CREATE TABLE IF NOT EXISTS frota_locacoes (… veiculo_id OU placa_terceiro/modelo_terceiro, payable_id …)
CREATE TABLE IF NOT EXISTS frota_requisicoes (… tipo abastecimento|lavagem, status, aprovado_por/em, leitura_id …)
ALTER TABLE frota_leituras ADD COLUMN IF NOT EXISTS proxima_km integer;  ADD COLUMN IF NOT EXISTS proxima_data date
ALTER TABLE frota_leituras DROP/ADD CONSTRAINT frota_leituras_tipo_check  -- só se ainda não aceita troca_*:
    tipo IN ('km','abastecimento','troca_oleo','troca_pneu','troca_correia','troca_filtro','troca_pastilha')
```

**Telas** (todas em `/redesign/equipamentos?t=<id>`, grupo solto "Frota · …" ao lado das da frente 10)

| id | o quê | ações por linha |
|---|---|---|
| `frota-saidas` | abertas primeiro ("Em uso"), KM rodado | Registrar retorno (KM ≥ saída; grava `frota_leituras` km) |
| `frota-saida-nova` | veículo, motorista (CNH primeiro), KM, motivo (5), destino | 409 se o veículo já está fora |
| `frota-multas` | data/hora, órgão·auto, pontos, valor (c/ desconto), condutor, **sugerido**, situação | Indicar condutor (pré-preenche o sugerido) · Marcar paga · Descontar em folha (pede «Sim, descontar») |
| `frota-multa-nova` | campos livres; sugere condutor por `frota_saidas` cobrindo data+hora, senão última vistoria na janela | — |
| `frota-trocas` | por veículo × tipo: última troca, KM na troca, próxima KM, **Restam** (vermelho = vencido), próxima data | — |
| `frota-troca-nova` | óleo/pneu/correia/filtro/pastilha; óleo/pneu/correia também atualizam `frota_veiculos.km_proxima_troca_*` | — |
| `frota-locacoes` | frota ou terceiro, locadora, contrato, período, mensal, franquia, título | Encerrar |
| `frota-locacao-nova` | «Gerar título» = 1ª mensalidade em contas a pagar (confirm) | — |
| `frota-requisicoes` | pendente → aprovada/negada → realizada | Aprovar · Negar · Realizada (abastecimento pede KM+litros+valor → leitura) |
| `frota-requisicao-nova` | abastecimento ou lavagem | — |

**Provado no sandbox por HTTP (2 veículos `FIXTURE DGX F10`, apagados ao fim):** saída dupla → 409; retorno 9.990 < 10.000 →
409; retorno 10.120 → leitura #1 e "120 km rodados"; multa às 00:08 com saída aberta → *"Condutor sugerido: ADEILSON"*
e o botão Indicar já vem com ele; multa 5 min depois do retorno → *"Sem posse datada"*; descontar sem confirmar → 400;
descontar → `employee_deductions` R$ 195,23 tipo `outros`, 1 parcela, ligado por `deduction_id`; descontar de novo → 409;
troca de óleo a 10.120 com próxima 15.000 → painel da frente 10 e tela de trocas mostram os mesmos **4.820 km**; requisição
realizada → leitura #5 de abastecimento e a tela `frota-abastecimentos` da frente 10 mostra R$/L 6,25; locação com
título → `payable_accounts` R$ 2.500,00 venc. 05/10/2026 status pendente. No banco: `INSERT` com km_retorno 999 < 1000
→ `violates check constraint`; 2ª saída aberta → `duplicate key … ux_frota_saidas_aberta`.

## 4. Oráculo

`backend/scripts/orq/test_oraculo_frota_operacional.py` — afirma (a) saída aberta única por veículo **e** índice único parcial
existe; (b) `km_retorno < km_saida` recusado pelo banco (savepoint desfeito); (c) multa com `desconto_folha` tem
`employee_deductions` do mesmo condutor; (d) `Restam` da tela == recomputado por SQL próprio (próxima KM da última
troca − max KM nos últimos `PERIODO_KM_DIAS`); (e) requisição de abastecimento realizada ↔ exatamente uma leitura.

```
# ANTES (24/09 23:56, sem o módulo)
FALHOU: builder _dgx_f10_frotas não importa: cannot import name '_dgx_f10_frotas' from 'modules.operacional.controllers.redesign_builders'
TOTAL frota_operacional: 1
exit=1

# DEPOIS (24/09 00:15, com as fixtures no sandbox)
saídas: 3 (abertas 1) · multas em folha: 1 · trocas conferidas: 3 · requisições realizadas: 1
TOTAL frota_operacional: 0
OK frota_operacional: saída única, hodômetro não recua, multa desconta do condutor, Restam fecha, requisição gera uma leitura
exit=0

# frente 10 continua verde (único oráculo com "frota" em scripts/orq)
vistorias de saída: 0 · com par: 0 · aguardando checklist: 0
OK vistoria_par: toda saída compara com a chegada certa ou espera o checklist
exit=0
```

Como roda: `orq.sh` do contrato com `--tmpfs /app/logs:mode=1777 --tmpfs /app/uploads:mode=1777` (a worktree precisa dos
diretórios `backend/logs` e `backend/uploads` vazios para o tmpfs ter ponto de montagem — criados, não commitados).

## 5. O que NÃO foi feito, e por quê

1. **`Restam` não é a função da frente 10 importada.** Ela é uma closure dentro de `_telas_frota` — só seria importável
   editando `_frente_10.py`, que é intocável nesta frente. `restam()` aqui tem a mesma régua (sem KM nos últimos
   `PERIODO_KM_DIAS` → "sem dado"; < 500 km → amarelo; negativo → vermelho) e o oráculo (d) prova que a conta fecha.
2. **Motorista não é "quem tem CNH".** 0 dos 63 ativos têm CNH cadastrada; restringir deixaria o formulário vazio. A lista
   é de ativos com quem tem CNH primeiro e "· CNH B" no rótulo. Quando o DP preencher `cnh_numero`, basta trocar o
   `_SQL_MOTORISTAS` para `WHERE coalesce(cnh_numero,'') <> ''`.
3. **Vistoria de saída/retorno não é criada automaticamente pela saída** — `vistoria_saida_id`/`vistoria_retorno_id` existem
   na tabela para o Jordan ligar, mas a vistoria da frente 10 pede fotos por área e OS; obrigar isso a cada saída de supervisão
   mataria o registro. A multa já usa a vistoria como 2ª fonte de posse.
4. **Título mensal recorrente da locação não foi gerado** — só a 1ª mensalidade, pelo mesmo `rd_action_payable`. A recorrência
   é a F11 (contas fixas → recorrência gera título) e não deve nascer duas vezes.
5. **Sem desconto parcelado de multa** — 1 parcela, valor cheio, tipo `outros`. Parcelar é decisão de DP (ver §7).
6. **Sem upload de comprovante** — `comprovante_url` é um link. A frente 10 já tem o padrão de foto multipart; replicá-lo
   para requisição antes de alguém pedir seria a 2ª cópia.
7. **`manutencoes` do builder não foi ligada aos veículos** — lê `equipment_maintenances` (patrimônio). Misturar exigiria a
   decisão "veículo é `equipment`?" que a frente 10 já deixou para o dono.
8. **Nada foi para produção.** Sem bake, deploy ou `docker cp`. O DDL de produção é o do §3, aplicado por `_ensure` no 1º acesso.

## 6. Como o Jordan testa amanhã

1. `Equipamentos → Frota · Novo veículo` — cadastrar o carro de supervisão (placa, modelo, próximas trocas em KM).
2. `Frota · Nova saída` — escolher o carro, o motorista, o KM do painel e o motivo → **Registrar saída**.
3. Tentar registrar outra saída do mesmo carro → deve recusar ("saída aberta").
4. `Frota · Saídas / retornos` → na linha "Em uso", **Registrar retorno** com o KM de volta (menor que o de saída → recusa).
5. `Frota · Nova multa` — data e hora dentro do período em que o carro estava fora → a mensagem já diz o condutor sugerido;
   em `Frota · Multas` a coluna "Sugerido" mostra o nome e **Indicar condutor** vem preenchido.
6. Na mesma linha, **Descontar em folha** → escolher «Sim, descontar» → confere em `DP → Descontos` a linha "Multa de trânsito #N".
7. `Frota · Nova troca` (óleo, KM atual, próxima em KM) → `Frota · Trocas` e `Frota · Painel` mostram o mesmo "Restam".
8. `Frota · Nova requisição` (abastecimento) → em `Frota · Requisições`: **Aprovar**, depois **Realizada** com KM, litros e valor
   → `Frota · Abastecimentos` (frente 10) ganha a linha com R$/L.
9. `Frota · Nova locação` com «Gerar título = Sim» → `Financeiro → Contas a pagar` tem a 1ª mensalidade (pendente, não paga).

## 7. Decisões que só o dono pode tomar

1. **Multa em folha: valor cheio numa parcela ou parcelado?** Hoje: cheio, 1 parcela, tipo `outros`. A CLT (art. 462) só permite
   o desconto com autorização ou dolo — vale confirmar com o contador se o termo de responsabilidade do condutor cobre isso.
2. **Cadastrar a CNH dos supervisores** (`employees.cnh_numero/categoria/validade`) — hoje 0 preenchidas; com isso a lista de
   motoristas passa a ser só quem pode dirigir e a validade vencida pode bloquear a saída.
3. **Veículo é patrimônio (`equipments`)?** Se sim, `manutencoes` e a frota viram uma coisa só — pendente desde a frente 10.
4. **Locação: título mensal recorrente** entra pela F11 (contas fixas) ou aqui? Sugiro F11, com `payable_id` da locação como
   origem.
5. **Exigir vistoria (fotos) em toda saída?** A tabela já tem os campos; o custo é operacional, não técnico.
