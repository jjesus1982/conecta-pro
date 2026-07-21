# FASE 2 — Plano de execução (paridade fiel Clássico → Redesign)

> Base sólida ANTES do fanout. T1 (eu) constrói+prova as fundações; T2/T4 entram só quando a
> base estiver pronta e o plano de ação montado. Ver [[PRE_MORTEM_FASE2]].

## Rulings do Jordan (travados 2026-07-21)
1. **Fidelidade:** a **INFORMAÇÃO** (dado de negócio) vem do **clássico** (ele já tem o real,
   ancorado no banco) — é a fonte da verdade dos dados. O **CÓDIGO/comportamento** o T1 corrige
   (conserta o que está errado/quebrado no redesign). Onde o pacote de design (*.dc.html) diverge
   do clássico, **o clássico vence**; botão inventado pelo design sem equivalente = remove.
2. **Sequência:** só avançamos com **base bem sólida** — fundações + buracos do pré-mortem
   resolvidos + plano de ação montado. Só então T2/T4 (T3 fora, missão grande) entram no fanout.

## As 3 FUNDAÇÕES (T1 constrói+prova antes do fanout)

### ✅ #1 — GATE de escrita (choke-point) — FEITO + PROVADO
`backend/modules/operacional/controllers/redesign_write_gate.py`. Reusa OTP (e-mail Jordan) via
tabela própria `redesign_gate_otp` (desacoplada dos lotes). Invariantes provados por self-test
(6/6): money/gov exige OTP humano de uso único; NUNCA auto-fire; NUNCA fabrica sucesso (só
retorno real do PSP/gov); homologação simula; teto `CONECTA_LIMITE_DIARIO_PAGAMENTOS`; idempotência.
API: `money_gov(db, ref, amount, otp_code, real_dispatch, is_homologacao)` + `op_write(...)` +
`is_homologacao_target(db, employee_id)`. Pagamentos com OTP próprio (Inter) DELEGAM ao serviço.

### ✅ #2 — Kit de ação data-driven (frontend) — FEITO (base)
Estender o `FormScreen` do ModuleView (que JÁ é data-driven: renderiza `scr.fields`, POSTa em
`scr.submit.endpoint`) p/ cobrir: tipos de campo (select/data/money/máscara), validação inline,
**diálogo de confirmação + campo de OTP**, preview/dry-run, wizard multi-step, row-actions de
tabela. FEITO a base: FormScreen estendido com fluxo **confirmar + OTP** (casa com o gate:
backend responde otp_required → tela pede código e reenvia com otp_code) + confirm humano.
Retrocompatível (forms atuais inalterados). tsc: ModuleView limpo. Incremental: preview/dry-run,
wizard multi-step, row-actions. → T2/T4 adicionam botões reais editando SÓ o backend, zero React.

### ⏳ #3 — Oráculo de fidelidade — DEPOIS
Ferramenta que compara Clássico × Redesign por tela (screenshot + diff dos campos-chave) →
pass/fail objetivo. Mata A2/A3 (o "acesso e vejo coisa diferente"). Todos os terminais + o
verificador usam antes de declarar uma tela fiel.

## Buracos do pré-mortem — status
- C1 quebrar clássico → guarda: aditivo + regressão do clássico ao tocar serviço compartilhado (protocolo a escrever no plano de ação).
- C2/C3/C4 dinheiro/gov/dado → ✅ coberto pela Fundação #1.
- A1 frontend → coberto pela Fundação #2 (em construção).
- A2/A3 fiel/oráculo → Fundação #3 + ruling #1.
- A4 verificador=construtor → papéis separados (no plano de ação).
- A5 fetch-ao-vivo-502 → regra: nada de I/O lento na request (materializar/cachear).
- A6 migrations concorrentes → protocolo: schema aditivo, 1 dono por onda.
- A7 escopo → ondas priorizadas (legal/dinheiro → diário → resto), fatias pequenas provadas.

## Depois das 3 fundações
Montar o **plano de ação** (ondas priorizadas + divisão T1/T2/T4 + protocolo de deploy frontend
serial + regressão do clássico), então liberar o fanout. NÃO antes.
