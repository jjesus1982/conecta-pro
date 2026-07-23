# PRÉ-MORTEM — Botões de Documento no Redesign (3 terminais, loop, deploy único)

> **Método:** é 2026-08. Entregamos "abrir HTML + baixar PDF" para todos os documentos do redesign. **Deu errado.** Este documento é a autópsia *antecipada* — cada modo de falha ancorado no código/memória real, com sinal de alerta e mitigação. Rigor = 2ª passada. Depois: protocolo de execução que já incorpora as mitigações.

## Fatos técnicos que moldam todos os riscos (provados hoje)
- **F1 — Deploy bakeia do DISCO, não do commit.** `deploy_backend_bluegreen.sh` faz `docker build` do contexto atual → o que estiver salvo no disco (mesmo não-commitado, mesmo quebrado) entra na imagem. Working tree tinha **20 arquivos de código sujos** durante o planejamento.
- **F2 — Árvore git COMPARTILHADA por 3 sessões claude.** `git add -A`/`git add .` de um terminal captura arquivo meio-feito de outro. Memória [[project_fase5_deploy_pr]], [[project_paridade_t4_financeiro_comercial]].
- **F3 — Builders importados com `try/except` individual** (`redesign_data_controller.py:2918`). Um builder quebrado NÃO derruba o app → **some em silêncio** (log error + segue). Botão simplesmente não aparece.
- **F4 — ModuleView é aditivo-seguro** (`scr.panels || []`, sem `scr.docs` hoje). Backend pode emitir `scr.docs` que o front velho ignora → **deploy backend antes, frontend depois** é seguro.
- **F5 — Produção roda `main_production:app`** (não `main.py`); vários geradores estão em routers NÃO montados em produção (ai/report_generator, analytics_dashboard, 3 submódulos hr). Rota que só existe no dev = 404 em produção. Memória [[project_fiscal_lapidacao_r1]].
- **F6 — `except: pass` esconde `NameError`** de import faltando no builder (mordeu na Fase 2). Bloco falha 100% silencioso.

---

## MODOS DE FALHA (por que falhou)

### A. Fundação compartilhada mal-selada (impacto: CATASTRÓFICO · prob: ALTA se paralelizada)
**Cenário:** os 3 terminais começam a fiar botões antes do `<DocButtons>`/`<ExportMenu>`/contrato `scr.docs`+`row.docs` estar estável. No meio, descobre-se que falta um 4º modo de fonte, ou o `row.docs` por-linha não carrega o `id`. Todos os 3 retrabalham 40 telas.
**Por que é grave:** o ModuleView e o `redesign_data_controller` (registry) são **intocáveis pelos 3** (regra). Se a fundação não cobre um caso, vira gargalo — só quem detém a fundação edita, e os outros 2 param.
**Sinal de alerta:** um terminal pedindo "preciso de um novo tipo de botão no ModuleView".
**Mitigação:** **Etapa 0 SERIAL** — a fundação é feita, deployada (backend+frontend) e **provada com 3 telas-piloto** (uma por-tela PDF, uma por-linha, uma export-JSON) ANTES de qualquer terminal sair fiando. A fundação cobre os **3 modos** já conhecidos (L9): (a) blob via `abrirPdf`; (b) Content-Disposition via `baixarArquivoAutenticado`; (c) payload JSON `{content,filename}`→Blob. Congelar o contrato `scr.docs`/`row.docs` e documentá-lo. Só então libera T1/T2/T4.

### B. Deploy do disco bakeia trabalho quebrado de outro terminal (impacto: CATASTRÓFICO · prob: ALTA)
**Cenário:** T1 dispara o deploy "de tudo de uma vez". No mesmo instante T2 tem um builder salvo pela metade (SyntaxError) no disco. O build bakeia o quebrado → aquele módulo some (F3) ou, se o erro for no import compartilhado, o backend não sobe.
**Por que é grave:** F1+F2. "Deploy de tudo de uma vez" só é seguro se o disco inteiro estiver consistente.
**Sinal de alerta:** `git status` com arquivos sujos; `python -m py_compile` falhando em algum builder.
**Mitigação — protocolo de RELEASE ÚNICO (§ Execução):** um único **release manager** (T1) executa o deploy, e só após um **checklist de porta-travada**: (1) os 3 terminais anunciam "commitei tudo, working tree limpo"; (2) `git status --short` = 0 arquivos de código sujos; (3) `py_compile` de TODOS os builders + `tsc --noEmit` do frontend passa; (4) ninguém edita/salva durante o build. Deploy = **build → smoke test → só então vira tráfego** (blue-green já aborta se green não sobe saudável).

### C. Botão que não aparece — falha silenciosa (impacto: ALTO · prob: ALTA)
**Cenário:** builder adiciona `scr.docs` mas faltou importar um helper, ou o schema saiu com chave errada. `except: pass` (F6) engole. A tela renderiza **sem o botão**. QA in-process vê a tela "ok". Vira "verde" sem funcionalidade.
**Sinal de alerta:** botão ausente onde o clássico tem; log "redesign_builders/X falhou".
**Mitigação:** (1) **nenhum `except: pass` novo** — capturar e logar com o nome do doc; (2) QA obriga contagem: `nº de scr.docs emitidos == nº esperado da matriz` por tela (oráculo numérico, não "renderizou"); (3) importar TODOS os helpers no topo e `py_compile` local antes de commit.

### D. Botão que abre LIXO ou vaza documento inseguro (impacto: CATASTRÓFICO · prob: MÉDIA)
**Cenário:** ligam o botão em `/campo/visitas/{id}/pdf` (**sem auth**, provado), ou em DANFE/NFC-e **placeholder fake**, ou SPED stub, ou comodato URL-simulada. Usuário clica → PDF vazio/lixo, ou documento exposto sem token.
**Por que é grave:** viola a regra de ouro "**nunca fabricar dado**" [[feedback_dado_real_vs_simulado]] e expõe documento. Documento fiscal/gov jamais pode dizer "transmitido" sem transmissão real.
**Sinal de alerta:** botão apontando p/ rota da lista ⛔ da MATRIZ.
**Mitigação:** a MATRIZ já marca os **10 ⛔ a corrigir/não-ligar**. Regra: item ⛔ = **botão desabilitado + tooltip honesto** ("aguardando emissão real"), nunca 200 fake. Corrigir `/campo/visitas` (add `CurrentActiveUser`) ANTES de ligar. Documento gov placeholder = não expor.

### E. Vazamento de documento por gate ausente (impacto: CATASTRÓFICO/LGPD · prob: MÉDIA)
**Cenário:** botão de holerite/DRE/comprovante aparece (e o endpoint responde) para um perfil operacional sem permissão financeira. Financeiro = só Jordan+Pyetra [[project_financeiro_auditoria_organizacao]].
**Por que é grave:** vazamento LGPD; documento com dado pessoal/financeiro.
**Sinal de alerta:** endpoint de doc financeiro/fiscal sem `_FIN_GATE`/`_FISCAL_GATE`/`require_permission`.
**Mitigação:** o **gate é no BACKEND** (não só esconder o botão). Esconder o botão por perfil é UX; o endpoint DEVE gatear. QA: chamar o endpoint com token de perfil sem permissão → esperar 403, não 200. Dinheiro-que-sai (pagar) continua OTP — mas isto é leitura de comprovante (seguro).

### F. Rota errada → 404 em produção (impacto: MÉDIO · prob: ALTA)
**Cenário:** terminal adivinha a base da API (DP=`/people-management`, GED=`/ged`, portal=`/people-management/portal`, candidatos=`/human-resources` — bases DISTINTAS, provado). Ou liga rota que só existe em `main.py`, não em `main_production` (F5). Funciona no teste local, 404 no público.
**Sinal de alerta:** botão dá 404 no domínio público mas "funciona" no localhost dev.
**Mitigação:** **copiar a rota EXATA do backend** (a MATRIZ traz o path real por âncora arquivo:linha), nunca adivinhar. Verificação obrigatória: `grep` do path no router + confirmar que o router está incluído em `main_production.py`. Verificar pela rota da tela [[feedback_verificar_rota_da_tela]] no DOMÍNIO PÚBLICO com cache-bust [[feedback_verificacao_cache_bust]].

### G. Modo de fonte errado — JSON servido como PDF (impacto: MÉDIO · prob: MÉDIA)
**Cenário:** conciliação bancária (`/financial/bank-reconciliations/{id}/export`) devolve `{content,filename}` (JSON), não blob. Terminal liga com `abrirPdf` → abre JSON cru como se fosse PDF.
**Mitigação:** a fundação (A) já provê o modo (c). A MATRIZ marca L9 explicitamente. QA: checar content-type real da resposta antes de escolher o modo.

### H. Deploy frontend — chunk drift + OOM + ordem (impacto: ALTO · prob: MÉDIA)
**Cenário:** deploy do frontend sem purgar `.next/static` → ChunkLoadError "Algo deu errado" [[project_nginx_static_drift]]. Ou o build (8GB RAM) roda com 3 sessões + Chromium aberto → OOM mata processo. Ou frontend novo sobe antes do backend → espera `scr.docs` que não vem ainda.
**Mitigação:** **ordem: backend primeiro** (aditivo, F4), **frontend depois**, 1 vez no fim. Deploy frontend = rebuild container `conecta-pro-frontend` (:3001) + `rm -rf .next/static` antes [[project_frontend_deploy_target]]; pausar DET robot + fechar Chromium (anti-OOM); `NODE_OPTIONS=--max-old-space-size=8192`.

### I. Validação Playwright — profile lock / sweep concorrente (impacto: MÉDIO · prob: ALTA)
**Cenário:** os 3 terminais abrem o Chromium do MCP ao mesmo tempo → profile lock ("Browser profile locked by another terminal"). Ou 2 sweeps em paralelo se atrapalham [[project_ged_gedeon_aprovado_cic]].
**Mitigação:** validação browser **serializada** — um terminal por vez com o MCP. Antes de usar: se houver Chromium órfão, **matar** (`browser_close` + pkill chrome vivos + limpar SingletonLock). Ao concluir, matar a própria sessão do browser. Nunca 2 sweeps simultâneos.

### J. Loop autônomo diverge ou nunca termina (impacto: MÉDIO · prob: MÉDIA)
**Cenário:** loop "ultrathink" inventa trabalho fora do escopo, ou nunca atinge "done" por falta de critério.
**Mitigação:** **DoD fechado por terminal** (checklist de telas × docs da MATRIZ). Loop = commit por etapa, **nunca deploy** (deploy é do release manager, 1 vez). Loop encerra quando o checklist do território zera. Um terminal **nunca** toca arquivo de outro território (git add só do próprio módulo).

### K. QA/E2E afogado no volume (impacto: MÉDIO · prob: ALTA)
**Cenário:** ~137 afordâncias; testar todas E2E manualmente é inviável → amostram mal, bug escapa.
**Mitigação:** QA em 2 camadas: (1) **automática/oráculo** para 100% — por doc: endpoint responde 200 + content-type esperado + tamanho>0 + (p/ os ✅) bytes reais (não placeholder), via curl com token na rota da tela; (2) **browser E2E** por amostragem rigorosa dos críticos por-item (holerite, espelho 671, DANFSe, comprovante Inter, TRCT, kit ZIP) + 1 por módulo. Não-conformidade → corrige na hora, re-testa (loop-until-clean).

### L. Coordenação entre terminais (impacto: MÉDIO · prob: MÉDIA)
**Cenário:** dois terminais editam o mesmo builder-fronteira (ex.: gestao-de-pessoas vs departamento-pessoal se sobrepõem em GED/ponto). Colisão de git / retrabalho.
**Mitigação:** territórios **RÍGIDOS e exaustivos** (sem interseção — resolver as fronteiras GED/ponto/saúde no briefing). Arquivo de coordenação vivo (checklist compartilhado) onde cada um marca progresso. Jordan = árbitro de fronteira.

---

## PROTOCOLO DE EXECUÇÃO (incorpora as mitigações)

### Etapa 0 — FUNDAÇÃO (serial, só T1; T2/T4 aguardam)
1. `<DocButtons>` (3 modos: blob/CD/JSON) + `<ExportMenu>` (Excel/PDF/CSV client-side, portar `utils/export.ts`).
2. Contrato `scr.docs=[{label,url,formato,gate,disabled?,motivo?}]` (tela) + `row.docs`/`row.id` (linha) no ModuleView + convenção nos builders.
3. 3 telas-piloto (por-tela PDF · por-linha holerite · export-JSON conciliação) → deploy backend→frontend → **provar no browser**.
4. Congelar e documentar o contrato. **Só então liberar T1/T2/T4.**

### Etapa 1 — FIAÇÃO (3 terminais em loop paralelo, territórios rígidos)
- **T1:** operacional · campo · saúde-ocup · jurídico · relatorios · documentos/GED · bi.
- **T2:** departamento-pessoal · gestao-de-pessoas · portal-do-funcionário · rh · recrutamento · homologação. (Dono das fronteiras GED/ponto/saúde.)
- **T4:** financeiro · fiscal · empresas · crm · comercial · licitações · governo/integrações · area-do-cliente.
- Cada um: só seu builder; `git add` explícito do próprio arquivo; **commit por etapa** (2-3 telas/commit); `py_compile` antes de commitar; **sem deploy**; marca progresso no checklist; corrige os ⛔ do seu território (ou desabilita honesto).

### Etapa 2 — RELEASE ÚNICO (release manager = T1)
Porta-travada: (1) 3 terminais "commitei, tree limpo"; (2) `git status`=0 código sujo; (3) `py_compile` todos builders + `tsc --noEmit`; (4) freeze de edição. → **deploy backend** (blue-green, smoke test) → **push** → **deploy frontend** (purga static, anti-OOM) → **push**. Deploy = build+commit+push, tudo de uma vez, nada perdido.

### Etapa 3 — QA (oráculo, 100% dos docs)
Por afordância: curl com token na rota da tela → 200 + content-type certo + size>0 + (✅) bytes reais. ⛔ → 403/desabilitado honesto. Não-conformidade = corrige já, re-deploya no próximo release, re-testa.

### Etapa 4 — E2E rigoroso + validação Playwright MCP (serial)
Browser no domínio público (cache-bust): para os críticos por-item e 1 por módulo — botão existe, clica, abre HTML/baixa PDF real. Divergência → corrige e **tenta de novo** até passar. Chromium órfão → matar antes; matar a própria sessão ao concluir.

### Etapa 5 — Limpeza + Relatório
Matar sessões Chromium; cada terminal mata a sua ao terminar. **Relatório final:** o que foi feito, como, dificuldades, aprendizados, e como evitar os mesmos problemas nas próximas etapas do Conecta PRO.

## Definição de DONE (global)
Todo doc da MATRIZ: ✅ botão abrir-HTML + baixar-PDF funcionando no público, OU ⛔ desabilitado com motivo honesto. QA oráculo 100% verde. E2E dos críticos provado no browser. 0 arquivo sujo, tudo commitado+pushado. Relatório entregue.
