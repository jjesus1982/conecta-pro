# Investigação — de onde vem o "patronal efetivo baixo" na guia INSS real (2026-07-30)

> READ-ONLY. Medido da composição real dos DARF INSS (Onvio) + base da folha (hr_payslips).

## Pergunta
O DCTFWeb calcula patronal 28,8% (CPP 20% + RAT 3% + terceiros 5,8%), mas as guias INSS
jan-mai pareciam ter patronal muito menor. De onde vem?

## Medição — CPP (código 1138) como % da base INSS
| Mês | CPP 1138 | Base INSS | **% CPP** | Segurado 1082 | Total guia |
|---|--:|--:|--:|--:|--:|
| Jan | 6.136,62 | 85.596,25 | **7,2%** | ausente | 14.604,94 |
| Mar | 8.309,32 | 87.966,73 | **9,4%** | ausente | 16.993,55 |
| Abr | 9.916,87 | 93.842,90 | **10,6%** | ausente | 19.181,20 |
| Mai | 12.913,30 | 99.686,34 | **13,0%** | ausente | 22.754,50 |
| **Jun** | 19.441,46 | 97.207,33 | **20,0%** | **2.960,57** | 31.998,50 |

RAT (1646) ~4% e Terceiros (1170/1176/1191/1196/1200) ~5,8% são ESTÁVEIS todos os meses.
Só a **CPP (1138) rampa de 7,2% → 20%**.

## Conclusão (medida) — ATUALIZADA 2026-07-31 c/ confirmação do Jordan
> Jordan confirmou: Patrimonial = **Simples Anexo III** (patronal no DAS) e **NÃO há CPRB sobre receita**.
> Isso DESCARTA a hipótese inicial de desoneração/reoneração gradual.

1. As guias com CPP em rampa (7%→20%) são da **ELETRÔNICA** (CNPJ 35.710.481), que é **Lucro Real**.
   Lucro Real **sem CPRB** ⇒ a CPP deveria ser **20% cheia TODO mês**.
2. Logo, os **DARFs INSS de jan-mai da Eletrônica são INCOMPLETOS/parciais**: CPP só 7-13% e **sem a
   linha do Segurado (1082)**. **Junho é o 1º DARF completo** (CPP 20% + segurado). O oráculo INSS de
   jan-mai está, portanto, **SUBESTIMADO** — a reconciliação "INSS Δ=0" convergiu a guias parciais.
3. RAT (~4%) e Terceiros (5,8%) são estáveis e corretos todos os meses.

## A confirmar com a Portte
- Existe **DARF complementar** de INSS para jan-mai (que complete a CPP até 20% + o segurado)? Se sim,
  puxar/lançar — o INSS real jan-mai deve ficar ~como junho (~R$32k/mês), não R$14-22k.
- Por que os DARFs jan-mai saíram parciais (CPP 7-13%, sem segurado 1082)?

## Impactos p/ o contábil autônomo
- **DCTFWeb (28,8%) só está correto de JUNHO em diante** (CPP 20% cheia). Para jan-mai ele
  SUPERESTIMA a CPP (assume 20%, real 7-13%) → não transmitir sem ajustar a alíquota ao ano/mês
  da reoneração, OU passar a modelar CPRB.
- **INSS patronal no razão** (postado = guia − retido_folha): o TOTAL bate com a guia, mas a
  composição jan-mai é "patronal reduzido + sem segurado no DARF". O retido da folha (inss_value
  ~7k) ≠ segurado do DARF (2.960 em jun) — divergência folha-espelho × eSocial a investigar
  separadamente.

## A confirmar com Jordan/Portte
- A empresa está sob **desoneração/CPRB** (reoneração gradual)? Se sim, precisamos puxar/lançar a
  **CPRB sobre receita** e ensinar o DCTFWeb a usar a alíquota CPP do ano (não 20% fixo).
- Por que o **segurado (1082)** só aparece no DARF de junho? (recolhimento separado jan-mai?)

## Quantificação do GAP jan-mai (2026-07-31)
INSS "cheio" esperado (Lucro Real, sem CPRB) = CPP 20% + RAT/terceiros reais + segurado, vs guia parcial.

| Mês | base INSS | CPP% real | Gap CPP (20%−real) | Guia real |
|---|--:|--:|--:|--:|
| Jan | 85.596 | 7,2% | 10.983 | 14.605 |
| Fev | 83.550 | 7,0% | 10.897 | 14.061 |
| Mar | 87.967 | 9,4% | 9.284 | 16.994 |
| Abr | 93.843 | 10,6% | 8.852 | 19.181 |
| Mai | 99.686 | 13,0% | 7.024 | 22.754 |
| **Σ jan-mai** | | | **47.039** | 87.595 |
| Jun (completo) | 97.207 | 20,0% | 0 | 31.998 |

**Gap SÓLIDO (só CPP) = R$ 47.039** jan-mai — CPP declarada a 7-13% vs 20% devido.
**Gap total estimado ≤ R$ 79.772** — SUPERESTIMA: junho (guia completa) mostra segurado DARF
R$2.961 vs retido folha R$7.111, então o segurado do DARF é ~40% do retido; o gap real de segurado
é menor que o cheio. Faixa provável: R$47k (só CPP) a ~R$80k.

**Ação Portte:** existe DARF complementar jan-mai que suba a CPP p/ 20%? E qual a regra do segurado
(por que o 1082 do DARF é ~40% do inss_value da folha)?
