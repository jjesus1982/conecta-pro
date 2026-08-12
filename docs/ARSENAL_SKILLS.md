# Arsenal de fechamento de módulo — Conecta PRO

Ferramenta única para **uma coisa só**: pegar um módulo já codado e deixá-lo *entregue*.

Não é catálogo. Existem 15 skills nossas e 16 genéricas instaladas; aqui entram **as 11 que
atuam no fechamento**, mais as **5 travas mecânicas**. O resto (PDF, slides, folha-CCT,
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

## 2. As 7 travas (código, não skill)

Skill só age quando alguém invoca; **trava age sempre**. Cada uma nasceu de um erro medido.

| Trava | Impede | Onde |
|---|---|---|
| `checar_vocabulario.py` | lista literal que a coluna não tem — *31 obrigações onde havia 5* | `backend/scripts/qa` |
| `cacar_fabricacao.py` | valor inventado quando a fonte falha — *certidão de 180 dias sem consulta* | `backend/scripts/qa` |
| `checar_arsenal.py` | este documento mentindo — *pegou 2 erros meus 2h depois de escritos* | `backend/scripts/qa` |
| `test_oraculo_periodo_fechado.py` | reescrever período fechado — *184 lançamentos* | `backend/scripts/orq` |
| `_mutacao.py` | DELETE/UPDATE largo em produção — *apagou certidão legítima* | `backend/scripts/qa` |
| `checar_repositorio.py` | chamada para método que o repositório não tem — *78 num módulo só* | `backend/scripts/qa` |
| `checar_rotas_frontend.py` | frontend chamando rota que o backend não tem — *9 de 9 no SLA* | `backend/scripts/qa` |

⚠️ **`checar_repositorio` tem DOIS olhos, e o segundo nasceu de um verde incompleto meu.**
Com as 78 renomeações prontas ela disse `services: 0` e o dashboard continuava em 500: o
método existia e devolvia **dict** onde a anotação prometia schema. *"O método existe" não é
o contrato inteiro.* **Trava que só verifica metade encerra a investigação — é pior que
vermelho.** Ao escrever qualquer trava, pergunte o que ela ainda deixa passar.

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
vira ruído, fabricação nova acusa e **vai para o sino**. A base mora em
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
- **Commit por pathspec.** Nunca `git add -A`, nunca `--amend` amplo.
- **`docker cp` é volátil.** Só o bake entrega — e não recarrega módulo já importado.
- **Mutação em produção usa `_mutacao.Mutacao`.** Ensaio antes, sempre.

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
caminho: `checar_rotas_frontend` já responde "que superfície do frontend aponta para o vazio".

**Erro de domínio não tem trava possível.** Alíquota errada de Anexo III, competência
trocada, conta contábil semanticamente errada mas existente: o número tem fonte, passa em
todos os portões, e está errado. Ali só quem entende do assunto olhando.

### Onde as skills vivem

Cópia viva em `~/.claude/skills/conecta-pro-skills/`; espelho versionado em
`skills/_plugin/`. Editar de um lado só faz divergir — `checar_arsenal.py` acusa.
