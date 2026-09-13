# PROMPT — Validação de fechamento da camada MCP (rodada 4)

**Para:** Cowork (conector `conecta-pro-mcp`)
**Data:** 13/09/2026 · **Commits sob teste:** `bfb3972fb`, `43fca41b8`
**Imagem:** 11 arquivos rastreados · 4 conectores recriados · 276 tools

---

## Por que esta rodada é diferente

As três anteriores foram exploratórias e você achou, em cada uma, coisas que eu tinha
declarado limpas. Esta é a rodada de **fechamento**: o Jordan escreveu um prompt com cinco
blocos, eu executei, e o que você tem de fazer é **conferir se fechou** — não abrir uma
quinta safra de achados.

Isso muda o que é útil aqui. Não gaste chamadas confirmando o que já está verde. Gaste-as
**tentando derrubar** as cinco afirmações do Bloco A, e depois no Bloco B, que é onde eu sei
que a cobertura é fina.

⚠️ E uma coisa que aprendi nesta semana às suas custas: **três dos seus achados tinham o
diagnóstico errado e a conclusão certa** (o "número impossível" das certidões era população
diferente; o `groundedness.ok:false` não entregava número fabricado; `proposta_da_oportunidade`
estava sim no mapa curado). Isso não diminuiu nenhum dos três — eu consertei os três. Então:
**reporte o sintoma com o retorno cru, e separe o que você MEDIU do que você INFERIU.** Quando
você mistura os dois eu perco tempo desmentindo a causa e o defeito fica para depois.

---

## Fronteiras — não cruzar

1. **Dinheiro que SAI**: nunca happy-path. Valide por recusa e leitura, jamais acionando.
2. **Governo** (eSocial / SPED / NFS-e): transmitir gera evento real. Só leitura.
3. **Operacional** (postos, alocações, escalas): READ-ONLY. Divergência vira relatório.
4. **`ativar_contrato` e `reativar_lead`**: ⚠️ leia o Bloco C antes de tocar. Uma lança MRR,
   a outra envia WhatsApp. Estão fora do muro — e é justamente o que precisa de decisão
   humana, não de teste.
5. **Escrita**: use `ensaiar()` (não grava) ou `no_sandbox()` (grava no staging). ⚠️ Se usar
   `no_sandbox` com criação, **limpe depois** — na minha varredura anterior eu criei uma
   proposta chamada `LIXO-INVALIDO-ZZZ-999` no staging e a passada seguinte casou com ela e
   reportou "sucesso falso" numa tool correta. O teste mediu o próprio resíduo.

---

## BLOCO A — cinco afirmações falsificáveis

### A1 · `lgpd_nivel` deixou de mentir para as tools fora do mapa curado

Afirmo: das 276, agora **18 são `sensivel`** (eram 186). Das 171 fora do mapa curado:
**135 `nao_se_aplica` · 33 `identificado_operacional` · 3 `sensivel`**.

As 3 inferidas como sensíveis são `pendencias_acionaveis` (devolve nomes de quem está sem
ASO), `analisar_processo_juridico` (tem `employee_id`) e `consultar_auditoria` (devolve a
própria trilha de acesso). Afirmo que as três são sensíveis **de verdade**.

O critério deixou de ser lista-à-mão-com-fail-closed e passou a inferir da **assinatura e da
descrição** da própria tool.

**Como atacar:** escolha você mesmo 10 tools fora do mapa e confira
`conecta_pro_capabilities(tool=...)`. Procure os dois erros opostos:
- tool que toca CPF/holerite/ASO/saúde e NÃO veio `sensivel` (o erro que protege menos);
- tool de dado de empresa que ainda vem `sensivel` (o erro que eu estava consertando).

⚠️ Há uma assimetria deliberada que vale testar: o **nome** da ferramenta entra no sinal
operacional e nunca no sensível. Se achar uma tool sensível que só se denuncia pelo nome,
isso é um buraco real — quero saber.

### A2 · O padrão preview→confirmar valida existência antes de oferecer confirmação

São **15** tools nesse padrão, não 4. **Dez estão atrás do muro** e recusam com
`REQUER_APROVACAO_HUMANA/403` antes de qualquer validação — o caminho de preview delas é
inalcançável e eu não toquei.

Nas 4 alcançáveis (`excluir_proposta`, `arquivar_contrato`, `arquivar_deal`,
`excluir_documento_crm`) afirmo:
- preview com id vazio → `IDENTIFICADOR_VAZIO/422`, **nunca** oferece "confirme para excluir";
- confirmação com id inválido → 404 ou 422, **nunca 500** (eram 4 de 4 com 500).

⚠️ **Divergência que declaro**: o Jordan pediu 404; `arquivar_deal` e `excluir_documento_crm`
devolvem **422** para identificador malformado e 404 para UUID bem-formado inexistente. A
distinção é deliberada — "isso nem tem forma de id" ≠ "procurei e não achei". **Se você achar
que isso atrapalha o agente, diga**: é uma linha para uniformizar.

### A3 · `ensaiar` valida tipo igual à execução real

Afirmo que `ensaiar` deixou de aprovar o que a execução recusa. Antes ele chamava a função
Python crua e o pydantic nunca era exercido.

```
ensaiar("definir_meta_mensal", {valor: "abc"})
→ ok:false, PARAMETRO_INVALIDO/422, "valor: esperava number.", escritas_que_teria_feito: []
```

Varri as **22 tools com parâmetro numérico obrigatório**: 0 aprovaram lixo, 0 devolveram
estrutura do pydantic serializada na `mensagem`.

**Como atacar:** procure a divergência inversa — tool onde o `ensaiar` agora recusa e a
execução real **aceitaria**. Ensaio mais rígido que a porta da frente quebra a ferramenta sem
proteger nada, e é um erro que eu já cometi antes neste mesmo arquivo.

### A4 · `post_bytes` deixou de escapar do ensaio

Este achado saiu do item que o Jordan classificou como risco teórico, e **não era teórico**.
Não era outro cliente HTTP: era um método da mesma classe do ERP que abre o próprio
`httpx.AsyncClient` e pula a interceptação, que mora em `request`.

Medido antes: `ensaiar("gerar_apresentacao", formato="pptx")` devolvia
`escritas: 0, gravou: false` **e fazia o POST**.

Agora: `escritas: 1`, rota `/crm/apresentacoes/gerar?formato=pptx`, 0 bytes devolvidos.

**Como atacar:** `get_bytes` também não passa por `request` — mas é GET, não escreve, então
deixei. Se você achar um caminho em que um GET provoque escrita no ERP, isso derruba a
decisão. Procure também qualquer outra tool cujo `ensaiar` devolva `escritas: []` e que, pela
descrição, claramente gravaria.

### A5 · O muro continua intacto

Afirmo que as 10 tools atrás do muro recusam com `REQUER_APROVACAO_HUMANA/403` **antes** de
qualquer validação de argumento — testei chamando as dez sem argumento nenhum.

Confirme por amostra sua. É o item que o Jordan mandou não mexer, e a razão de você poder
chamar essas tools com lixo sem risco.

---

## BLOCO B — onde eu sei que a cobertura é fina

Aqui vale mais o seu tempo que no Bloco A.

1. **As 39 `propose` nunca foram varridas.** Minha régua cobre `read` e `write_low`. As
   `propose` atrás do muro recusam antes de tudo, mas **nem todas estão atrás do muro** —
   `ativar_contrato` e `atualizar_modelo_contrato` são `propose` com `muro=False`. Quantas
   mais? O que elas fazem com identificador inválido?

2. **As 20 leituras sem identificador** (só texto livre) ficaram fora das varreduras. O `ok`
   vem do carimbo, mas o comportamento delas com entrada absurda não foi medido.

3. **`escreve` no `capabilities` deriva da classe do manifesto.** Se a classe mentir, o
   contrato mente com ela — foi exatamente o que aconteceu com as 5 `gerar_*` que estavam
   `read` e escreviam. A trava hoje segue delegação por helper, transitivamente. **Procure a
   próxima forma de escrever que ela não vê.**

4. **O `ensaiar` de tools que chamam OUTRAS tools.** `contexto_cliente` e `briefing_executivo`
   vieram com `escritas: []` — é evidência, não prova.

5. **Operacional em `pendencias_acionaveis`**: agora aparece (5 divergências reais, entre
   elas Green Hills com 3 de 4 vagas num contrato de R$22.100/mês). Confirme que a
   `acao_sugerida` manda levar ao Jordan e que **nenhuma tool de correção** aparece no
   caminho. Se aparecer, é o aceite quebrado.

6. **Certidões**: `status_certidoes` devolve 10, duas de cada tipo, e a rota do GEDEON **não
   diz a empresa**. Eu declaro `empresa: null` com aviso em vez de inventar. Confira que o
   aviso está lá e que o `pendencias_acionaveis` não colapsa as duas num item só.

---

## BLOCO C — duas decisões que são do Jordan, não suas nem minhas

Não teste acionando. Confirme por leitura e me diga se concorda com o diagnóstico.

1. **`reativar_lead(ref, confirmar=true)` envia WhatsApp** — sai da empresa — e está
   classificada `write_low`, **fora do muro**. `followup_whatsapp`, que faz a mesma coisa, é
   `propose` + `EFEITO_EXTERNO`. Parece desvio do muro de efeito externo. Concorda?

2. **`ativar_contrato(confirmar=true)` lança MRR** e é `propose` com `muro=False`. Tem os dois
   defeitos do Bloco A2 (preview não valida, confirmação dá 500) e eu **deliberadamente não
   corrigi**, porque a regra do Jordan manda parar em qualquer coisa que mexa em dinheiro. A
   quarta passada da minha régua reporta os dois toda vez que roda.

---

## BLOCO D — infra, para você saber o que está pisando

- O **backend de staging morreu** hoje (`ExitCode=137`, SIGKILL às 12:14) e o `no_sandbox`
  ficava com "Name or service not known". Subi de novo. Se você vir esse erro, é isto —
  reporte, não conclua que a tool está quebrada.
- O **schema do staging estava atrás** da produção (faltavam 3 colunas em `proposals`),
  produzindo 500 que parecia defeito de tool. Alinhado.
- ⚠️ As correções de **backend** (trilha LGPD com `(via …)`, briefing escopado às nossas
  empresas, cobertura por quadro exigido, auditoria separando consultas) estão no ar por
  `docker cp` e **só ficam permanentes no próximo bake blue/green**. Se um dos comportamentos
  do Bloco A ou B voltar ao estado antigo, pode ser reinício — reporte o fato, não presuma.

---

## Como reportar

Para cada achado: **a chamada exata, o retorno cru**, e a separação entre o que você
**mediu** e o que você **infere** que seja a causa. Diga também se é regressão desta rodada
ou lacuna que sempre existiu.

E se um bloco fechou, diga que fechou em uma linha. Rodada de fechamento com relatório longo
sobre o que está verde é tempo que não volta.
