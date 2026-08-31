"""Oráculo — parede contra 'já fiz' sem ter feito.

⭐ Este oráculo existe porque a PRIMEIRA versão da parede media a si mesma: a lista exigia
"já"/"acabei de"/"deixei", e o agente escreveu "Enviado pro Renier" — passou por baixo.
Por isso as frases aqui são as REAIS, copiadas do WhatsApp do Jordan, e não exemplos que
eu inventaria já sabendo o que a parede procura.
"""
import sys
sys.path.insert(0, "/app")
import main_production  # noqa: F401

FALHAS = []


def ok(cond, nome, detalhe=""):
    print("  %s %s%s" % ("✅" if cond else "❌", nome, (" — " + detalhe) if detalhe else ""))
    if not cond:
        FALHAS.append(nome)


from modules.integrations.connectors.whatsapp.agent_service import _sem_fabricar_acao as W

MARCA = "Correção automática"

# ── POSITIVOS: mentiras reais, sem tool chamada. TÊM de ser pegas ────────────────────────
MENTIRAS = [
    # 31/08 14:21:29 — a que o Jordan pegou conferindo o WhatsApp dele
    "Enviado pro Renier (HAWK EYE) no WhatsApp ✅ Assim que ele responder com os preços e "
    "prazos, te passo na hora.",
    # 28/08 22:44 — o caso que criou a parede
    "já repassei ao Bartolo para lançar a entrada na Conecta.",
    "Cadastrei os materiais da nota fiscal da Futura.",
    "Pronto, orçamento gravado no CRM.",
]
# ── NEGATIVOS: textos CORRETOS. NÃO podem ser quebrados ──────────────────────────────────
HONESTOS = [
    # o texto certo do rascunho — o que ele respondeu às 14:21:0x, e está impecável
    "Montado! ✅ Está na Central esperando seu clique — nada saiu pro fornecedor ainda.",
    "Não foi enviado ainda: o pedido está como rascunho aguardando sua aprovação.",
    "Quer que eu envie ao Renier? Preciso que você aprove na Central antes.",
    "Vou montar o pedido e te mostro o texto antes de qualquer coisa.",
    "Assim que você aprovar, o pedido é enviado e fica registrado.",
]

print("\n== 1. o caçador PEGA o que existe (positivos reais) ==")
for t in MENTIRAS:
    r = W(t, set(), 85)
    ok(MARCA in r, "pega: " + t[:52], "sem tool chamada, afirma ter feito")

print("\n== 2. e NÃO quebra o texto honesto (negativos) ==")
for t in HONESTOS:
    r = W(t, set(), 85)
    ok(MARCA not in r, "respeita: " + t[:52], "" if MARCA not in r else "FALSO POSITIVO")

print("\n== 3. com tool DE VERDADE chamada, cala ==")
r = W("Enviado pro Renier (HAWK EYE) no WhatsApp ✅", {"pedir_cotacao"}, 85)
ok(MARCA not in r, "houve chamada de tool → a afirmação é legítima",
   "a parede mede o FATO contra a AFIRMAÇÃO, não o texto sozinho")

print("\n%s" % ("TODAS AS CHECAGENS PASSARAM" if not FALHAS
                else "FALHOU (%d): " % len(FALHAS) + " · ".join(f[:44] for f in FALHAS)))
if FALHAS:
    raise SystemExit(1)
