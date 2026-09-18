# PROMPT — Validação R7: a SPEC R6 implementada

**Para:** Cowork (conector `conecta-pro-mcp`)
**Data:** 18/09/2026
**Commits:** `1bd9d08c3` (R6) · `bc55303c1` (hash) · backend assado 4× no dia
**Antes de começar:** você derrubou o A1 da R5 com três linhas de leitura, e estava certo. O
CTR-2026-00025 **renderizava** e eu chamei de **emitido**. Essa correção governa esta rodada.

---

## Fronteiras

1. **Dinheiro que SAI**: nunca happy-path.
2. **Governo**: só leitura.
3. **Operacional**: READ-ONLY.
4. **Não abra assinatura de nada.** ⚠️ E agora há uma constraint: um segundo lote aberto é
   recusado. Testar isso criaria linha de assinatura real.
5. **Não reemita o 00022.** Ele está `active`.
6. Se usar `no_sandbox` para criar, **limpe depois**.

---

## BLOCO A — os onze itens da sua SPEC, como afirmações falsificáveis

### A1 · R6-1 — o documento agora é congelado

```
gerar_contrato_por_modelo("CTR-2026-00025")
→ status "emitido", congelado: true, conteudo_hash, clausulas_congeladas: 13
```
E no registro: `status: pending_signature` · `content` com 9539 caracteres · `clauses` com 13
títulos em jsonb · `pdf_file_path` preenchido · `conteudo_hash` · `emitido_em` · `emitido_por`.

**Ataque 1 — o alarme falso.** Emita duas vezes seguidas **sem mudar nada**. O hash tem de ser
IDÊNTICO e o `aviso_divergencia` tem de ficar ausente na segunda. ⚠️ Esta é a armadilha que me
pegou: minha primeira versão hasheava os **bytes do PDF**, e PDF carrega data de geração — o
aviso disparava em toda emissão. Alarme que soa sempre é alarme que ninguém lê, e eu tinha
entregado exatamente isso dentro da correção feita para provar integridade. Hash é do TEXTO.

**Ataque 2 — a divergência de verdade.** Altere um item (`descricao`, por exemplo), reemita, e
o envelope tem de trazer `aviso_divergencia` com `hash_anterior` e o novo. Restaure depois.

**Ataque 3 — minuta não congela.** `minuta=True` não pode gravar `content` nem mover `status`.
Se congelar, é defeito: minuta é rascunho para o jurídico do cliente.

**Ataque 4 — status que não deve retroceder.** O 00022 está `active`. Se algo o levar de volta
para `pending_signature`, é defeito — eu só avanço a partir de `draft`.

### A2 · R6-2 — `quantity` nunca mais é zero

`itens=[{"nome":"X","qtd":2,"total":3000}]` → `obter_contrato` mostra `quantity: 2`.
Sem o campo → `quantity: 1`. E o texto **nunca** imprime `qtd 0`.

⚠️ A guarda está também no RENDER, porque item gravado antes da correção tem `0` no banco —
corrigir só a escrita deixaria contratos existentes imprimindo zero. **Ataque:** ache um
contrato antigo com `quantity = 0` no banco e confirme que o texto dele imprime 1, não 0.

### A3 · R6-4 — `inscrever_lead_em_sequencia` atrás do muro

```
capabilities(tool="inscrever_lead_em_sequencia")
→ propose · atras_do_muro: true · sai_da_empresa preenchido · lgpd: identificado_operacional
```
Coerente com `inscrever_em_sequencia` nos quatro campos. **São duplicatas literais** — mesma
rota, mesmo payload, mesmo retorno. Mantive as duas por compatibilidade, com o docstring da
segunda dizendo que é duplicata. **Ataque:** se você achar terceira porta para
`/crm/sequences/{id}/enroll`, é defeito.

### A4 · R6-5 — opt-out casa o número inteiro

| entrada | esperado |
|---|---|
| `"   "` | 422 TELEFONE_INVALIDO |
| `"929999000199"` | 422 TELEFONE_INVALIDO |
| `"92 99999-000A"` | **422** TELEFONE_INVALIDO (era 404) |
| `"11999990000"` | 404 NUMERO_NAO_CADASTRADO |
| `"92999990000"` | aceita, `de_quem` = CONECTAMAIS ELETRONICA |

O `11999990000` é o seu ataque do DDD cruzado: mesmos 8 dígitos finais do cliente de 92, e
agora **não casa**.

⚠️ Armadilha que me pegou aqui: pus a checagem de letra só na rota do backend e ela **nunca
disparava**, porque a tool tira os não-dígitos ANTES de chamar — validação a jusante da
normalização não vê o que foi normalizado. A guarda foi para onde o dado cru entra.

**Ataque:** o caso ambíguo. Se houver dois cadastros com o mesmo número, tem de vir **409 com
a lista de candidatos**, nunca uma escolha silenciosa. Não consegui provocar com dado real —
se você conseguir, é o teste que falta.

### A5 · R6-6 — medido, não alterado

`crm.lembrete_reuniao` chama `notify_owner`: o lembrete pré-reunião vai para **o Jordan**, não
para o cliente. `sugerir_reuniao` está certa fora do muro, e o docstring agora diz isso.
**Ataque:** se você achar caminho em que esse lembrete saia para fora, a classificação muda.

### A6 · R6-8 — a constraint existe, e nada foi apagado

⚠️ **Divergi do seu pedido, com medição.** Você pediu "de-duplicar e então criar UNIQUE
(contrato, ordem)". Medi as 10 linhas com `reference_code` de contrato e **não havia o que
de-duplicar**: o invariante que importa não é "uma não-cancelada por ordem", é **"uma
AGUARDANDO por ordem"**. No 00022 a ordem 1 tem uma `SIGNED` (lote de 09/09) e uma `PENDING`
(lote de 11/09) — as duas legítimas. Uma constraint sobre "não-cancelada" obrigaria a cancelar
a assinada, que é destruir prova para agradar o schema, como você mesmo escreveu.

Índice **parcial**: `ux_sig_pendente_por_posicao`, sobre `(reference_code, signature_order)`
onde o status aguarda ação e `reference_code` não é vazio — 3.168 linhas de holerite e kit não
têm ordem por contrato e não podem ser varridas pela mesma régua.

**Ataque:** concorda com a troca de invariante? E: existe algum status que signifique "aguarda"
e que eu não listei (`PENDING`, `PENDENTE`, `SENT`, `ENVIADA`, `AWAITING`, `VIEWED`)? Um status
fora da lista é um segundo lote que passa.

### A7 · R6-9 — a trava contra o apagador existe e pega

`test_defaults_nao_apagam.py`, no build. Mede por **AST** a combinação perigosa: default `""`
num parâmetro guardado por `is not None`. Cada uma isolada é legítima; juntas apagam cadastro.
Provei reintroduzindo o defeito — reprova nomeando o parâmetro.

**Ataque:** ache uma tool de cadastro que apague dado por outro mecanismo que a régua não veja.

### A8 · R6-11 — §9.6 completo, 4 de 4

`portaria_remota` e `manutencao_cftv` e `eletronica_servico_unico`: "foro da Comarca de
Manaus/AM". `portaria_mao_de_obra` (CTR-2026-00019): "Foro de Manaus, Estado do Amazonas" —
⚠️ este é **literal no corpo do modelo**, não vem da variável. Não está quebrado, mas não
exercita a cadeia. Se você achar isso relevante, diga.

### A9 · R6-7 — já estava feito na R5

`atualizar_cliente` aceita `rua`, `numero`, `bairro`, `cep`, `uf`, `complemento` desde
`f259a6e52`. Você marcou como aberto; o que está aberto é **o dado**: ninguém preencheu o
endereço do Smart Tower, e eu não vou inventar um. **Confirme a assinatura da tool** — se ela
não aceitar os seis campos, aí sim eu errei o relatório.

---

## BLOCO B — R6-3 não foi feito, e colide com o seu próprio "Não fazer"

```
CONTRATANTE: {{contratante_nome}}, … neste ato representada por seu {{contratante_cargo}},
{{contratante_representante}}, inscrito no CPF sob o nº {{contratante_representante_cpf}};
```

`por seu` e `inscrito` estão **escritos no corpo do modelo**, não em variável. Corrigir a
concordância exige editar `corpo_template` — que o seu "Não fazer" proíbe por iniciativa
própria, porque muda a fôrma de todos os contratos pendurados, incluindo os dois do Kopenhagen.

**Parei ali.** Se você concorda que a grafia gramatical é mudança de fôrma diferente de mudança
de cláusula, diga — é o argumento que falta para o Jordan autorizar. E se houver caminho de
concordância que NÃO toque o corpo do modelo e eu não vi, é o achado mais útil desta rodada.

---

## BLOCO C — R6-10: varri, e o que achei precisa da decisão dele

Agrupei as tools por **EFEITO** (a rota que cada uma chama), como você sugeriu: 20 grupos com
2+ tools, **8 divergentes**. Depois de medir cada um, sobraram duas coisas:

**Uma suspeita que se resolveu:** `abrir_assinatura_contrato` é `propose` com `muro=False` e
está no mesmo grupo de `enviar_link_assinatura` (muro=True). Fui ler: ela **não envia nada**.
Quem manda e-mail é `convidar_para_assinar`, chamada só por `enviar_link_assinatura`. A
notificação que o motor universal dispara vai para o **sino do Portal de funcionários
signatários** — e o cliente não é funcionário. `muro=False` se sustenta; registro para não
virar suspeita de novo.

**Três que EXECUTAM no conector público** e eu **não** mexi, porque mudam o que o Jordan pode
fazer de dentro do ERP e duas tocam dinheiro e folha:

| tool | classe | muro | o que faz |
|---|---|---|---|
| `definir_parametros_precificacao` | propose | **false** | muda o parâmetro de TODO preço cotado |
| `revisar_justificativa_ponto` | propose | **false** | decide falta de gente; entra na folha |
| `atualizar_contrato` | propose | **false** | altera valor e vigência de contrato vigente |

São da mesma família das onze que fechei em 12/09: `propose` só gateia em modo agente, e o
conector público não está nesse modo. **Ataque:** confirme por chamada que as três executam (use
`ensaiar`, não chame direto) e diga se concorda que deviam entrar no muro. É decisão do Jordan.

---

## BLOCO D — risco residual

1. **CPF/RG em `crm_contacts.notes`** segue como texto livre lido por regex. Você ligou isso à
   cláusula 17.9 da minuta (eliminar dados em 30 dias) e o argumento é bom: não se elimina com
   confiança o que está em campo de observação. Não criei colunas para não abrir frente nova.
2. **Endereço do Smart Tower** tem só a cidade. O caminho existe; o dado não.
3. **O modelo que o ERP emite não é a minuta aprovada em 18/09** (seu §1.6). Não toquei.
   Continua sendo decisão dele, e a divergência é de conteúdo comercial, não de engenharia.
4. **`portaria_mao_de_obra` tem o foro literal no corpo** — não exercita a cadeia nova.
5. **O staging caiu 3× ontem**, uma delas voltando sem rede e reportando `healthy`. O script de
   bake passou a devolvê-lo ao ar no fim. Se o `no_sandbox` falhar por rede, é isto.

---

## Como reportar

Retorno cru primeiro. Separe **medido** de **inferido**, e marque a inferência como inferência —
foi o que mais me custou tempo nas rodadas anteriores. Para os blocos B e C quero julgamento,
não teste.

E inclua de propósito uma armadilha que tenha te pegado. As duas desta rodada foram minhas: o
hash do PDF que dispara alarme sempre, e a validação a jusante da normalização que nunca vê o
dado. As duas me ensinaram mais que qualquer teste verde.
