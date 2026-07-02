# REBUILD TRANSFER+TRIAGEM — COMPLETO (bloco 2B + consolidação)

- **Data:** 2026-06-09
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Imagem nova:** `conecta-pro-backend:latest` = **`c4bde53893fd`**
- **Status:** ✅ **COMPLETO.** 9 containers na imagem nova, running, health 200. Fixes duráveis.

---

## Bloco 2B — celery + flower na imagem nova
- Recriados: `celery-beat`, `celery-operacional`, `celery-nfse`, `celery-sefaz`, `celery-batch`, `celery-priority`, `celery-integrations`, `flower`.
- **Todos os 9 containers** = `c4bde53893fd`, `status=running`.
- **Gate final:** `/health` **200**.

| Container | Imagem | Status |
|-----------|--------|--------|
| backend + 7 celery + flower (9) | `c4bde53893fd` | running |

## Mudanças durabilizadas neste rebuild
1. **F-VISITA.2** (`983378bb`) — e-mail de solicitação de visita (interno sempre + cliente se cadastrado, best-effort).
2. **transferir_conversa** (`026f6f85`) — 4ª tool: encaminha a conversa ao time do setor no Chatwoot (`assign_team` no service).
3. **Triagem** (`31b8195f`) — pergunta o assunto antes de transferir pedido vago de humano.
4. **Preservados:** fix model campo (`4a1296e3`), agendar_visita (`87f0def9`), tool use F-B.1, SQLi fix.

## Jornada do rebuild
| Bloco | Ação | Resultado |
|-------|------|-----------|
| 1 | backup + tag + build + validação efêmera | `c4bde53` validada (`--network none`), produção intocada |
| 2A | swap `:latest` + recreate backend | backend na img nova, healthy, POST `/campo/visitas/` **201** (com auth), 4 tools |
| 2B | recreate celery + flower | 9 containers alinhados, health 200 |

## Prova de durabilidade
Containers recriados **a partir da imagem** (não docker cp). 4 tools carregam + POST visitas 201 → todos os fixes bakados; recreate não reverte mais.

## Rollback disponível
- Imagem: `pre-rebuild-transfer-20260609` = `b18575b9` (anterior) · `pre-rebuild-fvisita-20260609` = `5958168f` · `pre-rerebuild2-20260609` = `f0ee38d1`.
- Banco: `pre_rebuild_transfer_20260609_222719.dump`.
- Reverter: `docker tag conecta-pro-backend:pre-rebuild-transfer-20260609 conecta-pro-backend:latest` + recreate.

## Observações honestas (já no 2A)
- Gates 502 no 2A foram transitórios (boot); após healthy → 200/200/401, POST visitas 201 (com auth).
- Warning de orphan containers no compose: benigno (`--no-deps`); nada indevido tocado.

## Estado final
- 9 containers em `c4bde53`, running, **health 200**.
- `AGENT_ENABLED=true` — **4 tools** (consultar_cnpj, buscar_cliente, agendar_visita, transferir_conversa), modo copiloto.
- `visitas` = 0 (testes limpos). Webhook secret inalterado, dados intactos.
- **Sem pendências de rebuild.**

---

## Resumo
- REBUILD completo: 9 containers na imagem `c4bde53` (F-VISITA.2 + transferir_conversa + triagem bakados, anteriores preservados). ✅
- POST `/campo/visitas/` 201, 4 tools, health 200, 9/9 running. ✅
- Backup + tags de rollback no lugar. ✅
- Fim das pendências de rebuild — recreate agora é seguro.

*Rebuild TRANSFER+TRIAGEM completo.*
