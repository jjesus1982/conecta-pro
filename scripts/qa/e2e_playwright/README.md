# Roteiros da varredura E2E pelo navegador (07/09/2026)

Funções `async (page) => {...}` para o Playwright MCP (`browser_run_code_unsafe`, com `filename`),
com a sessão já logada em https://erp.conectamais.pro. Um arquivo por módulo do redesign
(`operacional.js`, `financeiro.js`…), `resto1/resto2.js` agrupam os menores, `classico1/2.js`
varrem as 317 páginas de /modulos, `interativo.js` preenche e submete 10 calculadoras/simulações.

Saída: uma linha por tela `tela|nav|ms|caracteres|botões|ERRO|console|API 4xx/5xx|início do texto`.
Regenerar as listas de abas: `python3` sobre `/api/v1/redesign/data/<slug>` (ver auditoria/qa/QA_E2E_20260907.md).
Aviso: 30 páginas/min do mesmo IP estoura o `frontend_limit` do nginx (503 nos prefetches do Next).
