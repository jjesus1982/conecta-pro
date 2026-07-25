# Recon financeiro — veredito das afirmações (2026-07-25)

Skill `conecta-backend-recon`, prefixo `financial`, `--surface redesign`. Cruza rotas montadas × superfície do redesign.

## Números
- **666 rotas montadas · 351 EXPOSTAS (53%) · 315 ÓRFÃS (47%) · 3 geradores órfãos.**
- Órfãs de AÇÃO (POST/PUT/DELETE): **147** = o gap acionável real (GET órfão o builder cobre via SQL direto — o `--surface redesign` superestima o gap de GET).

## As afirmações batem? → SIM (com 1 ajuste e 1 miss)

**HOLD — confirmado órfão (não exposto), como eu disse:**
- Fechamento/contabilidade: `POST /accounting/journal-entries`, `/accounting/periods/{id}/reopen`, `/accounting/charts`, `/accounting/cost-centers` — órfãos. Onda 2 ✅.
- Apuração: `GET /relatorios/apuracao-lucro-real`, `/accounting/dre-consolidado` — órfãos (existem, sem tela redesign). Onda 2 ✅.
- OFX/import: `POST /bank-transactions/import/ofx`, `/bank-reconciliations/{id}/import-statement` — órfãos (eu disse "UI OFX falta") ✅.
- AI billing: `/ai/advisor`, `/ai/billing/*` — órfãos.

**FALSO ÓRFÃO (o recon errou, eu estava certo):**
- `GET /relatorios/dre/pdf` — recon flagou órfão, mas o redesign TEM o botão via `doc("DRE (PDF)", ".../dre/pdf?ano={_ano}")` em relatorios.py:36 / financeiro.py:646 / empresas.py:73. A URL com `?ano=` variável quebra a heurística de âncora (falso-órfão conhecido da skill). **Minha afirmação "DRE+PDF real" HOLD.**

**MISS meu (recon pegou, eu não flaguei):**
- `GET /fiscal/nfse/{id}/danfse` (DANFSE — PDF da NFS-e por linha) — **órfão de verdade** (grep "danfse" no redesign = vazio). Gerador de documento sem botão no redesign fiscal. É fiscal (sessão paralela já mapeou em fiscal_redesign_gap). Wiring de botão `doc()` — barato.

## Nota metodológica
- Minhas entregas da Onda 1 (conciliar-liquido, registrar-cobranca, cobrar-recorrente, enviar-pix, balanço, orçado×realizado…) são prefixo `/redesign/action/*` + telas de builder (leem SQL) — **outro prefixo**, não aparecem neste recon de `/financial`. Foram verificadas à parte pelo **E2E no navegador** (renderizam + funcionam, 0 erros).
- Este recon prova o backlog **Onda 2/3** (as ~147 ações órfãs + geradores) — que é o que eu disse faltar.

## Veredito
**As afirmações holdam.** O financeiro ficou muito mais exposto (53% das rotas /financial + 100% do que construí no /redesign), MAS 47% das rotas /financial seguem órfãs (Onda 2/3) e há geradores sem botão (DANFSE). Nada que afirmei "funciona" se provou casca/quebrado no recon; o único ajuste é o DANFSE (gap fiscal, não financeiro-core). **→ Podemos ir pra Onda 2, depois Onda 3.** Folding: o botão DANFSE entra no escopo fiscal (ou fica com a sessão paralela).
