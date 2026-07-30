# Recon Financeiro × Redesign — 2026-07-30

**Comando:** `backend_recon.py financial --surface redesign`
**Números:** 597 rotas montadas · 336 expostas · 261 órfãs.

## Veredito: cobertura de gerador/documento = 100% (nenhum gap acionável meu)
- 🔴 **Geradores órfãos: 1, e é FALSO** — `GET /financial/relatorios/dre/pdf [key=dre]`. Botão existe em 3 builders (relatorios.py:36, financeiro.py:695, empresas.py:73); o `?ano=` quebra a heurística de âncora. DANFSe (o único gap real) foi fechado nesta leva.
- Tela financeira rodada de verdade (builder×banco): 48/51 tabelas com dado real; 3 vazias = **vazio-real honesto** (Cobranças/Fila: todas receivables 'paga', inadimplência 0; Compras-requisições: purchase_requisitions=0).

## Órfãs restantes = costuras de OUTROS T (passar a bola, NÃO wire)
- **Contábil (37)**: `/financial/accounting/*` (chart/cost-centers/accounts CRUD) → T1/T3.
- **Money-out (~14)**: `payables/bulk-payment`, `installments/{id}/pay`, `renegotiate`, `auto-criar`, `bulk-approve` → **T1 (OTP)**. Redesign roteia por propor→aprovar→OTP; wire cru = afrouxar parede. NÃO tocar.
- **cashflow (17)** e demais GET: os builders leem o banco por SQL direto → falso-órfã.

## Fechado nesta sessão (financeiro)
DANFSe emitida (botão) · BI-dashboard deletado (71 rotas) · credencial MCP sanitizada · schema drift DRE/balanço/apuração · DRE scoping (razão real direto).
