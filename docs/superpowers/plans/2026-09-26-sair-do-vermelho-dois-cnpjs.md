# Sair do vermelho — Patrimonial e Eletrônica

> **Para agentes de execução:** use `superpowers:subagent-driven-development` (um subagente
> por tarefa, revisão entre elas) ou `superpowers:executing-plans`. Os passos são checkbox.
> **Antes de qualquer tarefa [CÓDIGO], confirme que a [DECISÃO] de que ela depende foi
> tomada** — a coluna "depende de" na Parte III diz qual.

**Meta:** Patrimonial de −7,2% para +11,1% de margem operacional sem mudar de regime (ou
~+9% depois da curva do DAS, com a migração recuperando o resto); Eletrônica de −136,5%
para positiva.

**Arquitetura:** toda decisão fiscal sai de constante no código e vai para linha da tabela
`empresas` ou de parâmetros por CNPJ, lida por TODOS os leitores — inclusive os gatilhos do
banco. Padrão estabelecido em 26/09 com `empresas.corte_contabil`: **dois leitores, um fato.**

**Stack:** FastAPI · SQLAlchemy · PostgreSQL · caçadores em `backend/scripts/qa/` · oráculos
em `backend/scripts/orq/` · deploy blue/green.

**Medições:** todas de 26/09/2026, fonte citada em cada uma. As que vieram de subagente foram
re-conferidas antes de entrar — uma delas (C5) mudou de interpretação na conferência e
corrigiu o retrato de abertura deste plano.

---

> **Para quem for executar:** este plano tem DUAS naturezas misturadas de propósito, e elas
> estão marcadas. As tarefas **[CÓDIGO]** são implementáveis e seguem o formato de passos
> testáveis. As **[DECISÃO]** não são tarefas de engenharia — são atos do dono, do contador
> ou do advogado, e nenhuma linha de código as substitui. Executar as de código sem as de
> decisão produz um sistema correto sobre uma empresa irregular.

**Objetivo:** levar a Patrimonial de +2,1% para ~18% de margem operacional e a Eletrônica de
−136,5% para positiva, usando a legislação a favor em cada CNPJ.

**Base de medição:** competência **08/2026**, o único mês completo dos dois lados
(junho e julho distorcidos, setembro incompleto). Todos os números abaixo foram medidos em
26/09/2026 e a fonte de cada um está citada.

---

## Global Constraints

Valem para TODAS as tarefas deste plano:

- **Nunca fabricar número.** Onde a fonte está vazia, o lançamento não existe. O razão fica
  honestamente incompleto, nunca preenchido por estimativa.
- **Natureza de conta vem de `fin_accounting_accounts.account_type`**, jamais do primeiro
  dígito do código. Existem contas `EXPENSE` numeradas em 4.x neste plano de contas.
- **Todo parâmetro fiscal é POR EMPRESA.** Constante que codifica decisão sobre um CNPJ e é
  aplicada aos dois já custou um mês inteiro de receita (o corte contábil, 26/09/2026).
- **Toda superfície nova nasce vigiada:** caçador em `backend/scripts/qa/checar_*.py`
  registrado em `checar_regressao.py`, ou oráculo em `backend/scripts/orq/`. A trava afirma
  a REGRA, não a fotografia, e precisa provar que sabe mudar de resposta quando o dado muda.
- **Hot-copy não é permanente.** Toda mudança em `backend/` termina em
  `./scripts/deploy_backend_bluegreen.sh` e conferência `md5sum` imagem × disco.
- **Período fechado:** `empresas.corte_contabil` (Patrimonial 01/06/2026, Eletrônica
  01/08/2026). INSERT antes do corte é recusado pelo gatilho; UPDATE é permitido.

---

## O retrato, e de onde vem cada ponto

### Patrimonial — Simples Nacional Anexo IV

| | receita | despesa operacional | resultado | margem |
|---|---|---|---|---|
| **hoje (08/2026 medido)** | 262.161,56 | 256.542,76 | +5.618,80 | **+2,1%** |
| faturar o contratado (9 contratos ativos = 272.200,06) | 272.200,06 | 256.542,76 | +15.657,30 | +5,8% |
| − Sólides 28.650,00 (já cortada em 14/08) | 272.200,06 | 227.892,76 | +44.307,30 | +16,3% |
| − Portte 2.690,03 (contabilidade própria) | 272.200,06 | 225.202,73 | +46.997,33 | +17,3% |
| − odontológico 4.625,00 (é do sócio) | 272.200,06 | 220.577,73 | +51.622,33 | +19,0% |
| − advogados 3.000,00 (dívida da irmã) | 272.200,06 | 217.577,73 | **+54.622,33** | **+20,1%** |
| **RISCO:** DAS sobe de 7,02% para 16,16% | | +24.879,09 | +29.743,24 | +10,9% |
| se migrar de regime (Lucro Real 9,15%) | | −19.081,22 | **+48.824,46** | **+17,9%** |

### Eletrônica — Lucro Real

| | receita | despesa operacional | resultado | margem |
|---|---|---|---|---|
| **hoje (08/2026 medido)** | 13.300,00 | 31.454,13 | −18.154,13 | **−136,5%** |
| faturar os 4 contratos ativos (15.800,00) | 29.100,00 | 31.454,13 | −2.354,13 | −8,1% |
| − custo do ERP (11.970,00) sai da operação | 29.100,00 | 19.484,13 | **+9.615,87** | **+33,0%** |

**A conclusão estrutural:** mesmo faturando tudo, a Eletrônica só sai do vermelho se o custo
do Conecta PRO deixar de ser despesa da operação de segurança. Ela hoje não é uma empresa de
segurança com prejuízo — é **a casa do produto** com um resto de operação. Os R$ 11.970/mês
de "Vale Refeição" são PIX aos PJs que desenvolvem e sustentam o ERP (medido 26/09).

---

## A maior alavanca não precisa de ninguém

**R$ 211.975,96 de serviço prestado e não faturado**, medido em 26/09/2026:

| empresa | contratos ativos | valor/mês | faturado em 09/2026 | falta |
|---|---|---|---|---|
| Patrimonial | 9 | 272.200,06 | 76.024,10 (2 contratos) | **196.175,96** |
| Eletrônica | 5 | 15.800,00 | 23.160,00 (fora de contrato) | **15.800,00** |

Os sete contratos da Patrimonial sem nota em setembro:

```
CTR-2026-00013  Ideal Flores da Cidade     65.842,42
CTR-2026-00009  Villa dos Passaros         33.538,33
CTR-2026-00010  Mirante das Flores         28.694,30
CTR-2026-00007  Villa Dei Fiori            25.592,71
CTR-2026-00019  Green Hills                22.100,00   ← NUNCA faturado desde 01/09
CTR-2026-00016  Mirante das Flores (2º)    12.061,50
CTR-2026-00008  Michelangelo                8.346,70
```

Isto não depende de contador, advogado nem decisão de regime. É emissão.

---

# Parte I — As decisões (nenhuma linha de código as substitui)

Estas vêm primeiro porque **três tarefas de código dependem delas**. Implementar o LALUR sem
saber se o prejuízo é usável, ou parametrizar o anexo sem saber qual é, é construir sobre
suposição.

## D1 — Portaria ou vigilância? [DECISÃO · advogado tributarista · URGENTE]

**O fato medido:** 9 notas da Patrimonial, R$ 323.266,25, trazem **"portaria"** na descrição
— cinco delas dizem literalmente *"Mão de obra terceirizada para agentes de portaria"* — e
todas foram emitidas sob o **código 11.02, "Vigilância, segurança ou monitoramento"**.

**O conflito, em três documentos:**

| fonte | diz |
|---|---|
| a nota fiscal (código 11.02) | vigilância |
| o CNAE na Receita (8111-7/00) | serviços combinados para apoio a edifícios |
| a descrição na própria nota | mão de obra terceirizada para agentes de portaria |

A Patrimonial **não tem CNAE de vigilância** — quem tem é a Eletrônica (8011-1/01). E a
Solução de Consulta COSIT nº 57/2015 diz: *"Os serviços de portaria e de zeladoria, porque
não se confundem com vigilância, limpeza ou conservação e são prestados mediante cessão de
mão-de-obra, são vedados aos optantes pelo Simples Nacional."* A vedação é o art. 17, XII
da LC 123; a consequência é **exclusão, com efeito retroativo**.

E há prova documental contra: **os clientes retêm os 11% da Lei 9.711/98**, retenção que só
existe em cessão de mão de obra, cuja lista (Decreto 3.048/99, art. 219 §2) inclui
literalmente *"portaria, recepção e ascensorista"*.

**O que salva parte:** o CNAE secundário 8121-4/00 (limpeza em prédios) **está** na lista
permitida do art. 18 §5º-C. Limpeza, jardinagem e piscina estão fora do risco. A portaria é
a parte exposta.

**A pergunta ao advogado, em uma linha:** *o que esses ~51 homens fazem no portão é
vigilância patrimonial desarmada (permitida no Anexo IV) ou portaria por cessão de mão de
obra (vedada no Simples)?*

**Por que decide tudo:** se for portaria, sair do Simples deixa de ser otimização e vira
eliminação de risco — e a **exclusão comunicada pela própria empresa** (art. 30, II da
LC 123) não tem multa, enquanto a **exclusão de ofício** tem e retroage.

## D2 — Regime tributário para 2027 [DECISÃO · dono + contador · prazo 31/01/2027]

A Patrimonial está barata no Simples **hoje** porque abriu em 31/03/2026 e o RBT12 ainda
está proporcionalizado. Medido nas duas guias reais: **6,675% em 07/2026 → 7,018% em
08/2026**. Com R$ 262 mil/mês, o anualizado é R$ 3.145.938 — **5ª faixa do Anexo IV**.

| regime | carga sobre a receita | por mês |
|---|---|---|
| Simples Anexo IV maduro | **16,16%** | 42.360 |
| Lucro Presumido | 18,77% | 49.200 |
| **Lucro Real** (margem real de 2,1%) | **9,15%** | 23.998 |

**O Lucro Real só perde para o Simples se a margem líquida passar de 24,3%.** A de agosto
foi 2,1%; empresa de portaria raramente passa de 10%.

**Ressalvas honestas:** (a) usei ISS de 5%, confirmado para Manaus nos itens 11.02, 07.10,
17.05 e 14.01 (LC municipal 2.833/2021); (b) Lucro Real traz EFD Contribuições, ECD, ECF e
LALUR — que é exatamente o que este plano constrói, então o custo marginal aqui é menor que
o de mercado; (c) a CPP patronal é devida nos três e não entra na comparação.

**A tabela do Anexo IV que uso:** faixas 1 a 5 conferidas por dois caminhos independentes —
as duas guias reais caem em faixas diferentes (2 e 3) e a fórmula fecha nas duas. **A 6ª
faixa está descartada**: as fontes dão parcela a deduzir de R$ 828.000, o que faria a
alíquota CAIR de 16,89% para 10,00% ao cruzar R$ 3,6 milhões. Nenhuma tabela progressiva faz
isso. **Não use a 6ª faixa sem confirmar na fonte oficial** — e isso importa, porque a
Patrimonial está a 87% dela.

## D3 — Classificação previdenciária no eSocial [DECISÃO · contador]

A DCTFWeb de 07 e 08/2026 declara **"Classificação Tributária 1 — Simples com tributação
previdenciária SUBSTITUÍDA"**, e declara só `1082-01 CP SEGURADOS`. Mas a guia do DAS traz
INSS de **R$ 171,06** em julho (1,0% do documento) e **nenhuma linha** em agosto — no Anexo
III seria ~43% da guia. Os dois documentos do governo se contradizem, e no meio deles a
**CPP patronal não está em lugar nenhum**.

| competência | folha | patronal (20% + RAT 3%) | retenção 11% dos clientes | descoberto |
|---|---|---|---|---|
| 06/2026 | 111.388,40 | 25.619,33 | 27.512,95 | −1.893,62 |
| 07/2026 | 102.322,90 | 23.534,27 | 22.689,44 | +844,83 |
| 08/2026 | 106.577,20 | 24.512,76 | 26.845,79 | −2.333,03 |

**O caixa não deve** — a retenção dos clientes cobre a patronal quase ao real, e a DCTFWeb
de agosto informa R$ 19.544,08 de crédito com só R$ 7.011,23 usados. **Falta a declaração.**
Ação: corrigir a classificação de `01 substituída` para `03 não substituída`, declarar a
patronal e abatê-la com o crédito. Retroativo a junho.

## D4 — O crédito de R$ 84.709,90 parado [DECISÃO · contador]

Retenção da Lei 9.711 escriturada em `1.1.3.02`, crescendo ~R$ 25 mil/mês. Caminhos, nesta
ordem: (1) abater a contribuição previdenciária própria via DCTFWeb — depende de D3;
(2) compensar com outros tributos federais via PER/DCOMP; (3) pedir restituição em dinheiro.
Prescrição: 5 anos.

## D5 — Os quatro itens de custo que saem [DECISÃO · dono]

| item | R$/mês (08/2026 medido) | por quê |
|---|---|---|
| Sólides | 28.650,00 | já cortada em 14/08; resta R$ 790,70/mês de assinatura |
| Portte Contábil | 2.690,03 | sai com a contabilidade própria |
| tratamento odontológico | 4.625,00 | é do dono, não da empresa — vai para `2.1.5.01` |
| advogados (mensalidade de 05/2025) | 3.000,00 | é dívida da Eletrônica, paga pela Patrimonial |

Os dois últimos não são corte de despesa: são **reclassificação**. O dinheiro sai igual, mas
sai da conta certa — e numa DRE que um banco vai ler, "tratamento odontológico" numa empresa
de portaria atrai pergunta.

## D6 — Laranjeiras: o mesmo mês faturado quatro vezes [DECISÃO · dono + contador]

Junho foi registrado no fisco **4 × R$ 42.544,50 = R$ 170.178,00** para uma mensalidade de
R$ 42.544,50: notas 1, 2 e 3 da Patrimonial (25/06, em 21 minutos, descrição idêntica — três
tentativas de correção que ficaram todas válidas) mais a nota 109 da Eletrônica (09/07),
que foi a que o condomínio pagou.

Receita fantasma **infla o RBT12**, que é o que acelera a subida da alíquota de D2. Pagou-se
DAS sobre faturamento que não existiu **e** chegou-se mais rápido na faixa cara. Ação:
cancelar as notas indevidas e retificar o PGDAS de 06/2026.

## D7 — A Eletrônica é empresa de segurança ou a casa do produto? [DECISÃO · dono]

Ela faturou R$ 13.300 em agosto e gastou R$ 31.454 para existir. Dentro disso, R$ 11.970/mês
são os PJs que desenvolvem o Conecta PRO. **Não tem folha desde junho** — zero holerites — e
os 7 "ativos" no cadastro são 5 PJs de TI, um colaborador de teste e o próprio dono
registrado como *"AGENTE DE PORTARIA / candidato"*.

Faturando os 4 contratos ativos ela vai a −8,1%. Só fica positiva (+33,0%) se o custo do ERP
sair da operação de segurança. Isso é uma decisão sobre **o que a Eletrônica é**, e ela
governa se a tarefa C4 (segregar o custo de P&D) é contabilidade ou reorganização.

---

# Parte II — As tarefas de código

**Arquitetura:** tudo que é decisão fiscal sai de constante no código e vai para linha da
tabela `empresas` ou de uma tabela de parâmetros por CNPJ, lida por TODOS os leitores —
inclusive os gatilhos do banco. O padrão já foi estabelecido em 26/09 com
`empresas.corte_contabil`, lido pelo Python e pelo `fn_bloqueia_periodo_fechado`: **dois
leitores, um fato.**

**Stack:** FastAPI + SQLAlchemy + PostgreSQL · scripts de vigia em `backend/scripts/qa/` ·
oráculos em `backend/scripts/orq/` · deploy blue/green.

## Estrutura de arquivos

| arquivo | responsabilidade |
|---|---|
| `backend/modules/financial/services/simulador_regime.py` | **criar** — compara Simples × Presumido × Real por empresa, com as alíquotas certas de cada uma |
| `backend/modules/financial/services/parametros_fiscais.py` | **criar** — fonte única dos parâmetros por CNPJ (substitui os dicts espalhados) |
| `backend/modules/financial/services/lalur_service.py` | **criar** — Parte A e Parte B |
| `backend/modules/financial/services/ledger_auto_service.py` | modificar — ler parâmetros em vez de constante |
| `backend/scripts/qa/checar_contrato_sem_nota_no_mes.py` | **criar** — vigia do faturamento |
| `backend/scripts/orq/test_oraculo_c8_simulador_regime.py` | **criar** — oráculo do simulador |

---

## Tarefa C1 — Simulador de regime tributário por empresa [CÓDIGO]

**Por quê agora:** a decisão D2 tem prazo (31/01/2027) e hoje é feita numa planilha de
terceiro que **usa a alíquota errada** para esta casa — a aba `REAL` da planilha do curso
aplica PIS 1,65% e COFINS 7,6% (não-cumulativos), quando vigilância e limpeza são 0,65% e
3,00% cumulativos por lei. Quem decidir por aquela planilha decide errado por 5,6 pontos.

**Arquivos:**
- Criar: `backend/modules/financial/services/simulador_regime.py`
- Criar: `backend/scripts/orq/test_oraculo_c8_simulador_regime.py`

**Interfaces:**
- Consome: `empresas` (regime, anexo, ISS, RAT), `accounting_entries` (receita e despesa
  por competência), `hr_payslips` (folha).
- Produz: `simular(empresa_id, competencia) -> dict` com uma entrada por regime, cada uma
  com `carga_total`, `pct_receita` e a abertura por tributo.

- [ ] **Passo 1 — escrever o oráculo, que falha**

O oráculo afirma a REGRA, com os dois pontos medidos em 26/09 como âncora:

```python
# As duas guias REAIS da Patrimonial, cada uma numa faixa diferente do Anexo IV.
# Se o simulador reproduz as duas, a tabela e a fórmula estão certas.
CASOS = [
    # (competência, receita bruta, DAS real da guia, faixa esperada)
    ("2026-07", 255400.06, 17048.87, 2),
    ("2026-08", 262161.56, 18399.33, 3),
]
for comp, receita, das_real, faixa in CASOS:
    r = simular(PATRIMONIAL, comp)["simples"]
    assert abs(r["das"] - das_real) < 1.00, f"{comp}: {r['das']} != {das_real}"
    assert r["faixa"] == faixa

# A regra que mais importa: no Anexo IV a CPP patronal fica FORA do DAS.
assert simular(PATRIMONIAL, "2026-08")["simples"]["cpp_dentro_do_das"] is False

# E a que a planilha do mercado erra: vigilância no Lucro Real é CUMULATIVA.
real = simular(ELETRONICA, "2026-08")["lucro_real"]
assert real["pis_aliquota"] == 0.0065 and real["cofins_aliquota"] == 0.0300
```

- [ ] **Passo 2 — rodar e ver falhar**

`docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_c8_simulador_regime.py`
Esperado: `ModuleNotFoundError: simulador_regime`.

- [ ] **Passo 3 — implementar o mínimo**

A tabela do Anexo IV **só até a 5ª faixa** (a 6ª está em aberto, ver D2), e a alíquota
efetiva pela fórmula oficial:

```python
#: Anexo IV — (teto do RBT12, alíquota nominal, parcela a deduzir).
#: Conferido por dois caminhos independentes em 26/09/2026: as guias reais de 07 e 08/2026
#: caem em faixas DIFERENTES (2 e 3) e a fórmula fecha nas duas.
#: A 6ª faixa está AUSENTE de propósito: as fontes dão dedução de R$ 828.000, o que faria a
#: alíquota CAIR de 16,89% para 10,00% ao cruzar R$ 3,6 mi. Curva progressiva não cai.
#: Enquanto não for confirmada na fonte oficial, o simulador RECUSA RBT12 acima de 3,6 mi
#: em vez de devolver número — recusar é honesto, chutar não é.
ANEXO_IV = [
    (180_000, 0.045, 0),
    (360_000, 0.090, 8_100),
    (720_000, 0.102, 12_420),
    (1_800_000, 0.140, 39_780),
    (3_600_000, 0.220, 183_780),
]

def aliquota_efetiva(rbt12: float) -> tuple[float, int]:
    for i, (teto, nominal, deduzir) in enumerate(ANEXO_IV, start=1):
        if rbt12 <= teto:
            return (rbt12 * nominal - deduzir) / rbt12, i
    raise FaixaNaoConfirmadaError(
        f"RBT12 de R$ {rbt12:,.2f} cai na 6ª faixa, cuja parcela a deduzir não foi "
        "confirmada na fonte oficial — ver D2 do plano de 26/09/2026."
    )
```

- [ ] **Passo 4 — rodar e ver passar**

Esperado: `TOTAL desvios C8: 0`.

- [ ] **Passo 5 — commit**

```bash
git add backend/modules/financial/services/simulador_regime.py \
        backend/scripts/orq/test_oraculo_c8_simulador_regime.py
git commit -F mensagem.txt   # número antes/depois, decisão respeitada, o que NÃO foi feito
```

---

## Tarefa C2 — Vigia do contrato ativo sem nota no mês [CÓDIGO]

**Por quê:** o Green Hills tem contrato ativo desde 01/09 com CNPJ, valor e status corretos,
e **nunca gerou uma nota**. Não falta dado — falta quem avise. R$ 22.100/mês invisíveis.

**Arquivos:**
- Criar: `backend/scripts/qa/checar_contrato_sem_nota_no_mes.py`
- Modificar: `backend/scripts/qa/checar_regressao.py` (registro)
- Modificar: `docs/ARSENAL_OPERACAO.md` (linha na tabela)

- [ ] **Passo 1 — provar que a trava que já existe NÃO pega este caso**

`checar_contrato_vs_faturado.py` existe e devolve 13 pistas. Rodar e verificar se o Green
Hills está entre elas. **Se estiver, esta tarefa morre e vira um ajuste naquela.** Se não
estiver, o passo 2 documenta por quê.

- [ ] **Passo 2 — escrever o caçador**

Linha canônica: `TOTAL: <n> contrato(s) ativo(s) sem nota na competência`.
Regra: contrato com `status='active'`, `start_date <= fim da competência`, `monthly_value > 0`,
e nenhuma NFS-e de produção não cancelada para o CNPJ do tomador naquela competência.
Agrupar por empresa e somar o valor — o número que sai é dinheiro não faturado.

- [ ] **Passo 3 — provar que sabe mudar de resposta**

Emitir (em transação revertida) uma nota fictícia para o Green Hills e verificar que o
caçador cai de N para N−1; reverter e verificar que volta a N. **Trava que não muda com o
dado não mede — afirma.**

- [ ] **Passo 4 — registrar e commitar**

---

## Tarefa C3 — Segregar o custo de P&D do Conecta PRO [CÓDIGO + depende de D7]

**Por quê:** a conta `5.2.1.02 Serviços de TI / ERP` existe no plano com **zero lançamentos
desde sempre**, enquanto R$ 11.970/mês de PIX aos PJs de desenvolvimento estão em
`5.1.1.03 Vale Refeição / Alimentação`. Controle contábil segregado de P&D é pré-requisito
da Lei do Bem (Lei 11.196/05) — que a Eletrônica não pode usar hoje (exige lucro tributável)
mas poderá quando voltar ao lucro, **e o benefício não é reivindicável retroativamente sem a
documentação**.

**Arquivos:**
- Criar: `backend/scripts/reclassificar_custo_pd.py` (um passo, idempotente, com backup)
- Criar: `backend/scripts/qa/checar_pd_sem_segregacao.py`

**Bloqueio:** depende de D7. Se a Eletrônica for reorganizada, a reclassificação muda de
empresa antes de mudar de conta. **Não executar antes da decisão.**

- [ ] **Passo 1 — identificar por CPF/CNPJ, não por valor**

Os PJs de TI são identificáveis em `employees` por `cargo` (DEV, Suporte, Técnico
Mantenedor) e `status='pj_ativo'`. Casar o `counterparty_document` da `bank_transactions`
com o CPF deles é prova; casar por valor não é.

- [ ] **Passo 2 — backup, reclassificar, medir antes/depois**

```sql
CREATE TABLE backup_reclass_pd_AAAAMMDD AS SELECT * FROM accounting_entries WHERE id IN (...);
UPDATE accounting_entries SET conta_debito = '5.2.1.02' WHERE id IN (...);
```

- [ ] **Passo 3 — caçador que vigia a recaída**

Pagamento a PJ com cargo de TI que caia em conta diferente de `5.2.1.02` acusa.

---

## Tarefa C4 — Grupo de receita não operacional no plano de contas [CÓDIGO]

**Por quê:** todas as receitas estão em `4.1 Receitas Operacionais`. **Não existe grupo de
receita não operacional**, e é justamente essa separação que diz se o negócio deve existir —
a lição do material estudado em 26/09, já implementada no caçador
`checar_operacao_que_nao_se_paga.py`, que hoje mede a operação por aproximação (pelo que ela
fatura em serviço) porque o plano não permite medir direito.

Hoje não distorce, porque aporte de sócio entra como passivo (`2.1.5.01`). Mas uma venda de
bem ou indenização somaria com faturamento de portaria sem ninguém ver.

**Arquivos:**
- SQL de dados: criar `4.3 Receitas Não Operacionais` com analíticas
- Modificar: `backend/scripts/qa/checar_operacao_que_nao_se_paga.py` (passar a excluir 4.3
  em vez de aproximar por 4.1.1)

**De quebra:** aposentar as quatro contas `EXPENSE` numeradas na faixa de receita
(`4.1.2 FGTS`, `4.1.3 INSS Patronal`, `4.2.1 Software`, `4.2.2 Infraestrutura`) — todas com
**zero movimento**, medido em 26/09. São a armadilha que faz alguém ler o plano pelo número.

---

## Tarefa C5 — O encargo que a precificação não conhece [CÓDIGO · a mais cara do plano]

**A descoberta, medida em 26/09/2026.** `backend/modules/financial/services/encargos.py:25`
documenta a própria origem:

> *"Simples Anexo III (Patrimonial) — **CONFIRMADO Portte (Jordan, 20/07)**: NÃO há cobrança
> dos 20% patronal (CPP fica DENTRO do DAS, junto com terceiros e RAT).
> Encargo = LR 0,6124 − CPP 20% − terceiros 5,8% − RAT 3% = **0,3244**"*

A guia do DAS de 07 e 08/2026 desmente: INSS de R$ 171,06 e depois nenhuma linha. **É Anexo
IV, e no Anexo IV a CPP e o RAT ficam FORA do DAS.**

| | composição | total |
|---|---|---|
| Lucro Real (Eletrônica) | INSS 20 + FGTS 8 + RAT 3 + terceiros 5,8 + férias 11,11 + 13º 8,33 + rescisão 5 | **61,24%** ✓ |
| Anexo III — **o que o código usa** | FGTS 8 + férias 11,11 + 13º 8,33 + rescisão 5 | **32,44%** |
| **Anexo IV — o real** | o anterior **+ CPP 20 + RAT 3** (terceiros não é devido no Simples) | **55,44%** |

**23 pontos percentuais de folha fora do preço.** Sobre a folha de agosto
(R$ 106.577,20): **R$ 24.512,76/mês** — que é, ao centavo, a CPP patronal medida na guia.
**A precificação não conhece o tributo que a declaração também não conhece.**

### A correção que isto impõe ao retrato deste plano

A margem operacional de 08/2026 que abre este documento (+2,1%) **não reconhece a CPP**.
Com ela reconhecida:

```
resultado operacional 08/2026 medido       +5.618,80   (+2,1%)
CPP patronal (20% + RAT 3% sobre a folha) −24.512,76
─────────────────────────────────────────────────────
resultado operacional REAL                −18.893,96   (−7,2%)
```

Os R$ 84.709,90 de crédito de retenção parados em `1.1.3.02` **são exatamente a CPP
acumulada que nunca virou despesa**. O caixa não deve — os clientes já retiveram. Mas o
preço dos contratos foi montado como se o tributo não existisse.

**As alavancas do plano ainda cobrem:** −18.893,96 + 38.965,03 (custos que saem) +
10.038,50 (contratado não faturado) = **+30.109,57 (+11,1%)**. Com a migração de regime,
+49.190 (**+18,1%**). Mas **contrato novo precisa nascer a 55,44%**, não a 32,44%.

**Arquivos:**
- Modificar: `backend/modules/financial/services/encargos.py`
- Modificar: `backend/modules/financial/controllers/precificacao_controller.py:29,39,113`
- Modificar: `backend/modules/financial/controllers/custeio_controller.py:29,208`
- Criar: `backend/scripts/orq/test_oraculo_c9_encargo_por_anexo.py`

- [ ] **Passo 1 — oráculo que afirma a regra, não o número**

```python
# A regra: no Anexo IV a CPP patronal e o RAT ficam FORA do DAS e entram no encargo.
# A prova de que é Anexo IV vem da GUIA, não do cadastro: composição do DAS sem
# linha de INSS relevante (detalhes_json->composicao->INSS < 10% da guia).
assert encargo_pct(regime="simples_nacional", anexo="IV") == pytest.approx(0.5544, abs=1e-4)
assert encargo_pct(regime="simples_nacional", anexo="III") == pytest.approx(0.3244, abs=1e-4)
assert encargo_pct(regime="lucro_real") == pytest.approx(0.6124, abs=1e-4)

# E a regra que impede o defeito de voltar: anexo DESCONHECIDO não cai em default.
with pytest.raises(AnexoNaoDeterminadoError):
    encargo_pct(regime="simples_nacional", anexo=None)
```

O último `assert` é o que mais importa. O defeito de hoje **não foi um número errado** — foi
um default silencioso que respondeu quando não sabia. Recusar é honesto.

- [ ] **Passo 2 — rodar, ver falhar** (`encargo_pct` hoje aceita só `regime`)

- [ ] **Passo 3 — implementar**

`encargo_pct(regime, anexo)` passa a exigir o anexo quando o regime é Simples, e os três
call-sites param de passar a string literal `"simples_nacional"` — passam o `empresa_id` e
o serviço resolve regime e anexo pela tabela `empresas`.

- [ ] **Passo 4 — medir o impacto em cada contrato ativo, SEM alterar preço**

Relatório, não ação: para os 9 contratos ativos da Patrimonial, qual seria o preço a 55,44%
e qual é o preço hoje. **Reajustar contrato é conversa com condomínio, não UPDATE.**

- [ ] **Passo 5 — commit com o número antes/depois**

**Bloqueio:** o valor 55,44% depende de D1 e D3. Se o advogado disser que é Anexo III (e a
guia estiver errada), o número volta a 32,44%. **O que NÃO depende de decisão é o
`AnexoNaoDeterminadoError`** — esse entra já.

---

## Tarefa C6 — O cronograma que não lê contrato [CÓDIGO]

**A causa-raiz do R$ 196.175,96, medida.** O sistema **não decide o que faturar por
contrato**. A única fonte é a tabela `nfse_cronograma`, lida por `propor()` em
`backend/modules/fiscal/services/nfse_lote.py:423`, que faz um único
`SELECT * FROM nfse_cronograma WHERE competencia = :c` (l.440) e **nunca toca em
`contracts`**.

A tabela é populada por `_ensure()` (l.329) a partir de uma constante Python hardcoded,
`_SEED_2026_09` (l.119), transcrita à mão de uma planilha `.ods` que o dono subiu em 24/09.
**Só existe seed de setembro. Outubro não tem uma linha.** Em 01/10 o faturamento inteiro
das duas empresas depende de alguém lembrar de transcrever outra planilha.

Nenhuma rotina agendada emite nota — a única task fiscal de NFS-e é
`fiscal.conciliar_nfse_com_fisco` às 05:30, que só faz GET e declara na docstring:
*"Não emite nota. Nenhuma."*

**Por que o Green Hills não saiu:** a linha 12 do cronograma descreve o contrato **velho**
(`CTR-2026-00006`, Eletrônica, R$ 500,00, hoje `terminated`). Os R$ 22.100 da Patrimonial
**não existem em lugar nenhum do caminho de emissão**. Nada falta no contrato — CNPJ
`08063476000183`, valor, `active` desde 01/09. Falta o caminho.

**E o contas-a-receber tem o mesmo buraco, por outro motivo:**
`financial.gerar_recebiveis_mes` roda `crontab(day_of_month=1)` (`celery_app.py:333`) e
filtra `WHERE c.status='active'` uma vez por mês. O `CTR-2026-00019` foi assinado em
**11/09**. **Contrato assinado depois do dia 1 nunca ganha recebível naquele mês** — o do
Green Hills em setembro é R$ 500,00, do contrato velho.

**Arquivos:**
- Modificar: `backend/modules/fiscal/services/nfse_lote.py` — `propor()` passa a derivar de
  `contracts` ativos e usar `nfse_cronograma` como **exceção declarada**, não como fonte
- Modificar: `backend/celery_app.py` — recebível deixa de ser mensal no dia 1
- Criar: `backend/scripts/qa/checar_cronograma_vs_contrato.py`

- [ ] **Passo 1 — inverter a fonte**

O contrato ativo passa a ser a fonte; o cronograma vira a lista de **exceções** (valor
diferente do contrato, empresa diferente, não faturar este mês), cada uma com motivo
escrito. Hoje é o contrário, e por isso um contrato novo é invisível.

- [ ] **Passo 2 — oráculo**

```python
# A regra: todo contrato ATIVO com valor > 0 e vigência na competência aparece na proposta.
propostas = propor(competencia="2026-09")
ativos = contratos_ativos_na_competencia("2026-09")
assert {c.id for c in ativos} <= {p.contrato_id for p in propostas}, \
    "contrato ativo que não virou proposta — foi assim que o Green Hills sumiu"
```

- [ ] **Passo 3 — o recebível deixa de depender do dia 1**

Rodar diariamente e criar o recebível do mês para contrato que **passou a estar ativo**
desde a última execução. Idempotente por `(contrato, competência)`.

- [ ] **Passo 4 — caçador da divergência cronograma × contrato**

Linha do cronograma cujo valor, empresa ou vigência não bate com o contrato acusa. Hoje
haveria pelo menos 3: Green Hills (R$ 500 × R$ 22.100), linha 2 (diz Eletrônica, a nota
saiu pela Patrimonial) e linhas 1 e 9 com `empresa_cnpj` **vazio** — que a rota de emissão
recusa com `EMPRESA_SEM_FONTE`.

---

## Tarefa C7 — Parâmetros fiscais por empresa: a fonte única [CÓDIGO]

**O inventário, medido em 26/09.** Cerca de 40 constantes codificam decisão fiscal por
empresa. As piores:

| defeito | onde | efeito |
|---|---|---|
| **4 cópias divergentes** do encargo de folha | `encargos.py:19`, `pricing_cct.py:30`, `pricing_engine.py:107` (Lucro **Presumido**), `cct_pricing_source.py:28` | três cargas tributárias diferentes para o mesmo cálculo |
| **3 cópias divergentes** da tabela do Anexo III | `crm/regime_tributario.py:34` (0,1320), `tax_calculator.py:22` (0,135), `empresa_service.py:70` (0,135) | LC 123 diz 13,5%; uma das três está errada |
| **tabela do Anexo IV não existe** em lugar nenhum | — | a empresa que é Anexo IV não tem tabela |
| `crm_pricing_params` **sem `empresa_id`** | tabela global, PK = `chave` | carga de Lucro Real (CPP 20% + terceiros 5,8%) aplicada a **79 funcionários do Simples** |
| `PADRAO_REGIME["lucro_real"]` diz PIS/COFINS **não-cumulativo** | `produto_fiscal.py:69` | **contradiz** `REGIME_PIS_COFINS` (`sped_contribuicoes_service.py:71`), que diz cumulativo para o MESMO CNPJ |
| RAT **2%** no manager, **3%** em toda precificação | `fgts_inss_manager.py:740` × 6 arquivos | número diferente conforme quem pergunta |
| **6 call-sites ainda leem `CORTE_CONTABIL` global** | `cobertura_sistema.py:54`, `reconciliation_service.py:675`, `regras.py:1258,1416,1496,1577` | o defeito que custou junho, agora na camada de LEITURA |
| `obligations_controller.py:38` tem `_CORTE = date(2026,8,1)` próprio | — | cópia independente que não lê `empresas.corte_contabil` |
| `empresas.rbt12` é **NULL nas duas** | `crm/regime_tributario.py:159` | a precificação do Simples **RECUSA hoje** com `RegimeNaoCadastrado` |
| `empresas.anexo_simples = 'III'` | banco | **conflita com o Anexo IV que as guias provam** — ver D1/D3 |

**Arquivos:**
- Criar: `backend/modules/financial/services/parametros_fiscais.py`
- Criar: colunas em `empresas`: `anexo_simples` (já existe, corrigir valor), `rat`, `fap`,
  `regime_pis_cofins`, `aliquota_iss`, `codigo_fpas`, `rbt12`
- Modificar: os ~40 call-sites, **um por vez, cada um com sua medição antes/depois**

- [ ] **Passo 1 — a fonte única, e a recusa**

```python
def parametro(empresa_id: str, nome: str):
    """Parâmetro fiscal DESTA empresa. Sem valor cadastrado, LEVANTA — não devolve default.

    O default silencioso é o defeito desta casa: `encargo_pct` devolvia o número do Lucro
    Real para o Simples sem avisar, e o corte da Eletrônica apagou junho da Patrimonial.
    Um parâmetro fiscal que não se sabe é uma pergunta ao contador, não um chute.
    """
```

- [ ] **Passo 2 — migrar UM call-site, medindo**

Começar por `cobertura_sistema.py:54` (o corte). Medir a cobertura da Patrimonial antes e
depois: hoje ela ignora junho e julho por causa do corte da irmã.

- [ ] **Passo 3 — caçador que impede a recaída**

Procura no código por alíquota literal (`0.20`, `0.058`, `1.65`, `7.60`, `0.6124`) em
arquivo de `modules/` fora de `parametros_fiscais.py` e acusa. Linha canônica:
`TOTAL: <n> alíquota(s) fixa(s) fora da fonte única`.

- [ ] **Passo 4 — os 39 restantes, um commit cada**

Não fazer em lote. Cada call-site tem um efeito diferente e uma medição própria.

---

## Tarefa C8 — LALUR: Parte A e Parte B [CÓDIGO]

### Primeiro, uma correção ao que eu afirmei antes

Eu disse, mais cedo em 26/09, que *"a estratégia 12 do Multiplicador é a carta certa"* para a
negociação com a PGFN. **Estava errado**, e a pesquisa na fonte primária mostra por quê — três
razões independentes, cada uma suficiente sozinha:

1. **A Portaria PGFN 6.757/2022, art. 37**, veda expressamente: *"É vedada a utilização de
   créditos decorrentes de prejuízo fiscal e de base de cálculo negativa da CSLL **nas
   transações por adesão e na transação individual simplificada**."* A dívida da Eletrônica
   foi feita **por adesão** (Edital PGDAU 11/2025).
2. **O piso de valor.** O art. 46 exige dívida **acima de R$ 1 milhão** para a individual
   simplificada e **acima de R$ 10 milhões** para a individual plena. A dívida é de
   **R$ 582.262,83**. Não alcança nenhuma das duas.
3. **O estoque não existe.** A Eletrônica está em Lucro Real desde 01/2026, e **todos os seis
   SISPAR são "Dívida Ativa — Simples Nacional"**. Nos anos do Simples não se apura prejuízo
   fiscal. O estoque possível começa em 2026 — e hoje não está escriturado em lugar nenhum.

**E há uma armadilha de leitura no próprio recibo de adesão:** o "70%" que aparece lá é o
**teto de desconto do § 3º da Lei 13.988/2020** (benefício de ME/EPP). O 70% do **inciso IV**
é outro instituto — a parcela do saldo que sobra *depois* do desconto e que poderia ser paga
com prejuízo fiscal. Confundir os dois faz parecer que o benefício já está no acordo. **Não
está.**

### Então por que construir o LALUR

Porque o prejuízo fiscal tem outro uso, e esse é real, imediato e está se perdendo:

> **reduzir o IRPJ e a CSLL futuros em até 30% do lucro ajustado, sem prazo de validade**
> (Lei 9.065/1995, art. 15 e 16; trava confirmada pelo STF no RE 591.340)

Medido no razão da Eletrônica em 2026: **T1 fechou com lucro de R$ 48.383,04 e gerou imposto;
T2 fechou com prejuízo de R$ 88.926,17 que não desfaz o imposto de T1** — cada trimestre é
período de apuração fechado — **e que hoje não está sendo carregado para lugar nenhum.**

E o parágrafo único do art. 15 é a sentença que decide tudo: o direito à compensação *"somente
se aplica às pessoas jurídicas que **mantiverem os livros e documentos comprobatórios**"*.
**Prejuízo sem livro é prejuízo que a PGFN glosa.**

### O defeito atual, medido

`apuracao_lucro_real_service.py:102-112` chama de `prejuizo_fiscal_compensavel` o valor
`-lucro` do período. Quatro defeitos:

| # | defeito |
|---|---|
| 1 | **não é estoque, é foto** — não soma períodos anteriores, não subtrai o compensado, **não persiste** (não há INSERT, não há tabela) |
| 2 | **não é fiscal, é contábil** — sem Parte A, prejuízo fiscal ≠ prejuízo contábil por definição |
| 3 | **não há compensação** — a palavra não aparece no arquivo; logo não há onde a trava de 30% se aplicar |
| 4 | **duas respostas na mesma tela** — soma dos trimestres R$ 102.400,33 × chamada anual R$ 54.017,29. O card de `_fin_contabil.py:408` mostra o anual; a régua ao lado mostra os trimestres |

O serviço **sabe** que não é LALUR — a docstring l.10 diz *"o LALUR é do contador"*. O problema
é o nome do campo prometer o que o valor não entrega.

**Arquivos:**
- Criar: `backend/modules/financial/services/lalur_service.py`
- Criar: tabelas `lalur_conta_b` e `lalur_lancamento`, view `v_lalur_saldo_b`
- Modificar: `apuracao_lucro_real_service.py` — renomear o campo enganoso e consumir o LALUR
- Criar: `backend/scripts/orq/test_oraculo_c10_lalur.py`

### O desenho, espelhando o Bloco M da ECF

**Duas tabelas e uma view.** Saldo **não é coluna** — é soma. O próprio manual da ECF descreve
o `M500` como *"gerado pelo sistema a partir do saldo inicial e das movimentações"*; a RFB não
guarda saldo, calcula. Esta casa já pagou caro por duas colunas para o mesmo fato.

- **`lalur_conta_b`** (espelha `M010`): `empresa_id`, `codigo`, `descricao`,
  `tributo` (`I`=IRPJ · `C`=CSLL — **contas separadas, a ECF valida separado**),
  `natureza` (`D`/`C`), `cod_pb_rfb`, `competencia_criacao`, `data_limite`,
  `saldo_inicial`. Para a Eletrônica o saldo inicial é **0,00**: Lucro Real começou em 01/2026.
  São duas linhas: `PF-2026` (IRPJ) e `BCN-2026` (CSLL).
- **`lalur_lancamento`** (espelha `M300`+`M305`+`M350`+`M355`+`M410`): `competencia`,
  `tributo`, `tipo` (`A` adição · `E` exclusão · `P` compensação · `B` só Parte B),
  `codigo_rfb`, `valor` (sempre positivo; o sinal é o tipo), `conta_b_id`
  (**obrigatório quando `tipo in ('P','B')`** — compensação sem origem é compensação de nada),
  `sinal_parte_b`, `historico` (**not null** — adição sem histórico é indefensável em
  fiscalização), `accounting_entry_id`, `documento_ref`, **`origem`**.

- [ ] **Passo 1 — a coluna `origem` é a linha divisória**

```sql
origem varchar(12) not null default 'contador'
       check (origem in ('contador','automatico'))
```

**Só três coisas podem ser `automatico`**, porque só elas são aritmética e não juízo: a CSLL
do próprio período, o prejuízo do período (`M410` com indicador `PF`/`BC`) e a compensação
calculada pela trava. **Todo o resto é `contador`, sem exceção.**

O Anexo I da IN 1700 tem **202 códigos de adição** e o Anexo II tem **144 de exclusão**.
Nenhum é derivável do plano de contas, porque a pergunta não é contábil: `A.069` é *"despesas
que não sejam consideradas **necessárias** à atividade"* — "necessária" não é campo.

**Três casos vivos no razão da Eletrônica que provam isso:**

| conta | valor 2026 | o juízo |
|---|---|---|
| `5.1.1.05` provisões de férias e 13º | 84.285,15 | o art. 13, I **veda** provisões mas **excetua exatamente essas duas**. Um sistema que adicionasse por regra de conta erraria em R$ 84 mil |
| `5.2.3.01` despesas financeiras | 10.370,40 | dentro, **oito saques em Banco24Horas** de R$ 500 a R$ 1.000. Tarifa é dedutível; saque sem documento é o caso-escola do `A.069` |
| `5.2.2.04` DAS/parcelamento | 2.699,58 | **um lançamento que precisa virar três**: principal dedutível, multa no `A.154`, juros de mora dedutíveis. A abertura está no DARF, não no razão |

- [ ] **Passo 2 — a trava de 30%, como regra e não como coluna**

```
ajustado = lucro_do_razão + Σ(tipo='A') − Σ(tipo='E')     [por período, por tributo]

se ajustado > 0:
    teto       = ajustado × 0,30          ← Lei 9.065/95 art. 15 e 16
    disponível = saldo da conta B (view, na data)
    compensa   = min(teto, disponível, compensacao_solicitada)
    lucro_real = ajustado − compensa
senão:
    grava lalur_lancamento tipo='B' com indicador PF/BC (é o M410)
```

Três regras que caem fora do SQL:

1. **A base dos 30% é o ajustado, nunca o lucro do razão.** Aplicar 30% sobre o razão produz
   um número que parece certo e está errado.
2. **Cada trimestre é período fechado.** O prejuízo de T2 **não retroage** sobre o imposto de
   T1. Qualquer tela que some o ano e mostre "prejuízo de R$ 54.017,29" esconde isso.
3. **Compensar é opção do contribuinte**, não automatismo — daí o `compensacao_solicitada`
   como parâmetro, não como coluna.

- [ ] **Passo 3 — fila de revisão, não formulário em branco**

No fechamento da competência o sistema lista as despesas do período (mesma query das l.68–83
que já existe) e pede **uma decisão por linha**: dedutível / adição com código do Anexo I /
abrir em partes. **Oferece a lista dos 202, não sugere um.** A diferença entre oferecer e
sugerir é a diferença entre um erro que alguém revisa e um erro que ninguém vê.

**Linha não decidida NÃO vira "dedutível" — vira pendência que impede fechar a competência.**
Nesta casa o estado não previsto sempre falhou aberto; aqui falhar aberto é subtributar.

- [ ] **Passo 4 — oráculo**

```python
# A regra da trava: nunca compensa mais que 30% do AJUSTADO, nem mais que o saldo.
r = apurar_lucro_real(ELETRONICA, "2026-T3", compensacao_solicitada=None)
assert r["compensacao"] <= r["lucro_ajustado"] * 0.30 + 0.01
assert r["compensacao"] <= saldo_parte_b(ELETRONICA, "I", "2026-09")

# A regra que o campo antigo quebrava: trimestre fechado não retroage.
assert apurar_lucro_real(ELETRONICA, "2026-T1")["irpj"] > 0, \
    "T1 deu lucro e gerou imposto; o prejuízo de T2 NÃO o desfaz"

# E a que impede o número fantasma: sem Parte A, não se afirma lucro real.
with pytest.raises(ParteANaoFechadaError):
    apurar_lucro_real(ELETRONICA, "2026-T3", exigir_parte_a=True)
```

- [ ] **Passo 5 — renomear o campo que promete o que não entrega**

`prejuizo_fiscal_compensavel` → `prejuizo_contabil_do_periodo`, com a observação na tela
dizendo o que falta. O card de `_fin_contabil.py:408` passa a mostrar, ao lado, **a contagem
de lançamentos sem decisão**: um estoque com 40 despesas não revisadas não é estoque, é
rascunho, e tem de se apresentar como tal.

**Prazo real:** a ECF do ano-calendário 2026 vence em **julho/2027**, e **escrituração não se
faz retroativamente sem substituição**. O prejuízo de T2/2026 (R$ 88.926,17) existe hoje e se
perde se o livro não existir.

**Ressalva de fonte:** o manual consultado é o do **Leiaute 10** (ADE Cofis 59/2023,
ano-calendário 2023). Os registros do Bloco M são estáveis há anos, mas **os números de linha
do M300 (173/174/347/348) têm de ser reconferidos contra o manual do ano-calendário 2026**
antes da implementação.

---

# Parte III — A ordem

Não é a ordem de dificuldade. É a ordem de **dependência**: fazer fora dela produz trabalho
que precisa ser refeito.

## Semana 1 — o que não depende de ninguém

| # | ação | valor | quem |
|---|---|---|---|
| 1 | **Emitir as 6 linhas do cronograma de setembro** | **R$ 174.075,96** | operação — 6 chamadas em `aa4-emitir-do-cronograma`, com `dry_run=nao` |
| 2 | Inserir a linha do Green Hills no cronograma (R$ 22.100, Patrimonial) e emitir | **R$ 22.100,00** | operação |
| 3 | Emitir os 4 contratos ativos da Eletrônica | **R$ 15.800,00** | operação |
| 4 | Ativar ou encerrar o `CTR-2026-00024` (Kopenhagen, R$ 40.612, `draft` desde 10/09) | R$ 40.612/mês | dono |

**Antes de emitir, três coisas a conferir** (medidas em 26/09): as linhas 1 e 9 do
cronograma estão com `empresa_cnpj` **vazio** e a rota as recusa com `EMPRESA_SEM_FONTE`;
a linha 2 diz Eletrônica mas a nota já saiu pela Patrimonial; e o recebível do Mirante é
R$ 13.561,50 contra um contrato de R$ 12.061,50.

**Total da semana 1: R$ 211.975,96**, sem contador, sem advogado, sem decisão fiscal.

## Semana 1 (paralelo) — a consulta que destrava tudo

**D1 ao tributarista.** Custa uma consulta e é o melhor dinheiro do mês: ela decide D2
(regime, prazo 31/01), D3 (classificação previdenciária), C5 (o encargo de 55,44% × 32,44%)
e C7 (o valor de `empresas.anexo_simples`).

## Semana 2 — parar de sangrar pelo mesmo lugar

| # | ação | efeito |
|---|---|---|
| 5 | **C6** — cronograma passa a derivar de contrato ativo | impede o próximo Green Hills |
| 6 | **C6** — recebível deixa de depender do dia 1 do mês | impede o próximo contrato assinado dia 11 |
| 7 | **C2** — caçador de contrato ativo sem nota na competência **corrente** | avisa antes de virar buraco |
| 8 | D5 — os quatro itens de custo saem (R$ 38.965,03/mês) | +14,3 pontos de margem |

**Sobre o item 7, e é uma lição:** a trava `checar_contrato_vs_faturado.py` **existe** e não
pegou o Green Hills, por duas razões independentes. A primeira é desenho consciente — ela
exclui o mês corrente porque *"acusar dia 10 que não faturou é alarme que ensina a ignorar o
painel"*. A segunda é que a cláusula `start_date <= :fim` foi adicionada **por causa do
Green Hills**, para matar um falso positivo em 25/09 — e a mesma linha que matou o falso
positivo cegou para o buraco verdadeiro. A trava nova precisa olhar o mês corrente sem
gritar cedo demais: a regra certa é **contrato ativo sem nota depois do dia de faturar**.

## Semana 3 em diante — depende de D1

| # | ação | depende de |
|---|---|---|
| 9 | **C5** — encargo por anexo, e o `AnexoNaoDeterminadoError` | D1 (o número); o erro entra já |
| 10 | **D3** — corrigir a classificação no eSocial, declarar a patronal | D1 |
| 11 | **D4** — compensar os R$ 84.709,90 de crédito | D3 |
| 12 | **C1** — simulador de regime | nada; alimenta D2 |
| 13 | **D2** — decidir o regime de 2027 | C1 + D1 |
| 14 | **C7** — parâmetros por empresa, 40 call-sites, um commit cada | D1 (o valor do anexo) |
| 15 | **D6** — cancelar as notas duplicadas do Laranjeiras, retificar o PGDAS de junho | dono |
| 16 | **D7** — decidir o que a Eletrônica é | dono |
| 17 | **C3** — segregar o custo de P&D | D7 |
| 18 | **C4** — grupo de receita não operacional | nada |

---

## Onde a margem termina

| etapa | Patrimonial |
|---|---|
| hoje, **com a CPP reconhecida** (08/2026) | **−7,2%** |
| + faturar o contratado | −3,5% |
| + os quatro cortes de D5 | **+11,1%** |
| − a curva do DAS (7,02% → 16,16%) | +2,0% |
| + migração de regime (se D2 assim decidir) | **+9,0%** |

| etapa | Eletrônica |
|---|---|
| hoje | **−136,5%** |
| + faturar os 4 contratos ativos | −8,1% |
| + custo do ERP sai da operação (D7) | **+33,0%** |

**O que o plano NÃO promete:** os 20,1% que apareceram no primeiro quadro deste documento
eram antes de reconhecer a CPP. Com ela, o teto realista da Patrimonial é **+11,1%** sem
mudar de regime e **~+9%** depois da curva do DAS — a migração é o que recupera. Preferi
corrigir o número no meio do plano a defender o primeiro.

---

## Autorrevisão

**Cobertura.** Cada frente que o dono pediu tem tarefa: sair do vermelho (semana 1 + D5),
aumentar lucratividade (C5, D2), parametrizar por CNPJ (C7), usar a lei a favor (D1–D4, C1).

**Números.** Todos medidos em 26/09/2026 com a fonte citada. Os que vieram de agente foram
**re-conferidos por mim** antes de entrar — o de encargos (C5) mudou de interpretação na
conferência e corrigiu o retrato de abertura.

**O que ficou sem tarefa, de propósito:** a dívida de R$ 582.262,83 da PGFN não está no
razão e **não há conta para ela no plano de contas**. Não criei tarefa porque os 31 PDFs no
sistema são guias de pagamento, não termos de adesão — não há documento que sustente o
lançamento. Fabricar passivo de seis dígitos a partir de um número que li num relatório meu
seria o oposto do que este plano defende.

**Risco maior do plano:** que as tarefas de código sejam feitas e as decisões não. Um
sistema correto sobre uma empresa irregular continua irregular — e mais caro de consertar,
porque agora tem código dependendo do parâmetro errado.
