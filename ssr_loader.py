"""
SSR Loader for Road Cost Estimator

Supports:
    - Excel (.xlsx)
    - Excel (.xls)
    - CSV (.csv)
    - PDF (.pdf)
    - DOCX (.docx)
    - TXT (.txt)

The loader converts supported SSR files into a common
Pandas DataFrame structure.

Standard columns returned:

    id
    item_no
    chapter
    description
    unit
    rate
    unit_kind
"""

import os
import re
import pandas as pd


# ============================================================
# OPTIONAL IMPORTS
# ============================================================

try:
    import pdfplumber
except ImportError:
    pdfplumber = None


try:
    from docx import Document
except ImportError:
    Document = None


# ============================================================
# STANDARD COLUMN NAMES
# ============================================================

STANDARD_COLUMNS = [
    "id",
    "item_no",
    "chapter",
    "description",
    "unit",
    "rate",
    "unit_kind"
]


# ============================================================
# COLUMN NORMALIZATION
# ============================================================

def normalize_column_name(column):
    """
    Convert different SSR column names into a common format.
    """

    text = str(column).strip().lower()

    text = re.sub(
        r"[^a-z0-9]+",
        "_",
        text
    )

    text = text.strip("_")

    return text


def find_column(df, possible_names):
    """
    Find a column from a list of possible names.
    """

    normalized = {
        normalize_column_name(col): col
        for col in df.columns
    }

    for name in possible_names:

        key = normalize_column_name(name)

        if key in normalized:
            return normalized[key]

    return None


# ============================================================
# UNIT CLASSIFICATION
# ============================================================

def unit_kind(unit):
    """
    Classify an SSR unit so the quantity engine can decide
    which basic measurement formula may apply.

    Examples:

        sqm / m2       -> area
        cum / m3       -> volume
        rm / m         -> length
        no / nos       -> number
        kg             -> weight
        tonne           -> weight
        lump sum        -> lump_sum
    """

    if unit is None:
        return "unknown"

    text = str(unit).strip().lower()

    # Remove spaces and punctuation for easier matching.
    cleaned = re.sub(
        r"[^a-z0-9]+",
        "",
        text
    )

    # --------------------------------------------------------
    # AREA
    # --------------------------------------------------------

    area_units = {
        "sqm",
        "m2",
        "sq.m",
        "sqmeter",
        "sqmeters",
        "squaremeter",
        "squaremeters"
    }

    if cleaned in {
        re.sub(r"[^a-z0-9]+", "", x)
        for x in area_units
    }:
        return "area"

    # --------------------------------------------------------
    # VOLUME
    # --------------------------------------------------------

    volume_units = {
        "cum",
        "m3",
        "cu.m",
        "cubicmeter",
        "cubicmeters"
    }

    if cleaned in {
        re.sub(r"[^a-z0-9]+", "", x)
        for x in volume_units
    }:
        return "volume"

    # --------------------------------------------------------
    # LENGTH
    # --------------------------------------------------------

    length_units = {
        "m",
        "rm",
        "rmt",
        "runningmeter",
        "runningmeters",
        "meter",
        "meters"
    }

    if cleaned in {
        re.sub(r"[^a-z0-9]+", "", x)
        for x in length_units
    }:
        return "length"

    # --------------------------------------------------------
    # NUMBER
    # --------------------------------------------------------

    number_units = {
        "no",
        "nos",
        "number",
        "numbers",
        "each",
        "item",
        "items"
    }

    if cleaned in {
        re.sub(r"[^a-z0-9]+", "", x)
        for x in number_units
    }:
        return "number"

    # --------------------------------------------------------
    # WEIGHT
    # --------------------------------------------------------

    weight_units = {
        "kg",
        "kgs",
        "kilogram",
        "kilograms",
        "mt",
        "ton",
        "tons",
        "tonne",
        "tonnes"
    }

    if cleaned in {
        re.sub(r"[^a-z0-9]+", "", x)
        for x in weight_units
    }:
        return "weight"

    # --------------------------------------------------------
    # LUMP SUM
    # --------------------------------------------------------

    if (
        "lump" in text
        or "sum" in text
        or cleaned in {"ls", "lumpsum"}
    ):
        return "lump_sum"

    return "unknown"


# ============================================================
# RATE CLEANING
# ============================================================

def clean_rate(value):
    """
    Convert an SSR rate into a numeric value.
    """

    if pd.isna(value):
        return 0.0

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()

    # Remove currency symbols and commas.
    text = text.replace(
        ",",
        ""
    )

    text = re.sub(
        r"[₹$]",
        "",
        text
    )

    # Keep numbers and decimal point.
    match = re.search(
        r"-?\d+(?:\.\d+)?",
        text
    )

    if not match:
        return 0.0

    try:
        return float(
            match.group()
        )

    except Exception:
        return 0.0


# ============================================================
# GENERATE IDS
# ============================================================

def ensure_ids(df):
    """
    Ensure every SSR item has a stable integer ID.
    """

    if "id" not in df.columns:

        df["id"] = range(
            1,
            len(df) + 1
        )

    else:

        ids = pd.to_numeric(
            df["id"],
            errors="coerce"
        )

        missing = ids.isna()

        if missing.any():

            next_id = (
                int(ids.dropna().max())
                + 1
                if not ids.dropna().empty
                else 1
            )

            for index in df.index[missing]:

                ids.loc[index] = next_id

                next_id += 1

        df["id"] = ids.astype(int)

    return df


# ============================================================
# STANDARDIZE DATAFRAME
# ============================================================

def standardize_dataframe(df):
    """
    Convert an arbitrary SSR DataFrame into the standard
    structure expected by the application.
    """

    if df is None:
        raise ValueError(
            "No SSR data was provided."
        )

    if not isinstance(df, pd.DataFrame):
        raise TypeError(
            "SSR data must be a pandas DataFrame."
        )

    if df.empty:
        raise ValueError(
            "The SSR file contains no data."
        )

    # --------------------------------------------------------
    # Remove completely empty rows/columns
    # --------------------------------------------------------

    df = df.dropna(
        axis=0,
        how="all"
    )

    df = df.dropna(
        axis=1,
        how="all"
    )

    df.columns = [
        normalize_column_name(col)
        for col in df.columns
    ]

    # --------------------------------------------------------
    # Find important columns
    # --------------------------------------------------------

    item_col = find_column(
        df,
        [
            "item_no",
            "item_number",
            "item",
            "item_code",
            "code",
            "sr_no",
            "sr_number",
            "serial_no",
            "sr"
        ]
    )

    chapter_col = find_column(
        df,
        [
            "chapter",
            "chapter_name",
            "section",
            "category",
            "group"
        ]
    )

    description_col = find_column(
        df,
        [
            "description",
            "item_description",
            "item_details",
            "details",
            "particulars",
            "work_description",
            "name"
        ]
    )

    unit_col = find_column(
        df,
        [
            "unit",
            "units",
            "uom",
            "unit_of_measurement"
        ]
    )

    rate_col = find_column(
        df,
        [
            "rate",
            "basic_rate",
            "unit_rate",
            "cost",
            "amount",
            "rate_rs",
            "rate_in_rs"
        ]
    )

    id_col = find_column(
        df,
        [
            "id",
            "item_id",
            "unique_id"
        ]
    )

    # --------------------------------------------------------
    # Validate important columns
    # --------------------------------------------------------

    if description_col is None:

        raise ValueError(
            "Could not identify the SSR description column."
        )

    if unit_col is None:

        raise ValueError(
            "Could not identify the SSR unit column."
        )

    if rate_col is None:

        raise ValueError(
            "Could not identify the SSR rate column."
        )

    # --------------------------------------------------------
    # Create standard DataFrame
    # --------------------------------------------------------

    result = pd.DataFrame()

    # ID
    if id_col:

        result["id"] = df[id_col]

    else:

        result["id"] = range(
            1,
            len(df) + 1
        )

    # Item number
    if item_col:

        result["item_no"] = (
            df[item_col]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    else:

        result["item_no"] = ""

    # Chapter
    if chapter_col:

        result["chapter"] = (
            df[chapter_col]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    else:

        result["chapter"] = "(no chapter)"

    # Description
    result["description"] = (
        df[description_col]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    # Unit
    result["unit"] = (
        df[unit_col]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    # Rate
    result["rate"] = (
        df[rate_col]
        .apply(clean_rate)
    )

    # Unit classification
    result["unit_kind"] = (
        result["unit"]
        .apply(unit_kind)
    )

    # --------------------------------------------------------
    # Clean rows
    # --------------------------------------------------------

    result = result[
        result["description"].str.strip() != ""
    ].copy()

    # --------------------------------------------------------
    # Clean chapter names
    # --------------------------------------------------------

    result["chapter"] = (
        result["chapter"]
        .replace(
            {
                "nan": "(no chapter)",
                "None": "(no chapter)",
                "": "(no chapter)"
            }
        )
    )

    # --------------------------------------------------------
    # Ensure IDs
    # --------------------------------------------------------

    result = ensure_ids(
        result
    )

    # --------------------------------------------------------
    # Reset index
    # --------------------------------------------------------

    result = result.reset_index(
        drop=True
    )

    return result


# ============================================================
# EXCEL LOADER
# ============================================================

def load_excel(file_source):
    """
    Load Excel SSR.

    Supports .xlsx and .xls.
    """

    extension = ""

    if isinstance(
        file_source,
        str
    ):
        extension = os.path.splitext(
            file_source
        )[1].lower()

    if extension == ".xls":

        try:
            return pd.read_excel(
                file_source,
                engine="xlrd"
            )

        except ImportError as error:

            raise RuntimeError(
                "Reading .xls files requires the xlrd package."
            ) from error

    return pd.read_excel(
        file_source
    )


# ============================================================
# CSV LOADER
# ============================================================

def load_csv(file_source):
    """
    Load CSV SSR.
    """

    try:

        return pd.read_csv(
            file_source
        )

    except UnicodeDecodeError:

        return pd.read_csv(
            file_source,
            encoding="latin1"
        )


# ============================================================
# PDF LOADER
# ============================================================

def load_pdf(file_source):
    """
    Extract tables/text from PDF.

    PDF SSR structures vary considerably, so the extracted
    result still needs to pass through standardization.
    """

    if pdfplumber is None:

        raise RuntimeError(
            "PDF support requires pdfplumber."
        )

    rows = []

    with pdfplumber.open(
        file_source
    ) as pdf:

        for page in pdf.pages:

            # ------------------------------------------------
            # Try tables first
            # ------------------------------------------------

            tables = page.extract_tables()

            for table in tables or []:

                if not table:
                    continue

                rows.extend(
                    table
                )

            # ------------------------------------------------
            # If no tables, extract text
            # ------------------------------------------------

            if not tables:

                text = page.extract_text()

                if text:

                    for line in text.splitlines():

                        rows.append(
                            [line]
                        )

    if not rows:

        raise ValueError(
            "No readable data was found in the PDF."
        )

    # Find the widest row.
    max_columns = max(
        len(row)
        for row in rows
        if row
    )

    normalized_rows = []

    for row in rows:

        row = list(row)

        row += [
            None
        ] * (
            max_columns
            - len(row)
        )

        normalized_rows.append(
            row
        )

    return pd.DataFrame(
        normalized_rows
    )


# ============================================================
# DOCX LOADER
# ============================================================

def load_docx(file_source):
    """
    Extract tables from DOCX.
    """

    if Document is None:

        raise RuntimeError(
            "DOCX support requires python-docx."
        )

    document = Document(
        file_source
    )

    rows = []

    for table in document.tables:

        for row in table.rows:

            rows.append(
                [
                    cell.text.strip()
                    for cell in row.cells
                ]
            )

    if not rows:

        # Try paragraphs if no tables exist.
        for paragraph in document.paragraphs:

            text = paragraph.text.strip()

            if text:

                rows.append(
                    [text]
                )

    if not rows:

        raise ValueError(
            "No readable SSR data was found in the DOCX file."
        )

    max_columns = max(
        len(row)
        for row in rows
    )

    normalized_rows = []

    for row in rows:

        row = list(row)

        row += [
            None
        ] * (
            max_columns
            - len(row)
        )

        normalized_rows.append(
            row
        )

    return pd.DataFrame(
        normalized_rows
    )


# ============================================================
# TXT LOADER
# ============================================================

def load_txt(file_source):
    """
    Load a text SSR file.
    """

    if hasattr(
        file_source,
        "read"
    ):

        raw = file_source.read()

        if isinstance(
            raw,
            bytes
        ):

            text = raw.decode(
                "utf-8",
                errors="replace"
            )

        else:

            text = str(raw)

    else:

        with open(
            file_source,
            "r",
            encoding="utf-8",
            errors="replace"
        ) as file:

            text = file.read()

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    if not lines:

        raise ValueError(
            "The TXT file contains no readable data."
        )

    # Try comma-separated text first.
    if "," in lines[0]:

        from io import StringIO

        return pd.read_csv(
            StringIO(
                "\n".join(lines)
            )
        )

    # Otherwise keep one line per row.
    return pd.DataFrame(
        {
            "description": lines
        }
    )


# ============================================================
# MAIN SSR LOADER
# ============================================================

def load_ssr(file_source):
    """
    Load and standardize an SSR file.

    file_source can be:

        - UploadedFile from Streamlit
        - File path
        - File-like object
    """

    if file_source is None:

        raise ValueError(
            "No SSR file was provided."
        )

    # --------------------------------------------------------
    # Determine file name
    # --------------------------------------------------------

    filename = getattr(
        file_source,
        "name",
        ""
    )

    if not filename and isinstance(
        file_source,
        str
    ):

        filename = file_source

    extension = os.path.splitext(
        str(filename)
    )[1].lower()

    # --------------------------------------------------------
    # Load according to extension
    # --------------------------------------------------------

    if extension in {
        ".xlsx",
        ".xls"
    }:

        raw_df = load_excel(
            file_source
        )

    elif extension == ".csv":

        raw_df = load_csv(
            file_source
        )

    elif extension == ".pdf":

        raw_df = load_pdf(
            file_source
        )

    elif extension == ".docx":

        raw_df = load_docx(
            file_source
        )

    elif extension == ".txt":

        raw_df = load_txt(
            file_source
        )

    else:

        # Try Excel as fallback.
        try:

            raw_df = pd.read_excel(
                file_source
            )

        except Exception as error:

            raise ValueError(
                "Unsupported SSR file format. "
                "Please upload XLSX, XLS, CSV, PDF, DOCX or TXT."
            ) from error

    # --------------------------------------------------------
    # Standardize
    # --------------------------------------------------------

    df = standardize_dataframe(
        raw_df
    )

    return df


# ============================================================
# CHAPTER MATCHING
# ============================================================

def match_chapters(
    all_chapters,
    wanted_chapters
):
    """
    Match requested chapter names against actual SSR
    chapter names.

    Matching is case-insensitive and tolerant of spaces,
    spelling variations and punctuation.
    """

    if not all_chapters:
        return []

    if not wanted_chapters:
        return []

    def clean(text):

        text = str(text).lower()

        text = re.sub(
            r"[^a-z0-9]+",
            " ",
            text
        )

        return " ".join(
            text.split()
        )

    cleaned_actual = {
        clean(chapter): chapter
        for chapter in all_chapters
    }

    matches = []

    for wanted in wanted_chapters:

        wanted_clean = clean(
            wanted
        )

        # Exact match
        if wanted_clean in cleaned_actual:

            matches.append(
                cleaned_actual[
                    wanted_clean
                ]
            )

            continue

        # Partial match
        for actual_clean, actual_original in (
            cleaned_actual.items()
        ):

            if (
                wanted_clean in actual_clean
                or actual_clean in wanted_clean
            ):

                if actual_original not in matches:

                    matches.append(
                        actual_original
                    )

    return matches


# ============================================================
# SSR SEARCH
# ============================================================

def search(
    df,
    chapters=None,
    keywords=None
):
    """
    Search SSR items by chapter and keywords.

    Example:

        search(
            df,
            chapters=["Road Sub grade"],
            keywords=["excavation"]
        )
    """

    if df is None:

        return pd.DataFrame(
            columns=STANDARD_COLUMNS
        )

    if df.empty:

        return df.copy()

    result = df.copy()

    # --------------------------------------------------------
    # Chapter filter
    # --------------------------------------------------------

    if chapters:

        chapter_values = {
            str(chapter).strip().lower()
            for chapter in chapters
        }

        result = result[
            result["chapter"]
            .astype(str)
            .str.strip()
            .str.lower()
            .isin(chapter_values)
        ]

    # --------------------------------------------------------
    # Keyword filter
    # --------------------------------------------------------

    if keywords:

        cleaned_keywords = [
            str(keyword).strip().lower()
            for keyword in keywords
            if str(keyword).strip()
        ]

        if cleaned_keywords:

            search_text = (

                result["description"]
                .fillna("")
                .astype(str)

                + " "

                + result["item_no"]
                .fillna("")
                .astype(str)

                + " "

                + result["chapter"]
                .fillna("")
                .astype(str)

            ).str.lower()

            mask = pd.Series(
                False,
                index=result.index
            )

            for keyword in cleaned_keywords:

                mask = (
                    mask
                    | search_text.str.contains(
                        re.escape(keyword),
                        na=False
                    )
                )

            result = result[
                mask
            ]

    return result.reset_index(
        drop=True
    )


# ============================================================
# GET SSR ITEMS FOR AI
# ============================================================

def get_ai_items(
    df,
    max_items=500
):
    """
    Return a clean SSR representation that can be sent to
    the AI for item selection.

    IMPORTANT:
    The AI can recommend which item applies, but the rate
    always comes directly from the SSR DataFrame.
    """

    if df is None or df.empty:

        return []

    columns = [
        "id",
        "item_no",
        "chapter",
        "description",
        "unit",
        "rate",
        "unit_kind"
    ]

    available_columns = [
        column
        for column in columns
        if column in df.columns
    ]

    data = df[
        available_columns
    ].head(
        max_items
    )

    records = []

    for _, row in data.iterrows():

        records.append(
            {
                "id": int(row["id"]),

                "item_no": str(
                    row.get(
                        "item_no",
                        ""
                    )
                ),

                "chapter": str(
                    row.get(
                        "chapter",
                        ""
                    )
                ),

                "description": str(
                    row.get(
                        "description",
                        ""
                    )
                ),

                "unit": str(
                    row.get(
                        "unit",
                        ""
                    )
                ),

                "rate": float(
                    row.get(
                        "rate",
                        0
                    )
                ),

                "unit_kind": str(
                    row.get(
                        "unit_kind",
                        "unknown"
                    )
                )
            }
        )

    return records


# ============================================================
# GET ITEM BY ID
# ============================================================

def get_item_by_id(
    df,
    item_id
):
    """
    Retrieve one SSR item by its ID.
    """

    if df is None or df.empty:

        return None

    try:

        item_id = int(
            item_id
        )

    except Exception:

        return None

    matches = df[
        df["id"] == item_id
    ]

    if matches.empty:

        return None

    return matches.iloc[0].to_dict()


# ============================================================
# QUANTITY FORMULAS
# ============================================================

def calculate_basic_quantity(
    unit_kind_value,
    length,
    width,
    thickness_mm=0,
    number=1
):
    """
    Calculate basic project quantities.

    This is intentionally deterministic.

    AI should select the applicable SSR item.
    Python should calculate the basic quantity.

    Returns None when a safe automatic formula cannot
    be determined.
    """

    try:

        length = float(
            length or 0
        )

        width = float(
            width or 0
        )

        thickness_mm = float(
            thickness_mm or 0
        )

        number = float(
            number or 1
        )

    except Exception:

        return None

    # --------------------------------------------------------
    # AREA
    # --------------------------------------------------------

    if unit_kind_value == "area":

        if length <= 0 or width <= 0:
            return None

        return length * width

    # --------------------------------------------------------
    # VOLUME
    # --------------------------------------------------------

    if unit_kind_value == "volume":

        if (
            length <= 0
            or width <= 0
            or thickness_mm <= 0
        ):
            return None

        thickness_m = (
            thickness_mm / 1000
        )

        return (
            length
            * width
            * thickness_m
        )

    # --------------------------------------------------------
    # LENGTH
    # --------------------------------------------------------

    if unit_kind_value == "length":

        if length <= 0:
            return None

        return length

    # --------------------------------------------------------
    # NUMBER
    # --------------------------------------------------------

    if unit_kind_value == "number":

        return max(
            0,
            number
        )

    # --------------------------------------------------------
    # UNKNOWN / WEIGHT / LUMP SUM
    # --------------------------------------------------------

    return None
