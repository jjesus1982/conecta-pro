# PROMPT — Validação independente da camada MCP do Conecta PRO (rodada 3)

**Para:** Cowork (conector `conecta-pro-mcp`)
**Data:** 13/09/2026 · **Commits sob teste:** `b4437c5f6`, `3eabc59cd`, `30be528a3`
**Imagem:** `conecta-pro-mcp:latest` · 4 conectores recriados · 276 tools (186 read · 51 write_low · 39 propose)

---

## Por que você está sendo chamado de novo

Nas duas rodadas anteriores você achou, com **seis** tentativas suas, **quatro** problemas que
minha varredura à mão havia declarado limpos — e a frase que ficou foi a sua:

> "Seis tentativas minhas acharam quatro problemas — isso não é amostra azarada, é cobertura
> incompleta."

Você estava certo. Minha varredura media o conjunto que eu tinha acabado de mexer. Nesta
rodada troquei a varredura à mão por uma **paramétrica sobre o registry**, como você pediu, e
ela achou 30 defeitos que eu não tinha visto — inclusive um que a trava de build deixava
passar havia semanas.

**Portanto: não confie nesta lista.** Ela é a lista do que EU consigo ver. Escolha seus
próprios alvos, especialmente fora do que está escrito aqui.

---

## Fronteiras — não cruzar em nenhuma hipótese

1. **Dinheiro que SAI**: nunca happy-path. PIX, pagamento, transferência → valide por recusa
   e por leitura, jamais acionando. OTP dispara pagamento real.
2. **Governo** (eSocial / SPED / NFS-e): transmitir gera evento real. Só leitura.
3. **Operacional** (postos, alocações, escalas): curado à mão pelo Jordan, **READ-ONLY**.
   Divergência que você achar é linha de relatório, nunca correção.
4. **Financeiro**: só Jordan (`jjesus`) e Pyetra (`pjesus`) têm acesso legítimo.
5. Dado pessoal **sensível** (holerite, CPF, ASO, salário individual): acesse só o necessário
   para validar, e saiba que **fica registrado** — a trilha é justamente um dos itens a testar.

---

## Bloco A — as 4 afirmações falsificáveis desta rodada

Cada uma é verificável. Se alguma não se sustentar, isso é o achado.

### A1 · Nenhuma leitura devolve 5xx para identificador inválido

Afirmo: rodando as **60 tools de leitura com argumento obrigatório** com lixo
(`"LIXO-INVALIDO-ZZZ-999"`), nenhuma devolve `http >= 500`. Antes eram **25**.

O motivo importa: 500 não informa nada e manda o agente tentar de novo igual. Vinte delas
vinham da validação de **tipo** do FastMCP — `mes` recebendo texto caía em
`FALHA_INESPERADA/500`. Agora deve vir `PARAMETRO_INVALIDO/422` **nomeando o campo e o tipo
esperado**.

Teste por conta própria, escolhendo tools que eu não citei. Sugestão de forma:
passe texto onde o parâmetro é numérico, UUID inválido onde é id, e string vazia.

### A2 · Não existe mais sucesso falso nas leituras

Afirmo que fechei quatro, todos da família daquele `ver_ficha_cliente` que **você** achou
(200 + ficha vazia + nenhum `ok`):

| Tool | Devolvia | Por que é falso sucesso |
|---|---|---|
| `consultar_kit` | `completude: "0%"` | lê-se "o condomínio existe e está sem documento" |
| `status_coleta` | `estado: "PENDING"` | lê-se "em andamento, aguarde" — para coleta que nunca existiu |
| `dossie_juridico` | `{"erro": …}` | recusa **fora** do envelope: sem `ok`, `codigo`, `http` |
| `gerar_aditivo_pdf` | `gerado: true` + `download_url` | **gerava um PDF de 262 KB** intitulado "Aditivo - LIXO-ZZZ-999" |

⚠️ **Mas atenção ao critério, que é onde eu quase errei.** Existem **quatro formas legítimas**
de uma leitura dizer "não achei", e exigir um formato único me faria "consertar" 14 tools
corretas:

1. envelope de recusa (`ok: false` + `codigo` + `http` + `mensagem` + `dica` + `request_id`);
2. negativa no vocabulário próprio (`{"existe": false}`, `{"encontrado": false}`);
3. busca sem resultado (`items: []`, `total: 0`);
4. tool de LLM recusando em prosa ("não é uma consulta financeira — é entrada inválida").

O que **não** é legítimo: 5xx, recusa fora do envelope, e corpo com dado sem nenhuma negativa.

**Se você discordar dessa taxonomia, quero saber.** Ela é minha, não é lei.

### A3 · Cinco tools estavam etiquetadas `read` e ESCREVEM

Este é o achado que vale mais que os outros, e ele é uma falha da **trava**, não do código.

`gerar_aditivo_pdf`, `gerar_atestado_pdf`, `gerar_orcamento`, `gerar_ordem_servico_pdf` e
`gerar_recibo_pdf` estavam `read` no manifesto — enquanto o docstring de cada uma diz, com
estas palavras: *"⚠️ ESCREVE no Conecta PRO — não é consulta."*

A trava `test_read_nao_escreve` deixou passar porque mede o **texto do corpo** da tool, e o
`erp.post(...?salvar=true)` mora no helper `_gerar_doc`. **Terceira vez** que essa mesma trava
mede um jeito de escrever em vez do fato; as duas anteriores estão anotadas no comentário dela.

Agora as 5 são `write_low` e a trava propaga **transitivamente** pelos helpers.

**O que eu preciso que você ataque:** eu consertei a delegação de **um** nível de indireção
propagada até ponto fixo. Procure o próximo formato que escapa. Candidatos que eu não
verifiquei: escrita via `asyncio.gather` de helpers, escrita dentro de `_legivel`/`_pdf_b64`,
tool que chama **outra tool** em vez de helper, e escrita que sai por um cliente HTTP que não
seja `erp`.

### A4 · A trilha de LGPD deixou de creditar o Jordan por acesso do agente

O conector público carrega a identidade dele, então `agente_acesso_sensivel` gravava
`jjesus@conectamais.pro` como se ele tivesse aberto o holerite com as próprias mãos.

Agora: `jjesus@conectamais.pro (via MCP publico sem escopo declarado)`.

Valide chamando uma tool sensível **coberta pela concessão** (`asos_vencendo` ou
`funcionarios_sem_aso` — obrigação de SST, autorizadas até 31/12/2026) e conferindo a trilha
via `consultar_auditoria` ou `/audit`. Confira também que a **tentativa recusada** aparece: o
registro é da intenção, antes de executar.

⚠️ Ponto honesto: essa correção está no ar via `docker cp` + reload, commitada, mas só fica
permanente no próximo bake blue/green do backend. Se ao validar você encontrar `quem` sem o
`(via …)`, pode ser que o backend tenha sido reassado por outro terminal — reporte o fato, não
presuma qual dos dois.

---

## Bloco B — o que eu NÃO cobri, e onde eu mais apostaria que há defeito

Não gaste seu tempo confirmando o que já está verde. Estes são os lugares onde eu sei que a
cobertura é fina:

1. **`conecta_pro_capabilities` cobre 29 das 276 tools (10,5%).** Uma tool fora do
   `capabilities` é uma tool cujo contrato o agente descobre errando. Quais das 247 ausentes
   têm parâmetro ambíguo o bastante para que a ausência custe uma chamada errada?

2. **As 51 `write_low`.** Minha varredura paramétrica cobriu **só as 60 leituras** — escrita
   com identificador inválido eu não varri, e agora há 5 tools novas nessa classe. Elas
   fabricam documento para entidade inexistente, como o aditivo fazia? Valide **sem** deixar
   lixo: prefira `ensaiar(...)` ou `no_sandbox(...)`.

3. **`ensaiar` e `no_sandbox` sob as tools novas.** As 5 reclassificadas passaram a ser
   escrita; o ensaio intercepta `request`, mas `_gerar_doc` monta a URL de um jeito próprio.
   O ensaio realmente segura elas, ou passa e grava?

4. **Nenhum item operacional aparece em `pendencias_acionaveis`.** O aceite "operacional vira
   RELATÓRIO, nunca correção" segue **sem verificação real**, porque a fonte nunca produziu
   item. Consegue provocar um? Se conseguir, confirme que o `acao_sugerida` diz para levar ao
   Jordan e que não há tool de correção no caminho.

5. **Paginação e cursor.** Não documentei. Toda tool de listagem tem `page_size` fixo em algum
   lugar; se a janela não alcança o conjunto e a tool **decide** algo, é falso-verde. Já me
   custou uma escrita em produção.

6. **ISO-8601 e número monetário nas 276.** Varri parcialmente. `R$ 255.400.06` malformado
   apareceu numa agregação e a origem **nunca foi encontrada** no backend — só normalizei no
   agregador. Se você achar a origem, isso é um achado real.

---

## Bloco C — como reportar

Para cada achado, o que me serve:

- **a chamada exata** (tool + argumentos) e a **resposta crua**;
- se é **defeito** ou **divergência de critério** (o meu critério pode estar errado, e já
  estava duas vezes);
- se é **regressão** desta rodada ou lacuna que sempre existiu;
- e, quando for uma trava minha que passou verde: **o que ela estava observando** em vez do
  fato. É a categoria que mais me custou nesta semana e a que eu menos vejo sozinho.

Não suavize. Nas duas rodadas anteriores as suas frases mais duras foram as que consertaram
mais código.
