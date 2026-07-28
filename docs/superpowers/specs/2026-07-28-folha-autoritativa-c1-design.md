# Frente C / C1 — Folha Autoritativa (demitir Portte) — Design

> Território T2 (eu). Objetivo: tornar o motor de folha do Conecta a **fonte da verdade** da folha CLT, saindo do fallback (hoje 100% espelho Portte), para eventualmente demitir a Portte. **Nunca corta às cegas** — só após rodar em paralelo e bater centavo a centavo, com CRC (pessoa física) assinando. [[project_financeiro_autonomo_prd]] [[feedback_money_out_t1_boundary]]

## Estado real (investigado 2026-07-28, oráculo)
- `hr_payslips`: **314/314 `source_system='portte'`**, todos com `external_id` → folha 100% espelho Portte. Zero 'conecta'. Competências jan–jun/2026 (56 em jun).
- **`irrf_value=0` em todos os 314** → IRRF não veio no import Portte. Conciliar IRRF vs Portte não bate por definição — nosso motor calcula o real, o delta é *esperado*.
- Motor existe: `folha/services/calculo_service.py::calcular_folha_colaborador` (CCT: insalubridade, adicionais, faltas) + `_batch`. Mas `_batch` **prioriza dados importados** (Portte) — é o "fallback". `calcular_folha_batch` **não persiste** conecta hoje.
- Constraint `hr_payslips`: UNIQUE `(condominio_id, payslip_code)` → dá pra gravar linha 'conecta' com `payslip_code` distinto **sem colidir/sobrescrever** a linha 'portte'.

## Arquitetura
Motor computa **independente** (CCT + contrato + dias) → **persiste em paralelo** (`source_system='conecta'`, payslip_code próprio, idempotente, NUNCA toca 'portte') → **concilia centavo-a-centavo** (por verba) → **certifica IRRF** (fila do gate C existente → CRC assina) → *(futuro, gated)* corta Portte. Os 2 espelhos coexistem até bater. Interface folha↔razão = `hr_payslips` source='conecta' (T1 consome via `ledger_auto`).

## Componentes / Fases
1. **Dry-run — relatório de delta (READ-ONLY, zero escrita)** ⭐ primeira entrega. Roda o motor independente nas 6 competências (jan–jun/2026, todos ativos), compara com a linha Portte (mesmo emp/comp), e produz por funcionário e por verba: base, total_proventos, INSS, **IRRF**, FGTS, líquido → delta Conecta×Portte. Relatório salvo em `auditoria/`. Revela se o motor é confiável ANTES de qualquer persistência.
2. **Motor completo + IRRF** — fechar o que o delta mostrar faltando/divergente (o IRRF é o maior, esperado). Ajustar `calcular_folha_colaborador` até bater centavo nas verbas onde a Portte tem valor (IRRF fica como novo dado nosso).
3. **Persistência paralela** — gravar `source_system='conecta'` (payslip_code próprio, idempotente por emp+comp+source). Não toca Portte.
4. **Certificação IRRF** — o IRRF calculado entra na fila de certificação (`certifications`, tipo `esocial_s2210`/folha) → CRC/humano assina. Gate legal.
5. **Recibos férias/13º** — geradores de documento.
6. *(Futuro, gated, NÃO nesta leva)* **Corte Portte** — só após centavo bater em N competências + CRC assinar. Flip do `source_system` priorizado de portte→conecta.

## Guardrails (inegociáveis)
- Nunca sobrescreve/deleta linhas 'portte' (paralelo puro).
- Legal/fiscal: software gera, **CRC pessoa física é o responsável técnico** que assina. Não se inventa número; oráculo exibido==banco.
- Corte só após bater centavo a centavo e CRC assinar. Nunca às cegas.
- Money-out (pagar a folha) = T1, gated OTP. C1 só produz a folha autoritativa, não paga.
- Motor é CCT SINDECOMPRESTS AM000613/2025 (agentes de portaria; piso R$1.670/2026).

## Verificação (oráculo)
Fase 1 (dry-run): o relatório É a verificação — números reais, não narrativa. Sem escrita, nada a reverter. Fases 3+: idempotência + query no banco (linhas 'conecta' existem, 'portte' intactas).

## Aberto p/ próxima fase
- Como o motor recebe dias-trabalhados/faltas por competência (do ponto? do import?). O dry-run vai expor se ele usa dados corretos por mês.
- Tolerância de conciliação: exata (R$0,00) nas verbas com valor Portte; IRRF fora (Portte=0).
