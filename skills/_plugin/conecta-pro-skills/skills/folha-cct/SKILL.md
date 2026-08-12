---
name: folha-cct
description: Use ao calcular, ajustar ou auditar a FOLHA DE PAGAMENTO do Conecta PRO — holerite, proventos/descontos, adicionais, VT/VR, INSS/IRRF/FGTS, contracheque. A base é a CCT SINDECOMPRESTS AM000613/2025 (agentes de portaria, NÃO vigilância). Cobre piso, adicionais POR PESSOA, VT/VR por escala, tabelas 2026, e o princípio inegociável de nunca inventar dado trabalhista/legal.
---

# Folha & CCT SINDECOMPRESTS — Conecta PRO

## Princípio inegociável
**Dado trabalhista/legal NUNCA se inventa.** O sistema calcula (cálculo híbrido) mas o **DP confere e ajusta** conforme a folha oficial (Domínio/Portte). Onde a folha oficial existe, ela é a fonte da verdade — o simulador CCT é fallback rotulado. Ver [[veracity-sweep]].

## Base salarial (regra de ouro)
- Somos **AGENTES DE PORTARIA** (não vigilância). CCT **SINDECOMPRESTS AM000613/2025**, vigência 2026, é a fonte (cargos/pisos/adicionais/benefícios) — tabela `cct_cargos`.
- Base = **PISO da categoria** (R$1.670 em 2026), **NUNCA** o mínimo federal. O mínimo federal 2026 = R$1.621 (só entra na faixa 1 do INSS).
- Cargos/CBO (da folha oficial Domínio): Agente de Portaria 5174-10 · Líder de Portaria 5103-10 · ASG 5143-20 · Artífice 5143-10 · Jardineiro 6220-10.

## Adicionais são POR FUNCIONÁRIO (não por cargo)
Colunas em `employees`: `insalubridade_percentual`, `periculosidade_percentual`, `adicional_ronda_percentual`, `recebe_intrajornada` (bool). Ex.: 2 ASG no mesmo cargo, só quem faz a atividade insalubre recebe. Adicional de ronda 15% (CCT Cl.23ª) só pra quem faz ronda. **Intrajornada = flag por-pessoa (default off)** — só paga quem de fato recebe. Noturno/hora-noturna-reduzida vêm do **ponto real** (`gp_clock_punches`, janela 22h–05h; hora noturna reduzida 52'30" gera horas fictícias pagas a 100%, separado do adicional noturno 20%).

## VT/VR por escala (regra da empresa)
`calculo_service.dias_vt_vr(escala, mes, ano)`: VT R$10/dia, VR R$22/dia.
- **12x36 (AGP/Líder)**: dia sim/dia não, indiferente a sáb/dom/feriado → dias pela ESCALA (~15). Piso já contempla.
- **44h comercial (ASG/Artífice/Jardineiro)**: seg–sex + sáb 8-12 → VT conta seg–sáb; **VR só seg–sex (sábado SEM VR)**.
- Co-participação (desconto): VT 4% + VR 1% do salário (fica no holerite, bate com Domínio). VR/VT o benefício vai no **Recibo de VT e VR** (doc próprio, ver [[gold-standard-pdf]]) — não nos proventos do holerite.
- Odonto = R$9,00 (co-part. 50%, empresa custeia a outra metade). **Sem seguro de vida** (era chumbado, removido).

## Tabelas federais 2026 (em calculo_service.py)
- **INSS 2026** (Portaria Interministerial MPS/MF nº 13): faixas 1621 / 2902,84 / 4354,27 / 8475,55; alíquotas 7,5/9/12/14%; teto desconto R$988,09. `INSS_CERTIFICADA=True`.
- **IRRF 2026** (Lei 15.270/2025 + 15.191/2025): tabela progressiva (isenção R$2.428,80) + **redutor** da reforma `978,62 − 0,133145×rendimento` (isenta até R$5.000, parcial até R$7.350). `IRRF_CERTIFICADA=False` (aguarda certificação humana com casos-teste).
- FGTS 8%. Divisor 12x36=180, 44h=220.

## Motor
`backend/modules/people_management/folha/services/calculo_service.py::calcular_folha_colaborador(db, employee_id, mes, ano)` — é o mesmo usado pelo fechamento (`calcular_folha_batch`) e pelo holerite/portal. Retorna proventos/descontos/bases/vt_vr/liquido. Ver [[gold-standard-pdf]] pro PDF.

## Nunca faça
- Não recalcular por cima da folha oficial quando ela existe (risco jurídico).
- Não usar mínimo federal como base.
- Não pôr adicional por cargo (é por pessoa).
- Não fabricar valor de imposto/apólice/benefício — se não há fonte, "aguardando dado".
- TDD aqui é bem-vindo (cálculo crítico): ver [[superpowers:test-driven-development]] pra INSS/IRRF/VT-VR novos.
