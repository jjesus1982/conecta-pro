# F-VISITA.1 pré — Métodos do `visita_service` (READ-ONLY)

- **Data:** 2026-06-09
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Saber exatamente como o agente criaria uma visita (campos obrigatórios, status, padrão async).
- **Veredito:** Serviço async **completo e pronto** — agente chamaria `VisitaService(db).criar_visita(VisitaCreate(...))`. Duas fricções: **`responsavel_id`** e **`endereco`** são obrigatórios. "Solicitada" não existe; criação assume **AGENDADA**.

---

## 1. `visita_service.py` — async, ciclo completo
`__init__(db: AsyncSession)`. Métodos:
- **`criar_visita(data: VisitaCreate, created_by)`**, `obter_visita`, `obter_visita_por_numero`, `atualizar_visita`, `excluir_visita`.
- Listagens: `listar_visitas(...)`, `listar_visitas_responsavel`, **`listar_visitas_cliente(cliente_id)`**, **`listar_visitas_lead(lead_id)`**, **`listar_pendentes_confirmacao()`**.
- Ciclo: **`confirmar_visita`**, `iniciar_deslocamento`, `fazer_checkin`, `fazer_checkout`, `registrar_resultado`, `cancelar_visita`, `reagendar_visita`, `agendar_followup`.
- Negócio: `registrar_interesse`, `vincular_proposta`, `registrar_contrato`, `registrar_nao_fechamento`, `adicionar_levantamento/necessidade/foto`, `obter_estatisticas`.
- **Repo async** (`AsyncSession`): `create`, `get_by_id`, `get_by_numero`, `update`, `delete` (soft), `list_*`, `_gerar_numero` (numero auto).

## 2. `VisitaCreate` — campos OBRIGATÓRIOS
| Campo | Tipo | Obs |
|-------|------|-----|
| **`responsavel_id`** | UUID | obrigatório — quem faz a visita |
| **`endereco`** | str (min 5, max 500) | obrigatório |
| **`data_visita`** | date | obrigatório |
| **`horario_inicio`** | time | obrigatório |

**Opcionais (com default):** `tipo`=COMERCIAL, `origem`=LEAD, `responsavel_tipo`=VENDEDOR, `responsavel_nome`, `duracao_prevista_minutos`=60, `horario_fim`.
**Vínculo (opcionais):** `cliente_id`, `contrato_id`, `lead_id`, `oportunidade_id`.
**Prospect sem cadastro:** `is_prospect`, `prospect_nome/empresa/cargo/telefone/celular/email/cnpj/cpf`.
**Endereço extra:** `endereco_complemento`, `bairro`, `cidade`, `estado`, `cep`, `latitude`, `longitude`, `ponto_referencia`.
**Outros:** `objetivo`, `tags`.

`TipoVisita`: TECNICA, COMERCIAL, VISTORIA, PROSPECCAO, ORCAMENTO, DEMONSTRACAO, ASSINATURA_CONTRATO, ACOMPANHAMENTO, OUTRO.

## 3. Status (`StatusVisita`)
`RASCUNHO, AGENDADA, CONFIRMADA, EM_DESLOCAMENTO, REALIZADA, CANCELADA, REAGENDADA, NAO_COMPARECEU`.
- ⚠️ **"solicitada" NÃO existe.** `VisitaCreate` sem campo `status` → model default `status = AGENDADA` (`models/visita.py:118`).
- Fluxo "criada → confirmada" nativo: `criar_visita`(AGENDADA) → `listar_pendentes_confirmacao` → `confirmar_visita`(CONFIRMADA).

## 4. Implicações para o agente (fatos)
- **Async pronto:** `VisitaService(db).criar_visita(VisitaCreate(...))` — mesma ponte async do resto (sem bridge sync).
- **2 fricções reais:**
  1. **`responsavel_id` obrigatório** — precisa de um vendedor/responsável padrão (não pode nulo).
  2. **`endereco` obrigatório** — leads de WhatsApp não têm endereço → agente **coleta na conversa** ou puxa de `clients` (se for cliente por CNPJ).
- **Sem "solicitada":** usar **AGENDADA** como "aguardando confirmação" + `confirmar_visita`.

## 5. DECISÕES (suas — não decidi escopo)
1. **`responsavel_id` padrão** do agente? (vendedor fixo? round-robin? — obrigatório, não pode nulo).
2. **Endereço:** agente coleta na conversa (prospect) e/ou puxa de `clients` ao identificar CNPJ?
3. Agente **cria AGENDADA** (humano confirma) mantendo copiloto, ou só **sugere**?
4. `tipo` default: **TECNICA** ou **COMERCIAL**?

---
*Read-only: `grep` de assinaturas em `visita_service.py`/`visita_repository.py`, `VisitaCreate` em `schemas/visita.py`, enums e `status` default em `models/visita.py`. Nada implementado. Escopo aguardando sua definição.*
