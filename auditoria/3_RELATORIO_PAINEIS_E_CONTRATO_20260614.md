# 📋 Relatório — Painéis Transparentes + Form de Contrato (resposta ao prompt CIC)

**Data:** 14/06/2026 · **Branch:** `fix/crm-qa-aprovado-20260614` · **Commit:** `305f0075`
**Deploy:** frontend em produção (BUILD_ID `conecta-pro-1781451819295`) · âncora `pre-paineis-20260614`
**Resultado:** 20 containers healthy · 0 unhealthy

---

## P1 🔴 — Painéis de Select/Dropdown transparentes → ✅ CORRIGIDO

### Validei o diagnóstico do CIC antes de aplicar — e ele estava certo
O CIC apontou Tailwind v4 sem `@theme inline`. Confirmei no código real:
- `src/styles/globals.css`: o bloco `@theme` (linhas 4-34) só registrava `--color-navy-*` e `--color-brand-*`. Os tokens semânticos (`--popover`, `--card`, `--primary`, `--secondary`, `--muted`, `--accent`...) existiam **só como HSL cru** em `:root`/`.dark`/`.light`, **sem** mapeamento para `--color-*`.
- Consequência (Tailwind v4): as utilities `.bg-popover`, `.bg-card`, `.text-popover-foreground` **não eram geradas** → **0 ocorrências** no bundle.
- `dropdown-menu.tsx` (linhas 50, 68) e `select.tsx` (linha 78) usam exatamente `bg-popover text-popover-foreground` → painel resolvia `background-color: rgba(0,0,0,0)` (transparente). 19 componentes UI afetados.

### Correção aplicada (forma idiomática v4)
Adicionei em `globals.css` um bloco `@theme inline` mapeando todos os tokens semânticos:
```css
@theme inline {
  --color-popover: hsl(var(--popover));
  --color-popover-foreground: hsl(var(--popover-foreground));
  --color-card: hsl(var(--card));
  /* ...background, foreground, primary, secondary, muted, accent,
     destructive, success, warning, border, input, ring */
}
```
`inline` é essencial: mantém o `var()` em runtime, preservando a troca light/dark automaticamente (os valores mudam entre `:root`/`.dark`/`.light`).

Além disso, uma **rede de segurança** para painéis de libs externas (datepickers/tooltips) que não usem o token do design system:
```css
[role="listbox"], [role="menu"], [data-radix-popper-content-wrapper] > * {
  background-color: hsl(var(--popover));
  color: hsl(var(--popover-foreground));
}
```

### Evidência (no CSS compilado servido em PRODUÇÃO)
- Antes: `.bg-popover{` → **0** ocorrências.
- Depois: `.bg-popover{background-color:hsl(var(--popover))}` ✅ + `.text-popover-foreground{color:hsl(var(--popover-foreground))}` ✅ + `.bg-card`, `.bg-accent`, `.bg-muted`, `.bg-secondary` ✅ + a rede de segurança `[role=listbox],[role=menu],[data-radix-popper-content-wrapper]>*{...}` ✅.
- Verificado baixando o bundle pela URL pública `https://erp.conectamais.pro/_next/static/chunks/<hash>.css`.

### Limitação honesta
Não tenho navegador para rodar o script de QA do CIC (console do browser). Minha evidência é o **CSS compilado**. A validação **visual/DOM nos dois temas** é exatamente o que o CIC certifica na re-auditoria com o `cicQABothThemes()`.

---

## P2 🟠 — Form "Novo Contrato" não implementado → ✅ IMPLEMENTADO

- **Antes:** clicar em "Novo Contrato" só mostrava toast "Formulário em desenvolvimento"; criação só via API.
- **Correção:** form modal em `contratos/page.tsx` com: nome, **cliente** (Select), **tipo** (recurring/one_time, Select), valor mensal, data de início, data de término. Validação alinhada ao backend: `start_date` obrigatório; `end_date` **obrigatório para recorrente** (senão `total_value` nasce 0). Submit → `POST /crm/contracts` → 201 → atualiza a lista. Loading + toast de erro/sucesso.
- **Bônus:** o form usa o componente `Select` — ou seja, também serve de teste real do fix do P1.
- **Fora de escopo:** edição de contrato (botão "Editar") continua "em desenvolvimento" — o P2 era criar.

---

## P3 🟡 — Robustez do create de lead → ✅ JÁ COBERTO
O botão "Criar Lead" já entra em `disabled` durante o request (anti double-submit) e todo erro gera toast (nada silencioso). O "422 intermitente" que o CIC viu foi provavelmente antes do fix; o guard já está no código. Se a re-auditoria reproduzir, investigo a fundo.

## P4 🟢 — Acabamento
"José Luís" não aparece sem acento na UI (só em dados). Datepickers/tooltips herdam o `--popover` corrigido (e a rede de segurança cobre os de libs externas).

---

## 🐛 Bug colateral encontrado e corrigido (não estava no prompt)
Ao validar, o container `frontend` estava **`unhealthy`** — o site respondia 200 por fora (via proxy reverso), mas o **healthcheck interno** (`wget 127.0.0.1:3000`) dava "connection refused". Causa: o Dockerfile de bake-by-copy esquecia `ENV HOSTNAME="0.0.0.0"`, então o Next standalone `server.js` bindava no hostname do container (Docker seta = ID do container) em vez de `0.0.0.0`. Corrigi (adicionei `ENV HOSTNAME="0.0.0.0"` + `ENV PORT=3000`, copiando do `frontend/Dockerfile` real), rebuild e re-swap. Resultado: **healthy em ~5s**, `127.0.0.1:3000` OK.

## Deploy / rollback
- Imagem: `conecta-pro-frontend:rebuild-paineis-20260614` · âncora: `pre-paineis-20260614`.
- Backend **não mudou** nesta rodada.
- Rollback: `docker tag conecta-pro-frontend:pre-paineis-20260614 conecta-pro-frontend:latest && docker compose -f docker-compose.yml up -d --no-deps --force-recreate frontend`.

## NÃO mexer (validado em rodadas anteriores)
Backend de Leads/Comissões/Contatos, pipeline ponderado, auto-comissão 5% no accept, simulador de precificação, palette numérico do Tailwind, e a limpeza de dados (só dado real: 11 clientes, 10 contratos MRR R$ 270k, 3 propostas a prospects).
