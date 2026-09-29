# Roteiro dos portais — 29/09/2026

Faça na SUA máquina. O servidor está bloqueado por IP no gov.br, isso já está provado.
Ordem por urgência. O item 1 é o que vence primeiro.

---

## 1. CRF/FGTS da PATRIMONIAL — vence em 5 dias (04/10)

É a certidão que o condomínio exige para pagar a fatura e que licitação pede.
A Caixa recusa o IP do nosso servidor (HTTP 403), então só sai da sua máquina.

**Site:** https://consulta-crf.caixa.gov.br/consultacrf/pages/consultaEmpregador.jsf

1. CNPJ: **66.014.833/0001-10**
2. Emitir a certidão e salvar o PDF.
3. Subir o PDF na pasta do Drive da Portte (a mesma dos outros documentos).

O nosso puxador reconhece pelo conteúdo e atualiza a validade sozinho.

> Também vencida, se quiser aproveitar: **certidão de falência** da Patrimonial,
> venceu 18/09. Não é exigida pela nossa régua, mas edital de licitação costuma pedir.

---

## 2. PROCURAÇÃO ELETRÔNICA — é ela que me destrava o resto

**Site:** https://cav.receita.fazenda.gov.br/

Entre com o **certificado A1 da PATRIMONIAL** instalado na sua máquina:
clique em "Entrar com gov.br" e depois em "Seu certificado digital".

Dentro do e-CAC, menu **Autorizações de Acesso (Procurações)** → cadastrar procuração eletrônica.

| campo | valor |
|---|---|
| Outorgante | CONECTAMAIS PATRIMONIAL — **66.014.833/0001-10** |
| Outorgado | CONECTAMAIS ELETRONICA — **35.710.481/0001-03** |
| Serviços | PGDAS-D e Defis · Situação Fiscal · Certidões · Parcelamentos · DCTFWeb · Caixa Postal |
| Validade | 5 anos |

Vale na hora. Depois dela, a sessão da Eletrônica que já funciona no servidor passa a
trocar de perfil para a Patrimonial, e eu leio tudo sozinho — essa etapa nunca mais
precisa de você.

---

## 3. RBT12 — aproveite que já está logado como Patrimonial

Não espere a procuração para isto. Estando dentro do e-CAC como a Patrimonial:

Menu **Simples Nacional** → **PGDAS-D e Defis 2018** → apuração de **08/2026**
(ou o extrato / a declaração completa, não o recibo).

**Me mande dois números:**
- **RBT12** (receita bruta dos últimos 12 meses)
- **alíquota efetiva** aplicada

Por que preciso: o recibo do PGDAS-D que já temos no Onvio só traz a receita do mês
(R$ 255.400,06 em 07/2026). O RBT12 não está nele, e sem ele metade da cotação por
WhatsApp usa tabela genérica em vez do número real da empresa. Não vou estimar esse
número: tentei deduzir pela alíquota do DAS e não bateu com a receita das notas.

---

## 4. DAM do ISS — o único prazo cego que sobrou

É da **ELETRÔNICA**, competência **08/2026**, venceu **10/09**. Está no sistema sem valor
porque o DAM só nasce no portal da SEMEF, e o nosso CNPJ **não tem Senha Web cadastrada**
(o portal responde "CPF/CNPJ não possui senha cadastrada").

**Site:** https://nfse.manaus.am.gov.br/login.aspx

- CNPJ: **35.710.481/0001-03** · Inscrição Municipal: **45177801**
- Se não tiver senha: na própria tela, "Não possui senha? Informe seu CPF/CNPJ e CLIQUE AQUI"
  leva ao cadastro (https://nfse.manaus.am.gov.br/senhaweb/SolicitacaoPJ.aspx).

Depois de logado, emita o DAM do ISS de 08/2026 e suba o PDF no Drive.
O captcha de imagem desse portal eu resolvo por máquina — só a senha falta.

> Referência do que já temos: o ISS de 07/2026 foram dois DAMs, 21499343 (próprio, R$ 625,00)
> e 21499344 (retenção, R$ 115,25), total R$ 740,25, vencendo 10/08.
> A Patrimonial tem IM própria (**721042001**), caso precise um dia.

---

## O que NÃO precisa fazer

Não tente mais o login por certificado pelo servidor. Quatro tentativas suas, navegador
limpo, sempre "Captcha inválido (ERL0033800)". O gov.br recusa a origem de rede daqui e
chegou a devolver o nosso IP na mensagem. O problema não é o certificado nem o captcha.
