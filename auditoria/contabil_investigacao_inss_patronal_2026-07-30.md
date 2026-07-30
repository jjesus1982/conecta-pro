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

## Conclusão (medida)
1. **NÃO é 16% fixo nem desoneração total** — é uma **CPP em RAMPA (7%→20%)**, característica de
   **desoneração da folha com REONERAÇÃO GRADUAL** (Lei 14.784/2023 / MP 1.202/2023). O setor de
   **vigilância/segurança/portaria é um dos 17 desonerados** (CPRB). A CPP volta por etapas até 20%.
2. **Junho = primeira guia com CPP 20% cheia** — coincide com a transição da folha p/ Patrimonial.
   Também é a 1ª guia com a linha **Segurado (1082)** — jan-mai o DARF só tem patronal (o segurado
   era recolhido em separado/GPS ou não constava neste DARF).
3. **Provável CPRB não capturada**: na desoneração, os 20% de CPP são substituídos por CPRB (~4,5%
   sobre a RECEITA BRUTA) — uma guia SEPARADA. Não achei DARF de CPRB no Onvio (categoria própria
   inexistente). Se existe, falta puxar; a contabilidade jan-mai deveria ter a CPRB sobre receita.

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
