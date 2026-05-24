# Arabic Translation & Multilingual Data Engineering

> **Why this file exists:** This project ingests data that contains Arabic text — specifically family relationship strings, student names, and potentially study fields. Getting Arabic data wrong causes silent failures: records are skipped, relationships are misclassified, and duplicate detection breaks entirely because "محمد" and "Mohamed" don't match. This document institutionalises every hard-won lesson about handling Arabic in this codebase.

---

## 1. Where Arabic Data Appears in This Project

| Location | Field | Arabic content | Risk if wrong |
|----------|-------|----------------|---------------|
| `scripts/bulk_import.py` | `relation` column in family sheet | Relationship strings ("زوجة", "ابن", etc.) | Family member skipped or misclassified |
| `students.full_name` | Student names | Arabic transliterations | Duplicate detection misses matches |
| `accompaniments.full_name` | Family names | Arabic names | Same |
| `student_enrichment.specialization` | Study field | Arabic or mixed Arabic/English | Field analysis charts show noise |
| Excel source file | Any cell | Encoding corruption from Excel | Data loss at parse time |

---

## 2. Relationship String Mapping (the RELATIONSHIP_MAP)

This is the most battle-tested Arabic-handling code in the project. Located in `scripts/bulk_import.py`:

```python
RELATIONSHIP_MAP = {
    # English variants
    "spouse": "Spouse", "wife": "Spouse", "husband": "Spouse",
    "son": "Son",
    "daughter": "Daughter",
    "sibling": "Sibling", "brother": "Sibling", "sister": "Sibling",
    "father": "Spouse", "mother": "Spouse",   # ← deliberate: parents mapped to Spouse
                                                #   because the DB CHECK constraint only
                                                #   allows (Spouse/Son/Daughter/Sibling)

    # Arabic variants (these are the ones that actually appeared in source data)
    "رب العائلة": "Spouse",    # "head of household" → treated as spouse
    "زوجة": "Spouse",          # wife
    "زوج": "Spouse",           # husband
    "ابن": "Son",
    "ابنة": "Daughter",
    "أخ": "Sibling",           # brother
    "أخت": "Sibling",          # sister

    # Skip patterns (the student themselves appear in family sheet)
    "student": None,
    "موفد": None,              # "delegate/sponsored student" in Arabic
}
```

**Fallback behaviour:** Any value NOT in the map is mapped to `"Sibling"`. This is a lossy default. If the source data introduces new Arabic relationship terms, they silently become "Sibling". The fix is to add the term to the map — do not change the fallback without checking what unknown values exist first.

**How to discover unknown relationship strings in a new file:**
```python
import pandas as pd
df = pd.read_excel("new_file.xlsx", sheet_name="family data")
print(df["relation"].value_counts(dropna=False))
# Any string not in RELATIONSHIP_MAP will become "Sibling"
```

---

## 3. Arabic Name Handling

### 3a. Why Duplicate Detection Partially Fails on Arabic Names

The soft-duplicate check in `duplicates.py` uses:
```sql
lower(trim(a.full_name)) = lower(trim(b.full_name))
```

This works for ASCII names. It **fails silently** for Arabic names in two ways:

**Problem 1: Transliteration variation**
The same Arabic name has multiple valid English transliterations:
| Arabic | Transliteration A | Transliteration B | Match? |
|--------|-------------------|-------------------|--------|
| محمد | Mohamed | Muhammad | ✗ missed |
| عبدالله | Abdullah | Abd Allah | ✗ missed |
| إدريس | Idris | Edriss | ✗ missed |
| فاطمة | Fatima | Fatema | ✗ missed |

**Problem 2: Arabic Unicode normalisation**
Arabic text has two encodings for many characters:
- Alef with hamza above: `أ` (U+0623) vs plain Alef: `ا` (U+0627)
- Alef with hamza below: `إ` (U+0625) vs plain Alef: `ا`
- Teh marbuta: `ة` (U+0629) vs plain teh: `ت` (U+062A)
- Yeh: `ي` (U+064A) vs alef maqsura: `ى` (U+0649)

Records for the same person can exist in both forms and NOT trigger a duplicate flag.

### 3b. Arabic Normalisation Function (to be implemented)

When adding fuzzy name matching, use this normalisation first:

```python
import unicodedata
import re

def normalise_arabic(name: str) -> str:
    """
    Normalise Arabic text for comparison purposes.
    - Remove diacritics (tashkeel/harakat)
    - Normalise alef variants to plain alef
    - Normalise teh marbuta to teh
    - Normalise yeh variants
    - Strip extra whitespace
    - Lowercase (handles any Latin characters in the name)
    """
    if not name:
        return ""

    # Remove Arabic diacritics (harakat): range U+0610–U+061A, U+064B–U+065F
    name = re.sub(r'[ؐ-ًؚ-ٟ]', '', name)

    # Normalise alef variants → plain alef (ا)
    name = re.sub(r'[أإآٱ]', 'ا', name)

    # Normalise teh marbuta → teh
    name = name.replace('ة', 'ت')

    # Normalise alef maqsura → yeh
    name = name.replace('ى', 'ي')

    # Unicode NFKD normalisation (handles composed characters)
    name = unicodedata.normalize('NFKD', name)

    return name.strip().lower()
```

Apply in duplicate detection:
```python
normalise_arabic(a.full_name) = normalise_arabic(b.full_name)
```

**Note:** This normalisation is lossy — names that differ only in diacritics will match. For this programme (administrative records, not a legal system), that is the correct tradeoff. Names that differ in diacritics are almost always the same person.

### 3c. Transliteration Matching (future work)

For catching "Mohamed" vs "Muhammad", options in order of engineering cost:

1. **Manual alias table** — maintain a `name_aliases.json` that maps common variants. Low cost, high accuracy for this specific programme's name set. Start here.
2. **Soundex/Metaphone** — works for English. Does not work for Arabic transliteration.
3. **Camel-tools / CAMeL** — Arabic NLP library that handles transliteration. High quality but requires installation and significant engineering.
4. **Edit distance (Levenshtein)** — catches typos but also flags unrelated short names as matches (false positives). Use with a threshold of ≤2 edits only for names longer than 6 characters.

**Recommended approach for this project:** Build a manual alias table first. The programme covers a specific cohort; most name variants are predictable.

---

## 4. Excel Arabic Encoding Issues

### 4a. What goes wrong

Excel files with Arabic content can produce several failure modes when read with pandas:

| Failure | Cause | Symptom |
|---------|-------|---------|
| Garbled text | Excel saved with ANSI encoding, read as UTF-8 | `Ø²ÙˆØ¬Ø©` instead of `زوجة` |
| Missing text | Excel formula cells not evaluated | Empty string where formula result expected |
| Wrong date | Excel serial number not converted | `44927` instead of `2023-01-01` |
| Mixed encoding | Different sheets saved at different times with different encodings | Some sheets fine, others garbled |

### 4b. Safe reading pattern

```python
# Always read with openpyxl engine (not xlrd — xlrd dropped xlsx support)
df = pd.read_excel(path, sheet_name="family data", engine="openpyxl")

# For CSVs from Arabic-locale systems, try these encodings in order:
for enc in ["utf-8", "utf-8-sig", "cp1256", "iso-8859-6"]:
    try:
        df = pd.read_csv(path, encoding=enc)
        break
    except (UnicodeDecodeError, pd.errors.ParserError):
        continue
```

**`cp1256`** is Windows Arabic codepage — the most common encoding for Excel files produced on Arabic-locale Windows machines. If you receive a CSV from a Libyan government system, try `cp1256` first.

**`utf-8-sig`** handles UTF-8 files with a BOM (Byte Order Mark) that Microsoft Excel adds when saving as UTF-8. The BOM shows up as `ï»¿` at the start if read as plain `utf-8`.

### 4c. Detecting encoding before reading

```python
import chardet

with open(path, "rb") as f:
    raw = f.read(50000)  # Read first 50KB
    result = chardet.detect(raw)
    print(result)  # {'encoding': 'Windows-1256', 'confidence': 0.87}
```

Install: `pip install chardet`

---

## 5. RTL Rendering in Streamlit

Streamlit does not natively support RTL text direction. Arabic names display left-to-right in `st.dataframe()`, which is visually wrong but functionally acceptable for an administrative tool.

**Current state:** No RTL CSS has been applied. Arabic names in the dataframe display LTR. This is a known cosmetic issue.

**If RTL is needed:**
```python
# Inject custom CSS into the Streamlit app
st.markdown("""
<style>
    .stDataFrame td {
        direction: rtl;
        text-align: right;
    }
</style>
""", unsafe_allow_html=True)
```

**Warning:** This will right-align ALL dataframe cells, including numeric columns. You would need to be more selective with CSS selectors to apply RTL only to name columns.

---

## 6. Arabic in PDF Reports (ReportLab)

ReportLab does not support Arabic text rendering natively. Arabic characters display as isolated letters (not connected) and in LTR order (reversed). This affects `report.py` if Arabic names appear in the "Students Ending Within 6 Months" table.

**Current state:** The report assumes data is in Latin characters (English names, English country names from `study_country` column which is standardised). Names from `full_name` do appear in the report table — these may be Arabic and will render incorrectly.

**Fix options:**

Option A — Use `arabic-reshaper` + `python-bidi`:
```python
import arabic_reshaper
from bidi.algorithm import get_display

def render_arabic(text: str) -> str:
    """Reshape and apply bidi algorithm for correct ReportLab rendering."""
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)

# Use when building table cells:
soon_rows.append([render_arabic(r.get("full_name", "")), ...])
```
Install: `pip install arabic-reshaper python-bidi`

Option B — Use an Arabic-compatible font (e.g. Amiri, Noto Naskh Arabic):
```python
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
pdfmetrics.registerFont(TTFont("Amiri", "Amiri-Regular.ttf"))
# Then use fontName="Amiri" in ParagraphStyle
```

Option B alone is not sufficient — font must be combined with reshaping (Option A) for correct ligature rendering.

**Recommendation:** For the current programme scope (executive-level PDF read by Arabic speakers on screen), Option A is sufficient. Implement when a user reports garbled names in the PDF.

---

## 7. National ID (NID) as a Join Key

The 12-digit Libyan NID is used as the primary join key between `students` and `student_enrichment`. NID data quality issues that affect joins:

| Issue | Example | Effect |
|-------|---------|--------|
| Float suffix from Excel | `119670291604.0` | NID becomes 16 chars; join fails |
| Short NID from Excel | `4567890123` (10 digits) | Needs zero-padding to `004567890123` |
| Leading zeros stripped by Excel | `019670291604` → `19670291604` | Needs zero-padding |
| NID as integer column | `119670291604` read as `float64` | `.0` appended; `clean_nid()` strips it |

The `clean_nid()` function in `bulk_import.py` handles all of these:
```python
def clean_nid(val) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    if s.endswith(".0"):
        s = s[:-2]                         # strip Excel float suffix
    return s.zfill(12) if s.isdigit() and len(s) < 12 else s
    # zfill(12): zero-pad short numeric NIDs
```

**Always use `clean_nid()` before any NID comparison or insert.** Never compare raw Excel NID values.

---

## 8. Arabic in Duplicate Detection — Practical Checklist

Before running a duplicate scan on new data:

- [ ] Run `normalise_arabic()` on `full_name` before comparison
- [ ] Check `clean_nid()` was applied to all NID fields
- [ ] Inspect relationship map for any new unknown strings
- [ ] Check for BOM or encoding issues in the source file
- [ ] Verify `student id` column wasn't read as float (producing `.0` suffix)
- [ ] Confirm country names are standardised (the `Study_Country_Standardized` column in the enrichment sheet exists for this reason)

---

## 9. Known Arabic Data in Production (as of 2026-05-24)

- **Family relationship strings:** Both Arabic and English were present in the source Excel. All resolved via RELATIONSHIP_MAP.
- **Student names:** Mixed — some records have Arabic full names, most have Latin transliterations.
- **Study fields:** The `specialization` column in `student_enrichment` is predominantly English (the source used English academic field names). Occasional Arabic entries exist.
- **Country names:** Standardised in the `Study_Country_Standardized` Excel column before import. The raw country column had variants like "UK", "United Kingdom", "Britain" — standardisation was done externally before this import.

**The most common unhandled Arabic data risk going forward:** New data entry via the web form. The Data Entry page has no restrictions on character set in any text field. A data-entry user typing Arabic in `full_name` or `study_field` will produce Arabic text in the database that the duplicate detector won't match against Latin-transliterated equivalents of the same person.
