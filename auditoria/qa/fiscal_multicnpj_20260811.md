# Fiscal — fechamento multi-CNPJ (2026-08-11)

Skill `fecha-modulo`, três lentes. Mapa do módulo por `graphify` (AST, 123 nós), plano em
`docs/superpowers/plans/2026-08-11-fiscal-dois-cnpjs.md`, execução em loop.

## O que mudou a leitura do módulo

O grupo tem DOIS CNPJs desde 2026 e **nenhuma tela fiscal dizia de qual empresa era a linha**.
O painel somava, e a soma escondia exatamente o que importa:

| | Eletrônica `35.710.481` | Patrimonial `66.014.833` |
|---|---|---|
| Certidões | 8 (3 **VENCIDAS**) | **1** de 8 tipos |
| Obrigações fiscais | 31 (5 pendentes) | **ZERO** |
| NFS-e 2026 | 83 · R$ 1.544.613,06 | 16 · R$ 443.381,11 |
| Regime | Lucro Real | Simples Anexo III |

A Patrimonial **fatura R$ 443 mil e não tem nenhuma obrigação fiscal cadastrada** — sendo
Simples, que deve DAS todo mês. E tem 1 dos 8 tipos de certidão: sem CRF-FGTS nem CND Federal
não se fatura em cliente grande nem se entra em licitação.

Vencidas na Eletrônica: **CRF-FGTS (09/08)**, **Neg. Estadual (09/08)** — anteontem — e
Alvará (28/02).

## Achados anteriores, na mesma rodada

| Achado | Medido | Estado |
|---|---|---|
| "Obrigações em aberto: 31" | verdade 5 — filtro excluía 4 grafias de "feito" e errava a única real (`cumprida`) | ✅ corrigido |
| "Faturamento (12m)" | ancorava na última nota do ARQUIVO (29/12/2025), ignorava as 99 notas de 2026 | ✅ corrigido |
| 3 certidões vencidas | painel mostrava "9" em verde | ✅ corrigido |
| 99 NFS-e de 2026 | existiam só como CONTAGEM no KPI — nenhuma tela para clicar | ✅ tela criada |

## O que foi entregue

- **`painel-por-empresa`** — uma linha por CNPJ com certidões, vencidas, obrigações e
  faturamento 12m daquela empresa. Empresa que emite nota e não tem obrigação nenhuma vira
  alerta *"sem obrigação cadastrada"*; um zero silencioso passaria por "nada a pagar".
- **`certidoes-cobertura`** — matriz tipo × empresa. `FALTA` = nunca cadastrada, `VENCIDA`
  com a data. 7 faltas visíveis. Catálogo sai do banco, não de lista fixa.
- **`nfse-emitidas`** — as 99 notas de 2026, com a empresa emitente.
- **Coluna Empresa** em `certidoes`, `certidoes-cnd` e `guias` (LEFT JOIN de propósito:
  linha órfã continua aparecendo — é a que mais precisa ser vista).
- **Datas honestas**: `nfse` se declara ARQUIVO anterior a 2026; `guias-fgts`/`guias-inss`
  dizem a última competência que têm (12.2025 e 11.2025) e que a origem não separa por CNPJ.

## Veredito por lente

| Lente | Status | Evidência |
|---|---|---|
| **DADO** | ✅ | 3/3 oráculos fiscais verdes. `test_oraculo_fiscal_painel` (4 KPIs) e `test_oraculo_fiscal_multicnpj` (painel/cobertura/colunas/buraco) comparam a tela com a **verdade do banco escrita de forma independente**, não com a query do builder |
| **TELA** | ⚠️ **parcial** | Playwright MCP **não está disponível nesta sessão** — não há como abrir o navegador. Verificado pela rota real do dispatcher (`/redesign/data/fiscal`) com token válido, após o bake. Pela regra da casa isso é "API 200", que **não** equivale a entregue |
| **CÓDIGO** | ✅ | `ruff` limpo em `fiscal.py` e nos dois oráculos; `test_u2_fiscal` (pré-existente) não regrediu |

**Por que o QA de 09/08 aprovou KPIs errados:** ele conferiu a tela contra as *queries do
builder*, e batiam. A query é que estava errada. É a diferença entre "o número está certo" e
"a afirmação está certa" — a própria skill avisa, e o QA anterior (meu) caiu nela.

## Achados que NÃO são código (para o Jordan)

1. **A Patrimonial não tem obrigação fiscal nenhuma cadastrada.** Não é bug de rota: o sync
   do Drive resolve empresa pelo CNPJ do PDF e o mapa `EMPRESAS_POR_CNPJ` tem os dois. É dado
   que não chegou.
2. **As guias pararam.** FGTS na competência 12.2025, INSS em 11.2025. Nada de 2026, e a
   Patrimonial começou a folha em jun/2026.
3. **Obrigações param na competência 06/2026**; a última criação foi 17/07.
4. **Zero NFS-e em agosto**, nas cinco tabelas (última: 31/07). Pode ser faturamento de fim de
   mês — ou sincronização parada.
5. **3 certidões vencidas**, duas em 09/08. Ação humana, não de código.

## Não coberto

- **Lente TELA no navegador**: sem Playwright nesta sessão. Quem tiver acesso deve abrir
  `/redesign/fiscal?_cb=$(date +%s)`, clicar nos três itens novos do menu (Painel por
  empresa, Cobertura de certidões, NFS-e emitidas) e conferir que a matriz mostra `FALTA` em
  laranja na coluna da Patrimonial.
- **Ninguém validou os números fiscais em si** — que a alíquota do Anexo III esteja correta é
  conferência de contador, não de QA. O que se prova aqui é exibido == banco.
- **Nenhuma obrigação foi criada** para "completar" a Patrimonial. O buraco é achado, não
  lacuna a preencher com linha fabricada.
