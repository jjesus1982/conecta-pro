# F-CRM pré — CORRIGIDO: contatos/atividades/360° (READ-ONLY)

- **Data:** 2026-06-09
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Entender o "controller fantasma" de contatos e o desenho real do CRM.
- **Veredito:** O esquema é **rico e já existe** (contatos, atividades, link Lead↔Client) — está **vazio de dados**, não faltando estrutura. Corrige 2 erros do relatório anterior.

---

## ⚠️ Correções ao relatório anterior (`FCRM_PRE_MODELO_CLIENTE_LEAD`)
Eu havia checado o **nome de tabela errado** (`client_contacts`). O correto é **`crm_contacts`**:
1. **`crm_contacts` EXISTE** (eu disse que não existia). Estrutura confirmada; **0 linhas** (vazia).
2. **`clients.lead_id` EXISTE** (FK Lead→Client) e **10/11 clients estão vinculados** (eu disse que não havia link Lead→Client).
3. `crm_activities` também existe (vazia).
> Transparência: foram erros de verificação meus (nome da tabela). Estes números vêm de `to_regclass`/`information_schema`/contagens reais.

## 1. O "controller fantasma" — na verdade é um CRM 360° (parcial)
`modules/crm/controllers/contact_controller.py` (usa `get_async_session`, SQL cru):
- **Contatos:** `GET/POST/DELETE /contacts/` sobre **`crm_contacts`** (campos: client_id, name, role, email, phone, whatsapp, is_primary, notes).
- **Atividades:** `crm_activities` (type: call|email|whatsapp|visit|meeting|note, subject, description, outcome, scheduled_at).
- **Visão 360°** (a partir de ~linha 265): junta `clients` + `leads` (via `c.lead_id`), `client_contracts` (ativos, `monthly_value`), `opportunities`, `crm_contacts`, `crm_activities`, `nfses` (por `tomador_cpf_cnpj`), `employees/allocations/posts`.

## 2. Estruturas e DADOS reais
| Tabela | Existe? | Linhas |
|--------|---------|--------|
| `crm_contacts` | ✅ | **0** |
| `crm_activities` | ✅ | **0** |
| `clients` | ✅ | 11 (100% CNPJ/nome/email; **0 telefone/whatsapp**) |
| `leads` | ✅ | 6 whatsapp (todos com telefone) |
| `clients.lead_id` (FK→leads) | ✅ | **10/11 vinculados** |

## 3. Implicações reais para o CRM/agente
- **Esquema pronto:** contatos por cliente (`crm_contacts` com phone/whatsapp/role), atividades, e link **Lead↔Client** (`clients.lead_id`) já existem. É **problema de DADOS (vazio)**, não de estrutura.
- **Match número→cliente:** ainda **impossível por telefone** (clients.phone e crm_contacts.phone ambos vazios). **Por CNPJ funciona** (clients 100%).
- **Lead↔Client:** já há o caminho (`clients.lead_id`); 10 clientes já apontam para um lead. Um lead novo de WhatsApp poderia, no futuro, ser **promovido a client** ou vinculado.
- **Popular `crm_contacts`** (telefone/whatsapp dos responsáveis, a partir das NFS-e/contratos/cadastro) habilitaria o reconhecimento automático por número — hoje o gargalo.

## 4. 🔐 Observação de segurança (read-only, não corrigi)
No `contact_controller.py` (~linha 53-54) o filtro usa **interpolação de string** do query param:
```python
where = f"WHERE cc.client_id = '{client_id}'"
```
→ **SQL injection** potencial via `?client_id=`. Endpoint exige auth (`CurrentActiveUser`), mas vale corrigir para parâmetro bindado. **Apenas reportando** (fora do escopo agora).

## 5. DECISÕES (suas — não inventei escopo)
1. F-CRM vai **popular `crm_contacts`** (telefone/whatsapp dos clientes) para habilitar match por número? De onde (NFS-e? contratos? cadastro manual?).
2. O agente deve **registrar atividade** (`crm_activities` type=whatsapp) a cada conversa? E **promover/vincular** o Lead de WhatsApp a um Client quando identificar CNPJ (via `clients.lead_id`)?
3. Identificação de cliente: por **CNPJ** (viável hoje) — o agente pergunta/recebe e usa `get_client_by_document`?
4. Corrigir a SQLi do contact_controller (§4) entra no escopo ou fica como tarefa à parte?

---
*Read-only: leitura do controller + `to_regclass`/`information_schema`/contagens. Corrige 2 imprecisões do relatório anterior (crm_contacts existe; lead_id existe). Nada implementado.*
