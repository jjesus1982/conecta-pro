"""Cria o MODELO de contrato de SEGURANÇA ELETRÔNICA EM SERVIÇO ÚNICO (Conecta Mais Eletrônica).

Texto-base: `Contrato_Chacaras_Maiapolis_Controle_de_Acesso_FINAL` (revisão Furtado Maia
Advocacia), entregue pelo Jordan em 09/09/2026. Nada do texto jurídico foi reescrito — os
dados das partes viraram variáveis para o modelo servir a outros clientes.

Cobre controle de acesso, CFTV, automação de portões, cerca elétrica e interfonia, na
modalidade FORNECIMENTO + INSTALAÇÃO + CONFIGURAÇÃO, valor ÚNICO (não recorrente).

⚠️ SEIS CLÁUSULAS SÃO BLINDAGEM JURÍDICA e não podem ser genericizadas — o oráculo
`test_oraculo_contrato_eletronica_unico.py` afirma cada uma pela string:

    2.2  exclui "dificuldades comerciais de fornecimento" do rol de força maior
    2.3  multa moratória da CONTRATADA por atraso, com teto
    3.2  parcela final RETIDA até o Termo de Entrega sem ressalvas
    7.2  prazo de homologação para apontar defeitos por escrito
    9.3  vedada conversão automática da cortesia em contrato oneroso
    11.2 responsabilidade integral e REGRESSIVA por vazamento de biometria

ÚNICA alteração de redação em relação ao documento de origem: sai "2 (duas) vias de igual
teor" e saem as linhas manuscritas de testemunha; entra o fecho por assinatura eletrônica
(MP 2.200-2 art. 10 §2º) **com as duas testemunhas assinando eletronicamente na mesma
plataforma** — decisão do Jordan em 09/09/2026.

⚠️ Este modelo é o único da casa COM testemunha. Manutenção e portaria seguem sem, apoiados
na dispensa do art. 784 §4º do CPC. Aqui as testemunhas não são dispensadas: elas assinam.
Por isso o fecho NÃO invoca a dispensa — invocá-la e ao mesmo tempo colher a assinatura
seria o documento contradizendo a si mesmo. O `[[BLOCO_ASSINATURAS]]` desenha os quadros de
testemunha somente quando o contexto pede (`testemunhas=True`), então os outros dois modelos
seguem intactos.

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/seed/modelo_eletronica_unico.py
"""
import asyncio
import json

from sqlalchemy import text

from core.database import async_session_factory

TEMPLATE = """CONTRATO DE PRESTAÇÃO DE SERVIÇOS DE FORNECIMENTO, INSTALAÇÃO E CONFIGURAÇÃO DE SISTEMA DE SEGURANÇA ELETRÔNICA / CONTROLE DE ACESSO

Pelo presente instrumento particular de prestação de serviços, de um lado:

CONTRATADA: {{contratada_razao_social}}, inscrita no CNPJ sob o nº {{contratada_cnpj}}, com sede em {{contratada_endereco}}, neste ato representada por seu {{contratada_cargo}}, Sr. {{contratada_representante}}, inscrito no CPF sob o nº {{contratada_representante_cpf}}; e, de outro lado:

CONTRATANTE: {{contratante_nome}}, inscrita no CNPJ sob o nº {{contratante_cnpj}}, com sede na {{contratante_endereco}}, neste ato representada por sua {{contratante_cargo}}, {{contratante_representante}}, inscrita no CPF sob o nº {{contratante_representante_cpf}};

têm entre si justo e contratado o presente Contrato de Prestação de Serviços, de caráter ÚNICO (não recorrente), regido pelas cláusulas a seguir, tendo como base a proposta comercial {{proposta_numero}} aceita pela CONTRATANTE, que integra este instrumento.

CLÁUSULA PRIMEIRA — DO OBJETO

1.1. Constitui objeto deste contrato a prestação, pela CONTRATADA, em caráter de serviço único, do fornecimento, instalação, configuração, integração, cadastramento inicial e treinamento operacional do sistema integrado de controle de acesso descrito na proposta {{proposta_numero}}, compreendendo, em resumo: {{objeto_resumo}}; e a disponibilização do Conecta Plus, plataforma de gestão condominial e de controle de acessos.

1.2. A descrição detalhada dos equipamentos, quantidades e especificações consta da proposta comercial aceita, parte integrante deste contrato. Ajustes pontuais de posicionamento poderão ser definidos, de comum acordo, na execução, sem alteração do valor.

CLÁUSULA SEGUNDA — DO PRAZO DE EXECUÇÃO

2.1. Os serviços serão executados no prazo de até {{prazo_exec_dias}} ({{prazo_exec_dias_extenso}}) dias úteis, contados da assinatura deste contrato e do pagamento da entrada.

2.2. O prazo será prorrogado, sem ônus para nenhuma das partes, exclusivamente por atrasos decorrentes de força maior ou caso fortuito devidamente comprovados, ou por pendências de responsabilidade exclusiva da CONTRATANTE, excluindo-se deste rol dificuldades comerciais de fornecimento da CONTRATADA.

2.3. O atraso injustificado da CONTRATADA na entrega técnica para além do prazo de {{prazo_exec_dias}} dias úteis sujeitará a empresa à multa moratória de {{multa_atraso_dia}}% ao dia, calculada sobre o valor total do contrato, limitada ao teto de {{multa_teto_pct}}%.

CLÁUSULA TERCEIRA — DO VALOR E DA FORMA DE PAGAMENTO

3.1. Pelo objeto deste contrato, a CONTRATANTE pagará à CONTRATADA o valor total de {{valor_total_fmt}} ({{valor_total_extenso}}).

3.2. O pagamento observará: entrada de {{entrada_fmt}} ({{entrada_pct}}%) na assinatura; {{parcelas_descricao}}; e a parcela final de {{parcela_retida_fmt}} retida, a ser paga no prazo de até 5 dias úteis contados da efetiva assinatura sem ressalvas do Termo de Entrega previsto na Cláusula Sétima.

3.3. Os pagamentos serão feitos por PIX, boleto ou transferência. O atraso de qualquer parcela sujeitará a CONTRATANTE à multa de 2% (dois por cento), juros de mora de 1% (um por cento) ao mês e correção monetária.

[[TABELA_COMPOSICAO]]

CLÁUSULA QUARTA — DA PLATAFORMA CONECTA PLUS

4.1. O Conecta Plus, plataforma de gestão condominial e de controle de acessos, é disponibilizado à CONTRATANTE mediante mensalidade de {{conecta_plus_fmt}} ({{conecta_plus_extenso}}), a qual passa a ser faturada a partir de 30 (trinta) dias após a assinatura do Termo de Entrega do serviço.

4.2. A mensalidade do Conecta Plus poderá ser reajustada anualmente pela variação do IPCA. A CONTRATANTE poderá, a qualquer tempo, mediante aviso de 30 (trinta) dias, encerrar a assinatura mensal do Conecta Plus, sem multa, preservados os demais termos deste contrato.

CLÁUSULA QUINTA — DAS OBRIGAÇÕES DA CONTRATADA

5.1. Fornecer, instalar e configurar os equipamentos conforme a proposta; empregar equipe técnica própria e qualificada; entregar o sistema em pleno funcionamento; realizar o cadastramento inicial e o treinamento operacional da equipe da CONTRATANTE; prestar suporte durante a garantia e a manutenção cortesia; e observar as normas técnicas aplicáveis.

CLÁUSULA SEXTA — DAS OBRIGAÇÕES DA CONTRATANTE

6.1. Disponibilizar o acesso e a infraestrutura básica (energia, pontos, local e link de internet) necessários à instalação e ao funcionamento; designar responsável para acompanhamento e recebimento; efetuar os pagamentos nos prazos ajustados; e zelar pela adequada utilização dos equipamentos.

CLÁUSULA SÉTIMA — DA ENTREGA TÉCNICA E DO TERMO DE ENTREGA

7.1. Concluída a instalação e a configuração, a CONTRATADA realizará a entrega técnica, com testes de funcionamento, formalizada pela assinatura de um Termo de Entrega do serviço.

7.2. A CONTRATANTE terá até {{homologacao_dias}} ({{homologacao_dias_extenso}}) dias úteis, contados da entrega técnica e do treinamento operacional, para apontar por escrito eventuais defeitos, incompatibilidades ou pendências, período no qual o sistema operará em fase de homologação.

7.3. A assinatura (ou o aceite tácito) do Termo de Entrega marca o início da garantia dos serviços, da manutenção cortesia e do início do faturamento do Conecta Plus.

CLÁUSULA OITAVA — DA GARANTIA

8.1. Os equipamentos fornecidos têm garantia conforme os prazos do fabricante. Os serviços de instalação e configuração têm garantia de {{garantia_meses}} ({{garantia_meses_extenso}}) meses, contados da assinatura do Termo de Entrega.

8.2. A garantia cobre defeitos de fabricação e de execução, excluídos os danos decorrentes de mau uso, intervenção de terceiros, vandalismo, surtos elétricos, descargas atmosféricas e caso fortuito ou força maior.

CLÁUSULA NONA — DA MANUTENÇÃO EM CORTESIA

9.1. Como cortesia, a CONTRATADA prestará, pelo prazo de {{cortesia_meses}} ({{cortesia_meses_extenso}}) meses contados da assinatura do Termo de Entrega, a manutenção preventiva e corretiva do sistema de CFTV e dos demais itens de segurança eletrônica objeto deste contrato, com a mão de obra inclusa.

9.2. Peças e componentes de reposição não estão inclusos na cortesia e, quando necessários, serão orçados à parte e substituídos somente após aprovação da CONTRATANTE. Encerrado o período de cortesia, a manutenção poderá ser contratada em instrumento próprio.

9.3. Encerrado o período de cortesia de {{cortesia_meses}} ({{cortesia_meses_extenso}}) meses, a manutenção preventiva e corretiva cessará de pleno direito. Caso a CONTRATANTE opte por contratar a manutenção mensalizada, as partes deverão formalizar instrumento contratual autônomo ou aditivo específico, sendo vedada qualquer conversão automática em contrato oneroso.

CLÁUSULA DÉCIMA — DA PROPRIEDADE E DA LICENÇA DE SOFTWARE

10.1. Os softwares e a plataforma Conecta Plus são de propriedade da CONTRATADA, licenciados à CONTRATANTE apenas para uso conforme sua finalidade, vedada a cópia, redistribuição, sublicenciamento ou modificação.

CLÁUSULA DÉCIMA PRIMEIRA — DA PROTEÇÃO DE DADOS (LGPD)

11.1. O sistema envolve o tratamento de dados pessoais, inclusive biometria facial (dado sensível, art. 11 da Lei nº 13.709/2018). A CONTRATANTE é a CONTROLADORA e a CONTRATADA atua como OPERADORA, tratando os dados exclusivamente para a finalidade contratada e conforme as instruções da CONTROLADORA, com medidas de segurança adequadas, confidencialidade, comunicação de incidentes sem demora injustificada e eliminação ao término do contrato, salvo obrigação legal de guarda.

11.2. A CONTRATADA responderá integral e regressivamente perante a CONTRATANTE por eventuais multas, condenações judiciais ou indenizações de terceiros decorrentes de incidentes de segurança da informação (como vazamento de dados biométricos) cuja origem decorra de falha ou vulnerabilidade de segurança da própria plataforma Conecta Plus.

CLÁUSULA DÉCIMA SEGUNDA — DA RESCISÃO

12.1. Qualquer das partes poderá rescindir este contrato em caso de descumprimento de cláusula pela outra, não sanado no prazo de 10 (dez) dias após notificação por escrito, sem prejuízo da exigência dos valores devidos até então.

12.2. Caso a CONTRATANTE desista do serviço após a assinatura, mas antes da conclusão, ressarcirá à CONTRATADA os valores e as despesas comprovadamente já incorridos (equipamentos adquiridos e serviços executados) até a data da desistência, devolvendo-se eventual saldo pago a maior.

CLÁUSULA DÉCIMA TERCEIRA — DAS DISPOSIÇÕES GERAIS

13.1. Este contrato não gera vínculo empregatício entre as partes. Alterações somente terão validade se formalizadas por termo aditivo escrito. A tolerância quanto ao descumprimento de qualquer cláusula não implica novação ou renúncia.

CLÁUSULA DÉCIMA QUARTA — DO FORO

14.1. As partes elegem o foro da Comarca de {{foro}} para dirimir quaisquer questões oriundas deste contrato, com renúncia a qualquer outro, por mais privilegiado que seja.

Por terem lido e concordado com todas as cláusulas e condições ora estabelecidas, as partes firmam o presente instrumento por assinatura eletrônica, na forma do art. 10, § 2º, da MP nº 2.200-2/2001, juntamente com 2 (duas) testemunhas, que igualmente o assinam por meio eletrônico na mesma plataforma, tendo a integridade deste documento conferida pelo provedor de assinatura, conforme manifesto ao final, que registra, para cada signatário, autoria, data e hora.

{{cidade_assinatura}}, {{data_assinatura_extenso}}.

[[BLOCO_ASSINATURAS]]
"""

CLAUSULAS = [
    "CLÁUSULA PRIMEIRA — DO OBJETO",
    "CLÁUSULA SEGUNDA — DO PRAZO DE EXECUÇÃO",
    "CLÁUSULA TERCEIRA — DO VALOR E DA FORMA DE PAGAMENTO",
    "CLÁUSULA QUARTA — DA PLATAFORMA CONECTA PLUS",
    "CLÁUSULA QUINTA — DAS OBRIGAÇÕES DA CONTRATADA",
    "CLÁUSULA SEXTA — DAS OBRIGAÇÕES DA CONTRATANTE",
    "CLÁUSULA SÉTIMA — DA ENTREGA TÉCNICA E DO TERMO DE ENTREGA",
    "CLÁUSULA OITAVA — DA GARANTIA",
    "CLÁUSULA NONA — DA MANUTENÇÃO EM CORTESIA",
    "CLÁUSULA DÉCIMA — DA PROPRIEDADE E DA LICENÇA DE SOFTWARE",
    "CLÁUSULA DÉCIMA PRIMEIRA — DA PROTEÇÃO DE DADOS (LGPD)",
    "CLÁUSULA DÉCIMA SEGUNDA — DA RESCISÃO",
    "CLÁUSULA DÉCIMA TERCEIRA — DAS DISPOSIÇÕES GERAIS",
    "CLÁUSULA DÉCIMA QUARTA — DO FORO",
]

# Defaults do modelo. Sobrescritíveis por contrato em `contracts.emissao_config`.
# Ficam no MODELO (não no código do render) porque são cláusula, não regra de sistema:
# mudar o teto da multa é decisão jurídica e tem de ser versionada junto com o texto.
VARIAVEIS = {
    "prazo_exec_dias": 60,
    "multa_atraso_dia": "0,5",
    "multa_teto_pct": 10,
    "homologacao_dias": 10,
    "garantia_meses": 6,
    "cortesia_meses": 6,
    "conecta_plus_valor": 400,
    "foro": "Manaus/AM",
    "cidade_assinatura": "Manaus/AM",
    # ⚠️ anda junto com o fecho do TEMPLATE acima. Ligar aqui sem trocar o texto (ou o
    # contrário) faz o instrumento contradizer a si mesmo — ver `_bloco_assinaturas`.
    "testemunhas": True,
}

TPL_ID = "b7e4c9a2-1f68-4d35-8a90-2c5be7104fd3"
SERVICE_TYPE = "eletronica_servico_unico"
NOME = "Segurança Eletrônica — Serviço Único (Controle de Acesso / CFTV)"
DESCRICAO = (
    "Fornecimento, instalação e configuração de sistema de segurança eletrônica em valor "
    "ÚNICO (não recorrente): controle de acesso, CFTV, automação de portões, cerca elétrica "
    "e interfonia. Emitido pela Conecta Mais Eletrônica. Base: revisão Furtado Maia."
)


async def main() -> None:
    async with async_session_factory() as db:
        # upsert por SERVICE_TYPE, não só por id: se alguém já tiver criado o tipo por outro
        # caminho, atualizar é o certo — dois modelos com o mesmo service_type fariam o
        # `modelos_disponiveis` oferecer duas linhas idênticas e indistinguíveis na tela.
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
            print(f"  modelo ATUALIZADO ({len(TEMPLATE)} chars, {len(CLAUSULAS)} cláusulas) id={ja}")
        else:
            await db.execute(text("""
                INSERT INTO contract_templates
                    (id, name, description, service_type, content_template, clauses, variables,
                     version, is_active, created_at, updated_at)
                VALUES (CAST(:i AS uuid), :n, :d, :s, :c, CAST(:k AS jsonb), CAST(:v AS jsonb),
                        1, true, now(), now())"""), {**params, "i": TPL_ID})
            print(f"  modelo CRIADO ({len(TEMPLATE)} chars, {len(CLAUSULAS)} cláusulas) id={TPL_ID}")
        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
