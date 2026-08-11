# Site Conecta Mais — mundo visual "Memorial Descritivo"

Prévia em **https://conectamais.pro/novo/** (o site antigo segue intacto na raiz).

## Por que esta direção

O sorteio do Impeccable (seed `2b036e29`) designou o candidato **7** da lista
ordenada por ressonância — o mecanismo existe justamente para impedir que a
escolha convirja no default da categoria. Os sete mundos derivados do universo
de quem decide (síndico, gestor, construtora, órgão público) foram: livro de
ocorrências · quadro de escala 12x36 · mosaico de CFTV · planta baixa · crachá ·
sinalização predial ABNT · **edital e memorial descritivo**.

O contrato de direção completo está como comentário HTML no topo de cada página
emitida — inclusive no build, para poder ser auditado.

## Estrutura

    gerar.py      conteúdo (dados) + template → emite as 6 páginas
    estilo.css    o sistema visual inteiro
    fotos/        chapas reais; ausente = marcador hachurado honesto

    python3 web/novo/gerar.py     # escreve em /var/www/web.conectamais.pro/novo

## Regras que este site herda do projeto

1. **Nada inventado.** Nenhum número, certificação, cliente, prazo ou depoimento
   sai da minha cabeça. O que falta aparece na página como selo laranja tracejado
   `a preencher:` e é listado ao fim de cada execução do gerador.
2. **Todo CTA carrega `[c:<slug>]`** no `?text=` do wa.me, lido por
   `_atribuicao_do_texto` (whatsapp/agent_service.py) → grava `leads.utm_campaign`,
   que é o denominador do CAC.
3. **Ordem das palavras-chave de origem importa:** *portaria remota* vence
   *agentes de portaria*, que vence *monitoramento*, que vence *instagram*.
   Trocar o texto de um botão sem olhar isso reatribui o lead ao serviço errado.

## Promoção para a raiz (quando o Jordan aprovar)

Publicar em `/var/www/web.conectamais.pro/` e só então redirecionar
`conectamaistech.com.br` e `conectamais.com.br` **caminho a caminho** (301) —
nunca em bloco para a home, senão quem pesquisou "portaria remota Manaus" cai
numa home genérica.

O `sitemap.xml` do site atual declara as URLs como `www.conectamais.com.br`,
domínio diferente do que hospeda: isso divide autoridade de SEO e precisa ser
corrigido na promoção.

---

# v2 — preto conduzido por fotografia (2026-08-11)

A v1 (memorial descritivo, papel branco) foi **reprovada pelo Jordan**. Gerador
preservado em `gerar_v1_memorial.py`.

## O que a varredura de referência mostrou

| site | o que faz |
|---|---|
| **Gocil** (a maior do Brasil) | hero cinza-azulado **sem imagem nenhuma**, texto centralizado, botão dourado |
| **Haganá** (4 estados) | carrossel de 2014, gente recortada sobre gradiente azul, chatbot com avatar |
| **Ajax Systems** (referência mundial) | preto, uma linha de display, um botão, mosaico de fotografia grande e escura |

A barra do setor brasileiro é baixa. A referência mundial é preta com um acento
— e **o emblema da Conecta Mais já é preto e laranja**. O azul do site antigo
traía a própria marca; o branco da v1 também.

## Fotos provisórias

Seis imagens do **Pexels** (uso comercial livre, sem atribuição obrigatória),
listadas em `fotos/PROVISORIAS.json`. Enquanto forem de banco, a legenda diz
**"imagem ilustrativa"** — legendar foto de banco como "nossa central" seria
afirmação falsa. Substituir por foto real remove o aviso automaticamente.

Duas trocas feitas na revisão: a foto de central anterior tinha **bandeira dos
Estados Unidos visível** (inaceitável para empresa de Manaus) e o hero anterior
era abstrato demais para ler como prédio.

---

# v3 — alinhado ao Design System do Conecta PRO

Referência recebida do Jordan em 11/08/2026 (pasta "Redesign Conecta PRO logo 2",
61 arquivos). O guia oficial está capturado em `DESIGN-SYSTEM-referencia.png`.

## Valores — copiados, não deduzidos

| papel | token |
|---|---|
| Navy / primária | `#16277D` |
| Laranja / ação | `#F26522` (hover `#DA560F`) |
| Tinta / texto | `#0F1B3A` |
| Fundo app | `#F4F6FB` · Superfície `#FFFFFF` |
| Borda `#E7ECF3` · Texto fraco `#64748B` · Placeholder `#94A3B8` · Preenchimento `#F1F4FA` |
| Fonte | **Sora**, única |
| Sombra | `0 8px 20px rgba(22,39,125,.08)` — azulada, nunca cinza |

## O limite do que se herda — e por que ele existe

Ao receber o guia eu passei do ponto: comecei a reproduzir a GRAMÁTICA do ERP no
site — botão de canto curto, lockup com pastilha, escala tipográfica de 13px.
O Jordan cortou na hora, e com razão.

**Do sistema herda-se a paleta e a fonte. Só.**

| herda | não herda |
|---|---|
| navy `#16277D`, laranja `#F26522`, tinta `#0F1B3A` | raio de botão (app usa 10px; site usa pílula) |
| fundo `#F4F6FB`, borda `#E7ECF3`, texto fraco `#64748B` | lockup com pastilha (é do produto, não da empresa) |
| **Sora** como fonte única | escala de 13px (densidade de tela de folha) |
| sombra azulada `rgba(22,39,125,.08)` | componentes de UI (KPI card, badge, tabela) |

Um ERP existe para o operador conferir dado denso; um site existe para o síndico
decidir em segundos. Mesmas cores, respiro diferente. Confundir os dois foi erro
meu, registrado aqui para não repetir.
