"""
ReAct + MRKL Agent for Citi Bike Pass Optimizer.

Uses Ollama (phi3:mini) as the LLM backbone with a ReAct loop:
  Thought → Action → Observation → ... → Final Answer

MRKL Tools available:
  - csv_sql        : run SQL over uploaded trip CSV
  - policy_retriever: fetch + extract Citi Bike pricing page
  - calculator     : safe arithmetic
"""

import json
import re
import sys
import os
import time
from typing import Any, Generator

import requests as http_requests

# Allow imports from parent bike_optimizer directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.calculator import calculator  # noqa: E402
from tools.csv_sql import csv_sql  # noqa: E402
from tools.policy_retriever import policy_retriever  # noqa: E402

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "phi3:mini"

MAX_STEPS = 12  # safety ceiling for the ReAct loop

SYSTEM_PROMPT = """You are a Citi Bike cost optimizer. Analyze trip data and pricing to recommend:
"Buy Monthly Membership" OR "Pay Per Ride/Minute".

OUTPUT FORMAT — follow this EXACTLY every single turn:

Thought: <one sentence of reasoning>
Action: <tool_name>
Action Input: {"key": "value"}

NEVER wrap Action Input in extra braces like {{...}}.
NEVER output JSON like {"action": "csv_sql", "input": {...}}.
Always put the tool name directly after "Action:" on its own line.

When you have calculated both costs, output a Final Answer in EXACTLY this structure:

Final Answer:
DECISION: Buy Monthly Membership
JUSTIFICATION: <one paragraph with numbers, e.g. "With 150 rides averaging 52 min, pay-per-use costs $X vs membership $Y...">
COST BREAKDOWN:
- Pay Per Use total: $<number>
- Monthly Membership total: $<number>
- Savings with recommended plan: $<number>
WEEKLY BREAKDOWN:
- Week 1: <rides> rides, avg <min> min, $<cost>
- Week 2: <rides> rides, avg <min> min, $<cost>
- Week 3: <rides> rides, avg <min> min, $<cost>
- Week 4: <rides> rides, avg <min> min, $<cost>
ASSUMPTIONS: <list key assumptions>
CITATION: Citi Bike Pricing page, captured 2026-03-23

---
TOOLS:

1. policy_retriever
   Action Input: {"url": "https://citibikenyc.com/pricing", "query": "membership price per minute"}
   Returns pricing text snippets.

2. csv_sql
   Action Input: {"sql": "SELECT ..."}
   Table name: trips  (always lowercase, no prefix)
   EXACT column names in this dataset:
     ride_id, rideable_type, started_at, ended_at,
     start_station_name, start_station_id,
     end_station_name, end_station_id,
     start_lat, start_lng, end_lat, end_lng, member_casual
   DURATION: use epoch diff — epoch(ended_at::TIMESTAMP) - epoch(started_at::TIMESTAMP)
   DO NOT use tripduration, ebike, week(), or any column not listed above.
   IMPORTANT: Always filter WHERE member_casual='casual' to analyze the target rider only.
   Correct example:
     SELECT COUNT(*) AS total_rides,
            ROUND(AVG(epoch(ended_at::TIMESTAMP)-epoch(started_at::TIMESTAMP))/60,1) AS avg_min,
            SUM(CASE WHEN rideable_type='electric_bike' THEN 1 ELSE 0 END) AS ebike_count
     FROM trips
     WHERE member_casual='casual'

3. calculator
   Action Input: {"expression": "19.99 * 4", "units": "USD"}
   Numbers and +,-,*,/ only. No variables or text.
   Use this to compute: pay-per-use total cost AND membership total cost.
   Citi Bike pricing (use these numbers):
     Single classic ride: $4.99 for 30 min, then $0.26/min overage
     E-bike single ride: $4.99 + $0.26/min from minute 1
     Monthly membership: $19.99/month, 45 min free per classic ride, e-bike $0.26/min surcharge

---
PRICING FACTS (already retrieved — do NOT call policy_retriever):
  - Single classic ride: $4.99 for up to 30 min, then $0.26/min overage
  - E-bike single ride: $4.99 + $0.26/min from minute 1
  - Monthly membership: $19.99/month, 45 min free per classic ride, e-bike $0.26/min surcharge
  - Break-even: if pay-per-use total > $19.99 → buy membership; else → pay per use

PLAN (follow in order, 4 steps only):
1. Call csv_sql to get total_rides, avg_min, ebike_count WHERE member_casual='casual'.
2. Call calculator: pay_per_use = total_rides * 4.99 (add overage if avg_min > 30).
3. Call calculator: membership = 19.99 (add ebike_count * avg_min * 0.26 if ebike > 0).
4. Output Final Answer in the EXACT structured format above with real dollar numbers.
"""


def _sanitize_llm_output(text: str) -> str:
    """
    Remove prompt-injection hallucinations that phi3:mini sometimes generates.
    Strips everything from '## Your task', 'Human:', 'User:', '---' onward
    when they appear mid-output after the agent has started responding.
    """
    # Cut off at known injection markers
    cutoff_patterns = [
        r'\n##\s+Your task',
        r'\nYour task:',
        r'\nHuman:',
        r'\nUser:',
        r'\n---\n.*?Single Ride Pass',  # fake pricing re-injection
    ]
    for pattern in cutoff_patterns:
        m = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if m:
            text = text[:m.start()].strip()
    return text


def _call_ollama(prompt: str) -> str:
    """Call Ollama phi3:mini and return the generated text."""
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.0,
            "num_predict": 500,
            "stop": ["Observation:", "\n##", "\nYour task", "Human:", "User:"],
        },
    }
    try:
        resp = http_requests.post(OLLAMA_URL, json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except Exception as e:
        return f"Error calling Ollama: {e}"


def _parse_action(text: str) -> tuple[str | None, dict | None]:
    """
    Extract Action name and Action Input JSON from LLM output.
    Handles two formats phi3 sometimes emits:
      A) Standard ReAct:  Action: csv_sql\nAction Input: {"sql": "..."}
      B) JSON-wrapped:    Action: {"action": "csv_sql", "input": {"sql": "..."}}
    """
    # --- Format B: phi3 emits {"action": ..., "input": ...} after "Action:" ---
    # Match Action: followed immediately by a JSON object (possibly multi-line)
    json_action_match = re.search(
        r'Action:\s*(\{(?:[^{}]|\{[^{}]*\})*\})', text, re.DOTALL
    )
    if json_action_match:
        try:
            obj = json.loads(json_action_match.group(1))
            # Only treat as format-B if it has an "action" or "tool" key
            tool_name = (obj.get("action") or obj.get("tool") or "").strip().lower()
            tool_input = obj.get("input") or obj.get("action_input") or {}
            if tool_name:
                return tool_name, tool_input
        except json.JSONDecodeError:
            pass

    # --- Format A: standard ReAct ---
    action_match = re.search(r"Action:\s*(\w+)", text)
    if not action_match:
        return None, None

    tool_name = action_match.group(1).strip().lower()

    # Grab everything after "Action Input:" up to the next blank line or end
    input_match = re.search(
        r"Action Input:\s*(\{[\s\S]*?\})\s*(?:\n\n|\nThought:|\nObservation:|\nFinal|$)",
        text,
    )
    if not input_match:
        # Looser fallback — grab first {...} after Action Input:
        input_match = re.search(r"Action Input:\s*(\{[\s\S]*?\})", text, re.DOTALL)

    tool_input: dict = {}
    if input_match:
        raw = input_match.group(1).strip()
        try:
            tool_input = json.loads(raw)
        except json.JSONDecodeError:
            # Manual field extraction
            sql_m = re.search(r'"sql"\s*:\s*"([\s\S]*?)"\s*(?:,|\})', raw)
            url_m = re.search(r'"url"\s*:\s*"(.*?)"', raw)
            query_m = re.search(r'"query"\s*:\s*"(.*?)"', raw)
            expr_m = re.search(r'"expression"\s*:\s*"([^"]*?)"', raw)
            units_m = re.search(r'"units"\s*:\s*"([^"]*?)"', raw)
            if sql_m:
                sql_val = sql_m.group(1).replace('\\n', ' ').strip()
                tool_input = {"sql": sql_val}
            elif url_m:
                tool_input = {
                    "url": url_m.group(1),
                    "query": query_m.group(1) if query_m else "membership price",
                }
            elif expr_m:
                tool_input = {
                    "expression": expr_m.group(1),
                    "units": units_m.group(1) if units_m else None,
                }

    # Post-process: strip accidental outer { } from SQL values
    if "sql" in tool_input:
        sql_val = str(tool_input["sql"]).strip()
        if sql_val.startswith("{") and sql_val.endswith("}"):
            sql_val = sql_val[1:-1].strip()
        tool_input["sql"] = sql_val

    return tool_name, tool_input


def _dispatch_tool(tool_name: str, tool_input: dict) -> str:
    """Call the appropriate MRKL tool and return the observation as a string."""
    if tool_name == "csv_sql":
        result = csv_sql(tool_input.get("sql", "SELECT 1"))
    elif tool_name == "policy_retriever":
        result = policy_retriever(
            url=tool_input.get("url", "https://citibikenyc.com/pricing"),
            query=tool_input.get("query", "membership price fee"),
            k=tool_input.get("k", 6),
        )
    elif tool_name == "calculator":
        result = calculator(
            expression=tool_input.get("expression", "0"),
            units=tool_input.get("units"),
        )
    else:
        result = {
            "success": False,
            "error": f"Unknown tool: '{tool_name}'. Use csv_sql, policy_retriever, or calculator.",
        }

    # Summarize the result for the LLM context window
    if result.get("success"):
        data = result.get("data", result)
        if tool_name == "csv_sql":
            rows = data.get("rows", [])
            row_count = data.get("row_count", 0)
            preview = rows[:5] if rows else []
            return json.dumps(
                {"row_count": row_count, "preview": preview, "source": data.get("source")},
                default=str,
            )
        elif tool_name == "policy_retriever":
            passages = data.get("passages", [])
            captured_at = data.get("captured_at", "")
            return json.dumps(
                {
                    "captured_at": captured_at,
                    "passages": [
                        {"text": p["text"], "score": p["score"]} for p in passages[:6]
                    ],
                },
                default=str,
            )
        elif tool_name == "calculator":
            return json.dumps(data, default=str)
    else:
        return json.dumps({"error": result.get("error", "Unknown error")})


def run_agent(
    pricing_url: str,
) -> Generator[dict[str, Any], None, None]:
    """
    Hybrid ReAct+MRKL agent loop.

    Steps 1-3 are executed deterministically by Python (tool dispatch),
    yielding real Thought→Action→Observation cards with accurate data.
    Step 4 asks phi3:mini to synthesize a Final Answer from the computed numbers.

    This ensures the MRKL tools always run and produce real numbers,
    while the LLM role is scoped to narrative synthesis — what small
    models do reliably.
    """
    total_start = time.time()
    steps = []
    step_num = 0

    # ── STEP 1: csv_sql ──────────────────────────────────────────────────────
    step_num += 1
    sql = (
        "SELECT COUNT(*) AS total_rides, "
        "ROUND(AVG(epoch(ended_at::TIMESTAMP)-epoch(started_at::TIMESTAMP))/60,1) AS avg_min, "
        "SUM(CASE WHEN rideable_type='electric_bike' THEN 1 ELSE 0 END) AS ebike_count "
        "FROM trips WHERE member_casual='casual'"
    )
    thought1 = "I will query the trip data to get ride count, average duration, and e-bike share for the target rider."
    t = time.time()
    obs1_raw = _dispatch_tool("csv_sql", {"sql": sql})
    latency1 = round(time.time() - t, 3)

    step1 = {
        "step": step_num, "type": "action", "content": thought1,
        "tool": "csv_sql", "tool_input": {"sql": sql},
        "observation": obs1_raw, "latency_s": latency1,
    }
    steps.append(step1)
    yield step1

    # Parse csv_sql result
    try:
        obs1 = json.loads(obs1_raw)
        row = obs1.get("preview", [{}])[0] if obs1.get("preview") else {}
        total_rides = int(row.get("total_rides", 0))
        avg_min = float(row.get("avg_min", 0))
        ebike_count = int(row.get("ebike_count", 0))
    except Exception:
        total_rides, avg_min, ebike_count = 0, 0, 0

    # ── STEP 2: calculator — pay-per-use cost ─────────────────────────────────
    step_num += 1
    classic_rides = total_rides - ebike_count
    overage_min = max(0, avg_min - 30)

    # Classic: $4.99 base + $0.26/min overage per ride
    classic_cost = classic_rides * (4.99 + overage_min * 0.26)
    # E-bike: $4.99 + $0.26/min for full duration per ride
    ebike_cost = ebike_count * (4.99 + avg_min * 0.26)
    ppu_total = round(classic_cost + ebike_cost, 2)

    if ebike_count > 0:
        expr_ppu = f"{classic_rides} * ({4.99} + {overage_min} * 0.26) + {ebike_count} * ({4.99} + {avg_min} * 0.26)"
    else:
        expr_ppu = f"{total_rides} * ({4.99} + {overage_min} * 0.26)"

    thought2 = f"Now I will calculate the total pay-per-use cost for {total_rides} rides (avg {avg_min} min, {ebike_count} e-bike)."
    t = time.time()
    obs2_raw = _dispatch_tool("calculator", {"expression": expr_ppu, "units": "USD"})
    latency2 = round(time.time() - t, 3)

    # Use our own computed value (calculator may round differently)
    try:
        obs2 = json.loads(obs2_raw)
        ppu_total = round(float(obs2.get("value", ppu_total)), 2)
    except Exception:
        pass

    step2 = {
        "step": step_num, "type": "action", "content": thought2,
        "tool": "calculator", "tool_input": {"expression": expr_ppu, "units": "USD"},
        "observation": obs2_raw, "latency_s": latency2,
    }
    steps.append(step2)
    yield step2

    # ── STEP 3: calculator — membership cost ──────────────────────────────────
    step_num += 1
    # Membership: $19.99/month, e-bike surcharge $0.26/min per e-bike ride
    mem_ebike_surcharge = round(ebike_count * avg_min * 0.26, 2)
    mem_total = round(19.99 + mem_ebike_surcharge, 2)
    expr_mem = f"19.99 + {mem_ebike_surcharge}" if mem_ebike_surcharge > 0 else "19.99"

    thought3 = f"Now I will calculate the monthly membership cost (${19.99} + e-bike surcharges of ${mem_ebike_surcharge})."
    t = time.time()
    obs3_raw = _dispatch_tool("calculator", {"expression": expr_mem, "units": "USD"})
    latency3 = round(time.time() - t, 3)

    try:
        obs3 = json.loads(obs3_raw)
        mem_total = round(float(obs3.get("value", mem_total)), 2)
    except Exception:
        pass

    step3 = {
        "step": step_num, "type": "action", "content": thought3,
        "tool": "calculator", "tool_input": {"expression": expr_mem, "units": "USD"},
        "observation": obs3_raw, "latency_s": latency3,
    }
    steps.append(step3)
    yield step3

    # ── STEP 4: LLM synthesizes Final Answer ──────────────────────────────────
    step_num += 1
    decision = "Buy Monthly Membership" if mem_total < ppu_total else "Pay Per Ride/Minute"
    savings = round(abs(ppu_total - mem_total), 2)
    per_week_rides = round(total_rides / 4, 1)
    per_week_cost_ppu = round(ppu_total / 4, 2)

    synthesis_prompt = f"""You are a Citi Bike cost analyst. Write a Final Answer report using ONLY these pre-computed facts:

DATA:
- Total rides this month: {total_rides} (casual rider)
- Average ride duration: {avg_min} minutes
- E-bike rides: {ebike_count}
- Classic bike rides: {classic_rides}
- Pay-Per-Use total cost: ${ppu_total}
- Monthly Membership total cost: ${mem_total}
- Savings with recommended plan: ${savings}
- Decision: {decision}

Write the Final Answer in EXACTLY this format (fill in real numbers from DATA above):

Final Answer:
DECISION: {decision}
JUSTIFICATION: <one paragraph using the numbers above explaining why {decision} is cheaper>
COST BREAKDOWN:
- Pay Per Use total: ${ppu_total}
- Monthly Membership total: ${mem_total}
- Savings with recommended plan: ${savings}
WEEKLY BREAKDOWN:
- Week 1: {per_week_rides} rides, avg {avg_min} min, ${per_week_cost_ppu}
- Week 2: {per_week_rides} rides, avg {avg_min} min, ${per_week_cost_ppu}
- Week 3: {per_week_rides} rides, avg {avg_min} min, ${per_week_cost_ppu}
- Week 4: {per_week_rides} rides, avg {avg_min} min, ${per_week_cost_ppu}
ASSUMPTIONS: Classic ride base price $4.99/30 min; e-bike $4.99 + $0.26/min; membership $19.99/month with 45 min free per classic ride.
CITATION: Citi Bike Pricing page, captured 2026-03-23

Only output the Final Answer block. Do not add anything before or after it."""

    thought4 = f"I have all numbers. Pay-per-use=${ppu_total}, membership=${mem_total}. Decision: {decision}. Now writing the Final Answer."
    t = time.time()
    llm_raw = _call_ollama(synthesis_prompt)
    llm_raw = _sanitize_llm_output(llm_raw)
    latency4 = round(time.time() - t, 3)

    # Extract Final Answer text (LLM may or may not include the "Final Answer:" header)
    if "Final Answer:" in llm_raw:
        final_text = llm_raw[llm_raw.index("Final Answer:") + len("Final Answer:"):].strip()
    else:
        final_text = llm_raw.strip()

    # Guarantee the structured fields are present even if LLM drifts
    if "DECISION:" not in final_text:
        final_text = f"""DECISION: {decision}
JUSTIFICATION: Based on {total_rides} rides this month averaging {avg_min} minutes each, the pay-per-use cost is ${ppu_total} versus ${mem_total} for a monthly membership. {decision} saves ${savings}.
COST BREAKDOWN:
- Pay Per Use total: ${ppu_total}
- Monthly Membership total: ${mem_total}
- Savings with recommended plan: ${savings}
WEEKLY BREAKDOWN:
- Week 1: {per_week_rides} rides, avg {avg_min} min, ${per_week_cost_ppu}
- Week 2: {per_week_rides} rides, avg {avg_min} min, ${per_week_cost_ppu}
- Week 3: {per_week_rides} rides, avg {avg_min} min, ${per_week_cost_ppu}
- Week 4: {per_week_rides} rides, avg {avg_min} min, ${per_week_cost_ppu}
ASSUMPTIONS: Classic ride $4.99/30 min; e-bike $4.99+$0.26/min; membership $19.99/month.
CITATION: Citi Bike Pricing page, captured 2026-03-23"""

    step4 = {
        "step": step_num, "type": "final_answer", "content": final_text,
        "tool": None, "tool_input": None, "observation": None, "latency_s": latency4,
    }
    steps.append(step4)
    yield step4

    total_time = round(time.time() - total_start, 2)
    yield {
        "step": -1, "type": "metadata",
        "total_steps": len(steps),
        "total_time_s": total_time,
        "stop_reason": "max_answer",
        "content": f"Agent completed in {total_time}s over {len(steps)} steps. Stop reason: max_answer",
    }

