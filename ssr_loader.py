"""
SSR Loader

Supports:
- Excel (.xlsx, .xls)
- CSV (.csv)
- PDF (.pdf)
- Word (.docx)
- Text (.txt)

All supported files are converted into a common DataFrame structure
used by the Road Estimator.
"""

import io
import re

import pandas as pd
import pdfplumber
from docx import Document


# ============================================================
# EXCEL SETTINGS
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
# UNIT FUNCTIONS
# ============================================================

def _clean_unit(u: str) -> str:
    """
    Clean SSR unit text.
    """

    u = " ".join(str(u).split()).lower()

    u = u.replace(
        "meter",
        "metre"
    )

    return u


def unit_kind(unit: str) -> str:
    """
    Map SSR unit text to a quantity type.
    """

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


# ============================================================
# COMMON DATAFRAME CLEANING
# ============================================================

def _clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean and standardize SSR data so every supported file format
    produces the same DataFrame structure.
    """

    # Make a copy so the original data is not modified.
    df = df.copy()

    # --------------------------------------------------------
    # Make sure all required columns exist
    # --------------------------------------------------------

    required_columns = [
        "sr_no",
        "chapter",
        "item_no",
        "description",
        "extra_spec",
        "unit",
        "rate",
        "labour_rate",
    ]

    for column in required_columns:

        if column not in df.columns:

            df[column] = ""


    # --------------------------------------------------------
    # Clean text columns
    # --------------------------------------------------------

    for column in [
        "chapter",
        "description",
        "unit",
        "extra_spec",
    ]:

        df[column] = (
            df[column]
            .fillna("")
            .astype(str)
            .str.replace(
                r"\s+",
                " ",
                regex=True
            )
            .str.strip()
        )


    # --------------------------------------------------------
    # Chapter
    # --------------------------------------------------------

    df["chapter"] = (
        df["chapter"]
        .replace(
            "",
            "(no chapter)"
        )
    )


    # --------------------------------------------------------
    # Numeric columns
    # --------------------------------------------------------

    df["rate"] = pd.to_numeric(
        df["rate"],
        errors="coerce"
    )

    df["labour_rate"] = pd.to_numeric(
        df["labour_rate"],
        errors="coerce"
    )


    # --------------------------------------------------------
    # Remove rows without item number
    # --------------------------------------------------------

    df = df[
        df["item_no"].notna()
    ].copy()


    # --------------------------------------------------------
    # Remove rows without rate
    # --------------------------------------------------------

    df = df[
        df["rate"].notna()
    ].copy()


    # --------------------------------------------------------
    # Convert item number to text
    # --------------------------------------------------------

    df["item_no"] = (
        df["item_no"]
        .astype(str)
        .str.strip()
    )


    # --------------------------------------------------------
    # Unit type
    # --------------------------------------------------------

    df["kind"] = (
        df["unit"]
        .map(unit_kind)
    )


    # --------------------------------------------------------
    # Unique ID
    # --------------------------------------------------------

    df = df.reset_index(
        drop=True
    )

    df["id"] = df.index


    return df


# ============================================================
# EXCEL LOADER
# ============================================================

def _load_excel(file) -> pd.DataFrame:
    """
    Load Maharashtra PWD SSR Excel file.

    First attempts to read the official SSR structure.
    If that structure is not found, attempts a more general
    Excel table format.
    """

    try:

        raw = pd.read_excel(
            file,
            sheet_name=SHEET,
            header=None,
            usecols=range(9)
        )

        df = (
            raw
            .iloc[2:]
            .rename(columns=COLS)
        )

        df = df[
            list(COLS.values())
        ]

        return _clean_dataframe(
            df
        )

    except Exception:

        # ----------------------------------------------------
        # Fallback for normal Excel tables
        # ----------------------------------------------------

        file.seek(0)

        excel_file = pd.ExcelFile(
            file
        )

        first_sheet = (
            excel_file.sheet_names[0]
        )

        df = pd.read_excel(
            file,
            sheet_name=first_sheet
        )

        df = _standardize_columns(
            df
        )

        return _clean_dataframe(
            df
        )


# ============================================================
# CSV LOADER
# ============================================================

def _load_csv(file) -> pd.DataFrame:
    """
    Load SSR CSV file.
    """

    file.seek(0)

    df = pd.read_csv(
        file
    )

    df = _standardize_columns(
        df
    )

    return _clean_dataframe(
        df
    )


# ============================================================
# PDF LOADER
# ============================================================

def _load_pdf(file) -> pd.DataFrame:
    """
    Load text-based SSR PDF.

    This requires pdfplumber.

    Important:
    Scanned/image-only PDFs require OCR and may not work
    with this basic loader.
    """

    try:

        import pdfplumber

    except ImportError:

        raise ImportError(
            "PDF support requires pdfplumber. "
            "Add 'pdfplumber' to requirements.txt."
        )


    file.seek(0)

    extracted_rows = []

    with pdfplumber.open(
        file
    ) as pdf:

        for page in pdf.pages:

            # ----------------------------------------------
            # Try table extraction first
            # ----------------------------------------------

            tables = page.extract_tables()

            if tables:

                for table in tables:

                    for row in table:

                        if not row:
                            continue

                        extracted_rows.append(
                            row
                        )

            else:

                # ------------------------------------------
                # Fallback to text extraction
                # ------------------------------------------

                text = page.extract_text()

                if text:

                    for line in text.splitlines():

                        extracted_rows.append(
                            [line]
                        )


    if not extracted_rows:

        raise ValueError(
            "No readable data was found in the PDF. "
            "If the PDF is scanned, OCR support is required."
        )


    # --------------------------------------------------------
    # Try converting extracted table data
    # --------------------------------------------------------

    max_columns = max(
        len(row)
        for row in extracted_rows
    )


    normalized_rows = []

    for row in extracted_rows:

        row = list(row)

        row += [
            ""
        ] * (
            max_columns - len(row)
        )

        normalized_rows.append(
            row
        )


    raw_df = pd.DataFrame(
        normalized_rows
    )


    # --------------------------------------------------------
    # Attempt to identify columns
    # --------------------------------------------------------

    df = _convert_generic_table(
        raw_df
    )


    return _clean_dataframe(
        df
    )


# ============================================================
# DOCX LOADER
# ============================================================

def _load_docx(file) -> pd.DataFrame:
    """
    Load SSR from a Word document.

    Tables are preferred.
    """

    try:

        from docx import Document

    except ImportError:

        raise ImportError(
            "DOCX support requires python-docx. "
            "Add 'python-docx' to requirements.txt."
        )


    file.seek(0)

    document = Document(
        file
    )


    rows = []


    # --------------------------------------------------------
    # Read Word tables
    # --------------------------------------------------------

    for table in document.tables:

        for row in table.rows:

            rows.append(
                [
                    cell.text.strip()
                    for cell in row.cells
                ]
            )


    if rows:

        raw_df = pd.DataFrame(
            rows
        )

        df = _convert_generic_table(
            raw_df
        )

        return _clean_dataframe(
            df
        )


    # --------------------------------------------------------
    # Fallback: read paragraphs
    # --------------------------------------------------------

    paragraphs = []

    for paragraph in document.paragraphs:

        text = paragraph.text.strip()

        if text:

            paragraphs.append(
                [text]
            )


    if not paragraphs:

        raise ValueError(
            "No readable SSR data was found in the DOCX file."
        )


    raw_df = pd.DataFrame(
        paragraphs
    )

    df = _convert_generic_table(
        raw_df
    )

    return _clean_dataframe(
        df
    )


# ============================================================
# TXT LOADER
# ============================================================

def _load_txt(file) -> pd.DataFrame:
    """
    Load a simple text-based SSR file.
    """

    file.seek(0)

    content = file.read()

    if isinstance(
        content,
        bytes
    ):

        content = content.decode(
            "utf-8",
            errors="ignore"
        )


    lines = [
        line.strip()
        for line in content.splitlines()
        if line.strip()
    ]


    if not lines:

        raise ValueError(
            "The TXT file is empty."
        )


    rows = []


    for line in lines:

        # Try common separators.
        if "|" in line:

            row = [
                x.strip()
                for x in line.split("|")
            ]

        elif "\t" in line:

            row = [
                x.strip()
                for x in line.split("\t")
            ]

        elif "," in line:

            row = [
                x.strip()
                for x in line.split(",")
            ]

        else:

            row = [
                line
            ]


        rows.append(
            row
        )


    raw_df = pd.DataFrame(
        rows
    )


    df = _convert_generic_table(
        raw_df
    )


    return _clean_dataframe(
        df
    )


# ============================================================
# GENERIC COLUMN STANDARDIZATION
# ============================================================

def _normalize_column_name(name) -> str:

    name = str(
        name
    ).lower().strip()

    name = re.sub(
        r"[^a-z0-9]+",
        "_",
        name
    )

    return name.strip("_")


def _standardize_columns(
    df: pd.DataFrame
) -> pd.DataFrame:
    """
    Convert common SSR column names into the internal names
    used by the application.
    """

    df = df.copy()


    rename_map = {}


    for column in df.columns:

        normalized = _normalize_column_name(
            column
        )


        if normalized in [
            "sr_no",
            "sr",
            "serial_no",
            "serial_number",
            "s_no"
        ]:

            rename_map[
                column
            ] = "sr_no"


        elif normalized in [
            "chapter",
            "chapter_name",
            "section"
        ]:

            rename_map[
                column
            ] = "chapter"


        elif normalized in [
            "item_no",
            "item_number",
            "item",
            "item_code",
            "code"
        ]:

            rename_map[
                column
            ] = "item_no"


        elif normalized in [
            "description",
            "item_description",
            "particulars",
            "work_description"
        ]:

            rename_map[
                column
            ] = "description"


        elif normalized in [
            "extra_spec",
            "extra_specification",
            "specification",
            "specifications"
        ]:

            rename_map[
                column
            ] = "extra_spec"


        elif normalized in [
            "unit",
            "units"
        ]:

            rename_map[
                column
            ] = "unit"


        elif normalized in [
            "rate",
            "basic_rate",
            "unit_rate",
            "amount"
        ]:

            rename_map[
                column
            ] = "rate"


        elif normalized in [
            "labour_rate",
            "labor_rate",
            "labour",
            "labor"
        ]:

            rename_map[
                column
            ] = "labour_rate"


    df = df.rename(
        columns=rename_map
    )


    return df


# ============================================================
# GENERIC TABLE CONVERTER
# ============================================================

def _convert_generic_table(
    raw_df: pd.DataFrame
) -> pd.DataFrame:
    """
    Attempt to convert an extracted table into the common SSR
    structure.
    """

    df = raw_df.copy()


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


    if df.empty:

        raise ValueError(
            "No table data was found."
        )


    # --------------------------------------------------------
    # Try first row as header
    # --------------------------------------------------------

    first_row = [
        str(x).strip()
        for x in df.iloc[0].tolist()
    ]


    header_text = " ".join(
        first_row
    ).lower()


    header_keywords = [
        "item",
        "description",
        "rate",
        "unit",
        "chapter"
    ]


    header_found = sum(
        keyword in header_text
        for keyword in header_keywords
    )


    if header_found >= 2:

        df.columns = first_row

        df = df.iloc[
            1:
        ].copy()


        df = _standardize_columns(
            df
        )


    # --------------------------------------------------------
    # If no recognizable headers exist,
    # use positional mapping.
    # --------------------------------------------------------

    if "item_no" not in df.columns:

        columns = list(
            df.columns
        )


        # Common simple SSR layout:
        #
        # 0 = serial
        # 1 = chapter
        # 2 = item number
        # 3 = description
        # 4 = unit
        # 5 = rate


        if len(columns) >= 6:

            rename = {
                columns[0]: "sr_no",
                columns[1]: "chapter",
                columns[2]: "item_no",
                columns[3]: "description",
                columns[4]: "unit",
                columns[5]: "rate",
            }


            if len(columns) >= 7:

                rename[
                    columns[6]
                ] = "labour_rate"


            df = df.rename(
                columns=rename
            )


    return df


# ============================================================
# MAIN SSR LOADER
# ============================================================

def load_ssr(file) -> pd.DataFrame:
    """
    Load SSR based on the uploaded file type.

    Supported:
        XLSX
        XLS
        CSV
        PDF
        DOCX
        TXT
    """

    # --------------------------------------------------------
    # Get filename
    # --------------------------------------------------------

    if hasattr(
        file,
        "name"
    ):

        filename = file.name.lower()

    else:

        filename = str(
            file
        ).lower()


    # --------------------------------------------------------
    # Excel
    # --------------------------------------------------------

    if filename.endswith(
        (
            ".xlsx",
            ".xls"
        )
    ):

        return _load_excel(
            file
        )


    # --------------------------------------------------------
    # CSV
    # --------------------------------------------------------

    if filename.endswith(
        ".csv"
    ):

        return _load_csv(
            file
        )


    # --------------------------------------------------------
    # PDF
    # --------------------------------------------------------

    if filename.endswith(
        ".pdf"
    ):

        return _load_pdf(
            file
        )


    # --------------------------------------------------------
    # DOCX
    # --------------------------------------------------------

    if filename.endswith(
        ".docx"
    ):

        return _load_docx(
            file
        )


    # --------------------------------------------------------
    # TXT
    # --------------------------------------------------------

    if filename.endswith(
        ".txt"
    ):

        return _load_txt(
            file
        )


    # --------------------------------------------------------
    # Unsupported format
    # --------------------------------------------------------

    raise ValueError(
        "Unsupported SSR file format. "
        "Please upload XLSX, XLS, CSV, PDF, DOCX or TXT."
    )


# ============================================================
# SSR SEARCH
# ============================================================

def search(
    df: pd.DataFrame,
    chapters=None,
    keywords=None
) -> pd.DataFrame:
    """
    Search SSR items by chapter and keywords.
    """

    out = df


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

        cleaned_keywords = [
            str(k).strip()
            for k in keywords
            if str(k).strip()
        ]


        if cleaned_keywords:

            pattern = "|".join(
                re.escape(k)
                for k in cleaned_keywords
            )


            out = out[
                out["description"]
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
    Normalize chapter names so small spelling/case differences
    do not prevent matching.
    """

    name = str(
        name
    ).lower()


    # Common spelling corrections.
    name = name.replace(
        "maintainance",
        "maintenance"
    )


    name = name.replace(
        "surevy",
        "survey"
    )


    name = name.replace(
        "sub  grade",
        "sub grade"
    )


    name = name.replace(
        "sub-grade",
        "sub grade"
    )


    name = " ".join(
        name.split()
    )


    return name


# ============================================================
# CHAPTER MATCHING
# ============================================================

def match_chapters(
    df_chapters,
    wanted
) -> list:
    """
    Map requested chapter names to actual SSR chapter names.

    Matching ignores:
    - case
    - extra spaces
    - selected spelling differences
    """

    wanted_normalized = {
        norm_chapter(x)
        for x in wanted
    }


    matched = set()


    for chapter in df_chapters:

        normalized_chapter = norm_chapter(
            chapter
        )


        if normalized_chapter in wanted_normalized:

            matched.add(
                chapter
            )


    return sorted(
        matched
    )
