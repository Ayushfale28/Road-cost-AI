"""Reads the Maharashtra PWD SSR Excel (sheet 'SSR 2022-23')."""
import pandas as pd

SHEET = "SSR 2022-23"
COLS = {0: "sr_no", 1: "chapter", 2: "item_no", 4: "description", 5: "extra_spec",
        6: "unit", 7: "rate", 8: "labour_rate"}


def _clean_unit(u: str) -> str:
    u = " ".join(str(u).split()).lower().replace("meter", "metre")
    return u


def unit_kind(unit: str) -> str:
    """Map SSR unit text to a quantity type."""
    u = _clean_unit(unit)
    if "square metre" in u:
        return "area"
    if "cubic metre" in u:
        return "volume"
    if "running metre" in u:
        return "length"
    if "kilometre" in u:
        return "km"
    if "number" in u:
        return "nos"
    if "tonne" in u:
        return "tonne"
    return "other"


def load_ssr(path) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=SHEET, header=None, usecols=range(9))
    df = raw.iloc[2:].rename(columns=COLS)[list(COLS.values())]
    df = df[df["item_no"].notna()].copy()
    for c in ("chapter", "description", "unit"):
        df[c] = df[c].fillna("").astype(str)
    df["chapter"] = df["chapter"].str.replace(r"\s+", " ", regex=True).str.strip()
    df.loc[df["chapter"] == "", "chapter"] = "(no chapter)"
    df["description"] = df["description"].str.replace(r"\s+", " ", regex=True).str.strip()
    df["unit"] = df["unit"].str.replace(r"\s+", " ", regex=True).str.strip()
    df["rate"] = pd.to_numeric(df["rate"], errors="coerce")
    df["labour_rate"] = pd.to_numeric(df["labour_rate"], errors="coerce")
    df = df[df["rate"].notna()].reset_index(drop=True)
    # item_no is stored as a number in Excel (e.g. 39.9 for 39.90), so show it as is
    df["item_no"] = df["item_no"].astype(str)
    df["kind"] = df["unit"].map(unit_kind)
    df["id"] = df.index
    return df


def search(df: pd.DataFrame, chapters=None, keywords=None) -> pd.DataFrame:
    out = df
    if chapters:
        out = out[out["chapter"].isin(chapters)]
    if keywords:
        pat = "|".join(k.strip() for k in keywords if k.strip())
        if pat:
            out = out[out["description"].str.contains(pat, case=False, regex=True, na=False)]
    return out


def norm_chapter(name: str) -> str:
    return " ".join(str(name).lower().replace("maintainance", "maintenance").split())


def match_chapters(df_chapters, wanted) -> list:
    """Map wanted chapter names to the real (messy) chapter names in the SSR, ignoring case/spelling variants."""
    w = {norm_chapter(x) for x in wanted}
    return sorted({c for c in df_chapters if norm_chapter(c) in w})
