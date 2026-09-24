# DGX Y5 — o que o COLABORADOR vê de tudo isso

**Branch:** `dgx/y5-portal-colaborador` · **Módulo:** portal · **Data:** 24/09/2026
**Sandbox:** `conecta_pro_staging` · container `teste-dgx-y5` (porta 8275, parado no fim)

---

## §1 — O inventário honesto (o entregável mais importante)

### 1.1 As três coisas com nome parecido que NÃO são a mesma

| Onde | O que é | Lê o quê |
|---|---|---|
| `/modulos/meu-espaco` | **o portal VIVO.** Página escrita à mão, 3166 linhas, `frontend/src/app/modulos/meu-espaco/page.tsx` | chama `/api/v1/people-management/portal/self-service/*` direto (constantes `SS_BASE`/`PONTO_BASE`/`REEMB_BASE`) + `/api/v1/signatures/*` |
| `/redesign/portal-do-funcionario` | ModuleView genérico | `GET /api/v1/redesign/data/portal-do-funcionario` → builder `portal_do_funcionario.py` |
| `/redesign/meu-espaco` | ModuleView genérico, outro slug | JSON estático `frontend/src/app/redesign/_modules/meu-espaco.json` |

Em 22/09 o Jordan mandou 46 pessoas para «Meu Espaço → Meus pagamentos». A tela existia no
**redesign**; as pessoas abrem `/modulos/meu-espaco`. A confusão está documentada no próprio
docstring de `meus_pagamentos` no `self_service_controller.py`. **Medido hoje:** `meus-pagamentos`
também não estava no menu do redesign — a rota existia, a tela não. Esta frente pôs a aba.

### 1.2 O que o colaborador vê hoje — abas e rotas REAIS

Token de colaborador de verdade (senha = dígitos do CPF), duas contas do sandbox,
`GET` em toda a superfície. Todas as 18 rotas abaixo responderam **200**.

**Abas da página escrita à mão** (`TABS`, `page.tsx:97-114`), na ordem: Documentos a assinar ·
Comunicados · Minha escala · Holerite · Meus pagamentos · Documentos · Férias · Ponto ·
Benefícios · Reembolso · Treinamentos · Ouvidoria · Meus dados.

Base: `/api/v1/people-management/portal` (aggregator) → `self-service` (controller).

| Rota | Status medido | Observação |
|---|---|---|
| `/self-service/me` | 200 | dashboard pessoal |
| `/self-service/meus-dados` · `PUT` | 200 | |
| `/self-service/onboarding-status` | 200 | |
| `/self-service/meu-ponto` · `/ponto-hoje` | 200 | |
| `/self-service/facial/{referencia,cadastrar,batida}`, `/tentativa-falhou`, `/batida-contingencia` | — | batida facial |
| `/self-service/meus-beneficios` | 200 | tipo/operadora/desconto — **sem dizer por qual regra** |
| `/self-service/meus-documentos` + `/{id}/download` | 200 | `ged_kit_documents`, ownership conferido |
| `/self-service/meus-holerites` + `/{m}/{a}` + `/{m}/{a}/pdf` | 200 | detalhe **todo em branco** (ver 1.4) |
| `/self-service/meus-treinamentos` | 200 | |
| `/self-service/minha-escala` + `/proximo-turno` | 200 | |
| `/self-service/minhas-ferias/saldo` · `/solicitacoes` | 200 | **sem recibo, sem aviso** — e `/solicitacoes` devolvia **`[]`** para quem tinha 3 férias (ver 1.4 iii) |
| `/self-service/minhas-notificacoes` + `/{id}/lida` | 200 | |
| `/self-service/meus-pagamentos` | 200 | traz `pix_e2e_id`; a tela mostrava como texto solto |
| `/self-service/meus-reembolsos` · `/categorias-reembolso` · `/solicitar-reembolso` | 200 | |
| `/self-service/ouvidoria/minhas` + `POST /ouvidoria` | 200 | |
| `/self-service/meu-espelho/{m}/{a}/pdf` | 200 `%PDF` | **já é o mesmo do DP** (ver §4d) |
| `/signatures/meus-pendentes` + `/assinar-lote` | 200 | 1ª aba do Meu Espaço; genérica por `signer_id` |

**Builder do redesign** `portal_do_funcionario.py` (`build`, escopado por `_resolve_me`):
16 telas — dashboard, contracheque, ferias, ponto, beneficios, escalas, documentos,
treinamentos, dados-pessoais, ouvidoria, comunicados, bater-ponto, assinaturas-pendentes,
contracheques-ged, meus-direitos-cct, calculadora-rescisao.

### 1.3 O que EXISTE no sistema e ele NÃO via

| Coisa | Quem construiu | Por que ele não via |
|---|---|---|
| **Recibo de férias** | U2 | só `GET /api/v1/redesign/ferias/{vid}/recibo/pdf`, namespace do escritório, sem porta no portal |
| **Aviso de férias (PDF)** | U2 | idem `.../aviso/pdf`. *A fila de assinatura já funcionava* — `document_type='aviso_ferias'` entra em `sig_signature_requests` e `meus-pendentes` é genérica |
| **Crachá com foto** | F6 (gerador) + T1 (foto) | só `GET /api/v1/redesign/crachas/pdf?ids=` (lote do DP) |
| **Status da justificativa** | ponto (`gp_justifications`) | **nenhuma rota do portal**. 13 justificativas no sandbox, todas `pendente`, a mais antiga de 21/07 — quem escreveu nunca mais viu |
| **Por qual regra o benefício é concedido** | F3 (`beneficio_tipos`) | `/meus-beneficios` mostrava «Plano Odontológico · R$ 9,00» e ninguém sabia de onde saía o 9,00 |
| **Comprovante do pagamento** | financeiro | `pix_e2e_id` vinha no JSON e a tela imprimia como texto; sem coluna, sem cópia |
| **Espelho de ponto** | DP | **já estava lá** e é o mesmo PDF do DP — a única coisa desta lista que não faltava |

### 1.4 Três achados que valem mais que o inventário

**(i) VAZAMENTO real, provado.** `GET /api/v1/redesign/ferias/{vid}/recibo/pdf`, `.../aviso/pdf`
e `GET /api/v1/redesign/crachas/pdf?ids=` pediam só `CurrentActiveUser`. Medido: o token do
colaborador **B** baixou o recibo, o aviso e o crachá de **A** — HTTP 200, `%PDF`, 37 KB.
`CurrentActiveUser` prova que você entrou, não que o papel é seu.

**(ii) O holerite do colaborador saía em branco.** `hr_payslips.earnings/deductions` guarda as
chaves em **português** (`descricao`/`valor`/`referencia`/`codigo`); `payslip_portal_service.
_to_portal_dict` só lia as em inglês. Resultado em `/meus-holerites/7/2026`: **10 linhas com
descrição `""` e R$ 0,00**, com o líquido certo no topo. O total nunca denunciou porque vem de
outro campo. (`_is_total_row` já lia `descricao` — alguém consertou metade.)

**(iii) A aba Férias do portal estava VAZIA para todo mundo, com HTTP 200.**
`GET /self-service/minhas-ferias/solicitacoes` delegava a `my_vacations_controller.
get_vacation_requests`, que lia `modules.operacional.vacations.models.VacationRequest` — a
**cópia morta** `employee_vacation_requests`, que parou em 01/04 com pedidos presos em
SUBMITTED (o próprio builder do portal já comenta que a autoritativa é `hr_vacation_requests`).
Pior: o campo `dias` dessa cópia guarda **texto** («15 dias») e o schema pede `int`; a validação
estourava, o `except (ImportError, Exception)` engolia e a função devolvia `[]`. Medido: um
colaborador com **3 férias** recebia `200` com lista vazia. Zero não é a mesma coisa que nenhum.
Consequência colateral: os `id` que a tela mostrava eram os da cópia — **não** casariam com
`/minhas-ferias/{vid}/recibo/pdf`. Sem consertar isto, o botão de recibo daria 404.

**(iv) Quatro controllers do portal são casca vazia.** `my_profile_controller.py`,
`my_schedules_controller.py`, `my_documents_controller.py` e `my_comunicados_controller.py`
anunciam endpoints no docstring e **não têm um único `@router.`** — só `APIRouter(tags=…)`.
Estão no `aggregator` e no `__all__`. Não quebram nada (o self-service cobre tudo), mas o
`__init__` promete o que não existe. Não apaguei: memória da casa (09/09) é que apagar
`my_*_controller` derrubou o Meu Espaço por import tardio.

---

## §2 — O que o DGX tem

O DGX dá ao colaborador o **espelho**, o **recibo**, o **aviso** e o **crachá** pela mesma
porta por onde ele bate ponto — não há «pede ao DP». O que faltava aqui não era o documento:
era a **porta escopada**. Nenhum gerador novo foi escrito nesta frente.

---

## §3 — O que foi feito

### Arquivos

| Arquivo | O quê |
|---|---|
| `backend/core/auth/module_scope.py` | **+ `exigir_dono(user, employee_id, modulo='dp')`** — quem não tem o módulo só alcança o PRÓPRIO cadastro. 404, não 403 (403 confirmaria que o documento existe). |
| `…/redesign_builders/_dgx_u2_ferias.py` | `exigir_dono` em `rd_recibo_pdf` e `rd_aviso_pdf` + helper `dono_da_ferias`. **Toque fora do módulo, declarado.** |
| `…/redesign_builders/_dgx_f6_dp.py` | `exigir_dono` por id em `rd_crachas_pdf_get`. **Toque fora do módulo, declarado.** |
| `…/employee_portal/controllers/self_service_controller.py` | 4 rotas novas + `regra` e `competencia` em `/meus-beneficios` |
| `…/employee_portal/services/payslip_portal_service.py` | lê as chaves em PT (`descricao`/`valor`/`referencia`/`codigo`) além das em inglês |
| `…/employee_portal/controllers/my_vacations_controller.py` | `get_vacation_requests` passa a ler `hr_vacation_requests` (a autoritativa) por SQL, sem `except` que devolve `[]` |
| `…/redesign_builders/_dgx_y5_portal.py` **(novo)** | pendura os botões e as 2 telas no builder do portal |
| `…/redesign_builders/portal_do_funcionario.py` | plug: 1 import + `*_y5.EXTRA_MENU` + `await _y5.telas(...)` |
| `backend/scripts/orq/test_oraculo_y5_portal_colaborador.py` **(novo)** | o oráculo |

### Rotas novas — todas escopadas pelo TOKEN

Nenhuma recebe id de pessoa no caminho nem no corpo: **não há o que forjar.**

| Rota | O que entrega |
|---|---|
| `GET /…/portal/self-service/meu-cracha/pdf` | crachá do logado, com foto (`cracha_pdf.montar_crachas`) |
| `GET /…/portal/self-service/minhas-ferias/{vid}/recibo/pdf` | recibo U2; férias de outro → **404** |
| `GET /…/portal/self-service/minhas-ferias/{vid}/aviso/pdf` | aviso U2; férias de outro → **404** |
| `GET /…/portal/self-service/minhas-justificativas` | o que ele escreveu + `situacao` (Em análise pelo DP / Aprovada / Não aceita) |

### Telas (deep-link `/redesign/portal-do-funcionario?t=<id>`)

| `t=` | Grupo | O que mudou |
|---|---|---|
| `dados-pessoais` | (base) | botão **Meu crachá** |
| `ponto` | (base) | botões **Espelho MM/AAAA** do mês corrente e do anterior |
| `ferias` | (base, sobrescrita) | por linha aprovada: **Recibo** e **Aviso** |
| `beneficios` | (base, sobrescrita) | coluna **Como é concedido** (`beneficio_tipos`, F3) |
| `meus-pagamentos` | **EXTRA_MENU (novo)** | coluna **Comprovante** (`pix_e2e_id`) |
| `minhas-justificativas` | **EXTRA_MENU (novo)** | enviada / tipo / motivo / situação / decidida em |

**DDL: nenhuma.** Esta frente não cria tabela nem coluna — não há `_ensure` para rodar em
produção no 1º acesso. Só leitura de `hr_vacation_requests`, `gp_justifications`,
`employee_benefits`, `beneficio_tipos`, `payroll_payments`, `employees`.

**Zero mudança em `frontend/`.** O shell do redesign já renderiza `docs` (DocButtons → fetch
com Bearer → `a.download`) e `type: table`; bastou o backend emitir.

---

## §4 — Oráculo

`backend/scripts/orq/test_oraculo_y5_portal_colaborador.py` — mede a **saída**, de fora, com
token de colaborador de verdade (senha = dígitos do CPF), dois colaboradores A e B.

```bash
docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" \
  -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env \
  -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \
  -e Y5_BASE=http://teste-dgx-y5:8080 \
  conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_y5_portal_colaborador.py
```

### Vermelho (antes do código) — `TOTAL y5: 10`

```
A = ADAILSON SERRA ALVES (2430761d…)  ·  B = ADEILSON DINIZ DEODATO (f5c6e91a…)

[a] vazamento entre colaboradores
  ✗ /…/self-service/minhas-justificativas → 404 (rota do portal não existe)
  ✓ 21 rotas do portal: nenhuma trouxe id/nome/CPF de B
  ✗ B baixou o recibo de férias de A (/api/v1/redesign/ferias/51b2fa36…/recibo/pdf → 200)
  ✗ B baixou o aviso de férias de A (/api/v1/redesign/ferias/51b2fa36…/aviso/pdf → 200)
  ✗ B baixou o crachá de A (/api/v1/redesign/crachas/pdf → 200)

[b] aviso de férias na fila de assinatura do colaborador
  ✓ o aviso de férias entra na fila «documentos a assinar» do dono
  ✓ o aviso de A não aparece na fila de B

[c] crachá, recibo e aviso pelo portal do próprio colaborador
  ✗ meu crachá: HTTP 404, começa com b'{"detail'
  ✗ meu recibo de férias: HTTP 404, começa com b'{"detail'
  ✓ B leva 404 ao pedir «meu recibo de férias» de A pela rota do portal
  ✗ meu aviso de férias: HTTP 404, começa com b'{"detail'
  ✓ B leva 404 ao pedir «meu aviso de férias» de A pela rota do portal

[d] espelho do colaborador × espelho do DP (mesma fonte)
  ✓ espelho 09/2026: texto do portal IDÊNTICO ao do DP (1742 chars)

[e] conferência interna não vaza para o colaborador
  ✓ nenhuma das rotas do portal cita folha_/ponto_/banco_horas_conferencia

[f] o que o colaborador passa a ver
  ✗ 3 benefício(s) sem a regra de concessão
  ✗ /minhas-justificativas → HTTP 404
  ✗ holerite 07/2026: 10 sem descrição

fixtures 'FIXTURE DGX Y5' restantes: 0

TOTAL y5: 10
```

### Verde (depois) — `TOTAL y5: 0`

```
[a] vazamento entre colaboradores
  ✓ 21 rotas do portal: nenhuma trouxe id/nome/CPF de B
  ✓ B NÃO baixa o recibo de férias de A (HTTP 404)
  ✓ B NÃO baixa o aviso de férias de A (HTTP 404)
  ✓ B NÃO baixa o crachá de A (HTTP 404)

[b] aviso de férias na fila de assinatura do colaborador
  ✓ o aviso de férias entra na fila «documentos a assinar» do dono
  ✓ o aviso de A não aparece na fila de B

[c] crachá, recibo e aviso pelo portal do próprio colaborador
  ✓ meu crachá: 200 e %PDF (35 KB)
  ✓ meu recibo de férias: 200 e %PDF (37 KB)
  ✓ B leva 404 ao pedir «meu recibo de férias» de A pela rota do portal
  ✓ meu aviso de férias: 200 e %PDF (37 KB)
  ✓ B leva 404 ao pedir «meu aviso de férias» de A pela rota do portal

[d] espelho do colaborador × espelho do DP (mesma fonte)
  ✓ espelho 09/2026: texto do portal IDÊNTICO ao do DP (1742 chars)

[e] conferência interna não vaza para o colaborador
  ✓ nenhuma das rotas do portal cita folha_/ponto_/banco_horas_conferencia

[f] o que o colaborador passa a ver
  ✓ 3 benefício(s) dizem por qual regra são concedidos
  ✓ minhas férias: 3 na tela == 3 em hr_vacation_requests
  ✓ minhas justificativas: 0 com status visível
  ✓ holerite 07/2026: 10 linha(s) com descrição e valor

fixtures 'FIXTURE DGX Y5' restantes: 0

TOTAL y5: 0
```

> A linha «minhas férias» foi acrescentada ao oráculo **depois** da rodada vermelha, quando
> o achado (iii) apareceu nos logs. Contra o código anterior ela dá
> `✗ minhas férias: 0 na tela × 3 em hr_vacation_requests` — o vermelho de nascimento
> completo seria **11**, não 10.

Fixture: **1 linha** em `sig_signature_requests` (`document_name LIKE 'FIXTURE DGX Y5%'`),
apagada no fim — contagem final impressa é 0.

**Sobre (d):** os dois PDFs vêm do MESMO `ler_espelho`/`montar_espelho_ponto_pdf`; a única
diferença de código é que o portal chama `calcular_espelho` sob demanda quando o DP ainda não
fechou o mês. `cmp` dos bytes diverge só no trailer do ReportLab (mesmos 39 394 bytes); o
**texto extraído é idêntico**, que é o que a pessoa lê.

**Ressalva honesta:** a linha «minhas justificativas: 0 com status visível» é vacuamente verde
— o colaborador A do sandbox não tem justificativa. Conferido à mão com quem tem
(ANTONIO CARLOS CASTRO GAMA, 1 pendente de 17/09): a rota devolve `total:1`, `pendentes:1`,
`situacao:"Em análise pelo DP"`, e a tela `minhas-justificativas` do redesign traz `rows=1`.

---

## §5 — O que NÃO foi feito (e o diff de `frontend/` que ficou pendente)

### 5.1 O diff de `frontend/` — a página escrita à mão não muda sozinha

`/redesign/portal-do-funcionario` **já mostra tudo isto hoje, sem tocar no frontend**. Mas
`/modulos/meu-espaco` — o portal que as pessoas realmente abrem — é escrito à mão e só mostra
o que o código dele chama. Ficou pendente para o orquestrador, em
`frontend/src/app/modulos/meu-espaco/page.tsx`:

1. **`TABS` (L97-114)** — acrescentar uma aba:
   ```ts
   { key: 'justificativas', label: 'Minhas justificativas' },
   ```
   e um `case 'justificativas'` que busca
   `GET ${SS_BASE}/minhas-justificativas` e renderiza
   `justificativas[] → {enviada_em, tipo, motivo, situacao, decidida_em}`.
   Cores: `pendente` âmbar, `aprovada` verde, `rejeitada` vermelho.

2. **Aba Férias (≈L845)** — hoje só `saldo` + `solicitacoes`. Para cada solicitação com
   `status === 'APPROVED'`, dois botões usando o MESMO `baixarPdf` que já existe em L785:
   ```ts
   `${SS_BASE}/minhas-ferias/${f.id}/recibo/pdf`
   `${SS_BASE}/minhas-ferias/${f.id}/aviso/pdf`
   ```
   ✔ o `id` devolvido agora é o de `hr_vacation_requests` (§1.4 iii), que é exatamente o que
   essas duas rotas esperam. Antes desta frente era o da cópia morta e daria 404.

3. **Aba Meus dados (≈L2388)** — um botão «Meu crachá» com o mesmo `baixarPdf`, apontando
   para `${SS_BASE}/meu-cracha/pdf`.

4. **Aba Benefícios (≈L1917)** — o JSON agora traz `regra` por benefício e `competencia` no
   topo. Uma linha de texto sob cada benefício.

5. **Aba Meus pagamentos (L1900-1902)** — `comprovante` é impresso como texto solto. Virar um
   campo copiável (`navigator.clipboard`) com rótulo «Comprovante (procure no seu extrato)».

6. **Cosmético, os três downloads da página (L785, L1700, L2139)** abrem
   `window.open(URL.createObjectURL(b))` sem `a.download` — o arquivo salva com nome de blob.
   Trocar pelo helper `abrirPdf` de `frontend/src/lib/pdf.ts`, que o redesign já usa.

### 5.2 O que deliberadamente NÃO fiz

- **Não apaguei os 4 controllers-casca** (`my_profile`, `my_schedules`, `my_documents`,
  `my_comunicados`). Em 09/09 apagar `my_*_controller` derrubou o Meu Espaço por import
  tardio. Ficam registrados aqui; a limpeza é decisão de quem tiver o mapa inteiro.
- **Não liguei benefício × competência com número próprio.** O que o colaborador recebeu na
  competência já está no **holerite** (agora legível). Um segundo número calculado por outro
  caminho ia acabar contradizendo o holerite na tela da própria pessoa.
- **Não toquei em `folha_beneficio_conferencia`, `ponto_folha_conferencia` nem
  `banco_horas_conferencia`.** São a nossa apuração paralela. O oráculo trava isso.
- **Não mexi na fila de assinatura.** Ela já era genérica e já pegava o `aviso_ferias` da U2;
  o oráculo só provou que pega — e que não pega o dos outros.
- **Não corrigi os 102 cadastros de benefício** cujo `employee_benefits.employee_contribution`
  diverge da regra (51 odonto + 51 seguro de vida — ver §7). Corrigir muito registro de uma vez
  sem achar a regra é como se erra grande.
- **Não mexi em `checar_regressao.py`** — o orquestrador registra o oráculo.

---

## §6 — Como o Jordan testa amanhã

1. Entrar como colaborador (e-mail dele, **senha = os 11 dígitos do CPF, sem ponto nem traço**).
2. `/redesign/portal-do-funcionario` → aba **Meus dados** → botão **Meu crachá** → baixa um PDF
   com foto, nome de guerra e CPF mascarado.
3. Aba **Ponto** → botões **Espelho 09/2026** e **Espelho 08/2026** no topo da tela.
4. Aba **Férias** → numa linha *Aprovada*, os botões **Recibo** e **Aviso** na coluna da direita.
5. Aba **Benefícios** → coluna **Como é concedido**: «Desconto de 4% sobre o salário base».
6. Aba **Meus pagamentos** (menu novo) → coluna **Comprovante** com o e2e do Pix.
7. Aba **Minhas justificativas** (menu novo) → o que ele escreveu e **Em análise pelo DP**.
8. Aba **Holerite** (ou `/modulos/meu-espaco` → Holerite → um mês) → agora as linhas têm nome
   e valor: «DIAS NORMAIS · 30,00 · R$ 1.670,00», e não 10 linhas em branco valendo zero.
9. A prova do vazamento fechado: pegue o link do **Recibo** de um colaborador e abra logado como
   **outro** colaborador → **404**. Com a conta do Jordan (módulo DP) → abre normal.

---

## §7 — Decisões que só o dono pode tomar

1. **Benefício: o cadastro diverge da regra, em 51 pessoas.** `employee_benefits` diz odonto
   R$ 9,00 (51 cadastros) e seguro de vida R$ 4,00 (51 cadastros); `beneficio_tipos` (F3,
   derivado do `calculo_service`) diz R$ 8,50 e R$ 2,00; e o holerite de 07/2026 **não tem
   nenhuma das duas linhas**. Três fontes, três respostas.
   A tela hoje mostra o cadastro rotulado «Desconto (cadastro)» e a regra ao lado, sem escolher.
   **Qual é a verdade?** Enquanto não houver resposta, a pessoa vê as duas.
2. **Holerite duplicado.** `hr_payslips` tem **duas** linhas de 07/2026 para o mesmo
   colaborador (uma com códigos da Domínio — `8781`, `998` —, outra com os códigos internos —
   `0001`, `1010`). O portal mostra a primeira que vier. Não é frente minha, mas o colaborador
   é quem vê.
3. **Recibo de férias não é persistido** (é recalculado a cada abertura — decisão registrada
   pela U2 §7). Se o colaborador baixar hoje e o DP alterar os dias amanhã, o mesmo link dá
   outro papel. Vale congelar quando ele assinar?
4. **O recibo de férias não entra na fila de assinatura** (só o aviso). Foi decisão da U2.
   Confirmar que segue valendo agora que o colaborador consegue baixá-lo.
5. **Os 4 controllers-casca do portal** (§1.4 iv): apagar, ou preencher?
6. **A cópia morta `employee_vacation_requests`** (§1.4 iii) continua no banco e num model
   (`modules/operacional/vacations/models`). O portal não lê mais dela. Apagar tabela e model,
   ou manter como arquivo histórico? Não apaguei nada — não é dado que eu criei.
