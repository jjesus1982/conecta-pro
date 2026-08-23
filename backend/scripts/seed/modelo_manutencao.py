"""Cria o MODELO de contrato de manutenção de segurança eletrônica (Conecta Mais Eletrônica).

Texto entregue pelo Jordan em 22/08/2026, com os dados das partes substituídos por variáveis
para que o modelo sirva a outros condomínios. Nada do texto jurídico foi reescrito.

ÚNICA alteração de redação, e é a mesma decisão que o Jordan tomou para o contrato de
portaria: sai o fecho com testemunhas e "2 (duas) vias de igual teor", entra o fecho por
assinatura eletrônica (MP 2.200-2 art. 10 §2º + CPC 784 §4º, que dispensa testemunha em
documento eletrônico cuja integridade seja conferida pelo provedor). O manifesto ao final do
PDF é o que sustenta essa dispensa.
"""
import asyncio
import json
import uuid

from sqlalchemy import text

from core.database import async_session_factory

TEMPLATE = """CONTRATO DE PRESTAÇÃO DE SERVIÇOS DE MANUTENÇÃO PREVENTIVA E CORRETIVA DE SISTEMAS DE SEGURANÇA ELETRÔNICA

Pelo presente instrumento particular, de um lado:

CONTRATADA: {{contratada_razao_social}}, pessoa jurídica de direito privado, inscrita no CNPJ sob o nº {{contratada_cnpj}}, com sede na {{contratada_endereco}}, neste ato representada por seu Diretor Executivo, Sr. {{contratada_representante}}, brasileiro, portador da Cédula de Identidade RG nº {{contratada_representante_rg}} e inscrito no CPF sob o nº {{contratada_representante_cpf}}; e, de outro lado:

CONTRATANTE: {{contratante_nome}}, inscrito no CNPJ sob o nº {{contratante_cnpj}}, com sede na {{contratante_endereco}}, neste ato representado por seu {{contratante_cargo}}, Sr. {{contratante_representante}}, brasileiro, portador da Cédula de Identidade RG nº {{contratante_representante_rg}} e inscrito no CPF sob o nº {{contratante_representante_cpf}}, com endereço no próprio condomínio.

As partes acima qualificadas têm, entre si, justo e contratado o presente Contrato de Prestação de Serviços, que se regerá pelas cláusulas e condições seguintes, tendo como base a visita técnica de levantamento realizada em {{visita_data}} (Relatório de Visita Técnica {{visita_numero}}) e a respectiva proposta comercial.

CLÁUSULA PRIMEIRA — DO OBJETO

1.1. O presente contrato tem por objeto a prestação, pela CONTRATADA, de serviços de manutenção preventiva e corretiva dos sistemas de segurança eletrônica instalados no CONTRATANTE, compreendendo os seguintes sistemas existentes:

{{inventario_sistemas}}

1.2. Os serviços destinam-se a manter o pleno funcionamento dos sistemas existentes. A modernização, padronização ou ampliação dos equipamentos não integra este contrato e será objeto de proposta específica.

CLÁUSULA SEGUNDA — DO ESCOPO DOS SERVIÇOS

2.1. Manutenção preventiva. Executada em visitas semanais programadas ({{visitas_mes}} visitas por mês), com checklist por sistema e emissão de relatório técnico ao final de cada visita, abrangendo cancelas, controle de acesso, CFTV, cerca elétrica, interfonia e infraestrutura.

2.2. Manutenção corretiva. Atendimento a chamados de falha, ilimitado em quantidade, com a mão de obra inclusa no valor mensal. O diagnóstico é gratuito. Prazo de resposta de até {{prazo_resposta_extenso}} horas úteis; suporte remoto/telefônico via 0800 e WhatsApp no mesmo dia útil.

2.3. Exclusões. Não estão incluídos no valor mensal, sendo orçados à parte e executados somente após aprovação formal do CONTRATANTE: peças, componentes e materiais de reposição; instalação de novos equipamentos e ampliação; modernização/padronização de cancelas e equipamentos; obras civis e infraestrutura elétrica nova; link de internet; e reforma estrutural da cerca elétrica.

CLÁUSULA TERCEIRA — DO VALOR E DO PAGAMENTO

3.1. Pelos serviços descritos na Cláusula Segunda (itens 2.1 e 2.2), o CONTRATANTE pagará à CONTRATADA o valor mensal de {{valor_mensal_fmt}} ({{valor_mensal_extenso}}).

3.2. O pagamento será mensal, por PIX, boleto ou transferência, com vencimento no dia {{dia_vencimento}} ({{dia_vencimento_extenso}}) de cada mês.

3.3. O atraso no pagamento sujeitará o CONTRATANTE à multa de 2% (dois por cento), juros de mora de 1% (um por cento) ao mês e correção monetária, sem prejuízo da suspensão dos serviços após 15 (quinze) dias de inadimplência, mediante prévia comunicação.

CLÁUSULA QUARTA — DO REAJUSTE

4.1. O valor mensal será reajustado anualmente, tendo como data-base o mês de assinatura deste contrato ({{mes_base_reajuste}}), pela variação acumulada do IPCA (Índice Nacional de Preços ao Consumidor Amplo) nos 12 (doze) meses anteriores à data do reajuste, ou, na sua ausência, por índice oficial que o substitua.

CLÁUSULA QUINTA — DAS PEÇAS E MATERIAIS

5.1. Peças, componentes e materiais de reposição serão orçados separadamente e substituídos somente após aprovação formal do CONTRATANTE, ficando a CONTRATADA obrigada a apresentar orçamento prévio e a executar o serviço somente após o aceite.

CLÁUSULA SEXTA — DO PRAZO E DA VIGÊNCIA

6.1. O presente contrato vigorará pelo prazo de {{vigencia_meses_extenso}} meses, com início de vigência em {{vigencia_inicio_extenso}} e término em {{vigencia_fim_extenso}}, renovável automaticamente por igual período, salvo manifestação em contrário de qualquer das partes, por escrito, com antecedência mínima de {{renovacao_aviso_dias_extenso}} dias do termo.

CLÁUSULA SÉTIMA — DA GARANTIA

7.1. A CONTRATADA garante a mão de obra dos serviços executados pelo prazo de 90 (noventa) dias, contados da data de cada atendimento.

CLÁUSULA OITAVA — DAS OBRIGAÇÕES DO CONTRATANTE

8.1. São obrigações do CONTRATANTE: disponibilizar o acesso às áreas e aos equipamentos nas visitas programadas e corretivas; designar responsável (síndico ou zelador) para acompanhamento dos serviços e aprovação de orçamentos de peças; manter a energia e a infraestrutura básica de funcionamento dos equipamentos; aprovar previamente a substituição de peças e materiais; e efetuar os pagamentos nos prazos ajustados.

CLÁUSULA NONA — DAS OBRIGAÇÕES DA CONTRATADA

9.1. São obrigações da CONTRATADA: executar os serviços por meio de equipe técnica qualificada, com zelo e observância das normas técnicas aplicáveis; emitir relatório técnico de cada visita preventiva e de cada atendimento corretivo; manter sigilo sobre as informações e as imagens a que tiver acesso; manter sua regularidade fiscal e trabalhista, exibindo as certidões quando solicitado; e apresentar orçamento prévio para peças e materiais não inclusos.

CLÁUSULA DÉCIMA — DA PROTEÇÃO DE DADOS PESSOAIS (LGPD)

10.1. Na execução dos serviços de manutenção do sistema de CFTV, a CONTRATADA poderá ter acesso a imagens que constituem dados pessoais. Para os fins da Lei nº 13.709/2018 (LGPD), o CONTRATANTE é o CONTROLADOR desses dados e a CONTRATADA atua como OPERADORA, tratando-os exclusivamente para a finalidade de manutenção e conforme as instruções do CONTROLADOR.

10.2. A CONTRATADA obriga-se a: (i) não acessar, copiar ou divulgar imagens além do estritamente necessário à manutenção; (ii) adotar medidas de segurança adequadas; (iii) manter confidencialidade; (iv) comunicar ao CONTRATANTE, sem demora injustificada, qualquer incidente de segurança envolvendo dados pessoais; e (v) ao término do contrato, eliminar eventuais cópias de imagens em seu poder, salvo obrigação legal de guarda.

CLÁUSULA DÉCIMA PRIMEIRA — DA REVISÃO POR DIVERGÊNCIA DE INVENTÁRIO

11.1. Os quantitativos deste contrato baseiam-se no inventário registrado no Relatório de Visita Técnica {{visita_numero}}, cujas medidas de cerca elétrica e verificação canal a canal do CFTV são estimativas a confirmar. Caso a visita técnica de detalhamento revele divergência material de quantidades, o valor mensal poderá ser revisto de comum acordo entre as partes, por termo aditivo.

CLÁUSULA DÉCIMA SEGUNDA — DA RESCISÃO

12.1. O contrato poderá ser rescindido por qualquer das partes, imotivadamente, mediante aviso prévio por escrito de 30 (trinta) dias.

12.2. O descumprimento de qualquer cláusula, não sanado no prazo de 10 (dez) dias após notificação, faculta à parte prejudicada a rescisão imediata, sem prejuízo das penalidades e da cobrança dos valores devidos até a data da rescisão.

CLÁUSULA DÉCIMA TERCEIRA — DAS COMUNICAÇÕES E NOTIFICAÇÕES

13.1. As comunicações e notificações entre as partes serão consideradas válidas quando feitas por escrito aos endereços indicados no preâmbulo, ou pelos canais eletrônicos previamente informados. A CONTRATADA disponibiliza, para esse fim, o e-mail jjesus@conectamais.pro e o WhatsApp/0800 880 4414. Presumem-se recebidas as comunicações em até 2 (dois) dias úteis do envio.

CLÁUSULA DÉCIMA QUARTA — DA IDENTIFICAÇÃO DA EQUIPE TÉCNICA

14.1. A CONTRATADA executará os serviços por meio de técnicos identificados e uniformizados, comprometendo-se a informar previamente ao CONTRATANTE a relação dos profissionais que acessarão as dependências do condomínio, para fins de controle de acesso e segurança, respondendo por sua conduta durante os atendimentos.

CLÁUSULA DÉCIMA QUINTA — DAS DISPOSIÇÕES GERAIS

15.1. Este contrato não gera vínculo empregatício entre a CONTRATADA (ou seus prepostos) e o CONTRATANTE. Alterações somente terão validade se formalizadas por termo aditivo escrito e assinado. A tolerância quanto ao descumprimento de qualquer cláusula não implica novação ou renúncia.

CLÁUSULA DÉCIMA SEXTA — DO FORO

16.1. As partes elegem o foro da Comarca de Manaus/AM para dirimir quaisquer questões oriundas deste contrato, com renúncia a qualquer outro, por mais privilegiado que seja.

Por terem lido e concordado com todas as cláusulas e condições ora estabelecidas, as partes firmam o presente instrumento por assinatura eletrônica, na forma do art. 10, § 2º, da MP nº 2.200-2/2001, dispensada a assinatura de testemunhas nos termos do art. 784, § 4º, do Código de Processo Civil, uma vez que a integridade deste documento é conferida pelo provedor de assinatura, conforme manifesto ao final.

Manaus/AM, {{data_assinatura_extenso}}.

[[BLOCO_ASSINATURAS]]
"""

CLAUSULAS = [
    "CLÁUSULA PRIMEIRA — DO OBJETO",
    "CLÁUSULA SEGUNDA — DO ESCOPO DOS SERVIÇOS",
    "CLÁUSULA TERCEIRA — DO VALOR E DO PAGAMENTO",
    "CLÁUSULA QUARTA — DO REAJUSTE",
    "CLÁUSULA QUINTA — DAS PEÇAS E MATERIAIS",
    "CLÁUSULA SEXTA — DO PRAZO E DA VIGÊNCIA",
    "CLÁUSULA SÉTIMA — DA GARANTIA",
    "CLÁUSULA OITAVA — DAS OBRIGAÇÕES DO CONTRATANTE",
    "CLÁUSULA NONA — DAS OBRIGAÇÕES DA CONTRATADA",
    "CLÁUSULA DÉCIMA — DA PROTEÇÃO DE DADOS PESSOAIS (LGPD)",
    "CLÁUSULA DÉCIMA PRIMEIRA — DA REVISÃO POR DIVERGÊNCIA DE INVENTÁRIO",
    "CLÁUSULA DÉCIMA SEGUNDA — DA RESCISÃO",
    "CLÁUSULA DÉCIMA TERCEIRA — DAS COMUNICAÇÕES E NOTIFICAÇÕES",
    "CLÁUSULA DÉCIMA QUARTA — DA IDENTIFICAÇÃO DA EQUIPE TÉCNICA",
    "CLÁUSULA DÉCIMA QUINTA — DAS DISPOSIÇÕES GERAIS",
    "CLÁUSULA DÉCIMA SEXTA — DO FORO",
]

TPL_ID = "8f2c1a44-3d5e-4b90-9c71-6ea2d0f45b18"


async def main() -> None:
    async with async_session_factory() as db:
        ja = (await db.execute(text(
            "SELECT id::text FROM contract_templates WHERE id::text = :i"), {"i": TPL_ID})).scalar()
        if ja:
            await db.execute(text(
                "UPDATE contract_templates SET content_template=:c, clauses=CAST(:k AS jsonb), "
                "updated_at=now() WHERE id::text=:i"),
                {"c": TEMPLATE, "k": json.dumps(CLAUSULAS), "i": TPL_ID})
            print(f"  modelo ATUALIZADO ({len(TEMPLATE)} chars, {len(CLAUSULAS)} cláusulas)")
        else:
            await db.execute(text("""
                INSERT INTO contract_templates
                    (id, name, description, service_type, content_template, clauses,
                     version, is_active, created_at, updated_at)
                VALUES (CAST(:i AS uuid), :n, :d, :s, :c, CAST(:k AS jsonb),
                        1, true, now(), now())"""),
                {"i": TPL_ID,
                 "n": "Manutenção de Segurança Eletrônica (padrão)",
                 "d": "Manutenção preventiva e corretiva de CFTV, cancelas, controle de "
                      "acesso, cerca elétrica e interfonia. Emitido pela Conecta Mais "
                      "Eletrônica.",
                 "s": "manutencao_cftv",
                 "c": TEMPLATE, "k": json.dumps(CLAUSULAS)})
            print(f"  modelo CRIADO ({len(TEMPLATE)} chars, {len(CLAUSULAS)} cláusulas)")
        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
