# EduPulse Analytics — System Requirements Specification (SRS)

**Document Version:** 1.0.0  
**Status:** Architecture & Requirements Phase (Approved for Review)  
**Application Name:** EduPulse Analytics  
**Full Project Title:** Cloud-Based Student Performance Analytics Using Big Data Technologies  

---

## 1. Executive Summary & Purpose

EduPulse Analytics is a scalable academic analytics platform engineered to empower colleges and universities to process, analyze, and visualize student academic performance across both marks-based and grade-based evaluation systems. 

Academic institutions face immense heterogeneity in evaluation frameworks:
1. **Autonomous / Continuous Internal Assessment (Marks-based):** Internal assessments, laboratory exams, external theory papers, and dynamic passing cutoff thresholds per subject.
2. **Affiliated University Result Sheets (Grade-based):** Letter grades (e.g., `O, A+, A, B+, B, C, F`), semester grade point averages (SGPA), absent status codes (`Ab`), and withheld results.

EduPulse Analytics bridges this gap with high-performance Big Data processing powered by **Apache PySpark**, a modern **Flask** web application, responsive **Plotly.js** analytical visualizations, auditable data validation pipelines, and an optional, strictly opt-in **Amazon Web Services (AWS) S3** cloud archive.

---

## 2. System Scope & Guiding Principles

### 2.1 Scope Boundaries
- **In-Scope:**
  - Ingestion and schema mapping of CSV, XLSX, and XLS academic records.
  - Distinct data modeling for marks-based records and grade-based records.
  - Interactive class-wise spreadsheet-style entry for marks.
  - Synthetic data generation capable of producing $\ge 1,000,000$ records with configurable distributions, missing values, duplicates, and edge cases.
  - PySpark distributed processing pipeline for validation, deduplication, aggregation, and Parquet persistence.
  - Asynchronous background job monitoring to keep web requests non-blocking.
  - Rule-based, transparent student academic support indicators.
  - Local-first file architecture with structured manifests.
  - Optional, user-confirmed, zero-secret AWS S3 synchronization.
- **Out-of-Scope (Phase 1):**
  - Live relational database engines (PostgreSQL, MySQL) — system uses an auditable, file-first Parquet/JSON architecture.
  - Synchronous million-record web request processing.
  - Automated cloud provisioning (no automated IAM/S3 creation without explicit authorization).
  - Unverified automated conversion of letter grades into raw numeric marks.

### 2.2 Core Architectural Principles
1. **Integrity of Academic Semantics:** Letter grades, SGPA, numeric marks, absent markers (`Ab`), and withheld results must never be conflated, fabricated, or converted without an explicit institution-approved mapping matrix.
2. **Separation of Raw and Processed State:** Raw uploaded datasets are strictly immutable. Normalized, validated, and aggregated datasets are saved separately with complete cryptographic audit manifests.
3. **Decoupled Heavy Computation:** The Flask web interface must remain snappy and responsive. All Spark transformations are queued into an asynchronous background processing service.
4. **Privacy and Local-First Default:** Real student academic data stays strictly local. Cloud synchronization requires explicit user action, clear cost warnings, and least-privilege access.

---

## 3. Technology Stack & Specifications

| Tier | Technology | Justification & Role |
| :--- | :--- | :--- |
| **Backend Core** | Python 3.10+ / Flask | Lightweight, robust web microframework, modular Blueprint routing, Jinja2 templating. |
| **Big Data Engine** | Apache Spark 3.4+ / PySpark | Distributed DataFrame operations for million-record schema normalization, validation, deduplication, and aggregation. |
| **Spreadsheet Ingestion** | pandas, openpyxl, xlrd | Lightweight parsing, sheet detection, and sample inspection (first 50-100 rows) for preview and column mapping. |
| **Storage Formats** | Apache Parquet & JSON / CSV | Columnar, compressed, high-throughput analytical format (Parquet); interoperable tabular export (CSV); metadata manifests (JSON). |
| **Frontend Framework** | Bootstrap 5.3 + Custom CSS | Mobile-first responsive layout, accessible typography, modal dialogs, and robust form styling. |
| **Icons & Visuals** | Lucide Icons | Clean, modern, accessible SVG iconography. |
| **Interactive Charts** | Plotly.js | Client-side reactive charts (histograms, box plots, scatter distributions, multi-bar comparisons). |
| **Job Management** | Python Process/Thread Pool + JSON Heartbeats | Non-blocking execution of PySpark batch tasks decoupled from HTTP request-response cycles. |
| **Cloud Storage** | AWS SDK (boto3) | *Optional, disabled by default.* S3 integration with private buckets and IAM least-privilege policies. |
| **Testing Suite** | pytest, pytest-cov, moto | Comprehensive unit, integration, mock-cloud, and performance benchmarking. |

---

## 4. Functional Requirements

### FR-1: Dual Academic Data Model Ingestion
- **FR-1.1 (Marks-Based Records):**
  - Ingest student identifiers, department, batch/year, section, semester, subject code, subject name, internal marks, maximum internal marks, external marks, maximum external marks, and total marks.
  - Dynamically configure passing rules per subject (e.g., minimum internal threshold, minimum external threshold, aggregate threshold).
  - Preserve explicit non-numeric statuses: `ABSENT`, `WITHHELD`, `INCOMPLETE`, `MALPRACTICE`.
- **FR-1.2 (Grade-Based Records):**
  - Ingest university result sheets with student identifiers, subject codes, subject names, letter grades (`O, A+, A, B+, B, C, F`), semester grade point average (`SGPA`), department, and examination period.
  - Distinguish between passed grades, failed grades (`F`), absent markers (`Ab`), withheld/moderated results, and unrecorded/blank cells.
  - Treat SGPA as a provided institution metric unless official credit calculation rules and course credits are explicitly configured.
  - Enforce strict guardrails prohibiting arbitrary numeric averaging of letter grades.

### FR-2: Guided 11-Step Spreadsheet Import Workflow
- **FR-2.1:** Upload CSV, XLSX, or XLS files through an accessible drag-and-drop file interface with client/server MIME and extension verification.
- **FR-2.2:** Automatically inspect the workbook structure, detect multiple sheets, and heuristically detect header rows.
- **FR-2.3:** Suggest format classification (Marks-Based vs. Grade-Based) based on column signature heuristics with manual override.
- **FR-2.4:** Provide an interactive visual column mapper matching incoming spreadsheet columns to canonical system fields.
- **FR-2.5:** Generate a paginated data preview (first 10–50 rows) showing mapped records before persistence.
- **FR-2.6:** Execute pre-flight data validation: range checks, mandatory field checks, duplicate detection against record keys (`StudentID + SubjectCode + Semester`).
- **FR-2.7:** Display a validation tally dashboard showing accepted, rejected, duplicate, and incomplete row counts.
- **FR-2.8:** Require explicit user confirmation before committing the import.
- **FR-2.9:** Persist original uploaded file to `data/raw/` without modification.
- **FR-2.10:** Persist normalized, validated dataset to `data/validated/`.
- **FR-2.11:** Generate an immutable cryptographic Import Manifest (`manifest.json`) recording UUID, timestamp, SHA-256 hash, mappings, validation statistics, and user comments.

### FR-3: Class Marks Entry Interface
- **FR-3.1:** Render an editable, spreadsheet-like interactive web table allowing teachers/coordinators to enter marks for an entire class.
- **FR-3.2:** Support dynamic addition and removal of student rows and subject columns.
- **FR-3.3:** Enable per-subject configuration of maximum marks and passing criteria directly within the entry view.
- **FR-3.4:** Real-time client-side validation highlighting cells with out-of-bounds values, negative numbers, or invalid characters.
- **FR-3.5:** Support saving an in-progress draft to local storage (`data/drafts/`) without triggering validation errors.
- **FR-3.6:** One-click bidirectional export to CSV and import from an existing CSV template.
- **FR-3.7:** Comprehensive review summary modal presenting pass/fail distributions before final dataset commit.

### FR-4: Synthetic Big Data Generation Engine
- **FR-4.1:** Capable of generating benchmark datasets of scalable size: **10,000**, **100,000**, **500,000**, and **1,000,000+** records.
- **FR-4.2:** Support parameterization: student count, subject count, semester range, department list, assessment scheme, and data model (marks vs. grades).
- **FR-4.3:** Enforce strict generation of fictional student identifiers (`STU-YYYY-XXXXX`), eliminating any possibility of real student identity leakage.
- **FR-4.4:** Support reproducible generation via deterministic random seeds (`--seed 42`).
- **FR-4.5:** Inject configurable data quality anomalies for validation stress testing: duplicate records (1-5%), missing values (2-8%), out-of-range marks (0.5%), malformed grade strings.
- **FR-4.6:** Stream-oriented, chunked/partitioned disk writing to prevent JVM or Python Out-Of-Memory (OOM) errors during generation.
- **FR-4.7:** Explicitly tag all generated data with `is_synthetic: true` metadata.

### FR-5: PySpark Big Data Processing Pipeline
- **FR-5.1:** Multi-stage distributed batch processing pipeline utilizing native PySpark DataFrame transformations.
- **FR-5.2:** Pipeline execution steps:
  1. *Discovery & Metadata Inspection:* Verify source file integrity and manifest.
  2. *Schema Enforcement:* Coerce fields into canonical Spark SQL schema (`StructType`).
  3. *Data Quality Filtering:* Detect null keys, format violations, and illegal characters.
  4. *Deduplication:* Apply windowed deduplication over natural composite keys (`student_id`, `subject_code`, `semester`, `academic_year`).
  5. *Status Normalization:* Classify marks and grades into standardized status categories (`PASS`, `FAIL`, `ABSENT`, `WITHHELD`).
  6. *Derived Field Calculation:* Compute totals, percentage scores, and grade points where approved.
  7. *Analytical Aggregations:* Pre-calculate subject-wise, class-wise, and semester-wise aggregates.
  8. *Parquet Persistence:* Write snappy-compressed partitioned Parquet files (`data/processed/{dataset_id}/`).
  9. *Job Execution Telemetry:* Record start time, end time, elapsed seconds, row counts read/accepted/rejected, memory usage, and execution log.
- **FR-5.3:** Decoupled execution via a non-blocking background job runner with live polling endpoints (`/api/jobs/{job_id}/status`).

### FR-6: Analytics & Decision Support
- **FR-6.1 (Marks-Based Analytics):**
  - Class mean, median, standard deviation, and interquartile range.
  - Subject-wise average comparisons and difficulty index ranking.
  - Pass/Fail ratios, distinction rates, and distribution histograms.
  - Semester-over-semester progression trends.
- **FR-6.2 (Grade-Based Analytics):**
  - Letter grade distribution per subject and across departments.
  - SGPA distribution curves, median SGPA, and honor rolls.
  - Failure rate hot-spots and absentee concentration analysis.
- **FR-6.3 (Student Support Indicators):**
  - Rule-based detection of academic distress:
    - *Threshold Alert:* Scoring below 40% in $\ge 2$ core subjects.
    - *Progression Alert:* Negative deviation $\ge 15\%$ across successive semesters.
    - *Attendance/Absentee Alert:* Missing examination or repeated absent markers (`Ab`).
  - Strict requirement: Present all indicators as rule-based transparent criteria with clear explanations; explicitly avoid clinical or diagnostic claims.

### FR-7: Dashboard Navigation & Pages
The application must implement nine core routes:
1. `/` — Responsive landing page with product overview and call-to-action.
2. `/dashboard` — High-level institutional metrics, summary cards, and quick insights.
3. `/data-management` — Dataset library, import wizard launcher, and manifest viewer.
4. `/class-entry` — Interactive spreadsheet table for direct marks input.
5. `/student-performance` — Individual student longitudinal academic trajectory.
6. `/academic-analysis` — Cross-sectional department, semester, and subject deep-dives.
7. `/processing-monitor` — Spark batch job queue, real-time progress bars, and execution logs.
8. `/reports` — Exportable analytical reports (CSV summaries, printable executive briefing).
9. `/settings` — Assessment criteria configuration, data retention rules, and cloud settings.

### FR-8: File-First Local Storage Engine
- **FR-8.1:** Fully operational without requiring an external database.
- **FR-8.2:** Structured directory tree separating `raw`, `validated`, `processed`, `analytics`, `reports`, `manifests`, `drafts`, and `synthetic`.
- **FR-8.3:** Atomic file write operations (write-to-temp then atomic rename) to eliminate file corruption.
- **FR-8.4:** Cryptographic manifest tracking with UUIDs and SHA-256 integrity checksums.

### FR-9: Optional AWS S3 Integration
- **FR-9.1:** Feature-flagged and disabled by default (`AWS_ENABLED=false`).
- **FR-9.2:** Zero cloud resource provisioning without explicit manual approval.
- **FR-9.3:** Secure credential ingestion via environment variables or IAM instance profiles (never committed in source control).
- **FR-9.4:** Pre-upload confirmation dialog indicating exact payload size, destination bucket, and cost disclaimers.
- **FR-9.5:** Comprehensive mocking layer using `moto` for local testing.

---

## 5. Non-Functional Requirements

### 5.1 Performance & Scalability
- **NFR-1.1 (Scale Target):** Support reliable generation and PySpark processing of at least $1,000,000$ academic records on standard commodity hardware (8 cores, 16 GB RAM).
- **NFR-1.2 (Web Responsiveness):** Dashboard and analytical query response times must remain under $500\text{ ms}$ by querying pre-aggregated metadata rather than scanning raw datasets on every request.
- **NFR-1.3 (Non-Blocking Jobs):** The Flask HTTP worker must never block on PySpark execution. All batch jobs run asynchronously.

### 5.2 Privacy & Security
- **NFR-2.1 (Data Minimization):** Real student names are stripped from analytical datasets. Real student IDs are pseudonymized or masked (`STU***789`) in logs and manifests.
- **NFR-2.2 (Local-First Default):** No academic record is ever transmitted to an external service or cloud provider without explicit user-initiated confirmation.
- **NFR-2.3 (File Injection Defenses):** Enforce strict file size limits (50 MB web upload limit), sanitize filenames, prevent directory traversal (`..` sanitization), and neutralize spreadsheet formula injections (`=`, `@`, `+`, `-`).

### 5.3 Reliability, Auditability & Maintainability
- **NFR-3.1 (Immutability):** Source upload files are write-protected and stored permanently in their raw format for provenance tracking.
- **NFR-3.2 (Audit Manifests):** Every data transformation, cleaning step, and validation outcome is logged in a machine-readable JSON manifest.
- **NFR-3.3 (Code Quality):** 100% type annotations on core service classes, comprehensive docstrings, and a modular architecture allowing easy transition to database backends in future releases.

### 5.4 Usability & Accessibility
- **NFR-4.1 (Accessibility):** Adhere to WCAG 2.1 AA standards for color contrast, semantic HTML, and keyboard navigability.
- **NFR-4.2 (Zero-Data States):** Every dashboard view must render informative, polished empty-state illustrations and actionable onboarding guidance when no datasets are loaded.
