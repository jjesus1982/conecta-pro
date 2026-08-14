# Responsivo / mobile — Operacional (redesign) · 14/08/2026

Navegador de verdade (Chromium headless), **30 combinações**: 10 telas × 3 aparelhos
(Android 360×800, iPhone 390×844, Tablet 768×1024), com `is_mobile` e `has_touch`
ligados e DPR real.

```bash
export QA_TOKEN=$(docker exec -e PYTHONPATH=/app conecta-pro-backend python3 -c \
  "from core.auth.jwt import create_access_token; print(create_access_token(subject='<user_id>'))")
python3 scripts/qa_responsivo_operacional.py
```

## O layout passa

| verificação | resultado |
|---|---|
| Página desliza na horizontal | **0 de 30** — `scrollWidth == innerWidth` sempre |
| Elemento vazando solto | **0 de 30** |
| Tela vazia / "Aguardando dado" | **0 de 30** |

As tabelas largas **rolam dentro do próprio container** (`overflow-x` no `rd-tbl-inner`),
que é o padrão certo: o conteúdo é acessível e o corpo da página nunca desliza.

## Duas coisas reais, e são de leitura, não de layout

**1 · Texto pequeno demais — vale para o redesign inteiro, não só o operacional**

```css
/* src/app/redesign/redesign.css */
.rd-pill   { font-size: 10.5px; padding: 3px 10px; }   /* até 200 por tela */
.rd-tbl-th { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; }
```

`rd-pill` é o selo de status dentro das linhas — aparece **200 vezes** numa tela de
Turnos. A 10,5px, com peso 700 e caixa alta, dá para ver mas cansa; o mínimo confortável
em celular é 12px.

Os números são **idênticos nos três aparelhos**, o que confirma: é estilo fixo, não
quebra de viewport.

**2 · Botão de documento pequeno para o dedo — tela de Rondas**

`rd-doc-act` ("Abrir" / "Baixar") mede **22px de altura × ~61px de largura**, e há
**102 deles na mesma tela**. Apple recomenda 44px, Material 48px. Errar o toque entre 102
botões de 22px empilhados é questão de tempo.

## ⚠️ A primeira medição estava errada e ia virar relatório

A primeira versão deste script acusou **2.365 "elementos vazando"** na tela de Turnos e
**0/30 sem problema** — eu ia reportar o mobile como quebrado.

Fui checar: **todos os 2.365 estavam dentro de um container com rolagem própria, zero
soltos**, e a página nem deslizava (`scrollW=390/390`). Ou seja, eu estava acusando o
padrão CERTO de ser defeito.

Duas outras correções no medidor pelo mesmo motivo:
- o link `sr-only` "Pular para o conteúdo principal" tem 1px **por desenho** (é recurso de
  acessibilidade); contá-lo como alvo de toque era acusar a solução de ser problema;
- o corte de texto passou de `<12px` para `<=11px`: 12px é o mínimo aceito, e contá-lo
  acusava 102 elementos corretos numa tela só.

## O que NÃO foi coberto

- **Aparelho físico**: tudo foi emulação. Toque real, teclado virtual cobrindo campo e
  rede 3G/4G não foram testados.
- **Orientação paisagem**: só retrato.
- **Formulários**: as 10 telas medidas são de leitura. Preencher formulário no celular
  (foco, zoom automático do iOS em input <16px, teclado cobrindo o botão) fica de fora.
- **Carga**: dimensão separada, segue não testada.
- **Leitor de tela**: acessibilidade além do tamanho de alvo não foi avaliada.

## Recomendação — e por que não apliquei

`rd-pill` e `rd-tbl-th` estão em `redesign.css`, que vale para **todos os módulos** do
redesign, não só o operacional. Mudar tamanho de fonte ali reflui em financeiro,
comercial, DP e no resto — e hoje eu já quebrei a folha de pagamento mexendo numa coluna
compartilhada sem conferir quem consumia. Aqui a lição vale de novo.

Proposta, se você aprovar:
1. `rd-pill` 10,5px → **12px** (e `padding` 3px → 4px para o selo não achatar);
2. `rd-tbl-th` 11px → **12px**;
3. `rd-doc-act` altura mínima **32px** (não 44 — empilhar 102 botões de 44px muda o
   desenho da tela; 32 já tira do risco sem redesenhar).

São três linhas de CSS. O risco não é a mudança, é o alcance — por isso fica com você.
