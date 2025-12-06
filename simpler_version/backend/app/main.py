import sys
sys.dont_write_bytecode = True

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import json
import re

from nutrition import calculate_bmr, calculate_calories, calculate_macros
from rag import SimpleRAG


def _default_notice(goal: str, calories: int, diet: str) -> str:
    gmap = {
        "fat_loss": "Aim for consistency; gentle deficit works best.",
        "maintenance": "Stay flexible and adjust portions to appetite.",
        "muscle_gain": "Prioritize protein and progressive training."
    }
    tail = gmap.get(goal, "Adjust portions to how you feel and train.")
    return f"This is a starting point around {int(calories)} kcal/day for a {diet} diet. {tail}"


def _parse_json_loose(plan_json: str) -> dict:
    try:
        return json.loads(plan_json)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", plan_json, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def _index_catalog(meals: list[dict]) -> dict:
    """name.lower() -> details (nums as int; lists preserved)"""
    idx = {}
    for m in meals:
        idx[m["name"].lower()] = {
            "name": m["name"],
            "type": m["type"],
            "calories": int(m["calories"]),
            "protein": int(m["protein"]),
            "carbs": int(m["carbs"]),
            "fats": int(m["fats"]),
            "diet": list(m.get("diet", [])),
            "tags": list(m.get("tags", [])),
            "cuisine": m.get("cuisine", ""),
            "allergens": list(m.get("allergens", [])) if isinstance(m.get("allergens"), list) else [],
        }
    return idx


load_dotenv()

app = FastAPI(title="DietPlanner Minimal")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize RAG
rag = SimpleRAG()


class UserProfile(BaseModel):
    age: int
    gender: str
    height_cm: float
    weight_kg: float
    activity: str
    goal: str
    diet_type: str = "omnivore"
    days: int
    exclude: str = ""


@app.get("/")
def root():
    return {"message": "DietPlanner API", "status": "running"}


@app.post("/generate")
def generate_plan(profile: UserProfile):
    """Generate a meal plan with weekly batching"""
    try:
        bmr = calculate_bmr(profile.age, profile.gender, profile.height_cm, profile.weight_kg)
        calories = calculate_calories(bmr, profile.activity, profile.goal)
        macros = calculate_macros(calories, profile.goal, profile.weight_kg)

        base_profile = {
            "goal": profile.goal,
            "calories": int(calories),
            "diet_type": profile.diet_type,
            "exclude": profile.exclude,
            "macros": macros,

        }

        # Retrieve context once
        context_meals = rag.retrieve_meals({**base_profile, "days": 7}, per_type=8)

        # Batch generation (<=7 days per call)
        target_days = max(1, int(profile.days))
        days_accum = []
        used_names = set()
        overall_notice = None

        while len(days_accum) < target_days:
            ask = min(7, target_days - len(days_accum))
            avoid_list = list(used_names)[:60]
            chunk_profile = {**base_profile, "days": ask, "avoid_names": avoid_list}

            plan_json = rag.generate_plan(chunk_profile, context_meals)
            plan_data = _parse_json_loose(plan_json)

            if (overall_notice is None) and isinstance(plan_data.get("notice"), str) and plan_data["notice"].strip():
                overall_notice = plan_data["notice"].strip()

            for d in plan_data.get("days", []):
                for m in d.get("meals", []):
                    if isinstance(m.get("name"), str) and m["name"]:
                        used_names.add(m["name"])
                d = dict(d)
                d["day"] = len(days_accum) + 1
                days_accum.append(d)
                if len(days_accum) >= target_days:
                    break

            if not plan_data.get("days"):
                break

        days_accum = days_accum[:target_days]
        if not overall_notice:
            overall_notice = _default_notice(profile.goal, calories, profile.diet_type)

        # Use the full catalog (not only retrieved ones) to maximize coverage
        catalog_idx = _index_catalog(rag.get_all_meals())

        # ensure we have at least calories for any name
        for d in days_accum:
            for m in d.get("meals", []):
                key = (m.get("name") or "").lower()
                if key not in catalog_idx:
                    catalog_idx[key] = {
                        "name": m.get("name",""),
                        "type": m.get("type",""),
                        "calories": int(m.get("calories", 0)),
                        "protein": 0, "carbs": 0, "fats": 0,
                        "diet": [], "tags": [], "cuisine": "", "allergens": [],
                    }

        day_totals = []
        for d in days_accum:
            totals = {"calories": 0, "protein": 0, "carbs": 0, "fats": 0}
            for m in d.get("meals", []):
                md = catalog_idx.get((m["name"] or "").lower(), {})
                totals["calories"] += int(m.get("calories", md.get("calories", 0)))
                totals["protein"]  += int(md.get("protein", 0))
                totals["carbs"]    += int(md.get("carbs", 0))
                totals["fats"]     += int(md.get("fats", 0))
            day_totals.append(totals)

        avg_cals = round(sum(t["calories"] for t in day_totals) / max(1, len(day_totals)))
        avg_pro  = round(sum(t["protein"]  for t in day_totals) / max(1, len(day_totals)))

        plan_out = {
            "notice": overall_notice,
            "days": days_accum,
            "catalog": catalog_idx,
            "day_totals": day_totals,
            "summary": {"avg_calories": avg_cals, "avg_protein": avg_pro},
        }

        return {
            "success": True,
            "targets": {
                "calories": int(calories),
                "macros": macros,
                "bmr": round(bmr),
            },
            "plan": plan_out,
            "retrieved_meals": context_meals[:5],
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
