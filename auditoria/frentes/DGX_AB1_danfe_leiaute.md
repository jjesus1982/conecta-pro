# DGX AB1 — O leiaute do DANFE e do DANFSe, no padrão de mercado

**Frente:** AB1 · **Branch:** `dgx/ab1-danfe-padrao` · **Data:** 25/09/2026
**Módulo:** fiscal · **Porta de teste:** 8298 (`teste-dgx-ab1`, parado ao fim)
**Nenhuma nota foi emitida nesta frente** — nem em homologação. Só foram gerados PDFs de notas
que já existiam, e feita **uma leitura** (GET, mTLS) no ADN para buscar o XML de uma NFS-e já
emitida. Nada foi transmitido ao fisco.

---

## §0 — A pergunta do dono, e a resposta que a norma dá

> «…preciso que seja no padrão de mercado, igual a que subi pra você que foi emitida por um
> outro sistema, se sair tudo com nossa cara talvez cause estranheza e descredibilidade…
> se for o caso me manda 3 modelos diferentes»

A intuição está certa, e a razão é mais forte do que ele supõe: **o leiaute do DANFE é
normativo**. Está no Manual de Orientação do Contribuinte da NF-e (MOC), Anexo «Manual de
Especificações Técnicas do DANFE», que fixa blocos, ordem, rótulos e conteúdo mínimo. Um DANFE
«com a nossa cara» não é feio — é **não conforme**. O mesmo vale para o DANFSe v2.0 do Padrão
Nacional da NFS-e.

Por isso **os «3 modelos diferentes» não podem ser 3 inventos.** O que existe de variação
legítima é:

| Forma | Existe na norma? | Entregue? | Por quê |
|---|---|---|---|
| **DANFE retrato** | sim — é a forma padrão do MOC | ✅ `01_danfe_retrato.pdf` | é a forma do DANFE real da empresa (NF-e 10.026) |
| **DANFE paisagem** | sim — mesma norma, mesmos blocos, folha deitada | ✅ `02_danfe_paisagem.pdf` | cabem mais colunas na tabela de itens; sai do **mesmo código**, a geometria é relativa à folha |
| **DANFE simplificado** | sim, mas com **hipótese de uso restrita** (Ajuste SINIEF 07/05 e MOC o admitem em situações específicas, como venda fora do estabelecimento) | ❌ **deliberadamente não** | a operação desta empresa é venda de material a condomínio, com entrega — o simplificado não cabe. Oferecê-lo como «terceiro modelo» seria oferecer uma não conformidade com cara de opção |
| **DANFSe v2.0** | leiaute do Padrão Nacional da NFS-e | ✅ `03_danfse.pdf` | é **outro documento**, não outro leiaute do mesmo — e é o terceiro PDF que o dono recebe para aprovar |

**Resposta curta ao dono:** são dois leiautes de DANFE (retrato e paisagem) e um DANFSe. O
«terceiro modelo» de DANFE que ele imaginou não existe como escolha livre — existe como exceção
legal que não se aplica a ele.

---

## §1 — A comparação campo a campo

### 1.1 DANFE — o real da empresa × o que o Conecta PRO gerava

Gabarito: `uploads/_entrada/NFs/DANFE 10.026 - CONDOMINIO RESIDENCIAL PARQUE DOS FRANCESES 09 2026.pdf`
(emitido em 17/09/2026 pelo `nfemais.com.br`; 6 itens, R$ 2.518,00, CFOP 5405, CST 060, ICMS zero).

Medição: o texto dos dois PDFs foi **extraído** (pymupdf) e comparado. A nota nº 13 do sandbox é
a réplica autorizada dessa NF-e — mesmos 6 itens, mesmo total.

| Bloco / campo do MOC | DANFE real (nfemais) | Conecta PRO **antes** | Conecta PRO **agora** |
|---|---|---|---|
| **Canhoto** — «RECEBEMOS DE …» | ✅ | ❌ **ausente** | ✅ |
| Canhoto — DATA DE RECEBIMENTO | ✅ | ❌ | ✅ |
| Canhoto — IDENTIFICAÇÃO E ASSINATURA DO RECEBEDOR | ✅ | ❌ | ✅ |
| Canhoto — quadro «NF-e / Nº / SÉRIE» ao lado | ✅ | ❌ | ✅ |
| **Emitente** — razão social | ✅ `CONECTAMAIS ELETRONICA LTDA` | ⚠️ saía o **nome fantasia** («CONECTA MAIS ELETRÔNICA») | ✅ razão social do XML |
| Emitente — endereço, bairro, município/UF | ✅ | ❌ **ausente** | ✅ |
| Emitente — CEP e FONE | ✅ | ❌ | ✅ |
| Emitente — logotipo | ❌ (o nfemais não põe) | ⚠️ banner de marca | ✅ discreto, dentro da caixa do emitente (o MOC admite) |
| Texto «Consulta de autenticidade no portal nacional…» | ✅ | ❌ | ✅ |
| **Bloco DANFE** — título + «DOCUMENTO AUXILIAR DA NOTA FISCAL ELETRÔNICA» | ✅ | ⚠️ só o título | ✅ |
| **0 - ENTRADA / 1 - SAÍDA** com o quadrinho do `tpNF` | ✅ | ❌ **ausente** | ✅ |
| Nº no formato `000.010.026` | ✅ | ❌ saía `13` | ✅ |
| **FOLHA x/y** | ✅ | ❌ **ausente** | ✅ |
| **Chave de acesso** formatada em grupos de 4 | ✅ | ✅ | ✅ |
| Código de barras **Code-128C** | ✅ | ⚠️ existia, sem conferência | ✅ conferido: 277 módulos + zonas mudas |
| **PROTOCOLO DE AUTORIZAÇÃO DE USO** — número **e data/hora** | ✅ `113263811849419 - 17/09/2026 10:48:26` | ⚠️ **só o número** | ✅ |
| NATUREZA DA OPERAÇÃO | ✅ | ✅ | ✅ |
| **INSCRIÇÃO ESTADUAL do emitente** | ✅ `054265746` | ❌ **ausente** | ✅ |
| **INSCRIÇÃO ESTADUAL DO SUBST. TRIB.** | ✅ | ❌ | ✅ |
| CNPJ do emitente na linha da IE | ✅ | ❌ | ✅ |
| **DESTINATÁRIO/REMETENTE** — nome, CNPJ | ✅ | ✅ | ✅ |
| Destinatário — DATA DA EMISSÃO | ✅ | ❌ | ✅ |
| Destinatário — **BAIRRO/DISTRITO** em campo próprio | ✅ | ⚠️ colado no endereço | ✅ |
| Destinatário — **DATA DA SAÍDA/ENTRADA** | ✅ | ❌ | ✅ |
| Destinatário — **FONE/FAX** | ✅ | ❌ | ✅ |
| Destinatário — **HORA DA SAÍDA** | ✅ | ❌ | ✅ |
| Destinatário — CEP, UF, IE | ✅ | ✅ | ✅ |
| **FATURA / DUPLICATAS** | — (omitido: nota à vista) | ❌ | ✅ **quando há duplicata**; omitido quando não há, como no gabarito |
| **CÁLCULO DO IMPOSTO** — BC ICMS | ✅ | ❌ | ✅ |
| — VALOR DO ICMS | ✅ | ✅ | ✅ |
| — **BC ICMS ST** | ✅ | ❌ | ✅ |
| — **VALOR DO ICMS SUBSTITUIÇÃO** | ✅ | ❌ | ✅ |
| — **VALOR TOTAL DO IPI** | ✅ | ❌ | ✅ |
| — VALOR TOTAL DOS PRODUTOS | ✅ | ✅ | ✅ |
| — VALOR DO FRETE | ✅ | ✅ | ✅ |
| — **VALOR DO SEGURO** | ✅ | ❌ | ✅ |
| — DESCONTO | ✅ | ✅ | ✅ |
| — **OUTRAS DESPESAS ACESSÓRIAS** | ✅ | ❌ | ✅ |
| — VALOR PIS / VALOR COFINS | ✅ | ⚠️ **recalculados** (41,54) | ✅ **do XML** (41,56) |
| — VALOR TOTAL DA NOTA | ✅ | ✅ | ✅ |
| **TRANSPORTADOR / VOLUMES** — bloco inteiro (razão social, frete por conta, ANTT, placa, UF, CNPJ, endereço, município, IE, quantidade, espécie, marca, numeração, peso bruto, peso líquido) | ✅ | ❌ **bloco inexistente** | ✅ |
| **PRODUTOS** — CÓDIGO, DESCRIÇÃO, NCM, CFOP, UN, QUANT, V.UNIT, V.TOTAL | ✅ | ✅ | ✅ |
| Produtos — **CST** | ✅ `060` | ❌ | ✅ |
| Produtos — **BC ICMS / V.ICMS / V.IPI / %ICMS / %IPI** | ✅ | ❌ **5 colunas ausentes** | ✅ |
| Produtos — descrição longa | quebra de linha | ⚠️ cortada | ✅ quebra em várias linhas |
| Produtos — **todos os itens** | ✅ | ❌ truncava: «… e mais N item(ns) — veja o XML» | ✅ pagina (provado com 80 itens → 3 páginas) |
| **CÁLCULO DO ISSQN** | — (omitido: sem serviço) | ❌ | ✅ **quando a nota tem serviço** |
| **DADOS ADICIONAIS** — INFORMAÇÕES COMPLEMENTARES | ✅ | ⚠️ caixa única | ✅ |
| **RESERVADO AO FISCO** | ✅ | ❌ **ausente** | ✅ |
| Tarja «SEM VALOR FISCAL» em homologação | n/a (nota real) | ✅ | ✅ **mantida** |
| Rodapé de marketing (0800, Instagram, site) | ❌ | ⚠️ **presente** | ✅ removido |

**O defeito mais grave da lista não é nenhum bloco ausente.** É esta linha: o PDF dizia
**PIS R$ 41,54** e o XML que a SEFAZ autorizou diz `<vPIS>41.56</vPIS>`. Dois centavos, mas é
o documento auxiliar **discordando do documento fiscal** — porque o DANFE recalculava os totais
a partir dos itens em vez de representar a nota. Agora, sempre que existe `xml_autorizado`,
**tudo** sai do XML.

### 1.2 DANFSe — os 9 do portal × o que o Conecta PRO gerava

Gabarito: os 9 PDFs em `uploads/_entrada/NFs/` (NFS 27–31, 116, 119, 120, 121), gerados pelo
**portal do fisco**, leiaute DANFSe v2.0. O confronto detalhado foi feito contra a **NFS-e 121**
(CONDOMINIO RESIDENCIAL PARQUE DOS FRANCESES, 09/2026, R$ 1.800,00).

| Bloco / campo do v2.0 | Portal | Conecta PRO **antes** | Conecta PRO **agora** |
|---|---|---|---|
| Canhoto «DATA CIENTIFICAÇÃO / IDENTIFICAÇÃO E ASSINATURA» | ✅ | ❌ | ✅ |
| Canhoto «Nº NFS-e / CHAVE NFS-e» | ✅ | ❌ | ✅ |
| Título «DANFSe v2.0 / Documento Auxiliar da NFS-e» | ✅ | ⚠️ «DANFSe — … Padrão Nacional» | ✅ |
| Município / **Ambiente Gerador** / **Tipo de Ambiente** | ✅ | ❌ | ✅ |
| CHAVE DE ACESSO DA NFS-e (50 dígitos) | ✅ | ✅ (no rodapé) | ✅ (no cabeçalho, como o portal) |
| **QR Code** de verificação | ✅ | ❌ **ausente** | ✅ — `https://www.nfse.gov.br/ConsultaPublica?tpc=1&chave=…` (**decodificado do PDF do portal**, não suposto) |
| NÚMERO / COMPETÊNCIA / DATA E HORA DA EMISSÃO | ✅ | ⚠️ parcial | ✅ |
| **NÚMERO DA DPS / SÉRIE DA DPS / DATA E HORA DA DPS** | ✅ `125 / 70000` | ❌ | ✅ |
| EMITENTE DA NFS-e / **SITUAÇÃO** / **FINALIDADE** | ✅ | ❌ | ✅ |
| Prestador — CNPJ, Indicador Municipal, Nome | ✅ | ✅ | ✅ |
| Prestador — **Telefone, Município/UF, IBGE/CEP, Endereço, E-mail** | ✅ | ❌ | ✅ |
| Prestador — **Simples Nacional / Regime de apuração** | ✅ | ❌ | ✅ |
| Tomador — CNPJ, Nome | ✅ | ✅ | ✅ |
| Tomador — **Indicador municipal, telefone, município/UF, IBGE/CEP, endereço, e-mail** | ✅ | ❌ | ✅ |
| Linhas «DESTINATÁRIO / INTERMEDIÁRIO não identificado» | ✅ | ❌ | ✅ |
| **Código de Tributação Nacional/Municipal** | ✅ `14.01.01 / 100` | ❌ | ✅ |
| **Código da NBS** | ✅ `1.2001.89.00` | ❌ | ✅ |
| **Local da Prestação / UF** | ✅ | ❌ | ✅ |
| Texto do código de tributação (`xTribNac`) | ✅ | ⚠️ cortado em 80 caracteres | ✅ |
| Descrição do Serviço | ✅ | ✅ | ✅ |
| **TRIBUTAÇÃO MUNICIPAL (ISSQN)** — tipo, município de incidência, BC, alíquota, **retenção**, ISSQN apurado | ✅ | ⚠️ só BC e ISSQN, sem rótulo de bloco | ✅ |
| **TRIBUTAÇÃO FEDERAL** — IRRF, contrib. previdenciária, contribuições sociais, PIS, COFINS, descrição da retenção | ✅ `IRRF 18,00 · CS 18,00 · «8 - PIS/COFINS Não Retidos, CSLL Retido»` | ❌ **bloco inexistente** | ✅ |
| **TRIBUTAÇÃO IBS/CBS** — CST/cClassTrib, indicador de operação, exclusões, BC após exclusões, alíquotas IBS UF/mun, alíquotas efetivas, valores apurados, CBS | ✅ | ❌ **bloco inexistente** | ✅ |
| VALOR TOTAL — operação, descontos, **total das retenções**, **valor líquido**, **total IBS/CBS**, **líquido + IBS/CBS** | ✅ | ⚠️ 5 linhas soltas | ✅ |
| INFORMAÇÕES COMPLEMENTARES (Lei 12.741/2012) | ✅ | ❌ | ✅ |
| Rodapé de marketing | ❌ | ⚠️ presente | ✅ removido |

**Onde estava o dado.** `nfse_emitidas_nacional` guarda 12 campos estruturados e **nenhum XML** —
metade dos blocos do v2.0 simplesmente não existia no ERP. A rota passou a buscar a NFS-e
assinada no ADN (`GET /nfse/{chave}`, leitura pura, mTLS) e a guardá-la em `xml_nfse`.
Confirmado em produção: a NFS-e 121 voltou com **7.547 caracteres** de XML assinado, e o DANFSe
gerado bate campo a campo com o do portal.

**Achado de infraestrutura:** `"danfse": "/nfse/DANFSe/{chave}"` estava declarado no `ENDPOINTS`
do manager nacional desde sempre e **não é rota** — devolve 404 `text/html` com a página do IIS
(o «404 que mente» já documentado no próprio arquivo). Nenhum método a usava. Entrada removida,
com a lição escrita no lugar. **O fisco não serve o PDF por API; serve o XML.**

---

## §2 — O que foi feito

| Arquivo | O quê |
|---|---|
| `backend/modules/fiscal/services/danfe_layout.py` **(novo, 952 linhas)** | o leiaute normativo do DANFE: grade de caixas em frações da folha (é isso que faz retrato e paisagem saírem do mesmo código), leitura completa do `nfeProc`, paginação de verdade, Code-128C, tarja |
| `backend/modules/gedeon/services/nfse_danfse_generator.py` **(reescrito)** | DANFSe v2.0 completo: `parse()` lê os ~68 campos do v2.0 da NFS-e assinada; `_render_danfse()` desenha os 12 blocos; QR Code; `garantir_coluna_xml()` (DDL idempotente) |
| `backend/modules/operacional/controllers/redesign_builders/_dgx_z3_tela_nfe.py` | `danfe_pdf()` virou 3 linhas delegando ao leiaute; a rota ganhou `?orientacao=retrato\|paisagem`. **A regra da tarja continua aqui** (`precisa_faixa_sem_valor_fiscal`) — não foi duplicada |
| `backend/modules/financial/controllers/fiscal_controller.py` | a rota do DANFSe garante a coluna, busca o XML no ADN na 1ª impressão e o guarda; falha de rede/certificado **não** derruba a impressão |
| `backend/modules/government_integrations/core/nfse_nacional.py` | removida a entrada morta `danfse` do `ENDPOINTS` (5 linhas de comentário no lugar) |
| `backend/scripts/orq/test_oraculo_ab1_danfe_leiaute.py` **(novo)** | o oráculo |

**Rotas** (nenhuma mudou de caminho):

* `GET /api/v1/redesign/nfe/{nfe_id}/danfe/pdf` — **novo parâmetro** `?orientacao=retrato|paisagem`
  (padrão `retrato`; o front não precisa mudar nada para continuar funcionando).
* `GET /api/v1/financial/fiscal/nfse-emitida/{chave}/danfse` — mesma URL, DANFSe v2.0.

**DDL que `garantir_coluna_xml` aplica em produção no 1º acesso:**

```sql
ALTER TABLE nfse_emitidas_nacional ADD COLUMN IF NOT EXISTS xml_nfse TEXT;
```

Nada mais. Nenhum DROP, nenhum UPDATE em dado que a frente não criou.

---

## §3 — Amostras para o dono aprovar

Em `/opt/conecta-pro/uploads/_saida/danfe_modelos/`, **geradas pelas rotas reais** (porta 8298),
a partir de notas **que já existiam**:

| Arquivo | Nota | O que é |
|---|---|---|
| `01_danfe_retrato.pdf` | NF-e nº 13, série 1, homologação — a **réplica autorizada da NF-e 10.026 real** (6 itens, R$ 2.518,00, CFOP 5405, CST 060) | A4 retrato — a forma padrão do MOC |
| `02_danfe_paisagem.pdf` | a mesma nota | A4 paisagem — a outra forma prevista |
| `03_danfse.pdf` | **NFS-e 121 REAL**, de produção (CONDOMINIO RESIDENCIAL PARQUE DOS FRANCESES, 09/2026, R$ 1.800,00) | DANFSe v2.0, a partir da NFS-e assinada pelo fisco |

Os dois DANFE saem com a tarja **SEM VALOR FISCAL / AMBIENTE DE HOMOLOGAÇÃO** atravessando a
página — como devem, porque a nota é de homologação. **Em produção, nota autorizada, a tarja
não aparece.** O DANFSe não tem tarja porque a NFS-e 121 é real.

Comando para o dono baixar:

```bash
scp -r root@82.25.75.74:/opt/conecta-pro/uploads/_saida/danfe_modelos/ ~/Downloads/
```

---

## §4 — Oráculo

`backend/scripts/orq/test_oraculo_ab1_danfe_leiaute.py`

Afirma, para **toda nota autorizada com XML no banco** (não para uma escolhida a dedo, e sem
entregar item nenhum na mão — os dados são carregados pelo caminho de produção,
`carregar_nota` → `danfe_pdf`): (a) os 46 blocos/rótulos obrigatórios do MOC estão no PDF ·
(b) chave, protocolo, natureza, IE do emitente, os 5 totais do `ICMSTot` e, item a item, NCM,
CFOP e `vProd` **batem com o XML**, recontados por parsing próprio (regex), não pelo módulo sob
teste · (c) nenhum item some — incluindo um caso de **80 itens** que força 3 páginas, com
`FOLHA n/N` coerente em todas · (d) o código de barras usa **subset C** · (e) não há rodapé de
marketing dentro do documento fiscal · (f) a tarja continua · (g) o DANFSe traz os 34 blocos do
v2.0 e os valores batem com a NFS-e assinada (vServ, vBC, pAliqAplic, vISSQN, vTotalRet, vLiq,
vIBSUF, vCBS) · (h) o **QR é decodificado do PDF gerado** e tem de apontar para a consulta
pública com a chave daquela nota — conferir o QR lendo o código-fonte não prova nada.

**VERMELHO** (código anterior à frente, `78ce4a58f`, mesmo oráculo, mesmo banco):

```
$ docker run --rm --network conecta-staging-network -v "$SP/antes/backend:/app:ro" … \
    python3 /app/scripts/orq/test_oraculo_ab1_danfe_leiaute.py
DANFEs conferidos contra o XML: 4 · DANFE de 80 itens: 0 páginas
  ✗ (a) nota 8/retrato: bloco/rótulo ausente no DANFE — «RECEBEMOS DE»
  ✗ (a) nota 8/retrato: bloco/rótulo ausente no DANFE — «TRANSPORTADOR / VOLUMES TRANSPORTADOS»
  ✗ (a) nota 8/retrato: bloco/rótulo ausente no DANFE — «RESERVADO AO FISCO»
  … (142 falhas de bloco ausente, 8 notas × retrato + a paisagem inexistente)
  ✗ (b) nota 13/retrato: total vPIS=41,56 do XML não aparece no PDF
        (o DANFE está recalculando em vez de representar a nota)
  ✗ (b) nota N/retrato: IE do emitente «054265746» do XML não está no PDF
  ✗ (c) leiaute normativo ausente — No module named 'modules.fiscal.services.danfe_layout'
  ✗ (e) nota N/retrato: rodapé de marketing «@conectamaisoficial» dentro do DANFE
  ✗ (g) DANFSe: bloco/rótulo ausente — «TRIBUTAÇÃO FEDERAL» … (41 falhas)
  ✗ (h) DANFSe: QR lido «» ≠ consulta pública da chave «https://www.nfse.gov.br/ConsultaPublica?...»
TOTAL desvios AB1: 207
```

Por item: **(a) 142 · (b) 5 · (c) 5 · (e) 12 · (g) 42 · (h) 1**.

**VERDE** (depois):

```
$ docker exec -e PYTHONPATH=/app teste-dgx-ab1 \
    python3 /app/scripts/orq/test_oraculo_ab1_danfe_leiaute.py
DANFEs conferidos contra o XML: 8 · DANFE de 80 itens: 3 páginas
OK DANFE/DANFSe: blocos do MOC e do v2.0 completos, valores iguais aos do XML,
nenhum item truncado, barras em subset C, QR na consulta pública, sem marketing.
TOTAL desvios AB1: 0
```

**Regressão do vizinho** — o oráculo da frente Z3, que também exercita `danfe_pdf`:

```
TOTAL falhas Z3: 0
OK NF-e: padrão homologação travado, recusa que ensina (NCM/destinatário/CFOP),
DANFE de homologação com SEM VALOR FISCAL, cancelamento com 15+ caracteres, xMotivo inteiro na lista.
```

Importadores do gerador de DANFSe (kits GEDEON, portal, NFS-e de entrada, controller fiscal e o
manager nacional) conferidos um a um por import real dentro do container: **todos OK**.
`ruff check` nos 6 arquivos: **All checks passed**.

---

## §5 — O que NÃO foi feito, e por quê

1. **DANFE Simplificado.** Existe na norma, mas com hipótese de uso restrita, e a operação da
   empresa não é uma delas (§0). Entregar três opções onde uma é errada é pior que entregar duas.
2. **DANFE etiqueta / DANFE de NFC-e (modelo 65).** A empresa não emite NFC-e. Fora do escopo.
3. **Nenhuma nota foi emitida.** Nem em homologação. A produção fiscal está LIGADA — o risco de
   um documento real e irreversível não se corre para testar leiaute. Todos os PDFs saíram de
   notas que já existiam.
4. **O endereço do emitente não foi corrigido.** É dado, não código, e é decisão do dono (§6.1).
5. **`xTribMun` não é impresso** separado de `xTribNac` — no gabarito os dois vêm com o mesmo
   texto e imprimir duas vezes a mesma frase gastaria 3 linhas por nada. Se algum município
   passar a divergir, é uma linha a acrescentar.
6. **A tabela de `tpRetPisCofins` não foi inventada.** Só o código **8** está medido (é o das
   notas desta empresa, lido do DANFSe do portal). Código sem descrição conhecida sai como
   código, não como descrição chutada.
7. **O XML da NFS-e só é buscado sob demanda**, quando alguém imprime o DANFSe. Não foi feito
   backfill dos 116 registros de `nfse_emitidas_nacional` — isso é trabalho de conciliação
   (frente AA4), não de leiaute, e 116 chamadas ao ADN merecem ser agendadas, não disparadas
   por uma frente de PDF.
8. **Nada foi feito no front.** As duas rotas mantêm o caminho antigo e o `?orientacao=` é
   opcional; o botão «DANFE (PDF)» que já existe continua funcionando e traz o retrato. Se o
   Jordan quiser o botão de paisagem na tela, é acrescentar um `doc(...)` com
   `?orientacao=paisagem` no builder — o orquestrador faz, eu não toco em `frontend/`.
9. **Sem XSD do DANFSe.** Como na frente Z2, não há pacote de schemas no repositório. A prova
   aqui é a comparação com os 9 DANFSe que o próprio fisco gerou.

---

## §6 — Decisões que só o dono pode tomar

### 6.1 — O endereço da empresa no ERP não é o endereço que o fisco tem ⚠️

Este é o achado mais importante desta frente, e não é sobre desenho.

| Fonte | Endereço | CEP | Telefone |
|---|---|---|---|
| **DANFE real** (nfemais, 17/09/2026) | Nova Palestina, 51 — Crespo, Manaus/AM | 69073488 | — |
| **DANFSe do portal** (NFS-e 121, o fisco) | RUA NOVA PALESTINA, 51, CRESPO | 69.073-488 | (92) 9348-5518 |
| **`empresas` do Conecta PRO** (produção e sandbox) | **Avenida Constantino Nery, 3343 — Chapada** | **69050001** | **(92) 3221-2100** |

A NF-e nº 13 que o ERP autorizou na SEFAZ em 24/09 **foi assinada com o endereço da Constantino
Nery** — o XML está lá, é possível conferir. Quer dizer: **as notas do Conecta PRO saem com um
endereço diferente das notas do nfemais e das NFS-e do portal.** O DANFE está certo (mostra o
que está no XML); o cadastro é que diverge.

**Qual dos dois é o endereço fiscal da CONECTAMAIS ELETRONICA LTDA hoje?** Se for a Nova
Palestina, é preciso corrigir `empresas.endereco_*` **antes** da primeira NF-e de produção — e
avaliar o que fazer com a nº 13, que já foi autorizada em homologação com o endereço errado.
Se for a Constantino Nery, é o cadastro do fisco (NFS-e) que está desatualizado.

### 6.2 — Logotipo no DANFE: sim ou não?

O DANFE real da empresa (nfemais) **não tem logotipo**. O MOC **permite** o logotipo na caixa de
identificação do emitente, e é o que a maioria dos ERPs faz. Entreguei com o logotipo discreto
dentro dessa caixa — em nenhum outro lugar do documento. Se o dono quiser **idêntico ao
nfemais**, é trocar um parâmetro (`logo=False`) e o documento sai sem nenhuma marca. **Qual ele
prefere?**

### 6.3 — Retrato ou paisagem como padrão do botão?

Hoje o botão «DANFE (PDF)» da tela traz o **retrato** (é o que o nfemais usa, e é o que o
cliente dele já conhece). A paisagem está acessível por `?orientacao=paisagem`. Vale um botão
separado na tela, ou o retrato basta?

### 6.4 — Backfill do XML das 116 NFS-e já emitidas

O DANFSe completo depende do XML assinado, que o ERP não guardava. A rota passa a buscá-lo na
primeira impressão de cada nota. As 116 já emitidas só ficam completas quando alguém as abrir —
ou se o dono autorizar um backfill agendado (116 leituras no ADN, sem emitir nada). **Autoriza?**
Isso pertence naturalmente à frente de conciliação (AA4).

### 6.5 — Kits do GEDEON entregues ao cliente

Os kits documentais montam DANFSe pelo mesmo gerador. A partir desta frente, o DANFSe que vai
ao condomínio é o leiaute v2.0 — mais parecido com o que ele receberia do portal, e sem o
rodapé de marketing. **Confirma que é isso que ele quer ver no kit?** (A alternativa seria
manter o resumo antigo, que era bonito e não era um DANFSe.)

---

## §7 — Como o Jordan testa amanhã

```bash
# 1. baixar as 3 amostras
scp -r root@82.25.75.74:/opt/conecta-pro/uploads/_saida/danfe_modelos/ ~/Downloads/

# 2. abrir lado a lado com a nota de verdade:
#    uploads/_entrada/NFs/DANFE 10.026 … .pdf   ×   01_danfe_retrato.pdf
#    uploads/_entrada/NFs/NFS 121 … .pdf        ×   03_danfse.pdf

# 3. na tela: Fiscal → NF-e → uma nota autorizada → botão «DANFE (PDF)»
#    a mesma nota em paisagem:
#    /api/v1/redesign/nfe/<id>/danfe/pdf?orientacao=paisagem

# 4. DANFSe de qualquer nota emitida (a chave está na lista do fiscal):
#    /api/v1/financial/fiscal/nfse-emitida/<chave>/danfse
#    (a 1ª abertura de cada nota demora ~2 s: é ela buscando o XML no fisco e guardando)
```

O que olhar, em ordem: o canhoto no topo · o endereço do emitente (é a pergunta do §6.1) ·
a linha do protocolo com data e hora · as 14 colunas da tabela de itens · o bloco do
transportador · «RESERVADO AO FISCO» no rodapé · e a ausência do 0800 e do Instagram.
