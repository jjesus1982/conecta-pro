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
