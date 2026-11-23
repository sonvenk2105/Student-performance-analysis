-- Run as the database owner after applying Flask migrations.
-- These views deliberately omit names, email addresses, student IDs and credentials.
CREATE OR REPLACE VIEW vw_assessment_history AS
SELECT a.id AS assessment_id, u.analytics_key AS student_key,
       a.course, a.semester, a.academic_year, a.label AS assessment_label,
       a.assessed_at::date AS assessment_date, a.percentage,
       a.grade, a.passed, a.total_obtained, a.total_maximum,
       a.rule_version, a.analysis_version
FROM assessment a
JOIN "user" u ON u.id = a.student_id;

CREATE OR REPLACE VIEW vw_subject_performance AS
SELECT m.id AS mark_id, m.assessment_id, u.analytics_key AS student_key,
       a.course, a.semester, a.academic_year, a.assessed_at::date AS assessment_date,
       a.label AS assessment_label, m.subject, m.obtained AS marks_obtained,
       m.maximum AS marks_maximum, m.passing AS subject_pass_mark,
       m.percentage, m.grade, m.passed AS subject_passed,
       a.passed AS assessment_passed, a.percentage AS assessment_percentage,
       a.total_obtained, a.total_maximum, a.rule_version
FROM assessment_mark m
JOIN assessment a ON a.id = m.assessment_id
JOIN "user" u ON u.id = a.student_id;

CREATE OR REPLACE VIEW vw_student_performance_summary AS
SELECT student_key, assessment_id, course, semester, academic_year,
       assessment_date, assessment_label, total_obtained, total_maximum,
       percentage, grade, passed, rule_version
FROM vw_assessment_history;

CREATE OR REPLACE VIEW vw_semester_performance AS
SELECT course, semester, academic_year,
       COUNT(DISTINCT student_key) AS students_represented,
       COUNT(DISTINCT assessment_id) AS assessment_count,
       AVG(percentage) AS average_assessment_percentage,
       COUNT(DISTINCT assessment_id) FILTER (WHERE passed) AS passed_assessments,
       COUNT(DISTINCT assessment_id) FILTER (WHERE NOT passed) AS failed_assessments,
       100.0 * COUNT(DISTINCT assessment_id) FILTER (WHERE passed)
         / NULLIF(COUNT(DISTINCT assessment_id), 0) AS assessment_pass_rate
FROM vw_assessment_history
GROUP BY course, semester, academic_year;

CREATE OR REPLACE VIEW vw_course_performance AS
SELECT course, COUNT(DISTINCT student_key) AS students_represented,
       COUNT(DISTINCT assessment_id) AS assessment_count,
       AVG(percentage) AS average_assessment_percentage,
       COUNT(DISTINCT assessment_id) FILTER (WHERE passed) AS passed_assessments,
       COUNT(DISTINCT assessment_id) FILTER (WHERE NOT passed) AS failed_assessments,
       100.0 * COUNT(DISTINCT assessment_id) FILTER (WHERE passed)
         / NULLIF(COUNT(DISTINCT assessment_id), 0) AS assessment_pass_rate
FROM vw_assessment_history
GROUP BY course;

-- Least-privilege example. Replace role/password out-of-band; never store here.
-- CREATE ROLE powerbi_reader LOGIN;
-- GRANT CONNECT ON DATABASE student_performance TO powerbi_reader;
-- GRANT USAGE ON SCHEMA public TO powerbi_reader;
-- REVOKE ALL ON ALL TABLES IN SCHEMA public FROM powerbi_reader;
-- GRANT SELECT ON vw_assessment_history, vw_subject_performance,
--   vw_student_performance_summary, vw_semester_performance,
--   vw_course_performance TO powerbi_reader;
