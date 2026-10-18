# Colosseum: rolling Maze stock

The normal mode prefers ten verified shared questions from the next reviewed
Maze exam. If that scope cannot supply a complete match, `available_preview`
checks earlier reviewed exam dates in descending order and selects the newest
scope that can supply a complete match. This also permits a valid older scope
while the next exam's curriculum mapping is incomplete. Generation still uses
`require_plan` and never relaxes the new scope's grounding requirements.

An older scope is rebuilt from the reviewed schedule and current curriculum.
Changed source hashes, missing mappings, corrupt/reported questions, private
questions, wrong grades and incomplete coverage remain excluded. Unscoped old
questions are not relabelled as a previous Maze exam. Questions from different
Maze scopes are never combined to fill a match.

`GET /api/arena/filters` exposes the selected `date`, `requested_date`, `fallback`
and `stock_available`. The lobby labels previous-version stock explicitly.
Availability checks do not claim booklets or increment question uses. Existing
lazy indexing can run during selection. Live joining, actual pairing and
scheduled acceptance resolve availability again; the actual match reserves one
booklet for both players using the existing matchmaking lock and claim rules.

Fallback does not generate new questions, consume provider quota, change Elo
rules or start the production pool. A live match still requires an opponent.
