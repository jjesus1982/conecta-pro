## Conhecimento: os dois CNPJs do Grupo

- **CONECTAMAIS ELETRONICA LTDA** (CNPJ1) — 35.710.481/0001-03, Manaus-AM. Regime **LUCRO REAL desde 01/01/2026**, com plano de retorno futuro ao Simples. Banco **Inter**. Fica com **Segurança Eletrônica + Portaria Remota** (+ quadro PJ/DEV/técnico). empresas.id `619a3df1-8bce-49ce-b77a-04f80a0e8491`.
- **CONECTAMAIS PATRIMONIAL LTDA** (CNPJ2) — 66.014.833/0001-10. **Simples Nacional, Anexo III**, CNAE 8111-7/00, serviços humanizados (agente de portaria, auxiliar/agente de serviços gerais, artífice, jardineiro, líder de portaria). Banco **Cora**. empresas.id `7d79ed12-d480-4906-b2e0-2b2c4d299bab`.
- Para uma visão consolidada ("o grupo"), lembrar que os dois CNPJs têm regimes, bancos e riscos tributários diferentes — nunca somar caixa/regime sem explicitar que é "GRUPO (consolidado)".

## Conhecimento: transição de competência em curso (julho/2026)

- Jan–maio/2026: folha apurada pela Eletrônica.
- Junho/2026 (fechada em julho/2026): 1ª folha apurada como Patrimonial.
- Folha/ponto/NFS-e das funções humanizadas migram para a Patrimonial ao longo de julho/2026; depois disso a Eletrônica volta ao Simples.
- O roster CLT ativo já é tratado como Patrimonial.

## Conhecimento: risco tributário aberto (Patrimonial)

- A liminar de PIS/COFINS/INSS da Patrimonial **deu entrada mas não foi deferida** (posição 2026-07). Enquanto isso: retenção normal, **INSS em dobro**, **DAS integral**. Este é um risco/custo ainda ativo — nunca reportar como resolvido no panorama executivo.

## Conhecimento: base trabalhista e governança

- CCT **SINDECOMPRESTS AM000613/2025** — categoria agentes de portaria (não vigilância), piso 2026 = R$ 1.670,00.
- Governança financeira: caixa/aging/pagamentos restritos à diretoria (Jordan + Pyetra); toda saída de dinheiro exige OTP humano.
- Operacional (postos/alocações) é curado à mão pelo Jordan e é read-only para agentes — divergência vira relatório, não correção automática.
- Jordan é a fonte da verdade para dado organizacional.

> _(aguardando confirmação Jordan: metas/OKRs formais do trimestre, roadmap de expansão além do que já está registrado no sistema)_

## Playbook: panorama consolidado

Situação: "me dá o panorama da empresa" / visão executiva pedida pelo CEO/diretoria.

Passos:
1. Puxar, via tools de leitura de cada módulo (financeiro, comercial, operacional, DP/RH, jurídico), os números reais do período — nunca compor um número que nenhuma tool retornou.
2. Separar a visão por CNPJ quando o tema for financeiro/tributário (Eletrônica x Patrimonial); usar "GRUPO (consolidado)" só quando for uma soma explícita e sinalizada como tal.
3. Trazer o status da transição de competência (qual folha/CNPJ está vigente) e o status do risco da liminar da Patrimonial, sempre que relevante ao panorama.
4. Sintetizar em formato executivo: diagnóstico, números-chave com fonte, riscos, recomendações — nunca decisão automática.

O que verificar antes de concluir:
- Nenhum valor financeiro/operacional volátil foi hardcoded neste playbook nem inventado na resposta — tudo vem de tool ao vivo.
- A liminar da Patrimonial nunca é descrita como deferida/zerada.

Ação: este playbook é **só leitura** — o panorama é para informar a decisão da diretoria, nunca para executar ação (pagamento, contratação, corte) diretamente. Qualquer ação decorrente segue o fluxo propor→aprovar do módulo específico (financeiro, comercial, operacional, ged, etc.).
