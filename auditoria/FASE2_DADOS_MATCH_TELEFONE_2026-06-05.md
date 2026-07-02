# Fase 2 — Dados reais de telefone para o match número→entidade (READ-ONLY)

- **Data:** 2026-06-05 ~21:25 UTC
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Definir a estratégia de match (número de entrada → cliente/lead) com base nos dados reais.

---

## 1. Onde há telefone populado (única fonte: leads)
| Fonte | Situação |
|-------|----------|
| `clients` | 11 registros, **0 com phone**, **0 com whatsapp** → inútil para match |
| `client_contacts` | **tabela NÃO EXISTE** (controller usa SQL cru que falharia) |
| `leads` | **11 registros, 11 com phone (100%)** → **única fonte usável** |

## 2. Formato real dos telefones em `leads`
- **11 dígitos, somente dígitos** (0 com `+`, 0 com símbolos `()- `, 11/11 só dígitos).
- DDD **92** (Manaus), padrão `92 9 XXXX XXXX` sem DDI.
- ⚠️ Últimos dígitos **sequenciais (01→11)** → têm cara de **dados de seed/teste**, não clientes reais.

## 3. Regra de normalização para o match (PROPOSTA)
- **Entrada (Baileys/Chatwoot):** chega em E.164 → `+5592XXXXXXXXX` (13 dígitos, com `55`).
- **Leads:** `92XXXXXXXXX` (11 dígitos, sem `55`, sem `+`).
- **Normalizar ambos** para os **últimos 11 dígitos** (DDD+número): remover `+`, remover `55` inicial se presente, comparar.
  - Ex.: `+5592991234567` → `92991234567` == lead `92991234567`.
- Cuidado com o **9º dígito** (celulares BR): comparar pelos últimos 11 garante DDD+9+8 dígitos.

## 4. Fluxo de entrada resultante (com os dados de hoje)
1. Mensagem entra → normaliza número (últimos 11 dígitos).
2. Busca em `leads.phone` normalizado:
   - **Match** → atualiza/anexa ao lead existente (dedupe).
   - **Sem match** → **cria novo Lead** (`source=whatsapp`).
3. Como `clients` não tem telefone, **não há match com cliente** hoje — tudo resolve em Lead. (Para casar com cliente no futuro, popular `clients.phone/whatsapp`.)
4. Registrar em `cwi_message_log` (idempotência por `chatwoot_message_id`).

## 5. Recomendações
- **Normalização canônica:** guardar no `cwi_message_log` (e idealmente no Lead) o telefone **normalizado** (só dígitos, com `55`) para casar com a entrada do Baileys de forma estável.
- Avaliar se os 11 leads atuais são seed/teste (sequenciais) — se sim, não poluir métricas de funil.
- (Opcional) popular `clients.phone/whatsapp` a partir das NFS-e/contratos para habilitar match com cliente.

---
*Read-only: `psql` (counts + formato mascarado). Nada alterado; telefones não expostos por inteiro.*
