# Decisões fiscais que só o Jordan pode tomar — 24/09/2026

> Todas vieram de algo **medido**, não de dúvida teórica. Cada uma tem o número do impacto e o
> que acontece se ficar em aberto. Ordenadas por urgência.

## 🔴 Urgente — afeta nota que sai AGORA pela Portte

### 1. O vale-alimentação do Ideal Flores está pela metade na planilha
A linha de setembro deduz **R$ 6.648,00** da base do INSS mas discrimina só
**VA 2.244,00 + VT 2.160,00 = R$ 4.404,00**. Faltam R$ 2.244,00 — e `4.488 + 2.160 = 6.648`
fecha exato, então o VA deveria ler **R$ 4.488,00**.

A dedução está certa. O que falta é **lastro no texto da nota**, que é o que a fiscalização lê.
**R$ 246,84 de INSS glosável**, mais multa. Corrigir na planilha antes da Portte emitir.

*(Há também R$ 0,23 de diferença no INSS: 11% de 59.194,42 dá 6.511,39 e a planilha diz 6.511,62.)*

### 2. ~~A série~~ — **DECIDIDA em 25/09: corte limpo**
O dono delegou («você decide que série usar») e confirmou a escolha: **NF-e na série 2** e
**NFS-e na série 901**, as duas começando do nº 1. O emissor antigo fica na série 1 (até a NF-e
10.026) e o portal na 70000 (até a NFS-e 123).

Razão principal: **risco de número queimado**. Continuar no 10.027 exigiria que o nfemais não
emitisse nem uma depois da virada — se emitisse, os dois pegariam o mesmo número e a SEFAZ
recusaria com 539. Com série própria o risco é zero.

Contrapartida aceita pelo dono: a numeração recomeça em 1.

## 🟡 Trava a produção

### 3. O último número real de cada documento
Sem isso a primeira emissão em produção é recusada por duplicidade. O sistema já **se recusa a
emitir** antes de alguém declarar (guarda de 24/09), mas o número é seu:

| Documento | Empresa | Último conhecido | Fonte |
|---|---|---|---|
| NF-e série 1 | Eletrônica | **10.026** | DANFE 17/09, protocolo 113263811849419 |
| DPS série 70000 | Eletrônica | **125** | NFS-e 121, 17/09 |
| DPS série 70000 | Patrimonial | **75** | NFS-e 31, 26/08 |

Confira no emissor em uso no dia — esses números crescem a cada nota que a Portte emite.

### 4. ~~Manutenção de CFTV~~ — **DECIDIDA em 25/09: 14.01.01**
O dono delegou («veja qual código é o mais adequado e use-o»). O texto oficial decide sozinho:
14.01 é «manutenção e conservação de máquinas, aparelhos, equipamentos»; 14.06 é «instalação e
montagem… exclusivamente com material por ele fornecido». A nota 116 estava certa, a 120 errada.

**Fica em aberto um caso vizinho:** a nota **119** (Gelain) é **portaria remota** e também saiu
14.06. Portaria remota é **monitoramento** (11.02), não instalação. Mudar altera alíquota e
possivelmente retenção — **pergunta para o contador**.

### 4b. ~~Manutenção de CFTV é 14.01 ou 14.06?~~ (histórico da pergunta)
Mesma empresa, mesmo mês, descrição **idêntica**, códigos diferentes:

| Nota | Descrição | Código |
|---|---|---|
| 116 | contrato de manutenção de CFTV/cerca/portões/cancelas | **14.01.01** |
| 120 | contrato de manutenção de CFTV/cerca/portões/cancelas | **14.06.01** |

Uma está errada, e o código define o ISS. Pergunta para o contador.

### 5. ~~PIS e COFINS na NF-e~~ — **DECIDIDO em 25/09: zerados**
O dono: «nós temos a liminar, então não é ser cobrado imposto sobre ela, é pra sair zerado».
Implementado como parâmetro `empresas.pis_cofins_processo` = **1038495-94.2024.4.01.3200**, com
o processo citado na linha e uma mensagem no corpo da nota.

**Fica para o contador, e não é detalhe:** o **CST**. Liminar SUSPENDE (CST 09); alíquota zero é
CST 06. Sem o texto da liminar não dá para decidir; ficou 09. E a liminar citada na NFS-e fala de
**retenção pelo tomador**, enquanto na NF-e o que se zera é o **PIS/COFINS próprio** — coisa
diferente. Vale ter a confirmação por escrito.

## 🟢 Recuperação de valor pago a mais

### 6. A dedução de VA/VT vale retroativo?
**13 das 25 notas** da Patrimonial (junho a agosto) saíram com **11% cheio sobre o bruto**, sem
dedução — R$ 267.581,00 de base, R$ 29.433,85 de INSS. As outras 12 deduziram e economizaram
R$ 9.062,38. Foi inconsistência do escritório, não política.

**Recuperar o que foi pago a mais, ou a regra vale daqui para a frente?**

### 7. Cancelar a nota 26 no fisco
Você confirmou que foi erro (Mirante, R$ 12.061,50, duplica a 27). Ela está marcada aqui como
`erro_confirmado` e **não conta mais como receita**. Mas **no fisco segue VÁLIDA**. Cancelar tem
prazo.

### 8. O rateio do Mirante
O Mirante recebe **duas notas no mesmo mês** e o VA+VT do contrato é **um só** (R$ 4.662,00).
Deduzir o valor inteiro nas duas deduziria **duas vezes**. Proporcional ao valor de cada nota?

## ⚪ Cadastro e efetivo

### 9. Prime Arena tem 4 alocados e 8 trabalhando
Faltam quatro alocações. Gente sem alocação some da cobertura do posto, do custo do contrato e
da dedução do INSS. Laranjeiras tem 9 no sistema e 8 na planilha.

### 10. 857 dos 867 produtos não podem sair numa NF-e
Não casam com nenhuma nota de compra, então não se sabe como a mercadoria entrou — e sem isso
o CFOP/CST de saída seria chute. Importar as notas de entrada que faltam, ou registrar à mão.

### 11. Uma linha do cronograma sem empresa
**Prime Arena · Manutenção · R$ 1.084,50** ("manutenção do motor de portão de entrada") não tem
dados bancários na descrição. Eletrônica ou Patrimonial?

### 12. Os 9 produtos com CST 20/41/50/400
Dependem de habilitação da empresa na SEFAZ-AM. Copiar o benefício do fornecedor seria usar
incentivo alheio — o sistema recusa e pergunta, de propósito.

---

## 13. ⚠️ A dedução do INSS na tela do lote lê a fonte de alocação mais POBRE

**Achado em 25/09/2026, cruzando com a sessão do t6.**

`modules/fiscal/services/nfse_lote.py` — a tela que propõe as 14 notas do mês com a dedução de
VA/VT já calculada — liga benefício a cliente pelo caminho:

```
folha_beneficio_conferencia → employee_alocacoes → condominios → clients
```

O autor foi cuidadoso: filtra por **vigência na competência**, não pelo estado de hoje. Mas a
tabela escolhida é a errada. Medido:

| | linhas | com `posto_id` | pessoas |
|---|---|---|---|
| `employee_alocacoes` | 73 | **0** | 62 |
| `allocations` | 89 | 89 | 86 |

**`posto_id` está vazio nas 73 linhas** — ela só sabe o condomínio, não o posto. E a sessão do t6
provou por evidência física (batida com `posto_nome` + comunicado do próprio no grupo) que ela
**não acompanha mudança de posto**: o Mauricio mudou para Green Hills em setembro e ela ainda diz
Mirante.

**Consequência:** o VA/VT de quem mudou de cliente no meio do mês é somado no cliente errado. A
dedução do INSS sai errada nos dois — a maior e a menor. Dedução a maior é glosável; a menor
paga imposto a mais. Os dois lados do que o dono pediu para evitar.

**A régua certa já existe e é de outra frente.** A AA6 (`va_vt_contrato.py`) apura por
**pessoa × dias de ESCALA no posto**, e mediu por que a escala vence:

> «no Laranjeiras erra 0,5% no VT e 2,6% no VA; no Ideal Flores 1,4% e 2,9%… `allocations` põe
> RILEM FERREIRA no Ideal Flores e a escala mostra os 16 plantões dele no Prime Arena»

Quando uma pessoa serve mais de um cliente no mês, **só a escala sabe onde ela esteve em cada dia**.

**O que fazer:** `nfse_lote.beneficios_por_tomador` deve consumir a apuração da AA6 em vez de
somar por alocação. Não fiz agora — a tela está em uso e a troca precisa de oráculo que prove o
número antes e depois, contra as três linhas reais do cronograma do dono. **Frente própria.**

**Enquanto isso, o que protege:** a tela mostra as **duas contas lado a lado** (a da folha e a que
o dono digitou) e **não escolhe** — quem escolhe é ele, que assina. Foi desenho consciente do
autor, e é o que impede o erro de virar nota.

---

## 14 · Endereço da Conecta Mais Eletrônica — ✅ **RESOLVIDO em 25/09/2026**

**Medido em 25/09/2026**, nos documentos que o próprio fisco emitiu:

| Fonte | Endereço |
|---|---|
| ERP (`empresas`), antes de hoje | Avenida Constantino Nery, 3343 — Chapada — CEP 69050-001 |
| DANFE da NF-e 10.026 (SEFAZ-AM, 17/09/2026) | **Rua Nova Palestina, 51 — Crespo — CEP 69073-488** |
| NFS-e 121 (ADN, competência 09/2026) | **o mesmo** |

**O que eu fiz:** corrigi o ERP para dizer o que o fisco já registrou, porque o endereço do
emitente vai **dentro do XML assinado** e nota autorizada com endereço fora do cadastro é
documento fiscal errado — que não se corrige editando campo.

**DECISÃO DO DONO, 25/09/2026:** *«o endereço certo é o da nova palestina, pode seguir»*.

O cadastro do ERP **já estava correto** desde a manhã — eu o havia alinhado ao que o fisco
registra, e a confirmação dele fecha a dúvida sem nenhuma mudança adicional. A Constantino
Nery era o dado errado, não uma mudança de sede: nada a fazer na Receita.

> **Esta era a única pendência que travava a primeira NF-e real.** Com ela fechada, o caminho
> está livre — o que não é ordem de emitir: quem manda é o dono.

A Patrimonial tinha rua e número certos e o **CEP vazio**; preenchido com 69055-630, da NFS-e 31.

---

## 15 · 8 produtos que não podem ser emitidos até alguém dizer o tratamento de saída

O catálogo fiscal tem 94 produtos ativos. **86 emitem**; estes 8 são recusados porque entraram
com um CST que **não tem regra de saída com fonte** — e o sistema recusa em vez de inventar,
que é o comportamento certo. NCM/CST chutado foi exatamente a rejeição da SEFAZ de 11/04/2026.

| CST de entrada | Código | Produto |
|---|---|---|
| *(vazio)* | EPI-001 | COLETE REFLETIVO TAM M |
| 20 (redução de BC) | 108662 | LUVA ALGODÃO 4 FIOS BRANCA |
| 20 | VTV-213 | CÂMERA BULLET METAL IP 4MP |
| 20 | VTV-074 | NVR 16CH 4K |
| 400 (CSOSN — não tributada no Simples) | 2011 | TORRE PLUG IN PLAY |
| 41 (não tributada) | 11838 | FONTE 5V 3A USB TIPO C |
| 50 (suspensão) | VTV-119 | SMART FITA LED WI-FI RGB |
| 50 | VTV-117 | SMART LÂMPADA RETRO 11W |

**O que decidir:** para cada um desses CST de entrada, qual é o CST de **saída** e por quê.
Não é escolha de programador — depende de *por que* a entrada foi assim, e a resposta certa
economiza imposto (ou evita pagar a mais). Vale levar ao contador junto com os XML de entrada.

> Enquanto não houver decisão, esses 8 aparecem na tela e a emissão recusa com mensagem que
> ensina. Nenhum deles é inventado para «destravar».

---

## 16 · Markup: 40% é regra da casa ou varia?

O campo nasce com **40%**, o número que o dono citou. Se variar por fornecedor, por linha de
produto ou por cliente, isso vira parâmetro — e parâmetro se lê do cadastro, não se adivinha.

**Lembrete que vale dinheiro:** markup ≠ margem. 40% de markup sobre custo 100 dá preço 140,
que é **28,6% de margem** sobre a venda. Para 40% de *margem*, o markup tem de ser **66,7%**.
O sistema devolve os dois números escritos justamente para essa conta não sair torta.

---

## 17 · 13 clientes sem endereço completo — NF-e de mercadoria exige

Dos 29 clientes, **15 têm endereço completo**, 1 foi preenchido das notas do fisco (Parque dos
Franceses) e **13 não têm nota que os diga** — esses só digitando:

ASSOCIACAO BRASIL SGI · CONDOMINIO DO CONJUNTO DOS JORNALISTAS · CONDOMÍNIO RESIDENCIAL PRAIA
DOS PASSARINHOS · Condomínio Park Village · Condomínio Residencial Smile Parque das Flores ·
Condomínio Residencial The Sun · Condomínio do Edifício Rio Jaguaribe · GRUPO PARVI · HAWK EYE ·
RAÇÃO CONFIANÇA AGROINDUSTRIAL LTDA · VEGA MANAUS TRANSPORTE DE PASSAGEIROS LTDA
*(mais 2 cadastros de teste: CONECTA MAIS - SEGURANCA E TECNOLOGIA e HOMOLOGACAO)*

**Divergência verdadeira, para o dono decidir:** o cadastro do **Parque dos Franceses** diz
logradouro «Rua Parque dos Franceses»; a NFS-e 121 que o fisco gerou diz **«A-1»**. Mantive o
cadastro e registrei a diferença — endereço meio-a-meio não é mais completo, é novo.

O script que faz isso a partir de qualquer nota nova:
`backend/scripts/qa/preencher_endereco_cliente_das_notas.py` (sem `--aplicar` só mostra).

---

## 18 · Buscar o XML assinado das 114 NFS-e restantes?

**Medido em 25/09/2026:** `nfse_emitidas_nacional` tem **123 notas** — 115 de produção e 8 de
homologação — e **nenhuma** tinha o XML assinado guardado. Busquei **uma** (a nº 99, Villa dos
Pássaros, 06/2026) pela rota, o ADN devolveu, gravou, e o DANFSe v2.0 saiu completo.

**Por que importa:** metade dos blocos do DANFSe v2.0 — tributação municipal, federal, IBS/CBS,
NBS, código de tributação nacional — **só existe no XML**. A tabela guarda 12 campos. Sem o
XML, o documento que vai ao condomínio sai pela metade.

**O que decidir:** autoriza buscar as 114 restantes? É **uma chamada ao portal nacional por
nota**, leitura pura (`GET /nfse/{chave}`), nada é alterado no fisco. Não disparei por conta
própria: 114 chamadas a órgão público merecem ser agendadas e paceadas, não disparadas por uma
frente de PDF.

Faz diferença prática se os kits do GEDEON passarem a levar o DANFSe ao condomínio.

---

## 19 · Modelo do DANFE — **RESOLVIDO em 25/09/2026**

Dono: *«vamos usar o modelo 4, apenas centralize a logo, está perfeito esse modelo»*.

É o padrão do botão «DANFE (PDF)»: marca centrada em faixa própria, emitente centralizado, QR
de consulta ao lado das barras, assinatura do Conecta PRO no pé da folha (fora do quadro
fiscal). `?marca=inline` devolve o formato anterior, para comparação.

**Fica em aberto, se ele quiser mexer:** o telefone `(92) 3221-2100` aparece na caixa do
emitente porque está no cadastro — o DANFE que a Portte emite deixa esse campo vazio.
