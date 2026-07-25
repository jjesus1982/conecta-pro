## Conhecimento: Estrutura societária (Grupo Conecta Mais)

- **CONECTAMAIS ELETRONICA LTDA** (CNPJ1) — 35.710.481/0001-03, Manaus-AM. Regime **LUCRO REAL desde 01/01/2026**, com plano de voltar ao **Simples** no futuro. Banco **Inter** (bank_code 077). Fica com **Segurança Eletrônica + Portaria Remota** (+ quadro PJ/DEV/técnico). empresas.id `619a3df1-8bce-49ce-b77a-04f80a0e8491`.
- **CONECTAMAIS PATRIMONIAL LTDA** (CNPJ2) — 66.014.833/0001-10, **SIMPLES Anexo III**, CNAE 8111-7/00 (serviços humanizados: agente de portaria, auxiliar/agente de serviços gerais, artífice, jardineiro, líder de portaria). Banco **Cora** (bank_code 403). empresas.id `7d79ed12-d480-4906-b2e0-2b2c4d299bab`.
- Estrutura societária e regime vigentes são consultados ao vivo (cadastro `empresas`, campo fonte de verdade); este arquivo só fixa o que é estável — não repita saldo/regime aqui se puder mudar sem aviso.
- Cora **não envia PIX** e exige aprovação dentro do próprio app do banco — isso é uma limitação operacional do CNPJ2, não um bug do ERP.

## Conhecimento: Tributos e retenções sobre a folha (fixos)

- ISS é recolhido em **Manaus**.
- Retenção previdenciária de **11%** na cessão de mão de obra (nota de serviço).
- **FGTS 8%** sobre a folha.
- IRRF conforme tabela vigente.
- Contabilidade: **Portte** (consultoria permanente).
- CCT **SINDECOMPRESTS AM000613/2025** — piso 2026 = **R$ 1.670,00** — categoria **agentes de portaria** (não vigilância). A folha é o maior custo da operação.

## Conhecimento: Situação da liminar PIS/COFINS/INSS da Patrimonial

- A liminar que pediria a suspensão de PIS/COFINS e o fim da retenção previdenciária em dobro para a Patrimonial **deu entrada mas AINDA NÃO FOI OBTIDA/DEFERIDA** (posição em 2026-07).
- Enquanto não deferida: a Patrimonial **continua sofrendo retenção normal**, o **INSS incide em dobro** (uma vez na nota de serviço/retenção de 11%, outra vez dentro da guia do Simples/DAS) e o **DAS é recolhido integral** (PIS/COFINS não estão zerados).
- NUNCA afirmar "liminar zerou PIS/COFINS" ou "INSS não retido" para a Patrimonial — isso é um erro de fato conhecido. Se perguntarem sobre o status da liminar, responder o estado acima e, se precisar de data/andamento processual, dizer que não está no contexto.

## Conhecimento: Transição de competência (jan–jun/2026)

- Jan–maio/2026: folha era da **Eletrônica**.
- Junho/2026 (fechada em julho/2026): **1ª folha como Patrimonial**.
- Folha/ponto/NFS-e das funções humanizadas estão migrando para a Patrimonial ao longo de julho/2026; depois disso a CNPJ1 (Eletrônica) volta ao Simples.
- O roster CLT ativo já é tratado como Patrimonial.
- Datas/competências exatas de corte além do que está acima: consultar o cadastro vivo — não cravar aqui.

## Conhecimento: Governança financeira

- Acesso a caixa/aging/pagamentos (visão financeira completa) é restrito à diretoria (Jordan e Pyetra).
- Toda saída de dinheiro (PIX/pagamento) exige aprovação humana com OTP — nenhuma ferramenta do CFO IA executa pagamento; o papel do CFO IA é diagnosticar e recomendar.

> _(aguardando confirmação Jordan: alíquotas específicas de IRRF por faixa, CNAE completo da Eletrônica, data exata prevista para a decisão/deferimento da liminar)_

## Playbook: fechamento do mês

Situação: gestor pede "fecha o mês" ou "como estamos financeiramente".

Passos:
1. Puxar o **saldo em conta por CNPJ** via tool de leitura financeira (Inter = Eletrônica, Cora = Patrimonial) — nunca estimar, só usar o que a tool retornar agora.
2. Puxar recebíveis (a receber/vencidos) e pagáveis (a pagar/vencidos) do período via tool de leitura.
3. Rodar a conciliação bancária disponível e reportar divergências como fato, não como suposição.
4. Calcular aging de recebíveis e apontar concentração de inadimplência, se houver.
5. Redigir o fechamento em formato CFO (Diagnóstico / Números-chave com fonte / Recomendação / Riscos / Próximos passos).

O que verificar antes de concluir:
- Todo número citado tem fonte explícita (ex.: "saldo Inter", "aging Cora").
- Nenhum valor foi arredondado ou "chutado" quando a tool não devolveu dado — nesse caso, declarar "esse dado não está no sistema".
- Se envolver decisão de regime tributário, endividamento, distribuição de lucro ou corte de folha: sinalizar ALTO RISCO e recomendar validar com a contabilidade (Portte).

Ação: este playbook é **só leitura e relatório** — o CFO IA nunca paga, transfere ou baixa nada. Se a conversa evoluir para "então paga/cobra", a via é o consultor comercial/operacional propor (ex.: `propor_cobranca`), nunca o CFO executando.

## Playbook: apuração de tributos por CNPJ

Situação: pergunta sobre quanto/como recolher tributos no mês.

Passos:
1. Confirmar o CNPJ em questão (Eletrônica = Lucro Real; Patrimonial = Simples Anexo III).
2. Para a Patrimonial: lembrar que o DAS é **integral** e o INSS incide **em dobro** enquanto a liminar não for deferida — nunca dizer que está zerado.
3. Para a Eletrônica: tributos apurados no regime Lucro Real (ISS Manaus, FGTS 8%, INSS 11% na cessão de mão de obra, IRRF).
4. Puxar os valores do mês via tool ao vivo (nunca hardcoded); se não disponível, declarar isso.
5. Recomendar confirmação final com a Portte antes de qualquer decisão de mudança de regime.

O que verificar: nunca declarar "liminar concedida"/"PIS/COFINS zerado" para a Patrimonial sem confirmação explícita nova do Jordan.
