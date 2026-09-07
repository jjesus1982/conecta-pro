"""
HERMES — Agente Documental do GEDEON
"Nenhum documento se perde, nenhum é duplicado"

Responsabilidades:
- Classificação automática de documentos uploadados
- Detecção de duplicatas por hash SHA-256
- Cache de documentos reutilizáveis entre meses
- Validação de autenticidade (chave de acesso NFS-e)
- Matching onvio_documents → colaborador → condomínio → kit (CPRO12 T4)
"""

import hashlib
import logging
import re
import unicodedata

logger = logging.getLogger(__name__)

# Tipos de documento reconhecidos automaticamente
TIPOS_DOCUMENTO = {
    # Folha de pagamento
    r"holerite|contracheque|recibo.*salario": "holerite",
    r"folha.*pagamento|payroll": "folha_pagamento",
    r"espelho.*ponto|ponto.*espelho|timesheet": "espelho_ponto",
    # Admissão/Demissão
    r"admiss[aã]o|contrato.*trabalho": "contrato_admissao",
    r"demiss[aã]o|rescis[aã]o|trct": "rescisao",
    r"seguro.*desemprego": "seguro_desemprego",
    # Saúde
    r"aso|atestado.*saude.*ocupacional": "aso",
    r"atestado.*medico|medical.*certificate": "atestado_medico",
    r"epi|equipamento.*protecao": "ficha_epi",
    # Certidões
    # Ordem importa: o genérico "cnd" ficava ANTES dos específicos e "CND-FGTS-05-09-2026.pdf"
    # virava cnd_federal (medido 07/09/2026). Específicos primeiro, federal por último.
    r"crf.*fgts|regularidade.*fgts|cnd.*fgts|fgts.*(cnd|crf|certid)": "crf_fgts",
    r"cndt|certidao.*trabalhista|cnd.*trabalhista|debitos.*trabalhistas|tst": "certidao_trabalhista",
    r"cnd.*municipal|certidao.*municipal|prefeitura|cnd.*manaus": "cnd_municipal",
    r"cnd.*estadual|certidao.*estadual|sefaz": "cnd_estadual",
    r"cnd.*(inss|previdenc)|certidao.*previdenc": "cnd_inss",
    r"falenc|recuperacao.*judicial|concordata": "certidao_falencia",
    r"cnd|certidao.*negativa.*debito|receita.*federal|rfb|pgfn": "cnd_federal",
    r"alvara.*funcionamento": "alvara_funcionamento",
    # Fiscal
    r"nota.*fiscal|nfs?-?e|nfse": "nota_fiscal",
    r"boleto|cobranca": "boleto",
    # Treinamentos
    r"nr-?\d+|treinamento|certificado.*curso": "certificado_nr",
}

# Categorias por tipo
_CATEGORIAS: dict[str, str] = {
    "holerite": "folha_pagamento",
    "folha_pagamento": "folha_pagamento",
    "espelho_ponto": "folha_pagamento",
    "contrato_admissao": "admissao",
    "rescisao": "demissao",
    "seguro_desemprego": "demissao",
    "aso": "saude",
    "atestado_medico": "saude",
    "ficha_epi": "saude",
    "cnd_federal": "certidoes",
    "crf_fgts": "certidoes",
    "certidao_trabalhista": "certidoes",
    "cnd_municipal": "certidoes",
    "cnd_estadual": "certidoes",
    "cnd_inss": "certidoes",
    "certidao_falencia": "certidoes",
    "alvara_funcionamento": "certidoes",
    "nota_fiscal": "fiscal",
    "boleto": "fiscal",
    "certificado_nr": "treinamento",
}

# Tipos reutilizáveis entre meses
_REUTILIZAVEIS: dict[str, bool] = {
    "cnd_federal": True,
    "crf_fgts": False,  # validade mensal
    "cnd_municipal": True,
    "cnd_estadual": True,
    "cnd_inss": True,
    "certidao_falencia": True,
    "certidao_trabalhista": True,
    "alvara_funcionamento": True,
    "holerite": False,
    "espelho_ponto": False,
    "aso": True,  # validade anual
    "ficha_epi": False,
    "nota_fiscal": False,
    "boleto": False,
}

# Mapa Onvio categoria → ged_kit_documents document_type — docs de empresa/condomínio
MAPA_TIPOS_ONVIO_EMPRESA: dict[str, str] = {
    "folha_pagamento": "folha_pagamento",
    # recibo_folha com doc_scope='condominio' → contracheque (per-kit, não per-employee)
    "recibo_folha": "contracheque",
    "dctfweb_recibo": "dctfweb_recibo",
    "dctfweb_extrato": "dctfweb_extrato",
    "dctfweb_declaracao": "dctfweb_declaracao",
    # dctfweb sub-tipos mapeados para o slot canônico dctfweb_extrato (§119)
    "dctfweb_creditos": "dctfweb_extrato",
    "dctfweb_debitos": "dctfweb_extrato",
    "dctfweb_resumo_creditos": "dctfweb_extrato",
    "dctfweb_resumo_debitos": "dctfweb_extrato",
    "fgts_guia": "gfd_fgts_mensal",
    "fgts_relatorio": "relatorio_gfd_fgts",
    "fgts_consignado": "comp_pag_fgts",
    "fgts_consignado_relatorio": "relatorio_gfd_fgts",
    "das_simples_nacional": "das_simples_nacional",
    "parcelamento_simples": "parcelamento_simples",
    "guia_issqn": "guia_issqn",
    "decimo_terceiro": "decimo_terceiro",
    "empresa_docs": "outro",
    "inss_guia": "gps_inss",
    "dar_sefaz": "dar_sefaz",
    "nfse": "nfse",
    "nfe_danfe": "outro",
    "processo_judicial": "outro",
}

# Mapa Onvio categoria → ged_kit_documents document_type — docs per-funcionário
MAPA_TIPOS_ONVIO_FUNCIONARIO: dict[str, str] = {
    "recibo_folha": "contracheque",
    "ficha_registro": "ficha_empregado",
    "contrato_trabalho": "contrato_trabalho",
    "atestado": "aso",
    "folha_ponto": "folha_ponto",
    "escala_mes": "escala_mes",
    # categorias que o classificador do Onvio passou a reconhecer em 07/09/2026
    "comunicacao_transferencia": "comunicacao_transferencia",
    "termo_salario_familia": "termo_salario_familia",
    "advertencia": "advertencia",
}

# Categorias de comprovante de pagamento que devem ser buscadas no Banco Inter
TIPOS_INTER: set[str] = {
    "comp_salario_individual",
    "comprovante_va",
    "comprovante_vt",
    "comp_pag_fgts",
    "comp_vt_individual",
    "comp_va_solides",
}

# Stop words ignoradas no matching de nomes (espelho de kit_builder_service)
_STOP_WORDS_MATCH = {
    "CONDOMINIO",
    "CONDOMINIUM",
    "RESIDENCIAL",
    "EDIFICIO",
    "PREDIAL",
    "VILLAGE",
    "DO",
    "DA",
    "DE",
    "DOS",
    "DAS",
    "E",
    "O",
    "A",
    "EM",
}


class Hermes:
    """
    Agente Documental — classificação e gestão inteligente
    de documentos do GEDEON.
    """

    def classificar_documento(
        self,
        nome_arquivo: str,
        conteudo_preview: str = "",
    ) -> dict:
        """
        Classificar documento automaticamente.
        Retorna tipo, categoria e metadados detectados.
        """
        # Sem acento: "Certidão Negativa de Débitos Trabalhistas.pdf" caía em "outros" (07/09/2026).
        import unicodedata as _ud
        texto = _ud.normalize("NFKD", nome_arquivo + " " + conteudo_preview).encode("ascii", "ignore").decode().lower()
        texto = re.sub(r"[_\-.]", " ", texto)

        for pattern, tipo in TIPOS_DOCUMENTO.items():
            if re.search(pattern, texto, re.IGNORECASE):
                return {
                    "tipo": tipo,
                    "categoria": _CATEGORIAS.get(tipo, "outros"),
                    "confianca": "alta",
                    "auto": True,
                }

        return {
            "tipo": "outros",
            "categoria": "outros",
            "confianca": "baixa",
            "auto": False,
        }

    def detectar_duplicata(
        self,
        arquivo_hash: str,
        documentos_existentes: list[dict],
    ) -> dict | None:
        """Detectar se documento já existe pelo hash."""
        for doc in documentos_existentes:
            if doc.get("hash") == arquivo_hash:
                return doc
        return None

    def calcular_hash(self, conteudo: bytes) -> str:
        """Calcular hash SHA-256 do documento."""
        return hashlib.sha256(conteudo).hexdigest()

    def pode_reutilizar(
        self,
        tipo: str,
        competencia_anterior: str,
        competencia_atual: str,
    ) -> bool:
        """
        Verificar se documento pode ser reutilizado do mês anterior.
        Certidões de longa validade: podem reutilizar.
        Holerites e espelhos de ponto: sempre novo.
        """
        return _REUTILIZAVEIS.get(tipo, False)

    async def processar_upload(
        self,
        nome_arquivo: str,
        conteudo: bytes,
        cliente_id: str,
        competencia: str,
        funcionario_id: str | None = None,
    ) -> dict:
        """
        Processar upload completo:
        1. Classificar automaticamente
        2. Calcular hash (detecção de duplicata)
        3. Retornar metadados para salvar
        """
        classificacao = self.classificar_documento(nome_arquivo)
        arquivo_hash = self.calcular_hash(conteudo)

        resultado = {
            "nome_original": nome_arquivo,
            "tipo": classificacao["tipo"],
            "categoria": classificacao["categoria"],
            "auto_classificado": classificacao["auto"],
            "hash": arquivo_hash,
            "cliente_id": cliente_id,
            "competencia": competencia,
            "funcionario_id": funcionario_id,
            "tamanho_bytes": len(conteudo),
        }

        logger.info(
            "HERMES: documento classificado — %s → %s [%s]",
            nome_arquivo,
            classificacao["tipo"],
            "auto" if classificacao["auto"] else "manual",
        )
        return resultado

    # ── Matching: onvio_documents → colaborador → condomínio → kit ──────────

    def _extrair_nome_do_arquivo(self, nome_arquivo: str) -> str | None:
        """Extrai nome do colaborador do nome_arquivo.

        Exemplos:
          'Ficha Registro de Empregado_Daniel Larroque.pdf' → 'Daniel Larroque'
          'Atestado médico - Antônio Walcicley 17-03-2026.pdf' → None (sem padrão _)
        """
        # Onvio nomeia "Recibo de Pagamento-08-2026-1-ALEXANDRESOUZADASILVA.pdf": o nome é o
        # ÚLTIMO segmento, por hífen ou sublinhado, sem espaços (07/09/2026).
        match = re.search(r"[-_ ]([A-Za-zÀ-ÿ][^-_/\\]*?)\.\w+$", nome_arquivo)
        if match:
            return match.group(1).strip()
        return None

    def resolver_colaborador(
        self,
        nome_arquivo: str,
        db,
    ) -> tuple[str | None, str | None]:
        """Resolve employee_id + condominio_id para doc scope=funcionario sem FK.

        INV-4: matching por nome (ILIKE) — fallback quando referente_a_employee_id IS NULL.
        Retorna (employee_id, condominio_id) como strings UUID, ou (None, None).
        """
        from sqlalchemy import text

        nome = self._extrair_nome_do_arquivo(nome_arquivo)
        if not nome:
            return None, None

        # Compara SEM espaço e sem acento: "ALEXANDRESOUZADASILVA" = "Alexandre Souza da Silva".
        import unicodedata as _ud
        chave = _ud.normalize("NFKD", nome).encode("ascii", "ignore").decode().upper()
        chave = re.sub(r"[^A-Z]", "", chave)
        if len(chave) < 6:
            return None, None
        _SEM = "upper(regexp_replace(translate(e.nome, 'áàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚÇ', 'aaaaeeiooouc' || 'AAAAEEIOOOUC'), '[^A-Za-z]', '', 'g'))"
        row = db.execute(
            text(f"""
                SELECT e.id::text AS emp_id, c.id::text AS cond_id
                FROM employee_alocacoes ea
                JOIN employees e ON e.id = ea.employee_id
                JOIN condominios c ON c.id = ea.condominio_id
                WHERE ea.ativo = true AND {_SEM} = :chave
                LIMIT 1
            """),
            {"chave": chave},
        ).fetchone()
        if row:
            return row[0], row[1]
        # Sem alocação ativa (escritório, afastado): ainda é gente da casa.
        row = db.execute(
            text(f"SELECT e.id::text FROM employees e WHERE {_SEM} = :chave LIMIT 1"), {"chave": chave}
        ).fetchone()
        if row:
            return row[0], None
        return None, None

    def _update_doc_fks(
        self,
        doc_id: str,
        emp_id: str,
        cond_id: str,
        db,
    ) -> None:
        """Grava referente_a_employee_id e condominio_id no onvio_documents (apenas se NULL)."""
        from sqlalchemy import text

        db.execute(
            text("""
                UPDATE onvio_documents
                SET referente_a_employee_id = CAST(:emp_id AS uuid),
                    condominio_id = CAST(:cond_id AS uuid)
                WHERE id = CAST(:doc_id AS uuid)
                  AND referente_a_employee_id IS NULL
            """),
            {"emp_id": emp_id, "cond_id": cond_id, "doc_id": doc_id},
        )

    def _get_docs_sem_vinculo(self, mes_ref: str, db) -> list:
        """Retorna onvio_documents do mês com caminho_local preenchido."""
        from sqlalchemy import text

        return db.execute(
            text("""
                SELECT id::text, nome_arquivo, categoria, caminho_local,
                       doc_scope, condominio_id::text,
                       referente_a_employee_id::text
                FROM onvio_documents
                -- 447 de 626 documentos não trazem mês no NOME (medido 07/09/2026) e ficavam
                -- para sempre sem vínculo. Fallback: sem mes_ref, vale o mês anterior à data
                -- em que o Onvio recebeu o arquivo (o pacote da competência X chega em X+1).
                WHERE (mes_ref = :mes_ref
                       OR (coalesce(mes_ref, '') = '' AND data_onvio IS NOT NULL
                           AND to_char(data_onvio - interval '1 month', 'MM.YYYY') = :mes_ref))
                  AND caminho_local IS NOT NULL
            """),
            {"mes_ref": mes_ref},
        ).fetchall()

    def vincular_doc_ao_kit(
        self,
        doc_id: str,
        nome_arquivo: str,
        categoria: str,
        caminho_local: str,
        doc_scope: str | None,
        cond_id: str | None,
        employee_id: str | None,
        ref_date: str,
        cond_to_ged: dict[str, str],
        db,
    ) -> bool:
        """Vincula doc Onvio ao slot correto no kit GED.

        Para scope=funcionario sem FK: resolve via resolver_colaborador() (INV-4).
        INV-5: só preenche slots com file_path IS NULL.
        """
        # Escopo nulo (o classificador de escopo do sync nunca roda): categoria de funcionário
        # é escopo de funcionário — os 47 recibos de agosto ficavam "ignorados" por isso.
        if not doc_scope and categoria in MAPA_TIPOS_ONVIO_FUNCIONARIO:
            doc_scope = "funcionario"
        # Resolver employee_id quando ausente (INV-4 — nome como fallback)
        if doc_scope == "funcionario" and not employee_id:
            resolved_emp, resolved_cond = self.resolver_colaborador(nome_arquivo, db)
            if resolved_emp:
                self._update_doc_fks(doc_id, resolved_emp, resolved_cond, db)
                employee_id = resolved_emp
                if not cond_id:
                    cond_id = resolved_cond

        if doc_scope == "funcionario" and employee_id:
            return self._vincular_funcionario(db, cond_to_ged, categoria, caminho_local, employee_id, ref_date)
        elif cond_id:
            return self._vincular_empresa(db, cond_to_ged, categoria, caminho_local, cond_id, ref_date)
        return False

    def _normalize(self, s: str) -> str:
        nfkd = unicodedata.normalize("NFKD", (s or "").upper())
        return "".join(c for c in nfkd if not unicodedata.combining(c))

    def _sig(self, s: str) -> set[str]:
        return {w for w in self._normalize(s).split() if w not in _STOP_WORDS_MATCH and len(w) >= 3}

    def _build_cond_to_ged_map(self, db) -> dict[str, str]:
        """Build condominios.id → ged_clients.id via word-set intersection."""
        from sqlalchemy import text

        condominios = db.execute(text("SELECT id::text, nome FROM condominios WHERE ativo = true")).fetchall()
        ged_clients = db.execute(text("SELECT id::text, name FROM ged_clients WHERE is_active = true")).fetchall()

        mapping: dict[str, str] = {}
        for cond_id, cond_nome in condominios:
            cond_sig = self._sig(cond_nome)
            if not cond_sig:
                continue
            for ged_id, ged_name in ged_clients:
                ged_sig = self._sig(ged_name)
                if cond_sig <= ged_sig or ged_sig <= cond_sig:
                    mapping[cond_id] = ged_id
                    break
        return mapping

    def _mes_ref_to_date(self, mes_ref: str) -> str:
        """'04.2026' → '2026-04-01'"""
        parts = mes_ref.split(".")
        return f"{parts[1]}-{parts[0]}-01"

    def _vincular_empresa(
        self,
        db,
        cond_to_ged: dict[str, str],
        categoria: str,
        caminho_local: str,
        cond_id: str,
        ref_date: str,
    ) -> bool:
        """Vincular doc empresa-level ao slot correspondente no kit."""
        from sqlalchemy import text

        kit_doc_type = MAPA_TIPOS_ONVIO_EMPRESA.get(categoria)
        if not kit_doc_type:
            return False

        ged_client_id = cond_to_ged.get(cond_id)
        if not ged_client_id:
            return False

        kit_row = db.execute(
            text("""
                SELECT id::text FROM ged_document_kits
                WHERE client_id = CAST(:client_id AS uuid)
                  AND reference_month = CAST(:ref_date AS date)
            """),
            {"client_id": ged_client_id, "ref_date": ref_date},
        ).fetchone()
        if not kit_row:
            return False
        kit_id = kit_row[0]

        # INV-5: só preenche slots vazios
        slot = db.execute(
            text("""
                SELECT id::text FROM ged_kit_documents
                WHERE kit_id = CAST(:kit_id AS uuid)
                  AND document_type = :doc_type
                  AND (file_path IS NULL OR file_path = '')
                  AND employee_id IS NULL
                LIMIT 1
            """),
            {"kit_id": kit_id, "doc_type": kit_doc_type},
        ).fetchone()
        if not slot:
            return False

        db.execute(
            text("""
                UPDATE ged_kit_documents
                SET file_path = :caminho, source_module = 'hermes', updated_at = NOW()
                WHERE id = CAST(:slot_id AS uuid)
            """),
            {"caminho": caminho_local, "slot_id": slot[0]},
        )
        return True

    def _vincular_funcionario(
        self,
        db,
        cond_to_ged: dict[str, str],
        categoria: str,
        caminho_local: str,
        employee_id: str,
        ref_date: str,
    ) -> bool:
        """Vincular doc per-employee ao slot correspondente no kit."""
        from sqlalchemy import text

        # Para categorias Inter: auto-categorizar + resumo kit (T-CATEGORIAS)
        if categoria in TIPOS_INTER and employee_id:
            try:
                emp_row = db.execute(
                    text("SELECT nome FROM employees WHERE id = CAST(:id AS uuid)"),
                    {"id": employee_id},
                ).fetchone()
                if emp_row:
                    mes_fmt = ref_date[5:7] + "." + ref_date[:4]  # "2026-03-01" → "03.2026"
                    from modules.integrations.inter.services.categorizacao_service import (
                        InterCategorizacaoService,
                    )

                    cat_svc = InterCategorizacaoService(db)
                    cat_svc.auto_categorizar_colaborador(emp_row[0], mes_fmt)
                    resumo = cat_svc.resumo_kit_colaborador(emp_row[0], mes_fmt)
                    logger.info(
                        "HERMES Inter categorias: %s (%s) → kit R$%.2f (%d docs)",
                        emp_row[0],
                        mes_fmt,
                        resumo["total_pago_kit"],
                        len(resumo["por_tipo_documento"]),
                    )
            except Exception as exc:
                logger.debug("HERMES Inter categorias falhou: %s", exc)

        kit_doc_type = MAPA_TIPOS_ONVIO_FUNCIONARIO.get(categoria)
        if not kit_doc_type:
            return False

        # Resolve condomínio do funcionário via alocações ativas
        aloc = db.execute(
            text("""
                SELECT condominio_id::text FROM employee_alocacoes
                WHERE employee_id = CAST(:emp_id AS uuid) AND ativo = true
                ORDER BY data_inicio DESC LIMIT 1
            """),
            {"emp_id": employee_id},
        ).fetchone()
        if not aloc:
            return False

        ged_client_id = cond_to_ged.get(aloc[0])
        if not ged_client_id:
            return False

        kit_row = db.execute(
            text("""
                SELECT id::text FROM ged_document_kits
                WHERE client_id = CAST(:client_id AS uuid)
                  AND reference_month = CAST(:ref_date AS date)
            """),
            {"client_id": ged_client_id, "ref_date": ref_date},
        ).fetchone()
        if not kit_row:
            return False
        kit_id = kit_row[0]

        # INV-5: só preenche slots vazios do mesmo funcionário
        slot = db.execute(
            text("""
                SELECT id::text FROM ged_kit_documents
                WHERE kit_id = CAST(:kit_id AS uuid)
                  AND document_type = :doc_type
                  AND employee_id = CAST(:emp_id AS uuid)
                  AND (file_path IS NULL OR file_path = '')
                LIMIT 1
            """),
            {"kit_id": kit_id, "doc_type": kit_doc_type, "emp_id": employee_id},
        ).fetchone()
        if slot:
            db.execute(
                text("""
                    UPDATE ged_kit_documents
                    SET file_path = :caminho, source_module = 'hermes', updated_at = NOW()
                    WHERE id = CAST(:slot_id AS uuid)
                """),
                {"caminho": caminho_local, "slot_id": slot[0]},
            )
            return True
        # Sem slot vazio (o kit do banco não pré-cria a vaga; a linha de contracheque que existe
        # é a gerada pelo ERP para assinatura): o ORIGINAL do Onvio entra como documento
        # próprio, sem sobrescrever e sem duplicar o mesmo arquivo. 45 de 49 recibos de
        # agosto/2026 morriam aqui (07/09/2026).
        ja = db.execute(
            text("SELECT 1 FROM ged_kit_documents WHERE kit_id = CAST(:kit_id AS uuid) "
                 "AND employee_id = CAST(:emp_id AS uuid) AND file_path = :caminho LIMIT 1"),
            {"kit_id": kit_id, "emp_id": employee_id, "caminho": caminho_local},
        ).fetchone()
        if ja:
            return False
        import os as _os
        db.execute(
            text("""
                INSERT INTO ged_kit_documents
                  (id, kit_id, employee_id, document_type, document_name, file_path, source_module,
                   auto_generated, is_signed, created_at, updated_at)
                VALUES (gen_random_uuid(), CAST(:kit_id AS uuid), CAST(:emp_id AS uuid), :tipo, :nome,
                        :caminho, 'hermes', false, false, NOW(), NOW())
            """),
            {"kit_id": kit_id, "emp_id": employee_id, "tipo": f"{kit_doc_type}_onvio",
             "nome": f"{_os.path.basename(caminho_local)[:150]} (original Onvio)", "caminho": caminho_local},
        )
        return True

    def _recalcular_completude_mes(self, db, ref_date: str) -> int:
        """Recalcular completion_percentage de todos os kits do mês (INV-12).

        A conta MUDOU DE CASA: mora em `services/completude_slots.py`, junto com os outros
        dois pontos que preenchem slot. Ela vivia só aqui, e por isso o `kit_pdf_controller`
        preenchia arquivo sem recalcular nada — maio ficou 93,7% montado anunciando 12,2%.
        """
        from modules.gedeon.services.completude_slots import recalcular_competencia

        return recalcular_competencia(db, ref_date)

    def processar_mes(self, mes_ref: str | None = None) -> dict:
        """
        Vincular todos os onvio_documents do mês aos slots ged_kit_documents.
        Idempotente: pula slots já preenchidos (INV-5).
        Recalcula completion_percentage após vincular (INV-12).
        """
        from datetime import date

        from core.database.session import get_sync_db

        if mes_ref is None:
            today = date.today()
            mes_ref = f"{today.month:02d}.{today.year}"

        ref_date = self._mes_ref_to_date(mes_ref)

        vinculados = 0
        ignorados = 0
        erros = 0

        with get_sync_db() as db:
            cond_to_ged = self._build_cond_to_ged_map(db)
            docs = self._get_docs_sem_vinculo(mes_ref, db)

            for doc in docs:
                doc_id, nome_arquivo, categoria, caminho_local, doc_scope, cond_id, employee_id = doc
                try:
                    ok = self.vincular_doc_ao_kit(
                        doc_id,
                        nome_arquivo,
                        categoria,
                        caminho_local,
                        doc_scope,
                        cond_id,
                        employee_id,
                        ref_date,
                        cond_to_ged,
                        db,
                    )
                    if ok:
                        vinculados += 1
                    else:
                        ignorados += 1
                except Exception as exc:
                    logger.error("HERMES: erro doc %s (%s): %s", doc_id, nome_arquivo, exc)
                    erros += 1

            db.commit()

            kits_atualizados = self._recalcular_completude_mes(db, ref_date)
            db.commit()

        logger.info(
            "HERMES %s: %d vinculados, %d ignorados, %d erros, %d kits atualizados",
            mes_ref,
            vinculados,
            ignorados,
            erros,
            kits_atualizados,
        )

        # Publicar evento GED_KIT_DOCUMENTO_VINCULADO (CAMADA 1 — FLUXO)
        if vinculados > 0:
            self._publicar_evento_vinculados(mes_ref, vinculados)

        return {
            "mes_ref": mes_ref,
            "vinculados": vinculados,
            "ignorados": ignorados,
            "erros": erros,
            "kits_atualizados": kits_atualizados,
        }

    def buscar_pagamentos_inter(
        self,
        nome: str,
        mes_ref: str | None,
        db,
    ) -> dict:
        """
        Busca transações de débito no Banco Inter por nome do colaborador (sync).
        Usado pelo endpoint /gedeon/colaborador/{nome}/pagamentos.

        Args:
            nome: Nome parcial — ex: "GRACIENE" ou "JONHATA DINIZ"
            mes_ref: Filtro MM.YYYY — ex: "03.2026"
            db: Session síncrona (SQLAlchemy)
        """
        from sqlalchemy import text

        pattern = f"%{nome.upper()}%"
        params: dict = {"pattern": pattern}
        date_filter = ""

        if mes_ref:
            partes = mes_ref.split(".")
            if len(partes) == 2:
                import calendar

                mes, ano = int(partes[0]), int(partes[1])
                ultimo = calendar.monthrange(ano, mes)[1]
                from datetime import date as _date

                params["inicio"] = _date(ano, mes, 1)
                params["fim"] = _date(ano, mes, ultimo)
                date_filter = "AND data_lancamento BETWEEN :inicio AND :fim"

        rows = db.execute(
            text(f"""
                SELECT id, data_lancamento, tipo_transacao, valor, descricao,
                       raw_payload, detalhes_destinatario
                FROM inter_transactions
                WHERE tipo_operacao = 'D'
                  AND (
                      UPPER(descricao) ILIKE :pattern
                      OR UPPER(raw_payload->>'counterpart_name') ILIKE :pattern
                  )
                  {date_filter}
                ORDER BY data_lancamento DESC, valor DESC
                LIMIT 50
            """),
            params,
        ).fetchall()

        transacoes = []
        total_valor = 0.0
        for r in rows:
            raw = r.raw_payload or {}
            det = r.detalhes_destinatario or {}
            valor = float(r.valor) if r.valor else 0.0
            total_valor += valor
            transacoes.append(
                {
                    "id": str(r.id),
                    "data": str(r.data_lancamento),
                    "tipo_transacao": r.tipo_transacao,
                    "valor": valor,
                    "descricao": r.descricao,
                    "nome_beneficiario": det.get("nome") or raw.get("counterpart_name"),
                    "banco_beneficiario": det.get("banco") or raw.get("counterpart_bank"),
                }
            )

        return {
            "nome_buscado": nome,
            "mes_ref": mes_ref,
            "total_transacoes": len(transacoes),
            "total_valor": round(total_valor, 2),
            "transacoes": transacoes,
        }

    def _publicar_evento_vinculados(self, mes_ref: str, vinculados: int) -> None:
        """Publica GED_KIT_DOCUMENTO_VINCULADO no barramento após linking bem-sucedido."""
        import asyncio

        try:
            from infrastructure.event_bus.bus import EventTypes, event_bus

            asyncio.run(
                event_bus.emit(
                    event_type=EventTypes.GED_KIT_DOCUMENTO_VINCULADO,
                    payload={"mes_ref": mes_ref, "vinculados": vinculados},
                    source_module="hermes",
                )
            )
            logger.info("HERMES: evento GED_KIT_DOCUMENTO_VINCULADO publicado (%d docs)", vinculados)
        except Exception as exc:
            logger.warning("HERMES: evento não publicado (bus desconectado?): %s", exc)


# Singleton global
hermes = Hermes()
