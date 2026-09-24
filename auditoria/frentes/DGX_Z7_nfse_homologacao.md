# DGX Z7 — NFS-e de serviço para os DOIS CNPJs, provada em HOMOLOGAÇÃO

**Frente:** Z7 (onda 8) · **Branch:** `dgx/z7-nfse-homologacao` · **Data:** 24/09/2026
**Módulo:** fiscal · **Porta de teste:** 8287 (`teste-dgx-z7`, parado ao fim)
**Ambiente de toda a frente:** HOMOLOGAÇÃO (produção restrita, `tpAmb = 2`).
**Nenhuma transmissão em produção — nem de NFS-e, nem de NF-e, nem para testar.**

O pedido do dono, no dia em que viu a primeira NF-e de produto autorizada:

> «a patrimonial tem apenas inscrição municipal, homologa também. nf de serviço e nf de
> produto pra eletronica e nf de serviço para a patrimonial»

---

## §1 — Qual é o caminho de homologação da NFS-e (medido, não lido)

A pergunta mais importante da frente era **onde** homologar. Havia três hipóteses e as três
foram medidas em 24/09/2026.

### 1.1 — O ABRASF de Manaus **não tem ambiente de homologação**

```
$ getent hosts nfse-hml.manaus.am.gov.br     →  (vazio — NXDOMAIN)
$ getent hosts nfse-prd.manaus.am.gov.br     →  167.249.182.59
$ getent hosts nfse.manaus.am.gov.br         →  167.249.182.55
$ curl .../arecepcionarloterps?wsdl (prd)    →  HTTP 200
```

`NFSeManausManager.URL_BASE_HOMOLOGACAO` e `WSDL_HOMOLOGACAO`
(`government_integrations/core/nfse_manaus.py:176,193`) apontam para
`nfse-hml.manaus.am.gov.br`, **um host que não existe no DNS**. Foi escrito por simetria com
o de produção, nunca exercido. Esse caminho está morto para homologação.

### 1.2 — Manaus **aderiu** ao Padrão Nacional. Não é previsão: são notas emitidas

```sql
select e.slug, count(*), min(competencia), max(competencia)
  from nfse_emitidas_nacional n join empresas e on e.id = n.empresa_id group by 1;
-- conecta_eletronica  | 89 | 2026-01 | 2026-09
-- conecta_patrimonial | 25 | 2026-06 | 2026-08
```

114 NFS-e **reais**, R$ 2.277.037,40, com chave nacional começando em `1302603` (código IBGE
de Manaus) — e 25 delas são da **Patrimonial**, que segundo a tela do ERP «não tinha nota
nenhuma». Exemplo real: `13026032266014833000110000000000003226090000954170`, vigilância
(`110201`), ISS 4,35%, competência 08/2026.

Isto derruba o comentário de `nfse_nacional.consultar_status_migracao()` («Manaus ainda
utiliza o padrão ABRASF», «migração prevista para 2026», status `aguardando`), que continua
no arquivo como texto informativo e **não** é usado por nenhuma decisão de código.

### 1.3 — O ambiente de teste do Padrão Nacional chama-se **PRODUÇÃO RESTRITA**, e tem host próprio

```
$ getent hosts sefin.producaorestrita.nfse.gov.br  →  189.9.67.145
$ getent hosts sefin.nfse.gov.br                   →  189.9.84.43
$ curl -o /dev/null -w '%{http_code} tls=%{ssl_verify_result}' https://sefin.producaorestrita.nfse.gov.br/sefinnacional
  403 tls=0
$ curl ... https://sefin.nfse.gov.br/sefinnacional
  403 tls=0
```

`403` sem certificado é o esperado — a autenticação é **mTLS com A1 ICP-Brasil**. TLS válido
nos dois (`ssl_verify_result=0`).

**Correção de um dado do briefing:** não é verdade que «o Padrão Nacional usa `tpAmb` dentro
do payload, não host separado». Usa **os dois**. O que confundiu foi o dicionário
`NFSE_NACIONAL_ENDPOINTS`, onde `producao` e `homologacao` apontavam para a MESMA URL — mas
esse dicionário era lido **só** por `NFSeNacionalClient`, uma classe de **305 linhas com ZERO
chamadores** em todo o backend (`grep -rn NFSeNacionalClient\|NFSE_NACIONAL_ENDPOINTS backend/`
fora do próprio arquivo: nada). Era um segundo cliente, morto, que:

- mandava JSON solto para `POST /dps` (a API real quer `{"dpsXmlGZipB64": …}` em `POST /nfse`);
- e, pedindo **homologação**, apontava para o host de **PRODUÇÃO**.

Exatamente o padrão do «emissor A» que a frente Z2 aposentou na NF-e. **Foi apagado**
(`NFSE_NACIONAL_ENDPOINTS`, `NFSeNacionalResult`, `NFSeNacionalClient`), e no lugar entrou
uma função de três linhas:

```python
URL_PRODUCAO          = "https://sefin.nfse.gov.br/sefinnacional"
URL_PRODUCAO_RESTRITA = "https://sefin.producaorestrita.nfse.gov.br/sefinnacional"

def url_para(ambiente) -> str:
    return URL_PRODUCAO if str(ambiente) == "producao" else URL_PRODUCAO_RESTRITA
```

O código que de fato emite (`NFSeNacionalManager`) já usava a produção restrita — quem
estava errado era só o cliente morto. `nfse_nacional.py` foi de **903 para 599 linhas**.

### 1.4 — A declaração

> **O caminho de homologação da NFS-e desta casa é UM: Padrão Nacional, host de produção
> restrita `sefin.producaorestrita.nfse.gov.br/sefinnacional`, com `<tpAmb>2</tpAmb>` no DPS
> assinado.** O ABRASF de Manaus não oferece homologação e não é mais o padrão da praça.

---

## §2 — As 27 NFS-e «autorizadas» que nunca saíram desta casa

Confirmado no sandbox, igual à produção:

```sql
select count(*) total,
 count(*) filter (where coalesce(protocolo,'')<>'')          com_protocolo,
 count(*) filter (where coalesce(codigo_verificacao,'')<>'') com_cod_verif,
 count(*) filter (where coalesce(xml_enviado,'')<>'')        com_xml_env,
 count(*) filter (where coalesce(xml_retorno,'')<>'')        com_xml_ret,
 count(*) filter (where coalesce(link_nfse,'')<>'')          com_link
from nfses;
-->  27 | 0 | 0 | 0 | 0 | 0
```

Três coisas a mais, que o briefing não tinha:

1. **Todas as 27 foram criadas no MESMO instante:** `created_at::date = 2026-03-23` para as
   27, com `data_emissao` espalhada entre 05/01 e 12/02/2026. É importação/seed, não emissão.
2. **Trazem a razão social ANTIGA** (`JORDAN SANTOS DE JESUS LTDA`) — a mesma marca de idade
   que a Z2 achou nas duas NF-e de 11/04/2026.
3. **Elas alimentam um cálculo de dinheiro.** `crm/services/precificacao_contrato.py:223`
   soma `valor_servicos` de `nfses` filtrando **`status = 'autorizada'`**:
   ```sql
   select count(*), sum(valor_servicos) from nfses
    where active and status='autorizada' and coalesce(protocolo,'')='';
   -->  27 | 542.673,92
   ```
   **R$ 542.673,92** de faturamento sem prova entram na precificação de contrato.

### A decisão: não tocar na linha, consertar o rótulo

O contrato desta onda diz, em letras próprias: *«Nunca DROP/DELETE/UPDATE em dado que você
não criou.»* Essas 27 linhas não são desta frente. Um `UPDATE … SET status='sem_comprovacao'`
seria reescrever o registro de outra pessoa com base numa inferência minha.

Então: **as linhas ficam exatamente como estão** e o que muda é quem decide o rótulo.

```python
def estado_real(status, protocolo, xml_retorno) -> tuple[str, str]:
    """«Autorizada» é afirmação sobre o FISCO, não sobre o nosso banco."""
    tem_prova = bool((protocolo or "").strip()) and bool((xml_retorno or "").strip())
    ...
    return "sem_comprovacao", "sem comprovação — nunca transmitida"
```

Função pura, em `_dgx_z7_nfse.py`, usada pela tela e afirmada pelo oráculo (item **c**) com
SQL próprio. A tela nunca mais chama de «autorizada» uma nota sem o número que o órgão
devolveu **e** o XML que ele assinou.

**O que isso NÃO resolve** está no §7.1: a precificação e outros 5 pontos leem
`nfses.status` cru e continuam contando as 27. Marcar no banco é ordem do dono.

---

## §3 — As notas em homologação — as DUAS empresas, AUTORIZADAS ✅

Todas por `POST /api/v1/redesign/action/z7-nfse-emitir` ou pelo serviço, contra
`sefin.producaorestrita.nfse.gov.br`, `cStat 100`, persistidas em `nfses` com XML em disco
**e** no banco.

### CONECTAMAIS ELETRONICA LTDA — CNPJ 35.710.481/0001-03 (Lucro Real)

| Série/Nº | NFS-e | nDFSe | cStat | Chave de acesso | Valor | ISS |
|---|---|---|---|---|---|---|
| 900/2 | 11 | **19174** | **100** | `13026032235710481000103000000000001126094358849046` | R$ 100,00 | 5,00% · R$ 5,00 |
| 900/3 | 12 | **19176** | **100** | `13026032235710481000103000000000001226093172723170` | R$ 250,00 | 5,00% · R$ 12,50 |
| 900/4 | 13 | **19177** | **100** | `13026032235710481000103000000000001326093781642947` | R$ 250,00 | 5,00% · R$ 12,50 |

Serviço `140601` (LC 116 item 14.06 — instalação e montagem de aparelhos e equipamentos),
que é o que esta empresa **de fato** usa nas 89 notas reais dela.

### CONECTAMAIS PATRIMONIAL LTDA — CNPJ 66.014.833/0001-10 (Simples Nacional) ✅

| Série/Nº | NFS-e | nDFSe | cStat | Chave de acesso | Valor | ISS |
|---|---|---|---|---|---|---|
| 900/2 | 7 | **19175** | **100** | `13026032266014833000110000000000000726099200510385` | R$ 100,00 | **não devolvido pelo fisco** |

Serviço `110201` (LC 116 item 11.02 — vigilância, segurança e monitoramento).

**A Patrimonial emite.** Ela não precisava de inscrição estadual para isso — a NFS-e é
municipal, e a inscrição municipal dela (721042001) já estava em `empresas`.

Duas coisas que o retorno do órgão ensinou, e que estão gravadas como ele mandou:

- **`E0120`** — «IM do prestador não deve ser informado, pois não existem informações
  complementares registradas no CNC NFS-e do município emissor». A retentativa sem a `<IM>`
  (que já existia no código desde 13/09) resolveu; a nota saiu com `im_omitida_por_E0120`.
  A Eletrônica **está** no CNC e manda a IM normalmente.
- **O fisco não devolve ISS para o Simples Nacional.** O `<valores>` da nota da Patrimonial
  tem só `<vLiq>100.00</vLiq>` — sem `vBC`, sem `pAliqAplic`, sem `vISSQN`. O ISSQN dela é
  apurado dentro do DAS. Então `iss_valor` fica **NULL** e a tela mostra **«—»**, nunca 0%.
  A alíquota que a tela recebe é ignorada de propósito: **grava-se o que o órgão devolveu.**

### O endereço legal das duas, pela boca do próprio fisco

O `<NFSe>` assinado traz o `<enderNac>` do CNC — o que **responde a pendência §7.5 da Z2**
(«o CEP da Patrimonial ficou em branco: não há fonte»). Agora há:

| | Logradouro | Nº | Bairro | CEP |
|---|---|---|---|---|
| Eletrônica | RUA NOVA PALESTINA | 51 | CRESPO | **69073488** |
| Patrimonial | RUA VICTOR HUGHES | 19 | PARQUE 10 DE NOVEMBRO | **69055630** |

**Não gravei isso em `empresas`** — é cadastro de outra frente e o endereço da Eletrônica no
ERP hoje é outro. Fica em §7.4 para o dono confirmar.

### O caminho inteiro, provado

| Operação | Resultado em homologação (produção restrita) |
|---|---|
| Montar DPS sem transmitir (dry run) | XML 1.351–1.513 bytes, `tpAmb 2`, assinatura XMLDSig |
| **Emissão (Eletrônica)** | **`HTTP 201 · cStat 100`** · nDFSe 19174/19176/19177 |
| **Emissão (Patrimonial)** | **`HTTP 201 · cStat 100`** · nDFSe 19175 (com retentativa E0120) |
| Consulta `GET /nfse/{chave}` das duas | `HTTP 200` com o `<NFSe>` assinado |
| Número de DPS já usado no fisco | `E0141` — recusa lida certo, número queimado com linha |
| Emissão pedindo PRODUÇÃO sem o gate | `PRODUCAO_TRAVADA` — nada transmitido, nada gravado |
| NF-e 55 pela Patrimonial | `DOCUMENTO_NAO_E_DESTA_EMPRESA` (§5) |
| **NF-e 55 pela Eletrônica (regressão da Z2)** | **`cStat 100`** · nº 10 · protocolo 113260013553911 |

---

## §4 — O que foi construído

| Arquivo | O quê |
|---|---|
| `backend/modules/fiscal/services/nfse_emissao.py` (novo, 400 l.) | numeração atômica, persistência em `nfses`, guarda do XML, DDL idempotente |
| `backend/modules/fiscal/services/documentos_da_empresa.py` (novo, 119 l.) | a decisão do dono virou dado: quem emite NF-e 55 e por que não |
| `backend/modules/operacional/controllers/redesign_builders/_dgx_z7_nfse.py` (novo, 330 l.) | a tela de emitir, a tela das emitidas, a ação, e `estado_real()` |
| `backend/modules/government_integrations/core/nfse_nacional.py` | **−304 linhas** (cliente morto) · a trava de produção · parser do retorno · `cNBS` opcional |
| `backend/modules/government_integrations/services/nfse_nacional_service.py` | aceita `numero` (o do contador) e `codigo_nbs` |
| `backend/modules/fiscal_contabil/notas_fiscais/nfe/emissor.py` | +19 l.: consulta a política de documentos antes de reservar número |
| `backend/modules/operacional/controllers/redesign_builders/fiscal.py` | plug da Z7 (3 linhas) · −52 l. da tela antiga que não persistia |
| `backend/scripts/orq/test_oraculo_z7_nfse.py` (novo) | o oráculo |

### 4.1 — A trava de produção: duas camadas + gate humano

Mora em `nfse_nacional.py`, **dentro do funil por onde TODO chamador passa** — não só o
emissor da Z7. Gate **próprio** (`NFSE_PRODUCAO_LIBERADA`): soltar a NF-e de mercadoria não
pode soltar junto a nota de serviço.

1. **`_exigir_ambiente_nfse(tp_amb, …)`** na primeira linha de `emitir_dps`, antes de montar,
   assinar ou reservar número. Produção só passa com a **frase-senha exata** — env valendo
   `"1"` ou `"true"` **não** abre.
2. **`_conferir_tp_amb(xml_assinado, tp_amb, url, …)`** relê o `<tpAmb>` do XML **já
   assinado**, imediatamente antes do POST, e confere contra o **host de destino**. Recusa
   quando: não há `tpAmb`; o `tpAmb` diverge do pedido; o host não corresponde ao `tpAmb`;
   ou é produção sem o gate.

A recusa **não** é engolida pelo `except Exception` da transmissão: `NFSeAmbienteError` sobe
como recusa, para a tela dizer «bloqueado de propósito» e não «erro».

Prova de ponta a ponta, pelo caminho real (`NFSeNacionalManager(ambiente=PRODUCAO)`):
```
NFSE_PRODUCAO_LIBERADA aberta? False
url que ele usaria: https://sefin.nfse.gov.br/sefinnacional · tp_amb: 1
RECUSADO: PRODUCAO_TRAVADA · Emissão de NFS-e em PRODUÇÃO bloqueada. NFS-e autorizada em
produção é documento fiscal irreversível, com ISS devido ao município…
```

### 4.2 — Numeração sem buraco (o `int(time.time())` morreu)

O número da DPS era `numero_dps = f"{int(datetime.now().timestamp())}"`: **buraco permanente
e garantido** na numeração fiscal, o mesmo defeito que a Z2 matou na NF-e. Agora é contador
atômico por (CNPJ + série + ambiente), mesmo desenho:

```sql
CREATE TABLE nfse_numeracao (prestador_cnpj, serie, ambiente, ultimo, PRIMARY KEY (…))
CREATE UNIQUE INDEX ux_nfses_prestador_serie_numero
  ON nfses (prestador_cnpj, serie_rps, numero_rps, ambiente)
  WHERE ambiente IS NOT NULL AND numero_rps IS NOT NULL
```

`INSERT … ON CONFLICT DO UPDATE SET ultimo = GREATEST(…)+1 RETURNING` — uma ida ao banco,
linha travada. O `WHERE ambiente IS NOT NULL` deixa as 27 linhas antigas de fora: elas não
têm ambiente e não podem ser julgadas por uma regra que nasceu depois delas.

**Série 900**, dedicada ao ERP: as notas que a empresa já emite pelo portal do fisco usam
outra numeração (nº 1–122), e série separada é o que impede colisão.

O número é reservado **antes** de ir ao fisco e nunca volta atrás. Falha de transmissão vira
linha com o motivo — senão o número some e vira buraco invisível.

### 4.3 — A guarda do XML, nos dois lugares (e ela salvou uma nota hoje)

`$NFSE_XML_DIR/<cnpj>/<AAMM>/<chave>-nfse.xml` (default `/app/uploads/nfse`, **bind do
host**, durável) **e** `nfses.xml_retorno` / `nfses.xml_enviado` no banco. O caminho fica em
`nfses.xml_path`.

O disco é escrito **antes** do INSERT, de propósito — e isso foi testado ao vivo sem querer:
a primeira emissão da Patrimonial (DPS 900/1) foi **autorizada pelo fisco** e o `INSERT`
estourou logo depois por um bug de bind (`asyncpg` confere o tipo do parâmetro antes do CAST
do SQL: `'2026-09-01'` como texto em coluna `date` dá `'str' object has no attribute
'toordinal'`). A transação voltou atrás, mas o XML da nota `…0006…` **ficou em disco**:
`/opt/conecta-pro/uploads/nfse/66014833000110/2609/13026032266014833000110000000000000626095590395911-nfse.xml`.
O bug foi corrigido (converte para `date`/`datetime` em Python). Sobre a nota órfã, ver §5.4.

### 4.4 — `cNBS`: um número fiscal inventado, removido

`_build_dps_xml` mandava `<cNBS>120032900</cNBS>` **chumbado em toda nota**. Medido hoje: o
fisco devolve o `xNBS` correspondente, e nas notas de **vigilância da Patrimonial** ele voltou
como *«Serviços de instalação de maquinários, aparelhos e equipamentos»* — descrição errada,
porque o código era o de outro serviço.

Não há tabela NBS oficial neste repositório. Então a tag virou **opcional** e, sem fonte, não
vai. Provado contra o fisco: **`cStat 100` sem `cNBS`** — a tag não é obrigatória. O oráculo
(item **h**) trava a volta do literal.

### 4.5 — As telas

| id | Grupo | O quê | Deep-link |
|---|---|---|---|
| `nfse-emitir-dps` | Notas fiscais | **Emitir NFS-e (serviço)** — empresa, tomador, código do serviço, valor, simulação | `/redesign/fiscal?t=nfse-emitir-dps` |
| `z7-nfse-emitidas` | Notas fiscais | **NFS-e emitidas pelo ERP** — 10 colunas, com estado real, protocolo e retorno do órgão | `/redesign/fiscal?t=z7-nfse-emitidas` |

A tela de emitir **reusa o id e a entrada de menu que já existiam** («NFS-e nacional — emitir
DPS», hoje rotulada «Emitir NFS-e (serviço)»). O corpo antigo — 52 linhas que apontavam
direto para `/government/nfse-nacional/emitir`, transmitiam e **não gravavam nada** — foi
apagado de `fiscal.py`. Dois caminhos de emissão, um deles sem persistência, é exatamente a
armadilha que a Z2 desmontou na NF-e. Aqui há **um**.

O ambiente **não** é escolhido na tela: vem de `empresas.nfse_ambiente`. A tela mostra qual é,
por empresa, e diz se a produção está travada — sem nunca expor a frase-senha.

Os **códigos de serviço** oferecidos no select são os quatro **medidos** nas 114 notas reais
das duas empresas (`110201`, `071002`, `140601`, `140101`), cada um rotulado com quem o usa.
Não é convenção: é o que cada CNPJ de fato declarou ao fisco.

---

## §5 — A Patrimonial fora da NF-e 55, com recusa que ensina

Antes, o emissor da Z2 respondia:

```json
{"code":"EMITENTE_INCOMPLETO",
 "message":"Emitente incompleto na tabela `empresas` — falta: inscrição estadual, CEP.
            Preencha o cadastro da empresa antes de emitir…"}
```

Texto que manda alguém gastar o dia atrás de uma IE **que o dono não pediu**. Agora:

```json
{"code":"DOCUMENTO_NAO_E_DESTA_EMPRESA",
 "message":"A CONECTAMAIS PATRIMONIAL não emite NF-e de produto (modelo 55). Ela tem apenas
            inscrição MUNICIPAL (721042001) e o que vende é serviço — vigilância, portaria e
            limpeza. Decisão de Jordan Jesus em 24/09/2026. O documento fiscal dela é a
            NFS-e: use a tela «Emitir NFS-e (serviço)», no grupo Notas fiscais do módulo
            Fiscal.",
 "empresa":"conecta_patrimonial",
 "tela":"/redesign/fiscal?t=nfse-emitir-dps"}
```

**A regra mora em dado, não em `if`** — e no mesmo lugar onde já vive toda a identidade
fiscal da empresa (doutrina que a Z2 estabeleceu: nada de identidade fiscal chumbado em
Python):

```sql
ALTER TABLE empresas ADD COLUMN IF NOT EXISTS emite_nfe_produto boolean NOT NULL DEFAULT true;
ALTER TABLE empresas ADD COLUMN IF NOT EXISTS motivo_nao_emite_nfe_produto text;
```

Mudar a decisão é **um UPDATE numa linha**, ao lado da `inscricao_estadual` que a motivou:

```sql
UPDATE empresas SET emite_nfe_produto = true, motivo_nao_emite_nfe_produto = NULL
 WHERE slug = 'conecta_patrimonial';
```

O padrão é `true`: empresa nova não nasce bloqueada por omissão. A semente da decisão só
escreve quando ninguém decidiu ainda (`WHERE emite_nfe_produto AND motivo IS NULL`) — rodar
`_ensure` de novo **não** desfaz a escolha do dono.

A trava roda em `emissor.emitir()` **antes de reservar número** — recusar depois queimaria um
número da série.

---

## §6 — Oráculo

`backend/scripts/orq/test_oraculo_z7_nfse.py` — afirma (a) homologação e produção são hosts
DIFERENTES e o código não os confunde · (b) nada gravado em ambiente de produção, nem nota nem
contador · (c) nenhuma linha exibida como «autorizada» sem protocolo E XML de retorno,
recontando por SQL próprio e passando pela função pura da tela · (d) o XML está em disco E no
banco, e o arquivo contém a chave da linha · (e) a Patrimonial é recusada na NF-e 55 pelo
motivo certo, sem falar em cadastro/IE, apontando tela — e a Eletrônica **não** é recusada ·
(f) as seis recusas da trava levantam de verdade, e o caminho legítimo (homologação) **passa**
· (g) índice único existe, numeração sem buraco, reservas consecutivas, **e nenhum número
reservado sem linha** · (h) nenhum número fiscal chumbado na montagem da DPS e nenhum
timestamp de volta como número de nota · (i) prova viva: NFS-e autorizada em homologação, com
chave e `cStat 100`, para **cada um** dos dois CNPJs.

**VERMELHO** (código de antes da frente, `96f2a5e73`, árvore extraída por `git archive`):
```
$ docker run … -v $SP/antes/backend:/app:ro … python3 /app/scripts/orq/test_oraculo_z7_nfse.py
  File "/app/scripts/orq/test_oraculo_z7_nfse.py", line 75, in main
    from modules.fiscal.services import nfse_emissao as em
ImportError: cannot import name 'nfse_emissao' from 'modules.fiscal.services'
EXIT=1
```

**VERDE** (depois):
```
$ docker run … -v $WT/backend:/app:ro … python3 /app/scripts/orq/test_oraculo_z7_nfse.py
hosts: hml=sefin.producaorestrita.nfse.gov.br prd=sefin.nfse.gov.br · produção: 0 notas,
0 contadores · nfses: 31 linhas · 4 com prova · 27 sem comprovação · XML guardado: 4/4 em
disco e no banco · numeração: reservas 1→2 (FIXTURE DGX Z7, apagada) · autorizadas em
homologação: 35710481000103=3, 66014833000110=1 · travas exercidas: 6
OK NFS-e: homologação é produção restrita com host próprio, nada em produção, «autorizada»
só com protocolo e XML do órgão, XML no disco E no banco, Patrimonial recusada na NF-e 55
pela decisão do dono, travas levantando, numeração sem buraco
TOTAL desvios: 0
EXIT=0
```

Fixtures `'FIXTURE DGX Z7'` (CNPJ 00000000000191) são criadas e apagadas dentro do próprio
oráculo, no item (g). As notas de teste no fisco levam `FIXTURE DGX Z7 - PRODUCAO RESTRITA -
SEM VALOR FISCAL` na descrição.

**Oráculos irmãos, depois das minhas mudanças:**
- `test_oraculo_z2_emissor_nfe.py` → `TOTAL desvios: 0` (10 notas, 3 autorizadas)
- `test_nfse_identidade_fiscal.py` → `TOTAL: 0 divergência(s)`

`ruff check` nos 8 arquivos da frente: **All checks passed**.
O guard multi-CNPJ segue vermelho em ~35 arquivos desta branch — **nenhum meu** (os meus
arquivos novos têm zero CNPJ literal; o único match em `fiscal.py` é um comentário
pré-existente, linha 682).

---

## §7 — O que NÃO foi feito, e por quê

1. **Nenhuma emissão em produção.** Por desenho. O caminho está pronto e travado.
2. **As 27 linhas não foram alteradas no banco.** O contrato proíbe UPDATE em dado que a
   frente não criou. A tela desta frente mostra o estado real; **outros seis pontos leem
   `nfses.status` cru e continuam contando as 27 como autorizadas** — `precificacao_contrato.py:223`
   (soma dinheiro, filtra `status='autorizada'`), `consultor_hub.py:718`,
   `kit_real_controller.py:539,788`, `kit_pdf_controller.py:518`, `fiscal_repository.py:534`,
   `nfse_entrada_sync_service.py:193`. Ver §8.1.
3. **Cancelamento de NFS-e não implementado.** O Padrão Nacional cancela por evento
   (`POST /nfse/{chave}/eventos`); não foi exercido nem uma vez, então não entrou. Emitir e
   cancelar são caminhos distintos e cancelamento sem prova é pior que ausência.
4. **A DPS 900/1 da Patrimonial ficou no fisco sem linha local.** Foi autorizada
   (`…0006…`, nDFSe 19173) e o INSERT estourou pelo bug de bind do §4.3. O XML está em disco.
   Não fabriquei a linha à mão: o remédio certo é **conciliação por consulta** (`GET
   /nfse/{chave}` → gravar), que não foi construída. Em homologação isso é inofensivo; em
   produção seria obrigatório. Ver §8.5.
5. **Números de DPS queimados por `E0141`** («essa série+número já existe») ficam registrados
   como queimados e a próxima emissão pega o seguinte — **uma tentativa por clique**, sem
   laço. Se houver muitos números queimados em sequência, o remédio é semear
   `nfse_numeracao.ultimo` com o último número real, não disparar N pedidos ao fisco. Marcado
   com `# ponytail:` no código.
6. **DANFSe em PDF não foi gerado aqui.** Já existe
   `gedeon/services/nfse_danfse_generator.py` e a rota
   `/financial/fiscal/nfse-emitida/{chave}/danfse`, que servem as notas do ADN; ligá-los às
   notas do ERP é trabalho de uma linha na tela e não foi feito porque essas notas são de
   homologação e não têm DANFSe com valor.
7. **Sem XSD local.** Os schemas oficiais do Padrão Nacional não estão no repositório. O
   validador de verdade é o fisco: schema inválido volta como `E0xxx` com o texto exato, e
   isso fica gravado em `nfses.mensagem_retorno` — foi assim que `E0120`, `E0141` e o `cNBS`
   errado desta frente foram diagnosticados.
8. **`nfse_manaus.py` (ABRASF) não foi aposentado**, só documentado. Ele tem 626 linhas, é
   importado em outros pontos e o histórico municipal (`nfse_manaus_historico`, 831 linhas)
   depende do vocabulário dele. Apagar é decisão de outra frente. **Mas a constante
   `URL_BASE_HOMOLOGACAO` aponta para um host inexistente** e quem tentar homologar por ali
   vai bater em `curl exit 6`.
9. **Modelo ORM `NFSe` aponta para uma tabela que não existe.**
   `financial/models/nfse.py:108` declara `__tablename__ = "nfse"`; no banco a tabela é
   `nfses` (`select to_regclass('public.nfse')` → vazio). Logo
   `fiscal_repository.create_nfse()` quebraria se fosse chamado. Achado de passagem — não é
   desta frente consertar, e nada que eu escrevi usa o ORM (tudo é SQL explícito).
10. **Não mexi em `empresas.endereco_*`** com o endereço que o fisco devolveu (§3). É
    cadastro, e o da Eletrônica no ERP hoje é outro.

---

## §8 — Decisões que só o dono pode tomar

1. **As 27 NFS-e fantasmas — marcar no banco ou deixar?**
   Elas dizem `autorizada`, nunca foram transmitidas, somam **R$ 542.673,92** e **entram no
   cálculo de precificação de contrato** (`precificacao_contrato.py` filtra por
   `status='autorizada'`). A tela desta frente já mostra a verdade; o cálculo não.
   Opções: **(a)** marcar as 27 com um estado honesto —
   `UPDATE nfses SET status='sem_comprovacao' WHERE created_at::date='2026-03-23' AND coalesce(protocolo,'')=''`
   — o que conserta os 6 leitores de uma vez; **(b)** deixar e aceitar que a precificação
   usa faturamento sem prova. **Eu não faço (a) sem a sua ordem:** é reescrever registro que
   não é meu. **Qual?**

2. **Ligar a produção da NFS-e.** O caminho está pronto. Para emitir de verdade é preciso,
   nesta ordem: (i) `UPDATE empresas SET nfse_ambiente='producao'` na empresa escolhida;
   (ii) `NFSE_PRODUCAO_LIBERADA` com a frase-senha no `.env` de produção. Só você faz isso.
   **Recomendação: antes, rodar uma competência inteira em homologação** com clientes e
   valores reais, e conferir contra as notas que o portal emitiu no mesmo mês.

3. **A numeração de produção (série 900).** O contador começa do 1 por CNPJ+série+ambiente.
   O fisco **já** recusou o nº 1 da Eletrônica com `E0141` — havia DPS série 900 emitida por
   alguém antes. Antes da primeira emissão em produção, `nfse_numeracao` precisa nascer com
   o **último número real** da série 900 de cada CNPJ. **Qual é? Ou prefere uma série nova,
   nunca usada (ex.: 901), para começar do 1 sem risco?**

4. **O endereço legal das duas empresas.** O fisco devolveu, do cadastro dele:
   Eletrônica = RUA NOVA PALESTINA, 51 — CRESPO — CEP 69073488;
   Patrimonial = RUA VICTOR HUGHES, 19 — PARQUE 10 DE NOVEMBRO — CEP 69055630.
   O ERP tem outro endereço para a Eletrônica e o CEP da Patrimonial estava em branco (§7.5
   da Z2). **Gravo o que o fisco tem, ou o cadastro do ERP é que está certo?**

5. **Conciliação com o fisco (consultar e gravar).** Hoje, se o fisco autorizar e o nosso
   INSERT falhar, a nota existe lá e não aqui — aconteceu uma vez nesta frente (§7.4). A
   correção é uma rotina que consulta `GET /nfse/{chave}` e grava a linha que faltou. Vale
   construir antes de produção? (Minha recomendação: **sim**, é barato e fecha o único furo
   conhecido.)

6. **Inscrição municipal da Patrimonial no CNC.** O fisco recusa a `<IM>` dela com `E0120`
   porque **a prefeitura não a tem no cadastro complementar**. Hoje a nota sai sem a IM e é
   autorizada. Vale abrir o pedido na SEMEF para cadastrá-la? Enquanto não, a retentativa
   resolve sozinha e some no dia em que o cadastro existir.

7. **NBS (`cNBS`).** A tag saiu do XML porque o valor chumbado estava errado e não há tabela
   NBS neste repositório. É opcional no leiaute e as notas são autorizadas sem ela. **Se o
   contador quiser a NBS na nota, precisamos da tabela oficial** — sem fonte, não volta.

8. **Alíquota de ISS da Eletrônica (5%).** É a que o fisco aplicou e devolveu (`pAliqAplic
   5.00`), e a mesma das 89 notas reais dela. Não foi escolhida por nós. Vale a confirmação
   do contador antes de produção. Para a Patrimonial não há o que confirmar: Simples
   Nacional, ISSQN no DAS, o fisco não devolve alíquota.

---

## §9 — Como o Jordan testa amanhã

```bash
# tela: Fiscal → grupo «Notas fiscais»
#   «Emitir NFS-e (serviço)»       → /redesign/fiscal?t=nfse-emitir-dps
#   «NFS-e emitidas pelo ERP»      → /redesign/fiscal?t=z7-nfse-emitidas

# 1) SIMULAR (não transmite, não gasta número): escolha a empresa, preencha
#    tomador + serviço + valor, deixe «Simulação» em SIM → volta o XML da DPS.
#
# 2) TRANSMITIR em homologação: troque «Simulação» para NÃO.
#    Espera: status "autorizada" · cStat 100 · chave de acesso · nDFSe preenchido.
#
# 3) CONFERIR: abra «NFS-e emitidas pelo ERP».
#    A nota nova aparece com ambiente "homologacao", protocolo e o retorno do órgão.
#    As 27 antigas aparecem como «sem comprovação — nunca transmitida» — é a verdade.
#
# 4) A PATRIMONIAL NA NF-e DE PRODUTO (tem de recusar, explicando):
curl -s -X POST http://127.0.0.1:8080/api/v1/fiscal/nfe/emitir \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"empresa_slug":"conecta_patrimonial","serie":1,"destinatario":{...},"items":[...]}'
# espera: HTTP 400 · code DOCUMENTO_NAO_E_DESTA_EMPRESA · a mensagem do §5

# 5) O XML guardado (5 anos):
ls -l /opt/conecta-pro/uploads/nfse/35710481000103/2609/
ls -l /opt/conecta-pro/uploads/nfse/66014833000110/2609/
```

---

## §10 — Para o orquestrador: DDL que `_ensure` aplica em produção no 1º acesso

```sql
-- nfse_emissao._ensure()
ALTER TABLE nfses ADD COLUMN IF NOT EXISTS ambiente     varchar(16);
ALTER TABLE nfses ADD COLUMN IF NOT EXISTS empresa_slug varchar(40);
ALTER TABLE nfses ADD COLUMN IF NOT EXISTS chave_acesso varchar(60);
ALTER TABLE nfses ADD COLUMN IF NOT EXISTS numero_dfe   varchar(20);
ALTER TABLE nfses ADD COLUMN IF NOT EXISTS c_stat       varchar(8);
ALTER TABLE nfses ADD COLUMN IF NOT EXISTS xml_path     text;
ALTER TABLE nfses ADD COLUMN IF NOT EXISTS criado_por   varchar(120);
CREATE INDEX IF NOT EXISTS ix_nfses_chave ON nfses (chave_acesso);
CREATE UNIQUE INDEX IF NOT EXISTS ux_nfses_prestador_serie_numero
  ON nfses (prestador_cnpj, serie_rps, numero_rps, ambiente)
  WHERE ambiente IS NOT NULL AND numero_rps IS NOT NULL;
CREATE TABLE IF NOT EXISTS nfse_numeracao (
  prestador_cnpj varchar(14) NOT NULL, serie varchar(5) NOT NULL,
  ambiente varchar(16) NOT NULL, ultimo integer NOT NULL DEFAULT 0,
  updated_at timestamp NOT NULL DEFAULT now(),
  PRIMARY KEY (prestador_cnpj, serie, ambiente));

-- documentos_da_empresa._ensure()
ALTER TABLE empresas ADD COLUMN IF NOT EXISTS emite_nfe_produto boolean NOT NULL DEFAULT true;
ALTER TABLE empresas ADD COLUMN IF NOT EXISTS motivo_nao_emite_nfe_produto text;
UPDATE empresas SET emite_nfe_produto = false, motivo_nao_emite_nfe_produto = '<a decisão>'
 WHERE slug = 'conecta_patrimonial' AND emite_nfe_produto AND motivo_nao_emite_nfe_produto IS NULL;
```

O único UPDATE é numa coluna criada por esta frente, e só quando ninguém decidiu ainda.
Nenhum dado pré-existente é alterado.

**Nada a pedir em `frontend/`**: as telas são `form` e `table` genéricos. A entrada de menu
nova (`z7-nfse-emitidas`) e o rótulo alterado (`nfse-emitir-dps` → «Emitir NFS-e (serviço)»)
vêm pelo `extraMenu` da API, verificados em `GET /api/v1/redesign/data/fiscal`.

**Trava nova para `checar_regressao.py`** (você registra): `test_oraculo_z7_nfse.py`.

**Container parado:** `teste-dgx-z7` (porta 8287) — removido ao fim.
