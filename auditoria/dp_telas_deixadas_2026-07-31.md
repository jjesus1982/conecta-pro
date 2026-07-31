# DP redesign — as 5 telas deixadas de fora (2026-07-31)

> Estado anterior: as 5 eram **read-only puras** (`cta="—"`, sem `ctaTo`, sem `editfn`).
> Regra mantida: **só endpoint REAL**. Onde não existe rota, a tela fica como está e o motivo é registrado.

## Resultado

| Tela | Antes | Agora | Prova |
|---|---|---|---|
| **ponto** | read-only | ✅ **ação por-linha "Ajustar"** | 300 linhas c/ botão; 3 casos inválidos → **422** |
| **esocial** | read-only | ✅ **CTA "Sincronizar espelho"** | CTA → form `sincronizar-esocial` |
| **beneficios-cct** | read-only | ✅ **CTA "Adicionar benefício"** | CTA → form `novo-beneficio-cct` |
| **folha-rubricas** | read-only | ⛔ **bloqueado (honesto)** | endpoint de ajuste é **stub** |
| **saldo-ferias** | read-only | ⛔ **read-only legítimo** | **zero** endpoints montados |

## 1. `ponto` — ajuste por-linha

- **Endpoint:** proxy novo `POST /api/v1/redesign/action/ponto-ajuste?eid=&dia=` → chama o serviço
  real `dashboard_service.registrar_ajuste`, que faz `INSERT INTO gp_clock_punches`
  (`device_type='ajuste_dp'`) — **a mesma tabela que a tela lê**.
- **Por que proxy e não o endpoint direto:** `AjusteRequest.ajustado_por` tem que ser a **identidade
  REAL** do usuário logado. O proxy injeta `current_user.id` (`CurrentActiveUser`); chumbar um rótulo
  no builder seria falsificar autoria de um ajuste de ponto.
- **`eid`/`dia` vêm da LINHA**, não do usuário — o operador só escolhe tipo, hora e motivo.
- **Validação antes do service** (422): tipo ∈ {entrada, saida}; motivo ≥ 5 caracteres; hora `HH:MM`.

Prova por curl (id falso + payloads inválidos — **nada foi escrito**):

| Payload | Status |
|---|--:|
| `punch_type:"xxx"` | **422** |
| `motivo:"abc"` (curto) | **422** |
| `hora:"8h"` (formato) | **422** |
| rota inexistente (controle) | 404 |
| sem token (controle) | 401 |

## 2. `esocial` — CTA sincronizar espelho

`POST /api/v1/government/esocial/espelho/sincronizar` (body todo opcional; enfileira Celery em
`gov.esocial`). Repovoa `esocial_eventos_espelho` — a própria tabela da tela. **Leitura apenas: não
transmite nada ao governo.** O botão "XML do evento" segue **desabilitado** e honesto — o backend
não expõe GET do XML transmitido (só geração de XML novo, que é outra coisa).

## 3. `beneficios-cct` — CTA adicionar benefício

`POST /api/v1/people-management/admin/cct/convencoes/{id}/beneficios` → grava em `cct_beneficios`
(mesma tabela lida). O `convencao_id` é resolvido **do banco** (`is_vigente`), não chumbado —
sobrevive à troca de CCT. Hoje: SINDECOMPRESTS · AM000613/2025.

**Sem ação por-linha de propósito:** o backend tem apenas GET e POST de benefício. Não existe
`PUT`/`PATCH`/`DELETE` — criar um botão "Editar" exigiria inventar rota.

## 4. `folha-rubricas` — BLOQUEADO (e por quê)

`POST /people-management/folha/ajuste/{employee_id}` **não persiste nada**: o handler devolve
`{"success": True, "message": "Ajuste registrado — sera aplicado no proximo calculo"}` sem um
único INSERT/UPDATE. **Religar isso daria ao usuário a certeza de um ajuste que nunca acontece.**

Caminho honesto (não feito aqui): o CRUD real de holerite é `/people-management/dp/payslips/*`, mas
(a) não há endpoint de editar **uma rubrica** isolada e (b) a query da tela nem traz `payslip_id`.
Exige backend novo — fora do escopo de "religar o que já existe".

## 5. `saldo-ferias` — read-only legítimo

A tela lê `employee_vacation_periods`. O único controller que expõe essa tabela vive em
`modules/hr/employee_portal/`, e **`modules.hr` não é montado** (`grep -c 'modules\.hr'
main_production.py` → 0): é código morto não roteado. Não há nenhuma rota de escrita.

⚠️ **Drift a investigar (não corrigido):** existe `hr_vacation_periods` (canônica paralela) enquanto
a tela lê a legada `employee_vacation_periods` — mesmo padrão de drift já corrigido na tela `ferias`.
Vale checar qual está sendo populada antes de qualquer ação futura.
