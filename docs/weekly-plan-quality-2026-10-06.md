# Weekly planner quality review — October 6, 2026

The planner produces usable schedules and concrete book assignments where the
indexed corpus is complete. Its current question coverage is uneven: math has
substantially more usable material than physics, and humanities has no usable
numbered-question corpus. Filling the time goal does not establish that every
block is a high-quality, exam-specific assignment.

## Method

Ten scenarios ran on the VM using a temporary SQLite backup of the actual
account history and the actual shared OCR/question index. Goal and preference
changes applied only to that copy. The live profile, saved calendar, accounts,
history and manual activity were not rewritten. The generated block titles,
topics, question ranges, duration distribution and warnings were inspected.
Checks covered overlaps, duplicate ranges, count accuracy, preserved manual
work, rest days and daily goals. The synthetic school scenario used a separate
feasible fixture because its school hours conflict with a saved manual class;
the real API correctly rejects conflicting fixed activities.

## Observed schedules after corrections

| Scenario | Scheduled minutes per day | Numbered practice blocks | Assigned questions |
| --- | --- | ---: | ---: |
| Four-hour goal, 45-minute focus | 225, 240, 225, 240, 240, 240, 240 | 16 | 139 |
| Eight-hour goal, balanced | 480 every day | 18 | 170 |
| Eight-hour goal, more practice | 480 every day | 22 | 200 |
| Eight-hour goal, more theory | 480 every day | 14 | 137 |
| Four-hour goal, Pomodoro | 230, 220, 240, 240, 235, 240, 235 | 25 | 131 |
| Four-hour goal, Friday rest | 240 on six days, 0 Friday | 10 | 85 |
| Eight-hour goal, five school days | 450 on school days, 480 otherwise | 18 | 172 |
| Grade 10 | 240 every day | 9 | 97 |
| Humanities without question sources | 240 every day | 0 | 0 |
| Eight-hour goal, registered midweek math exam | 480 every day | 17 | 67 |

The question totals exclude the timed weekly mock, whose count is a target
rather than a claim that a source booklet was retrieved. No overlaps, duplicate
in-week question ranges or inaccurate printed-range counts remained in these
scenarios. Explicit preferences changed the study/practice mix as intended.
Pomodoro blocks remained between 15 and 25 minutes, with the selected five-minute
breaks; no generated five-minute fragments remained.

A separate midweek-exam regression with ample questions exposed a false shortage: with eight available
hours per day and sufficient book questions, the old plan ended with 330 minutes
on Thursday and none on Friday. The corrected case retains 450–480 minutes every
day. Dated timed mocks retain their hard date; ordinary chapter preparation uses
the exam date for priority, and any work placed later is explicitly described as
post-exam consolidation rather than preparation for an upcoming exam. The
corresponding real-corpus scenario also reaches eight hours, but only 67 numbered
questions match its selected chapters; this exposes the chapter coverage limit.

## Bugs corrected

1. Indexed-only and catalogue-only books lost their grade/track restrictions
   when raw PDFs were absent. A grade-12 chemistry book could reappear in a
   grade-10 plan. All discovery paths now retain explicit grade/track information.
2. Several registered exams contributed topics to one earliest deadline.
   Registered and cached outlines now select the nearest dated topics per
   subject, preserve the correct source, and ignore exams already elapsed during
   regeneration. Selecting the timed mock is ordered by date as well.
3. Other saved weeks did not reserve their question ranges. Rebuilding one week
   now reserves future assignments in the student's other saved weeks without
   reserving the generated blocks it is replacing in the current week.
4. Pomodoro review and topic rounding emitted five- and ten-minute slivers.
   Useful remainders are rebalanced while preserving the selected focus cap.
5. Completed work recorded as `math` did not unlock the same topic in `ریاضی`.
   Session and task-progress subject aliases now use the same normalization as
   book selection, avoiding unnecessary restudy before numbered practice.
6. An early exam imposed a hard cutoff on an entire week's chapter workload,
   leaving later days empty and issuing a misleading free-time warning. Chapter
   preparation now uses a preferred deadline, while dated timed events retain
   their hard constraints. Later consolidation is labeled and disclosed.
7. The VM uses UTC, but student calendar times are Tehran-local. Regeneration
   could schedule work 3.5 hours in the past, or choose the wrong default week at
   the Saturday boundary. The planner and its overview now use a Tehran clock;
   authentication and persisted UTC timestamps are unchanged.

Regression cases also verify that a weak subject with verified wrong answers
receives more time and numbered questions than a corresponding strong subject,
that completed work is retained, and that manual activities and other accounts
remain protected.

## Remaining quality limits

- Physics has only ten usable numbered questions in the audited corpus. Once
  allocated, later blocks explicitly become lesson review/written practice.
- Chemistry has some numbered questions but incomplete chapter headings. Some
  assignments therefore remain general subject review rather than precise
  upcoming-exam chapters.
- No current upcoming mock outline was available for the audited real account.
  Registered/current outlines were exercised separately in regression tests;
  the production planner cannot reconstruct missing exam syllabuses reliably.
- Long practice blocks can have fewer questions than their time-based target
  because the available source range is short. Titles disclose answer analysis
  and review for the remainder; the planner does not invent extra numbers.
- Humanities currently produces general study/written practice, not a usable
  numbered-question plan. Complete grade-specific OCR/catalogue data and current
  exam outlines are needed before claiming comparable quality for that track.

Backend validation covers the full suite, the weakness regression and the
midweek-exam and UTC-server regressions: **444 passed, 3 skipped**.
Frontend code did not change in this review. No visual browser check is claimed.
