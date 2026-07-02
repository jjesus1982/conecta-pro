# Smoke test — POST /crm/proposals/{id}/send (marcar enviada) ✅

- **Data:** 2026-06-10
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Provar que o endpoint de marcar proposta como enviada funciona após o fix do create (`eb60ea82`).
- **Veredito:** ✅ **SIM, o `/send` funciona.** Marca `status=sent` + `sent_at=now`, sem PDF nem envio ao cliente.
- **Escrita:** só teste (criar+send+deletar 1 proposta, revertido). Nada implementado/commitado, sem rebuild, código intocado.

---

## 1. Execução (2 rodadas, mesmo resultado)
| Passo | Resultado |
|-------|-----------|
| **CREATE** `POST /crm/proposals` | HTTP **201** · status=`draft` · total=`1500.0` (2×750) · sent_at=`None` |
| **SEND** `POST /crm/proposals/{id}/send` | HTTP **201** · status=**`sent`** · sent_at=**`2026-06-10T01:52:34`** |

## 2. Estado final no banco (prova)
```
id=001f1786-… | status=sent | sent_at=2026-06-10 01:52:34 | responded_at=NULL | viewed_at=NULL
```
- `status='sent'` ✅ · `sent_at` preenchido ✅ · sem efeito colateral (PDF/envio) ✅.
- `responded_at`/`viewed_at` permanecem `NULL` (esperado — só se preenchem em fluxos de resposta/visualização futuros).

## 3. Limpeza
- Itens + proposta de teste deletados → **`proposals` = 0**.
- **`opportunities` seed (5) intactas** (não tocadas).

## 4. Veredito
**O `/send` funciona** — o caveat ("nunca exercido") está resolvido: pós-fix do create, marcar como enviada opera corretamente.
- Update escalar simples (`update_status(SENT)`), sem o bug de lazy-load que quebrava o create.

## 5. Implicação para o follow-up
- A query-fonte do follow-up confirmada viável: `proposals WHERE status='sent' AND sent_at < hoje-Xd AND responded_at IS NULL`.
- **Não usar `viewed_at`** como sinal (fica `null` sem tracking de abertura — fase futura pós-LGPD).

---

## Resumo
- CREATE 201 + SEND 201; banco confirma `status=sent` + `sent_at` preenchido. ✅
- proposals limpa (0), opportunities seed intactas. ✅
- `/send` validado — pronto para ser a base do follow-up. Nada implementado/commitado, sem rebuild.

*Smoke test concluído. PAREI.*
