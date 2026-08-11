#!/usr/bin/env python3
"""Gera o site da Conecta Mais — mundo visual "Memorial Descritivo".

Conteúdo em dados, HTML em template: o Jordan troca um texto ou um número sem
encostar em marcação, e as seis páginas saem coerentes entre si.

REGRA DA CASA, aplicada aqui: nada de número, certificação, cliente ou prazo
inventado. O que ainda não foi confirmado sai como <span class="preencher">,
visível na página, e entra na lista de pendências impressa no fim da execução.

  python3 web/novo/gerar.py            # escreve em /var/www/web.conectamais.pro/novo
  python3 web/novo/gerar.py --destino /tmp/previa
"""

import argparse
import html
import pathlib
from urllib.parse import quote

FONE = "558008804414"
FONE_HUMANO = "0800 880 4414"
CNPJ = "35.710.481/0001-03"

# Marcador [c:<slug>] lido por _atribuicao_do_texto (whatsapp/agent_service.py).
# ATENÇÃO à ordem das palavras-chave de origem: "portaria remota" vence
# "agentes de portaria", que vence "monitoramento", que vence "instagram".
# Mudar o texto sem olhar isso reatribui o lead para o serviço errado.
def zap(texto: str, slug: str) -> str:
    return f"https://wa.me/{FONE}?text={quote(f'{texto} [c:{slug}]')}"


PENDENCIAS: list[str] = []


def preencher(o_que: str) -> str:
    PENDENCIAS.append(o_que)
    return f'<span class="preencher">a preencher: {html.escape(o_que)}</span>'


ITENS = [
    {
        "n": "01",
        "slug": "portaria-remota",
        "titulo": "Portaria remota",
        "resumo": "Controle de acesso 24h operado da nossa central, sem porteiro no local.",
        "zap_texto": "Olá! Quero uma cotação de portaria remota.",
        "zap_slug": "site_portaria",
        "corpo": [
            "O acesso do condomínio passa a ser autorizado por um operador da nossa "
            "central, por vídeo e áudio, com abertura remota de portão e registro de "
            "cada entrada. O posto físico deixa de existir; a operação, não.",
            "É o serviço que mais reduz custo por posto — e o que mais assusta em "
            "assembleia. Por isso a especificação abaixo é pública: o que está "
            "contratado, quem opera, e o que acontece quando a internet cai.",
        ],
        "clausulas": [
            ("1.1", "Cobertura", "24 horas, 7 dias"),
            ("1.2", "Operação", "central própria"),
            ("1.3", "Vínculo do operador", "CLT direto"),
            ("1.4", "Registro de acesso", "vídeo + log por evento"),
            ("1.5", "Queda de link", None),
            ("1.6", "Prazo de implantação", None),
        ],
        "foto": ("Posto em operação", "Portaria atendida remotamente"),
    },
    {
        "n": "02",
        "slug": "agentes-de-portaria",
        "titulo": "Agentes de portaria",
        "resumo": "Equipe própria, registrada, na escala 12x36 — sem intermediação.",
        "zap_texto": "Olá! Quero uma cotação de agentes de portaria.",
        "zap_slug": "site_agentes",
        "corpo": [
            "Agentes de portaria alocados no seu endereço, contratados em regime CLT "
            "pela Conecta Mais. Não há intermediação nem cooperativa: quem está no "
            "posto é funcionário nosso, com o encargo recolhido em nosso CNPJ.",
            "Isso importa porque o passivo trabalhista de portaria terceirizada chega "
            "ao contratante. A composição de custo do posto sai da convenção coletiva "
            "vigente, e nós a mostramos item a item na cotação.",
        ],
        "clausulas": [
            ("2.1", "Escala", "12x36, diurno ou noturno"),
            ("2.2", "Vínculo", "CLT direto, sem terceiro"),
            ("2.3", "Base salarial", "CCT SINDECOMPRESTS 2026"),
            ("2.4", "Cobertura de falta", "substituto próprio"),
            ("2.5", "Uniforme e EPI", "fornecidos"),
            ("2.6", "Quadro atual", None),
        ],
        "foto": ("Equipe uniformizada", "Agentes em posto"),
    },
    {
        "n": "03",
        "slug": "monitoramento",
        "titulo": "Monitoramento 24h",
        "resumo": "Central própria acompanhando alarme e câmera, com resposta a evento.",
        "zap_texto": "Olá! Quero uma cotação de monitoramento.",
        "zap_slug": "site_monitoramento",
        "corpo": [
            "Alarmes e câmeras do seu endereço chegam à nossa central, onde um operador "
            "em turno trata o evento — verifica a imagem, aciona quem precisa ser "
            "acionado e registra o que foi feito.",
            "A diferença entre central própria e central contratada aparece no evento "
            "real: quem atende conhece a planta do seu posto e responde por ela.",
        ],
        "clausulas": [
            ("3.1", "Operação", "central própria, 24h"),
            ("3.2", "Tratativa de evento", "verificação em vídeo"),
            ("3.3", "Registro", "log por ocorrência"),
            ("3.4", "Tempo de resposta", None),
            ("3.5", "Integração com portaria", "mesma central"),
        ],
        "foto": ("Central 24h", "Sala de monitoramento em turno"),
    },
    {
        "n": "04",
        "slug": "seguranca-eletronica",
        "titulo": "Segurança eletrônica",
        "resumo": "Projeto, instalação e manutenção de CFTV, alarme e controle de acesso.",
        "zap_texto": "Olá! Quero um projeto de segurança eletrônica e CFTV.",
        "zap_slug": "site_cftv",
        "corpo": [
            "Levantamento no local, projeto com posicionamento de câmera e ponto de "
            "acesso, instalação e manutenção. O equipamento fica no cliente e a "
            "operação pode ser ligada à nossa central — ou não, se você preferir.",
            "Sem venda casada: o projeto é entregue com a lista de equipamento e as "
            "quantidades, e serve para você cotar em qualquer lugar.",
        ],
        "clausulas": [
            ("4.1", "Escopo", "projeto, instalação, manutenção"),
            ("4.2", "Propriedade do equipamento", "do contratante"),
            ("4.3", "Integração com central", "opcional"),
            ("4.4", "Garantia", None),
            ("4.5", "Prazo de execução", None),
        ],
        "foto": ("Instalação", "Câmera e controle de acesso instalados"),
    },
]

VALORES_PENDENTES = {
    "1.5": "o que acontece na queda de link (nobreak, 4G, protocolo)",
    "1.6": "prazo de implantação da portaria remota",
    "2.6": "quantos agentes no quadro hoje",
    "3.4": "tempo médio de resposta a evento",
    "4.4": "prazo de garantia da instalação",
    "4.5": "prazo de execução do projeto",
}


def cabeca(titulo: str, descricao: str, canonico: str) -> str:
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{html.escape(titulo)}</title>
<meta name="description" content="{html.escape(descricao)}">
<link rel="canonical" href="https://conectamais.pro{canonico}">
<link rel="icon" href="/links/logo.webp">
<link rel="stylesheet" href="/novo/estilo.css">
<meta property="og:title" content="{html.escape(titulo)}">
<meta property="og:description" content="{html.escape(descricao)}">
<meta property="og:image" content="https://conectamais.pro/links/logo.webp">
<meta property="og:type" content="website">
</head>
<body>
<!--
THESIS: o site é a ESPECIFICAÇÃO pública do serviço, não um folheto. Recusa o
hero escuro com vigilante sob gradiente azul que toda empresa de segurança
publica, e recusa também seu oposto previsível, o branco minimalista de startup.
OWN-WORLD: papel branco frio com massas pretas e o laranja #F26522 da marca como
carimbo; uma família só (Archivo variável, eixo de largura); cláusulas numeradas
com condutor pontilhado; fotos como chapas de dossiê técnico. Sem serifada de
display, sem gradiente, sem fundo creme.
STORY: quem decide entende o que está contratando linha a linha, acredita porque
vê a especificação em vez de adjetivo, e pede cotação pelo WhatsApp.
FIRST VIEWPORT: faixa preta de identificação, linha de documento (praça, data,
emissor), título como cláusula (ITEM 0N — NOME), chamada de uma linha, carimbo
laranja assentando à direita, e o índice dos itens logo abaixo da dobra.
FORM: memorial descritivo / edital; candidato 7 da lista ordenada por
ressonância; seed 2b036e29.
FINISH: unreviewed and undocumented is unfinished; this build ends with the
finish review, the verdict, and DESIGN.md
-->
<header class="masthead">
  <div class="interno">
    <img src="/links/logo.webp" alt="">
    <div class="marca">Conecta Mais<span>Segurança e Tecnologia</span></div>
    <nav>
      <a href="/novo/">Capa</a>
      <a href="/novo/portaria-remota/">Item 01</a>
      <a href="/novo/agentes-de-portaria/">Item 02</a>
      <a href="/novo/monitoramento/">Item 03</a>
      <a href="/novo/seguranca-eletronica/">Item 04</a>
      <a href="/novo/contato/">Contato</a>
    </nav>
  </div>
</header>
"""


PE = f"""
<footer class="pe">
  <div class="interno">
    <div>
      <h3>Serviços</h3>
      <a href="/novo/portaria-remota/">Portaria remota</a>
      <a href="/novo/agentes-de-portaria/">Agentes de portaria</a>
      <a href="/novo/monitoramento/">Monitoramento 24h</a>
      <a href="/novo/seguranca-eletronica/">Segurança eletrônica</a>
    </div>
    <div>
      <h3>Contato</h3>
      <a href="tel:+{FONE}">{FONE_HUMANO}</a>
      <a href="{zap('Olá! Vim pelo site e quero falar com a Conecta Mais.', 'site_rodape')}">WhatsApp</a>
      <a href="https://instagram.com/conectamaisoficial">Instagram</a>
    </div>
    <div>
      <h3>Empresa</h3>
      <a href="/novo/contato/">Onde estamos</a>
      <a href="https://conectamais.pro/links/">Links</a>
    </div>
  </div>
  <div class="legal">Conecta Mais — Segurança e Tecnologia · CNPJ {CNPJ} · Manaus/AM</div>
</footer>
</body>
</html>
"""


def identificacao(item: str) -> str:
    return (f'<div class="identificacao"><span>Emissor <b>Conecta Mais</b></span>'
            f'<span>Praça <b>Manaus/AM</b></span>'
            f'<span>Documento <b>{item}</b></span>'
            f'<span>CNPJ <b>{CNPJ}</b></span></div>')


def chapa(rotulo: str, legenda: str, arquivo: str) -> str:
    caminho = pathlib.Path(f"/var/www/web.conectamais.pro/novo/fotos/{arquivo}")
    if caminho.exists():
        img = f'<img src="/novo/fotos/{arquivo}" alt="{html.escape(legenda)}" loading="lazy">'
        classe = "chapa"
    else:
        PENDENCIAS.append(f"foto: {legenda} → /novo/fotos/{arquivo}")
        img = (f'<div class="marcador" role="img" aria-label="Foto a incluir: {html.escape(legenda)}">'
               f'Chapa a incluir<br>{html.escape(arquivo)}</div>')
        classe = "chapa vazia"
    return (f'<figure class="{classe}">{img}'
            f'<figcaption><b>{html.escape(rotulo)}</b>{html.escape(legenda)}</figcaption></figure>')


def pagina_item(it: dict) -> str:
    linhas = []
    for num, rotulo, valor in it["clausulas"]:
        v = (f'<span class="valor">{html.escape(valor)}</span>' if valor
             else f'<span class="valor">{preencher(VALORES_PENDENTES[num])}</span>')
        linhas.append(f'<li{"" if valor else " class=\"pendencia\""}><span class="n">{num}</span>'
                      f'<span class="rotulo"><b>{html.escape(rotulo)}</b></span>{v}</li>')
    titulo = f"{it['titulo']} — Conecta Mais"
    return (cabeca(titulo, it["resumo"], f"/novo/{it['slug']}/")
            + f'<main class="folha">{identificacao(f"Item {it['n']}")}'
            + '<div class="bloco capa"><div class="par"><div>'
            + f'<h1>{html.escape(it["titulo"])}</h1>'
            + f'<p class="chamada">{html.escape(it["resumo"])}</p>'
            + "".join(f"<p>{html.escape(p)}</p>" for p in it["corpo"])
            + f'<ul class="clausulas">{"".join(linhas)}</ul>'
            + '<div class="assinatura">'
            + '<p class="aviso">Cotação por posto, com a composição de custo aberta</p>'
            + '<div class="acoes">'
            + f'<a class="acao" href="{zap(it["zap_texto"], it["zap_slug"])}">'
            + '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">'
            + '<path d="M12.04 2C6.58 2 2.13 6.45 2.13 11.91c0 1.75.46 3.45 1.32 4.95L2 22l5.25-1.38a9.9 '
            + '9.9 0 0 0 4.79 1.22h.01c5.46 0 9.91-4.45 9.91-9.91S17.5 2 12.04 2zm5.8 14.02c-.24.68-1.4 '
            + '1.3-1.94 1.35-.5.05-1.13.07-1.82-.11-.42-.11-.96-.29-1.65-.59-2.9-1.25-4.8-4.17-4.95-4.37-.14-.2-1.18-1.57-1.18-3s.75-2.13'
            + ' 1.02-2.42c.27-.29.58-.36.78-.36l.56.01c.18 0 .42-.07.66.5.24.59.83 2.02.9 2.17.07.15.12.32.02.51-.09.2-.14.32-.28.49l-.42.49c-.14.14-.28.29-.12.57.16.29.71'
            + ' 1.17 1.53 1.9 1.05.94 1.94 1.23 2.22 1.37.27.15.43.12.59-.07.16-.2.68-.79.86-1.07.18-.27.36-.22.61-.13.24.09 1.55.73 1.82.86.27.14.44.2.51.32.07.11.07.66-.17'
            + ' 1.34z"/></svg>Solicitar cotação</a>'
            + f'<a class="acao secundaria" href="tel:+{FONE}">{FONE_HUMANO}</a>'
            + '</div></div></div>'
            + f'<div>{chapa(f"Chapa {it["n"]}", it["foto"][1], f"{it['slug']}.webp")}</div>'
            + '</div></div></main>' + PE)


def pagina_capa() -> str:
    idx = []
    for it in ITENS:
        idx.append(
            f'<a href="/novo/{it["slug"]}/"><span class="n">Item {it["n"]}</span>'
            f'<span class="titulo">{html.escape(it["titulo"])}'
            f'<em>{html.escape(it["resumo"])}</em></span>'
            f'<span class="seta" aria-hidden="true">→</span></a>'
        )
    return (cabeca("Conecta Mais — Segurança e Tecnologia · Manaus",
                   "Portaria remota, agentes de portaria, monitoramento 24h e segurança "
                   "eletrônica em Manaus. Equipe CLT própria e central de monitoramento própria.",
                   "/novo/")
            + '<main class="folha">' + identificacao("Memorial descritivo de serviços")
            + '<div class="bloco capa">'
            + '<div class="carimbo"><span>Equipe</span><b>CLT</b><span>própria</span></div>'
            + '<h1>Segurança patrimonial<br>especificada</h1>'
            + '<p class="chamada">Quatro serviços, cada um descrito como se descreve um '
            + 'contrato: o que está incluído, quem opera e sob qual vínculo. Sem adjetivo '
            + 'no lugar de cláusula.</p>'
            + '<p>A Conecta Mais opera em Manaus com equipe registrada em CLT direto e '
            + 'central de monitoramento própria. Nenhuma das duas coisas é detalhe: é o que '
            + 'define quem responde pelo passivo trabalhista do seu posto e quem atende '
            + 'quando o alarme dispara às três da manhã.</p>'
            + f'<div class="indice">{"".join(idx)}</div>'
            + '<div class="assinatura"><p class="aviso">Fale com quem opera, não com central de vendas</p>'
            + '<div class="acoes">'
            + f'<a class="acao" href="{zap("Olá! Vim pelo site e quero uma cotação.", "site_capa")}">Solicitar cotação</a>'
            + f'<a class="acao secundaria" href="tel:+{FONE}">{FONE_HUMANO}</a>'
            + '</div></div></div>'
            + '<div class="bloco"><h2>A operação</h2>'
            + '<div class="par"><div>'
            + '<p>Somos uma empresa de Manaus, com quadro próprio e operação própria. '
            + 'O que segue é o que dá para verificar antes de assinar.</p>'
            + '<ul class="clausulas">'
            + '<li><span class="n">A.1</span><span class="rotulo"><b>Razão social</b></span>'
            + '<span class="valor">Conecta Mais</span></li>'
            + '<li><span class="n">A.2</span><span class="rotulo"><b>CNPJ</b></span>'
            + f'<span class="valor">{CNPJ}</span></li>'
            + '<li><span class="n">A.3</span><span class="rotulo"><b>Praça</b></span>'
            + '<span class="valor">Manaus/AM</span></li>'
            + '<li><span class="n">A.4</span><span class="rotulo"><b>Central de monitoramento</b></span>'
            + '<span class="valor">própria, 24h</span></li>'
            + '<li><span class="n">A.5</span><span class="rotulo"><b>Vínculo do quadro</b></span>'
            + '<span class="valor">CLT direto</span></li>'
            + '<li class="pendencia"><span class="n">A.6</span><span class="rotulo"><b>Licenças e alvarás</b></span>'
            + f'<span class="valor">{preencher("números de alvará, licença ou registro que podemos citar")}</span></li>'
            + '<li class="pendencia"><span class="n">A.7</span><span class="rotulo"><b>Clientes atendidos</b></span>'
            + f'<span class="valor">{preencher("quais clientes autorizam aparecer com nome")}</span></li>'
            + '</ul></div>'
            + f'<div>{chapa("Chapa A", "Central de monitoramento em turno", "central.webp")}</div>'
            + '</div></div></main>' + PE)


def pagina_contato() -> str:
    return (cabeca("Contato — Conecta Mais", f"Fale com a Conecta Mais: {FONE_HUMANO}, Manaus/AM.",
                   "/novo/contato/")
            + '<main class="folha">' + identificacao("Encerramento")
            + '<div class="bloco capa"><h1>Contato</h1>'
            + '<p class="chamada">Quem responde é a operação. Se preferir, mande a planta do '
            + 'endereço e a quantidade de acessos — a cotação sai por posto, com a composição '
            + 'de custo aberta.</p>'
            + '<ul class="clausulas">'
            + '<li><span class="n">C.1</span><span class="rotulo"><b>WhatsApp e telefone</b></span>'
            + f'<span class="valor">{FONE_HUMANO}</span></li>'
            + '<li><span class="n">C.2</span><span class="rotulo"><b>Atendimento comercial</b></span>'
            + '<span class="valor">segunda a sexta</span></li>'
            + '<li><span class="n">C.3</span><span class="rotulo"><b>Central de monitoramento</b></span>'
            + '<span class="valor">24 horas</span></li>'
            + '<li class="pendencia"><span class="n">C.4</span><span class="rotulo"><b>Endereço</b></span>'
            + f'<span class="valor">{preencher("endereço comercial para publicar")}</span></li>'
            + '</ul>'
            + '<div class="assinatura"><p class="aviso">Abre a conversa já com o assunto preenchido</p>'
            + '<div class="acoes">'
            + f'<a class="acao" href="{zap("Olá! Vim pelo site e quero falar com a Conecta Mais.", "site_contato")}">Falar no WhatsApp</a>'
            + f'<a class="acao secundaria" href="tel:+{FONE}">Ligar {FONE_HUMANO}</a>'
            + '</div></div></div></main>' + PE)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--destino", default="/var/www/web.conectamais.pro/novo")
    a = ap.parse_args()
    raiz = pathlib.Path(a.destino)

    paginas = {"index.html": pagina_capa(), "contato/index.html": pagina_contato()}
    for it in ITENS:
        paginas[f"{it['slug']}/index.html"] = pagina_item(it)

    for caminho, conteudo in paginas.items():
        destino = raiz / caminho
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(conteudo, encoding="utf-8")
        print(f"  {destino}  ({len(conteudo):,} bytes)")

    if PENDENCIAS:
        print(f"\n  {len(PENDENCIAS)} PENDÊNCIAS marcadas na página (nada foi inventado):")
        for p in dict.fromkeys(PENDENCIAS):
            print(f"    - {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
