import sys
sys.dont_write_bytecode = True

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

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
    """
    Try to parse the model output as JSON, being forgiving about
    raw newlines / tabs / other control chars inside strings.
    """

    def _sanitize(s: str) -> str:
        # Walk through the text; whenever we're inside a quoted string,
        # turn raw newlines/tabs/control-chars into escaped forms.
        out = []
        in_str = False
        escaped = False

        for ch in s:
            if not in_str:
                out.append(ch)
                if ch == '"':
                    in_str = True
                continue

            # We are inside a string
            if escaped:
                # keep whatever comes after a backslash; json.loads
                # will validate whether it's a legal escape
                out.append(ch)
                escaped = False
                continue

            if ch == '\\':
                out.append(ch)
                escaped = True
            elif ch == '"':
                out.append(ch)
                in_str = False
            elif ord(ch) < 0x20:
                # other control characters -> space
                out.append(" ")
            else:
                out.append(ch)

        return "".join(out)

    # 1) First try raw
    try:
        return json.loads(plan_json)
    except json.JSONDecodeError:
        # 2) Sanitize and try again
        cleaned = _sanitize(plan_json)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # 3) As a last resort, extract the first {...} block
            m = re.search(r"\{.*\}", cleaned, re.S)
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

class GenerateRequest(BaseModel):
    full_name: Optional[str] = None
    profile: UserProfile


@app.get("/")
def root():
    return {"message": "DietPlanner API", "status": "running"}


@app.post("/generate")
def generate_plan(req: GenerateRequest):
    profile = req.profile
    full_name = (req.full_name or "").strip()
    """Generate a meal plan and return only success, title, content."""
    try:
        # 1) Compute targets (used to guide the LLM, not returned)
        bmr = calculate_bmr(profile.age, profile.gender, profile.height_cm, profile.weight_kg)
        calories = calculate_calories(bmr, profile.activity, profile.goal)
        macros = calculate_macros(calories, profile.goal, profile.weight_kg)

        # 2) Build profile for RAG + LLM
        profile_dict = {
            "full_name": full_name, 
            "goal": profile.goal,
            "calories": int(calories),
            "diet_type": profile.diet_type,
            "exclude": profile.exclude,
            "macros": macros,
            "days": profile.days,
        }

        # 3) Retrieve candidate meals
        context_meals = rag.retrieve_meals(profile_dict, per_type=8)

        # 4) Call LLM to get JSON {title, content}
        raw_plan = rag.generate_plan(profile_dict, context_meals)

        # 5) Parse JSON loosely and extract fields
        plan_data = _parse_json_loose(raw_plan)

        title = plan_data.get("title", "Meal Plan")
        content = plan_data.get("content", "")

        return {
            "success": True,
            "title": title,
            "content": content,
        }

    except Exception as e:
        # On error, still follow the same shape
        return {
            "success": False,
            "title": "Error",
            "content": str(e),
        }




if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
