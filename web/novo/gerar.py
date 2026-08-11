#!/usr/bin/env python3
"""Gera o site da Conecta Mais — v2, preto conduzido por fotografia.

A v1 (memorial descritivo, papel branco — preservada em gerar_v1_memorial.py)
foi reprovada pelo Jordan. A varredura de referência mostrou por quê: o setor
brasileiro publica hero cinza sem imagem (Gocil, a maior do país) ou carrossel de
2014 com gente recortada em gradiente azul (Haganá), e a referência mundial
(Ajax Systems) é preto + fotografia grande + um acento só.

O preto não é gosto: é o emblema da Conecta Mais, que é preto e laranja. O azul
do site antigo traía a própria marca.

Sobreviveu da v1 uma coisa, por indicação da revisão de acabamento: as linhas de
prova com valor à direita. Nenhum concorrente publica vínculo, cobertura e base
salarial — todos dizem "excelência e comprometimento". Viraram a ficha técnica
dentro de cada serviço.

REGRA DA CASA: nada inventado. O que não foi confirmado aparece na página como
selo laranja tracejado e é listado ao fim da execução.

  python3 web/novo/gerar.py
"""

import argparse
import html
import json
import pathlib
from urllib.parse import quote

FONE = "558008804414"
FONE_HUMANO = "0800 880 4414"
CNPJ = "35.710.481/0001-03"
FOTOS = pathlib.Path("/var/www/web.conectamais.pro/novo/fotos")


# Marcador [c:<slug>] lido por _atribuicao_do_texto (whatsapp/agent_service.py).
# ATENÇÃO à ordem das palavras-chave de origem: "portaria remota" vence
# "agentes de portaria", que vence "monitoramento", que vence "instagram".
# Trocar o texto de um botão sem olhar isso reatribui o lead ao serviço errado.
def zap(texto: str, slug: str) -> str:
    return f"https://wa.me/{FONE}?text={quote(f'{texto} [c:{slug}]')}"


PENDENCIAS: list[str] = []


def preencher(o_que: str) -> str:
    PENDENCIAS.append(o_que)
    return f'<span class="preencher">a confirmar: {html.escape(o_que)}</span>'


def _provisorias() -> set[str]:
    """Quais fotos ainda são de banco de imagem — para legendar com honestidade."""
    m = FOTOS / "PROVISORIAS.json"
    if not m.exists():
        return set()
    return {i["arquivo"] for i in json.loads(m.read_text(encoding="utf-8"))}


PROVISORIAS = _provisorias()

ITENS = [
    {
        "n": "01", "slug": "portaria-remota", "titulo": "Portaria remota",
        "resumo": "Controle de acesso 24h operado da nossa central, sem porteiro no local.",
        "zap_texto": "Olá! Quero uma cotação de portaria remota.", "zap_slug": "site_portaria",
        "corpo": [
            "O acesso do condomínio passa a ser autorizado por um operador da nossa "
            "central, por vídeo e áudio, com abertura remota de portão e registro de "
            "cada entrada. O posto físico deixa de existir; a operação, não.",
            "É o serviço que mais reduz custo por posto — e o que mais assusta em "
            "assembleia. Por isso a ficha abaixo é pública: o que está contratado, "
            "quem opera, e o que acontece quando a internet cai.",
        ],
        "prova": [
            ("Cobertura", "24 horas, 7 dias"),
            ("Operação", "central própria"),
            ("Vínculo do operador", "CLT direto"),
            ("Registro de acesso", "vídeo + log por evento"),
            ("Queda de link", None),
            ("Prazo de implantação", None),
        ],
        "legenda": "Hall de entrada com acesso controlado",
    },
    {
        "n": "02", "slug": "agentes-de-portaria", "titulo": "Agentes de portaria",
        "resumo": "Equipe própria, registrada, na escala 12x36 — sem intermediação.",
        "zap_texto": "Olá! Quero uma cotação de agentes de portaria.", "zap_slug": "site_agentes",
        "corpo": [
            "Agentes de portaria alocados no seu endereço, contratados em regime CLT "
            "pela Conecta Mais. Não há intermediação nem cooperativa: quem está no "
            "posto é funcionário nosso, com o encargo recolhido em nosso CNPJ.",
            "Isso importa porque o passivo trabalhista de portaria terceirizada chega "
            "ao contratante. A composição de custo do posto sai da convenção coletiva "
            "vigente, e nós a mostramos item a item na cotação.",
        ],
        "prova": [
            ("Escala", "12x36, diurno ou noturno"),
            ("Vínculo", "CLT direto, sem terceiro"),
            ("Base salarial", "CCT SINDECOMPRESTS 2026"),
            ("Cobertura de falta", "substituto próprio"),
            ("Uniforme e EPI", "fornecidos"),
            ("Quadro atual", None),
        ],
        "legenda": "Agente de portaria em posto",
    },
    {
        "n": "03", "slug": "monitoramento", "titulo": "Monitoramento 24h",
        "resumo": "Central própria acompanhando alarme e câmera, com resposta a evento.",
        "zap_texto": "Olá! Quero uma cotação de monitoramento.", "zap_slug": "site_monitoramento",
        "corpo": [
            "Alarmes e câmeras do seu endereço chegam à nossa central, onde um operador "
            "em turno trata o evento — verifica a imagem, aciona quem precisa ser "
            "acionado e registra o que foi feito.",
            "A diferença entre central própria e central contratada aparece no evento "
            "real: quem atende conhece a planta do seu posto e responde por ela.",
        ],
        "prova": [
            ("Operação", "central própria, 24h"),
            ("Tratativa de evento", "verificação em vídeo"),
            ("Registro", "log por ocorrência"),
            ("Tempo de resposta", None),
            ("Integração com portaria", "mesma central"),
        ],
        "legenda": "Câmera em operação",
    },
    {
        "n": "04", "slug": "seguranca-eletronica", "titulo": "Segurança eletrônica",
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
        "prova": [
            ("Escopo", "projeto, instalação, manutenção"),
            ("Propriedade do equipamento", "do contratante"),
            ("Integração com central", "opcional"),
            ("Garantia", None),
            ("Prazo de execução", None),
        ],
        "legenda": "Equipamento de segurança eletrônica",
    },
]

A_CONFIRMAR = {
    "Queda de link": "o que acontece na queda de link (nobreak, 4G, protocolo)",
    "Prazo de implantação": "prazo de implantação da portaria remota",
    "Quadro atual": "quantos agentes no quadro hoje",
    "Tempo de resposta": "tempo médio de resposta a evento",
    "Garantia": "prazo de garantia da instalação",
    "Prazo de execução": "prazo de execução do projeto",
}

ZAP_SVG = ('<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">'
           '<path d="M12.04 2C6.58 2 2.13 6.45 2.13 11.91c0 1.75.46 3.45 1.32 4.95L2 22l5.25-1.38a9.9'
           ' 9.9 0 0 0 4.79 1.22h.01c5.46 0 9.91-4.45 9.91-9.91S17.5 2 12.04 2zm5.8 14.02c-.24.68-1.4'
           ' 1.3-1.94 1.35-.5.05-1.13.07-1.82-.11-.42-.11-.96-.29-1.65-.59-2.9-1.25-4.8-4.17-4.95-4.37'
           '-.14-.2-1.18-1.57-1.18-3s.75-2.13 1.02-2.42c.27-.29.58-.36.78-.36l.56.01c.18 0 .42-.07.66.5'
           '.24.59.83 2.02.9 2.17.07.15.12.32.02.51-.09.2-.14.32-.28.49l-.42.49c-.14.14-.28.29-.12.57.16'
           '.29.71 1.17 1.53 1.9 1.05.94 1.94 1.23 2.22 1.37.27.15.43.12.59-.07.16-.2.68-.79.86-1.07.18'
           '-.27.36-.22.61-.13.24.09 1.55.73 1.82.86.27.14.44.2.51.32.07.11.07.66-.17 1.34z"/></svg>')

SETA_SVG = ('<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="2.2" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>')


def foto(nome: str, legenda: str, *, tag: str = "figure") -> str:
    """Chapa. Sem arquivo, marcador honesto. Com foto de banco, a legenda avisa —
    legendar imagem de banco como 'nossa central' seria afirmação falsa."""
    arq = f"{nome}.webp"
    if not (FOTOS / arq).exists():
        PENDENCIAS.append(f"foto real: {legenda} → /novo/fotos/{arq}")
        corpo = (f'<div class="marcador" role="img" aria-label="Foto a incluir: '
                 f'{html.escape(legenda)}">Foto a incluir<br>{arq}</div>')
        nota = " · foto pendente"
    else:
        corpo = (f'<img src="/novo/fotos/{arq}" alt="{html.escape(legenda)}" '
                 f'width="1400" height="1050" loading="lazy">')
        nota = " · imagem ilustrativa" if arq in PROVISORIAS else ""
    if tag == "img":
        return corpo
    return (f'<figure class="chapa">{corpo}'
            f'<figcaption><b>{html.escape(legenda)}</b>{nota}</figcaption></figure>')


def cabeca(titulo: str, descricao: str, canonico: str, atual: str = "") -> str:
    def na(slug, rot):
        marca = ' aria-current="page"' if slug == atual else ""
        return f'<a href="{slug}"{marca}>{rot}</a>'

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{html.escape(titulo)}</title>
<meta name="description" content="{html.escape(descricao)}">
<link rel="canonical" href="https://conectamais.pro{canonico}">
<link rel="icon" href="/links/logo.webp">
<link rel="preload" as="font" type="font/woff2" href="/novo/fontes/archivo-lat.woff2" crossorigin>
<link rel="stylesheet" href="/novo/estilo.css">
<meta property="og:title" content="{html.escape(titulo)}">
<meta property="og:description" content="{html.escape(descricao)}">
<meta property="og:image" content="https://conectamais.pro/novo/fotos/capa.webp">
<meta property="og:type" content="website">
<meta name="theme-color" content="#0A0A0A">
</head>
<body>
<!--
THESIS: segurança patrimonial mostrada, não adjetivada. Recusa as duas caras do
setor brasileiro — o hero cinza sem imagem e o carrossel de gente recortada em
gradiente azul — e prova o serviço com ficha técnica que nenhum concorrente
publica: vínculo, cobertura e base salarial.
OWN-WORLD: preto #0A0A0A do próprio emblema, fotografia grande e escura
conduzindo a página, laranja #F26522 como único acento; Archivo variável com
eixo de largura, uma família só; linhas de prova com condutor pontilhado.
STORY: quem decide vê a operação, lê a ficha e chama no WhatsApp.
FIRST VIEWPORT: fotografia em tela cheia sob véu escuro, selo laranja, título em
caixa alta, uma linha de apoio e a ação; abaixo, o mosaico fotográfico dos
quatro serviços.
FORM: preto conduzido por fotografia, derivado da varredura de referência
(Ajax Systems) contra o padrão do setor (Gocil, Haganá); v2, depois da v1
"memorial descritivo" ser reprovada pelo cliente.
FINISH: unreviewed and undocumented is unfinished; this build ends with the
finish review, the verdict, and DESIGN.md
-->
<header class="topo">
  <div class="interno">
    <img src="/links/logo.webp" alt="">
    <a class="marca" href="/novo/">Conecta Mais<span>Segurança e Tecnologia</span></a>
    <nav>
      {na('/novo/portaria-remota/', 'Portaria remota')}
      {na('/novo/agentes-de-portaria/', 'Agentes')}
      {na('/novo/monitoramento/', 'Monitoramento')}
      {na('/novo/seguranca-eletronica/', 'Eletrônica')}
      <a class="zap" href="{zap('Olá! Vim pelo site e quero uma cotação.', 'site_topo')}">Cotação</a>
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
      <a href="/novo/contato/">Contato e endereço</a>
      <a href="https://conectamais.pro/links/">Todos os links</a>
    </div>
  </div>
  <div class="legal">Conecta Mais — Segurança e Tecnologia · CNPJ {CNPJ} · Manaus/AM</div>
</footer>
<div class="barra-zap">
  <a class="acao" href="{zap('Olá! Vim pelo site e quero uma cotação.', 'site_barra')}">{ZAP_SVG}Falar no WhatsApp</a>
</div>
</body>
</html>
"""


def linhas_prova(itens) -> str:
    saida = []
    for rotulo, valor in itens:
        if valor:
            v, cls = f'<span class="valor">{html.escape(valor)}</span>', ""
        else:
            v, cls = f'<span class="valor">{preencher(A_CONFIRMAR[rotulo])}</span>', ' class="pendencia"'
        saida.append(f'<li{cls}><span class="rotulo"><b>{html.escape(rotulo)}</b></span>{v}</li>')
    return f'<ul class="prova">{"".join(saida)}</ul>'


def cartao(texto_zap: str, slug: str, titulo: str = "Cotação por posto") -> str:
    return (f'<aside class="cartao-acao"><h3>{html.escape(titulo)}</h3>'
            '<p>A cotação sai por posto, com a composição de custo aberta. '
            'Responde quem opera, não central de vendas.</p>'
            f'<a class="acao" href="{zap(texto_zap, slug)}">{ZAP_SVG}Solicitar cotação</a>'
            f'<a class="fone" href="tel:+{FONE}">{FONE_HUMANO}</a></aside>')


def pagina_item(it: dict) -> str:
    return (cabeca(f"{it['titulo']} — Conecta Mais", it["resumo"],
                   f"/novo/{it['slug']}/", f"/novo/{it['slug']}/")
            + '<section class="capa">'
            + f'<div class="foto">{foto(it["slug"], it["legenda"], tag="img")}</div>'
            + '<div class="conteudo">'
            + f'<span class="selo">Serviço {it["n"]}</span>'
            + f'<h1>{html.escape(it["titulo"])}'
            + f'<span class="fino">{html.escape(it["resumo"])}</span></h1>'
            + '</div></section>'
            + '<section class="secao"><div class="par"><div>'
            + "".join(f"<p>{html.escape(p)}</p>" for p in it["corpo"])
            + '<h2 class="titulo" style="margin-top:2.8rem">Ficha técnica</h2>'
            + '<p>O que está contratado, sem adjetivo. O que ainda não tem número está '
            + 'marcado como tal — não inventamos.</p>'
            + linhas_prova(it["prova"])
            + '</div>'
            + f'<div>{cartao(it["zap_texto"], it["zap_slug"])}</div>'
            + '</div></section>' + PE)


def pagina_capa() -> str:
    tiles = "".join(
        f'<a href="/novo/{it["slug"]}/">{foto(it["slug"], it["legenda"], tag="img")}'
        f'<span class="rotulo"><h2>{html.escape(it["titulo"])}'
        f'<em>{html.escape(it["resumo"])}</em></h2>'
        f'<span class="seta">{SETA_SVG}</span></span></a>' for it in ITENS)

    empresa = [("Razão social", "Conecta Mais"), ("CNPJ", CNPJ), ("Praça", "Manaus/AM"),
               ("Central de monitoramento", "própria, 24h"), ("Vínculo do quadro", "CLT direto")]
    linhas = "".join(
        f'<li><span class="rotulo"><b>{html.escape(r)}</b></span>'
        f'<span class="valor">{html.escape(v)}</span></li>' for r, v in empresa)
    linhas += ('<li class="pendencia"><span class="rotulo"><b>Licenças e alvarás</b></span>'
               f'<span class="valor">{preencher("números de alvará, licença ou registro")}</span></li>'
               '<li class="pendencia"><span class="rotulo"><b>Clientes atendidos</b></span>'
               f'<span class="valor">{preencher("quais clientes autorizam aparecer com nome")}'
               '</span></li>')

    return (cabeca("Conecta Mais — Segurança e Tecnologia · Manaus",
                   "Portaria remota, agentes de portaria, monitoramento 24h e segurança "
                   "eletrônica em Manaus. Equipe CLT própria e central de monitoramento própria.",
                   "/novo/")
            + '<section class="capa">'
            + f'<div class="foto">{foto("capa", "Condomínio atendido", tag="img")}</div>'
            + '<div class="conteudo">'
            + '<span class="selo">Manaus · operação própria</span>'
            + '<h1>Quem guarda<br>o seu patrimônio<br>é gente nossa'
            + '<span class="fino">Portaria remota, agentes de portaria, monitoramento 24h e '
            + 'segurança eletrônica — com equipe registrada em CLT direto e central de '
            + 'monitoramento própria.</span></h1>'
            + '<div class="acoes">'
            + f'<a class="acao" href="{zap("Olá! Vim pelo site e quero uma cotação.", "site_capa")}">'
            + f'{ZAP_SVG}Solicitar cotação</a>'
            + f'<a class="acao vazada" href="tel:+{FONE}">{FONE_HUMANO}</a>'
            + '</div></div></section>'
            + f'<div class="mosaico">{tiles}</div>'
            + '<section class="secao"><div class="par"><div>'
            + '<h2 class="titulo">Sem intermediário<br>entre você e o posto</h2>'
            + '<p>Quem está no seu posto é <strong>funcionário nosso</strong>, com encargo '
            + 'recolhido no nosso CNPJ. Quem atende o alarme às três da manhã é operador '
            + '<strong>da nossa central</strong>, não de uma central contratada.</p>'
            + '<p>As duas coisas decidem quem responde pelo passivo trabalhista do seu '
            + 'contrato e quem aparece quando o evento acontece. Por isso estão aqui, '
            + 'verificáveis, e não numa frase sobre excelência.</p>'
            + f'<ul class="prova">{linhas}</ul>'
            + '</div>'
            + f'<div>{foto("central", "Central de monitoramento em turno")}</div>'
            + '</div></section>' + PE)


def pagina_contato() -> str:
    dados = [("WhatsApp e telefone", FONE_HUMANO), ("Atendimento comercial", "segunda a sexta"),
             ("Central de monitoramento", "24 horas")]
    linhas = "".join(
        f'<li><span class="rotulo"><b>{html.escape(r)}</b></span>'
        f'<span class="valor">{html.escape(v)}</span></li>' for r, v in dados)
    linhas += ('<li class="pendencia"><span class="rotulo"><b>Endereço</b></span>'
               f'<span class="valor">{preencher("endereço comercial para publicar")}</span></li>')
    return (cabeca("Contato — Conecta Mais", f"Fale com a Conecta Mais: {FONE_HUMANO}, Manaus/AM.",
                   "/novo/contato/")
            + '<section class="secao" style="padding-top:clamp(2.5rem,6vw,4.5rem)">'
            + '<h2 class="titulo">Contato</h2>'
            + '<div class="par"><div>'
            + '<p>Quem responde é a operação. Se preferir, mande a planta do endereço e a '
            + 'quantidade de acessos — a cotação sai por posto, com a composição de custo '
            + 'aberta.</p>'
            + f'<ul class="prova">{linhas}</ul></div>'
            + f'<div>{cartao("Olá! Vim pelo site e quero falar com a Conecta Mais.", "site_contato", "Fale agora")}</div>'
            + '</div></section>' + PE)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--destino", default="/var/www/web.conectamais.pro/novo")
    a = ap.parse_args()
    raiz = pathlib.Path(a.destino)

    paginas = {"index.html": pagina_capa(), "contato/index.html": pagina_contato()}
    for it in ITENS:
        paginas[f"{it['slug']}/index.html"] = pagina_item(it)

    for caminho, conteudo in paginas.items():
        d = raiz / caminho
        d.parent.mkdir(parents=True, exist_ok=True)
        d.write_text(conteudo, encoding="utf-8")
        print(f"  {d}  ({len(conteudo):,} bytes)")

    if PROVISORIAS:
        print(f"\n  {len(PROVISORIAS)} fotos de banco (Pexels, uso comercial livre). A legenda "
              "diz 'imagem ilustrativa' — trocar por foto real da empresa.")
    if PENDENCIAS:
        print(f"\n  {len(dict.fromkeys(PENDENCIAS))} pendências marcadas NA PÁGINA:")
        for p in dict.fromkeys(PENDENCIAS):
            print(f"    - {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
