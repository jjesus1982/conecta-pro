# PRÉ-MORTEM — Programa Multi-CNPJ Grupo Conecta Mais

**Exercício:** É outubro/2026. O programa fracassou. Reconstituímos por quê — ANTES de escrever uma linha.
**Data:** 2026-07-17 · **Autores:** Jordan + Claude (t1) · **Docs-irmãos:** `PRD_MULTI_CNPJ_2026-07-17.md`, `PLANO_EXECUCAO_MULTI_CNPJ_2026-07-17.md`, `PLANO_MULTI_CNPJ_GRUPO_CONECTA_2026-07-17.md` (diagnóstico técnico completo)

Cada modo de falha: **como aconteceu** (narrativa do fracasso), **prevenção** (regra incorporada ao plano) e **sinal precoce** (o que monitorar para pegar ANTES do estrago).

---

## CATEGORIA A — Falhas que geram passivo legal/trabalhista (as mais graves)

### F1. "Os holerites antigos foram reescritos" ⚠️ O RISCO Nº 1
**Como aconteceu:** trocamos o branding para resolver o CNPJ novo; como holerite/espelho de ponto são re-renderizados on-the-fly do dict atual, TODOS os contracheques de competências antigas passaram a exibir a Patrimonial. Num processo trabalhista, o reclamante apresentou dois holerites da mesma competência com CNPJs diferentes. Perícia, presunção contra a empresa.
**Prevenção:** identidade do emitente resolvida POR COMPETÊNCIA + empresa do vínculo, NUNCA por constante global. Fronteira (definida pela Portte) gravada em config versionada. Documentos de competências fechadas = fonte histórica imutável.
**Sinal precoce:** gate automatizado — holerite de 06/2026 re-renderizado byte-a-byte idêntico ao atual; roda em TODO deploy das WS2/WS3.

### F2. "O sistema divergiu da Portte na transição trabalhista"
**Como aconteceu:** a Portte transferiu os funcionários com datas/competência próprias; nós marcamos `empresa_id` com datas assumidas. Holerites, SST e certidões ficaram com empregador errado por semanas sem ninguém notar.
**Prevenção:** o sistema NÃO assume datas — ele espelha as datas OFICIAIS da Portte (dependência externa D2 do plano de execução). Nenhum funcionário muda de `empresa_id` sem a data oficial registrada.
**Sinal precoce:** relatório de conciliação sistema×Portte por funcionário (CPF, empregador, data), rodado na entrada de cada resposta da Portte e a cada fechamento.

### F3. "SST transmitido pelo empregador errado"
**Como aconteceu:** a folha migrou, mas nossos S-2210/2220/2240 (que continuam sendo transmitidos POR NÓS) seguiram saindo pelo CNPJ1 — eventos rejeitados ou, pior, aceitos contra empregador sem vínculo.
**Prevenção:** transmissão SST bloqueada por trava: evento só sai se o `empregador_cnpj` = empresa vigente do funcionário na data do evento; segundo certificado carregado e selecionado por empresa antes da primeira transmissão pós-virada.
**Sinal precoce:** fila SST com validação pré-transmissão (dry-run diário); qualquer evento com empregador≠vínculo → alerta no sino, transmissão retida.

### F4. "Certidão verde do CNPJ1 mascarou o CNPJ2 irregular"
**Como aconteceu:** `ged_certidoes` sem coluna de CNPJ; painel mostrava "FGTS regular" (CNPJ1) enquanto o CNPJ2 — o empregador real — acumulava pendência. Descoberto ao perder uma licitação/apontamento do condomínio.
**Prevenção:** coluna `cnpj` em certidões + sync CND/CRF/CNDT em loop pelas DUAS empresas + painel exibe as duas colunas lado a lado (WS-GED, prioridade P1 por causa do kit de 28/07).
**Sinal precoce:** o próprio painel: célula "Patrimonial: aguardando dado" enquanto não houver certidão real — visível, honesto, cobrável.

## CATEGORIA B — Falhas de dinheiro

### F5. "Dinheiro no Cora invisível ou misturado"
**Como aconteceu:** recebimentos reais na conta Cora (já acontecendo — Mirante das Flores!) ficaram fora do sistema por semanas; quando a integração entrou, a conciliação por `ILIKE '%inter%' LIMIT 1` + `condominio_id` hardcoded misturou os extratos numa conta arbitrária. Fluxo de caixa e DRE viraram ficção.
**Prevenção:** (1) até a WS5 entrar, painéis exibem "Cora: aguardando integração" — nunca número fabricado; (2) conciliação REESCRITA para resolver `bank_account_id` real antes de qualquer sync do Cora; (3) importação retroativa do extrato Cora desde a abertura da conta como primeira carga.
**Sinal precoce:** oráculo diário: saldo exibido por conta == saldo da API por conta; recebimento do Mirante visível no sistema até o fim da WS5.

### F6. "Pagamento saiu pela empresa errada / teto compartilhado"
**Como aconteceu:** diaristas de portaria (despesa da Patrimonial) continuaram saindo pelo Inter do CNPJ1; o teto diário de R$100k somou as duas empresas e bloqueou a folha num dia de pico; caches Redis (`inter:token`, `inter:saldo`) colidiram entre contas.
**Prevenção:** roteamento por empresa dona da despesa; teto, saldo-mínimo e namespaces Redis particionados POR CONTA; `executar_lote` deixa de instanciar `InterAdapter` fixo.
**Sinal precoce:** guard de teste: pagamento de teste da Patrimonial NUNCA aparece em `inter_payments`; teto consumido exibido por conta.

### F7. "A folha não conseguiu ser paga pelo Cora"
**Como aconteceu:** descobrimos tarde que a API do Cora NÃO envia PIX por chave (transferência exige banco/agência/conta) e que toda saída exige aprovação no app. A folha da Patrimonial travou no dia do pagamento.
**Prevenção:** JÁ DESCOBERTO NA ARQUITETURA (pesquisa 17/07). Desenho da WS5 assume isso: agenda de beneficiários ganha dados bancários completos OU o pagamento usa o padrão "pago pelo app + conciliação"; aprovação no app Cora = gate humano oficial; webhook fecha o loop. Ensaio de pagamento real de R$0,01 no stage e depois em produção ANTES do primeiro pagamento de verdade.
**Sinal precoce:** o ensaio de R$0,01 é o próprio sinal — sem ele verde, nenhum pagamento real é agendado pelo Cora.

### F8. "Cobrança chegou ao condomínio com PIX/CNPJ errado"
**Como aconteceu:** régua de cobrança IA (PIX do Inter chumbado no prompt), kit de fatura (dados bancários Inter no PDF) e tela de cobranças (chave hardcoded) continuaram apontando o CNPJ1 para condomínios migrados. Cliente pagou na conta errada → conciliação manual, nota × recebimento cruzados entre empresas.
**Prevenção:** varredura dos pontos mapeados (collection_negotiator:93, kit_real_controller:614-620, cobrancas/page.tsx, banking_controller:205) na WS5; dados de recebimento SEMPRE derivados da empresa dona do contrato.
**Sinal precoce:** teste E2E por condomínio: fatura gerada exibe o banco/CNPJ da empresa do contrato (9 casos, um por condomínio).

## CATEGORIA C — Falhas fiscais

### F9. "NFS-e emitida com regime/CNPJ errado"
**Como aconteceu:** `optante_simples=True` era default (errado para o CNPJ1) e ISS 5% fixo (errado para o CNPJ2); na pressa, uma leva de notas de agosto saiu trocada — cancelamento, reemissão, cliente confuso.
**Prevenção:** parâmetros fiscais SEMPRE derivados do `regime_tributario` da tabela `empresas`; proibido default de regime em assinatura de função (gate de lint); homologação das duas empresas antes de produção.
**Sinal precoce:** gate diff-zero — XML do CNPJ1 pós-mudança idêntico ao pré-mudança; primeira nota do CNPJ2 conferida campo a campo contra a nota já emitida manualmente (Mirante) antes de automatizar.

### F10. "SPED/DCTFWeb/EFD-Reinf continuaram saindo só pelo CNPJ1"
**Como aconteceu:** o `empresa_context` com `LIMIT 1`+`lru_cache` ficou para depois; obrigações do CNPJ2 não foram geradas; multa.
**Prevenção:** matriz de obrigações × regime explícita no código (CNPJ2/Simples: DAS-PGDAS, sem SPED-LR); `get_empresa_fiscal()` por `empresa_id`. Enquanto a Portte cuida das obrigações, o sistema exibe o que é de quem — sem fingir que cumpre o que não cumpre.
**Sinal precoce:** painel de obrigações por empresa com status "responsável: Portte/sistema" — ponta solta fica visível.

### F11. "O kit do dia 28/07 saiu errado"
**Como aconteceu:** o beat `montar_kits_mensais` rodou em 28/07 às 07:00 — antes do go-live — e montou kits da competência 07 com guias/certidões/NFS-e todos do CNPJ1, ignorando que julho já era da Patrimonial. Retrabalho em 9 kits, condomínios receberam documentação errada.
**Prevenção:** GED multi-CNPJ promovido a P1 (pronto até 27/07) + regra de kit híbrido: cada documento resolve sua empresa POR COMPETÊNCIA/NATUREZA (ago+set = kits mistos por definição do Jordan; ~out = 100% Patrimonial). Se 27/07 estourar: pausar o beat e montar os kits de julho manualmente com conferência — decisão explícita, não acidente.
**Sinal precoce:** checkpoint no calendário de execução D-4 (24/07): "GED pronto para kit híbrido? SIM/NÃO → decisão beat".

## CATEGORIA D — Falhas de engenharia/processo

### F12. "A migration derrubou produção"
**Como aconteceu:** migration de `empresa_id` aplicada sobre schema com drift (houve DDL ad-hoc no operacional); 500 em cadeia; rollback improvisado sem snapshot.
**Prevenção:** ritual fixo por migration: (1) drift-check ORM-load, (2) snapshot rotulado do banco, (3) staging primeiro, (4) migration aditiva com backfill CNPJ1 e NUNCA NOT NULL na primeira leva, (5) blue-green.
**Sinal precoce:** o próprio drift-check; qualquer divergência ORM×banco ABORTA a frente até reconciliar.

### F13. "Os três terminais colidiram"
**Como aconteceu:** t1 (multi-CNPJ), t2 (financeiro) e t3 editaram os mesmos módulos; um deploy blue-green levou junto código半-pronto de outro terminal; regressão em produção que nenhum terminal reconhecia como sua.
**Prevenção:** divisão de território POR MÓDULO declarada no plano de execução; deploy sempre com `git status` limpo e diff revisado do que VAI na imagem; lock de deploy já existente respeitado; commits frequentes e pequenos por frente.
**Sinal precoce:** `git status` sujo com arquivos fora do território da frente ativa = parar e sincronizar com o Jordan.

### F14. "Env aplicado que não valia"
**Como aconteceu:** criamos `CORA_*` no `.env` da raiz, mas o runtime lia `backend/.env` (divergentes); credencial "configurada" que o container nunca viu; horas de debug.
**Prevenção:** WS1 inclui reconciliação dos DOIS arquivos `.env` + regra: mudança de env só vale após `up -d --force-recreate` + verificação lendo a config DE DENTRO do container.
**Sinal precoce:** script de verificação de env (nomes esperados presentes no ambiente do container) no checklist de cada frente.

### F15. "Regressão silenciosa no CNPJ1"
**Como aconteceu:** focados no CNPJ2, quebramos fluxos do CNPJ1 que continuou operando (emissão, conciliação Inter, holerite de quem?— não, todos migram; mas notas e cobrança da Eletrônica seguem). Cliente do Parise recebeu fatura quebrada.
**Prevenção:** TODA frente tem gate de regressão do CNPJ1 (diff-zero de XML, suítes `*_release` existentes, E2E Playwright das telas afetadas); backfill=CNPJ1 garante comportamento idêntico até a virada explícita.
**Sinal precoce:** suítes de release (16 fin + 7 ged + 4 ponto) rodadas após cada deploy — qualquer vermelho = rollback imediato.

### F16. "22 fixtures quebradas mascararam erro real"
**Como aconteceu:** parametrizar a empresa quebrou 22 arquivos de teste que travavam o CNPJ1; no vermelho generalizado, um erro genuíno passou despercebido ("deve ser fixture").
**Prevenção:** parametrização das fixtures é TAREFA PRÓPRIA da WS-proteção (antes das mudanças de emissão), transformando-as em gate diff-zero; proibido conviver com suíte vermelha.
**Sinal precoce:** contagem de testes verdes nunca regride entre deploys.

### F17. "O prazo comeu a cirurgia"
**Como aconteceu:** tentamos entregar TUDO até 31/07; P2 contaminou P0; viramos a data com metade das frentes 80% prontas e nenhuma 100%; a virada aconteceu no caos.
**Prevenção:** prioridade é lei: P0 (identidade, contratos, espelhamento trabalhista, kit) fecha ANTES de P1 (fiscal+Cora) que fecha antes de P2 (frontend/consultores). Degradação PLANEJADA: o que pode escorregar sem quebrar a virada está listado no plano de execução com o "modo manual" de cada item. Checkpoints diários contra o calendário.
**Sinal precoce:** checkpoint diário 18h: frente atrasada 1 dia → replanejar na hora (cortar escopo P2, nunca comprimir gate).

### F18. "Consultores IA induziram decisão errada"
**Como aconteceu:** CFO/CEO/CHRO continuaram agregando as duas empresas como uma; Jordan tomou decisão de caixa baseada em número misturado.
**Prevenção:** correção mínima IMEDIATA na virada: rótulo honesto "Grupo (2 CNPJs — consolidado)" + bloco `estrutura_grupo()` nos 8 consultores; segmentação real vem depois (P2).
**Sinal precoce:** pergunta-teste semanal a cada consultor ("qual o saldo da Patrimonial?") — resposta correta é "aguardando integração Cora", nunca um número inventado.

### F19. "A folha orgânica atropelou a Portte" (WS9)
**Como aconteceu:** empolgados, ligamos cálculo próprio como oficial antes da convergência; Portte (que é permanente e inegociável) foi surpreendida; números divergentes chegaram ao funcionário.
**Prevenção:** WS9 é PÓS-virada, sempre em paralelo, conciliada 100% contra a Portte; nada vira oficial sem o Jordan declarar o ponto de confiança; o funcionário NUNCA vê número do motor paralelo.
**Sinal precoce:** relatório mensal de convergência motor×Portte (meta: 100% em 3 competências seguidas antes de qualquer conversa sobre oficializar).

### F20. "Dependência externa travou o caminho crítico"
**Como aconteceu:** credencial de API do Cora não gerada, procurações gov não feitas, Portte sem resposta — as frentes técnicas ficaram prontas e paradas.
**Prevenção:** lista de destravas externas com dono (Jordan) e data-limite no plano de execução; item sem data vira risco nomeado no checkpoint diário.
**Sinal precoce:** o checkpoint diário lista as externas pendentes — 2 dias sem movimento = escalar.

---

## Adendo (17/07, após leitura dos documentos oficiais da Patrimonial)

**F21. "A nota/contrato saiu com razão social errada ou o serviço foi roteado pelo CNAE"**
**Como aconteceu:** o seed do banco dizia "Conecta Mais Patrimonial Ltda", mas a Receita registra
**CONECTAMAIS PATRIMONIAL LTDA** — documentos saíram com grafia divergente do CNPJ, gerando
questionamento em condomínio/licitação. E como os CNAEs das duas empresas se SOBREPÕEM (ambas têm
monitoramento 8020-0/01, apoio a edifícios 8111-7/00 e limpeza 8121-4/00), alguém "automatizou" o
roteamento por CNAE e classificou contrato no CNPJ errado.
**Prevenção:** grafia de razão social/CNPJ/IM/endereço SEMPRE copiada dos documentos oficiais
(cartão CNPJ) — nunca digitada; roteador serviço→empresa é REGRA DE NEGÓCIO declarada pelo Jordan
(tabela do PRD §1), proibido inferir por CNAE.
**Sinal precoce:** gate E1 confere o registro em `empresas` campo a campo contra o cartão CNPJ;
gate E2 confere a classificação dos 10 condomínios contra a tabela canônica.

## Síntese: as 5 regras que o pré-mortem impõe ao PRD

1. **Imutabilidade histórica**: documento de competência fechada nunca muda de identidade (F1).
2. **Espelhar, não assumir**: datas trabalhistas vêm da Portte; dinheiro vem da API; nada é inventado (F2, F5, doutrina veracity).
3. **Diff-zero no CNPJ1**: toda mudança prova que o mundo atual continua idêntico até a virada explícita (F9, F15, F16).
4. **Ritual de migration**: drift-check → snapshot → staging → aditiva/backfill → blue-green, sem exceção (F12).
5. **Prioridade é lei, degradação é planejada**: P0>P1>P2 com modo-manual documentado para cada item que pode escorregar (F11, F17).
