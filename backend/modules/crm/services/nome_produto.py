"""Padroniza a grafia do nome de produto/serviço do catálogo.

Pedido do Jordan (27/08/2026): "tem umas com letras maiúsculas, outras minúsculas,
padronize, não deixe ficar bagunçado". O catálogo veio de duas origens bagunçadas — 33
propostas digitadas à mão e a exportação do Bling — e nome de produto aparece no
ORÇAMENTO que vai para o cliente. Grafia inconsistente ali é a primeira coisa que se nota.

A regra é Sentence case: primeira letra maiúscula, resto minúsculo — MENOS o que não pode
descer, que é onde mora todo o cuidado deste arquivo:

  - MEDIDA/CÓDIGO (qualquer token com dígito) passa INTACTO: "2,5m", "1/3HP", "25x25",
    "4MP", "Cat6", "SG-16". Mexer aqui só estraga.
  - CAIXA CANÔNICA para o que tem grafia própria: PoE, MikroTik, TP-Link, Intelbras.
  - SIGLA CURTA em caixa alta continua em caixa alta: NVR, DPS, HD, TB, MP, IP, II, SG.
    Regra por FORMA (≤4 letras, tudo maiúsculo), não por lista — não dá para enumerar
    todo código de modelo que o Bling tem. Hifenizado é resolvido parte a parte: LC-LC.
  - A regra por forma tem exceção: palavra portuguesa curta gritada ("CABO", "RACK",
    "KIT") não é sigla e desce. Por isso `_NAO_E_SIGLA` existe — pequena e auditável.
  - SIGLA ESCRITA EM MINÚSCULA sobe: "nvr" → "NVR". Aqui a lista é necessária, porque
    "cabo" e "nvr" têm a mesma forma em minúsculo.
  - LIGAÇÃO desce no meio da frase: de, da, do, e, com, para, em, por, ou.

⚠️ Nunca use `.title()`: ele produz "Hd 2 Tb Purple (Surveillance)", "Poe" e
"Cordão Óptico Lc-Lc Duplex Monomodo 2,5M". Isso não pode sair num orçamento de cliente.

    python3 -m modules.crm.services.nome_produto     # roda o autoteste
"""
from __future__ import annotations

import re

#: Grafia própria — vence tudo. Chave em minúsculo.
_CANONICO = {
    "poe": "PoE", "wi-fi": "Wi-Fi", "wifi": "Wi-Fi",
    "intelbras": "Intelbras", "hikvision": "Hikvision", "dahua": "Dahua",
    "mikrotik": "MikroTik", "ubiquiti": "Ubiquiti", "tp-link": "TP-Link",
    "purple": "Purple", "furukawa": "Furukawa", "nexans": "Nexans",
    "clamper": "Clamper", "engetron": "Engetron", "moura": "Moura",
    "seagate": "Seagate", "hayonik": "Hayonik", "giga": "Giga",
    "jfl": "JFL", "ppa": "PPA", "garen": "Garen", "rossi": "Rossi",
    "conecta": "Conecta", "sentinela": "Sentinela",
}

#: Siglas que SOBEM quando vêm minúsculas. (Quando já vêm em caixa alta, a regra por
#: forma resolve sozinha.) Sem tokens de 1 letra: "a" e "m" viram ligação/medida.
_SIGLAS = {
    "cftv", "nvr", "dvr", "ip", "hd", "ssd", "led", "sfp", "dio", "dps", "otdr",
    "utp", "ftp", "stp", "upc", "apc", "gtin", "ean", "ncm", "cest", "cfop", "vpn",
    "ptz", "epi", "usb", "hdmi", "vga", "rj45", "ups", "gsm", "gps", "rfid",
    "cpf", "cnpj", "sla", "ia", "tb", "gb", "mb", "mp", "hp", "kva", "kwh",
    "mbps", "gbps", "nbr", "abnt", "os", "nfe", "nfse",
}

#: Palavra portuguesa curta que aparece GRITADA e NÃO é sigla. A regra por forma sozinha
#: preservaria "CABO" e "RACK"; esta lista é a exceção dela.
_NAO_E_SIGLA = {
    "cabo", "kit", "rede", "luz", "tubo", "base", "fita", "mesa", "rack", "tela",
    "piso", "cano", "fio", "fios", "peca", "peça", "kits", "novo", "nova", "alta",
    "área", "area", "obra", "hora", "dias", "mês", "mes", "ano", "por", "com", "para",
    "sem", "tipo", "caso", "item", "unid", "cada", "poço", "poco", "vala", "poste",
}

#: Descem no MEIO da frase (nunca na primeira posição).
_LIGACAO = {"de", "da", "do", "das", "dos", "e", "ou", "com", "sem", "para", "por",
            "em", "no", "na", "nos", "nas", "a", "o", "as", "os", "ao", "à", "às"}

_TEM_DIGITO = re.compile(r"\d")
_BORDAS = "()[]{},.;:—–•\"'"


def _nucleo(tok: str) -> str:
    """Token sem pontuação de borda. O hífen NÃO é borda: 'LC-LC' é um núcleo só."""
    return tok.strip(_BORDAS)


def _troca(tok: str, novo: str) -> str:
    """Substitui o núcleo preservando a pontuação de borda ('(cabo' → '(Cabo')."""
    n = _nucleo(tok)
    if not n:
        return tok
    i = tok.find(n)
    return tok[:i] + novo + tok[i + len(n):]


_VOGAIS = set("aeiouáàâãéêíóôõúüAEIOUÁÀÂÃÉÊÍÓÔÕÚÜ")


def _e_sigla_por_forma(n: str, tudo_caps: bool) -> bool:
    """Curto e em caixa alta = sigla/código de modelo.

    ⚠️ A regra depende do CONTEXTO, e ignorar isso me custou "MÃO DE OBRA" → "MÃO DE obra"
    em 27/08/2026, no arquivo real do Bling. Num nome MISTO ("gravador NVR 4 canais"), o
    caps salta e carrega informação. Num nome TODO em caps ("CONJUNTO EIXO PRINCIPAL DZ"),
    tudo grita e o sinal não distingue nada — usá-lo ali é ler ruído como sinal.

    Então, em nome todo-caps, só sobrevive o que não parece palavra: token SEM VOGAL
    (ZZ, NR, DZ, ZB, FC, T, L) ou o que estiver nas listas explícitas. "EIXO" e "MÃO" têm
    vogal e descem; "DZ" fica.

    Sigla com acento não existe: `isascii` derruba MÃO antes de qualquer outra coisa.
    """
    if not (n.isupper() and n.isalpha() and n.isascii()):
        return False
    if n.lower() in _NAO_E_SIGLA:
        return False
    if tudo_caps:
        return not (set(n) & _VOGAIS)
    return len(n) <= 4


def _caixa_nucleo(n: str, primeiro: bool, tudo_caps: bool = False) -> str:
    baixo = n.lower()

    if _TEM_DIGITO.search(n):          # medida ou código: intocável
        return n
    if baixo in _CANONICO:             # grafia própria vence tudo
        return _CANONICO[baixo]
    if "-" in n and len(n) > 1:        # LC-LC, TP-Link, off-grid → parte a parte
        partes = n.split("-")
        return "-".join(_caixa_nucleo(p, primeiro and i == 0, tudo_caps)
                        for i, p in enumerate(partes))
    # LIGAÇÃO ANTES da regra de forma: "DE"/"DO" em nome gritado passavam por sigla.
    if not primeiro and baixo in _LIGACAO:
        return baixo
    if _e_sigla_por_forma(n, tudo_caps):   # já veio gritado e é sigla → fica
        return n
    if baixo in _SIGLAS:               # veio minúscula e é sigla → sobe
        return baixo.upper()
    # Caixa interna deliberada que não é grito ("iPhone", "eSocial") → respeita.
    if len(n) > 1 and n[1:] != n[1:].lower() and not n.isupper():
        return n
    return (baixo[:1].upper() + baixo[1:]) if primeiro else baixo


def normalizar_nome_produto(nome: str) -> str:
    """Sentence case com siglas, marcas e medidas preservadas. Idempotente."""
    if not nome:
        return ""
    bruto = re.sub(r"\s+", " ", str(nome).strip())
    if not bruto:
        return ""

    # Nome inteiramente gritado: o caps deixa de ser sinal. Ver `_e_sigla_por_forma`.
    tudo_caps = not any(c.islower() for c in bruto if c.isalpha())

    saida: list[str] = []
    primeiro = True
    for tok in bruto.split(" "):
        n = _nucleo(tok)
        saida.append(_troca(tok, _caixa_nucleo(n, primeiro, tudo_caps)) if n else tok)
        # Só pontuação FORTE reinicia a frase; depois de vírgula ela continua.
        # ⚠️ Travessão NÃO reinicia: "Agente de portaria — posto 12x36" virava
        # "— Posto 12x36". Em português o travessão abre aposto, não frase nova.
        primeiro = tok.endswith((".", ":", ";"))
    return " ".join(saida)


def _autoteste() -> int:
    casos = [
        ("HD 2 TB Purple (surveillance)", "HD 2 TB Purple (surveillance)"),
        ("hd 2 tb purple (SURVEILLANCE)", "HD 2 TB Purple (surveillance)"),
        ("CÂMERA BULLET IP 4 MP 360°", "Câmera bullet IP 4 MP 360°"),
        ("cordão óptico LC-LC duplex monomodo 2,5m",
         "Cordão óptico LC-LC duplex monomodo 2,5m"),
        ("MOTOR DESLIZANTE 1/3HP", "Motor deslizante 1/3HP"),
        ("switch gerenciável intelbras SG 16 portas",
         "Switch gerenciável Intelbras SG 16 portas"),
        ("gravador NVR 4 canais PoE com IA", "Gravador NVR 4 canais PoE com IA"),
        ("GRAVADOR NVR 4 CANAIS POE COM IA", "Gravador NVR 4 canais PoE com IA"),
        ("DPS classe II (conjunto + disjuntores) por rack",
         "DPS classe II (conjunto + disjuntores) por rack"),
        ("CABO CAT6 - CAIXA 305M", "Cabo CAT6 - caixa 305M"),
        # Nomes REAIS do Bling, todos gritados — o caso que derrubou a 1ª versão.
        ("MÃO DE OBRA", "Mão de obra"),
        ("CONJUNTO DE ALAVANCAS DO DESTRAVAMENTO", "Conjunto de alavancas do destravamento"),
        ("CONJUNTO EIXO PRINCIPAL DZ INDUSTRIAL", "Conjunto eixo principal DZ industrial"),
        ("ROLAMENTO 6203 ZZ NR C3 1ª LINHA", "Rolamento 6203 ZZ NR C3 1ª linha"),
        ("NOBREAK ATTIV 1200VA", "Nobreak attiv 1200VA"),
        ("EMENDA INTERNA T 38X38 PERFIL LIDER", "Emenda interna T 38X38 perfil lider"),
        ("haste de esticar 25x25", "Haste de esticar 25x25"),
        ("   patch   cords   cat6  2,5m ", "Patch cords cat6 2,5m"),
        ("SERVIÇO: terminação de fibra em DIO, fusão e testes",
         "Serviço: Terminação de fibra em DIO, fusão e testes"),
        ("Agente de portaria (AGP) noturno — posto 12x36",
         "Agente de portaria (AGP) noturno — posto 12x36"),
        ("", ""),
    ]
    ruins = []
    for entrada, esperado in casos:
        obtido = normalizar_nome_produto(entrada)
        if obtido != esperado:
            ruins.append(f"  {entrada!r}\n    esperado {esperado!r}\n    obtido   {obtido!r}")
        if normalizar_nome_produto(obtido) != obtido:
            ruins.append(f"  NÃO IDEMPOTENTE: {obtido!r} → "
                         f"{normalizar_nome_produto(obtido)!r}")
    if ruins:
        print("FALHOU:\n" + "\n".join(ruins))
        return 1
    print(f"OK nome_produto: {len(casos)} casos — sigla curta gritada fica, sigla "
          f"minúscula sobe, palavra portuguesa gritada desce, marca com caixa própria, "
          f"medida intacta, hifenizado parte a parte, e idempotente")
    return 0


if __name__ == "__main__":
    raise SystemExit(_autoteste())
