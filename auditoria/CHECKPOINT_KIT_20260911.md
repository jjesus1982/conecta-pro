# Checkpoint — kit documental, onde paramos (11/09/2026)

**Retomar por aqui.** O trabalho do kit está estável e commitado; o que falta é decisão do Jordan,
não código quebrado.

---

## Estado, em números

| | antes de 09/09 | agora |
|---|---|---|
| Média de completude, 08/2026 | 22% | **56%** |
| Kits completos | 0 de 17 | **5 de 14** |
| Documentos no Drive dos clientes | 40 no maior kit | **706** (907 no banco) |
| "Condomínios" no panorama | 17 (4 fantasmas) | **14, todos reais** |

Kits em 100%: Ideal Flores (352 docs) · Mirante das Flores (168) · Prime Arena (101) ·
Villa Dei Fiori (126) · Laranjeiras Village (115).

**Michelangelo (1º kit REAL) está fechado:** 14 de 14 assinaturas — 10 do funcionário e as 4 da
empresa com ICP-Brasil, assinadas pelo Jordan em 10/09.

---

## A DECISÃO que estava na mesa quando paramos

O conferente reprovou o Ideal Flores mesmo com o checklist em 100%, por nome e assinatura:

- 352 arquivos para 233 nomes — **118 nomes repetidos** (duplicata exata, ids distintos);
- 37 nomes em padrão de coletor (`RECIBO_DE_ADIANTAMENTO_SALARIAL_40_08_20_08.2026_*.pdf`);
- 79 documentos sem assinatura do funcionário, 14 sem a da empresa;
- uma demissão em 24/08 (DANIEL SOUZA DOS SANTOS) sem TRCT no kit.

**Os defeitos de código estão corrigidos.** O que resta nos outros nove kits é RESÍDUO de antes
das correções — só o Michelangelo foi remontado do zero.

**Pergunta aberta ao Jordan, nas minhas palavras de 10/09:** remontar apaga o kit no banco e no
Drive e reconstrói. No Michelangelo (2 pessoas) ficou limpo; no Ideal Flores são 23 pessoas e 352
arquivos. As opções colocadas foram: (a) remontar um de cada vez começando pelo menor, com ele
olhando antes de seguir; (b) atacar só duplicatas e nomes, sem remontar.

---

## O que foi construído (commits de 09 e 10/09)

**Um GEDEON só.** Eram dois sistemas de kit escrevendo na mesma pasta do cliente e nenhum enxergava
o outro. Escrita unificada na estrutura de 5 pastas; leitura soma a nova e os meses antigos.
Retrato completo em `auditoria/GEDEON_E_GED_UM_SO_20260910.md`.

**Uma régua de completude.** Eram quatro fórmulas e a errada (`documents_signed / total_documents`)
rodava por último, sobrescrevendo a certa. Kit completo e não assinado lia 0%.

**`posts.ged_client_id`** estava NULO nos 16 postos — sete lugares adivinhavam o condomínio por
semelhança de nome. Preenchido pelo join que sempre existiu.

**O Hermes entrou no fluxo.** Conector `mcp-ged` (escopo ged+fiscal, 42 ferramentas), o bloco
`sistema` no orquestrador (as duas metades do kit numa montagem só), memória e skill
`conferir-kit-documental` aprovadas pelo Jordan e versionadas em `hermes-runtime/`.

**Travas novas, todas com oráculo:** pasta declarada por tipo · réguas que batem entre si ·
arquivo alcançável · assinado exige PDF · documento de outro ano não sobe · uma via por documento ·
documento do trabalhador só sobe assinado.

---

## Aberto, para retomar

| o quê | onde |
|---|---|
| Remontar ou limpar os 9 kits restantes | decisão do Jordan (acima) |
| `montar_kit_completo` sem condomínio dá timeout | achado do conferente, não atacado |
| SMART TORQUATO: 1 arquivo, não é cliente em tabela nenhuma | Jordan olhar antes de apagar |
| 3 colunas de `employees` fora do alembic | `auditoria/ANALISE_DOCS_REAIS_vs_CONECTA_PRO_20260909.md` §6 |
| Guias de 08/2026 vencem 20/09 | prazo, não defeito |

**Kit do Michelangelo:** https://drive.google.com/drive/folders/1M44slr08PkK2U54l18_irZnbQwlBKNHd
