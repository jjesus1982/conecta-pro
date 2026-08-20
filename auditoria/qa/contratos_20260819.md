# Contrato por modelo — 19/08/2026

**✅ FECHADO — 7/7.** Reproduz com `python3 backend/scripts/qa/fechado_contratos.py`.

```
[render]
  ✅ 1 · Green Hills traz todas as cláusulas do modelo — 12 cláusulas, 0 faltando, 388 KB
  ✅ 3 · CNPJ: 0 contrato de mão de obra fora da Patrimonial — 1 renderizado de 9
  ✅ 4 · vínculo: todo PDF de contrato aponta para um contract_id — 3/3
[travas e prova externa]
  ✅ 2 · strict: render com variável faltando FALHA
  ✅ 5 · link tokenizado abre sem login — HTTP 200 application/pdf
  ✅ 6 · travas do crm zeradas — repositório 0 · vocabulário 0 · rotas 0
[oráculos]
  ✅ 7 · 8/8 verdes (os 5 do crm + render, strict, CNPJ)
```

## A prova que importa

`GET /api/v1/crm/contracts/CTR-2026-00019/pdf-modelo`, **depois do bake**, com token real:

```
HTTP/2 200 · application/pdf · 397.674 bytes · 10 páginas
x-contratada-cnpj: 66.014.833/0001-10
x-clausulas: 12
x-aviso-empresa: o contrato aponta empresa_id de CNPJ 35.710.481/0001-03, mas por
                 'maodeobra' quem presta é CONECTAMAIS PATRIMONIAL LTDA
```

Conteúdo do PDF baixado: **12 ocorrências de CLÁUSULA**, CNPJ da Patrimonial presente,
**CNPJ da Eletrônica ausente**, HELY CARVALHO presente, R$ 22.100,00 presente, zero
marcação Jinja.

**10 páginas contra as 14 do `.docx`.** Não é conteúdo faltando — as 12 cláusulas estão
todas lá. É formatação: o `.docx` tem tabelas, quebras e espaçamento que o render em texto
corrido não reproduz. Se o número de páginas importar juridicamente, é ajuste de layout,
não de conteúdo.

## Veredito por lente

| lente | veredito |
|---|---|
| **CÓDIGO** | 3 costuras ligadas reusando o que existia. Não editei `contract_generator_service` (T2, 4 consumidores) — reusei o algoritmo. |
| **DADO** | O que faltava era dado, não máquina: `contract_items` com 0 linhas nos 15 contratos, `template_id` NULL nos 15, e nenhuma casa para o representante legal. |
| **TELA** | ❌ **NÃO COBERTO** — não abri navegador. A rota foi provada por `curl` autenticado e o PDF conferido byte a byte, mas ninguém clicou num botão. |
| **PRAZO** | Render de 388 KB responde em < 2 s. Sem teste de carga. |

## O que eu quebrei e consertei no meio

**O papel timbrado saía sempre pela Eletrônica.** O corpo dizia PATRIMONIAL e o cabeçalho
das 10 páginas dizia `CONECTA MAIS ELETRÔNICA · CNPJ 35.710.481/0001-03`, porque
`pdf_branding` faz `slug or "conecta_eletronica"`. Num contrato assinado é pior que o corpo
errado: aparece em toda folha.

**E o meu oráculo tinha dois furos**, os dois provados em vermelho depois do conserto:

1. olhava o **texto**, não o **artefato** — o timbre é aplicado na construção do PDF;
2. passava conferindo **zero PDFs** (os 8 contratos de mão de obra são recusados por dado
   incompleto e o caso de aceite tem `tipo_servico` NULL). Aprovava até contra a versão
   quebrada.

Mesmo padrão no portão: a condição 3 passava com "0 renderizados de 8", e o gate pulava em
silêncio três oráculos cujo nome eu tinha inventado.

## Dado que entrou (e por quê)

- **`contract_items`**, 0 linhas nos 15 contratos. Green Hills recebeu a composição
  distribuída **proporcionalmente** por decisão do Jordan — o noturno é mais caro porque
  carrega adicional noturno, hora noturna reduzida e adicional de intrajornada:
  `AGP Diurno 2 = R$ 10.605,78` · `AGP Noturno 2 = R$ 11.494,22` · soma R$ 22.100,00 =
  `monthly_value`. Prêmio do noturno em **8,38%**, idêntico à proporção do `.docx`.
- **`crm_contacts`** virou a casa do representante legal (`clients` não tem campo, e
  contato financeiro não é quem assina). HELY CARVALHO, CPF `[CPF A SER INFORMADO]` — é
  assim no documento original.
- **`contracts.template_id`** ligado no Green Hills.

## NÃO COBERTO

| item | motivo |
|---|---|
| Navegador | rota provada por `curl`; nenhuma tela aberta |
| Anexar PDF **assinado** | F3 pede o caminho; entreguei o vínculo do gerado, não o upload do assinado |
| Os outros 8 contratos de mão de obra | recusam por dado incompleto — falta `template_id` e `contract_items` em cada um |
| `CTR-2026-00006` (CFTV do Green Hills) | recusa correta: não há modelo de eletrônica cadastrado |
| Carga | não medida |

## Para o Jordan decidir

1. **Duas "CLÁUSULA DÉCIMA"** (anticorrupção e proteção de dados) — confirmado no PDF
   final: 12 cláusulas, 11 nomes distintos. Todo contrato herda.
2. **Título duplicado**: abre com *"PRESTAÇÃO DE SERVIÇOS DE SERVIÇOS GERAIS"* e logo
   depois *"DE PORTARIA 24 HORAS"*. Deveria ser variável — muda por tipo de contrato.
3. **`CTR-2026-00019` aponta `empresa_id` da Eletrônica** sendo mão de obra. O PDF sai
   certo pela regra e o header denuncia, mas a linha continua errada no banco.
4. **`tipo_servico` NULL** em 2 dos 15 contratos.
