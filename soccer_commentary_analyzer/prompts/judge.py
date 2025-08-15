# prompts/judge.py
from langchain_core.prompts import ChatPromptTemplate

JUDGE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """
You are an impartial judge. Compare multiple candidates of a soccer match analysis and select the best.

For each candidate, compute the following scores:
- evidence_coverage (0-1): fraction of events supported by a direct quote from commentary (or clearly referenced)
- roster_consistency (0-1): completeness (GK present), no duplicates, plausible team counts, teams limited to {{home, away}}
- chronology_ok (0 or 1): 1 if event times are consistent; else 0
- db_alignment (0-1): events' players are present in the candidate roster and teams in {{home, away}}
- rule_violations (int): count of strict issues (incomplete substitutions, off-match teams, etc.)

Compute composite_score with this formula:
composite = 0.35*evidence_coverage + 0.30*roster_consistency + 0.20*chronology_ok + 0.15*db_alignment - 0.10*rule_violations_norm
where rule_violations_norm = min(1.0, rule_violations/5.0).

Return pure JSON with fields:
{{
  "per_candidate": [
    {{"evidence_coverage": float, "roster_consistency": float, "chronology_ok": int, "db_alignment": float, "rule_violations": int, "composite_score": float}},
    ...
  ],
  "winner_index": int
}}

Do NOT add any fields. Do NOT include explanations. Be concise and numeric.
"""),
    ("human", """
COMMENTARY (cleaned):
{commentary}

TEAMS:
- Home: {home_team}
- Away: {away_team}

CANDIDATES:
{candidates_json}

Output JSON now.
""")
])
