# F-VISITA.1 pré (cont.) — responsável + enums + endereço (READ-ONLY)

- **Data:** 2026-06-09
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Resolver as 2 fricções de `criar_visita` (`responsavel_id`, `endereco`) e validar enums.
- **Veredito:** `responsavel_id` é UUID **sem FK** → você escolhe o id. **2 contas "Jordan Jesus"** (decisão sua). `OrigemVisita` **não tem WHATSAPP** (usar LEAD). Endereço do **cliente conhecido** dá pra puxar (10/11); prospect o agente coleta.

---

## 1. `responsavel_id` — UUID sem ForeignKey
`models/visita.py`: `responsavel_id = Column(UUID, nullable=False, index=True)` — **sem FK**. Referência solta (não validada pelo banco) + `responsavel_tipo` ∈ {TECNICO, VENDEDOR, SUPERVISOR, CONSULTOR}. Pode apontar para um `users.id`.

## 2. Jordan em `users` (colunas reais: id, email, name, role) — 2 contas
| Conta | id | role |
|-------|-----|------|
| `jjesus@conectamais.pro` (corporativo) | `ad9abb59-55fb-444e-a04f-0e1f22541de3` | **admin** |
| `jordansjesus@gmail.com` (pessoal) | `266007cb-02f9-4a88-8dbb-c47721dd0853` | operator |

- Também `jpires@conectamais.pro` = Jordana Bacry Pires (outra pessoa).
- **42 usuários role=`agente`** (provável equipe de campo/vendas) — opção para atribuir a vendedores.
- ⚠️ **Qual id usar é decisão sua** (natural: corporativo admin `ad9abb59…`).

## 3. Enums
- **`OrigemVisita`:** `LEAD, CLIENTE, INDICACAO, PROSPECCAO_ATIVA, CAMPANHA_MARKETING, INTERNA` — **sem WHATSAPP**. Para visita do WhatsApp → **`LEAD`** (default); o Lead já tem `source=whatsapp`.
- **`TipoVisita`:** TECNICA, COMERCIAL, VISTORIA, PROSPECCAO, ORCAMENTO, DEMONSTRACAO, ASSINATURA_CONTRATO, ACOMPANHAMENTO, OUTRO.
- **`TipoResponsavel`:** TECNICO, VENDEDOR, SUPERVISOR, CONSULTOR.

## 4. Endereço em `clients` (não `endereco`, e sim `address_*`)
Colunas: `address_street/number/complement/neighborhood/city/state/zipcode/country` (+ `billing_address_*`).
- **Fill: 10/11** com `address_street` e `address_city`.
- ➜ **Cliente identificado por CNPJ → agente puxa o endereço de `clients`** (resolve o obrigatório). **Prospect/lead desconhecido → agente coleta na conversa.**

## 5. Mapa final dos obrigatórios de `criar_visita`
| Obrigatório | Como resolver |
|-------------|---------------|
| `responsavel_id` | você escolhe: admin `ad9abb59` / operator `266007cb` / um agente (round-robin) |
| `endereco` | cliente conhecido → de `clients.address_*` (10/11) · prospect → agente coleta |
| `data_visita` / `horario_inicio` | agente coleta na conversa |
| `origem` (default) | `LEAD` (não há WHATSAPP) |
| `tipo` | TECNICA ou COMERCIAL (sua escolha) |

## 6. DECISÕES (suas)
1. **Qual `responsavel_id`** o agente usa por padrão? (admin `ad9abb59` / operator `266007cb` / distribuir entre os 42 `agente`).
2. `tipo` default: **TECNICA** ou **COMERCIAL**?
3. Confirmar: cliente conhecido → puxar endereço de `clients.address_*`; prospect → coletar. OK?

---
*Read-only: `users` (id/email/name/role), `OrigemVisita`/`TipoVisita`/`TipoResponsavel` em `models/visita.py`, `responsavel_id` sem FK, colunas e fill de endereço em `clients`. Nada implementado.*
