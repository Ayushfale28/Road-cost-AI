"""
SSR Loader

Supports:
- Excel (.xlsx, .xls)
- CSV (.csv)
- PDF (.pdf)
- DOCX (.docx)
- TXT (.txt)

The loader converts supported files into a common DataFrame
structure used by the Road Cost Estimator.
"""

import os
import re

import pandas as pd
import pdfplumber
from docx import Document


# ============================================================
# DEFAULT MAHARASHTRA PWD SSR SETTINGS
# ============================================================

SHEET = "SSR 2022-23"

COLS = {
    0: "sr_no",
    1: "chapter",
    2: "item_no",
    4: "description",
    5: "extra_spec",
    6: "unit",
    7: "rate",
    8: "labour_rate",
}


# ============================================================
# COMMON COLUMNS
# ============================================================

COMMON_COLUMNS = [
    "sr_no",
    "chapter",
    "item_no",
    "description",
    "extra_spec",
    "unit",
    "rate",
    "labour_rate",
]


# ============================================================
# UNIT CLEANING
# ============================================================

def _clean_unit(u: str) -> str:
    """
    Clean SSR unit text.
    """

    u = " ".join(str(u).split()).lower()

    u = u.replace("meter", "metre")

    return u


# ============================================================
# UNIT TYPE
# ============================================================

def unit_kind(unit: str) -> str:
    """
    Map SSR unit text to a quantity type.
    """

    u = _clean_unit(unit)

    if "square metre" in u or "sq.m" in u or "sqm" in u:
        return "area"

    if "cubic metre" in u or "cu.m" in u or "cum" in u:
        return "volume"

    if "running metre" in u or "r.m" in u or "rm" in u:
        return "length"

    if "kilometre" in u or "km" in u:
        return "km"

    if "number" in u or u == "no" or u == "nos":
        return "nos"

    if "tonne" in u or u == "mt":
        return "tonne"

    return "other"


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def _clean_text(value):
    """
    Convert a value to clean text.
    """

    if value is None:
        return ""

    return " ".join(str(value).split()).strip()


# ============================================================
# RATE CLEANING
# ============================================================

def _clean_number(value):
    """
    Convert values such as:

    1,250.50
    Rs. 1250.50
    ₹1250
    1250

    into numeric values.
    """

    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    text = text.replace(",", "")
    text = text.replace("₹", "")
    text = text.replace("Rs.", "")
    text = text.replace("Rs", "")
    text = text.strip()

    match = re.search(
        r"-?\d+(?:\.\d+)?",
        text
    )

    if not match:
        return None

    try:
        return float(match.group())
    except Exception:
        return None


# ============================================================
# STANDARDIZE DATAFRAME
# ============================================================

def _standardize_dataframe(df):
    """
    Convert a DataFrame into the common SSR structure.
    """

    if df is None:
        raise ValueError("No SSR data was found.")

    df = df.copy()

    # --------------------------------------------------------
    # Clean column names
    # --------------------------------------------------------

    df.columns = [
        _clean_text(column).lower()
        for column in df.columns
    ]

    # --------------------------------------------------------
    # Rename common column variations
    # --------------------------------------------------------

    rename_map = {}

    for column in df.columns:

        clean_column = (
            column
            .lower()
            .replace("_", " ")
            .replace("-", " ")
        )

        clean_column = " ".join(
            clean_column.split()
        )

        if clean_column in [
            "sr no",
            "sr. no",
            "serial no",
            "serial number",
            "s no",
            "s. no"
        ]:
            rename_map[column] = "sr_no"

        elif clean_column in [
            "item no",
            "item number",
            "item",
            "item code",
            "item id"
        ]:
            rename_map[column] = "item_no"

        elif clean_column in [
            "chapter",
            "chapter name",
            "section"
        ]:
            rename_map[column] = "chapter"

        elif clean_column in [
            "description",
            "item description",
            "work description",
            "particulars",
            "details"
        ]:
            rename_map[column] = "description"

        elif clean_column in [
            "extra spec",
            "extra specification",
            "specification",
            "specifications"
        ]:
            rename_map[column] = "extra_spec"

        elif clean_column in [
            "unit",
            "units"
        ]:
            rename_map[column] = "unit"

        elif clean_column in [
            "rate",
            "basic rate",
            "ssr rate",
            "rate rs",
            "rate rs."
        ]:
            rename_map[column] = "rate"

        elif clean_column in [
            "labour rate",
            "labor rate",
            "labour",
            "labor"
        ]:
            rename_map[column] = "labour_rate"

    df = df.rename(
        columns=rename_map
    )

    # --------------------------------------------------------
    # Make missing columns
    # --------------------------------------------------------

    for column in COMMON_COLUMNS:

        if column not in df.columns:

            df[column] = ""

    # --------------------------------------------------------
    # Clean text columns
    # --------------------------------------------------------

    text_columns = [
        "chapter",
        "item_no",
        "description",
        "extra_spec",
        "unit"
    ]

    for column in text_columns:

        df[column] = (
            df[column]
            .fillna("")
            .astype(str)
            .map(_clean_text)
        )

    # --------------------------------------------------------
    # Numeric columns
    # --------------------------------------------------------

    df["rate"] = df["rate"].apply(
        _clean_number
    )

    df["labour_rate"] = df[
        "labour_rate"
    ].apply(
        _clean_number
    )

    # --------------------------------------------------------
    # Keep rows that contain useful SSR information
    # --------------------------------------------------------

    has_item = (
        df["item_no"].astype(str).str.strip() != ""
    )

    has_description = (
        df["description"].astype(str).str.strip() != ""
    )

    df = df[
        has_item | has_description
    ].copy()

    # --------------------------------------------------------
    # Chapter cleanup
    # --------------------------------------------------------

    df["chapter"] = (
        df["chapter"]
        .str.replace(
            r"\s+",
            " ",
            regex=True
        )
        .str.strip()
    )

    df.loc[
        df["chapter"] == "",
        "chapter"
    ] = "(no chapter)"

    # --------------------------------------------------------
    # Description cleanup
    # --------------------------------------------------------

    df["description"] = (
        df["description"]
        .str.replace(
            r"\s+",
            " ",
            regex=True
        )
        .str.strip()
    )

    # --------------------------------------------------------
    # Unit cleanup
    # --------------------------------------------------------

    df["unit"] = (
        df["unit"]
        .str.replace(
            r"\s+",
            " ",
            regex=True
        )
        .str.strip()
    )

    # --------------------------------------------------------
    # Item number cleanup
    # --------------------------------------------------------

    df["item_no"] = (
        df["item_no"]
        .astype(str)
        .str.strip()
    )

    # --------------------------------------------------------
    # If rate is missing, try extracting it from description
    # --------------------------------------------------------

    missing_rate = df["rate"].isna()

    for index in df[missing_rate].index:

        description = str(
            df.loc[index, "description"]
        )

        numbers = re.findall(
            r"\b\d+(?:,\d{3})*(?:\.\d+)?\b",
            description
        )

        if numbers:

            possible_rate = _clean_number(
                numbers[-1]
            )

            if possible_rate is not None:
                df.loc[
                    index,
                    "rate"
                ] = possible_rate

    # --------------------------------------------------------
    # Keep only rows where a rate exists
    # --------------------------------------------------------

    df = df[
        df["rate"].notna()
    ].copy()

    # --------------------------------------------------------
    # Reset index
    # --------------------------------------------------------

    df = df.reset_index(
        drop=True
    )

    # --------------------------------------------------------
    # Quantity type
    # --------------------------------------------------------

    df["kind"] = df[
        "unit"
    ].map(
        unit_kind
    )

    # --------------------------------------------------------
    # Unique ID
    # --------------------------------------------------------

    df["id"] = df.index

    return df


# ============================================================
# EXCEL LOADER
# ============================================================

def _load_excel(file):
    """
    Load the original Maharashtra PWD SSR Excel format.

    First tries the official:
        SSR 2022-23

    sheet.

    If that sheet does not exist, it tries the first sheet.
    """

    try:

        raw = pd.read_excel(
            file,
            sheet_name=SHEET,
            header=None,
            usecols=range(9)
        )

        # Original Maharashtra SSR structure
        df = (
            raw.iloc[2:]
            .rename(columns=COLS)
        )

        df = df[
            list(COLS.values())
        ]

        return _standardize_dataframe(
            df
        )

    except ValueError:

        # ----------------------------------------------------
        # Fallback: first sheet
        # ----------------------------------------------------

        try:

            df = pd.read_excel(
                file
            )

            return _standardize_dataframe(
                df
            )

        except Exception as error:

            raise ValueError(
                f"Excel file could not be read: {error}"
            )


# ============================================================
# CSV LOADER
# ============================================================

def _load_csv(file):
    """
    Load CSV SSR.
    """

    try:

        df = pd.read_csv(
            file
        )

    except Exception:

        # Try alternate encoding
        if hasattr(file, "seek"):
            file.seek(0)

        try:

            df = pd.read_csv(
                file,
                encoding="latin1"
            )

        except Exception as error:

            raise ValueError(
                f"CSV file could not be read: {error}"
            )

    return _standardize_dataframe(
        df
    )


# ============================================================
# PDF TABLE LOADER
# ============================================================

def _load_pdf_tables(file):
    """
    Try extracting tables from a PDF.
    """

    rows = []

    with pdfplumber.open(file) as pdf:

        for page in pdf.pages:

            tables = page.extract_tables()

            for table in tables:

                if not table:
                    continue

                for row in table:

                    if row:

                        cleaned_row = [
                            _clean_text(cell)
                            for cell in row
                        ]

                        rows.append(
                            cleaned_row
                        )

    if not rows:
        return None

    # Remove completely empty rows
    rows = [
        row
        for row in rows
        if any(
            str(cell).strip()
            for cell in row
        )
    ]

    if not rows:
        return None

    # Use first row as header
    header = rows[0]

    data = rows[1:]

    # Make unique column names
    cleaned_headers = []

    for i, header_name in enumerate(header):

        name = _clean_text(
            header_name
        )

        if not name:
            name = f"column_{i}"

        cleaned_headers.append(
            name
        )

    # Make all rows same length
    width = len(
        cleaned_headers
    )

    fixed_data = []

    for row in data:

        row = list(row)

        if len(row) < width:

            row += [
                ""
            ] * (
                width - len(row)
            )

        elif len(row) > width:

            row = row[
                :width
            ]

        fixed_data.append(
            row
        )

    return pd.DataFrame(
        fixed_data,
        columns=cleaned_headers
    )


# ============================================================
# PDF TEXT LOADER
# ============================================================

def _extract_pdf_text(file):
    """
    Extract all readable text from a PDF.
    """

    text_parts = []

    with pdfplumber.open(file) as pdf:

        for page in pdf.pages:

            page_text = page.extract_text()

            if page_text:

                text_parts.append(
                    page_text
                )

    return "\n".join(
        text_parts
    )


def _load_pdf_text(file):
    """
    Convert PDF text into an approximate SSR DataFrame.

    This is intended for text-based PDFs.
    Scanned/image-only PDFs may require OCR.
    """

    text = _extract_pdf_text(
        file
    )

    if not text.strip():

        raise ValueError(
            "The PDF contains no readable text. "
            "If it is a scanned/image PDF, OCR is required."
        )

    rows = []

    for line in text.splitlines():

        line = _clean_text(
            line
        )

        if not line:
            continue

        # Look for an item number at the beginning.
        match = re.match(
            r"^(\d+(?:\.\d+)+|\d+)\s+(.*)$",
            line
        )

        if not match:
            continue

        item_no = match.group(1)
        remaining = match.group(2)

        # Try to find a unit and a rate.
        rate_match = re.search(
            r"(?:₹|Rs\.?|INR)?\s*"
            r"(\d[\d,]*(?:\.\d+)?)"
            r"\s*$",
            remaining,
            flags=re.IGNORECASE
        )

        rate = None

        if rate_match:

            rate = _clean_number(
                rate_match.group(1)
            )

            remaining = (
                remaining[
                    :rate_match.start()
                ].strip()
            )

        # Try to identify common units.
        unit = ""

        unit_patterns = [
            r"\bsquare metre\b",
            r"\bsq\.?\s*m\b",
            r"\bcubic metre\b",
            r"\bcu\.?\s*m\b",
            r"\brunning metre\b",
            r"\br\.?\s*m\b",
            r"\bmetre\b",
            r"\bm\b",
            r"\bkm\b",
            r"\bkilometre\b",
            r"\bnumber\b",
            r"\bnos\.?\b",
            r"\bno\.?\b",
            r"\btonne\b",
            r"\bkg\b"
        ]

        for pattern in unit_patterns:

            unit_match = re.search(
                pattern,
                remaining,
                flags=re.IGNORECASE
            )

            if unit_match:

                unit = unit_match.group(0)

                remaining = (
                    remaining[
                        :unit_match.start()
                    ]
                    + " "
                    + remaining[
                        unit_match.end():
                    ]
                ).strip()

                break

        description = _clean_text(
            remaining
        )

        if description:

            rows.append(
                {
                    "item_no": item_no,
                    "chapter": "(no chapter)",
                    "description": description,
                    "unit": unit,
                    "rate": rate,
                    "labour_rate": None
                }
            )

    if not rows:

        raise ValueError(
            "The PDF text could not be converted into "
            "recognizable SSR items. The PDF may have a "
            "different layout or may require OCR."
        )

    return _standardize_dataframe(
        pd.DataFrame(rows)
    )


# ============================================================
# PDF MAIN LOADER
# ============================================================

def _load_pdf(file):
    """
    Try PDF table extraction first.

    If no useful table is found, fall back to text extraction.
    """

    # --------------------------------------------------------
    # Try tables
    # --------------------------------------------------------

    try:

        table_df = _load_pdf_tables(
            file
        )

        if table_df is not None:

            try:

                standardized = (
                    _standardize_dataframe(
                        table_df
                    )
                )

                if not standardized.empty:

                    return standardized

            except Exception:
                pass

    except Exception:
        pass

    # --------------------------------------------------------
    # Reset file position
    # --------------------------------------------------------

    if hasattr(file, "seek"):

        try:
            file.seek(0)
        except Exception:
            pass

    # --------------------------------------------------------
    # Text fallback
    # --------------------------------------------------------

    return _load_pdf_text(
        file
    )


# ============================================================
# DOCX LOADER
# ============================================================

def _load_docx(file):
    """
    Extract tables from DOCX first.

    If there are no useful tables, use paragraphs.
    """

    document = Document(
        file
    )

    rows = []

    # --------------------------------------------------------
    # DOCX TABLES
    # --------------------------------------------------------

    for table in document.tables:

        for row in table.rows:

            values = [
                _clean_text(
                    cell.text
                )
                for cell in row.cells
            ]

            if any(values):

                rows.append(
                    values
                )

    if rows:

        header = rows[0]

        data = rows[1:]

        headers = []

        for i, name in enumerate(header):

            name = _clean_text(
                name
            )

            if not name:

                name = f"column_{i}"

            headers.append(
                name
            )

        width = len(headers)

        fixed_rows = []

        for row in data:

            row = list(row)

            if len(row) < width:

                row += [
                    ""
                ] * (
                    width - len(row)
                )

            elif len(row) > width:

                row = row[
                    :width
                ]

            fixed_rows.append(
                row
            )

        try:

            df = pd.DataFrame(
                fixed_rows,
                columns=headers
            )

            standardized = (
                _standardize_dataframe(
                    df
                )
            )

            if not standardized.empty:

                return standardized

        except Exception:
            pass

    # --------------------------------------------------------
    # Paragraph fallback
    # --------------------------------------------------------

    paragraph_rows = []

    for paragraph in document.paragraphs:

        line = _clean_text(
            paragraph.text
        )

        if not line:
            continue

        match = re.match(
            r"^(\d+(?:\.\d+)+|\d+)\s+(.*)$",
            line
        )

        if not match:
            continue

        item_no = match.group(1)
        description = match.group(2)

        rate_match = re.search(
            r"(?:₹|Rs\.?|INR)?\s*"
            r"(\d[\d,]*(?:\.\d+)?)"
            r"\s*$",
            description,
            flags=re.IGNORECASE
        )

        rate = None

        if rate_match:

            rate = _clean_number(
                rate_match.group(1)
            )

            description = (
                description[
                    :rate_match.start()
                ].strip()
            )

        paragraph_rows.append(
            {
                "item_no": item_no,
                "chapter": "(no chapter)",
                "description": description,
                "unit": "",
                "rate": rate,
                "labour_rate": None
            }
        )

    if not paragraph_rows:

        raise ValueError(
            "The DOCX file does not contain recognizable "
            "SSR tables or item data."
        )

    return _standardize_dataframe(
        pd.DataFrame(
            paragraph_rows
        )
    )


# ============================================================
# TXT LOADER
# ============================================================

def _load_txt(file):
    """
    Read a TXT SSR file.
    """

    raw = file.read()

    if isinstance(raw, bytes):

        text = raw.decode(
            "utf-8",
            errors="ignore"
        )

    else:

        text = str(raw)

    rows = []

    for line in text.splitlines():

        line = _clean_text(
            line
        )

        if not line:
            continue

        # ----------------------------------------------------
        # Try pipe-separated format
        # ----------------------------------------------------

        if "|" in line:

            parts = [
                _clean_text(x)
                for x in line.split("|")
            ]

            if len(parts) >= 4:

                rows.append(
                    parts
                )

                continue

        # ----------------------------------------------------
        # Try comma-separated format
        # ----------------------------------------------------

        if "," in line:

            parts = [
                _clean_text(x)
                for x in line.split(",")
            ]

            if len(parts) >= 4:

                rows.append(
                    parts
                )

                continue

        # ----------------------------------------------------
        # Try item-number text format
        # ----------------------------------------------------

        match = re.match(
            r"^(\d+(?:\.\d+)+|\d+)\s+(.*)$",
            line
        )

        if match:

            item_no = match.group(1)
            description = match.group(2)

            rate_match = re.search(
                r"(?:₹|Rs\.?|INR)?\s*"
                r"(\d[\d,]*(?:\.\d+)?)"
                r"\s*$",
                description,
                flags=re.IGNORECASE
            )

            rate = None

            if rate_match:

                rate = _clean_number(
                    rate_match.group(1)
                )

                description = (
                    description[
                        :rate_match.start()
                    ].strip()
                )

            rows.append(
                [
                    item_no,
                    "(no chapter)",
                    description,
                    "",
                    rate
                ]
            )

    if not rows:

        raise ValueError(
            "The TXT file does not contain recognizable "
            "SSR data."
        )

    # --------------------------------------------------------
    # Try to determine whether first row is a header
    # --------------------------------------------------------

    first_row = rows[0]

    first_text = " ".join(
        str(x).lower()
        for x in first_row
    )

    if (
        "item" in first_text
        or "description" in first_text
        or "rate" in first_text
    ):

        headers = first_row
        data = rows[1:]

        width = len(headers)

        fixed_data = []

        for row in data:

            row = list(row)

            if len(row) < width:

                row += [
                    ""
                ] * (
                    width - len(row)
                )

            elif len(row) > width:

                row = row[
                    :width
                ]

            fixed_data.append(
                row
            )

        df = pd.DataFrame(
            fixed_data,
            columns=headers
        )

    else:

        # Our extracted structure:
        # item_no, chapter, description, unit, rate

        fixed_rows = []

        for row in rows:

            row = list(row)

            if len(row) < 5:

                row += [
                    ""
                ] * (
                    5 - len(row)
                )

            fixed_rows.append(
                row[:5]
            )

        df = pd.DataFrame(
            fixed_rows,
            columns=[
                "item_no",
                "chapter",
                "description",
                "unit",
                "rate"
            ]
        )

    return _standardize_dataframe(
        df
    )


# ============================================================
# MAIN LOADER
# ============================================================

def load_ssr(file) -> pd.DataFrame:
    """
    Load SSR data from:

    Excel
    CSV
    PDF
    DOCX
    TXT

    Returns:
        pandas.DataFrame

    The returned DataFrame always uses the common SSR
    structure expected by app.py.
    """

    if file is None:

        raise ValueError(
            "No SSR file was provided."
        )

    # --------------------------------------------------------
    # Determine filename
    # --------------------------------------------------------

    if hasattr(file, "name"):

        filename = file.name.lower()

    else:

        filename = os.path.basename(
            str(file)
        ).lower()

    # --------------------------------------------------------
    # Excel
    # --------------------------------------------------------

    if filename.endswith(
        ".xlsx"
    ) or filename.endswith(
        ".xls"
    ):

        return _load_excel(
            file
        )

    # --------------------------------------------------------
    # CSV
    # --------------------------------------------------------

    elif filename.endswith(
        ".csv"
    ):

        return _load_csv(
            file
        )

    # --------------------------------------------------------
    # PDF
    # --------------------------------------------------------

    elif filename.endswith(
        ".pdf"
    ):

        return _load_pdf(
            file
        )

    # --------------------------------------------------------
    # DOCX
    # --------------------------------------------------------

    elif filename.endswith(
        ".docx"
    ):

        return _load_docx(
            file
        )

    # --------------------------------------------------------
    # TXT
    # --------------------------------------------------------

    elif filename.endswith(
        ".txt"
    ):

        return _load_txt(
            file
        )

    # --------------------------------------------------------
    # Unsupported
    # --------------------------------------------------------

    else:

        raise ValueError(
            "Unsupported SSR file format. "
            "Please upload XLSX, XLS, CSV, PDF, DOCX or TXT."
        )


# ============================================================
# SEARCH
# ============================================================

def search(
    df: pd.DataFrame,
    chapters=None,
    keywords=None
) -> pd.DataFrame:
    """
    Search SSR items by chapter and keywords.
    """

    out = df.copy()

    # --------------------------------------------------------
    # Chapter filter
    # --------------------------------------------------------

    if chapters:

        out = out[
            out["chapter"].isin(
                chapters
            )
        ]

    # --------------------------------------------------------
    # Keyword filter
    # --------------------------------------------------------

    if keywords:

        valid_keywords = [
            str(k).strip()
            for k in keywords
            if str(k).strip()
        ]

        if valid_keywords:

            # Use escaped keywords so special regex
            # characters do not break the search.

            pattern = "|".join(
                re.escape(k)
                for k in valid_keywords
            )

            out = out[
                out[
                    "description"
                ]
                .astype(str)
                .str.contains(
                    pattern,
                    case=False,
                    regex=True,
                    na=False
                )
            ]

    return out


# ============================================================
# CHAPTER NORMALIZATION
# ============================================================

def norm_chapter(
    name: str
) -> str:
    """
    Normalize chapter names for matching.
    """

    value = (
        str(name)
        .lower()
        .replace(
            "maintainance",
            "maintenance"
        )
    )

    value = " ".join(
        value.split()
    )

    return value


# ============================================================
# CHAPTER MATCHING
# ============================================================

def match_chapters(
    df_chapters,
    wanted
) -> list:
    """
    Map desired chapter names to real chapter names
    in the uploaded SSR.

    Matching ignores case, extra spaces and some
    spelling variations.
    """

    wanted_normalized = {
        norm_chapter(x)
        for x in wanted
    }

    return sorted(
        {
            chapter
            for chapter in df_chapters
            if norm_chapter(chapter)
            in wanted_normalized
        }
    )
