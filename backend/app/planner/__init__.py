"""Deterministic planner engine (growth-readiness project 2).

LLM may SUGGEST; this engine DECIDES. Every plan must come out of here so
the same input always yields the same plan and no hard constraint is ever
violated, regardless of what an LLM (or an agent) proposed.
"""
