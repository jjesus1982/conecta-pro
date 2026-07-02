-- FORWARD (upgrade) migrations FIN+DP 2026-06-01 — balde 1+2 (idempotente)
BEGIN;

-- === ENUMS (idempotentes) — necessarios pelas tabelas do balde 2 ===
-- CREATE TYPE (enums) idempotentes — necessarios pelas 17 tabelas do balde 2
DO $$ BEGIN CREATE TYPE activitylevel AS ENUM ('UNIT', 'BATCH', 'PRODUCT', 'CUSTOMER', 'FACILITY'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE activitystatus AS ENUM ('ACTIVE', 'INACTIVE', 'DEPRECATED', 'PENDING_APPROVAL'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE activitytype AS ENUM ('PRIMARY', 'SUPPORT', 'ADMINISTRATIVE', 'QUALITY', 'LOGISTICS', 'MAINTENANCE', 'SETUP', 'IDLE', 'REWORK', 'CUSTOMER_SERVICE'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE allocationbasis AS ENUM ('DIRECT_LABOR_HOURS', 'DIRECT_LABOR_COST', 'MACHINE_HOURS', 'UNITS_PRODUCED', 'REVENUE', 'DIRECT_MATERIALS', 'FLOOR_SPACE', 'HEADCOUNT', 'ACTIVITY_BASED', 'CUSTOM'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE allocationmethod_alloc AS ENUM ('DRIVER_BASED', 'PERCENTAGE', 'PROPORTIONAL', 'FIXED_AMOUNT', 'EQUAL_SHARE', 'WEIGHTED', 'FORMULA'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE allocationstatus AS ENUM ('DRAFT', 'PENDING', 'APPROVED', 'EXECUTED', 'REVERSED', 'CANCELLED'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE allocationtype AS ENUM ('POOL_TO_ACTIVITY', 'ACTIVITY_TO_OBJECT', 'DIRECT', 'OVERHEAD', 'RECIPROCAL', 'STEP_DOWN', 'ADJUSTMENT', 'REVERSAL'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE analysisscope AS ENUM ('GLOBAL', 'COST_CENTER', 'PRODUCT', 'SERVICE', 'CUSTOMER', 'PROJECT', 'ACTIVITY', 'POOL', 'CUSTOM'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE analysisstatus AS ENUM ('DRAFT', 'RUNNING', 'COMPLETED', 'FAILED', 'ARCHIVED'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE analysistype AS ENUM ('ABC_COSTING', 'PROFITABILITY', 'VARIANCE', 'BREAK_EVEN', 'COST_VOLUME_PROFIT', 'IDLE_CAPACITY', 'TREND', 'COMPARATIVE', 'WHAT_IF', 'CUSTOM'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE cache_status_enum AS ENUM ('VALID', 'STALE', 'EXPIRED', 'REFRESHING', 'ERROR'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE cache_type_enum AS ENUM ('WIDGET', 'KPI', 'DASHBOARD', 'REPORT', 'QUERY', 'AGGREGATION'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE costobjectstatus AS ENUM ('ACTIVE', 'INACTIVE', 'DISCONTINUED', 'PENDING'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE costobjecttype AS ENUM ('PRODUCT', 'SERVICE', 'CONTRACT', 'PROJECT', 'CUSTOMER', 'CUSTOMER_SEGMENT', 'CHANNEL', 'REGION', 'DEPARTMENT', 'BUSINESS_UNIT', 'ORDER', 'BATCH', 'CAMPAIGN'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE delivery_method_enum AS ENUM ('EMAIL', 'STORAGE', 'WEBHOOK', 'API'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE drivercategory AS ENUM ('RESOURCE', 'ACTIVITY', 'COST_OBJECT'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE drivermeasureunit AS ENUM ('QUANTITY', 'HOURS', 'MINUTES', 'DAYS', 'SQUARE_METERS', 'CUBIC_METERS', 'KILOGRAMS', 'LITERS', 'KILOMETERS', 'CURRENCY', 'PERCENTAGE', 'HEADCOUNT'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE driverstatus AS ENUM ('ACTIVE', 'INACTIVE', 'DEPRECATED'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE drivertype AS ENUM ('TRANSACTION', 'DURATION', 'INTENSITY', 'VOLUME', 'HEADCOUNT', 'AREA', 'REVENUE', 'CONSUMPTION', 'EQUIPMENT', 'CUSTOM'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE poolstatus AS ENUM ('ACTIVE', 'INACTIVE', 'CLOSED'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE pooltype AS ENUM ('OVERHEAD', 'LABOR', 'EQUIPMENT', 'FACILITIES', 'UTILITIES', 'ADMINISTRATIVE', 'TECHNOLOGY', 'QUALITY', 'LOGISTICS', 'MAINTENANCE', 'SHARED_SERVICES', 'CUSTOM'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE profitabilitylevel AS ENUM ('HIGHLY_PROFITABLE', 'PROFITABLE', 'MARGINAL', 'BREAK_EVEN', 'UNPROFITABLE'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE report_format_enum AS ENUM ('PDF', 'EXCEL', 'CSV', 'JSON', 'HTML'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE report_frequency_enum AS ENUM ('ONCE', 'DAILY', 'WEEKLY', 'BIWEEKLY', 'MONTHLY', 'QUARTERLY', 'YEARLY'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE report_status_enum AS ENUM ('ACTIVE', 'PAUSED', 'EXPIRED', 'CANCELLED', 'ERROR'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE report_type_enum AS ENUM ('CASH_FLOW', 'INCOME_STATEMENT', 'BALANCE_SHEET', 'ACCOUNTS_PAYABLE', 'ACCOUNTS_RECEIVABLE', 'BUDGET_VS_ACTUAL', 'PROFITABILITY', 'KPI_SUMMARY', 'COST_ANALYSIS', 'TAX_SUMMARY', 'BANK_RECONCILIATION', 'AGING_REPORT', 'CUSTOM'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE reportformat AS ENUM ('PDF', 'EXCEL', 'CSV', 'JSON', 'HTML'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE valueaddedtype AS ENUM ('VALUE_ADDED', 'NON_VALUE_ADDED', 'BUSINESS_VALUE'); EXCEPTION WHEN duplicate_object THEN null; END $$;


-- tabela ecd_resumos (enums: [])
CREATE TABLE IF NOT EXISTS ecd_resumos (
	id UUID NOT NULL,
	sped_file_id UUID NOT NULL,
	condominio_id UUID NOT NULL,
	ano INTEGER NOT NULL,
	data_inicio DATE NOT NULL,
	data_fim DATE NOT NULL,
	tipo_ecd VARCHAR(1) NOT NULL,
	total_ativo NUMERIC(15, 2) NOT NULL,
	total_passivo NUMERIC(15, 2) NOT NULL,
	patrimonio_liquido NUMERIC(15, 2) NOT NULL,
	total_receitas NUMERIC(15, 2) NOT NULL,
	total_despesas NUMERIC(15, 2) NOT NULL,
	resultado_exercicio NUMERIC(15, 2) NOT NULL,
	qtd_lancamentos INTEGER NOT NULL,
	qtd_contas INTEGER NOT NULL,
	qtd_centros_custo INTEGER NOT NULL,
	termo_abertura TEXT,
	termo_encerramento TEXT,
	hash_abertura VARCHAR(64),
	hash_encerramento VARCHAR(64),
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE,
	PRIMARY KEY (id)
);

-- tabela efd_contribuicoes_resumos (enums: [])
CREATE TABLE IF NOT EXISTS efd_contribuicoes_resumos (
	id UUID NOT NULL,
	sped_file_id UUID NOT NULL,
	condominio_id UUID NOT NULL,
	ano INTEGER NOT NULL,
	mes INTEGER NOT NULL,
	receita_bruta_cumulativo NUMERIC(15, 2) NOT NULL,
	receita_bruta_nao_cumulativo NUMERIC(15, 2) NOT NULL,
	receita_bruta_total NUMERIC(15, 2) NOT NULL,
	pis_base_calculo NUMERIC(15, 2) NOT NULL,
	pis_debito NUMERIC(15, 2) NOT NULL,
	pis_credito NUMERIC(15, 2) NOT NULL,
	pis_saldo_credor_anterior NUMERIC(15, 2) NOT NULL,
	pis_a_recolher NUMERIC(15, 2) NOT NULL,
	pis_saldo_credor NUMERIC(15, 2) NOT NULL,
	cofins_base_calculo NUMERIC(15, 2) NOT NULL,
	cofins_debito NUMERIC(15, 2) NOT NULL,
	cofins_credito NUMERIC(15, 2) NOT NULL,
	cofins_saldo_credor_anterior NUMERIC(15, 2) NOT NULL,
	cofins_a_recolher NUMERIC(15, 2) NOT NULL,
	cofins_saldo_credor NUMERIC(15, 2) NOT NULL,
	pis_retido NUMERIC(15, 2) NOT NULL,
	cofins_retido NUMERIC(15, 2) NOT NULL,
	qtd_documentos_receitas INTEGER NOT NULL,
	qtd_documentos_creditos INTEGER NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE,
	PRIMARY KEY (id)
);

-- tabela efd_icms_ipi_resumos (enums: [])
CREATE TABLE IF NOT EXISTS efd_icms_ipi_resumos (
	id UUID NOT NULL,
	sped_file_id UUID NOT NULL,
	condominio_id UUID NOT NULL,
	ano INTEGER NOT NULL,
	mes INTEGER NOT NULL,
	valor_contabil_entradas NUMERIC(15, 2) NOT NULL,
	base_icms_entradas NUMERIC(15, 2) NOT NULL,
	icms_entradas NUMERIC(15, 2) NOT NULL,
	ipi_entradas NUMERIC(15, 2) NOT NULL,
	valor_contabil_saidas NUMERIC(15, 2) NOT NULL,
	base_icms_saidas NUMERIC(15, 2) NOT NULL,
	icms_saidas NUMERIC(15, 2) NOT NULL,
	ipi_saidas NUMERIC(15, 2) NOT NULL,
	icms_st_entradas NUMERIC(15, 2) NOT NULL,
	icms_st_saidas NUMERIC(15, 2) NOT NULL,
	icms_debito NUMERIC(15, 2) NOT NULL,
	icms_credito NUMERIC(15, 2) NOT NULL,
	icms_saldo_credor_anterior NUMERIC(15, 2) NOT NULL,
	icms_outros_debitos NUMERIC(15, 2) NOT NULL,
	icms_outros_creditos NUMERIC(15, 2) NOT NULL,
	icms_estorno_debito NUMERIC(15, 2) NOT NULL,
	icms_estorno_credito NUMERIC(15, 2) NOT NULL,
	icms_saldo_devedor NUMERIC(15, 2) NOT NULL,
	icms_saldo_credor NUMERIC(15, 2) NOT NULL,
	icms_a_recolher NUMERIC(15, 2) NOT NULL,
	ipi_debito NUMERIC(15, 2) NOT NULL,
	ipi_credito NUMERIC(15, 2) NOT NULL,
	ipi_saldo_credor_anterior NUMERIC(15, 2) NOT NULL,
	ipi_a_recolher NUMERIC(15, 2) NOT NULL,
	ipi_saldo_credor NUMERIC(15, 2) NOT NULL,
	qtd_documentos_entradas INTEGER NOT NULL,
	qtd_documentos_saidas INTEGER NOT NULL,
	qtd_itens INTEGER NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE,
	PRIMARY KEY (id)
);

-- tabela fin_cost_analyses (enums: ['analysisscope', 'analysisstatus', 'analysistype', 'reportformat'])
CREATE TABLE IF NOT EXISTS fin_cost_analyses (
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	condominio_id UUID NOT NULL,
	code VARCHAR(30) NOT NULL,
	name VARCHAR(150) NOT NULL,
	description TEXT,
	analysis_type analysistype NOT NULL,
	status analysisstatus NOT NULL,
	scope analysisscope NOT NULL,
	period_start TIMESTAMP WITH TIME ZONE NOT NULL,
	period_end TIMESTAMP WITH TIME ZONE NOT NULL,
	reference_period VARCHAR(7),
	cost_center_ids JSONB,
	activity_ids JSONB,
	pool_ids JSONB,
	object_ids JSONB,
	filters JSONB,
	parameters JSONB,
	scenarios JSONB,
	comparison_period_start TIMESTAMP WITH TIME ZONE,
	comparison_period_end TIMESTAMP WITH TIME ZONE,
	results JSONB,
	total_cost NUMERIC(18, 2) NOT NULL,
	total_revenue NUMERIC(18, 2) NOT NULL,
	total_margin NUMERIC(18, 2) NOT NULL,
	margin_percent NUMERIC(8, 4) NOT NULL,
	total_direct_cost NUMERIC(18, 2) NOT NULL,
	total_indirect_cost NUMERIC(18, 2) NOT NULL,
	total_allocated NUMERIC(18, 2) NOT NULL,
	unallocated_cost NUMERIC(18, 2) NOT NULL,
	practical_capacity NUMERIC(18, 4),
	used_capacity NUMERIC(18, 4),
	idle_capacity NUMERIC(18, 4),
	idle_capacity_cost NUMERIC(18, 2),
	cost_variance NUMERIC(18, 2),
	volume_variance NUMERIC(18, 2),
	efficiency_variance NUMERIC(18, 2),
	price_variance NUMERIC(18, 2),
	break_even_units NUMERIC(18, 4),
	break_even_revenue NUMERIC(18, 2),
	safety_margin NUMERIC(18, 2),
	safety_margin_percent NUMERIC(8, 4),
	insights JSONB,
	recommendations JSONB,
	alerts JSONB,
	charts_data JSONB,
	started_at TIMESTAMP WITH TIME ZONE,
	completed_at TIMESTAMP WITH TIME ZONE,
	execution_time_ms INTEGER,
	error_message TEXT,
	report_format reportformat,
	report_path VARCHAR(300),
	report_generated_at TIMESTAMP WITH TIME ZONE,
	is_scheduled BOOLEAN NOT NULL,
	schedule_cron VARCHAR(50),
	next_run_at TIMESTAMP WITH TIME ZONE,
	last_run_at TIMESTAMP WITH TIME ZONE,
	shared_with JSONB,
	is_public BOOLEAN NOT NULL,
	is_template BOOLEAN NOT NULL,
	is_favorite BOOLEAN NOT NULL,
	active BOOLEAN NOT NULL,
	notes TEXT,
	tags JSONB,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	deleted_at TIMESTAMP WITH TIME ZONE,
	created_by UUID,
	updated_by UUID,
	deleted_by UUID,
	PRIMARY KEY (id),
	CONSTRAINT uq_cost_analysis_code UNIQUE (condominio_id, code)
);

-- tabela fin_cost_drivers (enums: ['drivercategory', 'drivermeasureunit', 'driverstatus', 'drivertype'])
CREATE TABLE IF NOT EXISTS fin_cost_drivers (
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	condominio_id UUID NOT NULL,
	code VARCHAR(30) NOT NULL,
	name VARCHAR(100) NOT NULL,
	description TEXT,
	driver_type drivertype NOT NULL,
	driver_category drivercategory NOT NULL,
	status driverstatus NOT NULL,
	measure_unit drivermeasureunit NOT NULL,
	measure_symbol VARCHAR(10),
	unit_cost NUMERIC(18, 6) NOT NULL,
	unit_cost_currency VARCHAR(3) NOT NULL,
	practical_capacity NUMERIC(18, 4),
	theoretical_capacity NUMERIC(18, 4),
	used_capacity NUMERIC(18, 4) NOT NULL,
	custom_formula TEXT,
	formula_variables JSONB,
	update_frequency VARCHAR(20) NOT NULL,
	last_rate_update TIMESTAMP WITH TIME ZONE,
	next_rate_update TIMESTAMP WITH TIME ZONE,
	rate_history JSONB,
	data_source VARCHAR(100),
	source_table VARCHAR(100),
	source_field VARCHAR(100),
	is_automated BOOLEAN NOT NULL,
	min_value NUMERIC(18, 4),
	max_value NUMERIC(18, 4),
	requires_validation BOOLEAN NOT NULL,
	total_allocations INTEGER NOT NULL,
	total_allocated_amount NUMERIC(18, 2) NOT NULL,
	average_rate NUMERIC(18, 6) NOT NULL,
	is_primary BOOLEAN NOT NULL,
	is_system BOOLEAN NOT NULL,
	active BOOLEAN NOT NULL,
	notes TEXT,
	tags JSONB,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	deleted_at TIMESTAMP WITH TIME ZONE,
	created_by UUID,
	updated_by UUID,
	deleted_by UUID,
	PRIMARY KEY (id),
	CONSTRAINT uq_cost_driver_code UNIQUE (condominio_id, code)
);

-- tabela fin_cost_objects (enums: ['costobjectstatus', 'costobjecttype', 'profitabilitylevel'])
CREATE TABLE IF NOT EXISTS fin_cost_objects (
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	condominio_id UUID NOT NULL,
	parent_id UUID,
	reference_type VARCHAR(50),
	reference_id UUID,
	code VARCHAR(50) NOT NULL,
	name VARCHAR(150) NOT NULL,
	short_name VARCHAR(50),
	description TEXT,
	object_type costobjecttype NOT NULL,
	status costobjectstatus NOT NULL,
	category VARCHAR(100),
	subcategory VARCHAR(100),
	level INTEGER NOT NULL,
	path VARCHAR(300),
	order_index INTEGER,
	revenue NUMERIC(18, 2) NOT NULL,
	revenue_budget NUMERIC(18, 2) NOT NULL,
	direct_material_cost NUMERIC(18, 2) NOT NULL,
	direct_labor_cost NUMERIC(18, 2) NOT NULL,
	other_direct_cost NUMERIC(18, 2) NOT NULL,
	total_direct_cost NUMERIC(18, 2) NOT NULL,
	allocated_overhead NUMERIC(18, 2) NOT NULL,
	allocated_activity_cost NUMERIC(18, 2) NOT NULL,
	total_indirect_cost NUMERIC(18, 2) NOT NULL,
	total_cost NUMERIC(18, 2) NOT NULL,
	cost_budget NUMERIC(18, 2) NOT NULL,
	cost_variance NUMERIC(18, 2) NOT NULL,
	gross_margin NUMERIC(18, 2) NOT NULL,
	gross_margin_percent NUMERIC(8, 4) NOT NULL,
	contribution_margin NUMERIC(18, 2) NOT NULL,
	contribution_margin_percent NUMERIC(8, 4) NOT NULL,
	net_margin NUMERIC(18, 2) NOT NULL,
	net_margin_percent NUMERIC(8, 4) NOT NULL,
	profitability_level profitabilitylevel,
	profitability_score NUMERIC(5, 2),
	unit_cost NUMERIC(18, 6) NOT NULL,
	unit_price NUMERIC(18, 6) NOT NULL,
	quantity NUMERIC(18, 4) NOT NULL,
	unit_of_measure VARCHAR(20),
	cost_breakdown JSONB,
	activities_consumed JSONB,
	drivers_consumed JSONB,
	allocations_count INTEGER NOT NULL,
	last_cost_update TIMESTAMP WITH TIME ZONE,
	reference_period VARCHAR(7),
	valid_from TIMESTAMP WITH TIME ZONE,
	valid_until TIMESTAMP WITH TIME ZONE,
	owner_id UUID,
	owner_name VARCHAR(100),
	department VARCHAR(100),
	is_strategic BOOLEAN NOT NULL,
	requires_analysis BOOLEAN NOT NULL,
	active BOOLEAN NOT NULL,
	notes TEXT,
	tags JSONB,
	extra_metadata JSONB,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	deleted_at TIMESTAMP WITH TIME ZONE,
	created_by UUID,
	updated_by UUID,
	deleted_by UUID,
	PRIMARY KEY (id),
	CONSTRAINT uq_cost_object_code UNIQUE (condominio_id, code)
);

-- tabela fin_cost_pools (enums: ['allocationbasis', 'poolstatus', 'pooltype'])
CREATE TABLE IF NOT EXISTS fin_cost_pools (
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	condominio_id UUID NOT NULL,
	parent_id UUID,
	cost_center_id UUID,
	code VARCHAR(30) NOT NULL,
	name VARCHAR(100) NOT NULL,
	description TEXT,
	pool_type pooltype NOT NULL,
	status poolstatus NOT NULL,
	allocation_basis allocationbasis NOT NULL,
	level INTEGER NOT NULL,
	path VARCHAR(200),
	order_index INTEGER,
	total_cost NUMERIC(18, 2) NOT NULL,
	allocated_cost NUMERIC(18, 2) NOT NULL,
	unallocated_cost NUMERIC(18, 2) NOT NULL,
	budget_amount NUMERIC(18, 2) NOT NULL,
	budget_variance NUMERIC(18, 2) NOT NULL,
	allocation_base_quantity NUMERIC(18, 4) NOT NULL,
	allocation_rate NUMERIC(18, 6) NOT NULL,
	rate_currency VARCHAR(3) NOT NULL,
	custom_allocation_formula TEXT,
	allocation_weights JSONB,
	cost_components JSONB,
	activities_count INTEGER NOT NULL,
	allocations_count INTEGER NOT NULL,
	last_allocation_date TIMESTAMP WITH TIME ZONE,
	reference_period VARCHAR(7),
	valid_from TIMESTAMP WITH TIME ZONE,
	valid_until TIMESTAMP WITH TIME ZONE,
	manager_id UUID,
	manager_name VARCHAR(100),
	department VARCHAR(100),
	is_homogeneous BOOLEAN NOT NULL,
	requires_approval BOOLEAN NOT NULL,
	auto_allocate BOOLEAN NOT NULL,
	active BOOLEAN NOT NULL,
	notes TEXT,
	tags JSONB,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	deleted_at TIMESTAMP WITH TIME ZONE,
	created_by UUID,
	updated_by UUID,
	deleted_by UUID,
	PRIMARY KEY (id),
	CONSTRAINT uq_cost_pool_code UNIQUE (condominio_id, code)
);

-- tabela fin_cost_activities (enums: ['activitylevel', 'activitystatus', 'activitytype', 'valueaddedtype'])
CREATE TABLE IF NOT EXISTS fin_cost_activities (
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	condominio_id UUID NOT NULL,
	parent_id UUID,
	cost_pool_id UUID,
	primary_driver_id UUID,
	cost_center_id UUID,
	code VARCHAR(30) NOT NULL,
	name VARCHAR(150) NOT NULL,
	short_name VARCHAR(50),
	description TEXT,
	activity_type activitytype NOT NULL,
	activity_level activitylevel NOT NULL,
	status activitystatus NOT NULL,
	value_added_type valueaddedtype NOT NULL,
	level INTEGER NOT NULL,
	path VARCHAR(300),
	order_index INTEGER,
	total_cost NUMERIC(18, 2) NOT NULL,
	fixed_cost NUMERIC(18, 2) NOT NULL,
	variable_cost NUMERIC(18, 2) NOT NULL,
	allocated_cost NUMERIC(18, 2) NOT NULL,
	activity_rate NUMERIC(18, 6) NOT NULL,
	rate_currency VARCHAR(3) NOT NULL,
	practical_capacity NUMERIC(18, 4),
	used_capacity NUMERIC(18, 4) NOT NULL,
	capacity_unit VARCHAR(20),
	standard_time NUMERIC(10, 4),
	actual_time NUMERIC(10, 4),
	time_variance NUMERIC(10, 4),
	execution_frequency VARCHAR(20) NOT NULL,
	executions_count INTEGER NOT NULL,
	last_execution_at TIMESTAMP WITH TIME ZONE,
	resources_consumed JSONB,
	outputs_produced JSONB,
	secondary_drivers JSONB,
	benchmark_cost NUMERIC(18, 2),
	benchmark_time NUMERIC(10, 4),
	benchmark_source VARCHAR(100),
	process_name VARCHAR(100),
	subprocess_name VARCHAR(100),
	department VARCHAR(100),
	responsible_id UUID,
	responsible_name VARCHAR(100),
	valid_from TIMESTAMP WITH TIME ZONE,
	valid_until TIMESTAMP WITH TIME ZONE,
	reference_period VARCHAR(7),
	is_core BOOLEAN NOT NULL,
	is_outsourceable BOOLEAN NOT NULL,
	is_automatable BOOLEAN NOT NULL,
	requires_approval BOOLEAN NOT NULL,
	active BOOLEAN NOT NULL,
	notes TEXT,
	tags JSONB,
	extra_metadata JSONB,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	deleted_at TIMESTAMP WITH TIME ZONE,
	created_by UUID,
	updated_by UUID,
	deleted_by UUID,
	PRIMARY KEY (id),
	CONSTRAINT uq_cost_activity_code UNIQUE (condominio_id, code)
);

-- tabela fin_cost_allocations (enums: ['allocationmethod_alloc', 'allocationstatus', 'allocationtype'])
CREATE TABLE IF NOT EXISTS fin_cost_allocations (
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	condominio_id UUID NOT NULL,
	allocation_number VARCHAR(30) NOT NULL,
	batch_id UUID,
	batch_sequence INTEGER,
	source_pool_id UUID,
	source_activity_id UUID,
	source_cost_center_id UUID,
	activity_id UUID,
	cost_object_id UUID,
	target_cost_center_id UUID,
	driver_id UUID,
	allocation_type allocationtype NOT NULL,
	status allocationstatus NOT NULL,
	allocation_method allocationmethod_alloc NOT NULL,
	description VARCHAR(200),
	reference VARCHAR(100),
	allocated_amount NUMERIC(18, 2) NOT NULL,
	currency VARCHAR(3) NOT NULL,
	driver_quantity NUMERIC(18, 6),
	driver_rate NUMERIC(18, 6),
	allocation_percentage NUMERIC(8, 4),
	allocation_weight NUMERIC(8, 4),
	formula_used TEXT,
	formula_variables JSONB,
	reference_period VARCHAR(7) NOT NULL,
	allocation_date TIMESTAMP WITH TIME ZONE NOT NULL,
	effective_date TIMESTAMP WITH TIME ZONE,
	cost_components JSONB,
	is_validated BOOLEAN NOT NULL,
	validated_at TIMESTAMP WITH TIME ZONE,
	validated_by UUID,
	validation_notes TEXT,
	approved_at TIMESTAMP WITH TIME ZONE,
	approved_by UUID,
	approval_notes TEXT,
	executed_at TIMESTAMP WITH TIME ZONE,
	executed_by UUID,
	is_reversed BOOLEAN NOT NULL,
	reversed_at TIMESTAMP WITH TIME ZONE,
	reversed_by UUID,
	reversal_reason TEXT,
	reversal_allocation_id UUID,
	journal_entry_id UUID,
	debit_account_id UUID,
	credit_account_id UUID,
	is_posted BOOLEAN NOT NULL,
	posted_at TIMESTAMP WITH TIME ZONE,
	source_document VARCHAR(100),
	source_system VARCHAR(50),
	external_reference VARCHAR(100),
	is_automatic BOOLEAN NOT NULL,
	is_recurring BOOLEAN NOT NULL,
	requires_approval BOOLEAN NOT NULL,
	active BOOLEAN NOT NULL,
	notes TEXT,
	tags JSONB,
	extra_metadata JSONB,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	deleted_at TIMESTAMP WITH TIME ZONE,
	created_by UUID,
	updated_by UUID,
	deleted_by UUID,
	PRIMARY KEY (id),
	CONSTRAINT uq_cost_allocation_number UNIQUE (condominio_id, allocation_number)
);

-- tabela financial_analytics_cache (enums: ['cache_status_enum', 'cache_type_enum'])
CREATE TABLE IF NOT EXISTS financial_analytics_cache (
	id UUID NOT NULL,
	condominio_id UUID NOT NULL,
	cache_key VARCHAR(255) NOT NULL,
	tipo cache_type_enum NOT NULL,
	status cache_status_enum NOT NULL,
	entity_type VARCHAR(100),
	entity_id UUID,
	query_hash VARCHAR(64),
	data JSONB NOT NULL,
	data_size_bytes INTEGER,
	row_count INTEGER,
	parametros JSONB,
	periodo_inicio TIMESTAMP WITHOUT TIME ZONE,
	periodo_fim TIMESTAMP WITHOUT TIME ZONE,
	ttl_seconds INTEGER NOT NULL,
	expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	is_expired BOOLEAN,
	hit_count INTEGER NOT NULL,
	miss_count INTEGER NOT NULL,
	last_hit_at TIMESTAMP WITHOUT TIME ZONE,
	last_refresh_at TIMESTAMP WITHOUT TIME ZONE,
	refresh_count INTEGER,
	refresh_duration_ms INTEGER,
	last_error TEXT,
	error_count INTEGER,
	tags JSONB,
	extra_metadata JSONB,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE,
	PRIMARY KEY (id)
);

-- tabela financial_scheduled_reports (enums: ['delivery_method_enum', 'report_format_enum', 'report_frequency_enum', 'report_status_enum', 'report_type_enum'])
CREATE TABLE IF NOT EXISTS financial_scheduled_reports (
	id UUID NOT NULL,
	condominio_id UUID NOT NULL,
	codigo VARCHAR(50) NOT NULL,
	nome VARCHAR(200) NOT NULL,
	descricao TEXT,
	tipo report_type_enum NOT NULL,
	formato report_format_enum NOT NULL,
	status report_status_enum NOT NULL,
	frequencia report_frequency_enum NOT NULL,
	hora_execucao TIME WITHOUT TIME ZONE,
	dia_semana INTEGER,
	dia_mes INTEGER,
	timezone VARCHAR(50),
	periodo_tipo VARCHAR(50),
	periodo_dias INTEGER,
	data_inicio DATE,
	data_fim DATE,
	valido_de DATE,
	valido_ate DATE,
	metodo_entrega delivery_method_enum NOT NULL,
	destinatarios_email JSONB,
	webhook_url VARCHAR(500),
	storage_path VARCHAR(500),
	template_id VARCHAR(100),
	template_config JSONB,
	custom_query TEXT,
	filtros JSONB,
	ordenacao JSONB,
	agrupamento JSONB,
	logo_url VARCHAR(500),
	header_text TEXT,
	footer_text TEXT,
	show_charts BOOLEAN,
	show_summary BOOLEAN,
	paper_size VARCHAR(20),
	orientation VARCHAR(20),
	proxima_execucao_at TIMESTAMP WITHOUT TIME ZONE,
	ultima_execucao_at TIMESTAMP WITHOUT TIME ZONE,
	ultima_execucao_status VARCHAR(50),
	ultima_execucao_erro TEXT,
	total_execucoes INTEGER,
	total_erros INTEGER,
	ultimo_arquivo_url VARCHAR(500),
	ultimo_arquivo_tamanho INTEGER,
	ultimo_arquivo_hash VARCHAR(64),
	notificar_sucesso BOOLEAN,
	notificar_erro BOOLEAN,
	notificar_email VARCHAR(255),
	tags JSONB,
	extra_metadata JSONB,
	created_by UUID,
	updated_by UUID,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE,
	PRIMARY KEY (id)
);

-- tabela payroll_integrations (enums: [])
CREATE TABLE IF NOT EXISTS payroll_integrations (
	id UUID NOT NULL,
	condominio_id UUID NOT NULL,
	name VARCHAR(100) NOT NULL,
	description TEXT,
	integration_type VARCHAR(30) NOT NULL,
	endpoint_url VARCHAR(500),
	api_version VARCHAR(20),
	auth_type VARCHAR(30),
	credentials JSONB,
	esocial_config JSONB,
	field_mapping JSONB,
	rubrica_mapping JSONB,
	sync_config JSONB,
	status VARCHAR(20) NOT NULL,
	last_sync_at TIMESTAMP WITHOUT TIME ZONE,
	last_sync_status VARCHAR(20),
	last_sync_message TEXT,
	last_sync_records INTEGER,
	total_syncs INTEGER,
	successful_syncs INTEGER,
	failed_syncs INTEGER,
	webhook_url VARCHAR(500),
	webhook_secret VARCHAR(200),
	webhook_events JSONB,
	error_log JSONB,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE,
	created_by UUID,
	ativo BOOLEAN NOT NULL,
	PRIMARY KEY (id)
);

-- tabela payroll_exports (enums: [])
CREATE TABLE IF NOT EXISTS payroll_exports (
	id UUID NOT NULL,
	condominio_id UUID NOT NULL,
	period_id UUID,
	integration_id UUID,
	export_code VARCHAR(50) NOT NULL,
	name VARCHAR(200) NOT NULL,
	description TEXT,
	export_format VARCHAR(30) NOT NULL,
	export_type VARCHAR(50),
	scope JSONB,
	file_config JSONB,
	file_name VARCHAR(255),
	file_path VARCHAR(500),
	file_size INTEGER,
	file_hash VARCHAR(64),
	status VARCHAR(20) NOT NULL,
	started_at TIMESTAMP WITHOUT TIME ZONE,
	completed_at TIMESTAMP WITHOUT TIME ZONE,
	processing_time_ms INTEGER,
	total_records INTEGER,
	processed_records INTEGER,
	success_records INTEGER,
	error_records INTEGER,
	warning_records INTEGER,
	transmission_id VARCHAR(100),
	transmission_date TIMESTAMP WITHOUT TIME ZONE,
	receipt_number VARCHAR(100),
	receipt_date TIMESTAMP WITHOUT TIME ZONE,
	errors JSONB,
	warnings JSONB,
	validation_results JSONB,
	download_url VARCHAR(500),
	download_expires_at TIMESTAMP WITHOUT TIME ZONE,
	download_count INTEGER,
	retry_count INTEGER,
	max_retries INTEGER,
	last_error TEXT,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE,
	created_by UUID,
	ativo BOOLEAN NOT NULL,
	PRIMARY KEY (id)
);

-- tabela simples_nacional_configs (enums: [])
CREATE TABLE IF NOT EXISTS simples_nacional_configs (
	id UUID NOT NULL,
	condominio_id UUID NOT NULL,
	anexo VARCHAR(10) NOT NULL,
	faixa VARCHAR(10),
	faturamento_12_meses NUMERIC(15, 2) NOT NULL,
	limite_sublimite NUMERIC(15, 2),
	aliquota_nominal NUMERIC(8, 4) NOT NULL,
	aliquota_efetiva NUMERIC(8, 4),
	parcela_deduzir NUMERIC(15, 2),
	reparticao JSONB,
	folha_pagamento_12_meses NUMERIC(15, 2),
	fator_r NUMERIC(8, 4),
	competencia VARCHAR(7) NOT NULL,
	valid_from DATE NOT NULL,
	valid_until DATE,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE,
	active BOOLEAN NOT NULL,
	PRIMARY KEY (id)
);

-- tabela sped_registros (enums: [])
CREATE TABLE IF NOT EXISTS sped_registros (
	id UUID NOT NULL,
	sped_file_id UUID NOT NULL,
	bloco VARCHAR(1) NOT NULL,
	registro VARCHAR(10) NOT NULL,
	linha INTEGER NOT NULL,
	conteudo TEXT NOT NULL,
	campos JSONB,
	documento_tipo VARCHAR(20),
	documento_id UUID,
	valido BOOLEAN,
	erro VARCHAR(255),
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id)
);

-- tabela tax_configurations (enums: [])
CREATE TABLE IF NOT EXISTS tax_configurations (
	id UUID NOT NULL,
	condominio_id UUID NOT NULL,
	name VARCHAR(100) NOT NULL,
	description TEXT,
	tax_type VARCHAR(30) NOT NULL,
	tax_regime VARCHAR(30) NOT NULL,
	calculation_type VARCHAR(30) NOT NULL,
	rate NUMERIC(8, 4),
	fixed_value NUMERIC(15, 2),
	base_reduction NUMERIC(8, 4),
	credit_rate NUMERIC(8, 4),
	icms_origin VARCHAR(1),
	icms_cst VARCHAR(3),
	icms_csosn VARCHAR(3),
	icms_modbc VARCHAR(1),
	icms_mva NUMERIC(8, 4),
	pis_cofins_regime VARCHAR(20),
	pis_cst VARCHAR(2),
	cofins_cst VARCHAR(2),
	ipi_cst VARCHAR(2),
	ipi_classe_enquadramento VARCHAR(5),
	iss_codigo_servico VARCHAR(20),
	iss_local_prestacao VARCHAR(20),
	has_retention BOOLEAN,
	retention_rate NUMERIC(8, 4),
	retention_minimum NUMERIC(15, 2),
	valid_from DATE NOT NULL,
	valid_until DATE,
	status VARCHAR(20) NOT NULL,
	special_rules JSONB,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE,
	created_by UUID,
	active BOOLEAN NOT NULL,
	PRIMARY KEY (id)
);

-- tabela tax_tables (enums: [])
CREATE TABLE IF NOT EXISTS tax_tables (
	id UUID NOT NULL,
	condominio_id UUID NOT NULL,
	name VARCHAR(100) NOT NULL,
	tax_type VARCHAR(30) NOT NULL,
	year VARCHAR(4) NOT NULL,
	valid_from DATE NOT NULL,
	valid_until DATE,
	brackets JSONB NOT NULL,
	dependent_deduction NUMERIC(15, 2),
	ceiling NUMERIC(15, 2),
	floor NUMERIC(15, 2),
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE,
	active BOOLEAN NOT NULL,
	PRIMARY KEY (id)
);

-- BALDE 1: colunas (tabelas vazias)
ALTER TABLE "codigos_servico" ADD COLUMN IF NOT EXISTS "subitem" VARCHAR(10);
ALTER TABLE "codigos_servico" ADD COLUMN IF NOT EXISTS "aliquota_minima" NUMERIC(8, 4);
ALTER TABLE "codigos_servico" ADD COLUMN IF NOT EXISTS "aliquota_maxima" NUMERIC(8, 4);
ALTER TABLE "codigos_servico" ADD COLUMN IF NOT EXISTS "iss_retido_obrigatorio" BOOLEAN;
ALTER TABLE "codigos_servico" ADD COLUMN IF NOT EXISTS "local_tributacao" VARCHAR(20);
ALTER TABLE "codigos_servico" ADD COLUMN IF NOT EXISTS "permite_deducao" BOOLEAN;
ALTER TABLE "codigos_servico" ADD COLUMN IF NOT EXISTS "exige_obra" BOOLEAN;
ALTER TABLE "codigos_servico" ADD COLUMN IF NOT EXISTS "exige_retencoes_federais" BOOLEAN;
ALTER TABLE "codigos_servico" ADD COLUMN IF NOT EXISTS "cnaes_relacionados" JSONB;
ALTER TABLE "codigos_servico" ADD COLUMN IF NOT EXISTS "created_at" TIMESTAMP WITHOUT TIME ZONE NOT NULL;
ALTER TABLE "codigos_servico" ADD COLUMN IF NOT EXISTS "updated_at" TIMESTAMP WITHOUT TIME ZONE;
ALTER TABLE "fin_stock_inventories" ADD COLUMN IF NOT EXISTS "number" VARCHAR(20) NOT NULL;
ALTER TABLE "fin_stock_inventories" ADD COLUMN IF NOT EXISTS "planned_date" DATE;
ALTER TABLE "fin_stock_inventories" ADD COLUMN IF NOT EXISTS "start_date" TIMESTAMP WITHOUT TIME ZONE;
ALTER TABLE "fin_stock_inventories" ADD COLUMN IF NOT EXISTS "end_date" TIMESTAMP WITHOUT TIME ZONE;
ALTER TABLE "fin_stock_inventories" ADD COLUMN IF NOT EXISTS "deadline" TIMESTAMP WITHOUT TIME ZONE;
ALTER TABLE "fin_stock_inventories" ADD COLUMN IF NOT EXISTS "filter_categories" JSONB;
ALTER TABLE "fin_stock_inventories" ADD COLUMN IF NOT EXISTS "filter_locations" JSONB;
ALTER TABLE "fin_stock_inventories" ADD COLUMN IF NOT EXISTS "filter_abc_class" JSONB;
ALTER TABLE "fin_stock_inventories" ADD COLUMN IF NOT EXISTS "filter_products" JSONB;
ALTER TABLE "fin_stock_inventories" ADD COLUMN IF NOT EXISTS "verified_items" INTEGER;
ALTER TABLE "fin_stock_inventories" ADD COLUMN IF NOT EXISTS "expected_value" NUMERIC(15, 2);
ALTER TABLE "fin_stock_inventories" ADD COLUMN IF NOT EXISTS "counted_value" NUMERIC(15, 2);
ALTER TABLE "fin_stock_inventories" ADD COLUMN IF NOT EXISTS "difference_value" NUMERIC(15, 2);
ALTER TABLE "fin_stock_inventories" ADD COLUMN IF NOT EXISTS "adjustment_value" NUMERIC(15, 2);
ALTER TABLE "fin_stock_inventories" ADD COLUMN IF NOT EXISTS "expected_quantity" NUMERIC(15, 4);
ALTER TABLE "fin_stock_inventories" ADD COLUMN IF NOT EXISTS "counted_quantity" NUMERIC(15, 4);
ALTER TABLE "fin_stock_inventories" ADD COLUMN IF NOT EXISTS "difference_quantity" NUMERIC(15, 4);
ALTER TABLE "fin_stock_inventories" ADD COLUMN IF NOT EXISTS "accuracy_rate" NUMERIC(5, 2);
ALTER TABLE "fin_stock_inventories" ADD COLUMN IF NOT EXISTS "hit_rate" NUMERIC(5, 2);
ALTER TABLE "fin_stock_inventories" ADD COLUMN IF NOT EXISTS "auto_adjust" BOOLEAN;
ALTER TABLE "fin_stock_inventories" ADD COLUMN IF NOT EXISTS "internal_notes" TEXT;
ALTER TABLE "fin_stock_inventories" ADD COLUMN IF NOT EXISTS "attachments" JSONB;
ALTER TABLE "fin_stock_inventories" ADD COLUMN IF NOT EXISTS "extra_data" JSONB;
ALTER TABLE "fin_stock_inventories" ADD COLUMN IF NOT EXISTS "ativo" BOOLEAN NOT NULL;
ALTER TABLE "fin_stock_inventory_items" ADD COLUMN IF NOT EXISTS "expiry_date" DATE;
ALTER TABLE "fin_stock_inventory_items" ADD COLUMN IF NOT EXISTS "aisle" VARCHAR(10);
ALTER TABLE "fin_stock_inventory_items" ADD COLUMN IF NOT EXISTS "rack" VARCHAR(10);
ALTER TABLE "fin_stock_inventory_items" ADD COLUMN IF NOT EXISTS "shelf" VARCHAR(10);
ALTER TABLE "fin_stock_inventory_items" ADD COLUMN IF NOT EXISTS "bin_loc" VARCHAR(10);
ALTER TABLE "fin_stock_inventory_items" ADD COLUMN IF NOT EXISTS "expected_quantity" NUMERIC(15, 4);
ALTER TABLE "fin_stock_inventory_items" ADD COLUMN IF NOT EXISTS "recount_quantity" NUMERIC(15, 4);
ALTER TABLE "fin_stock_inventory_items" ADD COLUMN IF NOT EXISTS "difference_quantity" NUMERIC(15, 4);
ALTER TABLE "fin_stock_inventory_items" ADD COLUMN IF NOT EXISTS "expected_value" NUMERIC(15, 2);
ALTER TABLE "fin_stock_inventory_items" ADD COLUMN IF NOT EXISTS "difference_value" NUMERIC(15, 2);
ALTER TABLE "fin_stock_inventory_items" ADD COLUMN IF NOT EXISTS "recounted_at" TIMESTAMP WITHOUT TIME ZONE;
ALTER TABLE "fin_stock_inventory_items" ADD COLUMN IF NOT EXISTS "recounted_by" UUID;
ALTER TABLE "fin_stock_inventory_items" ADD COLUMN IF NOT EXISTS "verified_at" TIMESTAMP WITHOUT TIME ZONE;
ALTER TABLE "fin_stock_inventory_items" ADD COLUMN IF NOT EXISTS "verified_by" UUID;
ALTER TABLE "fin_stock_inventory_items" ADD COLUMN IF NOT EXISTS "adjusted_at" TIMESTAMP WITHOUT TIME ZONE;
ALTER TABLE "fin_stock_inventory_items" ADD COLUMN IF NOT EXISTS "adjusted_by" UUID;
ALTER TABLE "fin_stock_inventory_items" ADD COLUMN IF NOT EXISTS "ativo" BOOLEAN NOT NULL;
ALTER TABLE "fin_stock_movements" ADD COLUMN IF NOT EXISTS "number" VARCHAR(20) NOT NULL;
ALTER TABLE "fin_stock_movements" ADD COLUMN IF NOT EXISTS "reason" VARCHAR(30) NOT NULL;
ALTER TABLE "fin_stock_movements" ADD COLUMN IF NOT EXISTS "expiry_date" DATE;
ALTER TABLE "fin_stock_movements" ADD COLUMN IF NOT EXISTS "source_location" VARCHAR(50);
ALTER TABLE "fin_stock_movements" ADD COLUMN IF NOT EXISTS "source_aisle" VARCHAR(10);
ALTER TABLE "fin_stock_movements" ADD COLUMN IF NOT EXISTS "source_rack" VARCHAR(10);
ALTER TABLE "fin_stock_movements" ADD COLUMN IF NOT EXISTS "source_shelf" VARCHAR(10);
ALTER TABLE "fin_stock_movements" ADD COLUMN IF NOT EXISTS "source_bin" VARCHAR(10);
ALTER TABLE "fin_stock_movements" ADD COLUMN IF NOT EXISTS "dest_location" VARCHAR(50);
ALTER TABLE "fin_stock_movements" ADD COLUMN IF NOT EXISTS "dest_aisle" VARCHAR(10);
ALTER TABLE "fin_stock_movements" ADD COLUMN IF NOT EXISTS "dest_rack" VARCHAR(10);
ALTER TABLE "fin_stock_movements" ADD COLUMN IF NOT EXISTS "dest_shelf" VARCHAR(10);
ALTER TABLE "fin_stock_movements" ADD COLUMN IF NOT EXISTS "dest_bin" VARCHAR(10);
ALTER TABLE "fin_stock_movements" ADD COLUMN IF NOT EXISTS "reference_type" VARCHAR(50);
ALTER TABLE "fin_stock_movements" ADD COLUMN IF NOT EXISTS "reference_id" UUID;
ALTER TABLE "fin_stock_movements" ADD COLUMN IF NOT EXISTS "reference_number" VARCHAR(50);
ALTER TABLE "fin_stock_movements" ADD COLUMN IF NOT EXISTS "invoice_number" VARCHAR(50);
ALTER TABLE "fin_stock_movements" ADD COLUMN IF NOT EXISTS "invoice_series" VARCHAR(10);
ALTER TABLE "fin_stock_movements" ADD COLUMN IF NOT EXISTS "invoice_key" VARCHAR(50);
ALTER TABLE "fin_stock_movements" ADD COLUMN IF NOT EXISTS "supplier_id" UUID;
ALTER TABLE "fin_stock_movements" ADD COLUMN IF NOT EXISTS "customer_id" UUID;
ALTER TABLE "fin_stock_movements" ADD COLUMN IF NOT EXISTS "requisition_id" UUID;
ALTER TABLE "fin_stock_movements" ADD COLUMN IF NOT EXISTS "requisition_number" VARCHAR(50);
ALTER TABLE "fin_stock_movements" ADD COLUMN IF NOT EXISTS "reversal_of" UUID;
ALTER TABLE "fin_stock_movements" ADD COLUMN IF NOT EXISTS "reversed_by" UUID;
ALTER TABLE "fin_stock_movements" ADD COLUMN IF NOT EXISTS "internal_notes" TEXT;
ALTER TABLE "fin_stock_movements" ADD COLUMN IF NOT EXISTS "attachments" JSONB;
ALTER TABLE "fin_stock_movements" ADD COLUMN IF NOT EXISTS "extra_data" JSONB;
ALTER TABLE "fin_stock_movements" ADD COLUMN IF NOT EXISTS "confirmed_by" UUID;
ALTER TABLE "fin_stock_movements" ADD COLUMN IF NOT EXISTS "ativo" BOOLEAN NOT NULL;
ALTER TABLE "fin_stock_reservations" ADD COLUMN IF NOT EXISTS "number" VARCHAR(20) NOT NULL;
ALTER TABLE "fin_stock_reservations" ADD COLUMN IF NOT EXISTS "description" VARCHAR(200);
ALTER TABLE "fin_stock_reservations" ADD COLUMN IF NOT EXISTS "batch_number" VARCHAR(50);
ALTER TABLE "fin_stock_reservations" ADD COLUMN IF NOT EXISTS "quantity_requested" NUMERIC(15, 4) NOT NULL;
ALTER TABLE "fin_stock_reservations" ADD COLUMN IF NOT EXISTS "quantity_pending" NUMERIC(15, 4);
ALTER TABLE "fin_stock_reservations" ADD COLUMN IF NOT EXISTS "required_date" TIMESTAMP WITHOUT TIME ZONE;
ALTER TABLE "fin_stock_reservations" ADD COLUMN IF NOT EXISTS "reference_type" VARCHAR(50);
ALTER TABLE "fin_stock_reservations" ADD COLUMN IF NOT EXISTS "reference_id" UUID;
ALTER TABLE "fin_stock_reservations" ADD COLUMN IF NOT EXISTS "reference_number" VARCHAR(50);
ALTER TABLE "fin_stock_reservations" ADD COLUMN IF NOT EXISTS "requester_id" UUID;
ALTER TABLE "fin_stock_reservations" ADD COLUMN IF NOT EXISTS "requester_name" VARCHAR(100);
ALTER TABLE "fin_stock_reservations" ADD COLUMN IF NOT EXISTS "requires_approval" BOOLEAN;
ALTER TABLE "fin_stock_reservations" ADD COLUMN IF NOT EXISTS "approved_by" UUID;
ALTER TABLE "fin_stock_reservations" ADD COLUMN IF NOT EXISTS "approved_at" TIMESTAMP WITHOUT TIME ZONE;
ALTER TABLE "fin_stock_reservations" ADD COLUMN IF NOT EXISTS "approval_notes" TEXT;
ALTER TABLE "fin_stock_reservations" ADD COLUMN IF NOT EXISTS "released_by" UUID;
ALTER TABLE "fin_stock_reservations" ADD COLUMN IF NOT EXISTS "release_notes" TEXT;
ALTER TABLE "fin_stock_reservations" ADD COLUMN IF NOT EXISTS "cancelled_by" UUID;
ALTER TABLE "fin_stock_reservations" ADD COLUMN IF NOT EXISTS "auto_expire" BOOLEAN;
ALTER TABLE "fin_stock_reservations" ADD COLUMN IF NOT EXISTS "allow_partial" BOOLEAN;
ALTER TABLE "fin_stock_reservations" ADD COLUMN IF NOT EXISTS "internal_notes" TEXT;
ALTER TABLE "fin_stock_reservations" ADD COLUMN IF NOT EXISTS "extra_data" JSONB;
ALTER TABLE "fin_stock_reservations" ADD COLUMN IF NOT EXISTS "ativo" BOOLEAN NOT NULL;
ALTER TABLE "goods_receipt_items" ADD COLUMN IF NOT EXISTS "updated_at" TIMESTAMP WITHOUT TIME ZONE;
ALTER TABLE "goods_receipts" ADD COLUMN IF NOT EXISTS "approval_notes" TEXT;
ALTER TABLE "goods_receipts" ADD COLUMN IF NOT EXISTS "rejected_at" TIMESTAMP WITHOUT TIME ZONE;
ALTER TABLE "goods_receipts" ADD COLUMN IF NOT EXISTS "rejected_by" UUID;
ALTER TABLE "goods_receipts" ADD COLUMN IF NOT EXISTS "internal_notes" TEXT;
ALTER TABLE "goods_receipts" ADD COLUMN IF NOT EXISTS "receiver_signature" TEXT;
ALTER TABLE "payable_categories" ADD COLUMN IF NOT EXISTS "created_by" UUID;
ALTER TABLE "payment_methods" ADD COLUMN IF NOT EXISTS "created_by" UUID;
ALTER TABLE "products" ADD COLUMN IF NOT EXISTS "technical_specs" TEXT;
ALTER TABLE "products" ADD COLUMN IF NOT EXISTS "conversion_factor" NUMERIC(10, 4);
ALTER TABLE "products" ADD COLUMN IF NOT EXISTS "min_stock" NUMERIC(10, 2);
ALTER TABLE "products" ADD COLUMN IF NOT EXISTS "max_stock" NUMERIC(10, 2);
ALTER TABLE "products" ADD COLUMN IF NOT EXISTS "cest" VARCHAR(10);
ALTER TABLE "products" ADD COLUMN IF NOT EXISTS "cfop_default" VARCHAR(10);
ALTER TABLE "products" ADD COLUMN IF NOT EXISTS "preferred_supplier_id" UUID;
ALTER TABLE "products" ADD COLUMN IF NOT EXISTS "thumbnail_url" VARCHAR(500);
ALTER TABLE "products" ADD COLUMN IF NOT EXISTS "documents" JSONB;
ALTER TABLE "products" ADD COLUMN IF NOT EXISTS "attributes" JSONB;
ALTER TABLE "products" ADD COLUMN IF NOT EXISTS "brand" VARCHAR(100);
ALTER TABLE "products" ADD COLUMN IF NOT EXISTS "manufacturer" VARCHAR(100);
ALTER TABLE "products" ADD COLUMN IF NOT EXISTS "model" VARCHAR(100);
ALTER TABLE "products" ADD COLUMN IF NOT EXISTS "internal_notes" TEXT;
ALTER TABLE "products" ADD COLUMN IF NOT EXISTS "blocked_reason" TEXT;
ALTER TABLE "products" ADD COLUMN IF NOT EXISTS "total_purchases" VARCHAR(10);
ALTER TABLE "products" ADD COLUMN IF NOT EXISTS "last_purchase_at" TIMESTAMP WITHOUT TIME ZONE;
ALTER TABLE "purchase_approvals" ADD COLUMN IF NOT EXISTS "info_requested_at" TIMESTAMP WITHOUT TIME ZONE;
ALTER TABLE "purchase_approvals" ADD COLUMN IF NOT EXISTS "info_provided_at" TIMESTAMP WITHOUT TIME ZONE;
ALTER TABLE "purchase_approvals" ADD COLUMN IF NOT EXISTS "notification_sent_at" TIMESTAMP WITHOUT TIME ZONE;
ALTER TABLE "purchase_approvals" ADD COLUMN IF NOT EXISTS "last_reminder_at" TIMESTAMP WITHOUT TIME ZONE;
ALTER TABLE "purchase_approvals" ADD COLUMN IF NOT EXISTS "attachments" JSONB;
ALTER TABLE "purchase_approvals" ADD COLUMN IF NOT EXISTS "created_by" UUID;
ALTER TABLE "purchase_order_items" ADD COLUMN IF NOT EXISTS "updated_at" TIMESTAMP WITHOUT TIME ZONE;
ALTER TABLE "purchase_quotation_items" ADD COLUMN IF NOT EXISTS "supplier_description" VARCHAR(500);
ALTER TABLE "purchase_quotation_items" ADD COLUMN IF NOT EXISTS "quantity_requested" NUMERIC(10, 2) NOT NULL;
ALTER TABLE "purchase_quotation_items" ADD COLUMN IF NOT EXISTS "quantity_offered" NUMERIC(10, 2);
ALTER TABLE "purchase_quotation_items" ADD COLUMN IF NOT EXISTS "min_quantity" NUMERIC(10, 2);
ALTER TABLE "purchase_quotation_items" ADD COLUMN IF NOT EXISTS "discount_percentage" NUMERIC(5, 2);
ALTER TABLE "purchase_quotation_items" ADD COLUMN IF NOT EXISTS "discount_amount" NUMERIC(15, 2);
ALTER TABLE "purchase_quotation_items" ADD COLUMN IF NOT EXISTS "availability" VARCHAR(50);
ALTER TABLE "purchase_quotation_items" ADD COLUMN IF NOT EXISTS "technical_specs" TEXT;
ALTER TABLE "purchase_quotation_items" ADD COLUMN IF NOT EXISTS "meets_specs" BOOLEAN;
ALTER TABLE "purchase_quotation_items" ADD COLUMN IF NOT EXISTS "evaluation_notes" TEXT;
ALTER TABLE "purchase_quotation_items" ADD COLUMN IF NOT EXISTS "updated_at" TIMESTAMP WITHOUT TIME ZONE;
ALTER TABLE "purchase_quotations" ADD COLUMN IF NOT EXISTS "reference" VARCHAR(50);
ALTER TABLE "purchase_quotations" ADD COLUMN IF NOT EXISTS "request_date" DATE NOT NULL;
ALTER TABLE "purchase_quotations" ADD COLUMN IF NOT EXISTS "sent_date" TIMESTAMP WITHOUT TIME ZONE;
ALTER TABLE "purchase_quotations" ADD COLUMN IF NOT EXISTS "received_date" TIMESTAMP WITHOUT TIME ZONE;
ALTER TABLE "purchase_quotations" ADD COLUMN IF NOT EXISTS "validity_date" DATE;
ALTER TABLE "purchase_quotations" ADD COLUMN IF NOT EXISTS "expected_delivery_date" DATE;
ALTER TABLE "purchase_quotations" ADD COLUMN IF NOT EXISTS "payment_installments" INTEGER;
ALTER TABLE "purchase_quotations" ADD COLUMN IF NOT EXISTS "internal_notes" TEXT;
ALTER TABLE "purchase_quotations" ADD COLUMN IF NOT EXISTS "rejected_at" TIMESTAMP WITHOUT TIME ZONE;
ALTER TABLE "purchase_quotations" ADD COLUMN IF NOT EXISTS "rejected_by" UUID;
ALTER TABLE "purchase_quotations" ADD COLUMN IF NOT EXISTS "selection_justification" TEXT;
ALTER TABLE "purchase_quotations" ADD COLUMN IF NOT EXISTS "comparison_notes" TEXT;
ALTER TABLE "purchase_quotations" ADD COLUMN IF NOT EXISTS "is_best_price" BOOLEAN;
ALTER TABLE "purchase_quotations" ADD COLUMN IF NOT EXISTS "is_best_delivery" BOOLEAN;
ALTER TABLE "purchase_quotations" ADD COLUMN IF NOT EXISTS "is_best_overall" BOOLEAN;
ALTER TABLE "purchase_requisition_items" ADD COLUMN IF NOT EXISTS "quantity_requested" NUMERIC(10, 2) NOT NULL;
ALTER TABLE "purchase_requisition_items" ADD COLUMN IF NOT EXISTS "quantity_received" NUMERIC(10, 2);
ALTER TABLE "purchase_requisition_items" ADD COLUMN IF NOT EXISTS "estimated_unit_price" NUMERIC(15, 2);
ALTER TABLE "purchase_requisition_items" ADD COLUMN IF NOT EXISTS "approved_unit_price" NUMERIC(15, 2);
ALTER TABLE "purchase_requisition_items" ADD COLUMN IF NOT EXISTS "actual_unit_price" NUMERIC(15, 2);
ALTER TABLE "purchase_requisition_items" ADD COLUMN IF NOT EXISTS "updated_at" TIMESTAMP WITHOUT TIME ZONE;
ALTER TABLE "purchase_requisitions" ADD COLUMN IF NOT EXISTS "revision" INTEGER;
ALTER TABLE "purchase_requisitions" ADD COLUMN IF NOT EXISTS "title" VARCHAR(200) NOT NULL;
ALTER TABLE "purchase_requisitions" ADD COLUMN IF NOT EXISTS "request_date" DATE NOT NULL;
ALTER TABLE "purchase_requisitions" ADD COLUMN IF NOT EXISTS "needed_by_date" DATE;
ALTER TABLE "purchase_requisitions" ADD COLUMN IF NOT EXISTS "approved_at" TIMESTAMP WITHOUT TIME ZONE;
ALTER TABLE "purchase_requisitions" ADD COLUMN IF NOT EXISTS "approved_budget" NUMERIC(15, 2);
ALTER TABLE "purchase_requisitions" ADD COLUMN IF NOT EXISTS "actual_total" NUMERIC(15, 2);
ALTER TABLE "purchase_requisitions" ADD COLUMN IF NOT EXISTS "min_quotations" INTEGER;
ALTER TABLE "purchase_requisitions" ADD COLUMN IF NOT EXISTS "delivery_address" TEXT;
ALTER TABLE "purchase_requisitions" ADD COLUMN IF NOT EXISTS "delivery_contact" VARCHAR(100);
ALTER TABLE "purchase_requisitions" ADD COLUMN IF NOT EXISTS "delivery_phone" VARCHAR(20);
ALTER TABLE "purchase_requisitions" ADD COLUMN IF NOT EXISTS "delivery_instructions" TEXT;
ALTER TABLE "purchase_requisitions" ADD COLUMN IF NOT EXISTS "suggested_supplier_id" UUID;
ALTER TABLE "purchase_requisitions" ADD COLUMN IF NOT EXISTS "supplier_justification" TEXT;
ALTER TABLE "purchase_requisitions" ADD COLUMN IF NOT EXISTS "internal_notes" TEXT;
ALTER TABLE "purchase_requisitions" ADD COLUMN IF NOT EXISTS "rejected_at" TIMESTAMP WITHOUT TIME ZONE;
ALTER TABLE "purchase_requisitions" ADD COLUMN IF NOT EXISTS "cancelled_at" TIMESTAMP WITHOUT TIME ZONE;
ALTER TABLE "purchase_requisitions" ADD COLUMN IF NOT EXISTS "cancelled_by" UUID;
ALTER TABLE "purchase_requisitions" ADD COLUMN IF NOT EXISTS "approval_history" JSONB;
ALTER TABLE "receivable_categories" ADD COLUMN IF NOT EXISTS "apply_interest" BOOLEAN;
ALTER TABLE "receivable_categories" ADD COLUMN IF NOT EXISTS "interest_rate" VARCHAR(10);
ALTER TABLE "receivable_categories" ADD COLUMN IF NOT EXISTS "apply_penalty" BOOLEAN;
ALTER TABLE "receivable_categories" ADD COLUMN IF NOT EXISTS "penalty_rate" VARCHAR(10);
ALTER TABLE "simples_nacional_das" ADD COLUMN IF NOT EXISTS "competencia" VARCHAR(7) NOT NULL;
ALTER TABLE "simples_nacional_das" ADD COLUMN IF NOT EXISTS "ano" INTEGER NOT NULL;
ALTER TABLE "simples_nacional_das" ADD COLUMN IF NOT EXISTS "mes" INTEGER NOT NULL;
ALTER TABLE "simples_nacional_das" ADD COLUMN IF NOT EXISTS "fator_r" NUMERIC(8, 4);
ALTER TABLE "simples_nacional_das" ADD COLUMN IF NOT EXISTS "folha_pagamento_12_meses" NUMERIC(15, 2);
ALTER TABLE "simples_nacional_das" ADD COLUMN IF NOT EXISTS "valor_das" NUMERIC(15, 2) NOT NULL;
ALTER TABLE "simples_nacional_das" ADD COLUMN IF NOT EXISTS "reparticao" JSONB;
ALTER TABLE "simples_nacional_das" ADD COLUMN IF NOT EXISTS "valor_irpj" NUMERIC(15, 2);
ALTER TABLE "simples_nacional_das" ADD COLUMN IF NOT EXISTS "valor_csll" NUMERIC(15, 2);
ALTER TABLE "simples_nacional_das" ADD COLUMN IF NOT EXISTS "valor_cofins" NUMERIC(15, 2);
ALTER TABLE "simples_nacional_das" ADD COLUMN IF NOT EXISTS "valor_pis" NUMERIC(15, 2);
ALTER TABLE "simples_nacional_das" ADD COLUMN IF NOT EXISTS "valor_cpp" NUMERIC(15, 2);
ALTER TABLE "simples_nacional_das" ADD COLUMN IF NOT EXISTS "valor_icms" NUMERIC(15, 2);
ALTER TABLE "simples_nacional_das" ADD COLUMN IF NOT EXISTS "valor_iss" NUMERIC(15, 2);
ALTER TABLE "simples_nacional_das" ADD COLUMN IF NOT EXISTS "numero_das" VARCHAR(30);
ALTER TABLE "simples_nacional_das" ADD COLUMN IF NOT EXISTS "iss_retido" BOOLEAN;
ALTER TABLE "simples_nacional_das" ADD COLUMN IF NOT EXISTS "valor_iss_retido" NUMERIC(15, 2);
ALTER TABLE "sped_files" ADD COLUMN IF NOT EXISTS "versao_layout" VARCHAR(10) NOT NULL;
ALTER TABLE "sped_files" ADD COLUMN IF NOT EXISTS "periodo_inicio" DATE NOT NULL;
ALTER TABLE "sped_files" ADD COLUMN IF NOT EXISTS "periodo_fim" DATE NOT NULL;
ALTER TABLE "sped_files" ADD COLUMN IF NOT EXISTS "data_geracao" TIMESTAMP WITHOUT TIME ZONE;
ALTER TABLE "sped_files" ADD COLUMN IF NOT EXISTS "data_validacao" TIMESTAMP WITHOUT TIME ZONE;
ALTER TABLE "sped_files" ADD COLUMN IF NOT EXISTS "cnpj" VARCHAR(14) NOT NULL;
ALTER TABLE "sped_files" ADD COLUMN IF NOT EXISTS "razao_social" VARCHAR(150) NOT NULL;
ALTER TABLE "sped_files" ADD COLUMN IF NOT EXISTS "inscricao_estadual" VARCHAR(14);
ALTER TABLE "sped_files" ADD COLUMN IF NOT EXISTS "uf" VARCHAR(2);
ALTER TABLE "sped_files" ADD COLUMN IF NOT EXISTS "caminho_arquivo" VARCHAR(500);
ALTER TABLE "sped_files" ADD COLUMN IF NOT EXISTS "pva_versao" VARCHAR(20);
ALTER TABLE "sped_files" ADD COLUMN IF NOT EXISTS "pva_resultado" VARCHAR(20);
ALTER TABLE "sped_files" ADD COLUMN IF NOT EXISTS "pva_erros" INTEGER;
ALTER TABLE "sped_files" ADD COLUMN IF NOT EXISTS "pva_avisos" INTEGER;
ALTER TABLE "sped_files" ADD COLUMN IF NOT EXISTS "pva_log" TEXT;
ALTER TABLE "sped_files" ADD COLUMN IF NOT EXISTS "protocolo" VARCHAR(50);
ALTER TABLE "sped_files" ADD COLUMN IF NOT EXISTS "recibo" VARCHAR(50);
ALTER TABLE "sped_files" ADD COLUMN IF NOT EXISTS "codigo_retorno" VARCHAR(10);
ALTER TABLE "sped_files" ADD COLUMN IF NOT EXISTS "mensagem_retorno" TEXT;
ALTER TABLE "sped_files" ADD COLUMN IF NOT EXISTS "sped_retificado_id" UUID;
ALTER TABLE "sped_files" ADD COLUMN IF NOT EXISTS "nire" VARCHAR(20);
ALTER TABLE "sped_files" ADD COLUMN IF NOT EXISTS "estatisticas" JSONB;
ALTER TABLE "sped_files" ADD COLUMN IF NOT EXISTS "valores_resumo" JSONB;
ALTER TABLE "sped_files" ADD COLUMN IF NOT EXISTS "created_by" UUID;
ALTER TABLE "suframa_configs" ADD COLUMN IF NOT EXISTS "tipo_zona" VARCHAR(20) NOT NULL;
ALTER TABLE "suframa_configs" ADD COLUMN IF NOT EXISTS "status" VARCHAR(20) NOT NULL;
ALTER TABLE "suframa_configs" ADD COLUMN IF NOT EXISTS "data_inscricao" DATE;
ALTER TABLE "suframa_configs" ADD COLUMN IF NOT EXISTS "cnpj" VARCHAR(14) NOT NULL;
ALTER TABLE "suframa_configs" ADD COLUMN IF NOT EXISTS "razao_social" VARCHAR(150) NOT NULL;
ALTER TABLE "suframa_configs" ADD COLUMN IF NOT EXISTS "nome_fantasia" VARCHAR(60);
ALTER TABLE "suframa_configs" ADD COLUMN IF NOT EXISTS "endereco" JSONB;
ALTER TABLE "suframa_configs" ADD COLUMN IF NOT EXISTS "codigo_municipio" VARCHAR(7);
ALTER TABLE "suframa_configs" ADD COLUMN IF NOT EXISTS "municipio_nome" VARCHAR(100);
ALTER TABLE "suframa_configs" ADD COLUMN IF NOT EXISTS "uf" VARCHAR(2) NOT NULL;
ALTER TABLE "suframa_configs" ADD COLUMN IF NOT EXISTS "cnaes_habilitados" JSONB;
ALTER TABLE "suframa_configs" ADD COLUMN IF NOT EXISTS "beneficio_ipi" BOOLEAN;
ALTER TABLE "suframa_configs" ADD COLUMN IF NOT EXISTS "beneficio_icms" BOOLEAN;
ALTER TABLE "suframa_configs" ADD COLUMN IF NOT EXISTS "beneficio_pis_cofins" BOOLEAN;
ALTER TABLE "suframa_configs" ADD COLUMN IF NOT EXISTS "beneficio_ii" BOOLEAN;
ALTER TABLE "suframa_configs" ADD COLUMN IF NOT EXISTS "reducao_icms_interno" NUMERIC(8, 4);
ALTER TABLE "suframa_configs" ADD COLUMN IF NOT EXISTS "reducao_icms_interestadual" NUMERIC(8, 4);
ALTER TABLE "suframa_configs" ADD COLUMN IF NOT EXISTS "credito_presumido_icms" NUMERIC(8, 4);
ALTER TABLE "suframa_configs" ADD COLUMN IF NOT EXISTS "simples_nacional" BOOLEAN;
ALTER TABLE "suframa_configs" ADD COLUMN IF NOT EXISTS "simples_anexo" VARCHAR(5);
ALTER TABLE "suframa_configs" ADD COLUMN IF NOT EXISTS "simples_faixa" VARCHAR(5);
ALTER TABLE "suframa_configs" ADD COLUMN IF NOT EXISTS "documentos" JSONB;
ALTER TABLE "suframa_configs" ADD COLUMN IF NOT EXISTS "created_by" UUID;
ALTER TABLE "suframa_operacoes" ADD COLUMN IF NOT EXISTS "suframa_config_id" UUID NOT NULL;
ALTER TABLE "suframa_operacoes" ADD COLUMN IF NOT EXISTS "documento_tipo" VARCHAR(10) NOT NULL;
ALTER TABLE "suframa_operacoes" ADD COLUMN IF NOT EXISTS "documento_id" UUID NOT NULL;
ALTER TABLE "suframa_operacoes" ADD COLUMN IF NOT EXISTS "chave_acesso" VARCHAR(44);
ALTER TABLE "suframa_operacoes" ADD COLUMN IF NOT EXISTS "numero_documento" VARCHAR(20);
ALTER TABLE "suframa_operacoes" ADD COLUMN IF NOT EXISTS "participante_cnpj" VARCHAR(14) NOT NULL;
ALTER TABLE "suframa_operacoes" ADD COLUMN IF NOT EXISTS "participante_suframa" VARCHAR(20);
ALTER TABLE "suframa_operacoes" ADD COLUMN IF NOT EXISTS "participante_razao_social" VARCHAR(150);
ALTER TABLE "suframa_operacoes" ADD COLUMN IF NOT EXISTS "cfop" VARCHAR(4) NOT NULL;
ALTER TABLE "suframa_operacoes" ADD COLUMN IF NOT EXISTS "valor_produtos" NUMERIC(15, 2) NOT NULL;
ALTER TABLE "suframa_operacoes" ADD COLUMN IF NOT EXISTS "ipi_isento" BOOLEAN;
ALTER TABLE "suframa_operacoes" ADD COLUMN IF NOT EXISTS "ipi_economia" NUMERIC(15, 2);
ALTER TABLE "suframa_operacoes" ADD COLUMN IF NOT EXISTS "icms_isento" BOOLEAN;
ALTER TABLE "suframa_operacoes" ADD COLUMN IF NOT EXISTS "icms_reducao_percentual" NUMERIC(8, 4);
ALTER TABLE "suframa_operacoes" ADD COLUMN IF NOT EXISTS "icms_economia" NUMERIC(15, 2);
ALTER TABLE "suframa_operacoes" ADD COLUMN IF NOT EXISTS "pis_suspenso" BOOLEAN;
ALTER TABLE "suframa_operacoes" ADD COLUMN IF NOT EXISTS "pis_economia" NUMERIC(15, 2);
ALTER TABLE "suframa_operacoes" ADD COLUMN IF NOT EXISTS "cofins_suspenso" BOOLEAN;
ALTER TABLE "suframa_operacoes" ADD COLUMN IF NOT EXISTS "cofins_economia" NUMERIC(15, 2);
ALTER TABLE "suframa_operacoes" ADD COLUMN IF NOT EXISTS "total_economia" NUMERIC(15, 2);
ALTER TABLE "suframa_operacoes" ADD COLUMN IF NOT EXISTS "pin_numero" VARCHAR(50);
ALTER TABLE "suframa_operacoes" ADD COLUMN IF NOT EXISTS "pin_data" DATE;
ALTER TABLE "suframa_operacoes" ADD COLUMN IF NOT EXISTS "pin_status" VARCHAR(20);
ALTER TABLE "suframa_operacoes" ADD COLUMN IF NOT EXISTS "internamento_data" DATE;
ALTER TABLE "suframa_operacoes" ADD COLUMN IF NOT EXISTS "internamento_protocolo" VARCHAR(50);
ALTER TABLE "suframa_operacoes" ADD COLUMN IF NOT EXISTS "updated_at" TIMESTAMP WITHOUT TIME ZONE;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "employee_registration" VARCHAR(50);
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "weekly_hours_minutes" INTEGER NOT NULL;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "daily_hours_minutes" INTEGER NOT NULL;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "max_daily_hours_minutes" INTEGER NOT NULL;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "default_entry_time" TIME WITHOUT TIME ZONE;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "default_exit_time" TIME WITHOUT TIME ZONE;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "default_break_start" TIME WITHOUT TIME ZONE;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "default_break_end" TIME WITHOUT TIME ZONE;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "daily_schedule" JSONB;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "work_days" VARCHAR[];
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "days_off" VARCHAR[];
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "entry_tolerance_minutes" INTEGER NOT NULL;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "exit_tolerance_minutes" INTEGER NOT NULL;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "break_tolerance_minutes" INTEGER NOT NULL;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "overtime_requires_approval" BOOLEAN NOT NULL;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "max_overtime_daily_minutes" INTEGER NOT NULL;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "max_overtime_weekly_minutes" INTEGER NOT NULL;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "overtime_multiplier_50" NUMERIC(4, 2) NOT NULL;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "overtime_multiplier_100" NUMERIC(4, 2) NOT NULL;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "use_time_bank" BOOLEAN NOT NULL;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "night_shift_multiplier" NUMERIC(4, 2) NOT NULL;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "night_hour_reduction" BOOLEAN NOT NULL;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "min_break_4h_minutes" INTEGER NOT NULL;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "min_break_6h_minutes" INTEGER NOT NULL;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "min_rest_between_shifts_hours" INTEGER NOT NULL;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "time_bank_expiry_months" INTEGER NOT NULL;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "time_bank_max_positive_hours" INTEGER NOT NULL;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "time_bank_max_negative_hours" INTEGER NOT NULL;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "require_geolocation" BOOLEAN NOT NULL;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "max_distance_meters" INTEGER NOT NULL;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "require_biometric" BOOLEAN NOT NULL;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "min_biometric_score" INTEGER NOT NULL;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "require_face_match" BOOLEAN NOT NULL;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "require_liveness" BOOLEAN NOT NULL;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "consider_holidays" BOOLEAN NOT NULL;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "holiday_calendar_id" VARCHAR(50);
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "collective_agreement_id" VARCHAR(50);
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "collective_agreement_name" VARCHAR(200);
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "valid_from" DATE;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "valid_until" DATE;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "notes" TEXT;
ALTER TABLE "work_schedules" ADD COLUMN IF NOT EXISTS "tags" JSONB;
COMMIT;
