# Homework in chat and the weekly plan

Tell the assistant about one homework assignment (for example, «۲۰ سؤال میدان
الکتریکی از کتاب خیلی سبز برای دوشنبه تکلیف دارم»). It extracts a draft and asks
for missing details. Follow-up messages fill the same draft in that conversation.
Drafts do not modify the calendar.

Review the lesson/topic, book/pages/questions, total minutes, delivery date/time,
activity and familiarity in the chat form, then select «ثبت در برنامه». Dates in
this form use the Gregorian calendar, with times interpreted in Tehran. If a
practice topic is unread, specify the prerequisite study portion of the total;
that study is placed before the exercises. Any model time suggestion is explicitly
an estimate, and the student can change it.

The default adds sessions to free time within the saved daily study limit. The
student may allow replacement if there is insufficient space. Replacement only
affects future, unstarted, generated sessions with the same subject and topic and
the appropriate study/practice goal. Manual activities, fixed/recurring commitments,
other lessons and completed/partial sessions stay intact. Insufficient capacity or
a stale calendar version leaves the plan unchanged. Confirming the same homework
again does not create duplicates.

Homework is saved atomically to the authenticated student's `StudentCalendar`, with
planned `TaskProgress` rows and a reviewed `Homework` record. Its blocks have manual
origin so a weekly rebuild preserves them. Home displays the same weekly blocks and
date-aware recurrence expansion as Schedule. Homework does not create knowledge
accuracy; actual answer outcomes and completion reports supply learning evidence.

API: `POST /api/boom/chat` accepts `conversation_id` and an optional `homework_id`
for a follow-up draft; its response contains `homework_draft`.
`POST /api/boom/homework/{id}/schedule` accepts the reviewed details and current
`calendar_version`. Scheduling is independent of model availability; if extraction
fails, the student can still fill the form manually.
