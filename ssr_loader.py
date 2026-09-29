"""
SSR Loader for Road Cost Estimator

Designed for Maharashtra PWD SSR 2022-23.

The loader converts the original SSR Excel workbook into a
standard DataFrame used by app.py.

Required output columns:

    id
    item_no
    chapter
    description
    unit
    rate
    kind

Supported input:
    - Excel .xlsx
    - Excel .xls
    - CSV
    - Streamlit UploadedFile
    - file path
    - bytes

The loader specifically understands the Maharashtra PWD
"SSR 2022-23" worksheet structure.
"""

import io
import os
import re

import pandas as pd


# ============================================================
# TEXT HELPERS
# ============================================================

def _clean_text(value):
    """
    Convert a cell value into clean readable text.
    """

    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    text = str(value)

    # Replace line breaks / tabs / repeated spaces
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def _normalise_name(value):
    """
    Normalize a column/sheet name for comparisons.
    """

    text = _clean_text(value).lower()

    text = text.replace("\n", " ")
    text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ============================================================
# SOURCE HANDLING
# ============================================================

def _prepare_excel_source(source):
    """
    Convert different input types into something pandas can read.
    """

    # --------------------------------------------------------
    # File path
    # --------------------------------------------------------

    if isinstance(source, (str, os.PathLike)):

        path = os.fspath(source)

        if not os.path.exists(path):
            raise FileNotFoundError(
                f"SSR file not found: {path}"
            )

        return path

    # --------------------------------------------------------
    # Streamlit UploadedFile / file-like object
    # --------------------------------------------------------

    if hasattr(source, "seek"):

        try:
            source.seek(0)
        except Exception:
            pass

        return source

    # --------------------------------------------------------
    # Raw bytes
    # --------------------------------------------------------

    if isinstance(source, (bytes, bytearray)):

        return io.BytesIO(source)

    raise TypeError(
        "Unsupported SSR source. "
        "Please provide an Excel file, CSV file, "
        "file path, bytes, or Streamlit UploadedFile."
    )


# ============================================================
# FIND SSR WORKSHEET
# ============================================================

def _find_ssr_sheet(excel_file):
    """
    Find the actual Maharashtra PWD SSR worksheet.

    Preferred:
        SSR 2022-23

    Fallback:
        Any sheet containing 'SSR 2022-23'
    """

    sheet_names = excel_file.sheet_names

    # Exact normalized match
    for sheet in sheet_names:

        if _normalise_name(sheet) == "ssr 2022-23":

            return sheet

    # Partial match
    for sheet in sheet_names:

        normalized = _normalise_name(sheet)

        if "ssr 2022-23" in normalized:

            return sheet

    # General SSR fallback
    for sheet in sheet_names:

        normalized = _normalise_name(sheet)

        if (
            "state schedule of rates" in normalized
            or normalized.startswith("ssr")
        ):

            return sheet

    raise ValueError(
        "The Maharashtra PWD SSR worksheet "
        "'SSR 2022-23' could not be found."
    )


# ============================================================
# FIND COLUMNS
# ============================================================

def _find_columns(columns):
    """
    Detect the important SSR columns.

    The actual Maharashtra SSR workbook contains:

        Sr. No.
        Chapter
        SSR Item No.
        Reference No.
        Description of the item
        Additional Specification
        Unit
        Completed Rate for 2022-23 excluding GST In Rs.
        Labour Rate...

    Only the required columns are extracted.
    """

    mapping = {}

    for column in columns:

        normalized = _normalise_name(column)

        # Sr. No.
        if (
            "sr" in normalized
            and "no" in normalized
            and "item" not in normalized
        ):
            mapping.setdefault(
                "sr_no",
                column
            )

        # Chapter
        elif normalized == "chapter":
            mapping["chapter"] = column

        elif "chapter" in normalized:
            mapping.setdefault(
                "chapter",
                column
            )

        # SSR Item Number
        elif (
            "ssr item" in normalized
            or normalized == "item no"
            or "item number" in normalized
        ):
            mapping["item_no"] = column

        # Description
        elif (
            "description of the item" in normalized
            or normalized == "description"
            or normalized.startswith("description ")
        ):
            mapping.setdefault(
                "description",
                column
            )

        # Unit
        elif normalized == "unit":
            mapping["unit"] = column

        elif "unit" == normalized.strip():
            mapping.setdefault(
                "unit",
                column
            )

        # Completed SSR Rate
        elif (
            "completed rate" in normalized
            and "2022-23" in normalized
        ):
            mapping["rate"] = column

        elif (
            "completed rate" in normalized
            and "rate" not in mapping
        ):
            mapping.setdefault(
                "rate",
                column
            )

    required = [
        "sr_no",
        "chapter",
        "item_no",
        "description",
        "unit",
        "rate"
    ]

    missing = [
        field
        for field in required
        if field not in mapping
    ]

    if missing:

        raise ValueError(
            "The SSR workbook is missing required columns: "
            + ", ".join(missing)
        )

    return mapping


# ============================================================
# INFER QUANTITY KIND
# ============================================================

def _infer_kind(unit, description=""):
    """
    Determine how the estimator should calculate a default quantity.

    Possible values:

        area
        volume
        length
        km
        number

    This is only a quantity-type helper.
    It does NOT decide engineering quantities.
    """

    unit_text = _clean_text(unit).lower()

    description_text = _clean_text(
        description
    ).lower()

    # --------------------------------------------------------
    # Volume
    # --------------------------------------------------------

    volume_patterns = [
        "cubic metre",
        "cubic meter",
        "cubic m",
        "cum",
        "m3",
        "m³",
        "cu.m",
        "cubic"
    ]

    if any(
        pattern in unit_text
        for pattern in volume_patterns
    ):

        return "volume"

    # --------------------------------------------------------
    # Area
    # --------------------------------------------------------

    area_patterns = [
        "square metre",
        "square meter",
        "square m",
        "sq metre",
        "sq meter",
        "sq.m",
        "sqm",
        "m2",
        "m²",
        "acre"
    ]

    if any(
        pattern in unit_text
        for pattern in area_patterns
    ):

        return "area"

    # --------------------------------------------------------
    # Kilometre
    # --------------------------------------------------------

    if (
        "kilometre" in unit_text
        or "kilometer" in unit_text
        or "km" == unit_text
        or "one kilometre" in unit_text
        or "running one kilometre" in unit_text
    ):

        return "km"

    # --------------------------------------------------------
    # Length
    # --------------------------------------------------------

    length_patterns = [
        "running metre",
        "running meter",
        "one running metre",
        "one running meter",
        "running one meter",
        "running one metre",
        "metre",
        "meter",
        "metre",
        "mtr"
    ]

    if any(
        pattern in unit_text
        for pattern in length_patterns
    ):

        return "length"

    # --------------------------------------------------------
    # Description fallback
    # --------------------------------------------------------

    if (
        "length" in description_text
        and "road" in description_text
    ):

        return "length"

    # --------------------------------------------------------
    # Everything else
    # --------------------------------------------------------

    return "number"


# ============================================================
# LOAD EXCEL SSR
# ============================================================

def _load_excel(source):
    """
    Read the actual Maharashtra PWD SSR workbook.
    """

    prepared_source = _prepare_excel_source(
        source
    )

    try:

        excel_file = pd.ExcelFile(
            prepared_source
        )

    except Exception as error:

        raise ValueError(
            "Unable to open the SSR Excel file. "
            "Please upload a valid .xlsx or .xls file."
        ) from error

    # --------------------------------------------------------
    # Find SSR worksheet
    # --------------------------------------------------------

    sheet_name = _find_ssr_sheet(
        excel_file
    )

    # --------------------------------------------------------
    # Read only columns A:I.
    #
    # The workbook contains a very large formatted sheet.
    # Reading only the actual SSR columns avoids unnecessary
    # memory usage.
    # --------------------------------------------------------

    try:

        raw = pd.read_excel(
            excel_file,
            sheet_name=sheet_name,
            usecols="A:I",
            header=1
        )

    except Exception as error:

        raise ValueError(
            f"Could not read the SSR worksheet '{sheet_name}'."
        ) from error

    if raw.empty:

        raise ValueError(
            "The SSR worksheet is empty."
        )

    # --------------------------------------------------------
    # Clean column names
    # --------------------------------------------------------

    raw.columns = [
        _clean_text(column).lower()
        for column in raw.columns
    ]

    # --------------------------------------------------------
    # Detect columns
    # --------------------------------------------------------

    column_map = _find_columns(
        raw.columns
    )

    # --------------------------------------------------------
    # Select only required columns
    # --------------------------------------------------------

    data = raw[
        [
            column_map["sr_no"],
            column_map["chapter"],
            column_map["item_no"],
            column_map["description"],
            column_map["unit"],
            column_map["rate"]
        ]
    ].copy()

    data.columns = [
        "sr_no",
        "chapter",
        "item_no",
        "description",
        "unit",
        "rate"
    ]

    return data


# ============================================================
# LOAD CSV SSR
# ============================================================

def _load_csv(source):
    """
    Load an SSR CSV file.
    """

    prepared_source = source

    if isinstance(
        source,
        (bytes, bytearray)
    ):

        prepared_source = io.BytesIO(
            source
        )

    try:

        # First try normal header
        raw = pd.read_csv(
            prepared_source
        )

    except Exception as error:

        raise ValueError(
            "Unable to read the CSV SSR file."
        ) from error

    if raw.empty:

        raise ValueError(
            "The uploaded SSR CSV is empty."
        )

    raw.columns = [
        _clean_text(column).lower()
        for column in raw.columns
    ]

    column_map = _find_columns(
        raw.columns
    )

    data = raw[
        [
            column_map["sr_no"],
            column_map["chapter"],
            column_map["item_no"],
            column_map["description"],
            column_map["unit"],
            column_map["rate"]
        ]
    ].copy()

    data.columns = [
        "sr_no",
        "chapter",
        "item_no",
        "description",
        "unit",
        "rate"
    ]

    return data


# ============================================================
# NORMALIZE SSR DATA
# ============================================================

def _normalise_ssr(raw):
    """
    Convert raw SSR data into the DataFrame expected by app.py.
    """

    data = raw.copy()

    # --------------------------------------------------------
    # Clean text columns
    # --------------------------------------------------------

    for column in [
        "chapter",
        "description",
        "unit"
    ]:

        data[column] = data[column].map(
            _clean_text
        )

    # --------------------------------------------------------
    # Forward-fill chapters
    #
    # In the Maharashtra SSR:
    #
    # Row 3:
    #   Road Survey and DPR
    #
    # Following rows contain item numbers while the chapter
    # cell may be blank.
    #
    # Therefore the current chapter is carried forward.
    # --------------------------------------------------------

    current_chapter = ""

    chapters = []

    for _, row in data.iterrows():

        chapter = _clean_text(
            row["chapter"]
        )

        if chapter:

            current_chapter = chapter

        chapters.append(
            current_chapter
        )

    data["chapter"] = chapters

    # --------------------------------------------------------
    # Numeric conversions
    # --------------------------------------------------------

    data["sr_no_numeric"] = pd.to_numeric(
        data["sr_no"],
        errors="coerce"
    )

    data["item_no_numeric"] = pd.to_numeric(
        data["item_no"],
        errors="coerce"
    )

    data["rate"] = pd.to_numeric(
        data["rate"],
        errors="coerce"
    )

    # --------------------------------------------------------
    # Keep actual SSR item rows only
    #
    # Chapter title rows have no SSR item number.
    # --------------------------------------------------------

    valid_rows = (
        data["item_no_numeric"].notna()
        &
        data["description"].ne("")
        &
        data["unit"].ne("")
        &
        data["rate"].notna()
    )

    data = data.loc[
        valid_rows
    ].copy()

    if data.empty:

        raise ValueError(
            "No valid SSR items were found in the workbook."
        )

    # --------------------------------------------------------
    # Clean item numbers
    #
    # Example:
    #
    # 1.01 -> "1.01"
    # 1.1  -> "1.1"
    # --------------------------------------------------------

    data["item_no"] = data[
        "item_no_numeric"
    ].map(
        lambda value: (
            f"{value:g}"
            if pd.notna(value)
            else ""
        )
    )

    # --------------------------------------------------------
    # Make rate numeric
    # --------------------------------------------------------

    data["rate"] = pd.to_numeric(
        data["rate"],
        errors="coerce"
    )

    # --------------------------------------------------------
    # Infer quantity kind
    # --------------------------------------------------------

    data["kind"] = [
        _infer_kind(
            unit,
            description
        )
        for unit, description
        in zip(
            data["unit"],
            data["description"]
        )
    ]

    # --------------------------------------------------------
    # Create internal ID
    #
    # app.py uses this as the DataFrame index.
    # --------------------------------------------------------

    data.reset_index(
        drop=True,
        inplace=True
    )

    data.insert(
        0,
        "id",
        range(
            len(data)
        )
    )

    # --------------------------------------------------------
    # Final column order
    # --------------------------------------------------------

    result = data[
        [
            "id",
            "item_no",
            "chapter",
            "description",
            "unit",
            "rate",
            "kind"
        ]
    ].copy()

    # --------------------------------------------------------
    # Final cleanup
    # --------------------------------------------------------

    result["chapter"] = result[
        "chapter"
    ].map(_clean_text)

    result["description"] = result[
        "description"
    ].map(_clean_text)

    result["unit"] = result[
        "unit"
    ].map(_clean_text)

    result["rate"] = pd.to_numeric(
        result["rate"],
        errors="coerce"
    )

    result = result[
        result["rate"].notna()
    ].copy()

    result.reset_index(
        drop=True,
        inplace=True
    )

    # Re-create IDs after final filtering
    result["id"] = range(
        len(result)
    )

    return result


# ============================================================
# PUBLIC LOAD FUNCTION
# ============================================================

def load_ssr(source):
    """
    Main SSR loading function used by app.py.

    Example:

        df = load_ssr(uploaded_file)

    or:

        df = load_ssr("SSR_2022-23 (2).xlsx")
    """

    if source is None:

        raise ValueError(
            "No SSR file was provided."
        )

    # --------------------------------------------------------
    # Detect file extension
    # --------------------------------------------------------

    filename = ""

    if isinstance(
        source,
        (str, os.PathLike)
    ):

        filename = os.fspath(
            source
        )

    elif hasattr(
        source,
        "name"
    ):

        filename = str(
            source.name
        )

    filename = filename.lower()

    # --------------------------------------------------------
    # CSV
    # --------------------------------------------------------

    if filename.endswith(
        ".csv"
    ):

        raw = _load_csv(
            source
        )

    # --------------------------------------------------------
    # Excel
    # --------------------------------------------------------

    else:

        raw = _load_excel(
            source
        )

    # --------------------------------------------------------
    # Normalize
    # --------------------------------------------------------

    result = _normalise_ssr(
        raw
    )

    # --------------------------------------------------------
    # Safety check
    # --------------------------------------------------------

    required_columns = [
        "id",
        "item_no",
        "chapter",
        "description",
        "unit",
        "rate",
        "kind"
    ]

    missing = [
        column
        for column in required_columns
        if column not in result.columns
    ]

    if missing:

        raise ValueError(
            "SSR loader failed to create required columns: "
            + ", ".join(missing)
        )

    if result.empty:

        raise ValueError(
            "SSR contains no usable items."
        )

    return result


# ============================================================
# CHAPTER MATCHING
# ============================================================

def match_chapters(
    available_chapters,
    wanted_chapters
):
    """
    Match requested chapter names against the actual
    chapter names in the SSR.

    This is tolerant of:
        - capitalization
        - extra spaces
        - line breaks
        - small spelling differences

    Example:

        match_chapters(
            all_chapters,
            ["Road Sub grade"]
        )
    """

    if not available_chapters:
        return []

    if not wanted_chapters:
        return []

    result = []

    normalized_available = []

    for chapter in available_chapters:

        clean = _clean_text(
            chapter
        )

        normalized_available.append(
            (
                clean,
                _normalise_name(
                    clean
                )
            )
        )

    for wanted in wanted_chapters:

        wanted_clean = _clean_text(
            wanted
        )

        if not wanted_clean:
            continue

        wanted_normalized = _normalise_name(
            wanted_clean
        )

        # ----------------------------------------------------
        # Exact match
        # ----------------------------------------------------

        for actual, normalized in normalized_available:

            if normalized == wanted_normalized:

                if actual not in result:
                    result.append(actual)

        # ----------------------------------------------------
        # Substring match
        # ----------------------------------------------------

        if not any(
            _normalise_name(item)
            == wanted_normalized
            for item in result
        ):

            for actual, normalized in normalized_available:

                if (
                    wanted_normalized in normalized
                    or normalized in wanted_normalized
                ):

                    if actual not in result:
                        result.append(actual)

    return result


# ============================================================
# SSR ITEM SEARCH
# ============================================================

def search(
    df,
    chapters=None,
    keywords=None
):
    """
    Search SSR items.

    Parameters
    ----------
    df:
        SSR DataFrame returned by load_ssr()

    chapters:
        List of chapter names.

    keywords:
        List of search keywords.

    Returns
    -------
    DataFrame
    """

    if df is None:

        return pd.DataFrame()

    if not isinstance(
        df,
        pd.DataFrame
    ):

        raise TypeError(
            "SSR search expects a pandas DataFrame."
        )

    result = df.copy()

    # --------------------------------------------------------
    # Chapter filtering
    # --------------------------------------------------------

    if chapters:

        normalized_chapters = {
            _normalise_name(
                chapter
            )
            for chapter in chapters
            if _clean_text(chapter)
        }

        if normalized_chapters:

            chapter_mask = result[
                "chapter"
            ].map(
                _normalise_name
            ).isin(
                normalized_chapters
            )

            result = result[
                chapter_mask
            ]

    # --------------------------------------------------------
    # Keyword filtering
    # --------------------------------------------------------

    clean_keywords = []

    for keyword in (
        keywords or []
    ):

        keyword = _clean_text(
            keyword
        )

        if keyword:

            clean_keywords.append(
                keyword.lower()
            )

    if clean_keywords:

        # Search across item number, chapter,
        # description and unit.

        searchable = (
            result["item_no"].astype(str)
            + " "
            + result["chapter"].astype(str)
            + " "
            + result["description"].astype(str)
            + " "
            + result["unit"].astype(str)
        ).str.lower()

        # Every keyword must occur somewhere
        # in the searchable item text.

        mask = pd.Series(
            True,
            index=result.index
        )

        for keyword in clean_keywords:

            mask &= searchable.str.contains(
                re.escape(keyword),
                na=False
            )

        result = result[
            mask
        ]

    # --------------------------------------------------------
    # Reset index
    # --------------------------------------------------------

    result = result.reset_index(
        drop=True
    )

    return result


# ============================================================
# AI-FRIENDLY SSR SEARCH
# ============================================================

def search_keywords(
    df,
    keywords,
    chapters=None
):
    """
    Convenience wrapper for AI-generated SSR keywords.

    Example:

        search_keywords(
            df,
            [
                "concrete pavement",
                "cement concrete",
                "PCC"
            ],
            ["Rigid Pavement"]
        )
    """

    return search(
        df=df,
        chapters=chapters,
        keywords=keywords
    )


# ============================================================
# GET SSR ITEM BY ID
# ============================================================

def get_item(
    df,
    item_id
):
    """
    Safely retrieve one SSR item by internal ID.
    """

    if df is None or df.empty:

        return None

    try:

        item_id = int(
            item_id
        )

    except (
        TypeError,
        ValueError
    ):

        return None

    matches = df[
        df["id"] == item_id
    ]

    if matches.empty:

        return None

    return matches.iloc[0]


# ============================================================
# GET ITEMS BY CHAPTER
# ============================================================

def get_chapter_items(
    df,
    chapter
):
    """
    Return all SSR items belonging to a chapter.
    """

    if df is None or df.empty:

        return pd.DataFrame()

    target = _normalise_name(
        chapter
    )

    mask = (
        df["chapter"]
        .map(_normalise_name)
        == target
    )

    return df[
        mask
    ].reset_index(
        drop=True
    )


# ============================================================
# MODULE TEST
# ============================================================

if __name__ == "__main__":

    default_file = (
        "SSR_2022-23 (2).xlsx"
    )

    if os.path.exists(
        default_file
    ):

        try:

            dataframe = load_ssr(
                default_file
            )

            print(
                "SSR loaded successfully."
            )

            print(
                f"Total usable items: "
                f"{len(dataframe)}"
            )

            print(
                "\nColumns:"
            )

            print(
                list(
                    dataframe.columns
                )
            )

            print(
                "\nFirst 5 items:"
            )

            print(
                dataframe.head()
            )

            print(
                "\nChapters:"
            )

            print(
                dataframe[
                    "chapter"
                ].nunique()
            )

        except Exception as error:

            print(
                "SSR loading failed:"
            )

            print(
                error
            )

    else:

        print(
            "Test file not found:"
        )

        print(
            default_file
        )
