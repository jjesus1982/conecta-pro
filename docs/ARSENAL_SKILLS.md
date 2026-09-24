# Arsenal de fechamento de módulo — Conecta PRO

> **Operação (o que roda, quando, como ler): `docs/ARSENAL_OPERACAO.md` — uma página.**
> Este arquivo guarda as lições e a história por trás de cada peça.

Ferramenta única para **uma coisa só**: pegar um módulo já codado e deixá-lo *entregue*.

Não é catálogo. Existem 15 skills nossas e 16 genéricas instaladas; aqui entram **as 11 que
atuam no fechamento**, mais as **79 travas mecânicas**. O resto (PDF, slides, folha-CCT,
jurídico, NotebookLM, genéricas de fan-out) é situacional e fica de fora de propósito —
arsenal grande vira cerimônia, e cerimônia é o que faz alguém pular etapa.

Fase do projeto: **revisão e fechamento**. Nada de feature nova. O código existe; falta
provar que funciona, ligar o que ficou solto, e entregar.

---

## 1. As 11 do fluxo

| # | Skill | Responde | Escreve? |
|---|---|---|---|
| 1 | **raio-x-modulo** | o que existe, o que é órfão, o que é casca | não |
| 2 | **finding-schema-drift** | *(só se der 500 por coluna/tabela)* o model pede o que o banco não tem? | sim |
| 3 | **veracity-sweep** | o exibido é verdade, onde não há oráculo? | sim |
| 4 | **plano-conecta** | onde vou pisar — **declara território** | não |
| 5 | **ponytail-conecta** | o que NÃO escrever; onde a preguiça é proibida | — |
| 6 | **oraculo-conecta** | como escrever oráculo que não apodrece | não |
| 7 | **raio-de-impacto** | quem mais depende disto? o defeito tem irmãos? | não |
| 8 | **fecha-modulo** | 3 lentes: dado · tela · código | não |
| 9 | **entregue-de-verdade** | os 3 portões antes de dizer "pronto" | não |
| 10 | **deploy-bake** | tornar durável sem quebrar | sim |
| 11 | **conecta-backend-recon** | *(dentro do raio-x)* rota montada sem superfície | não |

## 2. As 79 travas (código, não skill)

Skill só age quando alguém invoca; **trava age sempre**. Cada uma nasceu de um erro medido.
(Como cada uma é ligada — contada, sim/não, gate semanal, à mão — está na página operacional.)

| Trava | Impede | Onde |
|---|---|---|
| `checar_vocabulario.py` | lista literal que a coluna não tem — *31 obrigações onde havia 5* | `backend/scripts/qa` |
| `cacar_fabricacao.py` | valor inventado quando a fonte falha — *certidão de 180 dias sem consulta* | `backend/scripts/qa` |
| `checar_arsenal.py` | este documento mentindo — *pegou 2 erros meus 2h depois de escritos* | `backend/scripts/qa` |
| `test_oraculo_periodo_fechado.py` | reescrever período fechado — *184 lançamentos* | `backend/scripts/orq` |
| `_mutacao.py` | DELETE/UPDATE largo em produção — *apagou certidão legítima* | `backend/scripts/qa` |
| `checar_repositorio.py` | chamada para método que o repositório não tem — *78 num módulo só* | `backend/scripts/qa` |
| `checar_rotas_frontend.py` | frontend chamando rota que o backend não tem — *9 de 9 no SLA* | `backend/scripts/qa` |
| `checar_oraculo_externo.py` | número que **ninguém de fora** confirma — *ideia do T1* | `backend/scripts/qa` |
| `checar_beats.py` | **rotina agendada que roda e não produz** — *5 camadas, ver abaixo* | `backend/scripts/qa` |
| `checar_mcp_tools.py` | peça de parede **fora do git ou fora da imagem**; conector sem definição versionada; tool apontando para rota que não existe — *o conector do Jordan passou 2 semanas com imagem velha e nada denunciou* | `backend/scripts/qa` |
| `checar_desmonte_comportamento.py` | oráculo que **escreve em produção sem desmontar**, **medido rodando** — *a versão por regex acusou 26 e acertou 1, e foi apagada em 24/08* | `backend/scripts/qa` |
| `checar_periodo_do_servidor.py` | competência/data vinda do **modelo** e não do servidor — *o agente chutou 7/2025 e disse a um porteiro com 91 batidas que ele não tinha ponto* | `backend/scripts/qa` |
| `checar_sucesso_vazio.py` | motor responde **200 sem frase** — *11 de 59 perguntas ao chat morriam em "(sem resposta)" com `ok=True`* | `backend/scripts/qa` |
| `checar_uso_real.py` | **quem usa** — última escrita por família de tabela, requisições por rota, tabela nascida morta — *463 de 686 tabelas sem uma linha; nascer morto nunca acusou* | `backend/scripts/qa` |
| `checar_sino_surdo.py` (+ `sql/sino_corte.sql`) | origem do sino **que ninguém abre** — e **corta sozinho** após 14 medições seguidas, por gatilho BEFORE INSERT — *5.387 avisos em 30 dias, o dono abriu 19; 8 origens surdas* | `backend/scripts/qa` |
| `checar_registros_servidor.py` | registro **vazio ou encolhido** no processo que SERVE (rotas, tools, executores pela guarda, regras, beats, builders) — *executores 0 no backend, 8/8 verdes no teste* | `backend/scripts/qa` |
| `checar_nao_vigiado.py` | tela do redesign que **nenhum oráculo nem regra cita** — *o Balanço exibiu PL de +R$ 2,02 mi por meses sem vigia* | `backend/scripts/qa` |
| `checar_irreversivel.py` | registro **criado depois do disparo** externo (AST) — *a cotação de 31/08 saía por WhatsApp antes de existir* | `backend/scripts/qa` |
| `checar_dominio.py` (+ `verdades_dominio.py`) | verdade de domínio **curada** × código × banco × vigência — *FAIXAS_INSS_2026 com a tabela de 2024 num arquivo e a de 2026 no outro; "erro de domínio não tem trava" virou "tem, depois que um humano escreve a verdade uma vez"* | `backend/scripts/qa` |
| `checar_homologacao_na_receita.py` | **nota de TESTE contada como receita** — a conciliação da NFS-e, rodada com as empresas em homologação, gravou R$ 1.500 de notas minhas na tabela do faturamento real; a trava não confia na coluna `ambiente`, cruza com o que o sistema sabe ter emitido em teste — *24/09/2026, erro do orquestrador* | `backend/scripts/qa` |
| `checar_batida_faltando.py` | dia trabalhado **sem a batida de entrada ou saída** — não é atraso nem falta, é dado que falta, e o mapa de ponto chuta em cima dele — *64% do "atraso" medido pela X2 era isto; 114 dias na produção em 24/09* | `backend/scripts/qa` |
| `checar_bake_pendente.py` | o que está **no ar por docker cp** (docker diff) — e **assa sozinho** na madrugada se as 6 guardas passam — *14 arquivos de duas sessões no ar sem ninguém saber* | `backend/scripts/qa` |
| `checar_llm_martelando.py` | rotina que **martela o LLM falhando** — *30.800 chamadas/dia com 0 ok, quatro dias, e a única evidência era a fatura que não subia* | `backend/scripts/qa` |
| `checar_import_orfao.py` | `from X import Y` com X **apagado do disco** — servidor ou celery cai no boot, um bake por vez — *três pacotes "mortos" vivos por dentro (analytics, contract_analysis, signature), cada um descoberto por um crash* | `backend/scripts/qa` |
| `checar_beat_engole_falha.py` | task agendada cujo `except Exception` **loga e devolve normal** (AST) — task SUCCESS, `task_falha` cego — *o fechamento do razão parou 27 dias com ok=True; 55 tasks assim na estreia* | `backend/scripts/qa` |
| `checar_botao_morto.py` | endpoint que uma tela do redesign chama e o app **não tem** — cruza os 4.300 `endpoint` dos builders com a tabela de rotas, método incluso — *3 botões davam 404 desde que nasceram: `{ano}/{mes}` literal (o front não monta path param) e uma rota que nunca existiu* | `backend/scripts/qa` |
| `checar_tabela_fantasma.py` | `__tablename__` de tabela que **não existe em schema nenhum** — invisível ao censo de uso real por construção — *58 na estreia: a persistência inteira de governo (gov_*, 29) sem migration; `gov_sync_logs` lida pelo painel de status que devolve vazio todo dia* | `backend/scripts/qa` |
| `checar_varchar_teto.py` | `varchar(N)` com valor **encostado no teto** e comprimentos variados — *um varchar(20) passou meses porque o nome tinha exatamente 20* | `backend/scripts/qa` |
| `fechado_bartolo.py` · `fechado_contratos.py` · `fechado_financeiro.py` · `fechado_fiscal.py` · `fechado_gedeon.py` · `fechado_operacional.py` | critério de aceite **executável** por módulo: ✅/❌ por condição, exit code decide — *"fechado" vinha sendo afirmado em prosa*. Semanais desde 06/09: **existiam desde agosto e nenhum caminho os invocava** | `backend/scripts/qa` |
| `varredura_op_acoes.py` | tela/ação do operacional que **existe e não tem como funcionar** (rota morta, sem tela, sem fila) — *3 achados tropeçados um a um no T4* | `backend/scripts/qa` |
| `provar_desmonte.py` | prova de desmonte de UM oráculo, nas três perguntas e na ordem certa — *"escreveu?" vem antes de "antes == depois"* (à mão) | `backend/scripts/qa` |
| `checar_regressao.py` | o que liga tudo isto à meia-noite: linha de base fora do git, NÃO VERIFICADO quando o caçador não responde, sino só com novidade — *a base caiu a 0 numa noite sem resposta e acusou "0 → 25" por dez noites* | `backend/scripts/qa` |

### A lacuna que faltava: **rotina que roda e não produz**

Tínhamos trava para código morto e para número mentiroso. **Nenhuma para a rotina que existe,
está agendada, não reclama — e não faz nada.** Ela custou caro três vezes em agosto:

| sintoma | o que era |
|---|---|
| 3 agentes do GEDEON mortos 3 dias, **8 travas verdes** | `ImportError` na task agendada; 48 falhas no sino, ninguém leu |
| espelho do eSocial **37 dias** sem consultar o governo | beat diário rodando, `consultada_em` nunca gravado |
| **1.258 falhas de LLM, custo US$ 0,00** | nenhuma completou; erro de rotina de fundo não chega a tela nenhuma |

`checar_beats.py` responde em **cinco camadas**, cada uma pegando o que a anterior deixa passar:

```
1. o beat aponta para uma task REGISTRADA?
2. os `from X import Y` DENTRO da task resolvem?
3. o método chamado EXISTE e aceita os argumentos passados?
4. ela quebra CALADO? — `except Exception` que devolve valor: para o Celery isso é SUCESSO
5. a FILA tem consumidor? — beat agendado numa fila que nenhum worker escuta
```

**A camada 3 nasceu de um conserto incompleto:** trocar só o nome da classe transformaria
`ImportError` em `AttributeError` em dois dos três agentes — beat continua vermelho, mensagem
diferente. **A camada 5 é a mais silenciosa de todas:** foram medidas **101 execuções
enfileiradas e nunca consumidas** — mensagem que fica na fila não falha, não estoura, não vai
para o sino. E ela pergunta aos **workers vivos** (`active_queues`), não ao compose: vale quem
está de pé agora, não o que o arquivo promete.

⚠️ **Ruído de sino é o multiplicador desta família.** Sete tarefas falhando 16× cada
transformam o alarme em papel de parede — foi assim que os 3 agentes passaram 3 dias mortos à
vista de todos. **Limpar o ruído vale mais que qualquer conserto isolado.**

⚠️ **`checar_repositorio` tem DOIS olhos, e o segundo nasceu de um verde incompleto meu.**
Com as 78 renomeações prontas ela disse `services: 0` e o dashboard continuava em 500: o
método existia e devolvia **dict** onde a anotação prometia schema. *"O método existe" não é
o contrato inteiro.* **Trava que só verifica metade encerra a investigação — é pior que
vermelho.** Ao escrever qualquer trava, pergunte o que ela ainda deixa passar.

**Três regras trazidas pelo T1, medidas no financeiro (12/08) — e as três valem para todo
mundo, porque nas três ele estava confiante e errado:**

1. **Fora da janela de cobertura de uma fonte, ausência não é prova.** Comparou nosso extrato
   com a API do Inter e tratou "a API não tem linha nesta data" como duplicata: **169
   transações reais apagadas (R$12.117,13)**. O `/extrato` do Inter só devolve de 07/02 em
   diante. Prima-irmã do meu "zero achados por caminho errado é o pior tipo de verde".
2. **Antes de concluir "está velho", confirme que alguém escreve naquele campo.** Ele leu
   `last_sync_at` — coluna **morta**; quem grava é `last_balance_update`. Chegou a desenhar
   um alarme inteiro sobre a premissa falsa.
3. **Alarme que toca sempre é alarme que ninguém lê — o corte temporal é o que o mantém
   crível.** Escrituração agendada 05:20 contra extrato que chega 08:00 tocaria 21h por dia.

> *"O que me pegou foi sempre uma medição contra algo de fora, nunca uma releitura do meu
> próprio código."* — T1

**Mais duas, do mesmo, no dia seguinte:**

4. **Filtro por texto não é contagem — quem conta é o banco.** Ele "adjudicou" três grupos de
   duplicata consultando o extrato do Inter **por nome na descrição**; o filtro não contou um
   par e ele apagou R$32,00 de uma transação legítima. Quem pegou foi a checagem contra o
   saldo do próprio banco, que acusou a diferença exata. *A lição que ele escreveu na véspera
   o pegou no dia seguinte — e desta vez quem o pegou foi a máquina, não ele.*
5. **Invariante que o banco já garante não é invariante: é decoração.** Dois dos três que ele
   ia afirmar já eram impossíveis (índice UNIQUE e CHECK constraint existentes) — só
   descobriu **tentando ficar vermelho**. Viraram outra coisa, melhor: o oráculo passou a
   afirmar que **a garantia continua de pé**, porque constraint some em migration distraída e
   o defeito volta calado.

**Três regras que toda trava nova paga, medidas no MVP de serviços:**

1. **Prove o arreio antes de acusar o código.** Instanciei uma classe com o argumento errado
   e o `AttributeError` parecia defeito do sistema. Depois, 7 erros de tipo nos meus
   arquivos: o mesmo teste num arquivo intocado deu **48** — era a checagem isolada.
2. **Falso positivo mata a confiança mais rápido que achado nenhum.** A trava do frontend
   normalizava a barra final de um lado só: 3 dos 14 primeiros achados devolviam 200 no curl.
3. **Alcance se mede da TELA para trás.** "Alguém importa este arquivo" dava 185 de 205 vivos;
   andando dos `app/**`, os campeões da lista não são usados por página nenhuma. Número
   alarmista é tão inútil quanto número escondido.

**`_mutacao.Mutacao` é obrigatório em todo script que altera produção.** Ensaio é o padrão;
`--aplicar` explícito; acima do teto exige `--forcar`; lista vazia nunca aplica.

**Automático, à 00:00** (madrugada: conserto sem ninguém usando o sistema).
`checar_regressao.py` roda as travas mecânicas contra uma **linha de base** — dívida velha não
vira ruído, fabricação nova acusa e **vai para o sino** — e só vai quando é NOVIDADE: o
mesmo vermelho de ontem fica no log e volta ao sino na segunda-feira. Medido em 06/09/2026:
a varredura tocou vermelho dez noites seguidas com o mesmo número, o sino recebeu 5.387
avisos em 30 dias e o dono abriu 19. A base mora em
`/var/lib/conecta/qa_baseline.json`, **fora do git de propósito**: ela é reescrita sozinha
quando a dívida cai, e arquivo versionado alterado por cron deixaria o working tree sujo —
outro terminal veria ` M` e, pela regra da parede, pararia. Automação não pode disparar a
regra da parede falsamente.

Baixar a base é automático; **subir exige `--gravar` explícito** — deixar a dívida crescer é
decisão, não acidente.

---

## 3. Ordem até "entregue"

```
┌─ DESCOBRIR ─────────────────────────────────────────────────┐
│ 1. raio-x-modulo         o que existe, o que é órfão/casca  │
│ 2. finding-schema-drift  SÓ SE houver 500/UndefinedColumn   │
│ 3. veracity-sweep        o exibido é verdade? (sem oráculo) │
└─────────────────────────────────────────────────────────────┘
┌─ DECIDIR ───────────────────────────────────────────────────┐
│ 4. plano-conecta         DECLARA TERRITÓRIO (5 terminais)   │
└─────────────────────────────────────────────────────────────┘
┌─ CONSTRUIR ─────────────────────────────────────────────────┐
│ 5. ponytail-conecta + oraculo-conecta por lógica não-trivial│
│ 6. raio-de-impacto — o defeito tem irmãos? + /code-review   │
└─────────────────────────────────────────────────────────────┘
┌─ PROVAR ────────────────────────────────────────────────────┐
│ 7. fecha-modulo          3 lentes: dado · tela · código     │
│ 8. entregue-de-verdade   os 3 portões                       │
└─────────────────────────────────────────────────────────────┘
┌─ ENTREGAR ──────────────────────────────────────────────────┐
│ 9. deploy-bake · conferir na ROTA REAL depois do bake       │
└─────────────────────────────────────────────────────────────┘
┌─ VIGIAR (automático, 00:00) ────────────────────────────────┐
│ oráculos + checar_regressao · vermelho vira alerta no sino  │
│ o alerta compara com a rodada anterior: andou ou parou      │
└─────────────────────────────────────────────────────────────┘
```

**ENTREGUE** = os três, sem exceção:
1. servido pela **rota real depois do bake** (oráculo verde não é entrega);
2. oráculo verde na varredura;
3. **nenhuma superfície nova sem vigia**.

Faltando um, é "feito".

---

## 4. Regras que não se negociam

### Parede entre terminais — a primeira de todas

Cinco terminais trabalham neste repositório e neste banco **ao mesmo tempo**. Cada um no seu
módulo. **Nenhum desfaz o que o outro fez.**

Antes de escrever a primeira linha:

```bash
git log --since="1 day ago" --oneline -- <arquivos que vou tocar>
git status --short -- <arquivos que vou tocar>
```

| O que aparece | O que fazer |
|---|---|
| commits recentes de outro terminal | **leia-os antes de decidir** — pode já estar feito, ou pode haver decisão de negócio ali |
| ` M arquivo` (WIP não commitado) | **espere.** Não edite |
| **nada** | ⚠️ confirme que o arquivo é RASTREADO antes de concluir "livre" |

⚠️ **A parede lê `git status` — onde o git é cego, ela não existe.** Em 12/08 achei 73
arquivos de código do frontend (`frontend/src/lib`, incluindo `pdf.ts` e o `axios-instance`)
engolidos pela regra `lib/` do bloco de virtualenv Python. Sem histórico, sem revisão — e
dois terminais podiam se sobrescrever ali **sem nenhum sinal**. Silêncio do `git status` pode
ser "livre" ou "invisível"; são coisas opostas:

```bash
git check-ignore -v <arquivo> && echo "IGNORADO — a parede não protege este arquivo"
```
| nada | livre |

- **Não existe "só uma linhinha" em arquivo de outro terminal.**
- **`git add <arquivo>` leva o WIP alheio junto.** Índice temporário isola *arquivo*, não
  *trecho* — não resolve.
- **Decisão de negócio de outro terminal é lei**, mesmo que o código pareça errado. O corte
  contábil de 01/08 estava certo; quem passou por cima fui eu.
- Em dúvida sobre fronteira: **relatório, não correção.**

*Custo medido em 12/08: reclassifiquei 184 lançamentos por cima de decisão do Jordan
implementada pelo T1, e commitei WIP dele junto com o meu. Duas vezes, no mesmo dia.*

### As outras

- **Não fabricar.** Sem fonte, "aguardando dado". Vale para código e para relatório.
- **Dinheiro que sai:** nunca happy-path, sempre gate humano. **Governo:** só leitura.
- **Operacional é curado à mão pelo Jordan:** read-only para agentes; divergência vira
  relatório.
- **Commit por pathspec.** Nunca `git add -A`, nunca `--amend` amplo. ⚠️ **Arquivo NOVO não
  entra por `git commit -- <arq>`** — precisa de `git add <arq>` explícito antes, nomeado.
- **`docker cp` é volátil.** Só o bake entrega — e não recarrega módulo já importado.
- **Mutação em produção usa `_mutacao.Mutacao`.** Ensaio antes, sempre.

### As quatro compradas em 23–24/08/2026

- ⭐ **`git commit` aqui é entrar na fila de deploy de outra pessoa.** Não existe "commitei mas
  ainda não subi": o próximo bake de qualquer terminal leva o seu código. **Só commite o que
  pode ir a produção agora, sem você por perto para completar.**
- ⭐ **Confere o EXIT CODE, não o log.** O hook `ruff-format` reformata e faz o commit sair com
  `exit=1`; um `git log -1` logo depois mostra o commit de **outra sessão** e parece sucesso.
  Num índice compartilhado, **a evidência de sucesso é o trabalho alheio**. Custou 2 commits.
- ⭐ **Prova vazia sai verde.** `ANTES == DEPOIS` sobre zero escrita passa sempre — é a mesma
  forma de `exibido == banco` sobre 0 linhas. **Antes de afirmar que limpou, prove que
  escreveu.** E toda prova de desmonte tem duas metades: *[1] contagem intacta* e *[2] a
  vizinha REAL continua lá* — sem a segunda você provou que apagou, não que apagou só o seu.
- ⭐ **Confirmação por string não é parede contra LLM.** Uma tool que exige `confirmar="ACEITAR"`
  e devolve *"chame de novo com confirmar=ACEITAR"* ensina o chamador a passar. Serve para
  humano lendo; não serve para agente. **Quem aprova não pode ser quem pede** — o `propose`
  sai da conversa e espera um terceiro, e o aprovador lê a **consequência**, não o nome da tool.

### Git: a terceira armadilha, e ela contradiz a regra de cima

⚠️ **`git commit -- <pathspec>` commita o WORKING TREE daqueles caminhos e IGNORA o índice.**
Por desenho. Então ele **desfaz um `git rm --cached`** feito segundos antes, e grava a mudança
de conteúdo no lugar da remoção — `git show --stat` diz `4 ++--` e nunca `delete mode`.

**A regra da casa ("commit por pathspec, o índice é compartilhado") e `git rm --cached` são
incompatíveis.** Para destrackear aqui, índice temporário:

```bash
export GIT_INDEX_FILE=/tmp/idx
git read-tree HEAD && git rm --cached <arqs>
git commit-tree $(git write-tree) -p HEAD -m msg | xargs git update-ref HEAD
unset GIT_INDEX_FILE
git rm --cached <arqs>        # ← e ainda remova do índice COMPARTILHADO, senão volta como `A `
```

Falhei duas vezes nisto em 24/08/2026 e, nas duas, **acusei o índice compartilhado** — versão
plausível, com precedente nesta casa, e errada. *Prove o arreio antes de acusar o código.*

### Estado de execução não se versiona

Arquivo escrito por processo vivo (cron, bot, beat) dentro do repositório deixa ` M`
permanente — e **a regra da parede entre terminais é ` M` = outro terminal está aqui, para e
espera**. Com o working tree sujo de automação, o sinal que protege o código vira ruído.

Medido em 24/08: `git status` com **713 entradas**, das quais 33 eram o agente CTO escrevendo
`predicao/*.json` e rotacionando `memory/snapshots/`. A mesma decisão já tinha sido tomada
três vezes (`qa_baseline.json`, `agents/knowledge/*.json`, `agents/cto/tickets/*.json`) **sem
que ninguém varresse os irmãos**. E `.gitignore` **não desversiona o que já está versionado**:
a regra dos snapshots existia desde antes e os 30 antigos seguiam rastreados.

### Sobre a própria ferramenta: heurística erra nos DOIS sentidos

Seis medições por regex sobre código, num único dia, e **três inflaram, três zeraram**:

| o que media | disse | é |
|---|---:|---:|
| período no corpo do handler | 11 | 1 |
| equivalência de tool por NOME | 112 | 43 |
| prefixo exigindo aspas coladas | **0** | 23 |
| marca de teste por citação no arquivo | 6 | 27 |
| limpeza de entrada exigindo literal `'ZZ` | 29 | 20 |
| desmonte só como `DELETE … LIKE` | 20 | 18 |

⚠️ **O mais perigoso foi o `0`**, não os inflados: número inflado alguém confere; **zero
ninguém confere, porque parece boa notícia.**

### Número que você não mediu vai com a fonte — o rigor não pode parar na fronteira do seu módulo

Em 24–25/08/2026, **três números atravessaram sessões e cada um teve de ser buscado na fonte**:

```
capacidades do agente      62 × 189 × 49    (três contagens legítimas de coisas diferentes)
achado do ponto            19 dias × 9 dias  (critérios e janelas diferentes)
chaves de idempotência     429 × 357 × 1369  (vínculo chutado vs lido no código)
```

O `1369` foi meu: chutei `draft_id` onde o código usa `reference_id` e não filtrei `is_active`.
**Fui ler o código antes de publicar** e virou 357. O `baixa_pagavel 72` circulou por três
sessões e **não existe** — zero chaves, não "zero órfãs de 72" — e quase virou uma varredura
no financeiro atrás de baixa que nunca deixou de acontecer.

⭐ **O diagnóstico mais fino veio de quem errou** — e ele pediu que ficasse escrito que
**nasceu do erro, não da percepção**: *"regra que sobe com a origem limpa demais perde o
aviso — quem lê 'marque o que mediu e o que repetiu' precisa saber que quem escreveu isso já
tinha misturado os dois na mesma mensagem."* (sessão de integrations, 25/08):

> *"Eu MEDI o meu lado com rigor e construí a conclusão mais consequente em cima da lista do
> outro, sem tocar nela. O rigor parou exatamente onde o achado deixava de ser meu. E o
> formato escondeu: como as três primeiras linhas eram medição minha, a quarta herdou a
> aparência de medida."*

**Regras:**
- **marque o que mediu e o que repetiu.** Bloco de números onde só alguns são seus lê-se
  inteiro como medição — e a conclusão costuma se apoiar justamente no emprestado;
- **antes de agir sobre número alheio, reproduza-o** — ou diga que não reproduziu;
- **não reproduziu e o número decide algo?** Vá ao código descobrir o vínculo real. Foi o que
  separou 1369 de 357, e foi feito *antes* de mandar, que é onde a diferença existe.

### Campo compartilhado ganha leitor novo — veja por qual campo ele seleciona

Quando uma capacidade nova passa a ler um campo que já existia, o dono do campo costuma
descobrir que **o seu valor responde uma pergunta que ele não escreveu**. Em 25/08 a Central
ganhou aprovação em LOTE, e o dono de um rascunho 🔴 com `requires_otp=False` levantou:
*"meu False significava 'OTP é para executar money-out'; se agora significa também 'pode ser
aprovado em lote', ele diz uma coisa que eu não quis dizer."*

**A pergunta era a certa. A resposta veio do SQL, e era não:**

```sql
SELECT id FROM agent_drafts WHERE status='rascunho' AND payload->>'lote_id' = :l   -- quem ENTRA
if draft.requires_otp: pulados.append(...)                                          -- quem EXECUTA
```

Duas paredes em série, e discriminadores **separados desde o desenho**: o rascunho avulso não
tem `lote_id`, logo nunca chega ao laço. Não foi excluído — está estruturalmente fora.

⭐ **Registrar só o alerta produz paranoia; com o contraexemplo vira critério** (formulação do
dono do campo): **vá ver por qual campo o leitor novo seleciona antes de supor que é pelo seu.**
E quem propõe "trocar o discriminador para o meu campo" costuma estar curando um acoplamento
que não existe criando um que existiria.

### Acabar de acertar dá licença para o próximo palpite

A armadilha mais eficiente da noite de 24→25/08 não foi técnica. **Acertar uma correção cria
autoridade, e autoridade dispensa a próxima medição — nos dois sentidos, no mesmo par, na
mesma noite:**

```
sessão A pega um erro real de B  →  B aceita a correção SEGUINTE de A sem remedir
                                →  A, envalentonado, critica um teste de B SEM ABRIR o arquivo
```

Foi exatamente isto, uma hora depois de a regra *"marque o que mediu e o que repetiu"* ter
sido escrita, **pela mesma pessoa que a escreveu**.

O caso concreto: `baixa_pagavel`. Uma sessão disse "72 órfãs, é dinheiro parado" (certo na
existência); a outra disse "não existe, 0 chaves" (a consulta media *quantas bloqueiam*, com o
mesmo `is_active` do código, e a frase disse *quantas existem*). **As duas metades juntas é que
descrevem o fato:** 72 existem, todas `is_active=false`, e o gate exige ativa — logo **não
bloqueiam**. Nenhuma das duas sozinha estava certa.

**Regras:**
- **nenhum par é confiável por reputação, só por comando rodado** — inclusive quem acabou de
  te salvar, e principalmente você depois de salvar alguém;
- **medir "quantas bloqueiam" e escrever "quantas existem"** é o mesmo erro de etiqueta que o
  manifesto de risco cometeu 54 vezes: o número certo com a frase errada;
- ⚠️ **"não está quebrado agora" ≠ "está tudo bem".** Não havia coluna que dissesse quando as
  72 foram desativadas: se estiveram ativas antes, bloquearam. **O estado atual não conta a
  história — e a forma honesta é "não sabemos se houve, e dá para saber olhando X".**

### Tool inerte dentro de moldura que envia NÃO é inerte

Antes de rodar qualquer caminho de agente ponta a ponta, **pergunte o que a MOLDURA faz**, não
só a tool. Medido em 25/08/2026 no conector do WhatsApp (sessão de integrations):

```
a tool          _criar_rascunho_proposta → criar_rascunho          inerte, docstring diz "nada é enviado"
a moldura       agent_service.py:4603 · o LOOP responde ao lead ao fim do turno
                agent_service.py:2414 · handoff automático dispara WhatsApp ao RESPONSÁVEL
```

**Chamar qualquer tool numa conversa real termina em mensagem ao lead** — a tool é inerte, o
turno não. E o handoff manda para o telefone de um colega, por classificação, sem ninguém
pedir. Quem fosse "testar sem risco" com o próprio número mandaria mensagem para outra pessoa.

⭐ É a mesma forma do `confirmar=True` que mora na função interna e não na rota: **o disparo
vive uma camada abaixo de quem você chama, e quem chama sem saber já mandou.**

**Nosso motor in-process foi conferido no mesmo dia e está limpo** — `engine.py` e
`rascunho.py` não têm caminho de envio externo; as referências a e-mail ali resolvem **quem
aprova**, não destinatário. Mas isso só se sabe medindo, e vale remedir quando a moldura mudar.

### Guard de ambiente pede PROVA DE IDENTIDADE, não sinal de vida

"Fila vazia não é resultado" apareceu **quatro vezes em dois dias**, e a quarta é a que ensina:

```
1. ANTES == DEPOIS sobre zero escrita                    (o caminho nem foi exercido)
2. checar_repositorio achando 0 dentro do container      (raiz /app, não /opt/…/backend)
3. trava de desmonte varrendo /app/scripts/orq no host   (glob vazio → exit 0)
4. guard que só pergunta "existe e tem .py?"             ← EXISTE UM /app NO HOST
```

Nas três primeiras o caminho **não existia**. Na quarta ele existia e era o errado — e um
`.py` solto num diretório qualquer devolvia `TOTAL: 0` com exit 0.

**Um guard que pergunta "tem algum código aqui?" aprova qualquer diretório plausível.** Peça o
que só o lugar certo tem:

```python
esperados = {"crm", "financial", "people_management", "operacional"}
if len(esperados & {p.name for p in raiz.iterdir() if p.is_dir()}) < 3:
    raise SystemExit(2)
```

E **prove nas quatro direções, lendo o exit code do SCRIPT** — não o do `tail`, não o do
`sed`, não o do último elo do pipe. Esse erro custou três leituras erradas num dia só, e é
irmão do `> /dev/null` no `docker cp`: *ler o resultado do elo errado.*

### Família não é FORMA, é POPULAÇÃO — teste o dado antes de consertar os irmãos

*Conserte a família, não o caso* é regra da casa — e tem um irmão que ninguém escreve: **antes
de consertar os irmãos, prove que eles têm o defeito.** Forma igual com dado diferente dá
veredito diferente.

Caso de 27/08: um `Content-Disposition` estourou em latin-1. Outro módulo tinha **dois pontos
com a mesma forma** (nome de pessoa interpolado cru no cabeçalho). Em vez de consertar por
semelhança, testaram a população real:

```
91 nomes de pessoa testados ..... 0 quebram
 8 postos testados .............. 0 quebram
```

**Não quebram porque acento do português (ç, á, ã, é) CABE em latin-1.** O que estourou foi o
**travessão (—)**, que não cabe — e travessão aparece em **título digitado por humano**, não em
nome vindo do cadastro. Mesma forma, populações diferentes.

⭐ E a decisão certa foi **não mexer**, registrando a condição que acorda o defeito: *"se entrar
nome com caractere fora do latin-1, ou se alguém passar a montar esses nomes de arquivo a
partir de texto digitado, os dois pontos acordam."*

**Isto poupa trabalho, não cria:** no mesmo par de dias, uma varredura por forma acusou **26**
oráculos sem desmonte e a execução absolveu **25**; outra acusou **11** tools chutando data e
sobrou **1**. Três vezes a mesma lição, duas caras e uma barata.

**Antídotos, nesta ordem:**
1. **meça por comportamento, não por forma** — rode e conte, em vez de procurar a sintaxe.
   Nenhum regex sabe quantas formas de escrever `DELETE` existem; a contagem sabe;
2. **meça a mesma coisa por dois caminhos** e desconfie quando divergirem — foi o que pegou as
   seis;
3. **confira um a um antes de travar.** Trava que grita sem motivo é trava que se aprende a
   ignorar.

### Número dentro de comentário leva a data em que foi medido

Comentário que diz *"'saida_almoco' não existe — medido em 07/2026, zero de almoço"* continuava
verdadeiro sobre julho e **falso sobre agosto**, quando o app ganhou botão de pausa e a
contagem virou 288. Quem lê acredita no comentário, não na tabela.

**Bug erra e dá para ver; premissa envelhecida acerta até parar de acertar, e ninguém percebe
a transição.** Escreva `medido em <data>` ao lado de todo número que justifica uma decisão —
e, ao achar um vencido, **atualize a justificativa antes de mexer na regra**: no caso acima a
regra estava certa e só a razão tinha morrido.

---

## 5. Roteiro copiar-colar

> Troque **`<MÓDULO>`** e cole.

```
Vamos fechar o módulo <MÓDULO> do Conecta PRO. Fase de REVISÃO: nada de feature nova — é
provar o que existe e ligar o que ficou solto.

ANTES DE TUDO: confira se outro terminal está trabalhando neste módulo.
`git log --since="1 day ago"` e `git status` nos arquivos do módulo. Se houver WIP de outro
terminal, ESPERE — não editamos por cima e não desfazemos o trabalho de ninguém.

Depois siga a ordem, me dizendo o resultado de cada etapa:

1. /conecta-pro-skills:raio-x-modulo <MÓDULO>
2. Se houver 500 por coluna/tabela: /conecta-pro-skills:finding-schema-drift
3. /conecta-pro-skills:veracity-sweep <MÓDULO>   (só onde não há oráculo)
4. /conecta-pro-skills:plano-conecta              (o plano DECLARA TERRITÓRIO)
5. Execute em loop com /ponytail:ponytail + /conecta-pro-skills:ponytail-conecta.
   Cada lógica não-trivial nasce com oráculo (/conecta-pro-skills:oraculo-conecta),
   provado que PEGA — rode contra o código anterior e veja falhar.
6. /conecta-pro-skills:raio-de-impacto  (o defeito tem irmãos?) e /code-review no diff.
7. /conecta-pro-skills:fecha-modulo <MÓDULO>
8. /conecta-pro-skills:entregue-de-verdade
9. /conecta-pro-skills:deploy-bake e confira na ROTA REAL com token válido.

Regras: não fabricar dado · money-out e governo nunca em happy-path · operacional é
read-only · commit por pathspec · mutação em produção só via _mutacao.Mutacao.

Ao final: auditoria/qa/<MÓDULO>_AAAAMMDD.md com veredito por lente e o que NÃO foi coberto.
```

---

## 6. O que o arsenal ainda não faz

**Mapa do não-vigiado** — cruzar a superfície (rotas, telas, KPIs) com os oráculos e devolver
o descoberto, ordenado por raio de dano. É a única das três lacunas originais que falta; as
outras duas viraram `cacar_fabricacao` e `checar_vocabulario`. O MVP de serviços deu meio
caminho: `checar_rotas_frontend` já responde "que superfície do frontend aponta para o vazio";
`checar_uso_real` (06/09) responde a metade "quem de fato usa" — o cruzamento com os oráculos
continua por fazer.

**Uso real por PESSOA, nas leituras.** `checar_uso_real` vê escrita autenticada por rota e
por pessoa (`crm_audit_log` grava todo POST/PUT/PATCH/DELETE com o `user_id` do JWT), mas
leitura só aparece no nginx, sem usuário. "O Jordan abriu a tela" não é medível; "o Jordan
gravou algo por esta rota" é.

**Ação irreversível antes de gravar** tem trava desde 06/09 (`checar_irreversivel`, por AST,
só criação). Ela é forma, e forma erra: os 6 primeiros achados eram `UPDATE enviado=true`
depois do envio — a ordem certa — e foram conferidos um a um antes da base. Envio por
`httpx.post` a host externo continua fora dela.

**Descoberta.** O T1 fechou meio financeiro sem saber que as travas existiam — *"não usei
nenhuma das três: não sabia que existiam"*. Arsenal que ninguém acha é arsenal que não
existe. Desde 06/09 há `docs/ARSENAL_OPERACAO.md`, uma página com o que roda e como ler; o
que ainda falta é algo que a apresente a uma sessão nova sem alguém colar um roteiro.

**Oráculo interno não pega banco de dados errado.** Os 67 comparam *exibido == banco*: os
dois lados nossos. Quando o extrato teve 880 linhas duplicadas e 94 sinais invertidos, a tela
mostrava fielmente o que o banco tinha — **verde, e mentira**. `checar_oraculo_externo`
pergunta o que falta: *quem, de fora daqui, confirma este número, e quando confirmou?* Sete
âncoras hoje (saldo do banco, extrato, pagamentos do Inter, certidões, eSocial, folha da
Portte, NFS-e). ⚠️ **Âncora ausente é o pior achado** — o número que ninguém confirma nem
aparece na lista; leia com `--listar` e pergunte o que falta.

**Vigilância tem DOIS sistemas, e é fácil contar só um.** Oráculos em `scripts/orq/` rodam à
00:00 e aparecem na varredura; **regras proativas** em `notifications/proativo/regras.py`
rodam em beat e **não aparecem**. O extrato, por exemplo, é vigiado por `caixa_divergente`,
que é regra — quem contar só oráculos vai declarar o extrato descoberto, e quem contar só
regras vai achar que está tudo visto às 00:00.

**Erro de domínio: só depois que um humano olha.** Alíquota errada, competência trocada,
conta contábil semanticamente errada: o número tem fonte, passa em todos os portões, e está
errado. Desde 06/09 existe `verdades_dominio.py`: quem entende escreve a verdade UMA vez
(valor, fonte, vigência) e `checar_dominio` confere todo dia que o código diz o mesmo, que
a mesma verdade não tem dois valores, e que a vigência não venceu. O que não está na tabela
continua sem trava — a tabela é o limite, e crescê-la é trabalho de quem entende.

### Onde as skills vivem

Cópia viva em `~/.claude/skills/conecta-pro-skills/`; espelho versionado em
`skills/_plugin/`. Editar de um lado só faz divergir — `checar_arsenal.py` acusa.
