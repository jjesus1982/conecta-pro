# Fiscal — Gap redesign (recon --surface redesign, 2026-07-25)

`backend_recon.py fiscal --surface redesign`. Raw: `fiscal_redesign_gap_2026-07-25.txt`.

## Números
191 montadas · 97 expostas · **94 órfãs** · **3 geradores órfãos**.
⚠️ Órfãs infladas por **double-mount**: muitas rotas aparecem 2× (`.../fiscal/fiscal/...` além de `.../fiscal/...`) — o router monta com prefixo duplicado. O gap REAL de rotas distintas é ~metade.

## Geradores órfãos (candidatos)
- 🔴 **DANFSE** — `GET /financial/fiscal/nfse/{nfse_id}/danfse` 🏛️ (PDF da NFS-e). **Limpo e acionável**: há 831 NFS-e reais; wirar como doc() por-linha na tela de NFS-e do redesign fiscal, padrão do Componente A do DP. (A variante `/fiscal/fiscal/nfse/.../danfse` é o mesmo endpoint via double-mount — verificar qual responde antes.)
- `POST /fiscal/nfe-entrada/upload-xml` 🏛️ — upload de XML de NF-e de entrada (AÇÃO com upload, não doc). Precisa de form de upload.

## Observações p/ execução
- Fiscal vive sob o prefixo `financial` (662 rotas) — módulo **ativo em sessões paralelas** + money-adjacent. Coordenar antes de wirar (evitar colisão no builder fiscal).
- Muitas órfãs `calcular/*` (comparativo-regimes, lucro-real, retenções, limite-simples), `cfop/*`, `ncm/*`, `das/*` — calculadoras/CRUDs fiscais; parte é gap real de tela, parte double-mount. Triar antes.

## Status
Mapa entregue (read-only). Wiring do DANFSE recomendado como próximo passo limpo, mas **aguarda coordenação** (território paralelo) ou direção do Jordan.
