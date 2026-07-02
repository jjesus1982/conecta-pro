# WhatsApp — Evolution vs Baileys: estado atual e decisão (READ-ONLY)

- **Data:** 2026-06-05 ~17:33 UTC
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Mapear o estado do Evolution para subsidiar a decisão "Baileys (Chatwoot) vs Evolution (backend ERP)" como canal oficial de WhatsApp.
- **Veredito:** 🟢 **Baileys está conectado e operacional;** 🔴 **Evolution está "connecting" (não pareado, sem número).** Não há conflito de número agora, mas **não se deve linkar o mesmo número nos dois**.

---

## 1. Estado de cada provedor

| | **Baileys (via Chatwoot)** | **Evolution (via backend ERP)** |
|---|---|---|
| Container | `baileys-api` (healthy) | `evolution-api` (up) |
| Instância | conexão `+558008804414` | instância `conecta-pro` |
| Status | ✅ **conectado/logado** (mensagens fluindo) | 🔴 **`connecting`** (preso) |
| Número vinculado | `+558008804414` (Business "smbi") | **`null`** (nenhum) |
| Profile | — | "Conecta Mais" |
| Consumidor | Chatwoot (atendimento) | Backend ERP (`EVOLUTION_API_URL`) |
| Operacional? | **Sim** (1 conversa / 4 msgs sincronizadas) | **Não** (sem número, não conecta) |

## 2. Dependência do backend no Evolution
- `backend/.env`: `EVOLUTION_API_URL=http://evolution-api…`, `WHATSAPP_API_ENABLED=true`, `WHATSAPP_INSTANCE_ID=conecta-pro`.
- Ou seja, o ERP **acha que tem WhatsApp ligado** via Evolution, mas a instância está em `connecting`/`number=null` → **qualquer envio do backend por WhatsApp hoje falha** (provedor não conectado).

## 3. Há disputa de número?
- **Agora não:** o Evolution está com `number=null` (não linkado), e o Baileys detém o `+558008804414`.
- **Risco se tentar linkar o mesmo número nos dois:** o WhatsApp trata cada provedor como um "aparelho conectado". Linkar o mesmo número em Evolution **e** Baileys ao mesmo tempo gera **conflito de sessão** (desconexões/reconexões).
  - ⚠️ Possível relação com os warnings `timed out waiting for message` observados no Baileys — vale garantir que **ninguém** tente conectar o mesmo 0800 no Evolution enquanto o Baileys o detém.

## 4. Recomendação para a decisão (PROPOSTAS — nada executado)

**Opção 1 — Oficializar Baileys/Chatwoot (recomendada se o foco é atendimento humano):**
- Já está conectado e funcional.
- Ação: no `backend/.env`, **desativar o WhatsApp via Evolution** (`WHATSAPP_API_ENABLED=false`) ou migrar as features de envio do ERP para falar com o Chatwoot/Baileys, evitando dois caminhos.
- Aposentar/parar a instância Evolution para não competir.

**Opção 2 — Oficializar Evolution (se o ERP precisa enviar WhatsApp programático direto):**
- Exigiria **parear a instância `conecta-pro`** (hoje em `connecting`) com um número — **que NÃO pode ser o mesmo** já usado no Baileys, sob pena de conflito.
- Implicaria não usar o Baileys/Chatwoot para esse mesmo número.

**Em ambos os casos:** **um número = um provedor.** Definir qual sistema é o dono do `+558008804414` e desligar o outro para esse número.

## 5. Pendências relacionadas
- Acompanhar estabilidade do Baileys (warnings de timeout) — confirmar que não há tentativa concorrente de conexão.
- Decisão de negócio é sua; deixo as duas opções mapeadas, **nada executado**.

---
*Read-only: `fetchInstances` (GET) no Evolution via host, leitura de `env` e `backend/.env` (mascarado). Nenhuma instância/sessão/config alterada; apikey não exposta.*
