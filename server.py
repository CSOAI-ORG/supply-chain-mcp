#!/usr/bin/env python3
"""
Supply Chain Management MCP Server
====================================
By MEOK AI Labs | https://meok.ai

Supply chain management and logistics tools for AI agents.
Covers shipment tracking, inventory management, supplier scorecards,
demand forecasting, and route optimization.

Install: pip install mcp
Run:     python server.py
"""

import json
import math
import os
import random
import sys
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict
from mcp.server.fastmcp import FastMCP

# ── Authentication ──────────────────────────────────────────────
from auth_middleware import check_access

_MEOK_API_KEY = os.environ.get("MEOK_API_KEY", "")


def _check_auth(api_key: str = "") -> str | None:
    if _MEOK_API_KEY and api_key != _MEOK_API_KEY:
        return "Invalid API key. Get one at https://meok.ai/api-keys"
    return None


# ── Rate limiting ───────────────────────────────────────────────
FREE_DAILY_LIMIT = 10
_usage: dict[str, list[datetime]] = defaultdict(list)


def _rl(caller: str = "anonymous", tier: str = "free") -> Optional[str]:
    if tier == "pro":
        return None
    now = datetime.now()
    cutoff = now - timedelta(days=1)
    _usage[caller] = [t for t in _usage[caller] if t > cutoff]
    if len(_usage[caller]) >= FREE_DAILY_LIMIT:
        return (
            f"Free tier limit ({FREE_DAILY_LIMIT}/day). "
            "Upgrade: https://meok.ai/mcp/supply-chain/pro"
        )
    _usage[caller].append(now)
    return None


# ── In-memory data stores ──────────────────────────────────────

_shipments: dict[str, dict] = {}
_inventory: dict[str, dict] = {}


# ── FastMCP Server ──────────────────────────────────────────────

mcp = FastMCP(
    "supply-chain-mcp",
    instructions=(
        "Supply Chain Management MCP Server by MEOK AI Labs. "
        "Track shipments, manage inventory levels, evaluate supplier performance, "
        "forecast demand, and optimize delivery routes between warehouses."
    ),
)


@mcp.tool()
def track_shipment(
    shipment_id: str,
    action: str = "status",
    origin: str = "",
    destination: str = "",
    carrier: str = "",
    weight_kg: float = 0,
    status: str = "",
    caller: str = "",
    api_key: str = "",
) -> str:
    """Track shipment status. Actions: create, update, status, list."""
    if err := _check_auth(api_key):
        return err
    if err := _rl(caller):
        return err

    action = action.lower()
    now = datetime.now()

    if action == "create":
        if not origin or not destination:
            return json.dumps({"error": "origin and destination required for create"})
        _shipments[shipment_id] = {
            "shipment_id": shipment_id,
            "origin": origin,
            "destination": destination,
            "carrier": carrier or "unassigned",
            "weight_kg": weight_kg,
            "status": "CREATED",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "history": [{"status": "CREATED", "timestamp": now.isoformat(), "location": origin}],
        }
        return json.dumps({"message": f"Shipment {shipment_id} created", "shipment": _shipments[shipment_id]}, indent=2)

    elif action == "update":
        if shipment_id not in _shipments:
            return json.dumps({"error": f"Shipment {shipment_id} not found"})
        s = _shipments[shipment_id]
        new_status = status or s["status"]
        s["status"] = new_status
        s["updated_at"] = now.isoformat()
        s["history"].append({"status": new_status, "timestamp": now.isoformat()})
        if carrier:
            s["carrier"] = carrier
        return json.dumps({"message": f"Shipment {shipment_id} updated", "shipment": s}, indent=2)

    elif action == "status":
        if shipment_id not in _shipments:
            # Generate a simulated status for unknown shipments
            statuses = ["IN_TRANSIT", "AT_WAREHOUSE", "OUT_FOR_DELIVERY", "CUSTOMS_HOLD"]
            sim_status = statuses[hash(shipment_id) % len(statuses)]
            return json.dumps({
                "shipment_id": shipment_id,
                "status": sim_status,
                "simulated": True,
                "note": "Shipment not in local store. Showing simulated status.",
                "estimated_delivery": (now + timedelta(days=3)).strftime("%Y-%m-%d"),
            }, indent=2)
        return json.dumps(_shipments[shipment_id], indent=2)

    elif action == "list":
        return json.dumps({
            "total_shipments": len(_shipments),
            "shipments": list(_shipments.values())[:50],
        }, indent=2)

    return json.dumps({"error": f"Unknown action '{action}'. Use: create, update, status, list"})


@mcp.tool()
def manage_inventory(
    sku: str,
    action: str = "status",
    quantity: int = 0,
    warehouse: str = "main",
    reorder_point: int = 0,
    reorder_quantity: int = 0,
    unit_cost: float = 0,
    caller: str = "",
    api_key: str = "",
) -> str:
    """Manage inventory stock levels and reorder points. Actions: add, remove, status, reorder_check, list."""
    if err := _check_auth(api_key):
        return err
    if err := _rl(caller):
        return err

    action = action.lower()
    now = datetime.now()
    key = f"{sku}:{warehouse}"

    if action == "add":
        if key not in _inventory:
            _inventory[key] = {"sku": sku, "warehouse": warehouse, "quantity": 0,
                               "reorder_point": reorder_point or 10, "reorder_quantity": reorder_quantity or 50,
                               "unit_cost": unit_cost, "last_updated": now.isoformat()}
        _inventory[key]["quantity"] += quantity
        _inventory[key]["last_updated"] = now.isoformat()
        if unit_cost:
            _inventory[key]["unit_cost"] = unit_cost
        if reorder_point:
            _inventory[key]["reorder_point"] = reorder_point
        return json.dumps({"message": f"Added {quantity} units of {sku}", "inventory": _inventory[key]}, indent=2)

    elif action == "remove":
        if key not in _inventory:
            return json.dumps({"error": f"SKU {sku} not found in {warehouse}"})
        inv = _inventory[key]
        if inv["quantity"] < quantity:
            return json.dumps({"error": f"Insufficient stock. Available: {inv['quantity']}, Requested: {quantity}"})
        inv["quantity"] -= quantity
        inv["last_updated"] = now.isoformat()
        alert = inv["quantity"] <= inv["reorder_point"]
        result = {"message": f"Removed {quantity} units of {sku}", "inventory": inv}
        if alert:
            result["reorder_alert"] = f"Stock below reorder point ({inv['reorder_point']}). Reorder {inv['reorder_quantity']} units."
        return json.dumps(result, indent=2)

    elif action == "status":
        if key not in _inventory:
            return json.dumps({"sku": sku, "warehouse": warehouse, "status": "NOT_FOUND"})
        inv = _inventory[key]
        days_of_stock = inv["quantity"] / max(1, inv.get("daily_usage", 5))
        return json.dumps({**inv, "estimated_days_of_stock": round(days_of_stock, 1),
                           "below_reorder_point": inv["quantity"] <= inv["reorder_point"]}, indent=2)

    elif action == "reorder_check":
        alerts = []
        for k, inv in _inventory.items():
            if inv["quantity"] <= inv["reorder_point"]:
                alerts.append({"sku": inv["sku"], "warehouse": inv["warehouse"],
                               "current_stock": inv["quantity"], "reorder_point": inv["reorder_point"],
                               "suggested_order": inv["reorder_quantity"],
                               "estimated_cost": round(inv["reorder_quantity"] * inv.get("unit_cost", 0), 2)})
        return json.dumps({"reorder_alerts": alerts, "total_alerts": len(alerts)}, indent=2)

    elif action == "list":
        items = list(_inventory.values())[:100]
        total_value = sum(i["quantity"] * i.get("unit_cost", 0) for i in items)
        return json.dumps({"total_skus": len(_inventory), "total_inventory_value": round(total_value, 2),
                           "items": items}, indent=2)

    return json.dumps({"error": f"Unknown action '{action}'. Use: add, remove, status, reorder_check, list"})


@mcp.tool()
def supplier_scorecard(
    supplier_name: str,
    on_time_delivery_pct: float = 0,
    quality_defect_rate_pct: float = 0,
    price_competitiveness: float = 0,
    responsiveness_days: float = 0,
    compliance_score: float = 0,
    financial_stability: float = 0,
    caller: str = "",
    api_key: str = "",
) -> str:
    """Generate a supplier performance scorecard with weighted rating."""
    if err := _check_auth(api_key):
        return err
    if err := _rl(caller):
        return err

    weights = {
        "on_time_delivery": 0.25,
        "quality": 0.25,
        "price": 0.20,
        "responsiveness": 0.10,
        "compliance": 0.10,
        "financial_stability": 0.10,
    }

    # Normalize scores to 0-100
    delivery_score = min(100, max(0, on_time_delivery_pct))
    quality_score = min(100, max(0, 100 - quality_defect_rate_pct * 10))  # Lower defect = higher score
    price_score = min(100, max(0, price_competitiveness))
    response_score = min(100, max(0, 100 - responsiveness_days * 10))  # Fewer days = higher score
    compliance_normalized = min(100, max(0, compliance_score))
    financial_normalized = min(100, max(0, financial_stability))

    scores = {
        "on_time_delivery": {"raw": on_time_delivery_pct, "normalized": round(delivery_score, 1), "weight": weights["on_time_delivery"]},
        "quality": {"raw_defect_rate": quality_defect_rate_pct, "normalized": round(quality_score, 1), "weight": weights["quality"]},
        "price_competitiveness": {"raw": price_competitiveness, "normalized": round(price_score, 1), "weight": weights["price"]},
        "responsiveness": {"raw_days": responsiveness_days, "normalized": round(response_score, 1), "weight": weights["responsiveness"]},
        "compliance": {"raw": compliance_score, "normalized": round(compliance_normalized, 1), "weight": weights["compliance"]},
        "financial_stability": {"raw": financial_stability, "normalized": round(financial_normalized, 1), "weight": weights["financial_stability"]},
    }

    weighted_total = (
        delivery_score * weights["on_time_delivery"] +
        quality_score * weights["quality"] +
        price_score * weights["price"] +
        response_score * weights["responsiveness"] +
        compliance_normalized * weights["compliance"] +
        financial_normalized * weights["financial_stability"]
    )

    if weighted_total >= 85:
        rating = "PREFERRED"
    elif weighted_total >= 70:
        rating = "APPROVED"
    elif weighted_total >= 50:
        rating = "CONDITIONAL"
    else:
        rating = "AT_RISK"

    return json.dumps({
        "supplier": supplier_name,
        "assessment_date": datetime.now().isoformat(),
        "overall_score": round(weighted_total, 1),
        "rating": rating,
        "scores": scores,
        "recommendations": _supplier_recommendations(scores, rating),
    }, indent=2)


def _supplier_recommendations(scores: dict, rating: str) -> list[str]:
    recs = []
    if scores["on_time_delivery"]["normalized"] < 80:
        recs.append("Improve delivery reliability - consider contractual delivery SLAs")
    if scores["quality"]["normalized"] < 80:
        recs.append("Address quality issues - implement incoming quality inspection")
    if scores["responsiveness"]["normalized"] < 60:
        recs.append("Response time too slow - establish communication SLAs")
    if scores["compliance"]["normalized"] < 70:
        recs.append("Compliance gaps detected - request updated certifications")
    if rating == "AT_RISK":
        recs.append("URGENT: Begin sourcing alternative suppliers")
    return recs


@mcp.tool()
def demand_forecast(
    product_name: str,
    historical_sales: str = "",
    seasonality: str = "none",
    forecast_periods: int = 6,
    growth_rate_pct: float = 0,
    caller: str = "",
    api_key: str = "",
) -> str:
    """Generate basic demand prediction using moving average and growth trends."""
    if err := _check_auth(api_key):
        return err
    if err := _rl(caller):
        return err

    # Parse historical sales (comma-separated numbers)
    try:
        sales = [float(x.strip()) for x in historical_sales.split(",") if x.strip()] if historical_sales else []
    except ValueError:
        return json.dumps({"error": "historical_sales must be comma-separated numbers"})

    if len(sales) < 3:
        sales = [100, 110, 105, 120, 115, 130, 125, 140, 135, 150, 145, 160]

    # Simple moving average (last 3 periods)
    window = min(3, len(sales))
    sma = sum(sales[-window:]) / window

    # Seasonal multipliers
    seasonal_factors = {
        "none": [1.0] * 12,
        "retail": [0.8, 0.7, 0.9, 0.9, 1.0, 1.0, 0.9, 1.0, 1.1, 1.1, 1.3, 1.5],
        "summer": [0.7, 0.8, 0.9, 1.0, 1.2, 1.4, 1.5, 1.4, 1.1, 0.9, 0.7, 0.6],
        "winter": [1.3, 1.2, 1.0, 0.8, 0.7, 0.6, 0.6, 0.7, 0.9, 1.0, 1.2, 1.4],
        "flat": [1.0] * 12,
    }
    factors = seasonal_factors.get(seasonality.lower(), seasonal_factors["none"])

    growth_mult = 1 + (growth_rate_pct / 100)
    forecasts = []
    current_month = datetime.now().month
    for i in range(forecast_periods):
        month_idx = (current_month + i) % 12
        period_forecast = sma * factors[month_idx] * (growth_mult ** (i + 1))
        forecasts.append({
            "period": i + 1,
            "month": (datetime.now() + timedelta(days=30 * (i + 1))).strftime("%Y-%m"),
            "forecast": round(period_forecast, 0),
            "seasonal_factor": factors[month_idx],
        })

    avg_forecast = sum(f["forecast"] for f in forecasts) / len(forecasts)
    total_forecast = sum(f["forecast"] for f in forecasts)

    return json.dumps({
        "product": product_name,
        "method": "Simple Moving Average with Seasonal Adjustment",
        "historical_periods": len(sales),
        "sma_base": round(sma, 1),
        "seasonality": seasonality,
        "growth_rate_pct": growth_rate_pct,
        "forecast_periods": forecast_periods,
        "forecasts": forecasts,
        "summary": {
            "average_per_period": round(avg_forecast, 0),
            "total_forecast": round(total_forecast, 0),
            "trend": "GROWING" if growth_rate_pct > 0 else "DECLINING" if growth_rate_pct < 0 else "STABLE",
        },
    }, indent=2)


@mcp.tool()
def optimize_routing(
    warehouses: str,
    distances: str = "",
    vehicle_capacity_kg: float = 1000,
    total_load_kg: float = 500,
    caller: str = "",
    api_key: str = "",
) -> str:
    """Optimize delivery routes between warehouses using nearest-neighbor heuristic."""
    if err := _check_auth(api_key):
        return err
    if err := _rl(caller):
        return err

    wh_list = [w.strip() for w in warehouses.split(",") if w.strip()]
    if len(wh_list) < 2:
        return json.dumps({"error": "At least 2 warehouses required"})

    # Parse distance matrix or generate based on warehouse count
    dist_matrix: dict[tuple[str, str], float] = {}
    if distances:
        pairs = [d.strip() for d in distances.split(";") if d.strip()]
        for pair in pairs:
            parts = pair.split(":")
            if len(parts) == 2:
                locs = parts[0].split("-")
                if len(locs) == 2:
                    dist = float(parts[1])
                    dist_matrix[(locs[0].strip(), locs[1].strip())] = dist
                    dist_matrix[(locs[1].strip(), locs[0].strip())] = dist
    else:
        # Generate deterministic pseudo-distances
        for i, w1 in enumerate(wh_list):
            for j, w2 in enumerate(wh_list):
                if i != j:
                    seed = hash(f"{w1}-{w2}") % 1000
                    dist_matrix[(w1, w2)] = 50 + (seed % 200)

    # Nearest neighbor heuristic
    unvisited = set(wh_list[1:])
    route = [wh_list[0]]
    total_distance = 0

    current = wh_list[0]
    while unvisited:
        nearest = None
        nearest_dist = float("inf")
        for wh in unvisited:
            d = dist_matrix.get((current, wh), 999)
            if d < nearest_dist:
                nearest = wh
                nearest_dist = d
        if nearest:
            route.append(nearest)
            total_distance += nearest_dist
            unvisited.remove(nearest)
            current = nearest

    # Return to start
    return_dist = dist_matrix.get((current, wh_list[0]), 0)
    total_distance += return_dist
    route.append(wh_list[0])

    trips_needed = math.ceil(total_load_kg / vehicle_capacity_kg)

    legs = []
    for i in range(len(route) - 1):
        d = dist_matrix.get((route[i], route[i + 1]), 0)
        legs.append({"from": route[i], "to": route[i + 1], "distance_km": round(d, 1)})

    return json.dumps({
        "algorithm": "Nearest Neighbor Heuristic",
        "warehouses": wh_list,
        "optimized_route": route,
        "route_legs": legs,
        "total_distance_km": round(total_distance, 1),
        "vehicle_capacity_kg": vehicle_capacity_kg,
        "total_load_kg": total_load_kg,
        "trips_needed": trips_needed,
        "estimated_fuel_cost": round(total_distance * 0.15 * trips_needed, 2),
        "note": "Nearest-neighbor provides good approximation. Optimal solution requires TSP solver.",
    }, indent=2)


def main():
    mcp.run()


if __name__ == "__main__":
    main()


# ── MEOK monetization layer (Stripe upgrade · PAYG · pricing) ──────────
# Free tier is zero-config. Upgrade to Pro (unlimited) or pay-as-you-go per call.
import os as _meok_os
MEOK_STRIPE_UPGRADE = "https://buy.stripe.com/5kQ6oJ0xS3ce8sl7ew8k91j"  # Pro (unlimited)
MEOK_PAYG_KEY = _meok_os.environ.get("MEOK_PAYG_KEY", "")  # set to enable PAYG (x402 / ~GBP0.05 per call)
MEOK_PRICING = "https://meok.ai/pricing"


def meok_upsell(tier: str = "free") -> dict:
    """Monetization options for free-tier callers: Pro upgrade, PAYG, or pricing page."""
    if tier != "free":
        return {}
    return {"upgrade_url": MEOK_STRIPE_UPGRADE,
            "payg_enabled": bool(MEOK_PAYG_KEY),
            "pricing": MEOK_PRICING}
