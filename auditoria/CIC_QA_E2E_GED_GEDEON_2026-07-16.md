# QA E2E — CIC — MÓDULO GED/GEDEON · Validação pós-lapidação

> Cole no CIC. O módulo passou por lapidação completa (commit `d5733894`): consultor com
> dados reais, 6 rotas destravadas, workspace do Drive limpo + guard anti-lixo, caches
> ajustados, RiskMonitor corrigido. Pré-validado pelo dev: 29/29 pytest + 19/19 browser.
> Sua função: o carimbo independente, click-level. PASS/FAIL por item + veredito.

## CONTEXTO
- URL: https://erp.conectamais.pro/modulos/gestao-pessoas/ged → perfil Jordan/Pyetra.
- **Hard refresh (Ctrl+Shift+R)** em cada tela — houve deploy novo.
- Escopo: GED/GEDEON completo (15 telas do hub).

## 🚨 SEGURANÇA (produção)
- NÃO dispare montagem de kit real, envio a cliente, upload de documento real nem
  exclusão de arquivo do Drive. Pode navegar, filtrar, abrir fichas e consultar tudo.
- NÃO use o robô de coleta (Sólides/Onvio) — só leitura de status.
- Se criar algo de teste (não recomendado neste módulo), sinalize para o dev remover.

## PARTE A — Itens corrigidos (validar um a um)

### A1. Consultor GEDEON (/ged/consultor) — ERA: tudo "≈0" e "kit NÃO montado"
- [ ] Selecione competência JUNHO/2026: **Kits montados 9/11** (GREEN HILLS e PARISE
      VILLAGE sem kit é esperado — sem operação alocada).
- [ ] Coluna Funcionários com números REAIS (Michelangelo ≈3 · Ideal Flores ≈11 ·
      Mirante ≈9 · Prime Arena ≈6 · V. Pássaros ≈6 · V. Dei Fiori ≈7 · Laranjeiras ≈10)
      — NUNCA "≈0" para todos.
- [ ] "Pronto p/ fechar" = SIM nos que têm kit e zero intercorrências.
- [ ] Folha da competência: líquido **R$ 73.075,36** (junho, 56 holerites).

### A2. Dashboard GED (/ged) — ERA: 24 "kits" (12 eram pastas-lixo) e trava de 30s
- [ ] O painel "Kits por Condomínio" resolve (spinner "Lendo os kits no Drive…" some;
      1ª carga fria pode levar ~30s — recargas seguintes são instantâneas por ~10 min).
- [ ] **11 kits**, todos com NOME DE CONDOMÍNIO — nenhum card com nome de arquivo
      (".pdf", "Comprovante de…", "Recibo…").
- [ ] Média de conclusão plausível (~40%+), não distorcida.

### A3. Rotas destravadas (validar pela UI que as usa)
- [ ] /ged/upload: árvore de pastas carrega (usa /folders — a rota /root era 422).
- [ ] /ged/assinaturas: pendências/stats carregam sem erro no console.
- [ ] /ged/documentos: filtros + busca funcionam (tags most-used era 500).
- [ ] Console em TODAS as telas: **zero** erro 500/422 (referência dev: 0 em 15 telas).

### A4. Telas restantes do hub (sweep)
- [ ] /kits · /kit (ficha por condomínio: abra IDEAL FLORES — checklist + anexos reais)
      · /montar-kit (painel por competência com docs por subpasta + link do Drive)
      · /certidoes (cards com validade real e fonte marcada — inclusive "portal
      indisponível" é status honesto, não bug) · /clientes (CNPJs reais) · /relatorios
      · /whatsapp · /configuracoes · /onvio-sync · /consultor · /envios.
- [ ] /envios zerado é **vazio-real** (feature de templates/atribuições sem dados) —
      não conta como falha.
- [ ] Nenhuma tela com "Algo deu errado"/tela branca/chunk error.

## PARTE B — Interações (sem efeito externo)
- [ ] /kit?cond=IDEAL FLORES: ficha abre com blocos do checklist, arquivos por subpasta
      e score; botão "Atualizar" recarrega sem erro.
- [ ] /consultor: troque a competência (junho ↔ julho) — números mudam coerentemente
      (julho tem 7 kits no espelho).
- [ ] /ged: clique num condomínio do painel → navega pra ficha correspondente.
- [ ] Busca Sophia (/consultor ou onde exposta): buscar "ferias" retorna resultados.

## RELATÓRIO FINAL
1. PARTE A (A1–A4): PASS/FAIL por item, com print nos FAIL.
2. PARTE B: OK/observação por interação.
3. Console errors se houver (referência: dev fechou com zero).
4. **VEREDITO: APROVADO / APROVADO COM RESSALVA / REPROVADO** para o módulo GED/GEDEON
   em produção. Itens conhecidos que NÃO contam como falha nova: /envios vazio-real;
   1ª carga fria ~30s do painel (Drive); GREEN HILLS/PARISE sem kit (a confirmar com
   o Jordan se é esperado).
