# REGRAS DA SESSÃO (Jordan) — Botões de Documento no Redesign

Sessão longa e extenuante. 3 terminais (T1/T2/T4) fiam em LOOP; o orquestrador faz release, QA, E2E e relatório.

## Para os 3 terminais (fiação)
1. **LOOP ultrathink** até fechar o checklist do seu território. Respeite boas práticas.
2. **NÃO toque no escopo do outro.** Edite SÓ os builders do seu território. NUNCA a fundação (`ModuleView.tsx`, `docsource.ts`, `DocButtons.tsx`, `doc()`/`tbl` no `redesign_data_controller.py`) nem builder alheio.
3. **Commit por etapa realizada** (2-3 telas/commit). **USE PATHSPEC**: `git commit --no-verify -- <seu_builder.py>` (commita SÓ o seu arquivo, mesmo com a árvore compartilhada). Se der `index.lock`, espere 2s e repita. `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
4. **NÃO faça deploy. NÃO use o browser.** O release é ÚNICO (orquestrador). Você: fiação + commit + curl-verifica cada rota.
5. **Curl-verifique CADA rota** antes de ligar: 200 + content-type esperado + bytes>0 (a rota já existe no backend). Rota que falha (404/500/placeholder) → `disabled=True` honesto, NUNCA botão que abre lixo.
6. **Nunca fabricar.** ⛔ da MATRIZ (placeholder/stub/sem-transmissão/sem-auth) = `disabled` + motivo honesto.
7. `py_compile` do seu builder antes de cada commit. Importe TODOS os helpers no topo (`doc` incluso) — `except: pass` engole `NameError`.

## Para o orquestrador (release + validação — NÃO é dos terminais)
8. **Deploy ÚNICO de todo o trabalho de uma só vez** (porta-travada: todos os builders `py_compile` + tree limpo). Ordem: backend blue-green → frontend (rebuild imagem, DET pausado anti-OOM). **Deploy = deploy + commit + push.**
9. **Auditoria QA** (oráculo): curl 100% dos docs (200 + type + bytes; 403 p/ perfil sem permissão nos gated).
10. **E2E com extremo rigor** via **Playwright MCP** no domínio público: abrir/baixar cada crítico, ver no frontend que o trabalho foi feito. Não conformidade/bug/erro → **corrige IMEDIATAMENTE e tenta de novo** até passar.
11. **Chromium órfão → matar** antes de testar; **matar a própria sessão do browser ao concluir**.
12. **Relatório final:** o que foi feito, como, dificuldades, aprendizados, e como evitar os mesmos problemas em etapas futuras do Conecta PRO.

## Referências
`CONTRATO-FUNDACAO.md` (como ligar) · `MATRIZ-MESTRE-REDESIGN.md` (documento→rota→gate→status) · `PRE-MORTEM.md` (modos de falha) · `BRIEFING-T1/T2/T4.md` (território de cada um).
