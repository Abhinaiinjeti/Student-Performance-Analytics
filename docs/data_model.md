# EduPulse Analytics — Academic Data Models & Schema Specification

**Document Version:** 1.0.0  
**Status:** Architecture & Requirements Phase (Approved for Review)  
**System Name:** EduPulse Analytics  

---

## 1. Foundational Data Modeling Principles

EduPulse Analytics strictly isolates and models **two fundamentally distinct academic evaluation paradigms**:
1. **Marks-Based Evaluation:** Continuous assessment comprising numeric internal scores, external examination marks, configurable maximum thresholds, and composite passing rules.
2. **Grade-Based Evaluation:** Letter-graded result sheets (e.g., affiliated university examinations) featuring discrete letter grades, distinct absent codes (`Ab`), withheld records, blank/unrecorded cells, and official Semester Grade Point Averages (SGPA).

### 1.1 Strict Guardrails on Data Integrity
> [!CRITICAL]
> **No Unjustified Grade-to-Marks Conversion:** The platform strictly prohibits converting letter grades (e.g., `A+`, `B`) into arbitrary numeric marks or calculating arithmetic averages across letter grades unless an institution-approved, credit-weighted numeric conversion formula is explicitly configured.
>
> **Preservation of Non-Numeric Semantics:** An absent student (`Ab`), a withheld result (`W`), an incomplete evaluation (`I`), and a blank unrecorded cell (`NULL`) represent entirely distinct academic states and must **never** be coerced into a zero ($0.0$) score or an automatic failure.

---

## 2. Model A: Marks-Based Academic Schema

Marks-based records capture granular score components across multiple assessment periods (internal tests, lab assessments, semester-end examinations).

### 2.1 Entity Relationship & Attribute Specification

| Attribute Name | Data Type | Nullable? | Constraints & Format | Description |
| :--- | :--- | :--- | :--- | :--- |
| `student_id` | String | No | Regex: `^[A-Za-z0-9_-]{3,32}$` | Masked/pseudonymized student roll number or registration ID. |
| `department` | String | No | e.g., `CSE`, `ECE`, `MECH`, `MBA` | Academic department offering the course. |
| `batch` | String | No | e.g., `2022-2026`, `2023-2025` | Student enrollment cohort. |
| `section` | String | Yes | e.g., `A`, `B`, `Alpha` | Classroom section or cohort division. |
| `semester` | Integer | No | $1 \le \text{semester} \le 12$ | Academic semester index. |
| `academic_year` | String | No | e.g., `2024-2025` | Academic year of assessment. |
| `assessment_period` | String | No | e.g., `Midterm-1`, `Final-Exam` | Specific evaluation phase. |
| `subject_code` | String | No | Regex: `^[A-Za-z0-9]{3,12}$` | Standard institutional course identifier (e.g., `CS301`). |
| `subject_name` | String | No | Max length 128 | Descriptive name of the course. |
| `internal_marks` | Float | Yes | $0 \le m \le \text{max\_internal}$ | Scored internal assessment marks. |
| `max_internal` | Float | No | Default: $30.0$ or $40.0$ ($> 0$) | Configured maximum internal marks. |
| `external_marks` | Float | Yes | $0 \le m \le \text{max\_external}$ | Scored external/theory marks. |
| `max_external` | Float | No | Default: $70.0$ or $60.0$ ($> 0$) | Configured maximum external marks. |
| `total_marks` | Float | Yes | Internal + External (if valid) | Derived total score. |
| `max_total` | Float | No | $\text{max\_internal} + \text{max\_external}$ | Total maximum score possible. |
| `percentage` | Float | Yes | $(\text{total} / \text{max\_total}) \times 100$ | Derived percentage score. |
| `status` | String | No | Enum: `PASS, FAIL, ABSENT, WITHHELD, INCOMPLETE` | Categorical outcome based on configured rules. |
| `attendance_pct` | Float | Yes | $0.0 \le p \le 100.0$ | Optional student attendance percentage. |

### 2.2 Marks Passing Rule Logic
Passing criteria are highly variable across universities and autonomous institutions. EduPulse allows per-subject or per-program rule configuration:

$$\text{is\_passed} = (\text{internal} \ge \text{pass\_internal}) \land (\text{external} \ge \text{pass\_external}) \land (\text{total} \ge \text{pass\_total})$$

*Default Benchmark Rule:*
- Minimum Internal: $40\%$ of `max_internal` (e.g., $16 / 40$)
- Minimum External: $40\%$ of `max_external` (e.g., $24 / 60$)
- Minimum Aggregate: $40\%$ of `max_total` (e.g., $40 / 100$)

---

## 3. Model B: Grade-Based Academic Schema

Grade-based records mirror university result sheets (e.g., state technical universities, affiliated colleges) where students receive letter grades reflecting band classifications.

### 3.1 Entity Relationship & Attribute Specification

| Attribute Name | Data Type | Nullable? | Constraints & Format | Description |
| :--- | :--- | :--- | :--- | :--- |
| `student_id` | String | No | Regex: `^[A-Za-z0-9_-]{3,32}$` | Masked student roll number or registration ID. |
| `department` | String | Yes | e.g., `ECE`, `CIVIL` | Academic program or department. |
| `semester` | Integer | No | $1 \le \text{semester} \le 12$ | Academic semester index. |
| `academic_year` | String | Yes | e.g., `2024-2025` | Academic year. |
| `exam_type` | String | No | Enum: `REGULAR, SUPPLEMENTARY, REVALUATION` | Examination sitting classification. |
| `subject_code` | String | No | Regex: `^[A-Za-z0-9]{3,12}$` | Course catalog code (e.g., `MA201`). |
| `subject_name` | String | Yes | Max length 128 | Name of subject (if provided in header). |
| `course_credits` | Float | Yes | e.g., $3.0, 4.0$ ($> 0$) | Academic credit weighting (if provided). |
| `letter_grade` | String | Yes | e.g., `O`, `A+`, `A`, `B+`, `B`, `C`, `P`, `F` | Exact letter grade recorded. |
| `grade_status` | String | No | Enum: `PASSED, FAILED, ABSENT, WITHHELD, MISSING` | Canonical normalized result category. |
| `grade_point` | Float | Yes | e.g., $10, 9, 8, 7, 6, 5, 0$ | Numerical grade point (if official rule applied). |
| `sgpa` | Float | Yes | $0.0 \le \text{sgpa} \le 10.0$ | Semester Grade Point Average (provided metric). |
| `cgpa` | Float | Yes | $0.0 \le \text{cgpa} \le 10.0$ | Cumulative Grade Point Average (if available). |

### 3.2 Canonical Grade Status Classification

| Raw Source Value | Canonical Status | Definition & System Handling |
| :--- | :--- | :--- |
| `O, A+, A, B+, B, C, P` | `PASSED` | Student met learning objectives and earned course credits. |
| `F, U, FAIL` | `FAILED` | Student failed assessment; requires re-examination. Course credits earned = 0. |
| `Ab, AB, ABS, ABSENT` | `ABSENT` | Student was officially registered but absent from examination. |
| `W, WH, WITHHELD` | `WITHHELD` | Results withheld due to fee dues, malpractice inquiry, or document verification. |
| *(empty string)*, `NULL, -` | `MISSING` | Cell blank or unrecorded. Never assumed as failure; flagged for administrative audit. |

### 3.3 SGPA Governance & Calculation
- **Default Handling:** If `sgpa` is present as a column in the imported university sheet, it is preserved as an **authoritative institution-supplied metric**.
- **Credit-Weighted Calculation (Only when enabled):**
  If and only if official course credits ($C_i$) and institutional grade points ($G_i$) are verified, SGPA may be computed using the standard weighted formula:

$$\text{SGPA} = \frac{\sum_{i=1}^{n} (C_i \times G_i)}{\sum_{i=1}^{n} C_i}$$

---

## 4. Wide vs. Long Data Normalization Strategy

Spreadsheets uploaded by faculty or universities almost universally arrive in **Wide Format** (one student per row, multiple subjects spanning across horizontal columns):

### Wide Format (Input Representation)
```text
StudentID | StudentName | CS101_Int | CS101_Ext | CS102_Int | CS102_Ext | SGPA
STU001    | Jane Doe    | 35        | 55        | 28        | 48        | 8.5
STU002    | John Smith  | 18        | 22        | 32        | 50        | 6.2
```

### Long / Tidy Format (Internal PySpark Representation)
PySpark operations, aggregations, windowing, and Parquet storage require a normalized **Long Format** (one student-subject-assessment tuple per row):

```text
student_id | subject_code | internal | external | total | status | sgpa
STU001     | CS101        | 35.0     | 55.0     | 90.0  | PASS   | 8.5
STU001     | CS102        | 28.0     | 48.0     | 76.0  | PASS   | 8.5
STU002     | CS101        | 18.0     | 22.0     | 40.0  | FAIL   | 6.2
STU002     | CS102        | 32.0     | 50.0     | 82.0  | PASS   | 6.2
```

*Architectural Benefit:* Long format allows PySpark to perform distributed grouping, aggregations, and filtering across arbitrary combinations of subjects, departments, and semesters without dynamically altering the DataFrame schema.

---

## 5. Formal Schema Specifications

### 5.1 PySpark Parquet Lakehouse Schema (`StructType`)

#### Marks-Based Dataset Schema:
```python
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, DoubleType, BooleanType, TimestampType

MARKS_DATASET_SCHEMA = StructType([
    StructField("record_id", StringType(), False),
    StructField("dataset_id", StringType(), False),
    StructField("student_id", StringType(), False),
    StructField("department", StringType(), False),
    StructField("batch", StringType(), False),
    StructField("section", StringType(), True),
    StructField("semester", IntegerType(), False),
    StructField("academic_year", StringType(), False),
    StructField("assessment_period", StringType(), False),
    StructField("subject_code", StringType(), False),
    StructField("subject_name", StringType(), False),
    StructField("internal_marks", DoubleType(), True),
    StructField("max_internal", DoubleType(), False),
    StructField("external_marks", DoubleType(), True),
    StructField("max_external", DoubleType(), False),
    StructField("total_marks", DoubleType(), True),
    StructField("max_total", DoubleType(), False),
    StructField("percentage", DoubleType(), True),
    StructField("status", StringType(), False),
    StructField("attendance_pct", DoubleType(), True),
    StructField("is_synthetic", BooleanType(), False),
    StructField("created_at", TimestampType(), False)
])
```

#### Grade-Based Dataset Schema:
```python
GRADE_DATASET_SCHEMA = StructType([
    StructField("record_id", StringType(), False),
    StructField("dataset_id", StringType(), False),
    StructField("student_id", StringType(), False),
    StructField("department", StringType(), True),
    StructField("semester", IntegerType(), False),
    StructField("academic_year", StringType(), True),
    StructField("exam_type", StringType(), False),
    StructField("subject_code", StringType(), False),
    StructField("subject_name", StringType(), True),
    StructField("course_credits", DoubleType(), True),
    StructField("letter_grade", StringType(), True),
    StructField("grade_status", StringType(), False),
    StructField("grade_point", DoubleType(), True),
    StructField("sgpa", DoubleType(), True),
    StructField("is_synthetic", BooleanType(), False),
    StructField("created_at", TimestampType(), False)
])
```

### 5.2 JSON Schema: Import Manifest (`manifest.json`)
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "ImportManifest",
  "type": "object",
  "required": [
    "manifest_version",
    "dataset_id",
    "import_timestamp",
    "source_file",
    "model_type",
    "row_counts",
    "column_mappings",
    "validation_summary",
    "storage_locations"
  ],
  "properties": {
    "manifest_version": { "type": "string", "enum": ["1.0.0"] },
    "dataset_id": { "type": "string", "format": "uuid" },
    "import_timestamp": { "type": "string", "format": "date-time" },
    "source_file": {
      "type": "object",
      "required": ["original_filename", "stored_filename", "file_size_bytes", "sha256_checksum"],
      "properties": {
        "original_filename": { "type": "string" },
        "stored_filename": { "type": "string" },
        "file_size_bytes": { "type": "integer" },
        "sha256_checksum": { "type": "string" }
      }
    },
    "model_type": { "type": "string", "enum": ["marks_based", "grade_based"] },
    "row_counts": {
      "type": "object",
      "required": ["total_raw_rows", "accepted_rows", "rejected_rows", "duplicate_rows", "incomplete_rows"],
      "properties": {
        "total_raw_rows": { "type": "integer" },
        "accepted_rows": { "type": "integer" },
        "rejected_rows": { "type": "integer" },
        "duplicate_rows": { "type": "integer" },
        "incomplete_rows": { "type": "integer" }
      }
    },
    "column_mappings": { "type": "object" },
    "validation_summary": {
      "type": "object",
      "properties": {
        "error_count": { "type": "integer" },
        "warning_count": { "type": "integer" },
        "sample_errors": { "type": "array", "items": { "type": "string" } }
      }
    },
    "storage_locations": {
      "type": "object",
      "properties": {
        "raw_path": { "type": "string" },
        "validated_path": { "type": "string" },
        "processed_parquet_dir": { "type": "string" }
      }
    }
  }
}
```

---

## 6. Pre-Aggregated Analytics Schema

To guarantee instantaneous rendering of dashboard cards, charts, and tables without performing on-the-fly Spark scans over a million records, PySpark writes an analytics snapshot (`AGG_{dataset_id}.json`):

```json
{
  "dataset_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "generated_at": "2026-10-21T13:30:00Z",
  "total_records": 1000000,
  "unique_students": 50000,
  "unique_subjects": 20,
  "overall_pass_percentage": 82.45,
  "subject_performance": [
    {
      "subject_code": "CS301",
      "subject_name": "Data Structures",
      "total_students": 50000,
      "passed": 42100,
      "failed": 6900,
      "absent": 800,
      "withheld": 200,
      "average_marks": 68.4,
      "median_marks": 71.0,
      "std_dev": 14.2,
      "min_marks": 12.0,
      "max_marks": 99.0
    }
  ],
  "grade_distributions": {
    "O": 120500,
    "A+": 210400,
    "A": 340200,
    "B+": 180000,
    "B": 95000,
    "C": 32000,
    "F": 21900
  },
  "support_indicators_summary": {
    "at_risk_students_count": 1420,
    "repeated_failures_count": 310,
    "consecutive_decline_count": 890
  }
}
```

---

## 7. Unresolved Academic-Rule Questions & Design Risks

### 7.1 Academic Rule Clarifications Requiring Institution Alignment
1. **Revaluation & Supplementary Attempts:**
   - *Question:* When a student takes a supplementary exam or applies for revaluation, does the new grade overwrite the previous attempt, or are both attempts retained historically?
   - *Current Design Assumption:* Both records are retained historically, distinguished by `exam_type` (`REGULAR` vs `SUPPLEMENTARY`). The latest attempt is prioritized in current standing metrics.
2. **Treatment of Withheld (`W`) Results in Batch Pass Percentages:**
   - *Question:* Should withheld results be included in the denominator when calculating institutional pass rates?
   - *Current Design Assumption:* The denominator includes only students with resolved results (`PASSED + FAILED`). Withheld records are reported as a distinct operational KPI.
3. **Variable Passing Thresholds Across Departments:**
   - *Question:* Do Engineering, Medical, and Humanities departments under the same college enforce differing passing percentages (e.g., $40\%$ vs $50\%$)?
   - *Current Design Assumption:* Assessment rules are modularly configured per `department` and `subject_code` in `config/assessment_rules.py`.

### 7.2 Key Design Risks & Mitigations
- **Risk 1 (Schema Drift in University Result Sheets):** University result spreadsheets often change layout between semesters without warning.  
  *Mitigation:* The 11-step import wizard never assumes a hardcoded sheet index or header position. It employs interactive candidate column mapping with preview validation.
- **Risk 2 (Memory Overhead in Wide-to-Long Melting):** Melting wide Excel sheets with dozens of subjects for tens of thousands of rows can stress Python memory.  
  *Mitigation:* For large files ($> 10\text{ MB}$ or $> 20,000$ rows), conversion from wide to long format is performed directly via PySpark's `stack()` or `selectExpr()` expressions rather than in-memory pandas.
