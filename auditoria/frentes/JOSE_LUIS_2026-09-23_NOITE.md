# José Luís — o que ficou de pé na noite de 23/09/2026

**Para:** Jordan
**Estado:** itens 2, 3, 4 e 6 **no ar e assados** (md5 do disco == md5 da imagem) · item 1 (a
chave da captura de grupo) preparado e **não ligado** — é o único passo que espera a sua palavra
**Oráculo:** `scripts/orq/test_oraculo_grupos_jose_luis.py`, na varredura das 05:00, e provado
que fica vermelho se alguém tirar a parede

---

## O que já está provado por chamada, não por leitura de código

### Item 2 — modo observador (a parede)

Mandei uma mensagem real pelo webhook, como o Chatwoot manda:

```
{"status":"ok","grupo":"120363285473431324@g.us","observador":true,"message_id":99900001}
```

E no banco:

```
OPERACIONAL | ORLAILSON PAIVA PEREIRA | funcionario | operacional | relevante=t
chamadas ao agente: 0
```

Três coisas nessa linha valem mais que o `observador: true`:

- o autor foi resolvido pelo **telefone** (`ORLAILSON PAIVA PEREIRA`, `funcionario`), não pelo
  nome que o WhatsApp manda — que é forjável;
- a parede roda **antes** do enfileiramento do agente. Não é instrução de prompt, não é `foco`
  de papel: em modo `observar` o agente **não é chamado**. Prompt se desobedece; caminho que
  não executa, não;
- o José Luís tinha escrito a régua melhor que eu: *"silêncio tem que ser regra técnica, não
  minha boa vontade."*

### River Park fora — o controle que mais importa

Grupo **não cadastrado** (usei um JID inventado com o nome River Park):

```
resposta: observador: true     ← agente calado
wa_grupo_mensagens:   0        ← nada absorvido
agent_drafts:         0        ← nenhum pedido registrado
```

Grupo que ninguém cadastrou é ignorado **por inteiro**, não só silenciado. É fail-closed de
propósito: alguém te adicionar num grupo novo amanhã não começa a gravar conversa de terceiro.

### Item 2 do seu recado — pedido de escala vira aprovação

```
"Jordan, preciso trocar meu plantao de sabado com o Marcos, da pra ver?"
  → Autorizar troca de plantão — ORLAILSON
     gate 🟡 · status rascunho · aprovadores admin+gerente_operacional
     aplica_automaticamente: false
```

Mandei **duas vezes** a mesma mensagem: **um** rascunho. Idempotente por pessoa+rótulo+dia.

⚠️ Uma escolha que eu tomei e você precisa saber: **aprovar NÃO muda a escala.** Operacional é
curado à mão por você, e isso vale também para o que o agente registra. O título diz
"Autorizar", não "trocar" — um rascunho que se lesse "plantão trocado" faria quem aprova
acreditar num efeito que não existe. Aprovar autoriza; aplicar segue sendo seu clique.
Se você quiser que aprovar aplique de verdade, isso é decisão sua e eu preciso ouvir.

### Item 1 — Orlailson enxerga toda a operação

Aqui eu ia errar, e vale contar como.

A ideia óbvia era derivar "supervisor" de `employees.cargo ILIKE '%supervis%'`. Hoje isso dá
**exatamente uma** pessoa (ele, `Supervisor Operacional`), então funcionaria — e seria a trava
observando a coisa errada outra vez: `cargo` é texto que você edita na tela, e um "Supervisor
de Portaria" cadastrado semana que vem ganharia, **em silêncio**, visão sobre a vida de 61
pessoas. Autorização não se infere de rótulo.

A autoridade já existia e eu não tinha visto: ele tem conta no ERP com
`users.role = gerente_operacional`, ligada ao cadastro por `employee_id`. Reusei. São **duas
condições independentes**: o telefone resolve a funcionário com vínculo vivo **e** a conta tem
o papel.

E não são redundantes — o controle prova:

```
ORLAILSON (92981386006)  tipo=funcionario  papel=gerente_operacional   ✅
ELIZIEL   (92984997784)  tipo=lead         papel=None                  ✅ barrado
```

🔴 **Achado que é seu, não meu:** **Eliziel Gonzaga** tem `users.is_active = true` com
`gerente_operacional`, e o colaborador está `inativo`. No José Luís ele cai na primeira
condição e não entra. Mas a **conta viva com papel de gerente no ERP** é um furo de RBAC que
não é deste módulo — não mexi, perfis são seus.

✅ **`visao_operacao` — ele enxerga a operação, não só os grupos.** Voltei nisso depois de
confirmar os schemas (confirmar é medição; o que eu tinha me recusado a fazer era escrever SQL
sobre schema chutado). Reusa `dashboard_service.get_dashboard`, a **mesma** função que monta a
tela de ponto — não reescrevi consulta, porque número que o WhatsApp mostra diferente da tela é
pior que número nenhum: quem lê não sabe em qual acreditar.

```
colaboradores 63 · por escala: 12x36=42, 44h=21
a resolver: 210 inconsistências de ponto · 0 sem escala · 0 pontos em aberto
banco de horas: saldo médio −46,7h em 50 colaboradores
```

🔴 **Dois achados que caíram disso, e o segundo me corrigiu:**

1. **A carga do Sólides está de 17/09 — 7 dias.** Informativo, não alarme (veja abaixo por quê),
   mas você precisa saber: está velha de propósito ou a rotina parou?
2. **Eu quase reportei "rotina de ponto parada".** O dashboard dizia `presentes: 0 / ausentes: 63`
   e a carga tinha 7 dias — parecia óbvio. Fui medir as batidas: **83 batidas de 34 pessoas em
   23/09**, 2 já hoje. O ponto está fluindo; o relógio é **nosso** (`gp_clock_punches`), não o
   Sólides. O `0/63` é artefato da **meia-noite** — 00:07, o turno ainda não bateu.

E isso condenou o guarda que eu mesmo tinha escrito: ele media a carga do Sólides e dispararia
aviso de defasagem em **toda** chamada. Alarme que soa sempre é alarme que ninguém lê — é o hash
sobre bytes de PDF outra vez, e outra vez **dentro da correção feita para proteger de dado
velho**. Agora o frescor sai da última batida (régua de 12h, porque o turno mais longo da casa é
12x36), e o campo se chama `hoje_desde_meia_noite` com um `leia_assim`: número sem a janela que o
gerou não é dado, é susto.

⚠️ E o caminho para isso **não** era a ponte MCP: o conector interno não publica operacional, e
alargar o escopo dele exporia escrita de escala ao time. É in-process, como as calculadoras do
fiscal.

🔶 **O que ainda falta da operação:** postos, alocações vigentes, substituições pendentes e ASOs
vencendo. Rotas mapeadas, não ligadas:

```
/operacional/posts · /operacional/allocations/current · /operacional/substitutions/pending
/operacional/grade/{posto_id} · /operacional/presenca/substitutos/{posto_id}
/people-management/ponto/justificativas/pendentes · /people-management/sst/asos/vencendo
```

### Itens 3 e 4 — tom separado de dado, e resumo sob demanda

`resumo_grupos`, e só o supervisor alcança:

```
fuso: America/Manaus (UTC-4)
conversa_por_grupo: OPERACIONAL · operacional · 3 mensagens
dado relevante:     ORLAILSON 23/09 23:22 · 23/09 23:13
pedidos de escala:  Autorizar troca de plantão — ORLAILSON · rascunho · 23/09 23:22
decidir em:         /redesign/aprovacoes
```

`tom` (bom dia, figurinha, churrasco) entra **só como contagem** — o texto só aparece do que foi
classificado como dado. Foi o que o José Luís propôs e você aceitou pelo motivo certo: *"se todo
grupo despejar tudo, viramos ruído"*. Nada é empurrado: alguém pergunta, o resumo se monta.

O classificador é determinístico (sem LLM, custo zero) e acertou 10/10, incluindo os três
controles que **não** podem disparar: relato do passado ("ontem o Eduardo cobriu"), já resolvido
("já resolvi com o Marcos") e defeito que não é escala ("o portão está com defeito").

---

## Três defeitos meus, achados antes de assar

Conto porque os três são da mesma família e a família é a minha.

1. **O supervisor ia receber o prompt de VENDAS.** Dei a ele `foco` (que soma) num papel que
   precisa de `prompt` (que substitui). Seriam 41.692 caracteres de venda — com "CNPJ É
   OBRIGATÓRIO" em maiúsculas — contra 1.200 dizendo que ele é da casa. Já sabemos como o
   modelo resolve essa contradição, porque aconteceu em 11/09: gasta os tokens de saída nela e
   devolve **texto vazio**. Agora herda a base do funcionário (3.231 → 3.832 chars), de um lugar
   só.

2. **Hora errada no resumo.** Saía `03:22` para uma mensagem das `23:22` de Manaus. Resumo lido
   por gente com fuso de outro lugar é resumo **errado**, não detalhe de formato — irmão do
   `punch_timestamp` que já custou caro no operacional.

3. `asyncpg` exige `str` no `|| ' hours'`. Com `int`, a query inteira estourava.

---

## A ponte para as tools do MCP — escrita, INERTE, e o que a medição derrubou

Você pediu à noite que o José Luís tivesse as tools do MCP do Cowork. Escrevi a ponte (JSON-RPC
sobre `httpx`, sem dependência nova) e **não liguei em nenhuma tool**, porque a medição derrubou
duas premissas minhas:

1. **O conector interno não serve operacional.** Publica 146 tools (conferi que não é paginação —
   `nextCursor` é nulo) e nenhuma de posto/alocação/escala. Alargar o escopo dele resolveria o
   catálogo e **exporia escrita de escala ao time inteiro** — o oposto de operacional READ-ONLY.
   Leitura operacional do Orlailson tem de ser in-process, não por aqui.

2. **A parede de identidade recusou minha chamada, e está certa.** `ExigeIdentidade` respondeu
   *"toca dado pessoal e a chamada chegou SEM identidade"*. Meu atalho de usar só a conta de
   serviço não passa. Para passar, a ponte precisa mintar o JWT **da pessoa** — e o efeito
   colateral é melhor que o atalho: o RBAC do ERP passa a escopar a leitura por pessoa, em vez
   de eu manter uma allowlist à mão.

O que a ponte já acerta e vale guardar: ela entra pelo **`mcp-internal`** e **nunca** pelo
`conecta-pro-mcp`. Medido: o mesmo token dá **401** no público (que carrega a identidade sua) e
**200** no interno. Se algum dia essa ponte apontar para o público, um funcionário no WhatsApp
passa a agir como você.

E o fail-closed funcionou **contra mim**, que é o único jeito de saber que ele existe: sem
conseguir o contrato da tool, recusou as três que tentei em vez de chamar às cegas.

---

## O que falta, na ordem

1. **2º bake** — o primeiro leu o disco 23:28:48, antes do supervisor e do `resumo_grupos`.
   Essa é a armadilha das 17:39 que já me pegou; reconheci e estou tratando, não descobrindo.
2. **Ligar `BAILEYS_WHATSAPP_GROUPS_ENABLED=true`** no `chatwoot-fazerai`. É a captura de grupo
   inteira — a capacidade que a especificação chamava de "o principal, precisa que desenvolvam"
   é **uma variável de ambiente**. Só depois do bake: `docker cp` é volátil, e se o container
   reiniciasse sem a parede assada, os grupos cairiam no agente e ele começaria a responder.
3. **Ponte MCP**: mintar o JWT da pessoa (decisão sua — é impersonação, mesmo que só para
   leitura) e decidir de onde vem a leitura operacional.

## Decisões que são suas

- **Aprovar pedido de escala aplica a troca, ou só autoriza?** Implementei "só autoriza".
- **A ponte pode mintar JWT da pessoa para leitura?** Sem isso, ela não passa da parede.
- **A conta do Eliziel** fica ativa com `gerente_operacional` e colaborador `inativo`?
- **A carga do Sólides parada em 17/09** é decisão ou rotina caída?
- **Ligo a chave da captura de grupo?** É um `docker compose up -d` em
  `/opt/chatwoot-fazerai` depois de somar `BAILEYS_WHATSAPP_GROUPS_ENABLED=true` ao `.env`.
  Aditivo, reversível em um comando, e a parede que o protege está assada e provada. Não fiz
  sozinho por um motivo só: é outro stack e é a caixa de entrada de todo o WhatsApp da empresa.

## As 210 inconsistências de ponto

Apareceram sozinhas na primeira leitura da operação e não são desta frente — mas são o número
mais alto do painel e ninguém as pediu. Deixo apontado: `inconsistencias_periodo = 210`.
