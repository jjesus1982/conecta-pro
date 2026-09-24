# DGX Z2 — UM emissor de NF-e, provado em HOMOLOGAÇÃO

**Frente:** Z2 (onda 8) · **Branch:** `dgx/z2-emissor-nfe` · **Data:** 24/09/2026
**Módulo:** fiscal · **Porta de teste:** 8282 (`teste-dgx-z2`, parado ao fim)
**Ambiente de toda a frente:** HOMOLOGAÇÃO (`tpAmb = 2`). **Nenhuma transmissão em produção.**

---

## §1 — A escolha, medida

Havia DOIS emissores de NF-e e **zero notas autorizadas** em toda a história do sistema.

### O que cada um tinha (medido, não lido)

| | **A** — `fiscal_contabil/notas_fiscais/nfe/controller.py` | **B** — `financial/integrations/nfe_provider.py` |
|---|---|---|
| Linhas | 476 | 529 |
| Rotas expostas | **0** — `grep -c "@router"` = 0. O router estava montado em `main_production.py:976` e não tinha um único endpoint (apagados em `61a1d9519`) | 0 (nunca teve router) |
| Chamadores | só os 2 `include_router` + o `__init__` do pacote | **nenhum** fora de `tests/` |
| Ambiente | `tpAmb` chumbado **`"1"`** no XML (linha 205) e `homologacao=False` na transmissão (linha 395) — **não emitia em homologação nem se quisesse** | `tpAmb` por config, default homologação |
| Numeração | `_prox_numero(serie)` **ignora a série** e devolve `int(time.time()) % 1_000_000_000` — número de nota por timestamp: buraco permanente e garantido na numeração fiscal | nenhuma — `numero` é parâmetro de entrada |
| Emitente | 12 constantes chumbadas, com `EMITENTE_IE = "45177801"` — que é a inscrição **MUNICIPAL**, não a estadual | dict `_EMITENTE` chumbado, `"ie": ""` (vazia) e endereço "Rua dos Andrades, 1000, Centro" — **divergente do A** |
| Leiaute | montado à mão com lxml; completo para 4.00 mas **sem o grupo IBS/CBS** da NT 2025.002 | via PyNFe; **sem** IBS/CBS |
| Retorno da SEFAZ | lê `infProt` por XPath com namespace | `_parse_sefaz_xml` com regex **sem** prefixo → cega para `<ns0:cStat>`, que é como a SEFAZ-AM devolve o protNFe |
| Cancelamento | não tem | tem (110111), mas mandava o `envEvento` inteiro para um método que monta o `envEvento` sozinho |
| Inutilização | não tem | não tem |
| Persistência / guarda do XML | não tem (os endpoints que gravavam foram apagados) | não tem |
| Roda? | não foi possível provar — nunca teve rota | **não**: 6 chamadas erradas da API do PyNFe 0.6.5, todas medidas (ver abaixo) |

### Os defeitos do B, um a um, medidos contra a SEFAZ-AM

Cada linha abaixo é um `AttributeError` ou uma rejeição real de 24/09/2026:

1. `nf.destinatario_remetente = cli` → o serializador lê `nf.cliente` · `AttributeError`
2. `nf.identificador_unico = f"NFe{chave}"` → é `@property` sem setter · `AttributeError`
3. `adicionar_pagamento(forma_pagamento=, valor=)` → a entidade quer `t_pag=`, `v_pag=` · `vPag - Valor requerido`
4. `cli.tipo_documento = "PJ"` → gera a tag `<PJ>` · rejeição **215** (esperava CNPJ/CPF)
5. `nf.serie = "001"` e `nf.numero_nf = "000000001"` → rejeição **215** (`TSerie`/`TNF` não aceitam zero à esquerda; o padding existe só na chave)
6. `pis_modalidade=""` → `<CST/>` vazio · rejeição **215**; no PyNFe é `pis_modalidade` que vira o CST, `pis_situacao_tributaria` é ignorado

E mais três que faltavam nos dois: `infRespTec` (rejeição **972**), `cEAN = "SEM GTIN"` (rejeição **883**) e o grupo **IBS/CBS** (rejeição **1115**).

### A decisão

**Fica o B (PyNFe); o A é aposentado e o arquivo foi apagado.**

Três fatos, não preferência:

1. **O A não pode emitir em homologação.** `tpAmb="1"` no XML e `homologacao=False` na transmissão são constantes, não configuração. Sob a regra desta frente — nada sai em produção — o A é inutilizável por construção, e pior: qualquer rota nova nele emitiria nota real sem querer.
2. **O A tinha 0 rotas.** Aposentar custa apagar um arquivo e trocar dois `import`. Aposentar o B custaria reescrever o A inteiro, que já nasce com o defeito do item 1.
3. **O caminho do B foi o que autorizou.** A esteira serializar → assinar → transmitir → ler protocolo do PyNFe foi levada de ponta a ponta contra a SEFAZ-AM e devolveu `cStat 100`. O caminho do A nunca foi exercido por ninguém, nunca.

### O rito de aposentadoria

```
grep -rn "notas_fiscais.nfe.controller|notas_fiscais.nfe import controller" --include=*.py .
  backend/main_production.py:976                              → aponta para .emissor
  backend/modules/fiscal_contabil/__init__.py:40              → aponta para .emissor
  backend/modules/fiscal_contabil/notas_fiscais/nfe/__init__.py:9 → aponta para .emissor
  backend/tests/multicnpj_release/test_cnpj_guardrail.py:49   → entrada da baseline removida
```
Varredura ampliada (`_gerar_chave`, `_calcular_dv_modulo11`, `_prox_numero`, `_gerar_xml_nfe`,
`_assinar_nfe`, `_submeter_sefaz`, `nfe_emissao_router`) no backend inteiro, incluindo tools do
MCP e builders do redesign: **nenhum outro chamador**. A rota pública `/fiscal/nfe/emitir` foi
**mantida no mesmo path** — o front e o OpenAPI gerado não mudam.

Prova de import depois da poda: o backend sobe e loga
`NF-e Produto: OK (emitir + cancelar + inutilizar + listar + sefaz-status)`; o item (g) do
oráculo varre `/app` inteiro e confirma zero importadores e o arquivo ausente.

### De onde vinha «JORDAN SANTOS DE JESUS LTDA»

As duas tentativas de 11/04/2026 gravaram a razão social **antiga**. A origem é dupla:

- **imediata:** `git show 1bab9f4de:…/nfe/controller.py:40` → `EMITENTE_RAZAO_SOCIAL = "JORDAN SANTOS DE JESUS LTDA"`, constante chumbada. Foi corrigida depois no código, mas as linhas de `nfes` ficaram com o valor velho.
- **de raiz:** o **certificado A1 da Eletrônica** ainda carrega a razão antiga no subject:
  `CN=JORDAN SANTOS DE JESUS LTDA:35710481000103` (emitido 13/01/2026, válido até 13/01/2027).
  O mesmo já estava documentado em `modules/signatures/services/qualified_signer.py:129`.
  Quem copiou o nome do certificado copiou um nome vencido.

Agora a razão social vem de `empresas.razao_social` (`CONECTAMAIS ELETRONICA LTDA`), e o XML
autorizado de hoje traz `<xNome>CONECTAMAIS ELETRONICA LTDA</xNome>`.

---

## §2 — O emissor completo

**Arquivos**

| Arquivo | O quê |
|---|---|
| `backend/modules/financial/integrations/nfe_provider.py` (reescrito) | diálogo com a SEFAZ: leiaute 4.00 + IBS/CBS, assinatura A1, transmissão, leitura de retorno, cancelamento 110111, inutilização, **as duas travas de produção** |
| `backend/modules/fiscal_contabil/notas_fiscais/nfe/emissor.py` (novo) | numeração, persistência, guarda do XML, régua fiscal, 5 endpoints |
| `backend/modules/fiscal_contabil/notas_fiscais/nfe/controller.py` | **apagado** |
| `backend/scripts/orq/test_oraculo_z2_emissor_nfe.py` (novo) | o oráculo |

**Chave de acesso com DV** — `montar_chave()`: `cUF|AAMM|CNPJ|55|serie(3)|nNF(9)|tpEmis|cNF(8)` + DV
módulo 11. O padding existe **só** na chave; nas tags `<serie>`/`<nNF>` ele é rejeição 215.
O DV é recalculado por fora no item (a) do oráculo.

**Numeração por CNPJ + série + ambiente, sem buraco**

```sql
CREATE UNIQUE INDEX ux_nfes_emitente_serie_numero ON nfes (emitente_cnpj, serie, numero, tp_amb)
CREATE TABLE nfe_numeracao (emitente_cnpj, serie, tp_amb, ultimo, PRIMARY KEY (…))
```
`proximo_numero()` é um `INSERT … ON CONFLICT DO UPDATE SET ultimo = GREATEST(…)+1 RETURNING` —
uma ida ao banco, linha travada, atômico. Duas emissões concorrentes recebem números diferentes
e consecutivos (item (c) do oráculo). O `GREATEST` também considera `MAX(numero)` de `nfes` e
`MAX(numero_final)` das faixas inutilizadas, então um contador que nasce depois das notas não
repete número.

O número é reservado **antes** de ir à SEFAZ e nunca volta atrás. Se a transmissão falhar,
`_registrar_falha()` grava a linha mesmo assim — sem isso o número some e vira buraco invisível
(foi exatamente o que aconteceu com o nº 3 aqui, por um `AmbiguousParameterError`; a linha hoje
existe com o motivo escrito).

**Leiaute vigente** — PyNFe 0.6.5 serializa o 4.00, e `injetar_ibscbs()` acrescenta o grupo
`IBSCBS` por item e o `IBSCBSTot` no total (NT 2025.002, transição 2026: IBS-UF 0,1% ·
IBS-Mun 0,0% · CBS 0,9%). A árvore que o PyNFe devolve antes da assinatura **não tem namespace**
(o `xmlns` é atributo literal) — as tags entram sem prefixo.

**Assinatura com o A1 da empresa certa** — `_provider_para()` usa o registro único de
`qualified_signer` (`CERT_A1_PATH`/`CERT_A1_PASSWORD` para a Eletrônica,
`CERT_A1_PATH_PATRIMONIAL`/`CERT_A1_PASSWORD_PATRIMONIAL` para a Patrimonial). A senha só vem de
env e nunca é logada.

**Tributação** — o emissor **não** escolhe alíquota. `_tributar()` chama
`modules/fiscal/services/tributacao_nfe.calcular_puro` (frente Z4), que devolve CFOP, CST/CSOSN,
base, alíquota e as mensagens fiscais com norma e origem de cada número. `bloqueios` não vazio é
recusa. O item (h) do oráculo trava isso por AST: nenhum `cfop=`/`icms_modalidade=`/
`icms_aliquota=` literal em `nfe_provider.py`. Resultado na nota autorizada: CFOP **5102**,
CST **00**, ICMS **20%** (operação interna do AM — as duas empresas ficam DENTRO da ZFM, então o
Convênio ICM 65/88 não se aplica a elas), PIS **1,65%** CST 01, COFINS **7,60%** CST 01.

**Retorno da SEFAZ** — `_parse_sefaz_xml` aceita prefixo (`<ns0:cStat>`) e o **último** valor
vence: numa resposta de lote o `protNFe` vem depois do `104 Lote processado`. Lê `cStat`,
`xMotivo`, `nProt`, `chNFe`, `dhRecbto`, `tpAmb`.

**Guarda de 5 anos** — o `nfeProc` (NFe assinada + protNFe) vai para
`$NFE_XML_DIR/<cnpj>/<AAMM>/<chave>-proc.xml` (default `/app/uploads/nfe`, que é bind do host) e
o caminho fica em `nfes.xml_path`; o XML também fica em `nfes.xml_autorizado`. Cancelamento e
inutilização gravam `-cancelamento.xml` / `-inutilizacao.xml` e linha em `nfe_eventos`.

**A trava de produção (duas camadas + gate humano)**

1. `_exigir_ambiente(tp_amb, …)` no **começo** de `emitir`/`cancelar`/`inutilizar` — antes de
   reservar número. Produção só passa com `NFE_PRODUCAO_LIBERADA` valendo a frase-senha exata
   (env setada como "1"/"true" **não** abre).
2. `_conferir_tp_amb(xml, ambiente, …)` relê o `<tpAmb>` do XML assinado imediatamente antes do
   POST. XML sem `tpAmb`, com `tpAmb` divergente do pedido, ou com `tpAmb=1` sem o gate: nada é
   transmitido.

Prova de ponta a ponta com `NFE_AMBIENTE=1` e o gate fechado:
```
NFE_AMBIENTE = 1 · ambiente_atual() = 1
RECUSADO: PRODUCAO_TRAVADA · Emissão de NF-e em PRODUÇÃO bloqueada…
depois: notas tp_amb=1: 0 · contadores tp_amb=1: 0
```

---

## §3 — As notas em homologação

### CONECTAMAIS ELETRONICA LTDA — **AUTORIZADA** ✅

Emitida pelo endpoint real (`POST /api/v1/fiscal/nfe/emitir`, porta 8282):

| | |
|---|---|
| **cStat** | **100** |
| **xMotivo** | **Autorizado o uso da NF-e** |
| **Protocolo (nProt)** | **113260013553729** |
| **Chave** | **13260935710481000103550010000000081704723132** |
| tpAmb | **2 — homologação** |
| Número / série | 8 / 1 |
| Emitente | CONECTAMAIS ELETRONICA LTDA · CNPJ 35.710.481/0001-03 · IE **054265746** · CRT 3 |
| Destinatário | `NF-E EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL` · CNPJ 99999999000191 |
| Produto | NCM **85258919** (CAMERA BODYCAM 2K IP66 GPS WI-FI 4G) · CFOP 5102 · R$ 100,00 |
| Tributo | ICMS CST 00 a 20,00% (R$ 20,00) · PIS 1,65% · COFINS 7,60% · IBS/CBS CST 000 |
| XML | `/…/nfe/35710481000103/2609/13260935710481000103550010000000081704723132-proc.xml` |

O NCM veio das **compras reais** da empresa (`nfe_compras_estoque`, 3 entradas de bodycam) — a
frente Z1 ainda não entregou `fin_produtos` (a tabela não existe no sandbox).

### CONECTAMAIS PATRIMONIAL LTDA — **BLOQUEADA no cadastro**, não no código ⛔

O pedido de emissão é recusado antes de qualquer transmissão:

```json
{"code":"EMITENTE_INCOMPLETO",
 "message":"Emitente incompleto na tabela `empresas` — falta: inscrição estadual, CEP.
            Preencha o cadastro da empresa antes de emitir (nada é chutado aqui).",
 "faltam":["inscrição estadual","CEP"], "cnpj":"66014833000110"}
```

**Isto não é falta de código.** Toda a esteira foi exercida com o certificado A1 da Patrimonial
contra a SEFAZ-AM de homologação e passou por tudo:

- status do serviço com o cert da Patrimonial: `cStat 107 · Servico em Operacao · tpAmb 2`;
- XML montado no ramo Simples Nacional (CRT 1, CSOSN 102), assinado e **aceito no schema**;
- transmissão OK, `104 Lote processado`;
- e então, o único ponto que falta: **`209 · Rejeicao: IE do emitente invalida`**.

`empresas.inscricao_estadual` da Patrimonial está **vazia**, e não há IE dela em lugar nenhum do
sistema (`empresas`, `tenants`, `sped_files` — todos vazios para esse CNPJ). A consulta cadastro
da SEFAZ-AM não ajuda: o serviço `cadconsultacadastro2` responde *"The service cannot be found
for the endpoint"* — o Amazonas não oferece CONS-CAD.

**Não inventei IE.** A nota da Patrimonial sai no minuto em que o número real entrar no cadastro
(§7, item 1).

### O caminho inteiro, provado

| Operação | Resultado em homologação |
|---|---|
| Status do serviço (2 CNPJs) | `107 · Servico em Operacao` |
| **Emissão** | **`100 · Autorizado o uso da NF-e`** · nProt 113260013553729 |
| **Cancelamento** (evento 110111) | **`135 · Evento Registrado e viculado a NFe`** · nProt 113260013553728 (nota 5) e 113260013553732 (nota 4) |
| **Inutilização de faixa** (série 1, 9500–9502) | **`102 · Inutilizacao de numero homologado`** · nProt 113260013553731 |
| Inutilização de número já usado | `241 · Um numero da faixa ja foi utilizado` (a recusa certa, lida certo) |
| Emissão em produção sem gate | `PRODUCAO_TRAVADA` — nada transmitido, nada gravado |

A nota 4 foi **cancelada de propósito**: ela é de antes do fix do PIS/COFINS e saiu sem esses
grupos (o PyNFe pula o grupo quando `pis_modalidade` está vazio, e a SEFAZ autorizou assim).
Cancelar é o remédio fiscal correto — a nota válida é a 8.

---

## §4 — Oráculo

`backend/scripts/orq/test_oraculo_z2_emissor_nfe.py` — afirma (a) DV da chave recalculado por
fora · (b) numeração sem repetir e sem buraco, com o índice único conferido no `pg_indexes` ·
(c) duas emissões concorrentes com números distintos e consecutivos · (d) nenhuma nota com
`tp_amb='1'` e as quatro travas de produção levantando de verdade · (e) o XML guardado é um
`nfeProc` completo, em disco, com a chave e o protocolo da linha · (f) nota cancelada com evento
110111 em `nfe_eventos` · (g) o emissor aposentado sumiu e ninguém o importa · (h) nenhum tributo
literal no emissor.

**XSD:** o pacote oficial de schemas (PL_010) **não está no repositório**, então não há XSD
contra o que validar. Em vez de fingir validação, o item (e) confere a estrutura mínima
obrigatória do 4.00 (29 tags, incluindo `IBSCBS`, `Signature` e `protNFe`). O validador de
verdade é a SEFAZ: schema inválido volta como `cStat 215` com a mensagem do XSD — foi assim que
as rejeições 215 desta frente foram diagnosticadas, e fica gravado em `nfes.motivo_rejeicao`.

**VERMELHO** (código de antes da frente, `a5a6f2ce2`):
```
$ docker run … -v $SP/antes/backend:/app:ro … python3 /app/scripts/orq/test_oraculo_z2_emissor_nfe.py
  File "/app/scripts/orq/test_oraculo_z2_emissor_nfe.py", line 141, in main
    from modules.fiscal_contabil.notas_fiscais.nfe import emissor as em
ImportError: cannot import name 'emissor' from 'modules.fiscal_contabil.notas_fiscais.nfe'
```

**VERDE** (depois):
```
$ docker exec -e PYTHONPATH=/app teste-dgx-z2 python3 /app/scripts/orq/test_oraculo_z2_emissor_nfe.py
chaves conferidas: 7 · 35710481…/1/amb2: 1–8, 8 notas, 0 inutil. · concorrência: [1, 2] ·
autorizadas: 1 · canceladas: 2 · emissor aposentado: sem arquivo e sem chamador
OK emissor NF-e: chave com DV certo, numeração sem buraco e atômica, produção travada,
XML guardado, cancelamento com evento, emissor duplicado aposentado, tributo pela régua
TOTAL desvios: 0
```

Fixtures `'FIXTURE DGX Z2'` são criadas e apagadas dentro do próprio oráculo (item (c)).
Testes de unidade: `tests/test_nfe_provider.py` **11 passed, 2 skipped**;
`tests/test_financial_services_coverage.py -k NFeProvider` **9 passed** (o
`test_emitente_data`, que travava o dict chumbado, virou `test_emitente_nao_e_chumbado` +
`test_producao_travada_por_padrao`).

---

## §5 — O que NÃO foi feito

1. **Nenhuma emissão em produção.** Por desenho. O caminho está pronto e travado atrás do gate.
2. **Nenhuma tela.** É território da frente Z3. Os 5 endpoints mantêm o path antigo.
3. **A nota da Patrimonial não foi autorizada** — falta a IE no cadastro (§7.1). Não inventei.
4. **Sem XSD local.** Baixar o PL_010 do portal da NF-e é download com captcha; ficou como
   pendência de infraestrutura. O item (e) do oráculo diz isso em vez de fingir.
5. **DANFE em PDF** — `pdf_danfe` volta `None`. Tem gerador de PDF na casa
   (`crm/services/pdf_branding.py`) mas o DANFE tem leiaute próprio; fora do escopo.
6. **Carta de correção (evento 110110)** não foi implementada. Só 110111 e inutilização.
7. **Contingência (SVC-AN / FS-DA)** não implementada. Se a SEFAZ-AM cair, a emissão falha e a
   linha fica gravada com o motivo — não há caminho alternativo automático.
8. **`nfe_itens` não é populada** pelo emissor novo. Os itens vivem no XML guardado, que é a
   fonte legal. Popular a tabela é trabalho de relatório, não de emissão.
9. **Alíquota de IBS/CBS fixa em 2026** (0,1% / 0,0% / 0,9%). São as da transição; em 2027 mudam
   e viram parâmetro (`core/parametros.py` já existe para isso).
10. **O guard multi-CNPJ está vermelho em 35 arquivos** nesta branch — nenhum meu (os dois
    arquivos da frente têm 0 matches). A baseline está atrasada em relação a outras frentes da
    onda; removi só as duas entradas que ficaram órfãs pela poda.

---

## §6 — Como o Jordan testa amanhã

```bash
# 1. status do serviço (não emite nada)
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8080/api/v1/fiscal/nfe/sefaz-status?empresa_slug=conecta_eletronica"
# espera: servico_ativo true · ambiente "Homologação" · producao_liberada false

# 2. emitir em homologação
curl -s -X POST http://127.0.0.1:8080/api/v1/fiscal/nfe/emitir \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{
   "empresa_slug":"conecta_eletronica","serie":1,
   "destinatario":{"cnpj":"99999999000191","razao_social":"CLIENTE",
     "endereco":{"logradouro":"RUA TESTE","numero":"1","bairro":"CENTRO","municipio":"Manaus",
                 "cod_municipio":"1302603","uf":"AM","cep":"69010000"}},
   "items":[{"codigo":"BODYCAM","descricao":"CAMERA BODYCAM","ncm":"85258919","cfop":"5102",
             "unidade":"UN","quantidade":1,"valor_unitario":100.0}]}'
# espera: status "autorizada" · cStat "100" · protocolo preenchido · tp_amb "2"

# 3. cancelar (até 24h)  → cStat 135
curl -s -X POST …/fiscal/nfe/cancelar -d '{"chave_acesso":"<a chave>",
  "justificativa":"Cancelamento de teste em ambiente de homologacao"}'

# 4. inutilizar faixa    → cStat 102
curl -s -X POST …/fiscal/nfe/inutilizar -d '{"empresa_slug":"conecta_eletronica","serie":1,
  "numero_inicial":9600,"numero_final":9601,"justificativa":"Faixa reservada e nao utilizada"}'

# 5. ver a lista e o XML guardado
curl -s …/fiscal/nfe/listar | python3 -m json.tool
ls -l /opt/conecta-pro/uploads/nfe/35710481000103/2609/
```

Para a Patrimonial (passo 2 com `"empresa_slug":"conecta_patrimonial"`) a resposta hoje é a
recusa do §3 nomeando os dois campos que faltam.

---

## §7 — Decisões que só o dono pode tomar

1. **Inscrição Estadual da CONECTAMAIS PATRIMONIAL.** Sem ela a Patrimonial não emite NF-e
   modelo 55 — a SEFAZ-AM rejeita 209. Duas possibilidades: (a) a empresa **tem** IE e ela só não
   está no ERP → basta gravar em `empresas.inscricao_estadual` (junto com o CEP do endereço) e a
   nota sai; (b) a empresa **não tem** inscrição estadual → é preciso abrir IE na SEFAZ-AM, e até
   lá a Patrimonial só emite NFS-e (serviço/ISS), que é o que ela de fato vende. **Qual das duas?**
2. **Ligar produção.** O caminho está pronto. Para emitir de verdade: definir `NFE_AMBIENTE=1`
   **e** `NFE_PRODUCAO_LIBERADA` com a frase-senha no `.env` de produção. Só o dono faz isso.
   Recomendação: antes, rodar uma bateria em homologação com produtos e clientes reais.
3. **Série de produção.** A numeração é por CNPJ + série + ambiente e começa do 1. Se já existe
   NF-e emitida por outro sistema para a Eletrônica, o último número tem de entrar em
   `nfe_numeracao` (tp_amb='1') **antes** da primeira emissão, senão a SEFAZ rejeita 539
   (duplicidade). **Existe numeração anterior? Qual o último número?**
4. **Alíquota de ICMS interna do AM (20%).** Vem da régua da Z4, medida em 76 itens de notas de
   entrada AM→AM — o dispositivo do RICMS-AM não está no repositório. Vale uma confirmação do
   contador antes de produção.
5. **Endereço legal da Patrimonial.** Semeei rua/nº/bairro a partir de
   `crm/services/pdf_branding.py` (Rua Victor Hughes, 19 — Parque 10 de Novembro). O **CEP** ficou
   em branco de propósito: não há fonte. Confirmar endereço e CEP.
6. **Responsável técnico da NF-e.** Hoje vai o próprio CNPJ do emitente, contato "Suporte Conecta
   PRO", e-mail financeiro@conectamais.pro. Se houver CSRT emitido pela SEFAZ para a empresa, ele
   entra no grupo `infRespTec` — hoje não há.
