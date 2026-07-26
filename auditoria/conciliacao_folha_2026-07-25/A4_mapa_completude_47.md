# A4 — Conciliação 47 CLT jun/2026 (Patrimonial) — mapa de completude

Rodado PACED (endpoint /calcular individual). 37/47 conciliados (10 falharam em OOM
~call 10, auto-restart+resume; os 10 = ADAILSON..ANDREA já cobertos no sample de 6).

## Categorias de divergência
| Categoria | Func | Δlíquido total | Causa |
|-----------|------|----------------|-------|
| bate | 3 | R$1,53 | nativo == Portte |
| proventos_extra | 22 | R$4.470,95 | Portte tem proventos a mais (muitos pequenos R$40–80) |
| descontos_faltando | 5 | R$1.556,57 | nativo não puxa descontos (consignado/pensão/adiant.) |
| parcial | 4 | R$3.808,55 | mês parcial (admissão/rescisão); nativo = mês-cheio |
| inss_diverge | 1 | R$655,11 | base/composição |
| outro | 2 | R$8,08 | — |

## Roteiro de completude (o caminho pra folha autoritativa — sub-projeto A, A3)
1. **Mês parcial** — proporcionalizar salário+adicionais por dias trabalhados (do ponto/
   afastamento/admissão), em vez de mês-cheio. Maior gap por capita.
2. **Descontos completos** — alimentar consignado/pensão/adiantamento de employee_deductions
   (o nativo já lê alguns; faltam casos). Gaps grandes de líquido.
3. **Adicionais/HE finos** — a maioria dos "proventos_extra" é R$40–80 (rubrica menor); ajuste.

## Confirmações
- INSS/IRRF: fórmula OK — bate quando a base bate (visto no sample). Divergência = base, não cálculo.
- A folha nativa está PERTO para a maioria; o trabalho é completude (dados), não reescrever o motor.

## Nota OOM
Container backend 6GB: ~10 chamadas /calcular rápidas em série já estouram (memória acumula por
request). Rodar com sleep maior + lotes de ~8 + health-check/restart entre lotes.
