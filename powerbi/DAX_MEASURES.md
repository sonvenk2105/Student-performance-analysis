# Power BI measures

Import `vw_assessment_history` as **FactAssessment** and `vw_subject_performance` as **FactAssessmentMarks**. Relate both to shared dimensions by course, semester, student key, and date; relate the mark fact to assessment using `assessment_id`. Keep assessment-level measures on FactAssessment to avoid counting an assessment once per subject.

```DAX
Assessment Count = DISTINCTCOUNT(FactAssessment[assessment_id])
Student Count = DISTINCTCOUNT(FactAssessment[student_key])
Total Marks Obtained = SUM(FactAssessmentMarks[marks_obtained])
Total Maximum Marks = SUM(FactAssessmentMarks[marks_maximum])
Overall Percentage = DIVIDE([Total Marks Obtained], [Total Maximum Marks]) * 100
Average Student Percentage = AVERAGE(FactAssessment[percentage])
Pass Count = CALCULATE([Assessment Count], FactAssessment[passed] = TRUE())
Fail Count = CALCULATE([Assessment Count], FactAssessment[passed] = FALSE())
Pass Rate = DIVIDE([Pass Count], [Assessment Count]) * 100
Semester-wise Percentage = [Average Student Percentage]
Subject Pass Count = CALCULATE(COUNTROWS(FactAssessmentMarks), FactAssessmentMarks[subject_passed] = TRUE())
Subject Fail Count = CALCULATE(COUNTROWS(FactAssessmentMarks), FactAssessmentMarks[subject_passed] = FALSE())
```

`Average Student Percentage` is the mean across saved assessment records, so a student with multiple attempts contributes once per assessment. `Pass Rate` uses completed assessment records as the denominator, not distinct students; display assessment count beside it. The application's stored `passed` field applies the grading rule version attached to each record. Do not add a fixed pass threshold or grade scale in DAX.

For performance change, use the assessment date/attempt context and only compare records with the same course, semester, subject set, maxima, and grading-rule version. A simple previous-record delta is not a fair comparison when those differ. A safe starting measure when the report is filtered to comparable records is:

```DAX
Comparable Assessment Change (pp) =
VAR CurrentPct = [Average Student Percentage]
VAR PreviousPct = CALCULATE([Average Student Percentage], DATEADD(DimDate[Date], -1, MONTH))
RETURN CurrentPct - PreviousPct
```

This is a percentage-point change, not a relative percent change. Filter out non-comparable assessments before presenting it.
