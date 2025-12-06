import os 
import json
from typing import List, Dict, Any

import chromadb
from chromadb.utils import embedding_functions
from openai import OpenAI


MEAL_TYPES = ["breakfast", "lunch", "snack", "dinner"]


class SimpleRAG:
    def __init__(self, meals_file: str | None = None):
        self.meals_file = os.getenv("MEALS_FILE")

        # In-memory catalog (as loaded from JSON file)
        self._meals: List[Dict[str, Any]] = self._load_meals_file()

        # Embedding + Chroma
        self.embed_fn = embedding_functions.DefaultEmbeddingFunction()
        self.chroma = chromadb.Client()
        self.collection = self.chroma.create_collection(
            name="meals",
            embedding_function=self.embed_fn
        )

        self._load_meals_into_collection(self._meals)

    def reload(self):
        """Reload meals from file and rebuild the vector store."""
        self._meals = self._load_meals_file()
        self._load_meals_into_collection(self._meals)

    def get_all_meals(self) -> List[Dict[str, Any]]:
        """Return the full meal catalog as loaded from JSON."""
        return list(self._meals)

    def _load_meals_file(self) -> List[Dict[str, Any]]:
        path = self.meals_file

        if os.path.isdir(path):
            # Directory mode: merge all *.json files
            all_meals: list[dict] = []
            for fname in sorted(os.listdir(path)):
                if not fname.lower().endswith(".json"):
                    continue
                fpath = os.path.join(path, fname)
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, list):
                    raise ValueError(f"{fpath} must be a JSON array")
                all_meals.extend(data)
            data = all_meals

        # normalization and sanity checks
        out: list[dict] = []
        for m in data:
            for k in ["id", "name", "type", "calories", "protein", "carbs", "fats"]:
                if k not in m:
                    raise ValueError(f"Meal is missing field '{k}': {m}")
                
            m["type"] = str(m["type"]).lower()
            if isinstance(m.get("diet"), list):
                m["diet"] = [str(d).lower() for d in m["diet"]]
            out.append(m)

        return out


    def _meal_doc(self, m: dict) -> str:
        diets = ", ".join(m.get("diet", []))
        tags = ", ".join(m.get("tags", []))
        cuisine = m.get("cuisine", "")
        allergens = ", ".join(m.get("allergens", [])) if isinstance(m.get("allergens"), list) else str(m.get("allergens",""))
        return (
            f"{m['name']} — {m['type']} — {m['calories']} kcal, "
            f"{m['protein']}g protein, {m['carbs']}g carbs, {m['fats']}g fats. "
            f"Cuisine: {cuisine}. Diets: {diets}. Tags: {tags}. Allergens: {allergens}."
        )

    def _load_meals_into_collection(self, meals: List[dict]):
        try:
            self.collection.delete(where={})
        except Exception:
            pass

        ids, docs, metas = [], [], []
        for m in meals:
            ids.append(m["id"])
            docs.append(self._meal_doc(m))
            metas.append({
                "id": m["id"],
                "name": m["name"],
                "type": m["type"],
                "calories": int(m["calories"]),
                "protein": int(m["protein"]),
                "carbs": int(m["carbs"]),
                "fats": int(m["fats"]),
                "diet": ", ".join(m.get("diet", [])),
                "tags": ", ".join(m.get("tags", [])),
                "cuisine": m.get("cuisine", ""),
                "allergens": ", ".join(m.get("allergens", [])) if isinstance(m.get("allergens"), list) else str(m.get("allergens","")),
                # optional numeric helpers if present in your JSON
                "protein_share": float(m.get("protein_share", 0.0)),
                "protein_density": float(m.get("protein_density", 0.0)),
            })
        if ids:
            self.collection.add(ids=ids, documents=docs, metadatas=metas)

    def _diet_allowlist(self, diet_type: str) -> set[str]:
        """
        Which meal diet labels are acceptable for a given user diet.
        """
        diet_type = (diet_type or "omnivore").lower()

        mapping = {
            "omnivore": {"omnivore", "pescatarian", "vegetarian", "vegan", "gluten_free"},
            "pescatarian": {"pescatarian", "vegetarian", "vegan", "gluten_free"},
            "vegetarian": {"vegetarian", "vegan", "gluten_free"},
            "vegan": {"vegan", "gluten_free"},
            "gluten_free": {"gluten_free", "omnivore", "pescatarian", "vegetarian", "vegan"},
        }
        return mapping.get(diet_type, mapping["omnivore"])


    def _score_meal(
        self,
        target_cal: float,
        target_pro: float,
        meal: dict,
        goal: str,
        preferred_tags: set[str],
    ) -> float:
        """
        Lower score = better. Combines calorie distance, protein shortfall,
        goal-aware bonuses/penalties, and a tiny bias toward more protein.
        """
        cal = float(meal.get("calories") or 0)
        pro = float(meal.get("protein") or 0)

        # macro distance penalties 
        if target_cal > 0:
            cal_penalty = abs(cal - target_cal) / target_cal
        else:
            cal_penalty = 0.0

        if target_pro > 0 and pro < target_pro:
            pro_penalty = (target_pro - pro) / target_pro
        else:
            pro_penalty = 0.0

        goal = (goal or "maintenance").lower()
        if goal == "fat_loss":
            w_cal, w_pro = 0.6, 0.4
        elif goal == "muscle_gain":
            w_cal, w_pro = 0.4, 0.6
        else:
            w_cal, w_pro = 0.5, 0.5

        score = w_cal * cal_penalty + w_pro * pro_penalty

        tags = set(meal.get("tags") or [])

        # tag bonus
        if preferred_tags & tags:
            score -= 0.15

        # goal specific updates to the score
        if goal == "fat_loss" and cal > target_cal:
            # overweight meals are less desirable for fat loss
            score += 0.15

        if goal == "muscle_gain":
            pd = meal.get("protein_density")
            try:
                pd = float(pd) if pd is not None else None
            except ValueError:
                pd = None
            if pd is not None:
                score -= 0.3 * min(pd, 0.25)

        # 4) more protein is slightly better
        score -= pro * 0.001

        return score


    def _csv_set(self, md: dict, key: str) -> set:
        raw = md.get(key, "")
        if isinstance(raw, list):
            return {str(x).strip() for x in raw if str(x).strip()}
        return {t.strip() for t in str(raw).split(",") if t.strip()}

    def _has_tag(self, md: dict, tag: str) -> bool:
        return tag in self._csv_set(md, "tags")

    def retrieve_meals(self, profile: dict, per_type: int = 8) -> List[dict]:
        """
        Retrieve candidate meals per type with:
        - goal targets,
        - diet/exclusion filters,
        - semantic query using goal + diet + calories,
        - unified scoring.
        """
        if isinstance(profile, str):
            profile = {"goal": "maintenance", "calories": 2000, "diet_type": profile}

        goal = (profile.get("goal") or "maintenance").lower()
        diet_type = (profile.get("diet_type") or "omnivore").lower()
        calories = float(profile.get("calories") or 2000)

        macros = profile.get("macros") or {}
        daily_pro = float(
            macros.get("plan_protein_g")
            or macros.get("protein_g")
            or 0
        )

        allow_diets = self._diet_allowlist(diet_type)

        # Per-meal type calorie/protein targets (fractions of daily total)
        if daily_pro > 0:
            targets = {
                "breakfast": {"cal": 0.25 * calories, "pro": 0.20 * daily_pro},
                "lunch":     {"cal": 0.30 * calories, "pro": 0.30 * daily_pro},
                "snack":     {"cal": 0.15 * calories, "pro": 0.15 * daily_pro},
                "dinner":    {"cal": 0.30 * calories, "pro": 0.35 * daily_pro},
            }
        else:
            # fallback: only calories
            targets = {
                "breakfast": {"cal": 0.25 * calories, "pro": 0.0},
                "lunch":     {"cal": 0.35 * calories, "pro": 0.0},
                "snack":     {"cal": 0.10 * calories, "pro": 0.0},
                "dinner":    {"cal": 0.30 * calories, "pro": 0.0},
            }

        # Exclusion terms
        exclude_raw = profile.get("exclude") or ""
        exclude_terms = {
            t.strip().lower()
            for t in exclude_raw.replace(";", ",").split(",")
            if t.strip()
        }

        # Goal-specific minimum proteins and preferred tags
        min_protein_by_type: dict[str, dict[str, float]] = {
            "muscle_gain": {
                "breakfast":  max(20.0, 0.18 * daily_pro),
                "lunch":      max(30.0, 0.28 * daily_pro),
                "snack":      max(15.0, 0.12 * daily_pro),
                "dinner":     max(35.0, 0.30 * daily_pro),
            },
            "fat_loss": {
                "breakfast":  max(18.0, 0.20 * daily_pro),
                "lunch":      max(25.0, 0.25 * daily_pro),
                "snack":      max(12.0, 0.12 * daily_pro),
                "dinner":     max(28.0, 0.28 * daily_pro),
            },
            "maintenance": {
                "breakfast":  max(15.0, 0.16 * daily_pro),
                "lunch":      max(22.0, 0.22 * daily_pro),
                "snack":      max(10.0, 0.10 * daily_pro),
                "dinner":     max(25.0, 0.24 * daily_pro),
            },
        }
        min_protein_for_goal = min_protein_by_type.get(goal, min_protein_by_type["maintenance"])

        if goal == "muscle_gain":
            preferred_tags = {"high_protein", "breakfast_protein"}
        elif goal == "fat_loss":
            preferred_tags = {"low_carb", "low_fat"}
        else:
            preferred_tags = set()

        selected_all: list[dict] = []
        seen_ids: set[str] = set()

        for mtype in MEAL_TYPES:
            target = targets.get(mtype, {"cal": calories / 4.0, "pro": daily_pro / 4.0})
            target_cal = target["cal"]
            target_pro = target["pro"]
            min_pro = min_protein_for_goal.get(mtype, 0.0)

            # Build richer query text for Chroma
            query_parts = []

            if goal == "muscle_gain":
                query_parts.append("high protein")
            elif goal == "fat_loss":
                query_parts.append("lower calorie balanced")

            query_parts.append(diet_type)
            query_parts.append(mtype)

            if target_cal:
                query_parts.append(f"around {int(target_cal)} calories")

            if exclude_terms:
                query_parts.append("avoid " + ", ".join(sorted(exclude_terms)))

            query_text = " ".join(query_parts).strip() or mtype

            where = {"type": mtype}

            try:
                res = self.collection.query(
                    query_texts=[query_text],
                    n_results=50,
                    where=where,
                )
                metas = (res.get("metadatas") or [[]])[0]
            except Exception:
                metas = []

            if not metas:
                continue

            # diet + exclusion filtering
            filtered: list[dict] = []
            for meta in metas:
                # diet filter
                diets = meta.get("diet") or []
                if isinstance(diets, str):
                    diets = [d.strip() for d in diets.split(",") if d.strip()]

                if diets:
                    if not (allow_diets & set(d.lower() for d in diets)):
                        continue

                # exclusion filter (name + tags)
                name = (meta.get("name") or "").lower()
                tags = [t.lower() for t in (meta.get("tags") or [])]

                if exclude_terms and any(
                    term in name or any(term in tag for tag in tags)
                    for term in exclude_terms
                ):
                    continue

                if meta.get("type") != mtype:
                    continue

                filtered.append(meta)

            if not filtered:
                continue

            strong_candidates = [
                m for m in filtered
                if float(m.get("protein") or 0) >= min_pro
            ]
            candidates = strong_candidates if len(strong_candidates) >= per_type else filtered

            # scoring and selection
            scored: list[tuple[float, dict]] = []
            for meta in candidates:
                score = self._score_meal(
                    target_cal=target_cal,
                    target_pro=target_pro,
                    meal=meta,
                    goal=goal,
                    preferred_tags=preferred_tags,
                )
                scored.append((score, meta))

            scored.sort(key=lambda x: x[0])

            # choose up to per_type best for this meal type
            chosen_for_type: list[dict] = []
            for _, meta in scored:
                mid = meta.get("id")
                if mid and mid in seen_ids:
                    continue
                chosen_for_type.append(meta)
                if mid:
                    seen_ids.add(mid)
                if len(chosen_for_type) >= per_type:
                    break

            selected_all.extend(chosen_for_type)

        return selected_all


    def generate_plan(self, profile: dict, context: List[dict]) -> str:
        """Generate meal plan using LLM; expects profile {goal, calories, diet_type, days, avoid_names?}."""
        client = OpenAI(
            api_key=os.getenv("GROQ_API_KEY"),
            base_url="https://api.groq.com/openai/v1"
        )

        # Build compact context
        lines = []
        for m in context:
            tag_csv = m.get("tags", "")
            tags = tag_csv if isinstance(tag_csv, str) else ", ".join(tag_csv or [])
            lines.append(
                f"- {m['name']} ({m['type']}): {m['calories']} kcal, "
                f"{m['protein']}g P / {m['carbs']}g C / {m['fats']}g F; tags: {tags}"
            )
        context_str = "\n".join(lines)

        days = int(profile.get("days", 3))

        avoid = profile.get("avoid_names", [])
        avoid_str = ", ".join([a for a in avoid if isinstance(a, str)])[:1000]
        avoid_clause = f"\nAvoid repeating these meal names: [{avoid_str}]\n" if avoid_str else ""

        prompt = f"""You are an expert nutritionist and meal planner. Your role is to create personalized meal plans and to return ONLY valid JSON.
    NO markdown, NO prose, NO backticks.

    Create a meal plan for EXACTLY {days} day(s) for:
    - Goal: {profile['goal']}
    - Calories: {profile['calories']} kcal/day
    - Diet: {profile['diet_type']}

    Choose from these candidate meals (you may repeat across days if needed, but prefer variety):
    {context_str}
    {avoid_clause}
    STRICT JSON OUTPUT:
    {{
    "title": "Meaningful title of 3 words",
    "content": "Write the full {days}-day meal plan here as plain text. Clearly separate each day using labels like Day 1, Day 2, etc. For each day, mention breakfast, lunch, snack(s), and dinner chosen from the candidate meals above, with brief descriptions. Do not use markdown or bullet symbols, just plain sentences and line breaks."
    }}

    Rules:
    - Return valid JSON ONLY.
    - Do NOT include any keys other than title and content.
    - The content field must contain the entire multi-day plan as a single text block.
    - Make sure each day roughly matches the target calories and macros.
    - Keep the language natural, supportive and concise.
    - In JSON, you MUST escape all line breaks as \\n and tabs as \\t.
    - Never put literal line-break characters inside the content string.
    """

        response = client.chat.completions.create(
            model=os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=2000,
        )
        return response.choices[0].message.content
