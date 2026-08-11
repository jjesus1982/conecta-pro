# Fiscal / Contabilidade — fechamento do módulo (2026-08-11)

Terceira e última rodada do dia. As duas primeiras estão em `fiscal_20260809.md` e
`fiscal_multicnpj_20260811.md`. Esta fecha o módulo e encontra o defeito mais caro.

## O padrão que atravessa tudo o que se achou hoje

**Cinco componentes afirmavam coisas que não tinham como saber.** Não era código quebrado —
era código *confiante*. Cada um produzia um número ou um veredito plausível, e nenhum tinha
como estar certo:

| Componente | O que afirmava | O que sabia |
|---|---|---|
| KPI "Obrigações em aberto" | 31 pendentes | filtro com 4 grafias de "feito", nenhuma a real |
| KPI "Faturamento 12m" | R$ 3,0 mi | 12 meses a partir da última nota **arquivada** |
| `sefaz_am_client` | "regular", validade 07/02/2027 | nada — respondia igual para CNPJ inexistente |
| `prefeitura_manaus_client` | "irregular" | nada — respondia igual para o Banco do Brasil |
| Balanço Patrimonial | PL de **+R$ 2,02 milhões** | receita classificada como despesa negativa |

O denominador comum: **fallback silencioso**. Sem data do órgão → inventa 180 dias. Sem
conta no grupo esperado → ignora. Sem resposta do portal → assume regular. Cada fallback
transformava ausência de informação em afirmação.

## O defeito mais caro: o balanço

```
ANTES   Ativo 182.751,34 ≠ Passivo 279.818,06 + PL 2.020.962,77     "Não fecha"
DEPOIS  Ativo 182.751,34 = Passivo 279.818,06 + PL   −97.066,72     "Fecha ✓"
```

A classificação era pelo **primeiro dígito** do código, assumindo 3=Receita e 4=Despesa. O
plano desta empresa usa **4=Receita e 5=Despesa**, e não tem grupo 3. Resultado: a receita
virou despesa negativa e virou o "PL"; as 12 contas de despesa (R$ 2.118.029,49) sumiram.

**O sistema mostrava patrimônio de R$ 2 milhões onde há prejuízo de R$ 97 mil.**

A tela já dizia "Não fecha" desde sempre — e a diferença ERA o defeito. Ninguém investigou
porque um balanço que não fecha parece problema de lançamento, não de tela.

Agora a classificação vem de `fin_accounting_accounts.account_type`, que o plano declara
por conta. Conta com movimento e sem classificação passa a ser denunciada no subtítulo.

## Certidões: o que foi obtido e o que foi desfeito

Tentativa de cadastrar as que faltavam na Patrimonial expôs a fabricação:

- O sync gravou **4 certidões parecendo válidas até 2027** com o portal fora do ar
  (`indeterminado_portal_indisponivel`) e uma com a empresa `irregular`. Desfeitas.
- Duas fontes de portal davam veredito sobre CNPJ que nunca consultaram. Corrigidas: sem
  **data de validade no documento**, não há veredito. (Exigir que o HTML cite o CNPJ não
  bastou — o portal ecoa a query string de volta.)

**Obtido de verdade, via Infosimples** (token já existia; só endpoints de PF estavam ligados):

| | Documento |
|---|---|
| Patrimonial — CRF-FGTS | nº 2026080707256551439450, emitida 07/08, vence **05/09/2026** |
| Eletrônica — CRF-FGTS | vence **24/08/2026** — nunca esteve vencida; o registro é que estava velho |

Patrimonial: 1 → 3 certidões. Resta o **Alvará** da Eletrônica (vencido 28/02) — renovação
presencial, sem API.

## Veredito por lente

| Lente | Status | Evidência |
|---|---|---|
| **DADO** | ✅ | 7/7 oráculos verdes. Quatro são novos e todos provados contra o código anterior |
| **TELA** | ⚠️ parcial | Playwright MCP indisponível nesta sessão. Verificado pela rota real do dispatcher com token válido após bake — "API 200", que pela regra da casa não é "entregue" |
| **CÓDIGO** | ✅ | `ruff` limpo nos arquivos novos; E702 do `_fin_contabil` é pré-existente (12 na base → 11 agora) |

Oráculos do módulo: `test_oraculo_contabil_fecha`, `test_oraculo_portais_nao_chutam`,
`test_oraculo_cnd_nao_fabrica`, `test_oraculo_fiscal_painel`,
`test_oraculo_fiscal_multicnpj`, `test_u2_fiscal`, `test_u2_financeiro`.

O contábil trava a **identidade** (A = P + PL), não valores: mês novo entra sozinho, erro de
classificação futuro reprova sozinho.

## Erros meus nesta rodada, e o que ensinaram

1. **Anunciei "CRF-FGTS renovada"** com base no retorno do sync. O portal estava fora do ar.
   Lição: `status: "criada"` não é evidência — a evidência é o número do documento.
2. **Apaguei uma certidão legítima** na limpeza (filtro por nota pegou a Trabalhista da
   Patrimonial). Restaurada com registro do ocorrido; **precisa conferência manual no TST**.
3. **Primeira guarda dos portais foi insuficiente** — exigi que o HTML citasse o CNPJ, e o
   portal ecoa a query string. Só a exigência de data resolveu.

## Achados que NÃO são código (ficam com o Jordan)

1. **R$ 458 mil em contas transitórias**: R$ 141.355,52 em "Entradas a Classificar" e
   R$ 317.205,47 em "Saídas a Classificar", esperando classificação contábil.
2. **A Patrimonial não tem obrigação fiscal cadastrada** — fatura R$ 443 mil e é Simples
   (DAS mensal). O sync sabe rotear por CNPJ; o dado é que não chegou.
3. **Guias pararam**: FGTS em 12.2025, INSS em 11.2025. Nada de 2026.
4. **Obrigações param na competência 06/2026**; última criação em 17/07.
5. **Zero NFS-e em agosto** nas cinco tabelas (última: 31/07).
6. **Alvará vencido desde 28/02** — renovação presencial.
7. **CND Estadual e Municipal viraram emissão manual** — não há fonte que responda.

## Não coberto

- Navegador real (sem Playwright nesta sessão).
- Correção dos números fiscais em si — que a alíquota do Anexo III esteja certa é
  conferência de contador, não de QA. O que se prova aqui é exibido == banco.
- Os outros consumidores de `sefaz_am_client`/`prefeitura_manaus_client`, se existirem fora
  do fluxo de CND, herdam a correção mas não foram auditados um a um.
