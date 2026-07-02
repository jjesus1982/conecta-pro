-- REVERSAO FERIAS (legado hr_vacation_* preservado como origem) 2026-06-18
BEGIN;
DROP TABLE IF EXISTS employee_vacation_requests CASCADE;
DROP TABLE IF EXISTS employee_vacation_periods CASCADE;
COMMIT;
