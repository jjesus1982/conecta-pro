---
name: juridico
description: Use ao trabalhar no MÓDULO JURÍDICO do Conecta PRO — Central de Contratos (ciclo de vida, alertas de vencimento/renovação/reajuste/assinatura), compliance (CCT trabalhista, certidões CND/FGTS), LGPD, e revisão de cláusula com IA. Cobre o motor de alertas sobre a tabela contracts, as fontes reais, e o playbook de revisão adaptado do claude-for-legal (Apache-2.0) ao contexto brasileiro/segurança patrimonial.
---

# Módulo Jurídico — Conecta PRO (Conecta Mais)

## Contexto (objetivo)
A Conecta Mais é **empresa de segurança patrimonial**, NÃO escritório de advocacia. O jurídico é INTERNO: gestão dos próprios contratos, compliance trabalhista/CCT, LGPD, certidões. Ignore o grosso das suites de escritório (litígio/M&A/e-discovery). Escopo: **contratos + compliance + LGPD**.

## Central de Contratos (feito — base do módulo)
- Backend: `backend/modules/juridico/contracts_service.py` + `contracts_controller.py`. Endpoints `/api/v1/juridico/contratos/{dashboard,alertas,,{id}}`. Frontend: `frontend/src/app/modulos/juridico/contratos/page.tsx`. Card no `modules.ts` (id `juridico`).
- **Fonte real = tabela `contracts`** (rica: start/end_date, status, auto_renewal, renewal_notification_days, adjustment_enabled/next_adjustment_date, signature_required/signed_at, monthly_value, has_sla, clauses). NÃO invente — ver [[veracity-sweep]].
- **Motor de alertas** (datas reais, `date.today()`): vencimento (crítico≤30 / atenção≤60 / próximo≤90d), vencido (<0), renovação (auto_renewal & dentro de renewal_notification_days antes do fim), reajuste (adjustment_enabled & next_adjustment_date ≤45d), assinatura pendente (signature_required & !signed_at). "0 alertas de vencimento" é honesto quando os contratos vencem longe (não é bug).
- Inspirado no "renewal watcher" do `claude-for-legal` (Apache-2.0), implementado NATIVO. Automação: candidato a task Celery beat (ver [[deploy-bake]]).

## Compliance
- **CCT trabalhista** é o maior risco jurídico (folha/SINDECOMPRESTS) → ver [[folha-cct]].
- **Certidões** (CND federal/estadual/municipal, CRF/FGTS, CNDT) → `ged_certidoes` (validade real) + robô CND GEDEON. Reusar, não recriar.
- **LGPD** → `modules/security_lgpd` (consent/erasure/pia/audit, persistem em lgpd_*; erasure com anonimização real gated por confirmar=True). Já pronto.

## Revisão de cláusula com IA (fase 2 — adaptar de repo Apache-2.0)
Fonte legal de código: **`anthropics/claude-for-legal`** (Apache-2.0 → pode reusar prompts/playbook). Padrão: um PLAYBOOK que codifica as posições padrão da empresa por tipo de cláusula (posição desejada, faixa aceitável, gatilho de escalonamento); a IA (Bartolo) compara o contrato ENTRANTE cláusula-a-cláusula vs o playbook e sinaliza desvios. `zubair-trabzada/ai-legal-claude` tem boas ideias (review/risco/PDF) mas SEM licença → só ideias, não código. Adaptar ao BR (Lei 8.078 CDC, CLT, LGPD) e ao nosso negócio (contratos de portaria/segurança eletrônica).

## Não faça
- Não adotar CLM externo (OpenCLM=AGPL contamina; Wraft=Elixir). Construir nativo na `contracts`.
- Não inventar cláusula/parecer/valor legal — o humano (jurídico/contábil) certifica. Ver [[folha-cct]] e [[veracity-sweep]].
- PDF de contrato/aditivo = padrão-ouro, ver [[gold-standard-pdf]].
