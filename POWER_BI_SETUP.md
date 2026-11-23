# Power BI Desktop setup

## Data model and privacy

The PostgreSQL views in `powerbi/views.sql` use the actual Flask table names. They expose a randomly assigned `analytics_key` instead of a student name, email, or student ID. They do not expose passwords, upload paths, session data, or authentication secrets. Individual student report access must still be restricted; pseudonymous identifiers are personal data when they can be linked back by an administrator.

Apply the views as the database owner, then create a dedicated read-only login and grant it `SELECT` only on those views. Use private networking/VPN or a protected tunnel; do not expose PostgreSQL to the public internet. Store its credential in the Power BI credential manager, never in a PBIX query or website JavaScript.

## Recommended examiner workflow (Power BI Desktop)

1. Run the Flask migrations against PostgreSQL and create real assessment records.
2. Open PowerShell or a SQL client as the database owner and execute `powerbi/views.sql`.
3. In Power BI Desktop choose **Get data → PostgreSQL database**; enter the database host and name, then choose Import. Use the read-only analytics account.
4. Select `vw_assessment_history`, `vw_subject_performance`, `vw_semester_performance`, and `vw_course_performance`.
5. Add a date dimension and relate it to `assessment_date`. Relate course/semester/date dimensions to both fact tables. Relate facts by `assessment_id` only where a single-direction relationship avoids ambiguous filter paths.
6. Add measures from `powerbi/DAX_MEASURES.md`. Keep assessment-level counts and pass rates on the assessment view; subject-level counts belong on the subject view.
7. Build four report pages:
   - **Overall Performance:** student count, assessment count, mean percentage, assessment pass rate, course comparison, semester trend.
   - **Subject Analysis:** average subject percentage, subject pass/fail counts, top/bottom subjects, obtained versus maximum marks.
   - **Semester and Progress:** date trend and course/semester/year/attempt slicers; show percentage-point change only for comparable assessment sets.
   - **Individual Student:** filter on `student_key`, show subject results and assessment history; share only within the authorized college tenant/audience.
8. Validate several assessment totals against the Flask result page. Weighted percentage equals total obtained divided by total maximum times 100. Repeated attempts count as separate assessment records.
9. Save the `.pbix` locally. Refresh in Desktop before presenting; refresh credentials are managed in Power BI settings.

## Optional published or embedded reports

Embedding is not configured in this project. It requires appropriate Power BI licensing, tenant permissions, identity design, and a secure embed method. For authenticated staff use organizational access or a server-side embed-token design appropriate to the college tenant. Never ship a service principal secret or privileged access token to the browser. Do not use public publish-to-web for student-level data. Complete a privacy and access review before enabling embedding.

## Schema check

Views use the `user`, `assessment`, and `assessment_mark` tables and columns created by `app/models.py`. Re-run the view script after schema changes and verify view totals against the Flask result pages before sharing a report. The views include only completed assessments, so missing/incomplete work is not counted.
