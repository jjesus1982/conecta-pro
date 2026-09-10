# Conecta PRO — o que eu já sei desta casa

## Estrutura
- Conecta Mais Eletrônica — CNPJ 35.710.481/0001-03 (segurança eletrônica).
- Conecta Mais Patrimonial — CNPJ 66.014.833/0001-10 (mão de obra humanizada).
- 16 contratos ativos · 65 colaboradores ativos.
- Mão de obra humanizada sai pela Patrimonial; segurança eletrônica, pela Eletrônica.
  Contrato emitido pelo CNPJ errado é erro grave — a regra decide, não o cadastro.

## Regras que não se negociam
- Dinheiro que SAI (PIX, pagamento) nunca é executado por mim: só proponho.
  Execução real exige humano com OTP, fora deste agente.
- Emissão de contrato é restrita a Jordan e Pyetra.
- Postos, alocações, escalas e dossiê jurídico são curados à mão: para mim são somente leitura.
  Divergência vira relatório, nunca correção automática.
- Nunca fabricar dado. Vazio real se diz 'aguardando dado'; número inventado é pior
  que célula em branco.

## O que o Jordan já rejeitou — a lição, não a lista
- **36 de 36 propostas de "dar baixa" em conta a pagar foram REJEITADAS.** Nenhuma passou.
  Não proponha baixa automática de pagável: o comprovante do emissor é que quita a conta,
  não a inferência de que o valor bate. Status de pagamento é decisão do financeiro.
- 1 recomendação de risco e 1 cobrança também recusadas. O único rascunho já EXECUTADO em
  44 foi uma cobrança — a taxa de aceite de proposta minha é de 1 em 44.
- Leitura disso: quando eu não tenho certeza, o valor está em RELATAR, não em propor ação.
  Proposta recusada custa atenção do Jordan; relatório que ele lê custa menos e serve mais.

## Como se trabalha aqui
- Medir antes de afirmar. 'Parece que funcionou' não é resultado; número é.
- Verde que não pode ficar vermelho não prova nada.
- Verificar na rota que o usuário usa, não no builder — três vezes a tela certa
  no builder era a tela errada na rota.

## Kit documental — aprendido conferindo, aprovado pelo Jordan em 10/09/2026
- Dentro de '<AAAA-MM> Kit Documental' existem exatamente 5 pastas:
  Funcionarios, Certidoes, Guias, Beneficios, Financeiro.
- Destino de cada documento:
  · **Funcionarios** — tudo que é da pessoa (contracheque, folha de ponto, recibo de
    adiantamento, comprovante de pagamento, recibo de VT/VR) e os consolidados da folha.
    A ESCALA de trabalho NÃO entra no kit.
  · **Certidoes** — só certidão negativa da empresa: CND federal/estadual/municipal,
    CRF FGTS, CNDT.
  · **Guias** — guia de recolhimento (DARF, DCTFWeb, FGTS, INSS, ISS, DAS) e o comprovante
    de pagamento dela. Guia NUNCA vai para Financeiro.
  · **Beneficios** — a empresa comprando e distribuindo VT/VA: boleto e relatório SINETRAM,
    relatório Sólides e os comprovantes de pagamento dos dois.
  · **Financeiro** — só o que a Conecta Mais COBRA do condomínio: a NFS-e e o boleto do mês.
- Competência: todo arquivo é do mês do kit, ou do anterior quando é guia (a guia de agosto
  recolhe julho). Documento de outro ano dentro do kit do mês é erro.
- Nome de arquivo é o que o SÍNDICO lê. Nome interno de coletor — hash, CNPJ cru, caixa alta
  com underscore — não serve.
- Assinatura: contracheque, folha de ponto, recibo de adiantamento e recibos de VT/VR são
  assinados pelo funcionário; folha de ponto e recibo de adiantamento levam TAMBÉM a
  assinatura ICP-Brasil da empresa.

### Defeitos que eu mesmo já vi no kit
- O robô grava o mesmo documento duas vezes: uma com nome legível e outra com nome interno de
  coletor (guias e comprovantes de DAS/DARF/FGTS). Certidões também saem em padrão técnico,
  ex. `CND-RECEITA-17-11-2026.pdf`.
- Achando duplicata, eu **RELATO no parecer — não excluo**. Decisão do Jordan em 10/09/2026,
  e a razão é medida: naquele mesmo dia, uma limpeza automática por semelhança de nome quase
  apagou as notas fiscais NFS-27 e NFS-28 achando que eram cópias da NFS-26. Eram três notas
  diferentes. Nome de arquivo não distingue documento.
- `CONECTA VILLAGE (TESTE)` é condomínio de HOMOLOGAÇÃO, não cliente real: os 12 colaboradores
  são fictícios e o kit dele mora em `_TESTE (homologação — não é cliente)`.
