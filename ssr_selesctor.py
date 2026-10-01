"""
SSR item candidate search and selection.

Flow: Python keyword scoring finds a broad candidate list -> AI (if
available) picks the relevant subset from those candidates only, with a
reason -> user reviews. The AI can never invent an item; it can only
choose ids from the candidate list it was given.
"""

import re

import pandas as pd


def _norm(text) -> str:
    text = "" if text is None else str(text)
    text = re.sub(r"[^a-z0-9\s]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


CC_KEYWORDS = ["concrete", "cement concrete", "rigid pavement", "cc pavement", "pcc", "expansion joint"]
BT_KEYWORDS = ["bitumen", "bituminous", "dambar", "asphalt", "surface dressing", "tack coat", "prime coat",
               "premix", "dbm", "bc "]
NEW_ROAD_KEYWORDS = ["excavat", "earthwork", "sub grade", "subgrade", "sub base", "subbase", "base course",
                      "clearing", "cleaning", "grubbing", "formation"]
REPAIR_KEYWORDS = ["maintenance", "repair", "pothole", "patch", "crack", "ravel", "edge break",
                    "reinstatement"]

# Categories used only to spread the selection across different kinds of
# work rather than picking 10 near-duplicate rows -- NOT used to drop
# anything. A row that matches none of these can still be selected.
CATEGORY_KEYWORDS = {
    "site_preparation": ["clearing", "cleaning", "grubbing"],
    "excavation": ["excavat", "earthwork", "cutting"],
    "subgrade": ["sub grade", "subgrade"],
    "subbase": ["sub base", "subbase"],
    "base_course": ["base course"],
    "concrete_pavement": ["rigid pavement", "cement concrete", "concrete pavement", "pcc"],
    "expansion_joint": ["expansion joint"],
    "prime_coat": ["prime coat"],
    "tack_coat": ["tack coat"],
    "bituminous_surface": ["bitumen", "bituminous", "asphalt", "surface dressing", "premix", "dbm"],
    "pothole_repair": ["pothole"],
    "patch_repair": ["patch"],
    "crack_repair": ["crack"],
    "maintenance": ["maintenance"],
    "drainage": ["drain", "culvert"],
    "road_furniture": ["km stone", "kilometre stone", "sign board", "signboard", "road marking",
                        "guard stone", "boundary stone"],
    "road_safety": ["road safety", "crash barrier", "reflector", "delineator"],
}


def _keyword_score(text: str, keywords) -> int:
    return sum(1 for kw in keywords if kw in text)


def _categorise(text: str) -> str:
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return category
    return "other"


def score_item(row, mode: str, road_kind: str, ai_analysis: dict | None) -> tuple[int, list]:
    """Score one SSR row against the project. Returns (score, matched_reasons)."""
    description = _norm(row.get("description", ""))
    chapter = _norm(row.get("chapter", ""))
    text = f"{description} {chapter}"

    score = 0
    reasons = []

    if mode == "New Road Construction":
        hits = _keyword_score(text, NEW_ROAD_KEYWORDS)
        if hits:
            score += 10 * hits
            reasons.append("matches new-road work")

        if road_kind == "Concrete (CC)" and _keyword_score(text, CC_KEYWORDS):
            score += 20
            reasons.append("matches concrete/CC pavement")
        if road_kind == "Bitumen / Dambar" and _keyword_score(text, BT_KEYWORDS):
            score += 20
            reasons.append("matches bituminous/BT surfacing")

    if mode == "Repair (Existing Road)":
        hits = _keyword_score(text, REPAIR_KEYWORDS)
        if hits:
            score += 10 * hits
            reasons.append("matches repair/maintenance work")

    if ai_analysis:
        for defect in ai_analysis.get("defects", []) or []:
            if isinstance(defect, dict):
                defect_type = _norm(defect.get("type", "")).replace("_", " ")
                if defect_type and defect_type in text:
                    score += 8
                    reasons.append(f"AI-detected defect: {defect_type}")

        for work in ai_analysis.get("suggested_works", []) or []:
            if not isinstance(work, dict):
                continue
            for keyword in work.get("search_keywords", []) or []:
                keyword_norm = _norm(keyword)
                if keyword_norm and keyword_norm in text:
                    score += 5
                    reasons.append(f"AI suggestion keyword: {keyword_norm}")

    return score, reasons


def find_candidates(
    df: pd.DataFrame,
    mode: str,
    road_kind: str | None,
    ai_analysis: dict | None = None,
    allowed_chapters: list | None = None,
    max_per_category: int = 3,
    max_total: int = 40,
) -> pd.DataFrame:
    """
    Score SSR rows and return the strongest candidates, spread across
    categories (including "other").

    allowed_chapters restricts scoring to a specific chapter group.
    This matters because road-agnostic keywords such as "crack" or
    "patch" also appear in unrelated chapters like Bridge Maintenance or
    Waterproofing -- without this restriction those unrelated items
    could be scored and selected by mistake.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    pool = df
    if allowed_chapters:
        allowed_norm = {_norm(c) for c in allowed_chapters}
        pool = df[df["chapter"].map(_norm).isin(allowed_norm)]
        if pool.empty:
            pool = df

    scored = []
    for _, row in pool.iterrows():
        score, reasons = score_item(row, mode, road_kind, ai_analysis)
        if score <= 0:
            continue
        text = f"{_norm(row.get('description', ''))} {_norm(row.get('chapter', ''))}"
        scored.append({
            "id": int(row["id"]),
            "score": score,
            "reasons": reasons,
            "category": _categorise(text),
        })

    if not scored:
        return pd.DataFrame()

    scored.sort(key=lambda r: r["score"], reverse=True)

    kept = []
    category_counts: dict[str, int] = {}
    for candidate in scored:
        count = category_counts.get(candidate["category"], 0)
        if count >= max_per_category:
            continue
        category_counts[candidate["category"]] = count + 1
        kept.append(candidate)
        if len(kept) >= max_total:
            break

    ids = [c["id"] for c in kept]
    result = pool[pool["id"].isin(ids)].copy()
    result = result.merge(
        pd.DataFrame(kept)[["id", "score", "reasons", "category"]],
        on="id",
        how="left",
    )
    return result.sort_values("score", ascending=False).reset_index(drop=True)


def candidates_to_ai_payload(candidates: pd.DataFrame) -> list:
    """Trim candidate rows down to the fields the AI selector actually needs."""
    return [
        {
            "id": int(row["id"]),
            "chapter": row["chapter"],
            "description": row["description"][:200],
            "unit": row["unit"],
        }
        for _, row in candidates.iterrows()
    ]
