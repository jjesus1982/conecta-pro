# PRÉ-MORTEM — Fase 2 (paridade fiel Clássico → Redesign)

> Exercício: é daqui a X semanas e a Fase 2 FRACASSOU. Por quê? Abaixo, a autópsia —
> pior primeiro. Objetivo da Fase 2: trazer com FIDELIDADE o que o clássico MOSTRA **e**
> FAZ (botões/ações/informação) pro redesign, em 3 terminais (T1, T2, T4; T3 fora).
> Regra-mãe: **fidelidade = realidade do clássico ancorada no banco. NUNCA fabricar.**

## 🔴 CATASTRÓFICOS (existenciais — matam a empresa, não só o projeto)

### C1. Quebrar o CLÁSSICO que está no ar
Redesign e clássico **compartilham o mesmo backend, serviços e banco**. Mexer num serviço/
tabela compartilhada pra fazer um botão do redesign funcionar pode **derrubar o clássico que
opera a empresa AGORA** (folha, fiscal, ponto, PIX). Blast radius = ERP real fora do ar.
→ **Guarda:** toda mudança em serviço compartilhado exige regressão no clássico antes do merge.
Preferir ADITIVO (novo endpoint/coluna) a alterar o existente.

### C2. Dinheiro sai / transmissão gov dispara por acidente
Construir botões "Pagar"/"Transmitir" faz o CAMINHO até dinheiro/gov EXISTIR no código. Um bug,
um clique de teste, um double-fire → R$ real sai (Inter/Cora) ou um evento eSocial/DCTFWeb
transmite (ou duplica). **Irreversível.**
→ **Guarda:** gate humano OTP inviolável, um único choke-point. Nada paga/transmite sem OTP.
NUNCA testar botão de escrita com valor/CPF real. Teste só em base de homologação.

### C3. Sucesso FABRICADO em registro legal/financeiro
Tela diz "pago/transmitido/assinado" sem o backend real confirmar → **registro falso de
compliance/financeiro**. Fraude-adjacente, risco legal.
→ **Guarda:** documento fiscal/pagamento JAMAIS diz "autorizado/enviado" sem retorno real do
PSP/gov. Sem confirmação = 501/"pendente" honesto, nunca verde falso.

### C4. Corromper dado operacional real
Testar "criar rescisão / lançar diária / aprovar férias / alocar" num funcionário REAL cria
registro real nas tabelas compartilhadas → polui folha/operacional (curados à mão pelo Jordan).
→ **Guarda:** escrita só contra base de homologação (is_homologacao / cliente HOMOLOG). Operacional
segue READ-ONLY p/ agente.

## 🟠 ALTOS (afundam o esforço, não a empresa)

### A1. O FRONTEND não é fatiado por módulo → motor de conflito
Fase 1 foi backend (builders bem isolados em `redesign_builders/`). Fase 2 precisa de FORMS,
BOTÕES, WIZARDS = trabalho de FRONTEND em componentes COMPARTILHADOS (ModuleView, componentes
redesign). 3 terminais editando os mesmos arquivos React = merge-hell + **drift de chunk
estático** (ChunkLoadError / "Algo deu errado") no deploy de frontend (:3001). **A fundação da
Fase 1 NÃO resolve o frontend.** ← provavelmente o maior risco técnico novo.
→ **Guarda:** decidir ANTES — ou o ModuleView vira genérico o bastante p/ ninguém tocar (só data-
driven pelo backend), ou 1 terminal dono do frontend, ou fatiar componentes por módulo.

### A2. "Fiel" é indefinido → retrabalho e discussão infinita
Fonte da verdade ambígua: **display do clássico** vs **banco** vs **pacote de design (*.dc.html)**.
O redesign foi feito do pacote, que PODE divergir do clássico. Perseguir o pacote = divergir do
clássico (a dor do Jordan). Perseguir o clássico = contradizer o design.
→ **Guarda:** RULING do Jordan por escrito → **realidade do clássico vence** (ancorada no banco);
o pacote de design é cosmético onde conflita. Botão do design sem equivalente no clássico = remove.

### A3. Sem ORÁCULO de fidelidade lado-a-lado
Sem um jeito de comparar clássico × redesign por tela (screenshot + diff de campos-chave),
"fiel" é opinião. Vamos declarar pronto e o Jordan de novo "acesso e vejo coisa diferente".
→ **Guarda:** método de comparação real por tela (Playwright screenshot clássico vs redesign +
diff dos campos que importam) ANTES de declarar uma tela fiel.

### A4. Verificador = construtor (falso PASS)
In-process/curl passa enquanto a tela real (pela rota+formato dela) está quebrada — a lição que
já nos mordeu (rota dict-cru, CPF mascarado, `||` falsy, Suspense). 3 papéis (finder/fixer/
verificador) NUNCA no mesmo ator.
→ **Guarda:** verificar pela MESMA rota da tela, no browser, por um ator diferente do que construiu.

### A5. Padrão "fetch ao vivo na request" → 502 sob carga
Já mordeu o T4 (financeiro 502: fetch de banco ao vivo dentro do endpoint, ~4s, timeout nginx).
Repetir isso em wizards/telas pesadas = outages intermitentes.
→ **Guarda:** nada de I/O externo lento na request; materializar/cachear + job assíncrono.

### A6. Migrations concorrentes de 2 terminais → corrupção de schema
Features de escrita podem precisar de coluna/tabela nova. 2 migrations ao mesmo tempo no banco
compartilhado = conflito/corrupção.
→ **Guarda:** protocolo de migration — 1 dono de schema, ou lock, ou migrations aditivas revisadas.

### A7. Explosão de escopo → estados meio-feitos quebrados
621 P0 é enorme. Correr = muitos botões meio-ligados que ficam PIORES que antes (exatamente a
dor do Jordan amplificada).
→ **Guarda:** fatias verticais pequenas, cada uma provada ponta-a-ponta; **nunca** commitar botão
meio-ligado. Priorizar legal/dinheiro → uso diário → resto.

## 🟡 COORDENAÇÃO / PROCESSO

- **P1. Identidades:** Fase 2 = T1 (eu) + T2 + T4; T3 fora (missão grande). T2 estava realocado
  na Fase 1 (T4 pegou os módulos dele) — **re-travar quem é dono do quê**, senão 2 pegam o mesmo.
- **P2. Alvo móvel:** o clássico muda embaixo de nós (outras sessões, missão do T3 tocando código
  compartilhado). Espelhar um alvo que se move = perseguição sem fim. → congelar o escopo por onda.
- **P3. Árvore git multi-sessão:** stash/reset trocado (já mordeu), lock vazando (corrigido rm -rf,
  mas ferramenta nova pode reintroduzir), commits acumulando sem push (aconteceu, ahead:9).
  → push por iteração; referenciar stash por SHA; nunca `--continue`.
- **P4. Deploy contention:** Fase 2 = mais deploys, incl. FRONTEND (pipeline diferente, :3001,
  drift de chunk). 2 deploys de frontend simultâneos = ChunkLoadError em produção.
  → serializar deploy de frontend; purgar `.next/static` antigo; sync + try_files.
- **P5. Compactação de contexto** no meio de um wizard longo → perda de estado. → fatias curtas.
- **P6. Consolidações (40 no audit):** telas do clássico fundidas em menos telas no redesign.
  "Fiel" pode exigir des-fundir — decisão humana caso a caso, não automática.

## 🎯 OS 5 QUE REALMENTE NOS AFUNDAM (se eu tivesse que apostar)
1. **C1** quebrar o clássico vivo mexendo em serviço compartilhado.
2. **C2/C3** dinheiro/gov disparar ou verde fabricado num registro legal.
3. **A1** o frontend compartilhado virar merge-hell + ChunkLoadError com 3 terminais.
4. **A2/A3** "fiel" sem definição nem oráculo → entregar e o Jordan ver "coisa diferente" de novo.
5. **A7** correr e deixar dezenas de botões meio-ligados (pior que Fase 1).

## ✅ PRÉ-CONDIÇÕES (o que TEM que existir ANTES de escrever código da Fase 2)
1. **Gate money/gov/escrita inviolável** — um único choke-point, OTP humano, sem auto-fire; base
   de homologação p/ testar escrita.
2. **Ruling de fidelidade:** realidade do clássico (ancorada no banco) vence o pacote de design.
3. **Oráculo de fidelidade** por tela (clássico × redesign, screenshot + diff de campos).
4. **Decisão do frontend compartilhado** (dono único / data-driven / fatiar) — sem isso, não
   paralelizar frontend.
5. **Papéis separados** finder/fixer/verificador; verificação pela rota real da tela.
6. **Protocolo de migration** (sem concorrência de schema).
7. **Regressão do clássico** obrigatória ao tocar serviço compartilhado.
8. **Disciplina de escopo:** ondas priorizadas (legal/dinheiro → diário → resto); fatias pequenas
   provadas; zero botão meio-ligado commitado.
