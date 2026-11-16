# Tournaments

The public tournament page is available at `/#tournament`, from the landing page,
and in the Colosseum navigation. Registration is deliberately closed: the visible
button is a placeholder, and there are no enrollment or payment endpoints.

## Student experience

- Public standings include games, wins, draws, losses, league points, opponents'
  points (Buchholz), cumulative round percentages and unresolved ties. The league
  rules appear immediately below the standings table.
- A selectable league timeline shows the actual pairings and results of each
  published round. Future opponents stay unassigned until preceding results are
  settled.
- The knockout tree has connecting paths, seeded quarterfinals, semifinals,
  final and a third-place match. Four-player playoffs are also supported.
- Signed-in entrants see their assigned matches and official Tehran-local start
  and deadline. Start/resume is enabled only by server eligibility. The public
  page, diagrams and standings do not require sign-in.
- Play uses a fixed, pre-reviewed packet, a shared server deadline and existing
  math/diagram rendering. Answers autosave with revisions. A resumed match keeps
  its deadline and saved answers; it does not receive another time allowance.
- At expiry, the server grades the last answers it received. An offline or late
  client selection cannot silently replace those answers. Saving failures are
  visible and can be retried while the match remains open.

No participants, scores, question stock, tournament dates, awards or registration
successes are fabricated when no event has been prepared. The first view then
shows an explicitly labelled structural preview.

## Rules and lifecycle

Defaults are 32 entrants, five Swiss-style rounds, eight qualifiers, 15-minute
matches, three-minute attendance grace, 48 hours between league rounds and
24 hours between knockout rounds. Admin configuration can change these values
before activation. A roster must be even, fit the capacity, have enough entrants
for the playoffs and use at most half as many league rounds as entrants. This
conservative round limit preserves enough possible opponents for no-rematch
pairing.

Pairing is deterministic, avoids repeated league opponents and prefers close
league scores. A local two-pair refinement reduces avoidable score gaps. It is
not an implementation or certification of the full FIDE pairing rules.

League points are 3 for a win, 1 for a draw and 0 for a loss. Tie-break order is:

1. League points.
2. Sum of opponents' current/final league points.
3. **Sum of round percentages**, compared exactly before display rounding. This
   total can exceed 100%; it is not a mastery/accuracy percentage.
4. Fresh common qualification questions when a complete tie crosses the
   qualifying cutoff. Identifiers and response speed never choose a qualifier.

Exam percentages use `(3 * correct - wrong) / (3 * question_count) * 100`.
A present entrant beats an absent opponent regardless of a negative exam score.
Both absent entrants receive zero league points. Absence contributes -100 to the
third tie-break metric; that is a ranking penalty, not a scientific exam score.

For eight qualifiers, first-round seeds are 1/8, 4/5, 2/7 and 3/6. Tied knockout
matches require fresh questions. Double absence has no arbitrary winner; an
admin can prepare a fresh rescheduled match. A tournament cannot complete until
both the final and third-place match have winners. Late qualification/tie-break
resolution shifts unpaired dependent windows and publishes a schedule notice
instead of creating already-expired matches.

All tournament results are separate from permanent Arena Elo. Automatic question
generation, money collection, prize allocation and anti-cheat adjudication are
outside this feature. A real event still requires reviewed packets, announced
rules and organizer supervision of disputes.

## Preparing an event

An existing administrator uses the protected endpoints below. Participants must
already have accounts and saved profiles matching the event's grade and major.
This manual roster is not a public signup flow.

`POST /api/tournaments/admin/events` accepts:

```json
{
  "title": "عنوان دوره",
  "description": "بودجه‌بندی و توضیح دوره",
  "major": "ریاضی فیزیک",
  "grade": "دوازدهم",
  "capacity": 32,
  "league_rounds": 5,
  "playoff_size": 8,
  "duration_minutes": 15,
  "attendance_grace_minutes": 3,
  "round_interval_hours": 48,
  "playoff_interval_hours": 24,
  "starts_at": "2027-01-01T18:00:00+03:30",
  "participant_ids": [],
  "packets": {}
}
```

The timestamp is illustrative, not an announced event. Replace it before use.
Empty roster/packets can be saved as a draft; they cannot be activated. Supply
real account IDs and question-bank ID arrays keyed by `league-1` through
`league-5`, `quarterfinal`, `semifinal`, `final` and `third_place`. Other configured
league counts use the corresponding numbered keys; four-player playoffs omit
quarterfinals.

Packets must contain distinct, active, verified **shared** bank questions of the
same major/grade. IDs cannot repeat between rounds. Activation revalidates bank
status and freezes the packet snapshots; starting a match makes no model calls.

| Endpoint | Purpose |
| --- | --- |
| `PATCH /api/tournaments/admin/events/{id}` | Replace configuration while draft |
| `POST /api/tournaments/admin/events/{id}/activate` | Freeze validated roster/packets and pair round one |
| `POST /api/tournaments/admin/events/{id}/advance` | Reconcile deadlines/results, idempotently |
| `POST /api/tournaments/admin/events/{id}/tiebreak` | Prepare fresh questions for a cutoff tie, tied knockout or rescheduled double absence |

Tie-break payload: `bank_question_ids`, timezone-aware `starts_at`,
`duration_minutes`, plus `match_id` for a knockout match. Omit `match_id` for a
qualifying-cutoff test. These packets must also be unused verified questions.

## Storage and API boundaries

`tournament_events` is an additive SQLAlchemy table registered before the existing
startup schema initialization. An event revision atomically stores its roster,
packets, pairings and attempts. Compare-and-swap updates prevent concurrent
starts, submissions or advancement from overwriting each other.

Public endpoints are `GET /api/tournaments` and `GET /api/tournaments/{id}`.
Authenticated entrant endpoints are `GET /{id}/me`,
`POST /{id}/matches/{match_id}/start`, `PUT /{id}/matches/{match_id}/answers` and
`POST /{id}/matches/{match_id}/submit`, under `/api/tournaments`.

Start/resume returns only allowlisted question fields. Answer keys, private
attempts and phone-based usernames are absent from public projections. Scores
are withheld while the corresponding match is unresolved. Answer saves require
increasing revisions; identical retries are idempotent and stale revisions are
rejected. The full account-wipe flow anonymizes tournament entries, removes
private answers and replaces the account ID so reused IDs cannot inherit games.

## Validation

```powershell
cd backend
.venv/Scripts/python.exe -m pytest ../tests/tournaments_test.py -q
cd ../frontend
npm.cmd test
npx.cmd tsc --noEmit
npm.cmd run build
```

Feature tests cover a 32-entrant/five-round league, no rematches, locally improved
pairing, exact ties, knockout progression, qualification tests, server deadlines,
revisioned answer saves, concurrent starts/submissions, public privacy and account
wipe. Frontend tests cover empty/loading states, bracket structure, eligibility,
escaping, server-first resume and failed/concurrent answer saves.

A separate ignored local fixture was used for browser QA. Its pupils, packets,
accounts and database are synthetic and are not included in production data or
this feature's repository files. Passing these tests does not establish live
question quality, prize/fee compliance, production deployment or anti-cheat.
