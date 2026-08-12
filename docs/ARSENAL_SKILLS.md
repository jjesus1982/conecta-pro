# Arsenal de skills — Conecta PRO

Inventário real em 12/08/2026: **31 skills ativas** (+1 fantasma).
Atualizado no mesmo dia: três genéricas foram ADAPTADAS ao Conecta PRO e viraram nossas. O que cada uma faz, onde
uma encosta na outra, e em que ordem usar até um módulo estar **entregue**.

Fase atual do projeto: **revisão e fechamento**. Nada de feature nova — o código existe; o
que falta é provar que funciona e ligar o que ficou solto.

---

## 1. Inventário

### Nossas (`conecta-pro-skills`) — 15

| Skill | Responde | Escreve? |
|---|---|---|
| **raio-x-modulo** | O que existe neste módulo? O que o backend faz que ninguém alcança? | não (só relatório) |
| **conecta-backend-recon** | Quais rotas estão montadas e sem superfície no front? | não |
| **veracity-sweep** | O número exibido é verdade ou mock/hardcoded? | sim (corrige) |
| **fecha-modulo** | O que está no ar está certo? (dado / tela / código) | não (QA não conserta) |
| **finding-schema-drift** | O model pede coluna que o banco não tem? | sim (migration) |
| **deploy-bake** | Como tornar a mudança durável sem quebrar? | sim (deploy) |
| **folha-cct** | Cálculo de folha pela CCT SINDECOMPRESTS | sim |
| **gold-standard-pdf** | Qualquer PDF da marca | sim |
| **gold-standard-slides** | Qualquer apresentação | sim |
| **juridico** | Módulo jurídico: contratos, alertas, LGPD | sim |
| **plano-conecta** | Plano que DECLARA TERRITÓRIO (5 sessões no mesmo repo) | não |
| **oraculo-conecta** | Como escrever oráculo que afirma a REGRA, não a fotografia | não |
| **entregue-de-verdade** | Os 3 portões entre "feito" e "entregue" | não |
| **raio-de-impacto** | Quem mais depende disto? Esse defeito tem irmãos? | não |
| **ponytail-conecta** | As 3 colisões entre ponytail e esta realidade | não |

### Genéricas — 16

| Família | Skills | Uso aqui |
|---|---|---|
| **superpowers** (14) | **3 substituídas:** ~~writing-plans~~ → `plano-conecta` · ~~test-driven-development~~ → `oraculo-conecta` · ~~verification-before-completion~~ → `entregue-de-verdade`. **11 seguem genéricas:** executing-plans, subagent-driven-development, systematic-debugging, brainstorming, requesting-code-review, receiving-code-review, dispatching-parallel-agents, using-git-worktrees, finishing-a-development-branch, using-superpowers, writing-skills | processo |
| **graphify** | grafo de conhecimento | **só via `raio-de-impacto`** — e só para forma de subsistema desconhecido |
| **notebooklm** | API do NotebookLM | fora do pipeline |
| ~~read-only-postgres~~ | **PASTA VAZIA — skill fantasma, remover** | — |

### Fora do arsenal, mas parte do ciclo
`ponytail` (reflexo permanente, não se invoca por tarefa) · varredura diária dos 65 oráculos
(cron 05:00, não é skill) · `/code-review` (comando do CLI).

---

## 2. Onde uma encosta na outra (checagem de retrabalho)

**Não há duplicação real. Há quatro fronteiras que precisam ficar ditas:**

| Par | Parece igual porque | A diferença |
|---|---|---|
| `raio-x-modulo` × `conecta-backend-recon` | os dois mapeiam órfão | recon é **ferramenta** (rota × front). raio-x é o **protocolo** que combina recon + graphify + leitura do controller. Nunca chame recon sozinho para decidir — ela não sabe o que a rota faz |
| `veracity-sweep` × `fecha-modulo` (lente DADO) | os dois perguntam "o exibido == banco?" | fecha-modulo usa **oráculo** onde existe. veracity-sweep é o que se faz **quando não há oráculo** — e ela CORRIGE; fecha-modulo só julga |
| `fecha-modulo` × `entregue-de-verdade` | os dois são "antes de dizer pronto" | fecha-modulo é escala de **módulo** (3 lentes, relatório). entregue-de-verdade é escala de **frase**, e traz os 3 portões que separam "feito" de "entregue" |
| `oraculo-conecta` × ponytail | os dois exigem teste | TDD é ciclo completo (falha→passa→refatora). Ponytail exige **uma** checagem executável por lógica não-trivial. Em fase de revisão, ponytail basta; TDD só para lógica nova |

**Sobreposição que existe de verdade:** `writing-plans` → `executing-plans` →
`subagent-driven-development` são três da mesma família e sequenciais. Numa sessão só, use
writing-plans e execute você mesmo; as outras duas são para fan-out.

---

## 3. Ordem lógica até "entregue"

```
┌─ DESCOBRIR ────────────────────────────────────────────────┐
│ 1. raio-x-modulo        o que existe, o que é órfão/casca  │
│ 2. finding-schema-drift SÓ SE houver 500/UndefinedColumn   │
│ 3. veracity-sweep       o exibido é verdade? (sem oráculo) │
└────────────────────────────────────────────────────────────┘
┌─ DECIDIR ──────────────────────────────────────────────────┐
│ 4. plano-conecta        DECLARA TERRITÓRIO (5 sessões no repo)│
└────────────────────────────────────────────────────────────┘
┌─ CONSTRUIR ────────────────────────────────────────────────┐
│ 5. ponytail (sempre) + oraculo-conecta por lógica não-trivial│
│    → oráculo em backend/scripts/orq/, provado que PEGA      │
│ 6. raio-de-impacto — o defeito tem irmãos? + /code-review   │
└────────────────────────────────────────────────────────────┘
┌─ PROVAR ───────────────────────────────────────────────────┐
│ 7. fecha-modulo         3 lentes: dado · tela · código     │
│ 8. entregue-de-verdade   os 3 portões, antes de dizer pronto│
└────────────────────────────────────────────────────────────┘
┌─ ENTREGAR ─────────────────────────────────────────────────┐
│ 9. deploy-bake          docker cp é volátil; bake é durável│
│10. conferir na ROTA REAL após o bake                       │
└────────────────────────────────────────────────────────────┘
┌─ VIGIAR (automático) ──────────────────────────────────────┐
│ varredura diária 05:00 · vermelho vira alerta no sino      │
└────────────────────────────────────────────────────────────┘
```

**Definição de ENTREGUE** — os três, sem exceção:
1. servido pela **rota real** depois do bake (oráculo verde não é entrega);
2. oráculo verde na varredura;
3. **nenhuma superfície nova sem vigia**.

Faltando um, é "feito", não "entregue".

### Regras que atravessam tudo
- **Território primeiro:** `git log` e `git status` nos arquivos antes de editar. Cinco
  sessões no mesmo índice. Commit por pathspec, nunca `git add -A`.
- **Não fabricar:** sem fonte, "aguardando dado". Vale para código e para relatório.
- **Dinheiro/gov:** money-out nunca em happy-path; transmitir ao governo é ato real.
- **Operacional é read-only** para agentes: divergência vira relatório.

---

## 4. Roteiro copiar-colar

> Troque **`<MÓDULO>`** e cole. O resto é a sequência inteira.

```
Vamos fechar o módulo <MÓDULO> do Conecta PRO. Estamos em fase de REVISÃO: não é para criar
feature nova — é para provar o que existe e ligar o que ficou solto.

Siga esta ordem, e me diga o resultado de cada etapa antes de passar para a próxima:

1. /conecta-pro-skills:raio-x-modulo <MÓDULO>
   Quero saber: o que o backend codou, o que o front alcança, o que é órfão, o que é casca.

2. Se aparecer erro 500 por coluna/tabela: /conecta-pro-skills:finding-schema-drift

3. /conecta-pro-skills:veracity-sweep <MÓDULO>
   Só para o que NÃO tem oráculo. O exibido tem que bater com o banco.

4. /conecta-pro-skills:plano-conecta
   O passo 0 dela é território: `git log` e `git status` nos arquivos que vou tocar. Se
   houver WIP de outra sessão no MESMO arquivo, espere — índice temporário isola arquivo,
   não trecho.

5. Execute em loop, com /ponytail:ponytail ativo e /conecta-pro-skills:oraculo-conecta
   para cada lógica não-trivial. O oráculo afirma a REGRA, não a fotografia, e você prova
   que ele PEGA rodando contra o código anterior.

6. /conecta-pro-skills:raio-de-impacto
   Todo defeito corrigido: procure a família no repositório inteiro. Depois /code-review.

7. /conecta-pro-skills:fecha-modulo <MÓDULO>
   Três lentes. "NÃO VERIFICADO" é resultado válido; "passou" sem evidência não é.

8. /conecta-pro-skills:deploy-bake
   docker cp não recarrega módulo já importado — só o bake entrega.

9. /conecta-pro-skills:entregue-de-verdade
   Os 3 portões: rota real depois do bake · oráculo que pega · nenhuma superfície sem vigia.

Regras que não se negociam:
- Não fabricar dado. Sem fonte → "aguardando dado".
- Dinheiro que sai: nunca happy-path. Governo: só leitura.
- Operacional é curado à mão: divergência vira relatório, não correção.
- Commit por pathspec, com o achado no commit e a história longa no relatório.

Ao final, relatório em auditoria/qa/<MÓDULO>_AAAAMMDD.md com veredito por lente e o que
NÃO foi coberto.
```

---

## 4b. Genéricas adaptadas — e as que NÃO merecem adaptação

Três foram adaptadas porque falharam **aqui**, com caso medido em 11-12/08:

| Genérica | Nossa | O que a genérica não previa |
|---|---|---|
| graphify | **raio-de-impacto** | o grafo não acha os defeitos daqui (são semânticos). Acha "quem mais" — e eu declarei 3 defeitos corrigidos com a família viva: 5 janelas ancoradas, 5 vocabulários, 3 validades inventadas |
| ponytail | **ponytail-conecta** | 3 colisões: menor diff não vale em dinheiro/fisco/gov; superfície nova nasce vigiada; e a mensagem de commit é longa DE PROPÓSITO — é o único canal entre 5 sessões |
| writing-plans | **plano-conecta** | cinco sessões no mesmo índice git. O plano precisa declarar TERRITÓRIO — colidi com o T1 duas vezes no mesmo dia |
| test-driven-development | **oraculo-conecta** | não é ciclo vermelho-verde. É checagem que compara tela × banco em produção, e que apodrece se afirmar fotografia: 15 das 16 falhas de oráculo não eram defeito de produto |
| verification-before-completion | **entregue-de-verdade** | aqui "feito" e "entregue" são estados distintos: `docker cp` não recarrega módulo importado, e eu disse "pronto" 3 vezes estando só em FEITO |

**As que NÃO ganham adaptação, e o motivo:**
- `brainstorming`, `subagent-driven-development`, `dispatching-parallel-agents`,
  `using-git-worktrees`, `finishing-a-development-branch` — não usamos na fase de revisão.
- `systematic-debugging` — a lição daqui ("meça, não diagnostique de memória") já vive nas
  regras da casa; skill nova seria repetição.
- `notebooklm`, `gold-standard-*`, `folha-cct`, `juridico` — situacionais, já são nossas ou
  fora do pipeline.

### Onde as skills VIVEM (achado de 12/08)

O plugin `conecta-pro-skills` existia **só em `~/.claude/`, fora do git**. Treze skills, a
metodologia inteira, sem backup. Espelhado em `skills/_plugin/conecta-pro-skills/`.

⚠️ **A cópia viva continua sendo `~/.claude/`** — o espelho é backup, e vai divergir se
alguém editar num lado só. Ao mexer numa skill, copie para o espelho e commite.

---

## 5. O que o arsenal ainda não faz

Nenhuma das 26 responde **"onde estamos cegos?"**. Três lacunas medidas em 12/08:

1. **Vocabulário de domínio** — lista literal no código × `DISTINCT` real da coluna.
   Pegaria `NOT IN ('pago','paga',…)` numa tabela que usa `'cumprida'` (31 obrigações
   anunciadas onde havia 5) e `3=Receita` num plano que usa `4=Receita` (PL de +R$ 2,02 mi
   onde havia prejuízo de R$ 97 mil).
2. **Caça-fabricação** — código que inventa valor quando a fonte falha:
   `utcnow()+timedelta` virando validade · `except: pass` devolvendo veredito ·
   `max(coluna)` como âncora de janela · `[:N]` sem dizer que cortou.
3. **Mapa do não-vigiado** — superfície × 65 oráculos, ordenado por raio de dano.
   Teria gritado "o Balanço Patrimonial não tem oráculo" antes de o PL mentir por meses.

### As quatro travas mecânicas (12/08) — cada uma nasceu de um erro medido

| Trava | Erro que ela impede | Onde |
|---|---|---|
| `checar_vocabulario.py` | lista literal que a coluna não tem — 31 obrigações onde havia 5 | `scripts/qa/` |
| `cacar_fabricacao.py` | valor inventado quando a fonte falha — certidão de 180 dias sem consulta | `scripts/qa/` |
| `checar_arsenal.py` | o próprio arsenal mentindo — instrução velha faz o próximo errar com confiança | `scripts/qa/` |
| `test_oraculo_periodo_fechado.py` | reescrever período que o Jordan fechou — 184 lançamentos | `scripts/orq/` |
| `_mutacao.py` | DELETE/UPDATE largo demais em produção — apagou certidão legítima | `scripts/qa/` |

**`_mutacao.Mutacao` é obrigatório em todo script que altera dado de produção.** Ensaio é o
padrão; `--aplicar` é explícito; acima do teto exige `--forcar`; lista vazia nunca aplica.
A diferença entre acertar e apagar dado alheio, em 12/08, foi ter olhado a lista antes.

**Os dois primeiros JÁ EXISTEM como código** (12/08), não como skill —
`backend/scripts/qa/checar_vocabulario.py` e `backend/scripts/qa/cacar_fabricacao.py`.
Acharam, na primeira execução: 23 filtros que nunca casam nada, 4 janelas ancoradas (eu
tinha consertado 1 achando que era única) e a validade inventada do `crf_client`. Falta o
**mapa do não-vigiado**.

**Por que código e não skill:** Skill só age
quando alguém a invoca; check age sempre. Foi um check que achou o corte silencioso do
digest às 05:00 de hoje, sem ninguém pedir.
