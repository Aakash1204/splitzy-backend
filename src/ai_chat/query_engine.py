from datetime import date, timedelta
from decimal import Decimal
import json
import re
from typing import Any
import uuid
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai_chat.tools import FinancialTools
from src.core.config import settings

GEMINI_TOOLS_SCHEMA = [
    {
        "function_declarations": [
            {
                "name": "get_spend_by_category",
                "description": "Calculates total debit spend grouped by category, optionally filtered by date range and category name.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "start_date": {"type": "STRING", "description": "Start date in YYYY-MM-DD"},
                        "end_date": {"type": "STRING", "description": "End date in YYYY-MM-DD"},
                        "category": {"type": "STRING", "description": "Optional category name e.g. FOOD, TRAVEL, GROCERIES"},
                    },
                },
            },
            {
                "name": "get_spend_by_merchant",
                "description": "Calculates total debit spend for a specific merchant or merchant keyword.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "merchant_query": {"type": "STRING", "description": "Merchant name or search query e.g. Swiggy, Uber"},
                        "start_date": {"type": "STRING", "description": "Start date in YYYY-MM-DD"},
                        "end_date": {"type": "STRING", "description": "End date in YYYY-MM-DD"},
                    },
                },
            },
            {
                "name": "compare_periods",
                "description": "Compares spending between two date ranges (e.g., this month vs last month).",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "period1_start": {"type": "STRING", "description": "Start date of first period in YYYY-MM-DD"},
                        "period1_end": {"type": "STRING", "description": "End date of first period in YYYY-MM-DD"},
                        "period2_start": {"type": "STRING", "description": "Start date of second period in YYYY-MM-DD"},
                        "period2_end": {"type": "STRING", "description": "End date of second period in YYYY-MM-DD"},
                        "category": {"type": "STRING", "description": "Optional category filter"},
                    },
                    "required": ["period1_start", "period1_end", "period2_start", "period2_end"],
                },
            },
            {
                "name": "get_top_merchants",
                "description": "Gets top 5 merchants ranked by spend or visit frequency.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "sort_by": {"type": "STRING", "description": "'spend' or 'visits'"},
                        "start_date": {"type": "STRING", "description": "Start date in YYYY-MM-DD"},
                        "end_date": {"type": "STRING", "description": "End date in YYYY-MM-DD"},
                    },
                },
            },
            {
                "name": "get_cashflow_summary",
                "description": "Calculates total income inflows, debit outflows, net savings, and savings rate percentage.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "start_date": {"type": "STRING", "description": "Start date in YYYY-MM-DD"},
                        "end_date": {"type": "STRING", "description": "End date in YYYY-MM-DD"},
                    },
                },
            },
            {
                "name": "get_active_anomalies",
                "description": "Lists unreviewed spending anomalies such as double charges, large outliers, or category spikes.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {},
                },
            },
        ]
    }
]


class QueryEngine:
    @classmethod
    async def execute_tool(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        tool_name: str,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        """Dispatches to the deterministic FinancialTools functions."""
        def parse_d(val: Any) -> date | None:
            if not val or not isinstance(val, str):
                return None
            try:
                return date.fromisoformat(val)
            except Exception:
                return None

        if tool_name == "get_spend_by_category":
            return await FinancialTools.get_spend_by_category(
                db=db,
                user_id=user_id,
                start_date=parse_d(args.get("start_date")),
                end_date=parse_d(args.get("end_date")),
                category=args.get("category"),
            )
        elif tool_name == "get_spend_by_merchant":
            return await FinancialTools.get_spend_by_merchant(
                db=db,
                user_id=user_id,
                start_date=parse_d(args.get("start_date")),
                end_date=parse_d(args.get("end_date")),
                merchant_query=args.get("merchant_query"),
            )
        elif tool_name == "compare_periods":
            p1_s = parse_d(args.get("period1_start")) or (date.today() - timedelta(days=60))
            p1_e = parse_d(args.get("period1_end")) or (date.today() - timedelta(days=31))
            p2_s = parse_d(args.get("period2_start")) or (date.today() - timedelta(days=30))
            p2_e = parse_d(args.get("period2_end")) or date.today()
            return await FinancialTools.compare_periods(
                db=db,
                user_id=user_id,
                period1_start=p1_s,
                period1_end=p1_e,
                period2_start=p2_s,
                period2_end=p2_e,
                category=args.get("category"),
            )
        elif tool_name == "get_top_merchants":
            return await FinancialTools.get_top_merchants(
                db=db,
                user_id=user_id,
                start_date=parse_d(args.get("start_date")),
                end_date=parse_d(args.get("end_date")),
                sort_by=args.get("sort_by", "spend"),
            )
        elif tool_name == "get_cashflow_summary":
            return await FinancialTools.get_cashflow_summary(
                db=db,
                user_id=user_id,
                start_date=parse_d(args.get("start_date")),
                end_date=parse_d(args.get("end_date")),
            )
        elif tool_name == "get_active_anomalies":
            return await FinancialTools.get_active_anomalies(
                db=db,
                user_id=user_id,
            )
        else:
            return {"error": f"Unknown tool {tool_name}"}

    @classmethod
    async def process_query_fallback(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        message: str,
    ) -> tuple[str, dict[str, Any]]:
        """
        Deterministic rule-based query classifier and synthesizer when Gemini API
        is not configured, offline, or for unit/integration testing.
        """
        msg = message.lower()

        # 1. Comparison query
        if any(w in msg for w in ["compare", "vs", "versus", "more than", "increase", "decrease"]):
            today = date.today()
            this_month_start = today.replace(day=1)
            last_month_end = this_month_start - timedelta(days=1)
            last_month_start = last_month_end.replace(day=1)

            # Check category keyword
            cat = None
            for candidate in ["food", "travel", "groceries", "shopping", "utilities", "rent"]:
                if candidate in msg:
                    cat = candidate.upper()
                    break

            res = await FinancialTools.compare_periods(
                db=db,
                user_id=user_id,
                period1_start=last_month_start,
                period1_end=last_month_end,
                period2_start=this_month_start,
                period2_end=today,
                category=cat,
            )

            p1_spend = res["period1"]["spend"]
            p2_spend = res["period2"]["spend"]
            pct = res["percentage_change"]
            cat_str = f"on {cat} " if cat else ""

            if p2_spend > p1_spend:
                content = (
                    f"You spent {cat_str}₹{p2_spend:,.2f} this period compared to ₹{p1_spend:,.2f} previously "
                    f"— an increase of {abs(pct):.1f}% (+₹{res['difference']:,.2f})."
                )
            else:
                content = (
                    f"You spent {cat_str}₹{p2_spend:,.2f} this period compared to ₹{p1_spend:,.2f} previously "
                    f"— a reduction of {abs(pct):.1f}% (-₹{abs(res['difference']):,.2f})."
                )

            structured_payload = {
                "type": "comparison_bars",
                "title": f"Spend Comparison {f'({cat})' if cat else ''}",
                "period1_label": f"{last_month_start.strftime('%b %Y')}",
                "period1_amount": p1_spend,
                "period2_label": f"{this_month_start.strftime('%b %Y')}",
                "period2_amount": p2_spend,
                "percentage_change": pct,
            }
            return content, structured_payload

        # 2. Specific Merchant query
        for merchant_kw in ["swiggy", "zomato", "uber", "ola", "blinkit", "zepto", "amazon", "netflix", "makemytrip"]:
            if merchant_kw in msg:
                res = await FinancialTools.get_spend_by_merchant(db, user_id, merchant_query=merchant_kw)
                total = res["total_spend"]
                count = sum(m["transactions_count"] for m in res["merchants"])
                name = res["merchants"][0]["merchant"] if res["merchants"] else merchant_kw.capitalize()

                content = (
                    f"You have spent a total of ₹{total:,.2f} at {name} across {count} transaction(s)."
                )
                structured_payload = {
                    "type": "merchant_summary",
                    "merchant": name,
                    "total_spend": total,
                    "transaction_count": count,
                }
                return content, structured_payload

        # 3. Top Merchants query
        if any(w in msg for w in ["top merchant", "top merchants", "where did i spend most", "frequent"]):
            sort_by = "visits" if "visit" in msg or "frequent" in msg else "spend"
            res = await FinancialTools.get_top_merchants(db, user_id, sort_by=sort_by)
            top = res["top_merchants"]
            if not top:
                return "You have no debit transactions recorded yet.", {"type": "top_merchants", "items": []}

            lead = top[0]
            content = (
                f"Your top merchant by {sort_by} is {lead['merchant']} (₹{lead['total_spend']:,.2f} "
                f"across {lead['visits']} transactions), followed by {', '.join(m['merchant'] for m in top[1:])}."
            )
            structured_payload = {
                "type": "top_merchants_list",
                "sort_by": sort_by,
                "items": top,
            }
            return content, structured_payload

        # 4. Cashflow / Savings query
        if any(w in msg for w in ["cashflow", "savings", "saving", "income", "inflow", "salary"]):
            res = await FinancialTools.get_cashflow_summary(db, user_id)
            content = (
                f"Your total income is ₹{res['inflows']:,.2f} and total expenses are ₹{res['outflows']:,.2f}, "
                f"leaving net savings of ₹{res['net_savings']:,.2f} (Savings Rate: {res['savings_rate']:.1f}%)."
            )
            structured_payload = {
                "type": "cashflow_cards",
                "inflows": res["inflows"],
                "outflows": res["outflows"],
                "net_savings": res["net_savings"],
                "savings_rate": res["savings_rate"],
            }
            return content, structured_payload

        # 5. Anomalies query
        if any(w in msg for w in ["anomaly", "anomalies", "fraud", "suspicious", "double charge", "alert"]):
            res = await FinancialTools.get_active_anomalies(db, user_id)
            count = res["total_anomalies"]
            if count == 0:
                content = "Great news! There are currently no active anomalies or suspicious transactions detected."
            else:
                anom_descriptions = [f"{a['type']} at {a['merchant']} (₹{a['amount']})" for a in res["anomalies"][:3]]
                content = f"You have {count} active anomaly alert(s): {', '.join(anom_descriptions)}."
            structured_payload = {
                "type": "anomalies_list",
                "count": count,
                "items": res["anomalies"],
            }
            return content, structured_payload

        # 6. Default: Category breakdown
        res = await FinancialTools.get_spend_by_category(db, user_id)
        total = res["total_spend"]
        breakdown = res["breakdown"]

        if not breakdown:
            return "You do not have any recorded expenses yet.", {"type": "category_breakdown", "items": []}

        top_cats = [f"{b['category']}: ₹{b['amount']:,.2f}" for b in breakdown[:3]]
        content = (
            f"Your total spending is ₹{total:,.2f}. Your top spending categories are {', '.join(top_cats)}."
        )
        structured_payload = {
            "type": "category_breakdown",
            "total_spend": total,
            "items": breakdown,
        }
        return content, structured_payload

    @classmethod
    async def query(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        message: str,
    ) -> tuple[str, dict[str, Any] | None]:
        """
        Executes query with Gemini API tool-calling if key is present;
        otherwise runs deterministic tool query planner.
        """
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            return await cls.process_query_fallback(db, user_id, message)

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"

        system_instruction = (
            "You are Splitzy AI, an expert personal finance assistant. "
            "CRITICAL ACCURACY RULE: Never calculate sums or spend totals yourself. "
            "Always call the provided tools to query exact SQL data for the user. "
            "Provide a concise, helpful summary in prose and return a clean structured payload."
        )

        contents = [{"role": "user", "parts": [{"text": message}]}]

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                req_body = {
                    "contents": contents,
                    "tools": GEMINI_TOOLS_SCHEMA,
                    "systemInstruction": {"parts": [{"text": system_instruction}]},
                }
                resp = await client.post(url, json=req_body)
                if resp.status_code != 200:
                    return await cls.process_query_fallback(db, user_id, message)

                resp_data = resp.json()
                candidate = resp_data.get("candidates", [{}])[0]
                content_obj = candidate.get("content", {})
                parts = content_obj.get("parts", [])

                function_calls = [p["functionCall"] for p in parts if "functionCall" in p]

                if not function_calls:
                    # Return natural language text from Gemini with fallback payload
                    text_parts = [p["text"] for p in parts if "text" in p]
                    plain_text = " ".join(text_parts).strip()
                    _, payload = await cls.process_query_fallback(db, user_id, message)
                    return plain_text or "Here is your requested financial insight.", payload

                # Execute tool calls
                tool_results = []
                for fc in function_calls:
                    t_name = fc["name"]
                    t_args = fc.get("args", {})
                    t_res = await cls.execute_tool(db, user_id, t_name, t_args)
                    tool_results.append((t_name, t_res))

                # Feed tool results back to Gemini for final response
                function_response_parts = [
                    {
                        "functionResponse": {
                            "name": t_name,
                            "response": {"result": t_res},
                        }
                    }
                    for t_name, t_res in tool_results
                ]

                followup_contents = [
                    {"role": "user", "parts": [{"text": message}]},
                    {"role": "model", "parts": parts},
                    {"role": "user", "parts": function_response_parts},
                ]

                followup_resp = await client.post(
                    url,
                    json={
                        "contents": followup_contents,
                        "systemInstruction": {"parts": [{"text": system_instruction}]},
                    },
                )

                if followup_resp.status_code == 200:
                    f_data = followup_resp.json()
                    f_parts = f_data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                    final_text = " ".join(p["text"] for p in f_parts if "text" in p).strip()
                    # Return final text + structured payload from primary tool result
                    primary_tool_res = tool_results[0][1] if tool_results else None
                    return final_text, primary_tool_res
                else:
                    return await cls.process_query_fallback(db, user_id, message)

        except Exception:
            return await cls.process_query_fallback(db, user_id, message)
