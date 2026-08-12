---
name: gold-standard-slides
description: Use ao criar, gerar, converter ou ajustar QUALQUER apresentação/deck/slides da Conecta Mais ou Conecta PRO — institucional, comercial, proposta, resultado, treinamento — em HTML, PDF ou a partir de .pptx. Também quando o usuário disser "apresentação", "slides", "deck", "pitch" ou reclamar que uma apresentação ficou fraca/genérica/com cara de IA.
---

# Padrão-ouro de slides — Conecta Mais

Decks HTML autocontidos (CSS/JS inline, zero dependência), palco fixo 1920×1080 escalado ao viewport, marca Conecta Mais em todos os slides. O deck fraco típico: logo de emoji, paleta genérica, fonte de sistema, KPI quebrando linha, sem rodapé de marca. Esta skill existe para esse deck nunca mais sair.

## Regras da marca (inegociáveis)

1. **Paleta oficial** — só as variáveis de `brand.css` (azul #1E3A5F/#2D5F8B, laranja #F97316, fundo #F8FAFC). Fundo dark = azul-noite, nunca preto puro. Proibido inventar cor.
2. **Logo real** — embutir base64 dos assets da skill; em slide dark = `.logo-badge` branco + `assets/logo-clara-fundo.png` (regra completa em layouts.md). NUNCA emoji, ícone genérico ou "logo tipográfica".
3. **Tipografia** — Archivo (display 700–900) + Manrope (corpo), via Google Fonts. Nunca fonte de sistema.
4. **Rodapé de marca** (`.rodape-marca`) em todo slide interno; capa e contato ficam sem. Tagline: "Tecnologia para quem protege".
5. **Números em 1 linha** — KPI compacto ("R$ 272k", `tabular-nums`, `white-space:nowrap`). Se quebrar linha, abrevie o número, não encolha a fonte.
6. **Veracidade** — número de negócio vem do banco/MCP, nunca inventado (skill `veracity-sweep`). Dado interno (MRR, margem, folha) NÃO entra em deck para cliente/externo sem OK explícito do Jordan.

## Fluxo

1. **Descobrir**: público (interno × cliente × licitação), objetivo, densidade (falada: 1 ideia e ≤25 palavras/slide; leitura: grids estruturados, ≤6 blocos). Conteúdo excedente = mais slides, nunca fonte menor.
2. **Montar**: copiar `brand.css` INTEIRO no `<style>`; usar os layouts de [layouts.md](layouts.md) (capa, interno, KPI, comparativo, proposta, contato, gráfico) + controller JS de lá. Gráfico → invocar skill `dataviz` antes.
3. **Verificar (obrigatório antes de entregar)**: `python3 scripts/verificar_deck.py <deck.html> <prefixo>` → **LER os screenshots com os olhos** (Read): overflow? número quebrado? contraste? logo renderizou? Exit 1 = corrigir e repetir.
4. **Entregar**: HTML (navega com setas/swipe) e, se pedirem arquivo, `python3 scripts/exportar_pdf.py <deck.html>`. Precisa de .pptx editável → gerador `presentation_builder.py` do backend (outro caminho, mesmo padrão visual).

## Erros comuns (vistos no baseline real)

| Erro | Correção |
|---|---|
| Logo emoji 🛡 num quadrado | base64 dos assets da skill |
| "R$ 272 mil" em 3 linhas no cartão | `R$ 272k` + `.valor` (nowrap, tabular) |
| Cartões KPI com vazio enorme embaixo | `.kpi-card` (flex, justify center) |
| Azul claro + amarelo aleatórios | variáveis de `brand.css` |
| Slide sem identidade | `.rodape-marca` + `.eyebrow` + barra laranja no título |
| Entregar sem olhar | verificar_deck.py + Read dos PNGs, sempre |

## Red flags — pare e corrija

- "Vou usar um ícone parecido com a logo" → use a logo real.
- "A fonte padrão está boa" → não está; Archivo + Manrope.
- "Dá para diminuir a fonte para caber" → divida em 2 slides.
- "Não precisa screenshot, o HTML está certo" → scrollHeight não pega painel sobreposto; olhe a imagem.
- "O MRR impressiona o cliente" → dado interno; pergunte ao Jordan antes.
