# Paridade CRUD do DP redesign (todas as telas) — Design

Aprovado por Jordan 25/07. Missão: o redesign do Departamento Pessoal precisa das **mesmas capacidades do clássico** — criar, ver detalhe, editar, alterar, incluir, admitir, agir — não só tabelas read-only. Padrão-alvo = tela `rescisao` (ações por-linha) + CTAs que funcionam. Superpowers; loop autônomo; forma delegada.

## Diagnóstico (verificado no /data/departamento-pessoal)
Telas hoje (type · cta · ctaTo · ação):
- `visao` dash · "Nova admissão" · **ctaTo=None (morto)** · 0 linhas
- `funcionarios` table · "Nova admissão" · **morto** · 49 linhas · **sem ação por-linha**
- `admissao` table · "Nova admissão" · **morto** · 3 linhas · **sem form de admissão**
- `aviso-previo` table · vazio
- `folha-rubricas` table · só visual (400 linhas)
- `rescisao` table · rowDocs=True (TRCT/Aviso por-linha) = **o padrão certo**

Regressão: o redesign perdeu a capacidade de AGIR. Backend TEM os endpoints (só não religados).

## Mecanismos existentes (reusar)
- **Form de tela** `{type:"form", fields:[...], submit:{endpoint}}` → FormScreen posta `{...vals}` (Bearer) direto no endpoint. Chaves dos fields = schema do endpoint → CREATE sem wrapper. Tipos suportados: text, date, select, textarea (number→text).
- **Ação/doc por-linha** `docsfn=lambda r:[doc(...)]` → botões por linha (documentos/ações). É o que `rescisao` tem.
- **CTA** `scr.ctaTo` → ModuleView mostra o botão se `ctaTo && screens[ctaTo]` e navega.
- **EXTRA_MENU** (lista no builder) → telas de ação no nav.

## Falta na fundação (construir 1×, reutilizável)
- **Editar/ver por-linha:** hoje não há como abrir um form **pré-preenchido com os dados da linha** para editar. Design: `editfn(r)` no `tbl` (como `docsfn`) → devolve `{endpoint(PATCH), fields:[{key,label,type,value}]}`. ModuleView renderiza um botão "Editar" por-linha que abre o form pré-preenchido (inline/painel) → PATCH no endpoint. Aditivo/retrocompatível (linhas sem editfn não mudam). Isto destrava "clicar → ver → editar" em TODAS as telas.

## Endpoints reais disponíveis (amostra — nunca inventar)
- Admissão: `POST /hr/admissions` (candidate_name*, cpf*, position*, department, salary_proposed, expected_start_date, contract_type, birth_date, pis_pasep, notes), `PATCH /hr/admissions/{id}`, `/complete`, `/documents`.
- Empregado: `PATCH /hr/employees/{id}` (editar), `POST /hr/employees/{id}/deductions`.
- (Cada tela: mapear o endpoint do clássico antes de wirar.)

## Plano (loop, tela por tela, ordem por dor)
1. **Fundação — per-row edit/detail** no ModuleView (`editfn` + botão + form pré-preenchido → PATCH). Build+deploy+verificar no browser.
2. **Admissão** (dor #1): form `nova-admissao` + EXTRA_MENU + religar CTAs mortos (visao/funcionarios/admissao → ctaTo). Verificar: criar admissão real (candidato de teste) → 201.
3. **funcionarios:** per-row **Ver/Editar** (`editfn`→PATCH /hr/employees/{id}) + incluir (CTA admissão).
4. **CTAs mortos** das demais telas → apontar pros forms/ações certos.
5. **aviso-previo** e telas restantes → suas ações reais (mapear clássico → endpoint → wirar).

## Regras (inegociáveis)
- Só endpoints REAIS; nunca inventar ação/dado. Cada ação **curl-verificada** (201/200) + testada no browser (clicar/criar/editar) = oráculo "faz o que o clássico faz".
- Dinheiro/OTP e operacional **intocáveis**; folha sensível.
- Commit por pathspec (meu território: `redesign_builders/departamento_pessoal.py`, `ModuleView.tsx` fundação, handlers em `redesign_data_controller.py` se preciso). NÃO tocar arquivos do T1 (`_fin_*`, financial, banking). Commitar antes de deploy; coordenar bake.

## Verificação (gate)
Por tela: no browser, o botão faz o que promete (cria/edita/mostra) e o dado bate no banco. Progresso = telas com capacidade real / total.

## Artefatos
Spec (este) → writing-plans → execução no builder + ModuleView. Sem PII em git.
