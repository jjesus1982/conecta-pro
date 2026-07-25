# DP — Gap para MATAR O CLÁSSICO (superfície = só redesign, 2026-07-24)

Rodada: `backend_recon.py people-management --surface redesign`. Raw: `dp_redesign_gap_2026-07-24.txt`.
Objetivo do Jordan: quando o redesign estiver 100%, desligar o clássico. Este relatório mede o que o **redesign ainda não cobre** — não o clássico+redesign juntos.

## A diferença que muda tudo
| Superfície | Montadas | Expostas | Órfãs | Geradores órfãos |
|---|---|---|---|---|
| clássico+redesign (`--surface all`) | 698 | 633 | 65 | 5 |
| **SÓ redesign** (`--surface redesign`) | 698 | **375** | **322** | **21** |

O 1º recon (65 órfãs) **subestimou** o gap: contava exposição no clássico como cobertura. Para desligar o clássico, o número real é o de baixo: **322 rotas do DP que o clássico usa e o redesign ainda não referencia.**

## Refino honesto das 322 (nem toda órfã é gap real)
Os builders do redesign leem dados **direto do banco (SQL)**, então parte dos GET de leitura o redesign já cobre sem chamar a rota. O gap acionável é o subconjunto ação/escrita/documento:

- **159 WRITE/ação** (POST/PUT/DELETE/PATCH) — o redesign não tem esses botões/forms. **Gap real** (menos ~10 `/integration/*` server-to-server e os money-out com gate OTP).
- **163 GET-only** — leitura; boa parte o redesign já mostra via SQL nos builders. Gap real = subconjunto sem tela equivalente (a confirmar tela a tela).
- **21 geradores de documento** órfãos — ver abaixo.

## Os 21 geradores — separando redesign de portal
O **redesign** é a UI admin/gestão (substitui o clássico admin). O **portal-funcionário** é app SEPARADO do colaborador — os geradores `self-service/*` e `my-payslips` são responsabilidade do portal, NÃO do redesign.

**Responsabilidade do REDESIGN (~13) — gap real de documento:**
- `hr/contracts/.../download-aviso` (+ gerar) · `hr/payroll-export/contracheques-batch`
- `hr/payroll/employee/{id}/payslip-pdf` · `hr/payroll/.../esocial/receipt/{id}` 🏛️
- `hr/payroll/.../exports/` + `/process-pending` + `/{id}` + `/download-info` + `/retry` (pipeline de export de folha, 5 rotas)
- `hr/ponto/espelho/solicitar-homologacao/{mes}/{ano}` · `hr/reimbursements/attachments/{id}/download`
- `ponto/folha-pdf/{id}` (+ download) · `sst/ppp/{id}/pdf`

**Responsabilidade do PORTAL (~8) — fora do redesign:**
- `portal/my-payslips/{m}/{y}/pdf` · `portal/self-service/meu-espelho/{m}/{y}/pdf`
- `portal/self-service/meus-documentos/{id}/download` · `portal/self-service/meus-holerites` (+ variações)

## Leitura para o objetivo "matar o clássico"
- O finish-line do DP no redesign ≈ **~150–180 capacidades acionáveis** (159 ações − integrações/money-out + ~13 documentos + telas de leitura faltantes). Grande, mas finito e enumerável.
- O sub-projeto DP-DOCS (3 componentes) cobre 2–3 desses documentos. Os outros 5 sub-projetos atacam o resto.
- **Recomendação de método:** daqui pra frente rodar o recon SEMPRE com `--surface redesign` — é o oráculo do que falta para desligar o clássico. O `--surface all` só serve para achar o que não existe em lugar nenhum.
- Cada módulo terá seu próprio gap-redesign; DP é só o primeiro. A conta total (todos os módulos) define o "redesign 100%".

## Triagem dos 21 geradores redesign-órfãos (25/07 — conclusiva)
Investigados 1 a 1 (dado real + escopo + redundância). Resultado: **o gap de geradores acionável está fechado**.
- **FEITOS (2):** `ponto/folha-pdf` (Componente A — doc em fechamento-ponto) · aviso prévio de férias (Componente B — form+ação+gancho). No ar e duráveis.
- **BLOQUEADO (1):** `contracheques-batch` — bug `status=="Ativo"`≠`'ativo'` gera 0 (aguarda decisão do Jordan; mexe em folha + efeito massa).
- **Portal, não-redesign (8):** `portal/my-payslips/*/pdf`, `portal/self-service/meu-espelho|meus-documentos|meus-holerites*` — app do funcionário.
- **vazio-real (≈9):** `reimbursements/attachments/{id}/download` (`reimbursement_attachments`=0), pipeline `hr/payroll/.../exports/*` (`payroll_exports`=0, 5 rotas), `esocial/receipt` (`esocial_receipts` não existe). Endpoint existe, sem dado → não wirar botão morto (aguarda dado).
- **Redundante (1):** `hr/payroll/employee/{id}/payslip-pdf` = o `doc("Holerite")` que a tela **folha já expõe** (`/dp/payslips/{id}/pdf`).
- **Falso-órfão (1):** `sst/ppp/{id}/pdf` — exposto no clássico (`sst.ts`), âncora curta.

## Próximo
Geradores esgotados. O gap-redesign restante do DP é **159 ações (WRITE)** + **163 GET-only** (parte já coberta via SQL nos builders). Próxima frente: triar os GET-only para **telas de leitura faltantes** (baixo risco, padrão tabela) e depois as ações seguras (admin CCT etc.), deixando folha/dinheiro/integrações para decisão. Medir progresso pela queda das órfãs `--surface redesign`. Atualizar este relatório a cada rodada.
