"""
SSR Loader for Road Cost Estimator

Supported formats:
- Excel .xlsx
- Excel .xls
- CSV .csv
- PDF .pdf
- DOCX .docx
- TXT .txt

The loader converts supported SSR files into one common
DataFrame structure used by the application.
"""

import io
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
# STANDARD COLUMNS
# ============================================================

STANDARD_COLUMNS = [
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
# CHAPTER NORMALIZATION
# ============================================================

def norm_chapter(name: str) -> str:
    """
    Normalize chapter names so small spelling/case/spacing
    differences do not prevent matching.
    """

    if name is None:
        return ""

    text = str(name).strip().lower()

    # Common spelling variations
    replacements = {
        "maintainance": "maintenance",
        "maintenence": "maintenance",
        "surevy": "survey",
        "survery": "survey",
        "pot hole reparing": "pothole repairing",
        "pot hole repairing": "pothole repairing",
        "road works": "road work",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    # Normalize & -> and
    text = text.replace("&", "and")

    # Remove repeated spaces
    text = " ".join(text.split())

    return text


# ============================================================
# UNIT CLEANING
# ============================================================

def _clean_unit(unit: str) -> str:
    """
    Normalize SSR unit text.
    """

    if unit is None:
        return ""

    text = " ".join(str(unit).split()).lower()

    replacements = {
        "meter": "metre",
        "meters": "metres",
        "mtr": "metre",
        "mtrs": "metres",
        "sq.m": "square metre",
        "sq m": "square metre",
        "sqm": "square metre",
        "m2": "square metre",
        "m²": "square metre",
        "cu.m": "cubic metre",
        "cu m": "cubic metre",
        "cum": "cubic metre",
        "m3": "cubic metre",
        "m³": "cubic metre",
        "r.m.": "running metre",
        "rm": "running metre",
        "rmt": "running metre",
        "nos.": "number",
        "no.": "number",
        "nos": "number",
        "no": "number",
        "mt": "tonne",
        "mts": "tonne",
        "ton": "tonne",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return text


# ============================================================
# UNIT TYPE
# ============================================================

def unit_kind(unit: str) -> str:
    """
    Convert SSR unit text into a quantity type.

    Returns:
        area
        volume
        length
        km
        nos
        tonne
        kg
        litre
        other
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

    if "tonne" in u:
        return "tonne"

    if "kilogram" in u or u == "kg":
        return "kg"

    if "litre" in u or u == "l":
        return "litre"

    if "number" in u:
        return "nos"

    return "other"


# ============================================================
# COLUMN NAME NORMALIZATION
# ============================================================

def _normalize_column_name(name):
    """
    Convert arbitrary column names into a normalized form.
    """

    if name is None:
        return ""

    text = str(name).strip().lower()

    text = text.replace("\n", " ")
    text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text)

    return text


def _find_column(columns, possible_names):
    """
    Find a column from a list of possible names.
    """

    normalized = {
        _normalize_column_name(col): col
        for col in columns
    }

    for name in possible_names:

        key = _normalize_column_name(name)

        if key in normalized:
            return normalized[key]

    # Partial matching
    for normalized_name, original_name in normalized.items():

        for possible in possible_names:

            possible_key = _normalize_column_name(possible)

            if (
                possible_key in normalized_name
                or normalized_name in possible_key
            ):
                return original_name

    return None


# ============================================================
# STANDARDIZE DATAFRAME
# ============================================================

def _standardize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert a raw DataFrame into the standard SSR structure.
    """

    if df is None or df.empty:
        raise ValueError("The SSR file contains no readable data.")

    df = df.copy()

    # --------------------------------------------------------
    # Remove completely empty rows and columns
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
        raise ValueError("The SSR file contains no usable data.")

    # --------------------------------------------------------
    # Try to identify existing named columns
    # --------------------------------------------------------

    sr_col = _find_column(
        df.columns,
        [
            "sr_no",
            "sr no",
            "serial no",
            "serial number",
            "sr. no.",
            "sr."
        ]
    )

    chapter_col = _find_column(
        df.columns,
        [
            "chapter",
            "chapter name",
            "chapter_name"
        ]
    )

    item_col = _find_column(
        df.columns,
        [
            "item_no",
            "item no",
            "item number",
            "item no.",
            "item"
        ]
    )

    description_col = _find_column(
        df.columns,
        [
            "description",
            "item description",
            "work description",
            "particulars",
            "details"
        ]
    )

    extra_col = _find_column(
        df.columns,
        [
            "extra_spec",
            "extra specification",
            "extra spec",
            "specification",
            "specifications"
        ]
    )

    unit_col = _find_column(
        df.columns,
        [
            "unit",
            "units"
        ]
    )

    rate_col = _find_column(
        df.columns,
        [
            "rate",
            "basic rate",
            "ssr rate",
            "unit rate"
        ]
    )

    labour_col = _find_column(
        df.columns,
        [
            "labour_rate",
            "labour rate",
            "labor rate",
            "labour"
        ]
    )

    # --------------------------------------------------------
    # If named columns are not found, use positional mapping
    # --------------------------------------------------------

    if item_col is None or description_col is None or rate_col is None:

        if len(df.columns) >= 9:

            positional = list(df.columns)

            # Same basic structure as your original SSR loader
            sr_col = positional[0]
            chapter_col = positional[1]
            item_col = positional[2]
            description_col = positional[4]
            extra_col = positional[5]
            unit_col = positional[6]
            rate_col = positional[7]
            labour_col = positional[8]

        elif len(df.columns) >= 5:

            # Generic fallback
            positional = list(df.columns)

            sr_col = positional[0]
            item_col = positional[1]
            description_col = positional[2]
            unit_col = positional[3]
            rate_col = positional[4]

            if len(positional) > 5:
                chapter_col = positional[5]

    # --------------------------------------------------------
    # Create standard DataFrame
    # --------------------------------------------------------

    result = pd.DataFrame(index=df.index)

    def copy_column(source_col):

        if source_col is None:
            return pd.Series(
                [""] * len(df),
                index=df.index
            )

        return df[source_col]

    result["sr_no"] = copy_column(sr_col)
    result["chapter"] = copy_column(chapter_col)
    result["item_no"] = copy_column(item_col)
    result["description"] = copy_column(description_col)
    result["extra_spec"] = copy_column(extra_col)
    result["unit"] = copy_column(unit_col)
    result["rate"] = copy_column(rate_col)
    result["labour_rate"] = copy_column(labour_col)

    # --------------------------------------------------------
    # Clean text columns
    # --------------------------------------------------------

    text_columns = [
        "chapter",
        "description",
        "extra_spec",
        "unit"
    ]

    for column in text_columns:

        result[column] = (
            result[column]
            .fillna("")
            .astype(str)
            .str.replace(r"\s+", " ", regex=True)
            .str.strip()
        )

    # --------------------------------------------------------
    # Clean chapter
    # --------------------------------------------------------

    result.loc[
        result["chapter"] == "",
        "chapter"
    ] = "(no chapter)"

    # --------------------------------------------------------
    # Convert numeric columns
    # --------------------------------------------------------

    result["rate"] = pd.to_numeric(
        result["rate"],
        errors="coerce"
    )

    result["labour_rate"] = pd.to_numeric(
        result["labour_rate"],
        errors="coerce"
    )

    # --------------------------------------------------------
    # Remove rows without item number
    # --------------------------------------------------------

    result = result[
        result["item_no"].notna()
    ].copy()

    # --------------------------------------------------------
    # Remove completely meaningless item rows
    # --------------------------------------------------------

    result["item_no"] = (
        result["item_no"]
        .astype(str)
        .str.strip()
    )

    result = result[
        result["item_no"].ne("")
        &
        result["item_no"].ne("nan")
    ]

    # --------------------------------------------------------
    # Rate must be available for estimation
    # --------------------------------------------------------

    result = result[
        result["rate"].notna()
    ].copy()

    if result.empty:
        raise ValueError(
            "No usable SSR items with valid rates were found."
        )

    # --------------------------------------------------------
    # Add quantity type
    # --------------------------------------------------------

    result["kind"] = result[
        "unit"
    ].map(unit_kind)

    # --------------------------------------------------------
    # Reset index BEFORE creating IDs
    # --------------------------------------------------------

    result = result.reset_index(
        drop=True
    )

    # --------------------------------------------------------
    # Stable internal ID
    # --------------------------------------------------------

    result["id"] = result.index.astype(int)

    # --------------------------------------------------------
    # Final column order
    # --------------------------------------------------------

    final_columns = [
        "id",
        "sr_no",
        "chapter",
        "item_no",
        "description",
        "extra_spec",
        "unit",
        "rate",
        "labour_rate",
        "kind"
    ]

    result = result[
        final_columns
    ]

    return result


# ============================================================
# EXCEL LOADER
# ============================================================

def _load_excel(source) -> pd.DataFrame:
    """
    Load .xlsx or .xls.

    For your Maharashtra PWD SSR 2022-23 workbook,
    the sheet 'SSR 2022-23' is preferred.
    """

    sheet_name = "SSR 2022-23"

    # --------------------------------------------------------
    # .xlsx / .xls from path
    # --------------------------------------------------------

    if isinstance(source, (str, os.PathLike)):

        path = str(source)

        extension = os.path.splitext(
            path
        )[1].lower()

        if extension == ".xls":

            try:
                import xlrd
            except ImportError as error:

                raise ImportError(
                    "Reading .xls files requires the "
                    "'xlrd' package. Add xlrd to requirements.txt."
                ) from error

            engine = "xlrd"

        else:

            engine = "openpyxl"

        try:

            excel = pd.ExcelFile(
                path,
                engine=engine
            )

            if sheet_name in excel.sheet_names:

                raw = pd.read_excel(
                    path,
                    sheet_name=sheet_name,
                    header=None,
                    engine=engine
                )

                # Original PWD SSR structure
                if raw.shape[1] >= 9:

                    raw = raw.iloc[2:].copy()

                    raw = raw.iloc[
                        :,
                        list(range(9))
                    ]

                    raw.columns = [
                        "sr_no",
                        "chapter",
                        "item_no",
                        "_unused_3",
                        "description",
                        "extra_spec",
                        "unit",
                        "rate",
                        "labour_rate"
                    ]

                    raw = raw.drop(
                        columns=["_unused_3"]
                    )

                    return _standardize_dataframe(
                        raw
                    )

            # ------------------------------------------------
            # Fallback to first sheet
            # ------------------------------------------------

            raw = pd.read_excel(
                path,
                sheet_name=0,
                engine=engine
            )

            return _standardize_dataframe(
                raw
            )

        except Exception as error:

            raise ValueError(
                f"Could not read Excel SSR: {error}"
            ) from error

    # --------------------------------------------------------
    # Uploaded Streamlit file / file-like object
    # --------------------------------------------------------

    data = source.getvalue()

    extension = os.path.splitext(
        getattr(source, "name", "")
    )[1].lower()

    if extension == ".xls":

        try:
            import xlrd
        except ImportError as error:

            raise ImportError(
                "Reading .xls files requires the "
                "'xlrd' package. Add xlrd to requirements.txt."
            ) from error

        engine = "xlrd"

    else:

        engine = "openpyxl"

    try:

        excel = pd.ExcelFile(
            io.BytesIO(data),
            engine=engine
        )

        if sheet_name in excel.sheet_names:

            raw = pd.read_excel(
                io.BytesIO(data),
                sheet_name=sheet_name,
                header=None,
                engine=engine
            )

            if raw.shape[1] >= 9:

                raw = raw.iloc[2:].copy()

                raw = raw.iloc[
                    :,
                    list(range(9))
                ]

                raw.columns = [
                    "sr_no",
                    "chapter",
                    "item_no",
                    "_unused_3",
                    "description",
                    "extra_spec",
                    "unit",
                    "rate",
                    "labour_rate"
                ]

                raw = raw.drop(
                    columns=["_unused_3"]
                )

                return _standardize_dataframe(
                    raw
                )

        # Fallback
        raw = pd.read_excel(
            io.BytesIO(data),
            sheet_name=0,
            engine=engine
        )

        return _standardize_dataframe(
            raw
        )

    except Exception as error:

        raise ValueError(
            f"Could not read uploaded Excel SSR: {error}"
        ) from error


# ============================================================
# CSV LOADER
# ============================================================

def _load_csv(source) -> pd.DataFrame:
    """
    Load CSV SSR.
    """

    try:

        if isinstance(source, (str, os.PathLike)):

            df = pd.read_csv(
                source
            )

        else:

            data = source.getvalue()

            try:

                df = pd.read_csv(
                    io.BytesIO(data)
                )

            except UnicodeDecodeError:

                df = pd.read_csv(
                    io.BytesIO(data),
                    encoding="latin1"
                )

        return _standardize_dataframe(
            df
        )

    except Exception as error:

        raise ValueError(
            f"Could not read CSV SSR: {error}"
        ) from error


# ============================================================
# TXT LOADER
# ============================================================

def _load_txt(source) -> pd.DataFrame:
    """
    Load a simple text-based SSR.

    This supports delimited text where possible.
    """

    if isinstance(source, (str, os.PathLike)):

        with open(
            source,
            "r",
            encoding="utf-8",
            errors="replace"
        ) as file:

            text = file.read()

    else:

        text = source.getvalue().decode(
            "utf-8",
            errors="replace"
        )

    # Try tab-separated
    try:

        df = pd.read_csv(
            io.StringIO(text),
            sep="\t"
        )

        if len(df.columns) >= 4:

            return _standardize_dataframe(
                df
            )

    except Exception:
        pass

    # Try comma-separated
    try:

        df = pd.read_csv(
            io.StringIO(text)
        )

        if len(df.columns) >= 4:

            return _standardize_dataframe(
                df
            )

    except Exception:
        pass

    raise ValueError(
        "TXT SSR could not be converted into a tabular format."
    )


# ============================================================
# PDF LOADER
# ============================================================

def _load_pdf(source) -> pd.DataFrame:
    """
    Extract tables from a PDF.

    PDF layouts vary considerably. The loader attempts to
    detect tables, but a PDF with scanned images or a complex
    layout may require a dedicated OCR/table extraction step.
    """

    if pdfplumber is None:

        raise ImportError(
            "PDF support requires the 'pdfplumber' package."
        )

    if isinstance(source, (str, os.PathLike)):

        pdf_source = source

    else:

        pdf_source = io.BytesIO(
            source.getvalue()
        )

    rows = []

    try:

        with pdfplumber.open(
            pdf_source
        ) as pdf:

            for page in pdf.pages:

                tables = page.extract_tables()

                for table in tables:

                    if not table:
                        continue

                    for row in table:

                        if row:
                            rows.append(row)

    except Exception as error:

        raise ValueError(
            f"Could not extract tables from PDF: {error}"
        ) from error

    if not rows:

        raise ValueError(
            "No tabular data could be extracted from the PDF."
        )

    # --------------------------------------------------------
    # Determine maximum number of columns
    # --------------------------------------------------------

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
            max_columns - len(row)
        )

        normalized_rows.append(
            row
        )

    df = pd.DataFrame(
        normalized_rows
    )

    # PDF usually contains multiple header rows.
    # Standardization will attempt positional detection.
    return _standardize_dataframe(
        df
    )


# ============================================================
# DOCX LOADER
# ============================================================

def _load_docx(source) -> pd.DataFrame:
    """
    Extract tables from DOCX.
    """

    if Document is None:

        raise ImportError(
            "DOCX support requires the 'python-docx' package."
        )

    try:

        if isinstance(source, (str, os.PathLike)):

            document = Document(
                source
            )

        else:

            document = Document(
                io.BytesIO(
                    source.getvalue()
                )
            )

    except Exception as error:

        raise ValueError(
            f"Could not open DOCX file: {error}"
        ) from error

    rows = []

    for table in document.tables:

        for row in table.rows:

            values = [
                cell.text.strip()
                for cell in row.cells
            ]

            if any(values):

                rows.append(
                    values
                )

    if not rows:

        raise ValueError(
            "No table data was found in the DOCX file."
        )

    max_columns = max(
        len(row)
        for row in rows
    )

    normalized_rows = []

    for row in rows:

        row = list(row)

        row += [
            ""
        ] * (
            max_columns - len(row)
        )

        normalized_rows.append(
            row
        )

    df = pd.DataFrame(
        normalized_rows
    )

    return _standardize_dataframe(
        df
    )


# ============================================================
# MAIN LOADER
# ============================================================

def load_ssr(source) -> pd.DataFrame:
    """
    Load an SSR file and return a standardized DataFrame.

    Accepted:
        .xlsx
        .xls
        .csv
        .pdf
        .docx
        .txt
    """

    if source is None:

        raise ValueError(
            "No SSR file was provided."
        )

    # --------------------------------------------------------
    # Determine file extension
    # --------------------------------------------------------

    if isinstance(source, (str, os.PathLike)):

        extension = os.path.splitext(
            str(source)
        )[1].lower()

    else:

        filename = getattr(
            source,
            "name",
            ""
        )

        extension = os.path.splitext(
            filename
        )[1].lower()

    # --------------------------------------------------------
    # Route to correct loader
    # --------------------------------------------------------

    if extension in (
        ".xlsx",
        ".xls"
    ):

        return _load_excel(
            source
        )

    if extension == ".csv":

        return _load_csv(
            source
        )

    if extension == ".pdf":

        return _load_pdf(
            source
        )

    if extension == ".docx":

        return _load_docx(
            source
        )

    if extension == ".txt":

        return _load_txt(
            source
        )

    raise ValueError(
        f"Unsupported SSR file format: {extension or 'unknown'}"
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
    Search SSR items by chapter and description keywords.
    """

    if df is None or df.empty:

        return pd.DataFrame(
            columns=df.columns
            if isinstance(df, pd.DataFrame)
            else STANDARD_COLUMNS
        )

    out = df.copy()

    # --------------------------------------------------------
    # Chapter filtering
    # --------------------------------------------------------

    if chapters:

        wanted = {
            norm_chapter(chapter)
            for chapter in chapters
            if str(chapter).strip()
        }

        if wanted:

            out = out[
                out["chapter"]
                .map(norm_chapter)
                .isin(wanted)
            ]

    # --------------------------------------------------------
    # Keyword filtering
    # --------------------------------------------------------

    if keywords:

        clean_keywords = [
            str(keyword).strip()
            for keyword in keywords
            if str(keyword).strip()
        ]

        if clean_keywords:

            # Search each keyword safely.
            mask = pd.Series(
                False,
                index=out.index
            )

            for keyword in clean_keywords:

                mask = mask | (
                    out["description"]
                    .astype(str)
                    .str.contains(
                        re.escape(keyword),
                        case=False,
                        regex=True,
                        na=False
                    )
                )

            out = out[mask]

    return out.reset_index(
        drop=True
    )


# ============================================================
# MATCH CHAPTERS
# ============================================================

def match_chapters(
    df_chapters,
    wanted
) -> list:
    """
    Map requested chapter names to the actual chapter names
    present in the SSR.

    Matching ignores:
    - case
    - repeated spaces
    - selected spelling variations
    """

    if not wanted:
        return []

    wanted_normalized = {
        norm_chapter(name)
        for name in wanted
        if str(name).strip()
    }

    matches = []

    for chapter in df_chapters:

        normalized = norm_chapter(
            chapter
        )

        if normalized in wanted_normalized:

            matches.append(
                chapter
            )

    return sorted(
        set(matches)
    )
