# Re-rebuild da imagem (com o agente) — CONCLUÍDO

- **Data:** 2026-06-08 ~18:35 UTC
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Bakar o agente (Fase A) na imagem do backend — eliminar a fragilidade onde o recreate revertia o agente.
- **Resultado:** ✅ **SUCESSO. Os 9 containers rodam a imagem nova com o agente baked, healthy. Agente durável a recreate. Sem perda de dados.**

---

## 1. Resultado final
```
conecta-pro-backend             running/healthy  f0ee38d1a48a (NOVA, com agente)
conecta-pro-celery-beat         running/healthy  f0ee38d1a48a
conecta-pro-celery-operacional  running/healthy  f0ee38d1a48a
conecta-pro-celery-nfse         running/healthy  f0ee38d1a48a
conecta-pro-celery-sefaz        running/healthy  f0ee38d1a48a
conecta-pro-celery-batch        running/healthy  f0ee38d1a48a
conecta-pro-celery-priority     running/healthy  f0ee38d1a48a
conecta-pro-celery-integrations running/healthy  f0ee38d1a48a
conecta-pro-flower              running/healthy  f0ee38d1a48a
```
- **Containers na imagem anterior (`47b3f7`): 0.**
- Gates: `/health` **200**, webhook **200**.

## 2. O que isso resolveu
- Antes: a imagem `47b3f7` (de 15:08) não tinha o agente (criado depois, via `docker cp`). Na Parte B (ligar o agente), o recreate **reverteu o agente** → corrigido por re-cp.
- Agora: o agente (`agent_service.py` + `controller` com hook + **prompt v2**) está **baked na imagem**. Validado: **`agent_service.py` persiste após recreate** (Bloco 2A). **Recreate deixou de ser perigoso** para o agente.

## 3. Como foi feito (blocos, com gates)
- **Bloco 1:** backup do banco → tag rollback `pre-rerebuild-20260608` (→47b3f7) → build `rebuild-20260608b` (`f0ee38d1a48a`) → validação efêmera (agente presente, imports OK, prompt v2, md5 host==imagem).
- **Bloco 2A:** swap `:latest` → recreate backend → agente persiste + gates OK.
- **Bloco 2B:** recreate dos 8 celery + flower → todos healthy na imagem nova.

## 4. Estado do agente (inalterado, agora durável)
- `AGENT_ENABLED=true` (do `.env`), `OPENAI_AGENT_MODEL=gpt-4o-mini`, chave OpenAI do `.env` ativa.
- Modo **copiloto**: gera sugestão → nota privada no Chatwoot + rascunho (`drf`). **Não envia ao cliente.**
- Segredo do webhook: antigo `8ab9e3` (entrada não quebrou).

## 5. 🔙 Rollback / limpeza
- Rollback: `docker tag conecta-pro-backend:pre-rerebuild-20260608 conecta-pro-backend:latest` → `up -d --no-deps --no-build backend` (+ celery).
- Imagens de rollback preservadas: `pre-rerebuild-20260608` (47b3f7) e `pre-rebuild-20260608` (bfa169a2).
- Backup do banco: `backups/rebuild/pre_rerebuild_20260608_1825.dump`.
- **Limpeza futura (quando houver confiança):** `docker rmi conecta-pro-backend:rebuild-20260608 conecta-pro-backend:pre-rebuild-20260608` (imagens antigas) — opcional, fora de escopo agora.

## 6. Pendências (não-rebuild)
- **Custo:** com `AGENT_ENABLED=true`, cada mensagem de entrada gera 1 chamada OpenAI — acompanhar.
- **T1 senders duplicados** e **T2 rotação do segredo do webhook** (parqueada) — separadas.
- **F-B** (envio automático/tools) — só com decisão.

---
*Re-rebuild com gates/pausas aprovados. Agente baked → durável a recreate. Stack 100% na imagem nova, healthy, dados intactos, rollback pronto.*
