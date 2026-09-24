# DGX AA6 — VA e VT por contrato: a dedução da base do INSS, com procedência

**Branch:** `dgx/aa6-va-vt-por-contrato` · **Data:** 24/09/2026 · **Módulo:** folha (tela no DP)
**Decisão que atende:** *«vamos deduzir vale-alimentação e vale-transporte antes de aplicar os 11%
em todas as notas que tiver cessão de mão de obra, isso é regra, vai nos possibilitar economizar»*
— Jordan Jesus, 24/09/2026, com o recorte *«essa regra só vale para cessão de mão de obra que
sempre terá nota fiscal de serviço emitida pela conecta patrimonial»*.

---

## §1 Estado antes — medido em produção (só leitura) em 24/09/2026

**O sistema não sabia o número.**

```
beneficio_entregas ........ 0 linhas
beneficio_entrega_itens ... 0 linhas
beneficio_linhas .......... 2 linhas (só a diária do VT: SINETRAM e SOLIDES, R$ 10,00/dia)
beneficio_tipos ........... 8 ativos (a regra existe, o dado por contrato não)
folha_beneficio_conferencia 108 linhas, só 08/2026 — 54 pessoas, VR R$ 18.832,00, VT R$ 2.090,00
                            e 43 das 54 linhas de VT em `sem_modalidade`
solides_benefit_orders .... 30 linhas — são PIX para a Sólides, sem quebra por pessoa nem por mês
```

**A armadilha, medida.** `folha_verba_espelho` tem «Desconto VT» (1010) e «Desconto VR» (1011).
São 4% e 1% do salário **do empregado**, não o custo pago pela empresa:

```
1010  Desconto VT   354 linhas  R$ 22.565,23  (01–07/2026)
1011  Desconto VR   351 linhas  R$  5.897,71  (01–07/2026)
```

Em 07/2026 o desconto do empregado soma **R$ 3.926,40** e o custo real do benefício apurado nesta
frente soma **R$ 28.388,00** — **7,2 vezes** maior. Deduzir pela folha de desconto faria o dono
pagar cerca de **R$ 2.690,78 a MAIS** de INSS naquele mês. O oráculo afirma isso por AST e por valor.

**As notas de agosto não deduziram nada.** As cinco DANFSe da Patrimonial retiveram 11% do bruto,
conferido ao centavo. O cronograma de setembro deduz em **3 das 8 linhas** da Patrimonial.

---

## §2 O que o DGX tem e nós não tínhamos

O pedido de benefício do DGX é por **pessoa × dias**, ligado ao posto. Aqui o benefício era
calculado por pessoa (frente 03, em paralelo cego) mas **nunca somado por contrato** — e a emissão
da nota não tinha a quem perguntar. Esta frente é o elo que faltava: `contrato × competência →
VA, VT, dias, unitário, fonte`.

---

## §3 O que foi feito

### Arquivos

| Arquivo | O quê |
|---|---|
| `backend/modules/people_management/folha/services/va_vt_contrato.py` | a regra: `apurar`, `efetivo`, `para_nota`, `texto_discriminacao`, `registrar_decisao`, `unitarios` |
| `backend/modules/operacional/controllers/redesign_builders/_dgx_aa6_va_vt.py` | 2 telas + 2 ações |
| `backend/modules/operacional/controllers/redesign_builders/departamento_pessoal.py` | plug (`# dgx aa6`) |
| `backend/modules/operacional/controllers/redesign_builders/_dp_grupos.py` | abas no grupo **Benefícios & Reembolsos** |
| `backend/scripts/orq/test_oraculo_aa6_va_vt.py` | oráculo |

### DDL que `_ensure` aplica em produção no 1º acesso

```sql
CREATE TABLE IF NOT EXISTS va_vt_contrato_decisao (
  id bigserial PRIMARY KEY,
  client_id uuid NOT NULL, competencia date NOT NULL,
  pessoas integer, va numeric(12,2), vt numeric(12,2),
  justificativa text NOT NULL, decidido_por varchar(120),
  decidido_em timestamptz NOT NULL DEFAULT now(),
  UNIQUE (client_id, competencia)
);
```
Uma tabela, só para a decisão do dono. Nada mais é criado, nada existente é alterado.

### Telas

- `/redesign/departamento-pessoal?t=va-vt-contrato` — **VA e VT por contrato**: por cliente e
  competência (3 últimas), pessoas, dias VA/VT, VA, VT, dedução, INSS 11%, estado e a procedência
  inteira. Por linha: **Texto da nota** (a discriminação legal pronta, pede o bruto) e
  **Sobrescrever** (o dono digita VA/VT/pessoas com justificativa obrigatória).
- `/redesign/departamento-pessoal?t=va-vt-efetivo` — **Efetivo por contrato**: as quatro fontes
  lado a lado (alocação · alocação antiga · escala · ponto), o contratado (`required_headcount`),
  o conciliado e **cada divergência nome a nome, com a causa provável**.

### A régua escolhida, e por quê

O dono, em 24/09: *«tem muita rotatividade, não só lá mas em todos os condomínios, sempre fica
defasado»*. Contagem de cabeças em tabela de alocação é justamente o dado que apodrece — e seria a
base de um número de imposto. Então **a apuração não parte de um efetivo**: parte de
**pessoa × dias de escala naquele posto × R$/dia da CCT**, e a contagem é consequência.

Três réguas medidas em 08/2026 contra o que o dono escreveu na nota (VA · VT):

| cliente | cronograma | **escala** | ponto (batida no posto) |
|---|---|---|---|
| Laranjeiras Village | 2.552 · 1.136 | **2.486 · 1.130** | 1.958 · 890 |
| Ideal Flores | 4.488 · 2.160 | **4.356 · 2.130** | 2.332 · 1.130 |
| Prime Arena | 1.804 · 880 | **2.288 · 1.140** | 1.496 · 730 |

**A escala vence para o VALOR.** O **ponto perde por um motivo medido**: 48% das batidas de
08/2026 não têm `posto_id` (1.794 de 3.420) — o ponto é a melhor evidência de PRESENÇA, mas hoje
não sabe dizer ONDE em metade dos casos.

**Para a CONTAGEM a régua é outra: escala ∪ ponto, dentro do vínculo.** Ela dá **13** no Ideal
Flores — exatamente o efetivo que o dono confirmou —, e nenhuma das outras acerta (`allocations`
14, `employee_alocacoes` 12, escala sozinha 11, cronograma 12). O oráculo trava esse 13.

---

## §4 A apuração contra os três números reais do cronograma

Competência **08/2026** (é o benefício que a nota de setembro discrimina):

| cliente | presentes | escala | dias VA/VT | **VA apurado** | **VT apurado** | Δ VA | Δ VT |
|---|---|---|---|---|---|---|---|
| Laranjeiras Village | 9 | 8 | 113 / 113 | **2.486,00** | **1.130,00** | −66,00 (−2,6%) | **−6,00 (−0,5%)** |
| Ideal Flores | 13 | 11 | 198 / 213 | **4.356,00** | **2.130,00** | −132,00 (−2,9%) | **−30,00 (−1,4%)** |
| Prime Arena | 6 | 6 | 104 / 114 | **2.288,00** | **1.140,00** | +484,00 (+26,8%) | +260,00 (+29,5%) |

**Dois dos três reproduzem.** No VT — que é o número mais simples, R$ 10,00 × dias — o erro é de
**0,6 dia** no Laranjeiras e **3 dias** no Ideal Flores. No VA o erro é de 3 e 6 dias.

### Prime Arena: a diferença e a causa

A escala dá **114** dias de VT; o dono escreveu **88**. `114 − 88 = 26` = **exatamente o mês
inteiro de um dos dois 44h do posto** (GRACIENE PEREIRA DE CASTRO ou MALAQUIAS PEREIRA FERREIRA,
26 dias cada). No VA: `104 − 21 = 83` contra os 82 do dono — sobra **1 dia (R$ 22,00)**.

E o Prime Arena tem uma **segunda nota** no cronograma: *«manutenção de piscina e jardinagem»*,
**R$ 3.879,60, emitida pela ELETRÔNICA**. A hipótese que a aritmética sustenta é que **um dos dois
agentes de serviços gerais é faturado naquela nota** e por isso não entra na dedução da nota da
Patrimonial. **É decisão do dono, não minha** — por isso o Prime Arena é o único contrato que sai
com a contagem em «não sei» e um botão «Sobrescrever».

Repare ainda que o número do dono para o Prime Arena **não fecha com ele mesmo**: 82 dias de VA
para «08 funcionários» dá **10,25 dias por pessoa**, que não é um mês de ninguém.

### O erro de aritmética no Ideal Flores — R$ 2.244,00 de dedução sem lastro

A linha do cronograma declara:

```
DEDUÇÕES DA BASE DE CÁLCULO: R$ 6.648,00 ... Vale Alimentação 08/2026: R$ 2.244,00
Vale Transporte 08/2026: R$ 2.160,00 ... BASE: R$ 59.194,42
```

`2.244 + 2.160 = 4.404`, não 6.648. E `6.648 − 4.404 = 2.244` = **o VA de novo**. A base
(65.842,42 − 6.648 = 59.194,42) está certa; o que está errado é o **VA discriminado, que saiu pela
metade — deveria ler R$ 4.488,00**. Como está, **R$ 2.244,00 da dedução não têm lastro escrito na
nota** e são glosáveis: **R$ 246,84 de INSS em risco**, mais multa. A apuração desta frente dá
R$ 4.356,00 de VA — coerente com os 4.488,00 corrigidos, não com os 2.244,00 escritos.

(O INSS declarado, R$ 6.511,62, também está R$ 0,23 acima de `59.194,42 × 11% = 6.511,39`.)

---

## §5 O efetivo divergente, nome a nome — o achado mais caro da frente

**Quatro fontes dizem quem está em qual cliente. As quatro discordam, e nenhuma bate com a
planilha do dono.** 08/2026:

| cliente | alocação | alocação antiga | escala | ponto | contratado | **presentes (escala ∪ ponto)** | cronograma |
|---|---|---|---|---|---|---|---|
| Ideal Flores | 14 | 13 | 11 | 13 | 12 | **13** ← confirmado pelo dono | 12 |
| Laranjeiras Village | 10 | 9 | 9 | 9 | 9 | **9** | 8 |
| Mirante das Flores | 8 | 9 | 8 | 9 | 9 | **9** | — |
| Villa dos Pássaros | 5 | 6 | 6 | 6 | 6 | **6** | — |
| Villa Dei Fiori | 8 | 7 | 7 | 5 | 6 | **7** | — |
| Prime Arena | 4 | 7 | 6 | 5 | 6 | **6** | 8 |
| Michelangelo | 2 | 2 | 2 | 2 | 3 | **2** | — |
| Green Hills | 1 | 0 | 0 | 0 | 4 | **0** | — |
| Conectamais Eletrônica | 12 | 0 | 12 | 12 | 12 | **12** | — |

### Nome a nome, e a causa

**Desligados ainda alocados** (a alocação nunca foi encerrada — contaminam folha, faturamento,
ponto e agora imposto):

| pessoa | desligado em | cliente | onde ainda aparece |
|---|---|---|---|
| JONATHAN DO NASCIMENTO MENDES | 22/07/2026 | Laranjeiras Village | `allocations` **e 16 turnos lançados em 08/2026** |
| DANIEL SOUZA DOS SANTOS | 24/08/2026 | Ideal Flores | `allocations`, `employee_alocacoes`, escala |
| FERNANDO MIGUEL GOMES DA SILVA | 22/07/2026 | Michelangelo | `allocations` |
| MEIRE GABRIELA DA SILVA E SILVA | 18/09/2026 | Villa dos Pássaros | já encerrada pelo orquestrador com autorização do dono |

> O JONATHAN é a prova de que a régua da escala funciona sozinha: ele tem 16 turnos lançados em
> agosto e **não entra** na apuração, porque o vínculo acabou em julho. É a afirmação (b) do oráculo.

**Alocado no cliente e sem nenhum turno no mês** (alocação parada ou transferência sem encerrar):

| pessoa | cliente onde está alocado | onde de fato esteve |
|---|---|---|
| RILEM FERREIRA DE SOUZA | Ideal Flores (`allocations`) | **16 turnos no Prime Arena** — transferência sem encerrar a anterior |
| KELLY PATRICIA DA SILVA DE SOUZA | Ideal Flores | nenhum turno e nenhuma batida em 08/2026 (admitida 19/07, alocada 12/08) |
| NAILSON GARCIA GOMES | Ideal Flores | **bateu ponto no Ideal Flores** e não tem turno lançado — falta escala, não falta pessoa |
| ELEN XAVIER NUNES | Laranjeiras Village | nenhum turno em 08/2026 |
| ALEXANDRE SOUZA DA SILVA | Mirante das Flores | nenhum turno em 08/2026 |
| CINTIA BEZERRA OLIVEIRA | Villa Dei Fiori | `afastado_inss` — correto não ter turno |

**Trabalhou e não está alocado ali:**

| pessoa | cliente | evidência |
|---|---|---|
| KEYSON DA SILVA PINTO | Prime Arena | 16 turnos; sem linha em `allocations` (demitido 14/08) |
| RILEM FERREIRA DE SOUZA | Prime Arena | 16 turnos; alocado no Ideal Flores |
| MAURICIO ALVES CHAGAS | Mirante das Flores | turnos e ponto; só em `employee_alocacoes` |
| MEIRE GABRIELA DA SILVA E SILVA | Villa dos Pássaros | turnos e ponto; só em `employee_alocacoes` |

**A linha absurda:** **Jordan Santos de Jesus**, status `candidato`, **alocado no Villa Dei Fiori
desde 19/07/2026** em `allocations` e com turnos lançados. Não toquei.

**Duas tabelas de alocação vivas ao mesmo tempo.** `allocations` (89 linhas, via `posts`) e
`employee_alocacoes` (73 linhas, via `condominios`) são caminhos independentes para a mesma
pergunta, e discordam em 7 dos 9 clientes. A frente AA4 lê `employee_alocacoes`; o operacional
grava em `allocations`. **Isto é dívida de arquitetura, não erro de digitação** — e é a razão de
fundo de tudo acima.

---

## §6 Quanto vale por mês

Notas da **Patrimonial** no cronograma de 09/2026 (identificadas pelo banco CORA na descrição):
**8 notas, R$ 246.220,46 de bruto**.

| | dedução | INSS a 11% |
|---|---|---|
| Hoje — o cronograma deduz em **3** das 8 linhas | R$ 13.020,00 | **R$ 1.432,20** |
| Com a apuração automática nas **8** | **R$ 27.004,00** | **R$ 2.970,44** |
| **Ganho da automação** | +R$ 13.984,00 | **+R$ 1.538,24 / mês** |

**R$ 2.970,44 por mês** que deixam de sair do caixa — **R$ 35.645,28 por ano** — e nas cinco notas
de agosto, que não deduziram nada, esse dinheiro saiu.

> **Cuidado que a AA4 precisa saber:** o Mirante das Flores emite **duas** notas no mesmo mês
> (limpeza R$ 12.061,50 e portaria R$ 28.694,30) e o VA/VT do contrato é **um só**
> (R$ 4.662,00). Deduzir o valor inteiro nas duas deduziria duas vezes o mesmo benefício.
> A apuração devolve o total do contrato; **quem divide entre as notas é a emissão, e hoje não
> divide.** Decisão do dono: ratear por valor, ou pôr tudo na nota de portaria.

---

## §7 Oráculo

`backend/scripts/orq/test_oraculo_aa6_va_vt.py`

```bash
WT=/opt/conecta-pro/.claude/worktrees/agent-aa6
ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')
docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" -e PYTHONPATH=/app \
  -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env \
  -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \
  conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_aa6_va_vt.py
```

### VERMELHO — antes do código (serviço removido do disco)

```
(a) o serviço não deduz pelo desconto do empregado (1010/1011 · folha_verba_espelho)
  ✗ /app/modules/people_management/folha/services/va_vt_contrato.py não existe — o serviço da frente AA6 não foi escrito

TOTAL desvios: 1
```

### VERDE — depois

```
(a) o serviço não deduz pelo desconto do empregado (1010/1011 · folha_verba_espelho)
  ✓ nenhum SQL do serviço toca `folha_verba_espelho` (só a docstring explica por quê)
  ✓ RUBRICAS_PROIBIDAS declarada no serviço (1010/1011)

(c) base do INSS = bruto − VA − VT, e o texto da nota escreve exatamente esses números
  ✓ Prime Arena: base R$ 26.916,00 · INSS R$ 2.960,76 · discriminação completa na nota
  ✓ Laranjeiras Village: base R$ 38.856,50 · INSS R$ 4.274,22 · discriminação completa na nota
  ✓ Ideal Flores: base R$ 59.194,42 · INSS R$ 6.511,39 · discriminação completa na nota
  · desconto do empregado (1010+1011) em 07/2026: R$ 3926.40
  ✓ 07/2026: apurado R$ 28388.00 ≠ desconto do empregado R$ 3926.40 — bases distintas, e a nossa é MAIOR (é custo, não desconto)

(b) quem saiu antes da competência não entra na contagem do contrato
  ✓ JONATHAN DO NASCIMENTO MENDES (desligado em 22/07/2026) tem turno lançado mas NÃO conta no contrato

(d) contrato sem apuração confiável devolve «não sei», nunca zero silencioso
  ✓ 0 de 8 contratos com o VALOR em «não sei», todos com motivo escrito
  ✓ 1 de 8 contratos com a CONTAGEM em «não sei» (valor apurado, cabeça não)
  ✓ Ideal Flores: presentes no posto = 13, o mesmo efetivo que o dono confirmou em 24/09/2026
  ✓ para_nota(Prime Arena, 08/2026): sabe=True · va=2288.0 · vt=1140.0
  ✓ tomador inexistente → sabe=False, sem zero inventado

(e) toda pessoa somada num contrato está em alguma fonte de alocação/escala daquele cliente
  ✓ CONDOMINIO DO EDIFICIO MICHELANGELO: 2 pessoa(s), todas com fonte
  ✓ CONDOMINIO IDEAL FLORES DA CIDADE: 11 pessoa(s), todas com fonte
  ✓ CONDOMINIO MIRANTE DAS FLORES: 8 pessoa(s), todas com fonte
  ✓ CONDOMINIO PRIME ARENA: 6 pessoa(s), todas com fonte
  ✓ CONDOMINIO RESIDENCIAL VILLA DOS PASSAROS: 6 pessoa(s), todas com fonte
  ✓ CONDOMINIO VILLA DEI FIORI: 7 pessoa(s), todas com fonte
  ✓ CONECTAMAIS ELETRONICA LTDA: 12 pessoa(s), todas com fonte
  ✓ RESIDENCIAL LARANJEIRAS VILLAGE: 8 pessoa(s), todas com fonte
  ✓ nenhuma pessoa com mais de 31 dias somando todos os contratos

TOTAL desvios: 0
```

---

## §8 A porta que a frente AA4 usa

```python
from modules.people_management.folha.services import va_vt_contrato as vv

r = await vv.para_nota(db, 2026, 8, "47405340000166")   # competência do BENEFÍCIO, CNPJ do tomador
# {'sabe': True, 'va': 2288.0, 'vt': 1140.0,
#  'pessoas': None, 'pessoas_presentes': 6, 'pessoas_confiavel': False,
#  'pessoas_motivo': 'presentes no posto (escala ∪ ponto) 6 · alocação 4 · alocação antiga 7 — nenhuma bate; confirme a quantidade',
#  'dias_va': 104, 'dias_vt': 114, 'unitario_va': 22.0, 'unitario_vt': 10.0,
#  'competencia': '08/2026', 'fonte': 'escala do mês × R$ 22,00/dia (VA) e R$ 10,00/dia (VT) — cct_benefit_configs',
#  'motivos': [], 'cliente': 'CONDOMINIO PRIME ARENA'}

vv.texto_discriminacao(bruto, va, vt, pessoas, "08/2026")
```

**São DUAS certezas separadas, e a AA4 tem de tratar as duas:**
- `sabe` → o **valor** de VA e VT. Falso ⇒ `va`/`vt` são `None` e `motivos` diz por quê.
- `pessoas_confiavel` → a **contagem**. Falsa ⇒ `pessoas` é `None` e **a emissão tem de pedir ao
  humano**, porque «QUANTIDADE DE FUNCIONÁRIOS NO CONTRATO» é declaração legal na nota.

`texto_discriminacao` devolve, ao centavo, o formato que o dono já usa:

```
DEDUÇÕES DA BASE DE CÁLCULO: R$ 2.684,00 | QUANTIDADE DE FUNCIONÁRIOS NO CONTRATO: 08 |
Vale Alimentação 08/2026: R$ 1.804,00 | Vale Transporte 08/2026: R$ 880,00 |
BASE DE CÁLCULO PARA RETENÇÃO DE INSS: R$ 26.916,00 | Aplicada retenção do INSS (11%) conforme
o Art. 31 da Lei n. 9.711/98. VALOR DA RETENÇÃO DE INSS (11%): R$ 2.960,76
```

---

## §9 O que NÃO foi feito, e por quê

1. **Não corrigi nenhuma alocação.** Produção é só leitura para mim e a correção é do dono. As 3
   alocações de desligados (Jonathan, Daniel, Fernando), a transferência do Rilem, as 4 alocações
   paradas e a linha do próprio Jordan como `candidato` no Villa Dei Fiori estão **medidas e na
   tela**, prontas para ele aprovar — nenhuma foi tocada.
2. **Não uni `allocations` com `employee_alocacoes`.** É a raiz do problema e é uma frente própria:
   mexer nas duas hoje, com 5 sessões na mesma árvore, quebraria operacional e faturamento juntos.
   A apuração foi desenhada para **não depender de nenhuma das duas**.
3. **Não liguei a entrega de benefício por posto** (`beneficio_entregas`, 0 linhas). O motor da
   frente 03 já calcula por pessoa; ligar a entrega física por posto → cliente é outra frente. A
   apuração de hoje sai da escala, que é dado que já existe e é verificável.
4. **Não deduzi nada na emissão.** A AA4 é dona da nota. Esta frente é um serviço que ela consome;
   não toquei em `nfse_emissao.py`, `_dgx_z7_nfse.py`, `tributacao_nfe.py` nem `_dgx_z*`.
5. **Não ratiei o VA/VT do Mirante entre as duas notas dele.** Quem decide o critério é o dono
   (§6); inventar um rateio aqui seria decidir por ele numa base de imposto.
6. **Não mexi em folha nem em holerite.** A apuração lê `shifts`, `gp_clock_punches`,
   `cct_benefit_configs` e `employees`, e escreve **só** em `va_vt_contrato_decisao` (tabela nova).
   Σ|Δ| nos holerites publicados = **R$ 0,00 por construção**: nenhum caminho de escrita toca folha.
7. **Não corrigi o cronograma do dono.** O erro de R$ 2.244,00 no Ideal Flores e o INSS de
   R$ 0,23 estão relatados; a planilha é dele.

---

## §10 Como o Jordan testa amanhã

1. DP → **Benefícios & Reembolsos** → aba **VA/VT por contrato**.
2. Filtro **Competência = 08/2026**. Confira Laranjeiras (R$ 2.486 + R$ 1.130) e Ideal Flores
   (R$ 4.356 + R$ 2.130) contra o que o senhor escreveu nas notas de setembro.
3. Na linha do **Ideal Flores**, clique **Texto da nota**, digite `65.842,42` e confirme que a
   frase sai pronta para colar na descrição.
4. Na linha do **Prime Arena**, repare que a quantidade aparece como `6?` em laranja — o sistema
   está dizendo que **não sabe** a contagem. Clique **Sobrescrever**, escreva o número que o senhor
   assina e a justificativa (ex.: «o ASG da piscina é faturado na nota da Eletrônica»). A decisão
   fica gravada com o seu nome e a emissão passa a usar aquele número.
5. Aba **Efetivo por contrato**: cada divergência com nome e causa. É a lista do que corrigir na
   alocação.

---

## §11 Decisões que só o dono pode tomar

1. **Prime Arena:** um dos dois agentes de serviços gerais (GRACIENE ou MALAQUIAS) entra na nota da
   Patrimonial ou na de manutenção da Eletrônica? A aritmética diz que hoje um deles está fora da
   dedução — e são 26 dias (R$ 260 de VT + R$ 462 de VA).
2. **Ideal Flores:** confirmar que o VA de 08/2026 era **R$ 4.488,00** e não os R$ 2.244,00
   escritos na planilha. Se for, a nota que sair com o texto atual tem **R$ 2.244,00 de dedução
   sem lastro** — glosável.
3. **Mirante das Flores:** as duas notas do mês dividem o VA/VT como? (por valor, ou tudo na de
   portaria).
4. **As 3 alocações de desligados** (Jonathan 22/07, Daniel 24/08, Fernando 22/07): encerrar com
   `end_date` = data da demissão? Autorizar em lote.
5. **RILEM FERREIRA DE SOUZA:** está alocado no Ideal Flores e trabalhando no Prime Arena desde
   agosto. Transferir formalmente?
6. **KELLY, NAILSON, ELEN, ALEXANDRE:** alocados e sem turno nenhum no mês. Falta escala ou falta
   encerrar a alocação?
7. **Jordan Santos de Jesus, `candidato`, alocado no Villa Dei Fiori desde 19/07** — remover?
8. **Contagem na nota:** quando as fontes discordam, o sistema pergunta. Confirma que é assim que
   o senhor quer, ou prefere que ele imprima o número dos presentes no posto?
9. **Unificar as duas tabelas de alocação** — frente própria, e é a raiz de tudo no §5.
