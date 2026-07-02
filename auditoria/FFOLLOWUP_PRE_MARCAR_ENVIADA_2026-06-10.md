# Marcar proposta como ENVIADA — viabilidade (READ-ONLY)

- **Data:** 2026-06-10
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Mapear como marcar uma proposta como enviada (sent_at + status SENT) antes de implementar.
- **Veredito:** ✅ **Já existe e faz exatamente isso.** `POST /api/v1/crm/proposals/{id}/send` seta `status=SENT` + `sent_at=now`, sem PDF nem envio ao cliente. **Nada a implementar** — só testar.
- **NADA implementado.** Só leitura.

---

## 1. ProposalStatus — `SENT` existe
StrEnum: `draft, pending_review, pending_approval, approved, **sent**, **viewed**, accepted, rejected, expired, cancelled`. Status inicial no create = `draft`.

## 2. Endpoint pronto: `POST /api/v1/crm/proposals/{id}/send`
- Docstring: "Muda status para SENT e registra data de envio."
- Handler: `proposal = await repo.update_status(proposal_id, ProposalStatus.SENT, user_id=str(current_user.id))`.
- **NÃO gera PDF, NÃO envia ao cliente.** Pura transição status + timestamp = escopo exato.

## 3. `repo.update_status` (linha ~411) — seta os timestamps certos
```python
proposal.status = status.value
if status == ProposalStatus.SENT:
    proposal.sent_at = datetime.utcnow()
elif status == ProposalStatus.VIEWED:
    proposal.viewed_at = datetime.utcnow()
elif status in (ACCEPTED, REJECTED):
    proposal.responded_at = datetime.utcnow()
proposal.updated_at = datetime.utcnow()
await self.db.commit()
```
- Update escalar simples + commit (sem `calculate_totals`/lazy-load → **baixo risco** do bug do create).
- ⚠️ Não chama `can_transition_status` e o controller também não → **DRAFT→SENT funciona direto** (sem gating de transição).

## 4. sent_at / viewed_at / responded_at — onde são setados
- `sent_at`: **só** via `update_status(SENT)` (endpoint `/send`). Nenhum outro lugar.
- `viewed_at`: **só** via `update_status(VIEWED)` — e **não há mecanismo que dispare VIEWED hoje** (exigiria tracking de abertura pelo cliente, fase futura pós-LGPD). Ficará **null**.
- `responded_at`: ACCEPTED/REJECTED (usado em stats de tempo de resposta — `(responded_at - sent_at).days`).

## 5. `can_transition_status` — existe, mas não wired
Mapa de transições no service (`APPROVED→[SENT]`, `SENT→[...]`, etc.) existe, mas **não está plugado** no `update_status`/controller. Helper disponível, não gate ativo.

## 6. Outros endpoints de ciclo já existem
`/{id}/submit`, `/approve`, `/send`, `/accept`, `/reject`, `/new-version` — todo o lifecycle tem endpoint.

---

## Veredito
**Nada a implementar para "marcar como enviada".** `POST /{id}/send` faz `status=SENT` + `sent_at=now`, sem efeitos colaterais (PDF/envio).
- **Caveat:** o endpoint **nunca foi exercido** (proposals vazia/quebrada até `eb60ea82`). Risco de bug latente **baixo** (update escalar, sem lazy-load), mas **não verificado**.

## Caminho mais limpo (reusar 100%)
1. **Smoke test** (próximo passo, escrita mínima reversível): criar proposta → `POST /{id}/send` → confirmar `status=sent` + `sent_at` no banco → limpar. Prova o `/send` pós-fix-do-create.
2. **Follow-up** usaria: `proposals WHERE status='sent' AND sent_at < hoje-Xd AND responded_at IS NULL`. Não confiar em `viewed_at` (fica null sem tracking de abertura).

---
*Read-only: `ProposalStatus`, `update_status`, `can_transition_status`, endpoints do app vivo, grep de `sent_at`/`viewed_at` no módulo crm. Nada implementado.*
