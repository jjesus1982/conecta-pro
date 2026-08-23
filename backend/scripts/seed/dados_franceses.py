"""Dados do contrato de manutenção — Parque dos Franceses (Conecta Mais Eletrônica).

Tudo o que o instrumento afirma passa a ter casa no banco, para o render buscar em vez de
o texto carregar constante:
  · inventário dos sistemas  -> contract_items (um por sistema)
  · visita técnica e SLA     -> contracts.sla_config
  · proposta que originou    -> contracts.proposal_id (PROP-20260610-98EF41, R$ 1.800)
  · RG do síndico            -> crm_contacts.notes ("CPF ... · RG ...")

O relatório de visita RV-2026-00001 NÃO existe em crm_visit_reports — a referência foi
gravada como o Jordan a informou, e o gap está no relatório final. Não criei um registro
de visita falso só para o número fechar.
"""
import asyncio
import json

from sqlalchemy import text

from core.database import async_session_factory

CLIENTE = "bd351381-70c6-4499-b91d-acf0188dfa3f"
PROPOSTA = "31215a74-48a9-4d28-af07-c808c107449e"
TPL = "8f2c1a44-3d5e-4b90-9c71-6ea2d0f45b18"
ELETRONICA = "619a3df1-8bce-49ce-b77a-04f80a0e8491"
NUM = "CTR-2026-00020"

SISTEMAS = [
    ("Automação veicular",
     "4 (quatro) cancelas de fabricantes distintos (BRASSO, GAREN, PPA e não identificada)"),
    ("Controle de acesso",
     "antena de TAG veicular, teclado Control iD, módulo/leitor Citrox e interfonia"),
    ("CFTV", "aproximadamente 32 (trinta e duas) câmeras em DVRs Intelbras"),
    ("Cerca elétrica",
     "perímetro aproximado de 700 m, com 2 (duas) centrais Intelbras FA 1220S"),
    ("Interfonia e apoio",
     "porteiros eletrônicos Intelbras IPR 8010, totens de visitante e infraestrutura de "
     "rack/energia"),
]

SLA = {
    "visita_numero": "RV-2026-00001",
    "visita_data": "02/06/2026",
    "visitas_mes": 4,
    "prazo_resposta_horas": 24,
}


async def main() -> None:
    async with async_session_factory() as db:
        # 1 · endereço do condomínio (estava só com a cidade)
        await db.execute(text("""
            UPDATE clients SET address_street='Rua Parque dos Franceses', address_number='305',
                   address_city='Manaus', address_state='AM', updated_at=now()
            WHERE id::text = :c"""), {"c": CLIENTE})

        # 2 · o síndico — é quem assina pelo condomínio
        ja = (await db.execute(text(
            "SELECT id::text FROM crm_contacts WHERE client_id::text = :c "
            "AND name ILIKE '%israel%'"), {"c": CLIENTE})).scalar()
        notas = "CPF 531.109.432-04 · RG 17126045 SSP/AM"
        if ja:
            await db.execute(text(
                "UPDATE crm_contacts SET role='Síndico', notes=:n, is_primary=true, "
                "updated_at=now() WHERE id::text=:i"), {"n": notas, "i": ja})
            print("  síndico ATUALIZADO")
        else:
            await db.execute(text("""
                INSERT INTO crm_contacts (id, client_id, name, role, notes, is_primary,
                                          created_at, updated_at)
                VALUES (gen_random_uuid(), CAST(:c AS uuid), :n, 'Síndico', :o, true,
                        now(), now())"""),
                {"c": CLIENTE, "n": "Israel Rick Stone de Souza", "o": notas})
            print("  síndico CADASTRADO")

        # 3 · o contrato
        existe = (await db.execute(text(
            "SELECT id::text FROM contracts WHERE contract_number = :n"), {"n": NUM})).scalar()
        if existe:
            await db.execute(text("""
                UPDATE contracts SET template_id=CAST(:t AS uuid), empresa_id=CAST(:e AS uuid),
                       tipo_servico='manutencao_cftv', monthly_value=1800, payment_day=10,
                       start_date=DATE '2026-08-05', end_date=DATE '2027-08-04',
                       renewal_notification_days=30, notice_period_days=30,
                       sla_config=CAST(:s AS jsonb), proposal_id=CAST(:p AS uuid),
                       is_active=true, updated_at=now()
                WHERE contract_number = :n"""),
                {"t": TPL, "e": ELETRONICA, "s": json.dumps(SLA), "p": PROPOSTA, "n": NUM})
            cid = existe
            print(f"  contrato {NUM} ATUALIZADO")
        else:
            cid = (await db.execute(text("""
                INSERT INTO contracts
                    (id, contract_number, client_id, template_id, empresa_id, tipo_servico,
                     contract_type, status, name, description, monthly_value, payment_day,
                     start_date, end_date, renewal_notification_days, notice_period_days,
                     sla_config, proposal_id, is_active, created_at, updated_at)
                VALUES (gen_random_uuid(), :n, CAST(:c AS uuid), CAST(:t AS uuid),
                        CAST(:e AS uuid), 'manutencao_cftv', 'recurring', 'draft',
                        :nome, :desc, 1800, 10,
                        DATE '2026-08-05', DATE '2027-08-04', 30, 30,
                        CAST(:s AS jsonb), CAST(:p AS uuid), true, now(), now())
                RETURNING id::text"""),
                {"n": NUM, "c": CLIENTE, "t": TPL, "e": ELETRONICA,
                 "nome": "Manutenção de Segurança Eletrônica — Parque dos Franceses",
                 "desc": "Manutenção preventiva (4 visitas/mês) e corretiva ilimitada dos "
                         "sistemas de segurança eletrônica. Origem: PROP-20260610-98EF41.",
                 "s": json.dumps(SLA), "p": PROPOSTA})).scalar()
            print(f"  contrato {NUM} CRIADO")

        # 4 · inventário — um item por sistema
        await db.execute(text(
            "DELETE FROM contract_items WHERE contract_id::text = :c"), {"c": cid})
        for nome, desc in SISTEMAS:
            await db.execute(text("""
                INSERT INTO contract_items (id, contract_id, service_type, service_name,
                                            description, quantity, unit_price, total_price,
                                            is_active, created_at, updated_at)
                VALUES (gen_random_uuid(), CAST(:c AS uuid), 'manutencao_cftv', :n, :d,
                        1, 0, 0, true, now(), now())"""), {"c": cid, "n": nome, "d": desc})
        print(f"  inventário: {len(SISTEMAS)} sistemas em contract_items")
        await db.commit()

        soma = (await db.execute(text(
            "SELECT monthly_value, payment_day, start_date, end_date, sla_config "
            "FROM contracts WHERE contract_number=:n"), {"n": NUM})).mappings().first()
        print("  conferência:", dict(soma))


if __name__ == "__main__":
    asyncio.run(main())
