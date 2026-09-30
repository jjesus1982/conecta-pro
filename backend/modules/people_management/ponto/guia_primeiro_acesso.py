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
import os

URL_PORTAL = "https://erp.conectamais.pro"

#: Frase curta para avisos automáticos, onde não cabe o passo a passo inteiro.
COMO_BATER_CURTO = f"Bata o ponto no Conecta PRO, pelo navegador do celular: {URL_PORTAL} → Meu Espaço."

#: ⚠️ DIARISTA NÃO BATE PONTO — regra do dono, 26/09/2026: *"diarista não bate ponto, a diária é
#: o registro"*. Existe porque o agente NÃO SABIA e errou duas vezes na mesma conversa: registrou
#: batida de contingência para a THAYNÁ, que é diarista (sem `shifts`), e ainda gravou a hora
#: ERRADA — 12:18, o minuto da conversa, quando o supervisor a havia anunciado no posto às 07:00.
#: Cinco horas de diferença num registro que a folha lê.
DIARISTA_NAO_BATE = (
    "DIARISTA NÃO BATE PONTO: o lançamento da diária (`diaria_lancamentos`, com data, posto, "
    "turno e valor) JÁ É o registro do trabalho dele. Antes de registrar batida ou contingência "
    "para alguém, confira se a pessoa tem TURNO em `shifts` hoje. Sem turno, NÃO registre "
    "batida — você estaria criando um registro que não deveria existir. "
    "⚠️ E QUANDO REGISTRAR para quem TEM turno: a hora é a da ENTRADA REAL da pessoa (a do "
    "turno, ou a que ela/o supervisor informou), NUNCA o minuto em que a conversa está "
    "acontecendo. Gravar 'agora' transforma 5 horas trabalhadas em 5 horas perdidas."
)

#: ⭐ OS QUATRO POSTOS DE INTRAJORNADA — Jordan, 27/09/2026: *"tem 4 condomínios que os agentes
#: de portaria não batem intervalo, eles batem apenas entrada e saída, pois recebem o valor
#: adicional de intrajornada"*.
#:
#: 🔴 Existe porque o agente ERROU por não saber: disse ao ALAN *"qualquer trave na saída do
#: almoço, me chama"* — no Prime Arena, que é um desses quatro. Ofereceu ajuda para uma batida
#: que não deve existir. Eu havia ajustado os turnos E a flag do posto no banco, mas a regra
#: não estava no contexto dele. Terceira vez com a mesma causa: Tangerino, diarista, e agora
#: intrajornada. **Ele só sabe o que está escrito aqui.**
POSTOS_INTRAJORNADA = ("Condomínio Green Hills", "Condomínio Prime Arena",
                       "Condomínio Villa Dei Fiori", "Condomínio Villa dos Pássaros")

INTRAJORNADA = (
    "INTRAJORNADA — nestes quatro postos o AGENTE DE PORTARIA bate SÓ entrada e saída, NUNCA "
    "intervalo, porque recebe o adicional de intrajornada: "
    + " · ".join(POSTOS_INTRAJORNADA) + ". "
    "⚠️ NUNCA mencione almoço, intervalo ou pausa para quem trabalha nestes postos, e NUNCA "
    "ofereça ajuda com 'batida de almoço' — ela não existe lá. Se a pessoa disser que o app "
    "pediu intervalo, isso é DEFEITO a registrar, não orientação a dar. "
    "⚠️ A jornada segue 12 horas: a pausa é DENTRO dela e é paga, não é desconto. "
    "⚠️ Nos outros postos o intervalo existe normalmente — a regra é por POSTO, não por pessoa."
)

#: 🔴 QUARTA VEZ COM A MESMA CAUSA (30/09/2026, 06:57, e de novo com o WISLEY).
#:
#: Ele escreveu «não tá indo» e o agente respondeu: *«se você tentou antes das 07:00, o sistema
#: recusa mesmo — a janela abre no horário»*. **Falso.** A parede aceita até 5 minutos antes, e
#: eram 06:57: ele estava DENTRO. Provado por comportamento: **66 batidas em 30 dias foram
#: aceitas até 5 minutos antes** do início do turno.
#:
#: ⚠️ O custo não é a frase: é o desvio. Ele passa a achar que bastava esperar, e a causa real
#: do «não tá indo» fica sem apuração.
#:
#: E a causa é a de sempre — o prompt do agente não tinha **uma única** menção à tolerância.
#: «Faltar informação não produz silêncio no modelo: produz invenção plausível.» Tangerino,
#: diarista, intrajornada, e agora a janela. **Ele só sabe o que está escrito aqui.**
#:
#: ⭐ Lê a MESMA variável de ambiente que a parede (`punch_service`) e que o lembrete. Se alguém
#: mudar para 10, esta frase muda junto — número num lugar só.
TOLERANCIA_ANTES_MIN = int(os.getenv("PONTO_TOLERANCIA_ANTES_MIN", "5"))

JANELA_DA_BATIDA = (
    f"JANELA DA BATIDA — a tolerância é de {TOLERANCIA_ANTES_MIN} minutos, PARA OS DOIS LADOS. "
    f"Bater até {TOLERANCIA_ANTES_MIN} min ANTES do horário é ACEITO normalmente. "
    f"⚠️ NUNCA diga que o sistema recusa por ser «antes da hora» sem conferir a diferença: "
    f"quem bate 3 minutos antes das 07:00 está DENTRO da janela, e dizer o contrário manda a "
    f"pessoa esperar por nada E esconde a causa real da falha dela. "
    f"Só além de {TOLERANCIA_ANTES_MIN} minutos adiantado a batida é recusada — e aí a mensagem "
    f"do sistema diz isso com todas as letras. Se ela não disse, NÃO foi esse o motivo."
)

#: ⚠️ O que NUNCA deve ser dito. Existe para o agente ter a negativa explícita, não só a
#: ausência de informação — foi a ausência que produziu o erro do Tangerino.
NUNCA_DIZER = (
    "NÃO existe aplicativo de ponto da Conecta PRO em loja nenhuma. Nunca mande ninguém "
    "procurar app na App Store ou no Play Store, e NUNCA mencione o Tangerino como caminho "
    "para bater: ele foi desligado em 13/09/2026 e não registra mais nada. Se a pessoa já "
    "instalou o Tangerino, diga que aquele caminho morreu e passe o endereço do portal."
)


def guia(nome: str, email: str) -> str:
    """O passo a passo, personalizado. Serve para qualquer colaborador novo.

    ⚠️ A SENHA É SEMPRE O CPF. Jordan, 26/09/2026: *"a senha é sempre o cpf, não tem opção de
    criar senha"*. Minha primeira versão tinha um parâmetro `senha_e_cpf=False` para "quem criou
    senha própria" — um caso que NÃO EXISTE neste sistema, inventado por mim a partir de o Jair
    ter chegado por autocadastro. Mandei a ele "a senha é a que você criou", que é uma porta
    fechada. Não há variante: é o CPF.
    """
    primeiro = (nome or "").strip().split(" ")[0].title() or "tudo bem"
    senha = "🔒 *Senha:* o seu *CPF*, só os números — sem ponto e sem traço"
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
        # ⚠️ A ORDEM É A DO MUNDO, não a da minha cabeça: permissão → rosto → batida. Minha
        # primeira versão punha "bater o ponto" antes do cadastro do rosto, e a pessoa chegava
        # na batida sem poder concluir. Passo fora de ordem é passo que trava.
        "*4. Autorizar as duas permissões* — sem elas nada funciona\n"
        "📍 *Localização:* o sistema confere se você está no posto\n"
        "📷 *Câmera:* a batida tira uma foto sua, é a prova de que foi você\n\n"
        "*5. Cadastrar o rosto — UMA vez só*\n"
        "Na primeira vez o sistema pede *\"Cadastrar meu rosto\"*. Faça com boa luz, sem boné, "
        "sem óculos escuros e sem máscara. Depois disso é só olhar para a câmera em cada "
        "batida.\n"
        "⚠️ *Sem o rosto cadastrado a batida não passa* — é o passo que mais trava gente no "
        "primeiro dia.\n\n"
        "*6. Bater o ponto*\n"
        "Em *Meu Espaço* → *Ponto*. Bata na *entrada* e na *saída* do seu turno.\n\n"
        "*Se travar:* me manda aqui *o que apareceu na tela* (print ajuda). Eu registro sua "
        "batida por aqui no mesmo minuto e você não perde a hora — depois o DP valida. 🙏"
    )


async def enviar_guia(db, *, nome_ou_id: str) -> dict:
    """Manda o guia para UMA pessoa. Delega a resolução do destinatário à porta única.

    ⚠️ UM caminho, não dois. Minha primeira versão desta função resolvia o telefone por conta
    própria — e duas implementações da mesma regra divergem na primeira mudança, que é como esta
    casa ficou com três pareadores de batida e o terceiro com defeito por meses.
    `whatsapp.destinatario` é a porta: ela recusa ambíguo, desconhecido e telefone malformado.
    """
    from modules.integrations.connectors.whatsapp.destinatario import mandar, resolver

    alvo = await resolver(db, nome_ou_id)
    if not alvo["ok"]:
        return alvo
    if not alvo["email"]:
        return {"ok": False, "motivo": f"{alvo['nome']} está sem e-mail no cadastro — sem e-mail "
                                      "não há login para explicar, e inventar e-mail é o mesmo "
                                      "erro de inventar telefone (eu inventei o do Euler)"}
    return await mandar(db, quem=alvo["employee_id"],
                        texto=guia(alvo["nome"], alvo["email"]),
                        motivo="guia de primeiro acesso ao ponto")


#: ⭐ O CONVITE QUE FECHA O CICLO — Jordan, 26/09/2026: *"manda pro orlailson o link de
#: autocadastro de novos funcionários, assim ele vai mandar todas as vezes que um novo
#: funcionário for contratado, daí fechamos o ciclo e automatizamos tudo isso"*.
#:
#: ⚠️ NÃO EXISTE PÁGINA DE CADASTRO SEPARADA. Medido: as contas do Jair, da Thayná e do Ramon
#: nasceram todas por **login com Google** (`google_id` preenchido) — o callback do Google cria
#: o usuário como `role='pending'` no primeiro acesso. O "link de autocadastro" é a própria tela
#: de login; quem cria a conta é o primeiro clique da pessoa.
#:
#: Ciclo completo, e cada elo existe de verdade:
#:   1. o supervisor manda este convite ao contratado
#:   2. ele entra com o Gmail → conta nasce `pending` e o sino avisa os admins
#:   3. Jordan ou Pyetra aprovam (perfil `funcionario` + vínculo com o colaborador)
#:   4. a aprovação DISPARA o guia automaticamente (`api/v1/endpoints/users.py::aprovar_user`)
CONVITE_AUTOCADASTRO = "\n".join([
    "*Cadastro de novo colaborador — Conecta PRO*",
    "",
    "Manda este passo a passo para a pessoa no primeiro dia. Leva 1 minuto e é ela quem faz:",
    "",
    f"1️⃣ Abrir *{URL_PORTAL}* no navegador do celular",
    "2️⃣ Tocar em *Entrar com Google* e usar o *Gmail dela*",
    "3️⃣ Pronto — o cadastro fica *aguardando aprovação* e nós recebemos o aviso",
    "",
    "Depois que o Jordan ou a Pyetra aprovarem, *o sistema manda sozinho* para ela o passo a "
    "passo de como bater o ponto: como entrar, onde fica o ponto e as permissões de localização "
    "e câmera. Você não precisa explicar nada disso.",
    "",
    "⚠️ Duas coisas importantes:",
    "• *Precisa ser Gmail* — é por ele que o acesso é criado",
    "• *Não existe app para baixar.* Se alguém procurar na loja do celular não vai achar, e o "
    "*Tangerino foi desligado* em 13/09. É o navegador, sempre.",
    "",
    "Me avisa quando mandar para alguém que eu acompanho a aprovação. 🙏",
])
