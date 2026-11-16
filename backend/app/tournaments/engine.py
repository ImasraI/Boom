"""Deterministic Swiss pairing, tournament scoring and public standings."""
from functools import lru_cache
from fractions import Fraction


def score_packet(questions, answers):
    """Integer units avoid breaking an exact tie with rounded percentages."""
    correct = wrong = blank = 0
    for q in questions:
        choice = answers.get(str(q["id"]))
        if choice is None:
            blank += 1
        elif choice == q["answer"]:
            correct += 1
        else:
            wrong += 1
    units = 3 * correct - wrong
    return {"correct": correct, "wrong": wrong, "blank": blank,
            "units": units, "percent": round(100 * units / (3 * len(questions)), 1)}


def standings(state):
    rows = {p["id"]: {"player_id": p["id"], "name": p["name"], "played": 0,
                      "wins": 0, "draws": 0, "losses": 0, "points": 0,
                      "buchholz": 0, "score_percent": 0, "_opponents": [], "_scores": []}
            for p in state["players"]}
    for rnd in state["rounds"]:
        if rnd["stage"] != "league" or rnd.get("kind") == "qualification_tiebreak":
            continue
        for match in rnd["matches"]:
            if match["status"] not in ("completed", "forfeit", "bye"):
                continue
            a, b = match["a"], match["b"]
            if b is None:
                rows[a]["points"] += 3
                continue
            for player, opponent, side in ((a, b, "a"), (b, a, "b")):
                row = rows[player]
                row["played"] += 1
                row["_opponents"].append(opponent)
                # Forfeits are below the minimum attainable exam score for
                # ranking purposes, preventing absence outperforming play.
                attempt = match.get("attempts", {}).get(str(player), {})
                score = attempt.get("score")
                questions = match.get("questions") or rnd["questions"]
                value = Fraction(100 * score["units"], 3 * len(questions)) if score else Fraction(-100)
                row["_scores"].append(value)
                if match.get("double_forfeit"):
                    row["losses"] += 1
                elif match["winner_id"] == player:
                    row["wins"] += 1
                    row["points"] += 3
                elif match["winner_id"] is None:
                    row["draws"] += 1
                    row["points"] += 1
                else:
                    row["losses"] += 1
    for row in rows.values():
        row["buchholz"] = sum(rows[p]["points"] for p in row["_opponents"])
        exact_score = sum(row["_scores"], Fraction(0))
        row["score_percent"] = round(float(exact_score), 4)
        extra = []
        for record in state.get("qualification_results", []):
            score = record.get(str(row["player_id"]))
            extra.append(Fraction(100 * score["units"], 3 * score["total"]) if score else Fraction(-100))
        row["_key"] = (row["points"], row["buchholz"], exact_score, *extra)
    ordered = sorted(rows.values(), key=lambda r: (tuple(-v for v in r["_key"]), r["player_id"]))
    for i, row in enumerate(ordered):
        row["rank"] = i + 1 if not i or row["_key"] != ordered[i - 1]["_key"] else ordered[i - 1]["rank"]
        row["tied"] = sum(other["_key"] == row["_key"] for other in ordered) > 1
    return ordered


def cutoff_ties(state):
    table = standings(state)
    count = state["playoff_size"]
    if len(table) <= count or table[count - 1]["_key"] != table[count]["_key"]:
        return []
    return [row["player_id"] for row in table if row["_key"] == table[count]["_key"]]


def swiss_pairs(state):
    """Backtrack rather than silently rematching or producing an unfair bye.

    Only an even roster is activated. Candidate order prefers the closest
    tournament points, then standings rank, then stable ID. CAS on the event
    makes a round's pairings exactly once, independent of request order.
    """
    table = standings(state)
    ids = [row["player_id"] for row in table]
    positions = {p: i for i, p in enumerate(ids)}
    points = {row["player_id"]: row["points"] for row in table}
    met = {frozenset((m["a"], m["b"])) for r in state["rounds"]
           if r["stage"] == "league" and not r.get("kind")
           for m in r["matches"] if m["b"] is not None}

    @lru_cache(maxsize=None)
    def pair(remaining):
        if not remaining:
            return ()
        # Most constrained player first keeps backtracking bounded when five
        # rounds leave little flexibility in a small fixture roster.
        a = min(remaining, key=lambda p: (sum(frozenset((p, q)) not in met
                    for q in remaining if q != p), positions[p]))
        others = sorted((q for q in remaining if q != a and frozenset((a, q)) not in met),
                        key=lambda q: (abs(points[a] - points[q]), abs(positions[a] - positions[q]), q))
        for b in others:
            rest = pair(tuple(p for p in remaining if p not in (a, b)))
            if rest is not None:
                return ((a, b),) + rest
        return None

    result = pair(tuple(ids))
    if result is None:
        raise ValueError("بدون تکرار حریف امکان قرعه‌کشی این دور نیست؛ مدیر باید ساختار را بررسی کند.")
    result = list(result)
    # A first legal matching can leave a large, avoidable score mismatch in
    # its last pair. Refine two pairs at a time without introducing rematches.
    # Every accepted swap strictly reduces (largest gap, total gap); both are
    # non-negative integers bounded by the roster and tournament points, so
    # refinement terminates. Equal improvements keep the deterministic scan
    # order. This is a local fairness refinement, not a full FIDE pairing rule.
    while True:
        gaps = [abs(points[a] - points[b]) for a, b in result]
        total = sum(gaps)
        best = (max(gaps, default=0), total)
        change = None
        for i, (a, b) in enumerate(result):
            for j in range(i + 1, len(result)):
                c, d = result[j]
                other_max = max((gap for k, gap in enumerate(gaps) if k not in (i, j)), default=0)
                for first, second in (((a, c), (b, d)), ((a, d), (b, c))):
                    if frozenset(first) in met or frozenset(second) in met:
                        continue
                    first_gap = abs(points[first[0]] - points[first[1]])
                    second_gap = abs(points[second[0]] - points[second[1]])
                    candidate = (max(other_max, first_gap, second_gap),
                                 total - gaps[i] - gaps[j] + first_gap + second_gap)
                    if candidate < best:
                        best = candidate
                        change = (i, j, first, second)
        if change is None:
            return result
        i, j, first, second = change
        result[i], result[j] = first, second


def knockout_pairs(qualifiers):
    """Standard seeded tree: 1/8, 4/5, 2/7, 3/6 for eight entrants."""
    n = len(qualifiers)
    seeds = [1, 2]
    while len(seeds) < n:
        size = len(seeds) * 2 + 1
        seeds = [value for seed in seeds for value in (seed, size - seed)]
    return [(qualifiers[seeds[i] - 1], qualifiers[seeds[i + 1] - 1]) for i in range(0, n, 2)]
