import json
from src.image_to_text.image import BankStatementAnalysisResponse

sample_json = '''{
  "meta": {
    "statement_id": "stmt_2024_10_01",
    "currency_code": "INR",
    "currency_symbol": "₹",
    "period": "2024-10",
    "period_label": "October 2024"
  },
  "monthly_cash_flow": {
    "status": "SURPLUS",
    "income": 65000.0,
    "expenses": 38400.0,
    "net_savings": 26600.0,
    "net_savings_rate": 40.9
  },
  "category_breakdown": {
    "active_buckets_count": 5,
    "total_spent": 38400.0,
    "budget_limit": 45000.0,
    "budget_status": "IN_BUDGET",
    "categories": [
      {
        "id": "food",
        "name": "Food",
        "amount": 12288.0,
        "percentage": 32.0,
        "color_hex": "#B8A9FA"
      },
      {
        "id": "rent_bills",
        "name": "Rent/Bills",
        "amount": 10752.0,
        "percentage": 28.0,
        "color_hex": "#8EC5FC"
      },
      {
        "id": "travel",
        "name": "Travel",
        "amount": 6912.0,
        "percentage": 18.0,
        "color_hex": "#6EE7B7"
      },
      {
        "id": "shopping",
        "name": "Shopping",
        "amount": 5376.0,
        "percentage": 14.0,
        "color_hex": "#FCA5A5"
      },
      {
        "id": "other_utilities_subscriptions",
        "name": "Other Utilities & Subscriptions",
        "amount": 3072.0,
        "percentage": 8.0,
        "color_hex": "#FDE047"
      }
    ]
  },
  "spending_trends": {
    "range": "6M",
    "range_label": "Trailing 6 Months",
    "available_ranges": ["3M", "6M", "12M"],
    "highlighted_amount": 38400.0,
    "data_points": [
      {
        "period": "2024-05",
        "label": "May",
        "amount": 32500.0,
        "is_current": false
      },
      {
        "period": "2024-06",
        "label": "Jun",
        "amount": 38500.0,
        "is_current": false
      },
      {
        "period": "2024-07",
        "label": "Jul",
        "amount": 33500.0,
        "is_current": false
      },
      {
        "period": "2024-08",
        "label": "Aug",
        "amount": 40000.0,
        "is_current": false
      },
      {
        "period": "2024-09",
        "label": "Sep",
        "amount": 33500.0,
        "is_current": false
      },
      {
        "period": "2024-10",
        "label": "Oct",
        "amount": 38400.0,
        "is_current": true
      }
    ]
  }
}'''

parsed = BankStatementAnalysisResponse.model_validate_json(sample_json)
print("Schema Validation: SUCCESS")
print("Statement ID:", parsed.meta.statement_id)
print("Total Spent:", parsed.category_breakdown.total_spent)
print("Categories Count:", len(parsed.category_breakdown.categories))
print("Trends Points:", len(parsed.spending_trends.data_points))
