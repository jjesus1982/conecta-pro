---
name: conferir-kit-documental
description: Conferir o kit documental mensal de um condomínio da Conecta Mais (MCP ged) — ordem das tools, as 5 regras do dono checadas arquivo por arquivo, e os erros já vistos.
---

# Conferir kit documental — Conecta Mais

## Quando usar
Quando pedirem para "conferir o kit" de um condomínio numa competência (MM.AAAA) ou
"como estão os kits do mês". Papel do conferente: emitir parecer (veredito + achados +
faltando) ancorado no que as tools devolveram. Nunca preencher lacuna com suposição.

## Ferramentas (MCP `ged`)
- `cronograma_kit(competencia)` — prazos do mês: salário no 5º dia útil, VT/VR dia 16,
  prazo de assinatura 48h. Diz o que já dá para cobrar.
- `consultar_kit(condominio, competencia)` — base da conferência: % de completude,
  checklist (presente/falta), eventos do mês (contratações, demissões, férias) e a lista
  de arquivos no Drive COM `file_id`.
- `consultar_kits(competencia)` — panorama dos condomínios (completude, completos, pendentes).
- `status_coleta(task_id)` — acompanhar coleta/montagem em andamento.
- `buscar_documento(condominio, tipo)` — robô coleta UM tipo só daquele condomínio.
- `montar_kit_completo(condominio?, competencia?)` — monta tudo (~3 min, devolve task_id).
- `excluir_documento(condominio, file_id)` — manda arquivo errado para a lixeira do Drive
  (recuperável). Use o `file_id` do `consultar_kit`.
- `registrar_evento_kit(condominio, tipo, descricao)` — registra evento no checklist
  (contratacao, demissao, ferias, atestado, observacao...).

## Ordem
1. Confirmar condomínio e competência (sem competência, o kit usa o mês corrente).
2. `cronograma_kit` → prazos do mês.
3. `consultar_kit(condominio, competencia)` → completude, checklist, eventos, arquivos.
4. Se vier vazio (0 arquivos, 0%, nenhuma subpasta com conteúdo) → kit VAZIO: veredito
   reprovado, `faltando` = o checklist inteiro. Reportar também os eventos e os prazos
   vencidos. NÃO inventar conteúdo nem "deduzir" o que deveria estar lá.
5. Para cada arquivo, checar as 5 regras (abaixo), arquivo por arquivo.
6. Emitir parecer: veredito (aprovado/reprovado) + achados (o que está errado, com
   `file_id` quando houver) + faltando. Ação corretiva (coletar de novo / excluir errado)
   é proposta com base no `file_id`, nunca escrita às cegas.

## As 5 regras do dono (checar arquivo por arquivo)
Cada regra nasceu de um defeito real — todas são verificáveis no `consultar_kit`.

1. PASTAS. Dentro de "<AAAA-MM> Kit Documental" existem exatamente cinco:
   - **Funcionarios** → tudo que é da pessoa (contracheque, folha de ponto, recibo de
     adiantamento, comprovante de pagamento, recibo de VT/VR) e os consolidados da folha.
   - **Certidoes** → só certidão negativa da empresa (CND federal/estadual/municipal,
     CRF FGTS, CNDT).
   - **Guias** → guia de recolhimento e o comprovante de pagamento dela (DARF, DCTFWeb,
     FGTS, INSS, ISS, DAS). **Guia NUNCA vai para Financeiro.**
   - **Beneficios** → a EMPRESA comprando e distribuindo VT/VA: boleto e relatório
     SINETRAM, relatório Sólides e os comprovantes de pagamento dos dois.
   - **Financeiro** → só o que a Conecta Mais COBRA do condomínio: a NFS-e e o boleto
     do mês.
2. COMPETÊNCIA. Todo arquivo é da competência do kit — ou da anterior quando for GUIA
   (a guia de agosto recolhe julho). Documento de outro ano no kit do mês é erro.
3. NOME. O nome é o que o síndico lê. Nome interno de coletor (hash / CNPJ cru, ex.
   "cnd_receita_61e697a58521.pdf") não serve.
4. ESCALA de trabalho NÃO vai no kit. Folha de ponto vai.
5. ASSINATURA. Contracheque, folha de ponto, recibo de adiantamento e recibos de VT/VR
   são assinados pelo funcionário; folha de ponto e recibo de adiantamento levam TAMBÉM
   a assinatura da empresa com ICP-Brasil.

## Erros já vistos
- **Kit vazio (CONECTA VILLAGE (TESTE), 08.2026):** `consultar_kit` devolveu 0 arquivos,
  completude 0% e nenhuma subpasta com conteúdo, apesar de 12 contratações registradas em
  01/08/2026 e prazos já vencidos (ponto 10/09, VT/VR 16/09). Parecer: reprovado, com os
  10 documentos do checklist em `faltando` (folha, contracheques, comprovantes de salário,
  ponto, VT/VR, guias, comprovante INSS, certidões, NFS-e, boleto).
- Defeitos que cada regra existe para pegar: guia arquivada em Financeiro; documento de
  outro ano no kit do mês; arquivo com nome-hash do coletor; escala de trabalho no lugar
  da folha de ponto; documento sem assinatura do funcionário e sem ICP-Brasil.

## Pitfalls
- Kit vazio NÃO é aprovado silencioso: sem arquivo, `faltando` é o checklist inteiro.
- Não confundir "reprovado porque vazio" com "ainda não coletado" — o kit pode não ter
  sido montado ainda (`montar_kit_completo` / `buscar_documento`). Reportar o estado real
  como fato; se não der para distinguir, dizer que não dá e apontar a coleta.
- Silêncio do checklist não é prova de nada: só vale o que a tool devolveu, com a fonte.
