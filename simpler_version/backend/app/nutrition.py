ACTIVITY_MULTIPLIER = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
}

def calculate_bmr(age: int, gender: str, height_cm: float, weight_kg: float) -> float:
    """Calculate Basal Metabolic Rate."""
    if gender == "male":
        return 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
    else:
        return 10 * weight_kg + 6.25 * height_cm - 5 * age - 161

def calculate_calories(bmr: float, activity: str, goal: str) -> int:
    """Calculate target calories."""
    tdee = bmr * ACTIVITY_MULTIPLIER.get(activity, 1.55)
    
    if goal == "fat_loss":
        return round(tdee * 0.8)
    elif goal == "muscle_gain":
        return round(tdee * 1.15)
    else:
        return round(tdee)

def calculate_macros(
    calories: int,
    goal: str,
    weight_kg: float | None = None,
    planned_coverage: float = 0.8,
) -> dict:
    """
    Calculate daily macro targets.
    """

    #  base split & protein-per-kg
    if goal == "fat_loss":
        carb_ratio, fat_ratio = 0.35, 0.30
        protein_per_kg = 2.0     # higher protein to preserve muscle
        default_protein_ratio = 0.35
    elif goal == "muscle_gain":
        carb_ratio, fat_ratio = 0.45, 0.25
        protein_per_kg = 2.0     # typical bulking range ~1.8–2.2 g/kg
        default_protein_ratio = 0.30
    else:  # maintenance / balanced
        carb_ratio, fat_ratio = 0.45, 0.30
        protein_per_kg = 1.6
        default_protein_ratio = 0.25

    # Protein: prefer weight-base
    if weight_kg is not None and weight_kg > 0:
        min_per_kg, max_per_kg = 1.2, 2.2
        raw_protein = protein_per_kg * weight_kg
        raw_protein = max(min_per_kg * weight_kg,
                          min(raw_protein, max_per_kg * weight_kg))
        protein_g = round(raw_protein)
    else:
        protein_g = round((calories * default_protein_ratio) / 4)

    protein_kcal = protein_g * 4
    remaining_kcal = max(0, calories - protein_kcal)

    # 3) Distribute the remaining kcal between carbs and fats
    total_cf_ratio = carb_ratio + fat_ratio
    carb_kcal = remaining_kcal * (carb_ratio / total_cf_ratio)
    fat_kcal = remaining_kcal * (fat_ratio / total_cf_ratio)

    carbs_g = round(carb_kcal / 4)
    fats_g = round(fat_kcal / 9)

    # part of the macros covered by the plan
    coverage = max(0.5, min(planned_coverage, 1.0))

    return {
        # Full daily recommended targets
        "protein_g": protein_g,
        "carbs_g": carbs_g,
        "fats_g": fats_g,

        # Targets for the generated meal plan
        "plan_protein_g": round(protein_g * coverage),
        "plan_carbs_g": round(carbs_g * coverage),
        "plan_fats_g": round(fats_g * coverage),
        "coverage": coverage,
    }
