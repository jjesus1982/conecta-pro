# F-CRM pré — O que o modelo Cliente/Lead suporta hoje (READ-ONLY)

- **Data:** 2026-06-09
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Mapear campos e dados reais de `clients`/`leads` para o CRM/agente (identificar cliente, enriquecer).
- **Veredito:** Modelo rico, mas **dados de contato (telefone) vazios** → match por telefone não funciona; por **CNPJ** funciona (100% populado).

---

## 1. Modelo `clients` (`modules/clients/models/client.py`) — rico
- **Identificação:** `code` (único), `name`, `trading_name`, `client_type`, `document_type`, **`document_number`** (CNPJ/CPF, indexado), inscrição estadual/municipal.
- **Contato:** `email` (NOT NULL), `phone`, `mobile`, **`whatsapp`**, `website`.
- **Endereço** completo + endereço de cobrança.
- **Contatos responsáveis:** `financial_contact_name/email/phone` e `technical_contact_name/email/phone` (financeiro + técnico). **Não há campo específico "síndico"/"administrador".**
- `status`, `segment`.

## 2. Dados reais (11 clients — vieram das NFS-e)
| Campo | Populado |
|-------|----------|
| `document_number` (CNPJ, 14 díg) | **11/11 (100%)** ✅ |
| `name` | **11/11** ✅ |
| `email` | **11/11** ✅ |
| `phone` | **0/11** 🔴 |
| `whatsapp` | **0/11** 🔴 |
| `financial_contact_phone` | **0/11** 🔴 |

## 3. Tabela de contatos por cliente
- `client_contacts` → **NÃO EXISTE** no banco (o `crm/controllers/contact_controller.py` referencia uma tabela fantasma — SQL cru que falharia em runtime).
- Logo, **não há "múltiplos telefones por cliente"** disponíveis hoje.

## 4. Modelo `leads`
- Telefone **único** (`phone`, varchar 20, nullable). `source` inclui `whatsapp`. Sem CNPJ.
- (Já mapeado: 6 leads `whatsapp`, todos com telefone normalizado.)

## 5. Implicações para o CRM/agente (fatos, não decisão)
- **Match número WhatsApp → cliente: IMPOSSÍVEL hoje** (0 telefones em `clients`).
- **Match por CNPJ: VIÁVEL** — todos os 11 têm `document_number`. Se o agente **perguntar/receber o CNPJ**, `client_repository.get_client_by_document(cnpj)` identifica se já é cliente.
- **Match por nome:** possível mas frágil (fuzzy).
- Para habilitar match por telefone no futuro: **popular `clients.phone/whatsapp`** (a partir das NFS-e/contratos) — tarefa de dados à parte.

## 6. DECISÕES DE PRODUTO (sua definição — não inventei o escopo da F-CRM)
1. O objetivo é **identificar se o contato já é cliente**? Se sim, por qual chave? (CNPJ funciona; telefone não, até popular).
2. Vale **popular os telefones dos clients** (das NFS-e/contratos) para habilitar reconhecimento automático por número?
3. O agente deve **vincular o Lead a um Client** quando identificar o CNPJ? (hoje não há FK Lead→Client).
4. Precisa de campo "síndico/administrador"? (o modelo tem financeiro/técnico, não síndico).

---
*Read-only: leitura do `client.py`/`lead.py`, `information_schema`, `to_regclass`, contagens. Nada implementado. Escopo da F-CRM aguardando sua definição.*
