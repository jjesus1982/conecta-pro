# DGX Z6 — Bartolo: o apoio que tira dúvida dentro do fluxo fiscal

**Onda 8** (NF-e de material para os dois CNPJs) · branch `dgx/z6-bartolo-fiscal` · 24/09/2026
· porta 8286, container `teste-dgx-z6` (parado ao fim) · módulo `ai` / `fiscal`.

> O pedido do dono: *«e o Bartolo como chat dando o apoio nisso, tirando dúvidas, etc.»*

**A decisão que orienta a frente:** não nasce chat novo. **Bartolo é o nome que o dono dá ao
assistente que a casa já tem** — o `POST /api/v1/consultores/chat/consultar` do
`consultor_escopado_controller`, com a lente `fiscal` (linha ~125). O termo, aliás, já vivia no
repositório: o `tool_registry.py` fala do «Bartolo interno» × «Bartolo que atende no WhatsApp», e
o próprio controller cita «a condição 2 do aceite do Bartolo». O que faltava não era um chat —
era **alcance** e uma **regra de honestidade escrita**.

---

## §1 — O que o consultor respondia HOJE sobre nota fiscal (a linha de base)

Dez perguntas reais, feitas pela **rota real** (`POST /api/v1/consultores/chat/consultar`,
`persona: "fiscal"`, token do Jordan), contra o sandbox, **antes de uma linha de código desta
frente existir**. As respostas literais estão lado a lado no §3.

O que a linha de base mostrou — três «não existe» ditos com confiança sobre dado que existe:

| # | Pergunta | O que o Bartolo respondeu | O fato |
|---|----------|---------------------------|--------|
| 2 | «Por que a NF-e número 2 foi rejeitada?» | *«não há registro de rejeição para a nota nº 2 — o módulo fiscal não guarda motivo de rejeição de NF-e»*, e passou a falar de **NFS-e** nº 2 (serviço) | `nfes.motivo_rejeicao` da nota 2 diz, literal: **«Rejeicao: Informado NCM inexistente [nItem: 1]»** |
| 5 | «Quantas NF-e de saída existem?» | *«Não há NF-e de saída na base — o que existe no Fiscal é NFS-e»* e devolveu 114 notas de **serviço** | Havia **2** NF-e modelo 55 em `nfes`, de 11/04/2026, **ambas rejeitadas** |
| 3 | «Posso vender para o Ideal Flores com ICMS desonerado?» | achou o cliente e o contrato, mas nunca olhou se havia NF-e de mercadoria para ele | `nfe_saida` responde isso em uma consulta |
| 6 | «O produto VTV-121 está com NCM válido?» | achou no **catálogo do CRM** e validou o NCM — mas tratou catálogo de compra como se fosse cadastro fiscal | `products` ≠ `fin_produtos`; o primeiro não tem CST/CSOSN por CNPJ nem CFOP |
| 4 e 7 | «Qual CFOP para venda dentro do AM?» / «Qual a alíquota de ICMS?» | **tabela completa de CFOP (5.101/5.102/5.105/5.106/5.109/5.110) tirada da memória do modelo** | Nenhuma consulta foi chamada. Isso é exatamente o CFOP inventado que o dono não pode receber |

Nenhum desses é defeito do modelo. **Nenhuma tool do escopo fiscal lia `nfes`, `nfe_itens` nem o
cadastro fiscal do produto** — o Bartolo respondia de olhos fechados para esse pedaço.

**Medido no sandbox em 24/09/2026 (cópia de produção):**

| Fato | Número |
|------|--------|
| NF-e de saída em `nfes` | 2, ambas `rejeitada`, nenhuma autorizada |
| NCM dos itens dessas notas | `98010000` e `85258900` — **nenhum dos dois** existe nos 10.515 códigos de `ncms` |
| `products` sem NCM | 674 de 867 |
| Tools do escopo fiscal que liam NF-e de mercadoria | **0** de 17 |

---

## §2 — O que o DGX tem

O DGX não tem «um Bartolo». O que ele tem, e que orienta esta frente, é o princípio de que
**a regra é dado com fonte** — o evento com 40 atributos, a CCT como tabela, os 127 parâmetros
por CNPJ. Traduzido para um assistente fiscal: toda alíquota, NCM e CFOP tem de vir de uma
consulta com procedência, nunca da memória de quem responde. É por isso que esta frente não
acrescentou «conhecimento» ao prompt: acrescentou **consultas** e uma **proibição**.

---

## §3 — O que foi feito

### Arquivos

| Arquivo | O que é |
|---------|---------|
| `backend/modules/ai/conversation/services/orquestrador/tools_read_fiscal_nfe.py` | **novo** — 5 consultas de LEITURA registradas em `consultar_fiscal` pelo mesmo `registrar_read` das outras 17 |
| `backend/modules/operacional/controllers/redesign_builders/dgx_z6_bartolo.py` | **novo** — a tela «Bartolo — tire sua dúvida» + a ação `POST /api/v1/redesign/action/bartolo-perguntar` |
| `backend/modules/ai/conversation/controllers/consultor_escopado_controller.py` | +1 linha de import (registra as consultas) e a **regra de honestidade** dentro da lente `fiscal` |
| `backend/modules/operacional/controllers/redesign_builders/fiscal.py` | +1 item de `EXTRA_MENU` (grupo «Notas fiscais») e +2 linhas chamando `telas()` |
| `backend/scripts/orq/test_oraculo_z6_bartolo.py` | **novo** — o oráculo (26 afirmações) |

**DDL: nenhuma.** Esta frente não cria tabela nem coluna — não há `_ensure` a rodar em produção
no primeiro acesso. Lê `nfes`, `nfe_itens`, `ncms`, `products`, `fin_produtos` (quando a Z1 a
tiver criado), `proposals` e `proposal_items`.

### As 5 consultas novas (todas só leitura, dentro de `consultar_fiscal`)

| Consulta | O que faz | Fonte |
|----------|-----------|-------|
| `nfe_saida` | as NF-e de **mercadoria** e o status de cada uma; filtra por competência, número, série, status, chave, empresa | `nfes` |
| `nfe_rejeicao` | o **`xMotivo` literal** do retorno da SEFAZ + qual **campo** corrigir + (quando a rejeição é de NCM) **quais itens** têm NCM fora da tabela oficial, medido por SQL | `nfes.motivo_rejeicao` × `nfe_itens` × `ncms` |
| `produto_fiscal` | o cadastro do item nas **duas** fontes, rotuladas, e o que falta nele para a nota sair | `fin_produtos` (Z1) + `products` × `ncms` |
| `tributacao_nfe` | CFOP, CST/CSOSN e alíquotas **com a norma de cada número** — repassadas **verbatim** do serviço da Z4 | `modules/fiscal/services/tributacao_nfe.py` |
| `orcamento_origem` | o orçamento que origina a nota, com seus itens | `proposals` + `proposal_items` |

**Nenhuma emite, assina, transmite, cancela ou inutiliza documento fiscal.** Nenhuma escreve no
banco. A busca de NCM **não foi recriada**: `buscar_ncm` (10.515 códigos) já era op do
`consultar_fiscal` desde antes desta frente, e as descrições novas apontam para ela.

### A regra de honestidade (§4 do brief), escrita na lente `fiscal`

Duas frases entraram no prompt da lente, e um campo entrou nas respostas das tools:

- **«CONSULTE ANTES DE DIZER QUE NÃO EXISTE»** — o erro do §1 nomeado.
- **«PROIBIDO NESTA LENTE: inventar NCM, alíquota ou CFOP»** — «você pode explicar o que cada um
  significa e como se escolhe; você não pode CRAVAR o valor sem a consulta».
- Quando a consulta devolve `nao_sei`, a resposta traz `o_que_falta` e
  `onde_decidir: "/redesign/bi?t=decisoes-do-dono"` (tela que existe — conferida).
- Onde a Z4 marcou **«sem fonte — decisão do contador»**, a frase chega inteira: o cálculo passa
  sem ser reescrito, e a constante `SEM_FONTE` é idêntica nas duas frentes (o oráculo compara).

### A tela: `/redesign/fiscal?t=bartolo-fiscal`

Aba **«Bartolo — tire sua dúvida»**, grupo **«Notas fiscais»** (onde moram as telas da onda 8).
Um `select` com as **10 perguntas do §1 prontas para clicar** + um campo livre. A ação chama a
**mesma rota do chat** in-process (`consultar(ConsultarIn(pergunta, persona="fiscal"))`) — um
cérebro só, as mesmas tools, o mesmo RBAC. Provado por HTTP no container efêmero:

```
GET  /api/v1/redesign/data/fiscal   → 'bartolo-fiscal' em screens: True
                                     no menu: {'id':'bartolo-fiscal','label':'Bartolo — tire sua dúvida','grupo':'Notas fiscais'}
POST /api/v1/redesign/action/bartolo-perguntar {"frequente":"Por que a NF-e número 2 foi rejeitada?"}
     → ok=True  7.5s  modelo=deepseek-v4-flash
     → "xMotivo literal do retorno da SEFAZ: > 'Rejeicao: Informado NCM inexistente [nItem: 1]' …"
```

### As mesmas 10 perguntas, antes e depois

Mesma rota, mesmo token, mesmo sandbox. (A pergunta 6 da primeira rodada usava um código
inventado, `CAM-001`, que não existe no cadastro; foi remedida dos dois lados com um código
real, `VTV-121`. O caso «código que não existe» virou afirmação do oráculo, onde ele é
determinístico.)

### 1. Qual NCM devo usar para fita isolante?

**ANTES** (17.4s)

> **Sugestão: NCM 3919.10.20 — "De poli(cloreto de vinila)", em rolos de largura não superior a 20 cm.**
>
> Cadeia oficial: *Plástico e suas obras › Chapas, folhas, tiras, fitas, películas e outras formas planas, autoadesivas, de plástico, mesmo em rolos › Em rolos de largura não superior a 20 cm › De poli(cloreto de vinila)*.
>
> Observações úteis (fonte: tabela oficial de NCM consultada agora):
>
> - **É PVC?** A fita isolante elétrica comum é PVC. Se a sua for de **poli(cloreto de vinila) em rolo ≤ 20 cm** → 3919.10.20. Se for de **polipropileno** → 3919.10.10; **outro plástico** → 3919.10.90.
> - **Rolo acima de 20 cm de largura** → sai do "em rolos ≤ 20 cm" e vai para a posição 3919.90 (ex.: 3919.90.20 para PVC).
> - **Não é plástico?** Se a fita for **têxtil, com borracha** (tipo fita de tecido emborrachada), o caminho é outro: 5906.10.00 — *Fitas adesivas de largura não superior a 20 cm*. Vale o alerta: a busca por palavra ("fita isolante") trouxe primeiro resultados têxteis (58.06) e só o código 3919 apareceu quando busquei pela posição — por isso confira a **matéria constitutiva** antes de gravar.
>
> ⚠️ Isto é **sugestão de classificação**, não decisão: a responsabilidade pelo NCM é do contribuinte. Se me disser o fornecedor/produto exato (PVC, largura do rolo, uso elétrico), eu refino — ou me diga se quer o código na ficha do produto/lançamento, que eu preparo o rascunho para aprovação.
>
> [Aviso: alguns números acima não puderam ser verificados automaticamente contra os dados do ERP
>
> […corte em 1.500 caracteres]

**DEPOIS** (15.6s)

> **Não cravo o NCM — quem decide é o contribuinte. Mas a casa já tem os dois lados na base, e eles divergem:**
>
> **No cadastro FISCAL (fin_produtos, fonte que vale para emitir):**
> - `07622` — "FITA ISOL. 18MM X 20M AM IMPERIAL" → **NCM 39191020** — *De poli(cloreto de vinila)*, cap. 39 (plástico), em rolos de largura ≤ 20 cm. CEST 1000900, un. RL, origem 4, **pronto_para_emitir: true** (nada faltando). Fonte: `consultar_fiscal consulta=produto_fiscal busca="fita"`.
>
> **No catálogo de COMPRA (products — não é cadastro fiscal):**
> - `607` e `663` — mesma fita isolante PT → também **39191020**;
> - `67` — "Fita isolante" → **59061000** — *Fitas adesivas de largura não superior a 20 cm*, mas o capítulo 59 é **tecido com borracha** (têxtil), não PVC.
>
> **A divergência, explicitada:** o item `67` contradiz os outros três. O 59.06.10.00 é a posição de fita adesiva **de tecido emborrachado**; a fita isolante de PVC cai em **39.19** — "chapas, folhas, tiras, fitas, películas e outras formas planas, autoadesivas, de plástico, mesmo em rolos › Em rolos de largura não superior a 20 cm › De poli(cloreto de vinila)" (cadeia oficial trazida por `buscar_ncm`). Pela cadeia, o **39191020** é o que descreve o produto; o 59061000 só se a fita fosse têxtil.
>
> **Como eu trato isso:**
> - **Não escolho por você.** Meu palpite não substitui a consulta nem a assinatura do contador — e NCM errado derruba a NF-e na SEFAZ.
> - O que eu faço: **aponto a divergência** e pergunto. A decisão é sua/com contador **e é um
>
> […corte em 1.500 caracteres]


### 2. Por que a NF-e número 2 foi rejeitada?

**ANTES** (16.4s)

> Checagem feita nas fontes fiscais reais do ERP e a resposta honesta é: **não há registro de rejeição para a nota nº 2** — e o módulo fiscal não guarda motivo de rejeição de NF-e. Explico o que encontrei:
>
> **1. NFS-e nº 2 (serviço) — está AUTORIZADA, não rejeitada**
> - Fonte: `nfse_emitidas_nacional` (só entra na base a nota AUTORIZADA, cStat 100).
> - Nº 2 · 22/01/2026 16:38 · tomador **CONDOMÍNIO PRIME ARENA** (CNPJ 47.405.340/0001-66) · serviço "Vigilância, segurança ou monitoramento de bens, pessoas e semoventes" · R$ 36.586,90 · ISS 5% (R$ 1.829,34) · não retido · chave ...00002226013621149857.
>
> **2. NF-e de entrada (mercadoria)**
> - O módulo tem as NF-e de **entrada** (Distribuição DFe/SEFAZ) dos fornecedores, mas elas vêm listadas por chave/número do *fornecedor* — não existe aí nenhum registro de "nº 2" com rejeição, nem campo de motivo/status de rejeição.
>
> **Por que não consigo responder o "por que":** este ERP só recebe nota **autorizada** (NF-e de entrada via DFe e NFS-e via ADN). Mensagem de **rejeição** (código + motivo, ex.: 539/204/225) fica no retorno do SEFAZ/ADN para quem emitiu — não é ingerida aqui. Ou seja: **aguardando dado** para essa parte.
>
> Para eu fechar isso, me diga qual é:
> - **NFS-e nº 2** → já está autorizada (acima); se houve uma segunda tentativa rejeitada, o motivo está no retorno do emissor municipal, fora do ERP;
> - **NF-e modelo 55 (produto, saída)** → esta base não tem NF-e de saída (a Conecta emite NFS-e de serviço); esse log não existe aqui;
> -
>
> […corte em 1.500 caracteres]

**DEPOIS** (10.9s)

> ## Resposta: por que a NF-e nº 2 foi rejeitada
>
> **Retorno literal da SEFAZ (xMotivo):**
>
> > **Rejeicao: Informado NCM inexistente [nItem: 1]**
>
> **O que isso significa:** o NCM informado no **item 1** da nota não está na tabela oficial vigente. O campo a corrigir é o **NCM do item da nota (`nfe_itens.ncm`) e o cadastro fiscal do produto**.
>
> **O item que travou a nota:**
>
> | Item | Código | Descrição | NCM informado | CFOP |
> |---|---|---|---|---|
> | 1 | SEG-001 | SERVIÇO DE SEGURANCA PATRIMONIAL POSTO 24H | **98010000** | 5949 |
>
> **Dados da nota:** NF-e nº 2, série 1, modelo 55 · emitente CNPJ 35.710.481/0001-03 (Jordan Santos de Jesus Ltda) · destinatário CLIENTE TESTE LTDA · emissão 11/04/2026 · competência 2026-04 · valor R$ 5.000,00 · status **rejeitada**, sem protocolo de autorização. Nota rejeitada **não existe para o fisco**.
>
> ---
>
> ### Ponto importante: o cadastro do produto
>
> Consultei o cadastro fiscal pelo código `SEG-001` e o retorno foi: **não sei — a casa não tem esse dado registrado.** O `o_que_falta` é: *"nenhum produto com esse código/descrição, nem no cadastro fiscal nem no catálogo de compra. Sem o item identificado não há NCM a validar — e eu não invento NCM. Peça o código como ele aparece no cadastro."*
>
> Ou seja: não há NCM validado para esse item na base. A decisão está pendente em **/redesign/bi?t=decisoes-do-dono**.
>
> **Corrija no cadastro, não só na nota** — corrigido só na nota, a próxima sai rejeitada igual. Para achar o código vigente, use a consulta `busc
>
> […corte em 1.500 caracteres]


### 3. Posso vender material para o Ideal Flores com ICMS desonerado?

**ANTES** (34.5s)

> ## Resposta direta: com o que existe no sistema, **não consigo confirmar** — e não vou chutar ICMS (é matéria legal, não estimo).
>
> Não há **nenhum registro de benefício/desoneração de ICMS ativo** para nenhum dos dois CNPJs no nosso cadastro fiscal. O `panorama_grupo` de 09/2026 mostra: Eletrônica (35.710.481/0001-03) em **Lucro Real**, sem qualquer linha de benefício; Patrimonial (66.014.833/0001-10) em Simples com **"liminares_ativas": [] / nenhuma_concedida**. Ou seja: o que existe de desoneração na casa hoje é **nada**. Se ICMS desonerado existe aqui, ele não está cadastrado em lugar nenhum que eu leia — precisa de base legal (convênio/benefício) e confirmação da contabilidade/SEFAZ-AM.
>
> ## O que os dados mostram sobre o Ideal Flores
>
> - **Cliente:** CONDOMINIO IDEAL FLORES DA CIDADE — CNPJ **23.147.782/0001-91**, Manaus/AM, VIP, segmento enterprise (CRM, CLI-0015).
> - **Relação atual = serviço, não material:** contrato **CTR-2026-00013 "Portaria + Serv. Gerais — Ideal Flores"**, R$ **65.842,42/mês**, vigência 01/01–31/12/2026, renovação automática.
> - Nas NFS-e emitidas eu achei **9 notas, todas de serviço** ("Vigilância, segurança ou monitoramento de bens, pessoas e semoventes"), R$ 65.842,42 cada. **Não há uma única venda de material faturada ao Ideal Flores** — então "vender material" aqui é operação NOVA, e material = **NF-e de mercadoria pela Eletrônica** (não NFS-e). ICMS é imposto de mercadoria: nenhuma dessas 9 notas serve de precedente.
>
> ## ⚠️ Três coisas que apare
>
> […corte em 1.500 caracteres]

**DEPOIS** (24.0s)

> ## Resposta curta: **não sei — e não vou cravar.**
>
> "ICMS desonerado" não é um sim/não genérico: ele depende do **NCM do material**, da **condição tributária do destinatário** e da operação. Nenhum desses três eu tiro da memória — só de `buscar_ncm` / `produto_fiscal` / `tributacao_nfe`. Sem isso, dizer "pode" seria chute com consequência fiscal.
>
> ## O que eu já apurei (dado real)
>
> | Item | Achado | Fonte |
> |---|---|---|
> | Cliente | **CONDOMINIO IDEAL FLORES DA CIDADE** — CNPJ 23147782000191, Manaus/AM, ativo, VIP, 1 contrato, MRR R$ 65.842,42 | `crm/clientes` (CLI-0015) |
> | Orçamento de origem | **Não há** orçamento/proposta registrado que origine essa venda | `fiscal/orcamento_origem` → *"Não sei — a casa não tem esse dado registrado"* |
> | Histórico de NF-e 55 | **Nenhuma nota de mercadoria para o Ideal Flores.** Só existem 2 NF-e no acervo, ambas **rejeitadas**, destinatário "CLIENTE TESTE LTDA" | `fiscal/nfe_saida` |
> | Cadastro fiscal dos materiais | Os itens do catálogo estão **sem NCM** (câmeras, cabos, barreira, arame…) | `crm/catalogo` |
>
> Ou seja: essa seria a **primeira NF-e de mercadoria real** da casa — e o cadastro fiscal dos produtos hoje não tem NCM, que é justamente o campo que o fisco devolve rejeitado (a nota 2 do teste caiu por *"Informado NCM inexistente [nItem: 1]"*).
>
> ## O que falta para eu responder (e onde a decisão está pendente)
>
> 1. **Qual material.** Descrição ou SKU. Com isso eu rodo `buscar_ncm` (tabela oficial, 10.515 códigos) e `produto_fiscal` p
>
> […corte em 1.500 caracteres]


### 4. Qual CFOP para venda de material dentro do Amazonas?

**ANTES** (30.2s)

> **Ponto de partida:** operação **dentro do Amazonas** = CFOP de **prefixo 5** (nunca 6.xxx, que é interestadual). O código exato depende de três coisas: o material é de **produção própria** ou **revenda de terceiros**; o destinatário é **contribuinte** (revenda/industrialização) ou **consumidor final não contribuinte**; e a entrega é **no estabelecimento** ou **fora dele**.
>
> **Mapa padrão (tabela CFOP vigente – Ajuste SINIEF):**
>
> | Situação da venda de material (destino: Amazonas) | CFOP |
> |---|---|
> | Mercadoria adquirida de terceiros para revenda → destinatário **contribuinte** (o caso mais comum em "venda de material") | **5.102** |
> | Produção própria do estabelecimento → destinatário **contribuinte** | **5.101** |
> | Mercadoria de terceiros → **consumidor final não contribuinte** | **5.106** |
> | Produção própria → **consumidor final não contribuinte** | **5.105** |
> | Venda efetuada **fora do estabelecimento** (entrega em obra/veículo/balcão externo) | **5.103 / 5.104** |
> | Destinada à **Zona Franca de Manaus / ALC**, quando quem remete está **fora** da ZFM/ALC | **5.109 / 5.110** |
>
> Retornos e correlatas, se aparecerem no seu fluxo: devolução **5.201/5.202**, venda em consignação **5.405/5.406**.
>
> **Três armadilhas que eu sinalizo sempre:**
> 1. **CFOP não define tributo.** Ele diz *o que é* a operação. Quem define ICMS é o **CST/CSOSN + regra de ST**. Em operação interna **não existe DIFAL** — DIFAL só em interestadual. Se o material tem substituição tributária no AM, a nota
>
> […corte em 1.500 caracteres]

**DEPOIS** (12.5s)

> **Não sei.** — e não vou chutar: CFOP de mercadoria não sai de memória minha.
>
> Consultei `consultar_fiscal consulta=tributacao_nfe` (operação interna no AM, `destinatario.uf=AM`, `operacao=revenda`) e o retorno foi literalmente: *"Não sei — a casa não tem esse dado registrado."*
>
> **O que falta** (repetindo o retorno, sem parafrasear):
> > o serviço de tributação de NF-e de mercadoria (`modules/fiscal/services/tributacao_nfe.py`, frente Z4) não está neste servidor. Sem ele eu NÃO calculo imposto: alíquota, CST/CSOSN e CFOP de mercadoria não saem de palpite meu.
>
> **Onde a decisão está pendente:** `/redesign/bi?t=decisoes-do-dono`
>
> ---
>
> O que eu **posso** dizer com segurança, e o que ainda depende de dado real:
>
> - **É NF-e modelo 55, não NFS-e.** Venda de material é mercadoria; as duas não se somam nem se substituem. O CNPJ emitente disso é a **Conecta Eletrônica** (Lucro Real) — não a Patrimonial.
> - **Como o CFOP é escolhido** (estrutura, não o valor): ele codifica o *sentido da operação* (entrada/saída), a *abrangência* (interna, interestadual, exterior) e o *motivo/beneficiamento*. Venda de material a destinatário **no Amazonas** cai no grupo de operação **interna de saída** — e o restante do código depende de a mercadoria ser revenda de terceiro, produção própria, bem do ativo, brinde, etc. Qual desses é o seu caso, só o serviço fiscal da casa carimba — com a norma de cada número.
> - Eu **não cravo** o código de 4 dígitos. Qualquer um que eu escrevesse aqui seria invenção.
>
> ---
>
> […corte em 1.500 caracteres]


### 5. Quantas NF-e de saída existem e qual o status de cada uma?

**ANTES** (20.6s)

> **Não há NF-e de saída na base — o que existe no Fiscal é NFS-e (nota de serviço).** Se você quis dizer as notas de serviço emitidas, segue o retrato real:
>
> | Item | Número |
> |---|---|
> | NFS-e emitidas (total) | **114** |
> | Status | **100% "autorizada"** (114 de 114) |
> | Canceladas / pendentes / rejeitadas | **0** |
>
> Fonte: `consultar_fiscal` → `listar_nfse` (114 registros, todos `status: "autorizada"`) e `nfse_dashboard` (`nfse_emitidas: 114`).
>
> Distribuição por competência (mês):
> - 09/2026: 2 · 08/2026: 13 · 07/2026: 14 · 06/2026: 18 · 05/2026: 15 · 04/2026: 14 · 03/2026: 12 · 02/2026: 13 · 01/2026: 13
>
> Faturamento bruto acumulado: **R$ 2.277.037,40** · ISS total: **R$ 90.368,18**.
>
> **Observações da lente FISCAL:**
> 1. **NF-e de mercadoria: aguardando dado.** As tools fiscais que consultei só trazem NFS-e. Não há registro de NF-e (produto/ICMS) — se você espera notas de mercadoria, me diga que eu investigo onde elas estariam.
> 2. **Divisão por CNPJ** (dá para separar pelo prefixo da chave):
>    - Eletrônica (35.710.481 — Lucro Real): notas de instalação/manutenção (segurança eletrônica).
>    - Patrimonial (66.014.833 — Simples Anexo III): notas de vigilância/limpeza (mão de obra).
>    Se quiser, eu abro o detalhamento por CNPJ — e já adianto que vale cruzar algumas notas de "Vigilância/segurança" emitidas pelo CNPJ da Eletrônica para conferir se o escopo está na empresa certa.
>
> Quer que eu detalhe por CNPJ ou filtre por competência/serviço?

**DEPOIS** (9.4s)

> **NF-e de saída (modelo 55, mercadoria): existem 2 — e as duas estão REJEITADAS.** Fonte: `nfes` (consulta `nfe_saida`).
>
> | # | Série | Emissão | Competência | Destinatário | Valor | Status |
> |---|-------|---------|-------------|--------------|-------|--------|
> | 2 | 1 | 11/04/2026 | 2026-04 | CLIENTE TESTE LTDA | R$ 5.000,00 | **rejeitada** |
> | 1 | 1 | 11/04/2026 | 2026-04 | CLIENTE TESTE LTDA | R$ 5.000,00 | **rejeitada** |
>
> Nenhuma tem protocolo de autorização (`protocolo_autorizacao: null`) — ou seja, **nota rejeitada não existe para o fisco**.
>
> **O que a SEFAZ devolveu (xMotivo literal):**
>
> - **NF-e 2** — `"Rejeicao: Informado NCM inexistente [nItem: 1]"`
>   - Onde corrigir: item da nota → NCM, e o **cadastro fiscal do produto**.
>   - Item apontado: código `SEG-001` — “SERVICO DE SEGURANCA PATRIMONIAL POSTO 24H”, NCM `98010000`, CFOP `5949`. Esse NCM está fora da tabela oficial vigente.
>   - Correção é no **cadastro do produto**, não só na nota — corrigido só na nota, a próxima sai rejeitada igual. Para achar o código vigente: `buscar_ncm`; para ver o que o cadastro tem hoje: `produto_fiscal`. **Não cravo NCM novo** — a classificação é responsabilidade do contribuinte; o sistema sugere, quem decide é o contador.
>
> - **NF-e 1** — `"Lote processado"`
>   - Atenção: **“Lote processado” não é motivo de rejeição de nota** — é retorno de lote. A consulta `nfe_rejeicao` devolveu `nao_sei: true`, sem tradução cadastrada e sem campo a corrigir. Não vou inventar a causa: **o texto liter
>
> […corte em 1.500 caracteres]


### 6. O produto de código VTV-121 está com NCM válido para eu emitir nota?

**ANTES** (14.8s)

> **Sim — o NCM está preenchido e é um código válido**, mas com uma ressalva de classificação que vale conferir.
>
> **O que os dados mostram (catálogo CRM + tabela oficial da RFB):**
>
> | Campo | Valor |
> |---|---|
> | SKU | VTV-121 |
> | Nome | SMART INTERRUPTOR 1 SENSOR (IPI 9,75%) |
> | NCM cadastrado | 85365090 |
> | Origem | Bling (sem preço no catálogo) |
>
> **Na tabela oficial de NCM (10.515 códigos), o 85365090 existe** e a cadeia é:
> - Capítulo XVI → Máquinas, aparelhos e materiais elétricos
> - Posição **8536** — aparelhos para interrupção, seccionamento, proteção, ligação ou conexão de circuitos elétricos, **para tensão não superior a 1.000 V**
> - Subposição **8536.50** — Outros interruptores, seccionadores e comutadores
> - Item **8536.50.90** — "**Outros**"
>
> Ou seja: **não é código inexistente nem de outro capítulo** — está na família correta (interruptor, baixa tensão). Do ponto de vista de "dá para emitir", o NCM está preenchido e é válido.
>
> **Ressalvas que eu não posso decidir por você:**
> 1. **É um código residual ("Outros").** O 8536.50.90 é genérico; a RFB devolve a responsabilidade da classificação ao contribuinte. Se o item tem especificidade (ex.: classificação própria por tipo de acionamento/tensão), o correto seria o item específico do 8536.50, não o "Outros".
> 2. **Inconsistência dentro da própria família Bling "SMART":** o VTV-110 **SMART CONTROLE** está com **85437099** (posição 8543 — máquinas/aparelhos elétricos com função própria), enquanto VTV-121/122/123 (interruptores
>
> […corte em 1.500 caracteres]

**DEPOIS** (13.3s)

> **Resposta curta: o NCM é válido — mas isso, sozinho, não libera a nota.** O item ainda está no catálogo de compra, não no cadastro fiscal.
>
> **O que a consulta devolveu** (fonte: `produto_fiscal`, cruzando `fin_produtos` + `products` × `ncms`):
>
> | Campo | Valor |
> |---|---|
> | Código | VTV-121 — SMART INTERRUPTOR 1 SENSOR (IPI 9,75%) |
> | NCM | 85365090 |
> | Unidade | un |
> | Origem | 0 |
> | CEST | *(vazio)* |
> | CFOP de saída | *(vazio)* |
> | Situação | ativo |
> | Fonte do cadastro | **catálogo de compra (`products`) — NÃO é cadastro fiscal** |
>
> **O NCM confere?** Sim, existe na tabela oficial. Pela `buscar_ncm`, o 85365090 é: *Máquinas, aparelhos e materiais elétricos…* › *Aparelhos para interrupção, seccionamento, proteção, derivação, ligação ou conexão de circuitos elétricos… até 1.000 V* › *Outros interruptores, seccionadores e comutadores* › **Outros**. Ou seja, a cadeia fecha com a descrição do produto (interruptor/sensor de 1 canal). É sugestão, não homologação — **o NCM é responsabilidade do contribuinte**.
>
> **Onde está o bloqueio.** O registro veio carimbado como *catálogo de compra*, e o próprio retorno avisa: o item só vira linha de NF-e quando aparece com fonte **«cadastro fiscal»**, porque o catálogo de compra não carrega **CST/CSOSN por CNPJ** nem **CFOP de saída** — e é exatamente isso que está vazio aqui (`cfop_out: null`, sem CST). Os flags do registro dizem `pronto_para_emitir: true` / `falta_para_emitir: []`, mas a fonte do dado é a mesma que o aviso manda desconsi
>
> […corte em 1.500 caracteres]


### 7. Qual a alíquota de ICMS numa venda de material da Conecta Eletrônica para um cliente em Manaus?

**ANTES** (11.5s)

> Não tenho essa alíquota em nenhuma fonte do ERP — e não vou chutar valor legal. O que consultei e o que dá pra afirmar com dado real:
>
> **O que o ERP diz (e não é ICMS)**
> - `panorama_grupo` (09/2026): a **Conecta Eletrônica (CNPJ 35.710.481/0001-03)** está em **Lucro Real**, regime em que o ICMS é destacado normalmente na NF-e (não é o ICMS "dentro" do Simples). Impostos apurados do mês são só IRPJ/CSLL/PIS/COFINS/ISS — **nenhuma linha de ICMS** aparece.
> - `dashboard_fiscal` (09/2026): a receita da Eletrônica é **100% serviços** (`receita_servicos` R$ 48.120,00 / `receita_vendas` R$ 0,00) e a dedução é **ISS** (R$ 2.406,00). Ou seja: **não há venda de mercadoria registrada no sistema hoje** — o cenário da sua pergunta ainda não existe na base.
>
> **Por que eu não te dou o percentual**
> - O ERP não tem tabela de ICMS. Ele cobre NFS-e (serviços), obrigações, DRE, eSocial — não a tributação estadual de mercadoria.
> - A alíquota de ICMS numa venda de material **não é um número único**: depende do **NCM do produto**, de ser operação **interna (AM→AM)** ou interestadual, de haver **substituição tributária**, benefício/redução de base e da legislação vigente do Amazonas. Definir isso é ato do contador, não do ERP — e eu não invento valor legal.
>
> **Onde eu consigo ajudar de verdade**
> 1. **Classificação do produto**: me diga o que é o material e eu rodo `buscar_ncm` (tabela oficial, 10.515 códigos) e devolvo a classificação sugerida — é o insumo que a contabilidade precisa pra fixar a alíq
>
> […corte em 1.500 caracteres]

**DEPOIS** (14.1s)

> **NÃO SEI.**
>
> E não é retórica: a alíquota de ICMS de mercadoria é um dos três números que eu não posso cravar de memória (junto com NCM e CFOP). Consultei e a casa **não tem esse dado**:
>
> - `tributacao_nfe` → devolveu `nao_sei`. **O que falta:** *"o serviço de tributação de NF-e de mercadoria (`modules/fiscal/services/tributacao_nfe.py`, frente Z4) não está neste servidor. Sem ele eu NÃO calculo imposto: alíquota, CST/CSOSN e CFOP de mercadoria não saem de palpite meu."*
> - `nfe_saida` (Eletrônica) → nenhuma NF-e de saída registrada que sirva de precedente real.
> - `produto_fiscal` → não listo o cadastro todo; preciso do `codigo` ou de um `busca` (parte da descrição).
>
> **Onde a decisão está pendente:** `/redesign/bi?t=decisoes-do-dono`.
>
> Para o cálculo rodar, o serviço precisa destes campos — e é por isso que "venda de material para Manaus" ainda não fecha uma alíquota:
>
> | Campo | Por que muda o número |
> |---|---|
> | **empresa_cnpj** (emitente) | se o emitente está no AM, a venda para Manaus é **operaçom interna**; se está fora, é **interestadual** — são regras diferentes |
> | **NCM do item** | define o tratamento do produto |
> | **origem** da mercadoria | nacional/importada muda o CST |
> | **operação** | `revenda` ou `producao` |
> | **destinatário** | UF, CNPJ, inscrição estadual, **inscrição SUFRAMA** e código do município (Manaus = 1302603) — destinatário na Zona Franca de Manaus tem campo e tratamento próprios |
> | **valor** e **quantidade** | base de cálculo |
>
> O que eu **consi
>
> […corte em 1.500 caracteres]


### 8. Tenho um orçamento aprovado; o que falta para ele virar NF-e?

**ANTES** (48.1s)

> Não consigo responder no singular sem você me dizer **qual** orçamento — e há um detalhe importante de nomenclatura. Segue o estado real.
>
> ## 1) "Aprovado" ≠ o que está no CRM
> No CRM, **nenhuma proposta tem aprovação registrada** (`approved_by_id` e `approved_at` vazios em todas as 12). O que existe são **3 com status `accepted`** (aceite do cliente):
>
> | Proposta | Cliente | Valor | Aceite em | O que existe à frente |
> |---|---|---|---|---|
> | PROP-2026-00096 | Cond. Bosque Resid. Kopenhagen | R$ 45.312,00/mês | 10/09/2026 | CTR-2026-00024 *(draft)* + CTR-2026-00023 *(draft)* — somam 40.612 + 4.700 = 45.312 ✓ |
> | PROP-20260610-98EF41 | Cond. Resid. Parque dos Franceses | R$ 1.800,00/mês | 08/09/2026 | CTR-2026-00015 *(ativo)* e já há **NFS-e 121 de 17/09, R$ 1.800** |
> | PROP-20260623-485D7A | Residencial Laranjeiras Village (cerca elétrica) | R$ 11.966,70 (produto) | 23/06/2026 | **nenhum contrato** desse escopo e **nenhuma nota** de 11.966,70 |
>
> Se o que você chama de "aprovado" é o aceite do cliente, é um desses três. Se é aprovação formal interna, ela não está registrada em lugar nenhum — me diga qual e eu sigo.
>
> ⚠️ Também há duas propostas com status `draft` (PROP-2026-00123 e 00124) **tendo a própria Conecta Patrimonial como cliente** (intra-grupo, bateria de QA). Se alguma dessas é a sua, ela não pode virar nota: é registro de teste, não operação.
>
> ## 2) O que falta, por caso
>
> **Kopenhagen (o mais perto):** falta **contrato saído do rascunho**. Os dois estão `draft`/`pend
>
> […corte em 1.500 caracteres]

**DEPOIS** (32.9s)

> ## Primeiro, um alerta: há **três** propostas com aceite — e só uma delas é de mercadoria
>
> Fonte: `proposals` (CRM). Todas as três estão com `status: accepted` **e** `aprovada_internamente: false`:
>
> | Proposta | Cliente | Valor | Natureza | Vira… |
> |---|---|---|---|---|
> | **PROP-20260623-485D7A** | Cond. Residencial Laranjeiras Village (24.632.786/0001-28) | R$ 11.966,70 (aceita em 23/06/2026) | Cerca elétrica — 3 itens de material + 1 serviço | **NF-e (modelo 55)** |
> | PROP-2026-00096 | Cond. Bosque Residencial Kopenhagen | R$ 45.312,00 | Portaria / Conecta Plus / aluguel de equipamento | NFS-e |
> | PROP-20260610-98EF41 | Cond. Residencial Parque dos Franceses | R$ 1.800,00 | Manutenção preventiva/corretiva | NFS-e |
>
> Então: **NF-e de mercadoria só se aplica à Cerca Elétrica — Laranjeiras Village.** Se era outra que você tinha em mente, me diga. E confirme uma coisa: *accepted* é **aceite do cliente**; "aprovado internamente" é outro campo — e nas três ele está `false`.
>
> ## O que falta na Cerca Elétrica (PROP-20260623-485D7A)
>
> O orçamento tem 4 linhas, todas com `code: null` — **descrição livre, sem produto vinculado**. Descrição livre não tem NCM nem CFOP, e eu não invento nenhum dos dois. Item por item (fonte: `proposal_items` + `produto_fiscal`/catálogo):
>
> | Item do orçamento | No cadastro fiscal (`fin_produtos`)? | O que falta |
> |---|---|---|
> | Haste de passar 25x25 — 127 un | Não. Só no **catálogo de compra** (cod. 101, NCM 76042920) | Casar com produto fiscal — o catálo
>
> […corte em 1.500 caracteres]


### 9. A Conecta Patrimonial, que é do Simples Nacional, usa CST ou CSOSN na NF-e de material?

**ANTES** (20.3s)

> ## Resposta direta
>
> Na **NF-e de mercadoria**, quem é **optante do Simples Nacional usa CSOSN** (tabela do Simples: 101, 102, 103, 201, 202, 500, 900…), **não CST**. O CST (00, 10, 20, 40, 41, 60, 90…) é a tabela do **regime normal** — no nosso caso, a **Eletrônica (Lucro Real)**. As duas tabelas não se misturam no mesmo emitente: o campo `<ICMS>` só aceita um grupo por nota, conforme o regime do emissor.
>
> ## Mas tem um problema de escopo na sua pergunta
>
> **NF-e de material não é escopo da Patrimonial.** Pelo nosso desenho de CNPJ:
> - **Eletrônica** = equipamento (CFTV, acesso, alarme, infra, portaria remota) → **NF-e**, Lucro Real → **CST**.
> - **Patrimonial** = mão de obra humanizada → **NFS-e** (ISS, sem ICMS, logo sem CST/CSOSN).
>
> Então: se está saindo **NF-e de material no CNPJ da Patrimonial**, isso não é escolha de código — é **nota no CNPJ errado** (o certo seria a Eletrônica). E se for **NFS-e**, a pergunta nem se aplica: NFS-e de serviço não tem CST nem CSOSN de ICMS.
>
> ## O que eu consigo (e não consigo) confirmar do ERP
>
> **Confirmado** — Simples Nacional ativo para a operação de serviços (`consultar_fiscal → status_simples`): CNPJ 35710481000103, **Anexo III**, limite R$ 4.800.000/ano.
>
> **Não consigo confirm
>
> [Aviso: alguns números acima não puderam ser verificados automaticamente contra os dados do ERP — confira antes de decidir.]

**DEPOIS** (17.9s)

> ## Resposta direta
>
> **CSOSN — porque quem define é o REGIME do emissor, não o tipo do produto.**
>
> Na NF-e o campo de ICMS usa **duas tabelas diferentes**, e a escolha não tem nada a ver com ser material ou serviço:
>
> | Tabela | Quem usa |
> |---|---|
> | **CST** (Tabela B do regime normal) | Lucro Real / Presumido — **não optante** do Simples |
> | **CSOSN** (tabela do Simples Nacional, Ajuste SINIEF 07/05) | **optante do Simples Nacional** |
>
> Então: emitiu pela **Patrimonial (Simples)** → **CSOSN**. Emitiu pela **Eletrônica (Lucro Real)** → **CST**. Mesma mercadoria, tabelas diferentes — muda o CNPJ que emite.
>
> ## O que a base diz (fonte: consultar_fiscal)
>
> - `status_simples`: CNPJ **35710481000103 — Conecta Segurança LTDA**, **Anexo III**, serviços (Fator R ≥ 28%, "vigilância, limpeza"). Premissa confirmada: é optante.
> - `nfe_saida` filtrando empresa = **conecta_patrimonial**: **NÃO SEI** — o retorno foi ausência de dado: *"nenhuma NF-e de saída bate com esse filtro em `nfes`"*. Ou seja, **não há hoje nenhuma NF-e de mercadoria emitida pela Patrimonial** no sistema. Se ela já vendeu material, isso não está registrado aqui.
>
> ## Dois pontos que eu preciso te devolver como alerta
>
> 1. **Material de equipamento é história da Eletrônica.** O desenho da casa é: mão de obra → Patrimonial (NFS-e) · equipamento/CFTV → Eletrônica (NF-e). Se essa nota de material é venda de equipamento, o emissor natural é a **Eletrônica (Lucro Real)** — e aí a resposta muda para **CST**. Vale conferir quem e
>
> […corte em 1.500 caracteres]


### 10. O que significa a rejeição "Informado NCM inexistente" e como eu corrijo?

**ANTES** (21.4s)

> ## O que a rejeição quer dizer
>
> O texto é literal: **o NCM que foi informado na nota não existe na tabela oficial** de NCM da Receita Federal. O validador não "achou" o código — ele não bate com nenhum código vigente da tabela (a mesma que eu consulto aqui, com os códigos vigentes; é ela que decide, não o seu cadastro).
>
> Na prática, ela quase sempre é uma destas cinco coisas:
>
> | Causa | Exemplo típico |
> |---|---|
> | **Digitação** | dígito trocado — o NCM tem **8 dígitos**, sem ponto |
> | **Faltando/sobrando dígito** | código cortado (4 ou 6 dígitos) quando o item exige o item completo |
> | **Código extinto / fora de vigência** | a tabela é versionada; código da versão antiga deixa de existir |
> | **Código "pai"/genérico** | posição sem o item específico (".00") ou código de "não especificado" que não é aceito |
> | **Campo trocado** | NCM preenchido onde o campo é de **serviço** (item da lista LC 116 / NBS) — NCM é classificação de **mercadoria** |
>
> Essa última é a que mais mexe com a gente: mercadoria (NF-e) → **Eletrônica**; serviço (NFS-e) → **Patrimonial/portaria**. Se a nota rejeitada é de serviço, o problema pode não ser "o NCM certo", e sim que não era NCM ali.
>
> ## Como corrigir
>
> 1. **Pegue a mensagem completa e o item exato** que a SEFAZ/prefeitura apontou (a linha rejeitada, não a nota inteira).
> 2. **Identifique o produto** que está naquela linha.
> 3. **Valide o código na tabela oficial** — me diga o produto e eu consulto aqui, devolve ou confirma, com a cadeia capítulo › p
>
> […corte em 1.500 caracteres]

**DEPOIS** (25.8s)

> ## O que a rejeição significa
>
> O texto que voltou da SEFAZ, **literal**, na NF-e nº 2 (série 1, emitida 11/04/2026, destinatário CLIENTE TESTE LTDA) é:
>
> > **"Rejeicao: Informado NCM inexistente [nItem: 1]"**
>
> Traduzindo: o **NCM declarado no item 1 da nota não existe na tabela oficial de NCM vigente**. Não é erro de valor, de imposto nem de cadastro do cliente — é o campo de classificação do produto. A SEFAZ não autoriza a nota enquanto o código não for um NCM válido.
>
> Fonte: `nfes.motivo_rejeicao` (retorno da SEFAZ) + cruzamento `nfe_itens × ncms`.
>
> ## Onde aconteceu (dado real)
>
> | | |
> |---|---|
> | Nota | NF-e nº **2**, série 1 — status **rejeitada** |
> | Chave | 13260435710481000103550010000000021231171020 |
> | Item 1 | código **SEG-001** — "SERVICO DE SEGURANCA PATRIMONIAL POSTO 24H" |
> | NCM informado | **98010000** — e confirmei: a busca na tabela oficial por "9801" devolve **0 códigos**. Não existe. |
>
> A NF-e nº 1 também está **rejeitada**, mas com motivo diferente — "**Lote processado**" — para o qual **eu não sei** a causa: não há tradução cadastrada para essa rejeição. Leve o texto literal ao contador; decisão pendente em **/redesign/bi?t=decisoes-do-dono**.
>
> ## Como corrigir (a ordem importa)
>
> 1. **Corrija no CADASTRO do produto, não só na nota.** O caminho é `item da nota → NCM (nfe_itens.ncm)` **+** o cadastro fiscal do produto (fin_produtos). Se corrigir só na nota, a próxima sai rejeitada igual.
> 2. **Ache o código vigente** com a consulta `buscar_ncm` (tabela oficia
>
> […corte em 1.500 caracteres]

**O saldo das 10:**

| Efeito | Perguntas |
|--------|-----------|
| Passou a responder com dado real que antes negava | 2, 5, 10 (e 3, 8 ganharam o lado de NF-e) |
| Passou a distinguir cadastro fiscal × catálogo de compra | 1, 6, 8 |
| **Passou a dizer «não sei» em vez de inventar CFOP/alíquota** | **4, 7** |
| Já estava certo e continuou | 9 |

As perguntas 4 e 7 são o ponto que merece atenção do dono: **antes** o Bartolo entregava uma
tabela inteira de CFOP e discorria sobre ICMS de memória; **depois** ele diz «Não sei — e não vou
chutar», repete o `o_que_falta` e aponta o painel. Isso é a regra funcionando, não uma perda —
e vira número de verdade assim que a Z4 entrar no mesmo servidor (§7).

---

## §4 — Oráculo

`backend/scripts/orq/test_oraculo_z6_bartolo.py` — 26 afirmações.

```bash
ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' \
       | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')
docker run --rm --network conecta-staging-network -v "$PWD/backend:/app:ro" \
  -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env \
  -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \
  conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_z6_bartolo.py
# Z6_SEM_LLM=1 pula a rodada das 10 perguntas (deixa o oráculo determinístico e barato)
```

### Vermelho (rodado com os dois arquivos novos fora do lugar — o estado de antes)

```
[1] Toda ferramenta nova é SÓ LEITURA
  FALHA tools_read_fiscal_nfe.py existe
        /app/modules/ai/conversation/services/orquestrador/tools_read_fiscal_nfe.py
  FALHA dgx_z6_bartolo.py existe
        /app/modules/operacional/controllers/redesign_builders/dgx_z6_bartolo.py

[2] O que a casa não tem volta como «não sei» + ponteiro, nunca como número
ImportError: cannot import name 'tools_read_fiscal_nfe' from
  'modules.ai.conversation.services.orquestrador'
EXIT=1
```

### Verde (código no lugar, rodada completa, com as 10 perguntas de verdade)

```
[1] Toda ferramenta nova é SÓ LEITURA
  OK   tools_read_fiscal_nfe.py existe
  OK   tools_read_fiscal_nfe.py: nenhuma escrita em SQL
  OK   tools_read_fiscal_nfe.py: nenhum commit()
  OK   dgx_z6_bartolo.py existe
  OK   dgx_z6_bartolo.py: nenhuma escrita em SQL
  OK   dgx_z6_bartolo.py: nenhum commit()

[2] O que a casa não tem volta como «não sei» + ponteiro, nunca como número
  OK   produto inexistente → nao_sei=True
  OK   aponta o painel do dono
  OK   nenhum NCM de 8 dígitos na resposta
  OK   nenhuma alíquota na resposta
  OK   NF-e inexistente → nao_sei=True
  OK   aponta o painel do dono (nfe_saida)

[3] A explicação de rejeição cita o xMotivo REAL da nota
  OK   o NCM 98010000 da fixture NÃO está na tabela oficial
  OK   devolve o xMotivo caractere por caractere, sem reescrever
  OK   diz qual CAMPO corrigir
  OK   lista o item cujo NCM não está em `ncms` (medido por SQL)
  OK   a explicação não sugere nenhum NCM
  OK   a listagem carrega o mesmo motivo literal

[4] A tributação que o Bartolo diz É a que o serviço da Z4 calcula
  OK   o repasse entrega o OBJETO do serviço fiscal, sem recalcular nada
       (Z4 ausente nesta branch — provado por serviço injetado)
  OK   sem o serviço da Z4, o Bartolo diz que NÃO SABE em vez de estimar
  OK   e não devolve alíquota nenhuma

[5] As 10 perguntas frequentes — a tela e a rota
  OK   as 10 perguntas do §1 estão clicáveis na tela, na ordem
  OK   são 10
  OK   todas passam o mínimo de 3 caracteres do ConsultarIn
  OK   há campo livre além das frequentes
        [ 1/10] ok  Qual NCM devo usar para fita isolante?
        [ 2/10] ok  Por que a NF-e número 2 foi rejeitada?
        [ 3/10] ok  Posso vender material para o Ideal Flores com ICMS desonerado?
        [ 4/10] ok  Qual CFOP para venda de material dentro do Amazonas?
        [ 5/10] ok  Quantas NF-e de saída existem e qual o status de cada uma?
        [ 6/10] ok  O produto de código VTV-121 está com NCM válido para eu emitir
        [ 7/10] ok  Qual a alíquota de ICMS numa venda de material da Conecta Elet
        [ 8/10] ok  Tenho um orçamento aprovado; o que falta para ele virar NF-e?
        [ 9/10] ok  A Conecta Patrimonial, que é do Simples Nacional, usa CST ou C
        [10/10] ok  O que significa a rejeição "Informado NCM inexistente" e como
  OK   as 10 perguntas respondem sem erro pela rota real

  fixtures 'FIXTURE DGX Z6' apagadas.
TOTAL afirmações Z6 (Bartolo fiscal): 26 — 26 verdes, 0 vermelhas   (EXIT=0)
```

**A afirmação nº 4 é a que mais importa.** Ela prova que o Bartolo **não tem régua paralela**:
o que ele diz de tributação é o objeto que o serviço da Z4 devolveu, não uma releitura dele.
Com a Z4 presente, compara os dois cálculos por igualdade; sem ela (o caso desta branch), injeta
um serviço falso e exige **identidade de objeto** — que é mais forte. Se algum dia alguém
«melhorar» o repasse recalculando um campo, este teste fica vermelho.

**Um defeito real que o oráculo pegou durante a frente:** a primeira versão de
`orcamento_origem` lia `proposal_items.total_price`, coluna que não existe. O `SELECT` falhou e
deixou a `AsyncSession` em *«current transaction is aborted»* — **as duas perguntas seguintes da
mesma sessão morreram** com um erro que não tinha nada a ver com elas. Corrigidas as duas coisas:
a coluna certa (`total`) e um `rollback` por consulta (`_consulta`), para que uma consulta que
estoura não derrube a conversa inteira.

---

## §5 — O que NÃO foi feito, e por quê

1. **Nenhum chat novo, nenhuma persona nova, nenhum endpoint de conversa novo.** A casa já tem
   `/consultores/chat/consultar` com lente fiscal, o consultor fiscal ancorado
   (`/fiscal/consultor/perguntar`) e o botão «Abrir assistente» do redesign. Criar um quarto
   seria a quarta coisa para manter.
2. **`buscar_ncm` não foi reescrita.** Já existia, com relaxamento progressivo de termo e aviso
   de responsabilidade do contribuinte. As descrições novas apontam para ela.
3. **Nenhuma ferramenta de escrita.** O brief é explícito e a varredura do oráculo é a trava:
   o Bartolo não emite, não assina, não transmite, não cancela e não inutiliza.
4. **`frontend/` não foi tocado** (zona proibida). Consequência visível: a resposta do Bartolo
   chega no `message` da ação, que o `ModuleView.tsx` renderiza como **badge de texto** — ele
   quebra linha e cresce, mas **não renderiza Markdown**, então tabela e negrito aparecem como
   texto cru. O painel «Resultado» só sabe montar pares rótulo→valor e descarta texto longo.
   **O diff de frontend que faria melhor** (para o orquestrador decidir): em
   `frontend/src/components/redesign/ModuleView.tsx`, aceitar no resultado uma chave
   `resposta_markdown` e renderizá-la num bloco próprio com o mesmo renderer de Markdown que o
   chat flutuante já usa, em vez de passar pelo `fmt()` de escalares. São ~15 linhas, e com elas
   a ação passaria a devolver `resposta_markdown` em vez de empurrar tudo para o `message`.
5. **O elo rascunho-de-nota → orçamento não foi ligado.** A Z5 estava escrevendo o rastro
   (`nfe-rascunhos`) enquanto esta frente rodava, e adivinhar o nome da tabela dela seria chute.
   `orcamento_origem` lê o orçamento em si (`proposals` + `proposal_items`), que é o que o brief
   pede; ligar «esta nota veio daquele orçamento» é **uma linha de SQL** quando a Z5 estiver
   mergeada e o nome da tabela for conhecido.
6. **O gate de módulo não foi reaberto.** As consultas herdam o gate de **diretoria**
   (`user_has_module(user,"fiscal")`), como as outras 17. Quem não tem o módulo fiscal não vê
   nenhuma delas — inclusive na tela, porque a ação passa pela mesma rota.
7. **Nenhuma transmissão à SEFAZ**, em nenhum ambiente. Nada nesta frente fala com o fisco.
8. **A tradução de rejeição tem 7 entradas, não a tabela inteira da SEFAZ.** Elas casam por
   **texto literal** do `xMotivo` e apontam o **campo** a corrigir, nunca o valor. Rejeição sem
   entrada devolve `nao_sei` e manda levar o texto ao contador — decorar códigos de rejeição de
   memória seria a mesma invenção que a frente existe para impedir.

---

## §6 — Como o Jordan testa amanhã

1. Entrar no ERP e abrir **Fiscal** → grupo **«Notas fiscais»** → **«Bartolo — tire sua dúvida»**
   (deep-link: `/redesign/fiscal?t=bartolo-fiscal`).
2. No campo **«Perguntas frequentes»**, escolher **«Por que a NF-e número 2 foi rejeitada?»** e
   clicar **Perguntar ao Bartolo**. Esperado: ele mostra entre aspas o texto que a SEFAZ
   devolveu — *«Rejeicao: Informado NCM inexistente [nItem: 1]»* — o item `SEG-001` com NCM
   `98010000`, e diz que a correção é **no cadastro do produto**, não só na nota.
3. Escolher **«Qual CFOP para venda de material dentro do Amazonas?»**. Esperado **hoje**: ele
   diz **«Não sei»**, repete que o serviço de tributação da Z4 não está no servidor e aponta
   `/redesign/bi?t=decisoes-do-dono`. *Esse é o comportamento certo* — é a prova de que ele não
   inventa CFOP. Depois que a Z4 for para produção, a mesma pergunta passa a devolver o CFOP com
   a norma ao lado.
4. Escrever no campo livre: **«O produto 07622 está pronto para emitir?»**. Esperado: ele separa
   «cadastro fiscal» de «catálogo de compra» e lista o que falta.
5. Escrever algo que a casa não tem, ex.: **«qual o NCM do produto XPTO-999?»**. Esperado:
   «não sei», o que falta, e o ponteiro para o painel. **Nenhum número.**

---

## §7 — Decisões que só o dono pode tomar

1. **CFOP e alíquota de mercadoria enquanto a Z4 não estiver em produção.** Hoje o Bartolo se
   recusa a responder as perguntas 4 e 7. É o certo pela regra que o dono pediu, mas significa
   que, até a Z4 subir, quem precisar desse número tem de perguntar ao contador. **Confirma que
   é assim que quer?**
2. **`products` × `fin_produtos` — os dois cadastros convivem.** Medido: a fita isolante está nos
   dois com o mesmo NCM `39191020`, mas o item `67` do catálogo de compra diz `59061000`
   (capítulo têxtil) para o mesmo produto. E o `VTV-121` está só no catálogo de compra. O Bartolo
   **aponta a divergência** e não escolhe. Unificar os dois cadastros é decisão de dono
   (a frente Z1 levanta a mesma questão no §7 dela).
3. **A NF-e nº 1 está `rejeitada` com o motivo «Lote processado»** — que não é motivo de
   rejeição, é retorno de lote. O Bartolo diz que não sabe a causa e manda levar ao contador.
   Alguém precisa decidir se essas duas notas de teste de 11/04/2026 ficam no acervo ou são
   expurgadas — enquanto ficarem, elas aparecem em toda consulta de NF-e de saída.
4. **As duas notas de 11/04 têm emitente `35.710.481/0001-03` com razão social «JORDAN SANTOS DE
   JESUS LTDA»** e `is_zfm: true`. O Bartolo apontou isso sem decidir. Se o cadastro de emitente
   está com a razão social antiga, ela vai sair impressa no DANFE.
5. **O Bartolo no canal público (WhatsApp).** O `tool_registry` já separa `canais` e as 5
   consultas novas nasceram **só no canal interno** (default fail-closed). Abrir alguma delas ao
   cliente final é decisão do dono — `nfe_saida` e `orcamento_origem` mostram valor e cliente.
