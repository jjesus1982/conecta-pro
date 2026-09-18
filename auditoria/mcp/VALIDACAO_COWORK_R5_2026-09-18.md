# PROMPT — Validação: emissão de contratos + os 4 pendentes (rodada 5)

**Para:** Cowork (conector `conecta-pro-mcp`)
**Data:** 18/09/2026
**Commits sob teste:** `e7c717721` (emissão), `f259a6e52` (MCP), `29e976b4a`, `2ddb59bb2`, `93fca07db`
**Estado:** backend **assado** (blue/green, 2×) · MCP reconstruído · 4 conectores no ar

---

## O que mudou desde a sua última rodada

Duas frentes: os **4 pendentes** que dependiam de autorização do Jordan, e a **SPEC de emissão
de contratos**, que nasceu da sua sessão do CTR-2026-00025.

⚠️ **Três itens da SPEC foram implementados DIFERENTE do que o documento pedia**, e o Bloco C
explica cada um. Não são atalhos: em dois casos o pedido literal criaria um defeito pior
(segunda fonte de verdade; apagar histórico de assinatura). Quero que você ataque justamente
essas três decisões — se eu errei o julgamento, é ali.

⚠️ E uma coisa que aprendi com as suas quatro rodadas: **separe o que você MEDIU do que você
INFERIU como causa.** Três dos seus achados tinham diagnóstico errado e conclusão certa, e eu
gastei tempo desmentindo a causa antes de chegar ao defeito. Retorno cru primeiro, hipótese
depois e rotulada como hipótese.

---

## Fronteiras

1. **Dinheiro que SAI**: nunca happy-path.
2. **Governo** (eSocial/SPED/NFS-e): transmitir gera evento real. Só leitura.
3. **Operacional** (postos, alocações, escalas): READ-ONLY, divergência vira relatório.
4. **`ativar_contrato` e `reativar_lead` entraram no muro nesta rodada** — valide que recusam,
   nunca que executam.
5. Escrita: `ensaiar()` (não grava) ou `no_sandbox()` (grava no staging). ⚠️ Se criar no
   sandbox, **limpe**: numa varredura minha eu criei uma proposta chamada
   `LIXO-INVALIDO-ZZZ-999` e a passada seguinte casou com ela, reportando "sucesso falso" numa
   tool correta. O teste mediu o próprio resíduo.
6. **O CTR-2026-00025 está emitido e o 00022 está `active`.** Não reemita o 00022 e não abra
   assinatura de nada — abrir assinatura manda e-mail ao cliente.

---

## BLOCO A — emissão de contrato: seis afirmações falsificáveis

O contrato que ficou parado na sua sessão está emitido. Ataque o que segue.

### A1 · Emissão limpa funciona, e não só para portaria remota

```
gerar_contrato_por_modelo("CTR-2026-00025")
→ ok:true, status "emitido", 13 cláusulas, link
```

Afirmo que a causa era esta: `foro` e `cidade_assinatura` eram lidos **só** em `_ctx_one_time`,
que roda apenas quando `contract_type == 'one_time'`. Em contrato **recorrente** nunca entravam
no contexto, o `StrictUndefined` do Jinja os marcava vazios e a emissão recusava. Ou seja:
**nenhum contrato recorrente conseguia ser emitido por este caminho**, não só o 00025.

⚠️ E **não precisou de coluna nova** — eles já viviam em `contracts.sla_config` (JSONB). Se você
achar contrato onde a cadeia de origem (contrato → cidade do cliente → "Manaus/AM") não
resolve, ou onde o foro sai vazio, isso derruba a correção.

**Ataque sugerido:** `CTR-2026-00020` (manutencao_cftv), `CTR-2026-00024` (portaria_mao_de_obra)
e `CTR-2026-00023` (portaria_remota) estão em `draft`. Rode com `minuta=True` e confirme que a
recusa que vier NÃO fala de foro nem de cidade_assinatura.

### A2 · O texto contém o que tem de conter

`baixar_contrato_pdf(contrato_id="CTR-2026-00025", formato="texto")` — ⚠️ o parâmetro é
`contrato_id`, não `contrato`.

Afirmo 11 asserts: `Meridiana Vasconselos da Consta` · `718.131.102-63` · `Síndica` · `Manaus` ·
`foro da Comarca de Manaus/AM` · `R$ 5.000,00` · `24 (vinte e quatro) meses` ·
`vencimento no dia 10` · `640 tags` · `totem` · `leitor facial`. Sem `{{ }}`, sem `[A DEFINIR]`.

⚠️ Cuidado com uma armadilha que me pegou: o render **capitaliza nome próprio**. Procurar
`"TESTE OVERRIDE"` em caixa alta dá falso negativo — sai `Teste Override`.

### A3 · Erro de validação virou 422 com código, e nunca mais 403

Afirmo que estes três devolvem 422, nenhum 403, nenhum 500:

| chamada | código esperado |
|---|---|
| `itens=[{"nome":"X","subtotal":100}]` | `CAMPO_DESCONHECIDO` |
| `nome` com 300 caracteres | `CAMPO_LONGO_DEMAIS` (limite real: **200**, é `varchar(200)`) |
| itens somando 4900 num contrato de 5000 | `COMPOSICAO_NAO_FECHA`, com `diferenca` |

A causa era o controller mapeando **qualquer** recusa para 403 `SEM_PERMISSAO`. Três falhas da
sua sessão saíram assim e nenhuma era permissão.

**Ataque:** procure outra falha de validação da emissão que ainda saia 403 ou 500. E procure o
oposto — recusa de PERMISSÃO de verdade que tenha virado 422 por engano. Essa seria minha.

### A4 · A emissão é atômica

Afirmo: emissão que falha não muda nada. Havia dois commits e o primeiro acontecia **antes** do
render, então uma recusa deixava `grace_period_days` e os `contract_items`
apagados-e-reinseridos gravados.

**Ataque:** `obter_contrato("CTR-2026-00025")`, guarde `grace_period_days` e os ids dos itens,
force uma recusa (`subtotal` em vez de `total`), e leia de novo. Nada pode ter mudado —
inclusive os `created_at` dos itens.

### A5 · `obter_cliente` deixou de dar 405

A rota `GET /api/v1/clients/{id}` **não existia** — só `PUT` nesse path, e o Starlette responde
405. Criada. `obter_cliente("66.581.655/0001-09")` → `ok:true`, com `address_city: "Manaus"`.

### A6 · O manifesto de assinatura parou de se contradizer

`sig_signature_requests` do CTR-2026-00022 tinha **4 linhas** (dois lotes de abertura), e a
query do manifesto lia todos os lotes **ignorando `status`** — daí duas `#1 CONTRATADA` (uma
Assinado, uma Pendente) e duas `#2`. Agora lê o lote atual e descarta cancelado/expirado:
4 → 2 linhas coerentes, nos 2 contratos que estavam sujos, **sem tocar em dado**.

⚠️ Valide por LEITURA (`status_assinatura_contrato`, ou o `texto_extraido` do PDF do 00022).
**Não abra assinatura** para testar.

---

## BLOCO B — os 4 pendentes

### B1 · `reativar_lead` e `ativar_contrato` entraram no muro

```
reativar_lead(ref=..., confirmar=true)   → REQUER_APROVACAO_HUMANA/403
                                            sai_da_empresa: "um toque de WhatsApp para o lead frio"
ativar_contrato(contrato_id=..., confirmar=true) → REQUER_APROVACAO_HUMANA/403
                                            irreversivel: "ATIVA o contrato e lança o valor no MRR"
```

`reativar_lead` estava `write_low` fora do muro enquanto `followup_whatsapp`, mesmo efeito, era
`propose` + `EFEITO_EXTERNO`. **Ataque:** procure a terceira — outra tool que produza efeito
externo ou lance dinheiro e ainda esteja fora do muro. Foi assim que estas duas apareceram.

### B2 · Recusa dura no opt-out

```
registrar_optout_whatsapp(numero="0000000000")  → TELEFONE_INVALIDO/422 (sequência)
registrar_optout_whatsapp(numero="9033334444")  → DDD_INVALIDO/422 (DDD 90 não existe)
registrar_optout_whatsapp(numero="92123456789") → TELEFONE_INVALIDO/422 (11 dígitos sem o 9)
registrar_optout_whatsapp(numero="92991234567") → NUMERO_NAO_CADASTRADO/404
registrar_optout_whatsapp(numero="<real de cliente>") → aceita, com `de_quem`
```

Na rodada anterior eu recusei fazer a recusa dura porque minha visão do cadastro alcançava
**7 de 296** leads (`LeadRepository.list` filtra `is_active`), e ela barraria 291 pessoas
reais. A rota `GET /crm/telefone/de-quem` existe para tirar essa cegueira — lê cliente e lead
**sem** filtro de ativo.

⚠️ Há um **fail-open declarado**: se a consulta ao cadastro falhar, o opt-out é registrado com
aviso, em vez de recusado. Recusar por defeito meu deixaria alguém sem a proteção que pediu.
**Ataque:** se você conseguir fazer a consulta falhar e o opt-out passar sem aviso, é defeito.

### B3 · O backend está assado

O que estava no ar por `docker cp` desde 12/09 agora vem da imagem do commit. **Ataque:** se
qualquer comportamento do Bloco A ou B voltar ao estado antigo, reporte o fato — pode ser
reinício, e eu quero saber.

---

## BLOCO C — as três decisões que eu tomei contra o texto do documento

Aqui eu quero **julgamento**, não teste. Diga se concorda.

### C1 · O representante não foi para `clients`

A SPEC pedia `endereco`, `representante`, `representante_cargo`, `representante_cpf`,
`representante_rg` em `atualizar_cliente`. Medi: **o representante mora em `crm_contacts`**
(`name`, `role`, e CPF/RG dentro de `notes`), e é de lá que o renderizador de contrato lê.
Colunas de representante em `clients` criariam uma segunda fonte de verdade — o cadastro
mostrando um nome e o contrato imprimindo outro.

Implementei a intenção: tool nova **`definir_representante_cliente`** (nome, cargo, CPF, RG, no
formato que o render sabe ler) e `representante_cargo` na emissão. O **endereço** sim foi para
`atualizar_cliente` — o schema do backend já aceitava tudo e a tool só expunha `cidade`.

### C2 · A constraint de unicidade do §8 não foi criada

O pedido era `UNIQUE (contrato_id, ordem_signatario)`. Ela **apagaria histórico**: no
CTR-2026-00022 a ordem 1 do lote antigo está `SIGNED` — assinatura real do Jordan, sobre outro
hash de documento. Cancelar ou remover essa linha é reescrever o que aconteceu.

Fiz duas coisas: o manifesto lê o lote atual e respeita `status`; e a guarda contra abrir um
segundo lote foi para **dentro de `abrir_assinatura`** — das três portas que a chamam, só uma
tinha guarda, e guarda replicada em N chamadores é guarda que o próximo esquece.

### C3 · §1 não virou coluna nova

`foro`/`cidade_assinatura` já eram armazenáveis em `contracts.sla_config`. Criar colunas seria
migração sem necessidade. O defeito era de LEITURA (só no ramo one_time) e de ESCRITA (dentro
de `if unico:`).

---

## BLOCO D — onde eu sei que ainda há risco

1. **As 39 `propose` nunca foram varridas** pela minha régua, que cobre `read`, `write_low` e o
   padrão preview/confirmar. Duas delas estavam fora do muro até hoje.
2. **`descricao` do item** agora imprime nos dois caminhos (PDF e texto). Consertei o do PDF
   primeiro e o texto seguiu sem ela — se houver um terceiro caminho de montagem que eu não
   achei, é onde vai faltar.
3. **`crm_contacts.notes` guarda CPF e RG como texto livre**, lidos por regex no render. Escrevo
   no formato documentado (`CPF 000.000.000-00 · RG 1234567 SSP/AM`), mas formato livre ali
   some. Não criei colunas próprias para não abrir frente nova sem autorização.
4. **Endereço do Smart Tower tem só a cidade** — o texto sai "com sede na Manaus". O render
   avisa, não recusa. Agora há caminho para preencher, ninguém preencheu.
5. **O staging morreu 3× hoje** (`ExitCode=137`, SIGKILL, `OOMKilled=false`) e numa delas voltou
   **sem rede nenhuma** reportando `healthy`. Se o `no_sandbox` der
   "Name or service not known" ou "All connection attempts failed", é isto — reporte, não
   conclua que a tool quebrou.

---

## Como reportar

Por achado: **chamada exata, retorno cru**, e a separação entre medido e inferido. Diga se é
regressão desta rodada ou lacuna antiga. Para os itens do Bloco C, quero a sua opinião sobre o
julgamento, não um teste.
