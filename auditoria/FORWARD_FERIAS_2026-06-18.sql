-- FORWARD FERIAS: cria portal + migra 67 periodos + 15 requests (preserva legado) 2026-06-18
BEGIN;
CREATE TABLE IF NOT EXISTS employee_vacation_periods (
	id UUID NOT NULL,
	condominio_id UUID NOT NULL,
	employee_id UUID NOT NULL,
	start_date DATE NOT NULL,
	end_date DATE NOT NULL,
	concession_start DATE NOT NULL,
	concession_end DATE NOT NULL,
	total_days_entitled INTEGER NOT NULL,
	days_used INTEGER NOT NULL,
	days_sold INTEGER NOT NULL,
	days_remaining INTEGER NOT NULL,
	absences_count INTEGER NOT NULL,
	is_expired BOOLEAN,
	is_fully_used BOOLEAN,
	double_payment BOOLEAN,
	expires_at DATE,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE,
	PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS employee_vacation_requests (
	id UUID NOT NULL,
	condominio_id UUID NOT NULL,
	employee_id UUID NOT NULL,
	vacation_period_id UUID,
	request_code VARCHAR(30) NOT NULL,
	vacation_type VARCHAR(20) NOT NULL,
	status VARCHAR(20) NOT NULL,
	start_date DATE NOT NULL,
	end_date DATE NOT NULL,
	days_requested INTEGER NOT NULL,
	sell_days INTEGER,
	sell_requested BOOLEAN,
	advance_13th_requested BOOLEAN,
	advance_13th_approved BOOLEAN,
	vacation_salary NUMERIC(15, 2),
	vacation_bonus NUMERIC(15, 2),
	sell_value NUMERIC(15, 2),
	advance_13th_value NUMERIC(15, 2),
	inss_deduction NUMERIC(15, 2),
	irrf_deduction NUMERIC(15, 2),
	other_deductions NUMERIC(15, 2),
	net_value NUMERIC(15, 2),
	calculation_details JSONB,
	employee_notes TEXT,
	manager_notes TEXT,
	hr_notes TEXT,
	submitted_at TIMESTAMP WITHOUT TIME ZONE,
	manager_approved BOOLEAN,
	manager_approved_at TIMESTAMP WITHOUT TIME ZONE,
	manager_approved_by UUID,
	manager_rejection_reason TEXT,
	hr_approved BOOLEAN,
	hr_approved_at TIMESTAMP WITHOUT TIME ZONE,
	hr_approved_by UUID,
	hr_rejection_reason TEXT,
	scheduled_at TIMESTAMP WITHOUT TIME ZONE,
	scheduled_by UUID,
	cancelled_at TIMESTAMP WITHOUT TIME ZONE,
	cancelled_by UUID,
	cancel_reason TEXT,
	interrupted_at TIMESTAMP WITHOUT TIME ZONE,
	interrupted_by UUID,
	interrupt_reason TEXT,
	days_enjoyed_before_interrupt INTEGER,
	return_date DATE,
	actual_return_date DATE,
	payment_date DATE,
	paid_at TIMESTAMP WITHOUT TIME ZONE,
	payslip_id UUID,
	substitute_employee_id UUID,
	substitute_name VARCHAR(200),
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE,
	created_by UUID,
	PRIMARY KEY (id),
	CONSTRAINT ck_vacation_min_days CHECK (days_requested >= 5),
	CONSTRAINT ck_vacation_max_days CHECK (days_requested <= 30),
	CONSTRAINT ck_vacation_max_sell CHECK (sell_days <= 10),
	CONSTRAINT ck_vacation_dates CHECK (end_date >= start_date)
);
ALTER TABLE employee_vacation_periods ALTER COLUMN concession_start DROP NOT NULL;
ALTER TABLE employee_vacation_periods ALTER COLUMN concession_end DROP NOT NULL;
ALTER TABLE employee_vacation_requests ALTER COLUMN vacation_type DROP NOT NULL;
INSERT INTO employee_vacation_periods
 (id,condominio_id,employee_id,start_date,end_date,concession_start,concession_end,
  total_days_entitled,days_used,days_sold,days_remaining,absences_count,
  is_expired,is_fully_used,double_payment,expires_at,created_at,updated_at)
SELECT id,condominio_id,employee_id,start_date,end_date,NULL,NULL,
  days_entitled,days_used,days_sold,days_remaining,absences_count,
  is_expired,is_fully_used,false,limit_date,created_at,updated_at
FROM hr_vacation_periods
ON CONFLICT (id) DO NOTHING;
INSERT INTO employee_vacation_requests
 (id,condominio_id,employee_id,vacation_period_id,request_code,vacation_type,status,
  start_date,end_date,days_requested,sell_days,advance_13th_requested,
  net_value,calculation_details,employee_notes,manager_notes,hr_notes,
  submitted_at,manager_approved,manager_approved_at,manager_approved_by,
  hr_approved,hr_approved_at,hr_approved_by,cancelled_at,cancelled_by,cancel_reason,
  interrupted_at,interrupt_reason,return_date,actual_return_date,created_at,updated_at,created_by)
SELECT id,condominio_id,employee_id,period_id,request_code,NULL,status,
  start_date,end_date,days_requested,sell_days,advance_13th,
  net_value,calculation_details,employee_notes,manager_notes,hr_notes,
  submitted_at,manager_approved,manager_approved_at,manager_approved_by,
  hr_approved,hr_approved_at,hr_approved_by,cancelled_at,cancelled_by,cancellation_reason,
  interrupted_at,interruption_reason,return_date,actual_end_date,created_at,updated_at,created_by
FROM hr_vacation_requests
ON CONFLICT (id) DO NOTHING;
COMMIT;
