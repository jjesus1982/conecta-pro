"""Cria o MODELO de contrato de PORTARIA REMOTA (Conecta Mais Eletrônica).

Pedido do Jordan em 10/09/2026, para o segundo contrato do Kopenhagen: a proposta é mista —
agentes de portaria (Patrimonial, R$ 40.612/mês) e portaria remota (Eletrônica,
R$ 4.700/mês) — e a regra da casa é que a proposta pode misturar, o contrato e a nota
fiscal NUNCA. Faltava o instrumento do lado eletrônico.

⚠️ COMO ESTE TEXTO FOI FEITO, e o que isso exige de você:

O que é REUSO de cláusula já revisada pelo jurídico da casa:
  · LGPD com biometria facial (art. 11 da Lei 13.709/2018), incluindo a responsabilidade
    integral e regressiva por vazamento — vem do contrato Chácaras Maiápolis, revisão
    Furtado Maia, aprovado em 09/09/2026;
  · propriedade e licença do software Conecta Plus — mesma origem;
  · reajuste anual pelo IPCA e vigência com renovação automática — vêm do modelo de
    Manutenção de Segurança Eletrônica, aprovado em 22/08/2026;
  · fecho por assinatura eletrônica (MP 2.200-2 art. 10 §2º + CPC 784 §4º).

O que é NOVO e NÃO passou por advogado — as três cláusulas que nenhum contrato da casa
tinha, porque nenhum outro serviço aluga equipamento:
  · Cláusula 3ª  — locação dos equipamentos (posse, propriedade, uso, seguro)
  · Cláusula 8ª  — devolução ao término e o que acontece se houver dano ou falta
  · Cláusula 4ª  — obrigações de INFRAESTRUTURA da contratante (energia, internet), que
                   num serviço remoto é a causa mais comum de indisponibilidade e de
                   discussão sobre de quem é a culpa

Essas três precisam de leitura jurídica antes do primeiro contrato assinado. O modelo já
serve para MINUTA (é para isso que a minuta existe) — não para assinatura sem revisão.

O escopo do serviço é o da apresentação comercial do próprio Jordan
(Apresentacao_Kopenhagen_PortariaRemota.pptx): central 24h em Manaus, atendimento por IA de
voz com vídeo chamada ao morador, leitor facial, antenas de tag, motores de portão e o
aplicativo Conecta Plus.

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/seed/modelo_portaria_remota.py
"""
import asyncio
import json

from sqlalchemy import text

from core.database import async_session_factory

TEMPLATE = """CONTRATO DE PRESTAÇÃO DE SERVIÇOS DE PORTARIA REMOTA, MONITORAMENTO E LOCAÇÃO DE EQUIPAMENTOS

Pelo presente instrumento particular de prestação de serviços, de um lado:

CONTRATADA: {{contratada_razao_social}}, inscrita no CNPJ sob o nº {{contratada_cnpj}}, com sede em {{contratada_endereco}}, neste ato representada por seu {{contratada_cargo}}, Sr. {{contratada_representante}}, inscrito no CPF sob o nº {{contratada_representante_cpf}}; e, de outro lado:

CONTRATANTE: {{contratante_nome}}, inscrita no CNPJ sob o nº {{contratante_cnpj}}, com sede na {{contratante_endereco}}, neste ato representada por seu {{contratante_cargo}}, {{contratante_representante}}, inscrito no CPF sob o nº {{contratante_representante_cpf}};

têm entre si justo e contratado o presente Contrato de Prestação de Serviços de caráter CONTINUADO, regido pelas cláusulas a seguir.

CLÁUSULA PRIMEIRA — DO OBJETO

1.1. Constitui objeto deste contrato a prestação, pela CONTRATADA, dos serviços de PORTARIA REMOTA e monitoramento do CONTRATANTE, com o suporte da Central de Monitoramento da CONTRATADA, em Manaus/AM, em funcionamento 24 (vinte e quatro) horas por dia, todos os dias do ano, compreendendo:

a) atendimento remoto de visitantes e prestadores por assistente de voz e vídeo chamada dirigida ao morador, com acionamento da Central quando não houver resposta;
b) controle de acesso de veículos e de pedestres, com registro individualizado de cada entrada e saída, contendo data, hora e imagem;
c) acompanhamento das imagens dos pontos de acesso pela Central de Monitoramento;
d) acionamento dos serviços de emergência e comunicação ao CONTRATANTE em situação de risco;
e) disponibilização do Conecta Plus, aplicativo de gestão condominial e de controle de acessos, aos moradores e ao representante do CONTRATANTE, sem custo adicional durante a vigência.

1.2. Os serviços deste contrato NÃO substituem e não se confundem com a prestação de mão de obra de portaria presencial, que, quando contratada, é objeto de instrumento próprio e de outra prestadora.

CLÁUSULA SEGUNDA — DO PRAZO E DA VIGÊNCIA

2.1. O presente contrato vigorará pelo prazo de {{vigencia_meses_extenso}} meses, com início em {{vigencia_inicio_extenso}} e término em {{vigencia_fim_extenso}}, renovável automaticamente por igual período, salvo manifestação em contrário de qualquer das partes, por escrito, com antecedência mínima de {{renovacao_aviso_dias_extenso}} dias do termo.

CLÁUSULA TERCEIRA — DA LOCAÇÃO DOS EQUIPAMENTOS

3.1. Para a execução dos serviços, a CONTRATADA instala e mantém no CONTRATANTE, em regime de LOCAÇÃO, os equipamentos discriminados na proposta comercial aceita, que permanecem em sua propriedade durante toda a vigência e após o término deste contrato.

3.2. Os equipamentos são entregues em perfeito estado de funcionamento e destinam-se exclusivamente à execução deste contrato, sendo vedado ao CONTRATANTE removê-los, cedê-los, sublocá-los, modificá-los ou permitir intervenção de terceiros não autorizados pela CONTRATADA.

3.3. A manutenção preventiva e corretiva dos equipamentos locados, incluindo peças e mão de obra, é de responsabilidade da CONTRATADA e está inclusa no valor mensal, ressalvadas as hipóteses do item 3.4.

3.4. Respondem por conta do CONTRATANTE os danos decorrentes de mau uso, vandalismo, furto, intervenção de terceiros não autorizados, surtos elétricos e descargas atmosféricas, hipóteses em que o reparo ou a reposição serão orçados à parte e executados após aprovação.

CLÁUSULA QUARTA — DAS OBRIGAÇÕES DA CONTRATANTE

4.1. Para que o serviço remoto funcione, o CONTRATANTE obriga-se a manter, às suas expensas e em funcionamento contínuo: energia elétrica nos pontos de instalação; link de internet com a capacidade indicada pela CONTRATADA; e as condições físicas de acesso aos equipamentos.

4.2. A indisponibilidade de energia ou de link de internet suspende a prestação do serviço remoto enquanto perdurar, sem ônus para a CONTRATADA e sem suspensão do faturamento, cabendo ao CONTRATANTE comunicar a ocorrência de imediato.

4.3. São ainda obrigações do CONTRATANTE: manter atualizado o cadastro de moradores, veículos e autorizados; designar responsável para acompanhamento; e efetuar os pagamentos nos prazos ajustados.

CLÁUSULA QUINTA — DAS OBRIGAÇÕES DA CONTRATADA

5.1. Manter a Central de Monitoramento em operação 24 horas por dia, todos os dias do ano; empregar operadores treinados; manter os equipamentos locados em funcionamento; guardar sigilo sobre imagens e dados a que tiver acesso; manter sua regularidade fiscal e trabalhista; e prestar suporte técnico ao CONTRATANTE.

CLÁUSULA SEXTA — DO VALOR E DO PAGAMENTO

6.1. Pelos serviços e pela locação dos equipamentos descritos neste contrato, o CONTRATANTE pagará à CONTRATADA o valor mensal de {{valor_mensal_fmt}} ({{valor_mensal_extenso}}).

[[TABELA_COMPOSICAO]]

6.2. O pagamento será mensal, por PIX, boleto ou transferência, com vencimento no dia {{dia_vencimento}} ({{dia_vencimento_extenso}}) de cada mês.

6.3. O atraso no pagamento sujeitará o CONTRATANTE à multa de 2% (dois por cento), juros de mora de 1% (um por cento) ao mês e correção monetária, sem prejuízo da suspensão dos serviços após 15 (quinze) dias de inadimplência, mediante prévia comunicação.

CLÁUSULA SÉTIMA — DO REAJUSTE

7.1. O valor mensal será reajustado anualmente, tendo como data-base o mês de assinatura deste contrato ({{mes_base_reajuste}}), pela variação acumulada do IPCA nos 12 (doze) meses anteriores à data do reajuste, ou, na sua ausência, por índice oficial que o substitua.

CLÁUSULA OITAVA — DA DEVOLUÇÃO DOS EQUIPAMENTOS

8.1. Encerrado este contrato por qualquer motivo, o CONTRATANTE facultará à CONTRATADA, em até 10 (dez) dias úteis, o acesso necessário à retirada dos equipamentos locados.

8.2. Os equipamentos serão devolvidos no estado em que foram entregues, ressalvado o desgaste natural de uso. Havendo dano ou falta, o CONTRATANTE indenizará a CONTRATADA pelo valor de reposição do bem, apurado em orçamento apresentado.

8.3. A retirada dos equipamentos não depende de notificação judicial e não caracteriza interrupção indevida de serviço, uma vez encerrada a vigência.

CLÁUSULA NONA — DA PROPRIEDADE E DA LICENÇA DE SOFTWARE

9.1. Os softwares e a plataforma Conecta Plus são de propriedade da CONTRATADA, licenciados ao CONTRATANTE apenas para uso conforme sua finalidade e durante a vigência deste contrato, vedada a cópia, redistribuição, sublicenciamento ou modificação.

CLÁUSULA DÉCIMA — DA PROTEÇÃO DE DADOS (LGPD)

10.1. O serviço envolve o tratamento de dados pessoais, inclusive imagens e biometria facial (dado sensível, art. 11 da Lei nº 13.709/2018). O CONTRATANTE é o CONTROLADOR e a CONTRATADA atua como OPERADORA, tratando os dados exclusivamente para a finalidade contratada e conforme as instruções do CONTROLADOR, com medidas de segurança adequadas, confidencialidade, comunicação de incidentes sem demora injustificada e eliminação ao término do contrato, salvo obrigação legal de guarda.

10.2. A CONTRATADA responderá integral e regressivamente perante o CONTRATANTE por eventuais multas, condenações judiciais ou indenizações de terceiros decorrentes de incidentes de segurança da informação (como vazamento de imagens ou de dados biométricos) cuja origem decorra de falha ou vulnerabilidade de segurança da própria plataforma Conecta Plus ou da Central de Monitoramento.

10.3. As imagens captadas serão armazenadas pelo prazo técnico do sistema e disponibilizadas ao CONTRATANTE mediante solicitação formal de seu representante legal, observada a finalidade de segurança.

CLÁUSULA DÉCIMA PRIMEIRA — DA RESCISÃO

11.1. O contrato poderá ser rescindido por qualquer das partes, imotivadamente, mediante aviso prévio por escrito de 30 (trinta) dias.

11.2. O descumprimento de qualquer cláusula, não sanado no prazo de 10 (dez) dias após notificação, faculta à parte prejudicada a rescisão imediata, sem prejuízo das penalidades e da cobrança dos valores devidos até a data da rescisão.

11.3. Em qualquer hipótese de rescisão, observar-se-á o disposto na Cláusula Oitava quanto à devolução dos equipamentos.

CLÁUSULA DÉCIMA SEGUNDA — DAS DISPOSIÇÕES GERAIS

12.1. Este contrato não gera vínculo empregatício entre as partes. Alterações somente terão validade se formalizadas por termo aditivo escrito. A tolerância quanto ao descumprimento de qualquer cláusula não implica novação ou renúncia.

CLÁUSULA DÉCIMA TERCEIRA — DO FORO

13.1. As partes elegem o foro da Comarca de {{foro}} para dirimir quaisquer questões oriundas deste contrato, com renúncia a qualquer outro, por mais privilegiado que seja.

Por terem lido e concordado com todas as cláusulas e condições ora estabelecidas, as partes firmam o presente instrumento por assinatura eletrônica, na forma do art. 10, § 2º, da MP nº 2.200-2/2001, dispensada a assinatura de testemunhas nos termos do art. 784, § 4º, do Código de Processo Civil, uma vez que a integridade deste documento é conferida pelo provedor de assinatura, conforme manifesto ao final.

{{cidade_assinatura}}, {{data_assinatura_extenso}}.

[[BLOCO_ASSINATURAS]]
"""

CLAUSULAS = [
    "CLÁUSULA PRIMEIRA — DO OBJETO",
    "CLÁUSULA SEGUNDA — DO PRAZO E DA VIGÊNCIA",
    "CLÁUSULA TERCEIRA — DA LOCAÇÃO DOS EQUIPAMENTOS",
    "CLÁUSULA QUARTA — DAS OBRIGAÇÕES DA CONTRATANTE",
    "CLÁUSULA QUINTA — DAS OBRIGAÇÕES DA CONTRATADA",
    "CLÁUSULA SEXTA — DO VALOR E DO PAGAMENTO",
    "CLÁUSULA SÉTIMA — DO REAJUSTE",
    "CLÁUSULA OITAVA — DA DEVOLUÇÃO DOS EQUIPAMENTOS",
    "CLÁUSULA NONA — DA PROPRIEDADE E DA LICENÇA DE SOFTWARE",
    "CLÁUSULA DÉCIMA — DA PROTEÇÃO DE DADOS (LGPD)",
    "CLÁUSULA DÉCIMA PRIMEIRA — DA RESCISÃO",
    "CLÁUSULA DÉCIMA SEGUNDA — DAS DISPOSIÇÕES GERAIS",
    "CLÁUSULA DÉCIMA TERCEIRA — DO FORO",
]

# Sem testemunha: este modelo invoca a dispensa do art. 784 §4º, como manutenção e portaria.
# O único da casa que colhe testemunha é o `eletronica_servico_unico`, por decisão do Jordan
# em 09/09 — e lá o fecho NÃO invoca a dispensa. Os dois andam juntos, sempre.
VARIAVEIS = {"foro": "Manaus/AM", "cidade_assinatura": "Manaus/AM"}

TPL_ID = "c8f1d3b6-2e47-4a95-b073-9d5ac2e81f04"
SERVICE_TYPE = "portaria_remota"
NOME = "Portaria Remota — Monitoramento 24h e Locação de Equipamentos"
DESCRICAO = (
    "Portaria remota com Central 24h, atendimento por voz e vídeo, controle de acesso, "
    "locação dos equipamentos e Conecta Plus. Mensal, emitido pela Conecta Mais Eletrônica. "
    "⚠️ Cláusulas 3ª, 4ª e 8ª (locação, infraestrutura e devolução) ainda sem revisão "
    "jurídica — serve para MINUTA."
)


async def main() -> None:
    async with async_session_factory() as db:
        ja = (await db.execute(text(
            "SELECT id::text FROM contract_templates WHERE id::text = :i OR service_type = :s"),
            {"i": TPL_ID, "s": SERVICE_TYPE})).scalar()
        params = {"n": NOME, "d": DESCRICAO, "s": SERVICE_TYPE, "c": TEMPLATE,
                  "k": json.dumps(CLAUSULAS), "v": json.dumps(VARIAVEIS)}
        if ja:
            await db.execute(text(
                "UPDATE contract_templates SET name=:n, description=:d, service_type=:s, "
                "content_template=:c, clauses=CAST(:k AS jsonb), variables=CAST(:v AS jsonb), "
                "is_active=true, updated_at=now() WHERE id::text=:i"), {**params, "i": ja})
            print(f"  modelo ATUALIZADO ({len(TEMPLATE)} chars, {len(CLAUSULAS)} cláusulas)")
        else:
            await db.execute(text("""
                INSERT INTO contract_templates
                    (id, name, description, service_type, content_template, clauses, variables,
                     version, is_active, created_at, updated_at)
                VALUES (CAST(:i AS uuid), :n, :d, :s, :c, CAST(:k AS jsonb), CAST(:v AS jsonb),
                        1, true, now(), now())"""), {**params, "i": TPL_ID})
            print(f"  modelo CRIADO ({len(TEMPLATE)} chars, {len(CLAUSULAS)} cláusulas)")
        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
