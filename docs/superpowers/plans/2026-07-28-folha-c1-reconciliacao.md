# Frente C / C1 — Reconciliação da Folha Autoritativa — Plan

> Spec: `docs/superpowers/specs/2026-07-28-folha-autoritativa-c1-design.md`. Objetivo: fazer o motor Conecta bater centavo-a-centavo com a Portte, verba a verba, para virar fonte da verdade. **Nunca corta às cegas; CRC assina.** [[project_financeiro_autonomo_prd]]

## Mapa de reuso (graphify + investigação 2026-07-28 — NÃO refazer)
**JÁ EXISTE (reusar):**
- `folha/services/calculo_service.py::calcular_folha_colaborador` (11 funções) — motor: computa proventos, INSS, IRRF, FGTS, VT/VR, **proporcionalização admissão/desligamento já correta** (`fator=dias/30`). ⚠️ tinha bug (`import calendar` faltando, já corrigido).
- `common/utils/clt_calculator.py` — tabelas INSS/IRRF/FGTS. Reusar.
- `hr/services/vacation_service.py` (férias) + `termination_service`/`cct_service` (`calcular_verbas_rescisorias`) — verbas de férias/13º/rescisão. Reusar.
- `certification/` — o gate C (fila de assinatura). Reusar p/ certificar IRRF.
- `scripts/folha_c1_dryrun.py` — harness de comparação. Expandir (hoje só líquido → por verba).
**NÃO EXISTE (construir):** camada de reconciliação verba-a-verba; persistência paralela source='conecta'; alimentar o motor com dado REAL por-pessoa.

## Achado que dirige tudo (dry-run 2026-07-28)
0/47 batem em jun. **Proporcionalização NÃO é o problema (já correta).** Divergências bidirecionais por-pessoa (R$1–R$202) → o motor usa **estimativa uniforme**; a Portte usa **dado real** (dias efetivos, horas noturnas/HE do ponto, adicionais/descontos individuais). Categorias jun: 6 admissão-parcial (base ok, resíduo=dado real), 2 férias, 5 desconto-grande(empréstimo), 34 "outros" (muitos a R$1–35 = quase batem). IRRF=0 nos dois (correto — salários abaixo da isenção).

## Fases
### Fase A — Harness de reconciliação por-verba (READ-ONLY) ⭐
Expandir `folha_c1_dryrun.py`: comparar **cada verba** (não só líquido) conecta×portte, casando por descrição normalizada. Saída: por competência, quais VERBAS divergem e quanto (Σ|Δ| por verba). Isso troca "0/47 batem" por "verba X diverge R$Y em N pessoas" — o mapa cirúrgico. Sem escrita.

### Fase B — Fechar as verbas que batem quase (os R$1–35)
Muitos divergem por centavos (arredondamento/base). Ajustar o motor verba a verba até bater os "quase". Re-roda harness, mede Σ|Δ| cair. Verbas com valor Portte → alvo R$0,00.

### Fase C — Dado real por-pessoa (o lever grande)
Alimentar o motor com dias/horas reais por competência: (1) ponto histórico (batidas → dias/horas noturnas/HE); (2) faltas/afastamentos; (3) empréstimos/descontos individuais (de onde a Portte tira?). Investigar a fonte de cada. Onde não há dado real (mês sem ponto), o motor fica honesto ("estimado") — não fabrica.

### Fase D — Verbas complexas (férias/13º/rescisão)
Reusar vacation_service/termination/cct para os meses de férias/13º. Casar o split (DIAS NORMAIS + HORAS FERIAS + médias) que a Portte faz.

### Fase E — Persistência paralela
Gravar source='conecta' (payslip_code próprio, idempotente por emp+comp+source). NUNCA toca 'portte'. Só depois que a Fase A-D mostrar Σ|Δ| aceitável.

### Fase F — Certificar IRRF + recibos férias/13º
IRRF calculado → fila `certifications` → CRC assina. Geradores de recibo.

### Fase G — (Futuro, gated) Corte Portte
Só após N competências baterem centavo + CRC assinar. Flip do source priorizado. Nunca nesta trilha.

## Guardrails
Nunca sobrescreve/deleta Portte. CRC pessoa-física assina (software não é responsável). Oráculo exibido==banco; onde falta dado real, "estimado", nunca fabrica. Money-out = T1.

## Ordem / medição
A → B → C (o grande) → D → E → F. **Métrica única: Σ|Δ| por competência caindo** (harness re-roda a cada fase). Começa por A (expandir o harness — read-only, revela as verbas culpadas).
