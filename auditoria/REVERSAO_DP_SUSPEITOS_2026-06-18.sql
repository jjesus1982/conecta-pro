-- REVERSAO DP (DROP so seguro enquanto vazias) 2026-06-18
BEGIN;
DROP TABLE IF EXISTS "employee_documents" CASCADE;
DROP TABLE IF EXISTS "employee_notifications" CASCADE;
DROP TABLE IF EXISTS "employee_payroll_configs" CASCADE;
DROP TABLE IF EXISTS "employee_preferences" CASCADE;
DROP TABLE IF EXISTS "payroll_events" CASCADE;
COMMIT;
