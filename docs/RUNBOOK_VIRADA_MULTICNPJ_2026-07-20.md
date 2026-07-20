# RUNBOOK — Virada Multi-CNPJ (antecipada) · Grupo Conecta Mais

**Data:** 2026-07-20 · **Objetivo do Jordan:** virar antes do 31/07 com janela longa de teste.
**Estado:** ENSAIO E2E **GO (9/9)** · suítes release **37/37** · bloco Cora **100%**.

> A "virada" no SISTEMA já está feita e validada (flip dos 56, contratos migrados,
> fiscal/banco parametrizados). Este runbook é para você OPERAR e TESTAR com segurança
> até a competência real de julho, e para reagir se algo aparecer.

---

## 1. O que JÁ está pronto (validado sobre dados reais)

- **2 empresas** ativas e completas (Eletrônica LR · Patrimonial Simples Anexo III faixa 4).
- **Contratos**: 7 → Patrimonial, 3 → Eletrônica, com aditivos gerados (assinatura pendente).
- **Funcionários**: 53 vínculos vigentes na Patrimonial (fronteira 2026-07); histórico fica na Eletrônica.
- **Documentos** (holerite/espelho/recibo/TRCT/aviso): identidade por empregador × competência
  — junho sai CNPJ1, julho sai CNPJ2, sem reescrever o passado.
- **Fiscal**: NFS-e por empresa, NSU por empresa, notas da Patrimonial importadas, regra de
  substituição corrigida.
- **Cora**: conta registrada, saldo/extrato conciliando, cobrança (boleto+PIX), pagamento
  (guias/boletos com aprovação no app), webhook em tempo real, comprovante por banco.
- **Certidões** por CNPJ, kits híbridos prontos, dashboard do Grupo, 8 consultores IA no contexto Grupo.

## 2. O que VOCÊ precisa fazer (operacional/externo)

| # | Ação | Prazo | Efeito |
|---|---|---|---|
| 1 | **D7** — no app Cora, desligar aprovação in-app p/ pagamentos via API (suporte) | quando puder | pagamento 100% automático; até lá você aprova no app |
| 2 | **Aditivos** — colher assinatura dos 7 condomínios | até 30/07 | formaliza a transferência com o cliente (não bloqueia faturamento) |
| 3 | **Custo de posto** — pedir à Portte o % de encargo exato do Anexo III | quando puder | eu troco 1 linha e a precificação da Patrimonial fica exata |
| 4 | **Frontend** — avisar quando T1/T2 tiverem uma janela de árvore limpa | quando puder | subo minhas 5 telas (já commitadas) |

## 3. Como TESTAR (a qualquer momento)

- **Veredito da virada**: `docker exec conecta-pro-backend sh -c 'cd /app && PYTHONPATH=/app python scripts/ensaio_multicnpj.py'` → deve dar **GO 9/9**.
- **Regressão (nada quebrou no CNPJ1)**: as 3 suítes `*_release` + `multicnpj_release` (37/37).
- **Cobrança real Cora** (reversível): emitir R$5 e cancelar — provado.
- **Pagamento real Cora** (aprovação sua no app): DARF/boleto R$5 → INITIATED → aprova → webhook concilia → cancelar se for só teste.
- **Documento por competência**: gerar holerite de um funcionário em 06/2026 (sai CNPJ1) e 07/2026 (sai CNPJ2).

## 4. Assinatura dos aditivos (quando os condomínios assinarem)

Marcar `contract_addendums.signed=true` do aditivo `TRANSF-*` correspondente — o motor de
alertas de contrato para de cobrar a pendência.

## 5. Rollback (se algo der muito errado na virada real)

- **Backups automáticos** diários 03:00 (`backups/postgresql/backup_*.sql.gz`) + snapshots
  rotulados por etapa (`pre_multicnpj_*`, `pre_espelhamento_*`, `pre_classificacao_*`).
- **Reverter o flip trabalhista**: `UPDATE employees SET empresa_id='<eletronica>'` (o snapshot
  pre_espelhamento tem o estado anterior) + limpar `MULTICNPJ_FRONTEIRA_COMPETENCIA`.
- **Reverter contrato**: `UPDATE contracts SET empresa_id='<eletronica>'` (migração é aditiva).
- Cada migration de `empresa_id` é aditiva com backfill CNPJ1 — reverter é um UPDATE.

## 6. Pendências minhas (pós-externos)

- Pagamento de guias/DAS/FGTS da Patrimonial via Cora em produção (após D7, disparo automático).
- Deploy do frontend (janela coordenada).
- Custo de posto Anexo III (1 linha, após % da Portte).
