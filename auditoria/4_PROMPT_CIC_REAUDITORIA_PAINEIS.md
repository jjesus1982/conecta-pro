# 🔁 Prompt CIC — Re-Auditoria dos Painéis Transparentes + Form de Contrato

> **Cole no CIC.** Ambiente: **PRODUÇÃO** (`https://erp.conectamais.pro`). O fix do P1 (painéis transparentes) já foi aplicado e está no ar. Sua missão: **certificar com o seu próprio script** que todos os painéis estão opacos nas 8 telas, em **light e dark**, e validar o novo form de Novo Contrato. Seja cético — só ✅ com a tabela do script imprimindo `❌ 0`.

---

## Contexto da correção aplicada (para você conferir)
- **Causa raiz confirmada** (você acertou): Tailwind v4 sem `@theme inline`. O `@theme` só registrava `--color-navy/brand`; os tokens semânticos (`--popover` etc.) não viravam `--color-*`, então `.bg-popover` não era gerada → painéis transparentes.
- **Fix:** bloco `@theme inline` em `globals.css` mapeando todos os tokens semânticos para `--color-*` (mantendo `var()` em runtime p/ light/dark) + rede de segurança `[role="listbox"],[role="menu"],[data-radix-popper-content-wrapper] > *`.
- **Evidência server-side:** no CSS de produção, `.bg-popover{background-color:hsl(var(--popover))}` agora existe (antes: 0 regras).
- Também foi implementado o **form de Novo Contrato** (antes era só toast "em desenvolvimento").

## 🔐 Acesso
- `https://erp.conectamais.pro` · `admin@conectapro.com.br` / `admin123`

---

## ✅ P1 — Certificação dos painéis (use seu script `cicQABothThemes()`)
Faça login e, em **cada tela abaixo**, abra o formulário/modal que contém os Selects/Dropdowns e rode `await cicQABothThemes()` no console. O critério é o resumo final imprimir **`❌ 0`** (em light **e** dark):

1. **Dashboard** (`/modulos/crm`) — filtros, se houver.
2. **Leads** (`/modulos/crm/leads`) — abrir o menu **"Ações do lead"** de uma linha + filtros. *(O select "Origem" do Novo Lead é `<select>` nativo — vai dar `⚠️ verificar`, é esperado, ignore.)*
3. **Oportunidades** (`/modulos/crm/oportunidades`) — abrir **"Nova Oportunidade"** (cobre Etapa/Cliente/E-mail/Responsável). *(Obs.: o módulo pode estar sem dados — o importante é o modal abrir e os Selects renderem opacos.)*
4. **Propostas** (`/modulos/crm/propostas`) — abrir o form de nova proposta (cliente/tipo de cobrança/status).
5. **Contratos** (`/modulos/crm/contratos`) — filtro **"Todos os status"** + abrir o **novo form de Novo Contrato** (Cliente, Tipo) — ver P2 abaixo.
6. **Clientes** (`/modulos/crm/clientes`) — filtros/segmento/status.
7. **Contatos** (`/modulos/crm/contatos`).
8. **Comissões** (`/modulos/crm/comissoes`) — regras/status/filtros.

Precificação não tem dropdown (usa cards + toggle) — pular (só validar tooltips, se houver).

**Aprovação P1:** em todas as 8 telas e nos 2 temas, o painel tem `backgroundColor` opaco (≈ `rgb(255,255,255)` no light; o tom escuro no dark), opções legíveis sem vazamento, sombra/borda visíveis. Qualquer `❌ TRANSPARENTE` reprova e aponta o campo exato.

---

## ✅ P2 — Form de Novo Contrato (novo)
- Em **Contratos**, clique **"Novo Contrato"** → deve abrir um **modal** (não mais o toast "em desenvolvimento").
- Preencha: Nome, **Cliente** (Select), **Tipo** = Recorrente, Valor mensal, **Início** (obrigatório), **Término** (obrigatório p/ recorrente).
- **Esperado:** criar → **201**, toast de sucesso, o contrato aparece na listagem com valores corretos.
- Teste a validação: sem `start_date` → deve bloquear com mensagem clara; recorrente sem `end_date` → deve pedir a data de término (para o total não nascer R$ 0).
- ⚠️ **Marque seu contrato de teste com `TESTE_CIC_`** no nome e **remova ao final**.

## ✅ P3 — Robustez do create de lead
- Em **Leads → Novo Lead**, crie **10 leads seguidos** pela UI. Esperado: **todos 201**, zero 422 espúrio, botão entra em loading/disabled durante cada request (sem double-submit), todo erro com toast.
- Marque com `TESTE_CIC_` e limpe ao final.

---

## ⛔ Regras de produção
- **NÃO** delete dados reais; marque testes com `TESTE_CIC_` e **limpe 100% ao final** (confirme contagem 0).
- **NÃO** toque em `.env`, mailer, credenciais, infra, agente José Luís.
- O script de UI **não altera dados** (só abre/fecha menus) — pode rodar à vontade.

## 📦 Entregável
1. **Veredito:** painéis **aprovados sem ressalvas ✅**? (sim/não).
2. **Tabela por tela** (saída do `cicQABothThemes`): tela | tema | ✅/❌ | campos que falharam (se houver).
3. **P2:** form de contrato criou 201? print + evidência.
4. **P3:** 10 criações de lead, quantas 201/422.
5. **Regressões** (se houver) + **confirmação de limpeza** (`TESTE_CIC_` = 0).

> Se algum painel ainda vazar (`❌ TRANSPARENTE`), me diga **a tela, o tema e o campo** exatos (o script já mostra o `rgba(0,0,0,0)`), que eu corrijo o caso específico.
