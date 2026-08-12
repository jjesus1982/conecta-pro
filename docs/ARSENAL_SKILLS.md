# Arsenal de skills — Conecta PRO

Inventário real em 12/08/2026: **26 skills ativas** (+1 fantasma). O que cada uma faz, onde
uma encosta na outra, e em que ordem usar até um módulo estar **entregue**.

Fase atual do projeto: **revisão e fechamento**. Nada de feature nova — o código existe; o
que falta é provar que funciona e ligar o que ficou solto.

---

## 1. Inventário

### Nossas (`conecta-pro-skills`) — 10

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

### Genéricas — 16

| Família | Skills | Uso aqui |
|---|---|---|
| **superpowers** (14) | writing-plans, executing-plans, subagent-driven-development, test-driven-development, systematic-debugging, brainstorming, verification-before-completion, requesting-code-review, receiving-code-review, dispatching-parallel-agents, using-git-worktrees, finishing-a-development-branch, using-superpowers, writing-skills | processo |
| **graphify** | grafo de conhecimento do código | estrutura |
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
| `fecha-modulo` × `verification-before-completion` | os dois são "antes de dizer pronto" | fecha-modulo é escala de **módulo** (3 lentes, relatório). verification-before-completion é escala de **frase**: não afirme o que não verificou |
| `test-driven-development` × ponytail | os dois exigem teste | TDD é ciclo completo (falha→passa→refatora). Ponytail exige **uma** checagem executável por lógica não-trivial. Em fase de revisão, ponytail basta; TDD só para lógica nova |

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
│ 4. writing-plans        plano DECLARA TERRITÓRIO (5 sessões)│
└────────────────────────────────────────────────────────────┘
┌─ CONSTRUIR ────────────────────────────────────────────────┐
│ 5. ponytail (sempre) + 1 checagem executável por lógica    │
│    → oráculo em backend/scripts/orq/                       │
│ 6. /code-review no diff                                    │
└────────────────────────────────────────────────────────────┘
┌─ PROVAR ───────────────────────────────────────────────────┐
│ 7. fecha-modulo         3 lentes: dado · tela · código     │
│ 8. verification-before-completion  antes da frase "pronto" │
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

4. /superpowers:writing-plans
   O plano tem que DECLARAR TERRITÓRIO: quais arquivos você vai tocar. Antes de escrever,
   rode `git log --since="1 day ago"` e `git status` neles — outras sessões trabalham no
   mesmo repositório e já colidimos por não fazer isso.

5. Execute em loop, com /ponytail:ponytail ativo.
   Toda lógica não-trivial nasce com uma checagem executável — oráculo em
   backend/scripts/orq/. Prove que o oráculo PEGA o defeito: rode contra o código anterior.

6. /code-review no diff.

7. /conecta-pro-skills:fecha-modulo <MÓDULO>
   Três lentes. "NÃO VERIFICADO" é resultado válido; "passou" sem evidência não é.

8. /conecta-pro-skills:deploy-bake
   docker cp não recarrega módulo já importado — só o bake entrega.

9. Depois do bake, confira na ROTA REAL com token válido. Oráculo verde não é entrega.

Regras que não se negociam:
- Não fabricar dado. Sem fonte → "aguardando dado".
- Dinheiro que sai: nunca happy-path. Governo: só leitura.
- Operacional é curado à mão: divergência vira relatório, não correção.
- Commit por pathspec, com o achado no commit e a história longa no relatório.

Ao final, relatório em auditoria/qa/<MÓDULO>_AAAAMMDD.md com veredito por lente e o que
NÃO foi coberto.
```

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

**As três devem ser CÓDIGO no pre-commit e na varredura diária, não skill.** Skill só age
quando alguém a invoca; check age sempre. Foi um check que achou o corte silencioso do
digest às 05:00 de hoje, sem ninguém pedir.
