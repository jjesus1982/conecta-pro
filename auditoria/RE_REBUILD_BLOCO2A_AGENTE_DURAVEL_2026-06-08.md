# Re-rebuild — Bloco 2A: backend na imagem nova, agente DURÁVEL

- **Data:** 2026-06-08 ~18:30 UTC
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Trocar `:latest` para a imagem com o agente baked e recriar o backend.
- **Resultado:** ✅ **Backend na imagem nova, healthy. Agente PERSISTE após recreate (fragilidade resolvida).** Celery/flower seguem na imagem anterior (próximo gate).

---

## 1. O que foi feito
1. **Swap de tag:** `docker tag conecta-pro-backend:rebuild-20260608b conecta-pro-backend:latest` → `:latest` = `f0ee38d1a48a`.
2. **Recreate só do backend:** `docker compose up -d --no-deps --no-build backend` (compose intocado).

## 2. Teste decisivo (durabilidade)
- **`agent_service.py` PRESENTE após o recreate** ✅ — antes (Parte B) o recreate revertia o agente; agora ele está **baked na imagem**, então persiste.
- `import agent_service` OK, `agent_enabled()=True`.

## 3. Gates de produção (OK)
| Gate | Resultado |
|------|-----------|
| backend | running/healthy, IMG `f0ee38d1a48a`, RestartCount=0 |
| `/health` | 200 |
| webhook `?token=<ativo 8ab9e3>` | 200 (entrada não quebrou) |
| `AGENT_ENABLED` | true |
| `OPENAI_AGENT_MODEL` | gpt-4o-mini |
| dados | `cwi_message_log=20`, `leads whatsapp=5` (intactos) |

## 4. Estado das imagens
```
:latest                 f0ee38d1a48a  (NOVA, com agente) — backend rodando nela ✅
:rebuild-20260608b      f0ee38d1a48a
:pre-rerebuild-20260608 47b3f70359a5  (ROLLBACK)
backend                 -> f0ee38d1a48a (NOVA) ✅
8 celery + flower       -> 47b3f70359a5 (anterior, sem agente) — intactos (não usam o agente)
```

## 5. 🚦 GATE — Bloco 2B (celery + flower) aguardando aprovação
```bash
docker compose -f docker-compose.yml -f docker-compose.celery.yml up -d --no-deps --no-build \
  celery-beat celery-operacional celery-nfse celery-sefaz celery-batch celery-priority celery-integrations flower
```
- **Seguro:** mesmo código baked; os workers não usam o agente, mas recriar os alinha à imagem nova (consistência).
- Validar pós: workers healthy, Celery processando, Flower no ar.
- **Não executado** — parei para revisão.

## 6. 🔙 Rollback
```bash
docker tag conecta-pro-backend:pre-rerebuild-20260608 conecta-pro-backend:latest
docker compose up -d --no-deps --no-build backend
```
Imagem `47b3f7` intacta sob `:pre-rerebuild-20260608`. Backup do banco: `backups/rebuild/pre_rerebuild_20260608_1825.dump`.

---
*Bloco 2A: swap de tag + recreate do backend. Agente baked → persiste após recreate (resolvido). Gates OK, dados intactos. Celery/flower no próximo gate.*
