"""O passo a passo ÚNICO de primeiro acesso ao ponto. Uma fonte, para todo mundo.

🔴 POR QUE ESTE ARQUIVO NASCEU EM 26/09/2026 — o agente improvisou e mandou um recém-contratado
instalar um app morto.

O José Luís disse ao Wisley, contratado ontem: *"É o Tangerino, Wisley. No iPhone não precisa de
link — abre a App Store e busca Tangerino"*. O **Tangerino está desligado desde 13/09**: medido,
223 batidas até aquele dia e ZERO depois. O rapaz ia baixar um app morto e continuar sem bater.

⭐ E A CULPA NÃO FOI DO MODELO: foi do que a casa REPETIA. O lembrete diário de ponto dizia
*"Bata o ponto pelo app do Conecta PRO"* — uma frase errada saindo para todo mundo, todos os
dias. Jordan: *"não usamos app ainda, usamos o link do sistema do portal do funcionário no
navegador"*. Sem nenhum fato melhor no contexto, o agente completou a frase com o único app de
ponto que ele conhecia pelo histórico. **Uma mentira repetida 1.500 vezes vira a verdade dele.**

Então o remédio não é proibir o agente de falar: é **existir um texto certo para ele usar**. Este
módulo é esse texto, e é a única fonte — se o caminho mudar, muda aqui e muda em todo lugar.

⚠️ NÃO INVENTE PASSO. Cada linha abaixo está no dado ou na palavra do dono:
  · navegador, não app                      → Jordan, 26/09
  · `erp.conectamais.pro`                   → o link que a casa já manda nos avisos
  · senha inicial = CPF                     → `candidatos_esteira_controller`, convenção do
                                              onboarding, e foi como eu criei France e Wisley
  · foto + localização                      → `gp_clock_punches` tem `foto_capturada_url`,
                                              `latitude/longitude` e `dentro_geofence`
  · Tangerino nunca                         → última batida dele 13/09/2026
"""
from __future__ import annotations

#: Onde o ponto é batido. UMA constante — a que o lembrete, o agente e o guia usam.
URL_PORTAL = "https://erp.conectamais.pro"

#: Frase curta para avisos automáticos, onde não cabe o passo a passo inteiro.
COMO_BATER_CURTO = f"Bata o ponto no Conecta PRO, pelo navegador do celular: {URL_PORTAL} → Meu Espaço."

#: ⚠️ O que NUNCA deve ser dito. Existe para o agente ter a negativa explícita, não só a
#: ausência de informação — foi a ausência que produziu o erro do Tangerino.
NUNCA_DIZER = (
    "NÃO existe aplicativo de ponto da Conecta PRO em loja nenhuma. Nunca mande ninguém "
    "procurar app na App Store ou no Play Store, e NUNCA mencione o Tangerino como caminho "
    "para bater: ele foi desligado em 13/09/2026 e não registra mais nada. Se a pessoa já "
    "instalou o Tangerino, diga que aquele caminho morreu e passe o endereço do portal."
)


def guia(nome: str, email: str, *, senha_e_cpf: bool = True) -> str:
    """O passo a passo, personalizado. Serve para qualquer colaborador novo.

    `senha_e_cpf=False` para quem já trocou a senha ou fez autocadastro com senha própria —
    prometer "sua senha é o CPF" a quem escolheu outra senha é mandar a pessoa bater numa porta
    fechada e ensinar que a nossa orientação não vale.
    """
    primeiro = (nome or "").strip().split(" ")[0].title() or "tudo bem"
    senha = ("🔒 *Senha:* o seu *CPF*, só os números — sem ponto e sem traço"
             if senha_e_cpf else
             "🔒 *Senha:* a que você criou no cadastro. Se não lembrar, me chama que eu peço "
             "a redefinição ao DP")
    return (
        f"Oi {primeiro}! Aqui é o José Luís. Vou te passar o passo a passo do ponto. 👇\n\n"
        "⚠️ *Não existe app para baixar.* Não procure nada na loja do celular — o ponto é "
        "batido pelo *navegador*, no site do Conecta PRO.\n\n"
        "*1. Abrir*\n"
        f"No navegador do celular (Safari no iPhone, Chrome no Android), abra:\n{URL_PORTAL}\n\n"
        "*2. Entrar*\n"
        f"📧 *E-mail:* {email}\n{senha}\n\n"
        "*3. Deixar na tela inicial* (assim vira um ícone e você não digita o endereço de novo)\n"
        "• *iPhone:* toque em *Compartilhar* (o quadradinho com a seta) → *Adicionar à Tela de "
        "Início*\n"
        "• *Android:* toque nos *três pontinhos* → *Adicionar à tela inicial*\n\n"
        "*4. Bater o ponto*\n"
        "Dentro do sistema, vá em *Meu Espaço* → *Ponto*. Bata na *entrada* e na *saída* do seu "
        "turno.\n\n"
        "*5. Autorizar as duas permissões* — sem elas a batida NÃO fecha\n"
        "📍 *Localização:* o sistema confere se você está no posto\n"
        "📷 *Câmera:* a batida tira uma foto sua, é a prova de que foi você\n\n"
        "*Se travar:* me manda aqui *o que apareceu na tela* (print ajuda). Eu registro sua "
        "batida por aqui no mesmo minuto e você não perde a hora — depois o DP valida. 🙏"
    )
