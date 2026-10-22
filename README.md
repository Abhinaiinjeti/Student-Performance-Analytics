# EduPulse Analytics — Academic Big Data Platform

**Cloud-Based Student Performance Analytics Using Big Data Technologies**

[![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Flask Version](https://img.shields.io/badge/Flask-3.1%2B-lightgrey.svg)](https://flask.palletsprojects.com/)
[![Apache PySpark](https://img.shields.io/badge/PySpark-4.2-orange.svg)](https://spark.apache.org/)
[![Tests](https://img.shields.io/badge/Tests-44%20Passing-brightgreen.svg)]()
[![License](https://img.shields.io/badge/License-Academic%20Open-green.svg)]()

EduPulse Analytics is an enterprise-grade academic intelligence platform engineered for colleges and universities to process, validate, and analyze high-volume student records across both **continuous marks-based evaluations** and **university grade-based result sheets**.

---

## 🚀 Key Architectural Features

- **Dual Academic Data Models:**
  - **Model A (Marks-Based):** Internal assessments, external theory exams, configurable passing thresholds per subject, and interactive class marks entry.
  - **Model B (Grade-Based):** Letter grades (`O, A+, A, B+, B, C, P, F`), institutional SGPA preservation, credit-weighted averages, and distinct non-numeric handling (`Ab` absent, withheld, unrecorded blanks).
  - **Strict Guardrail:** Prohibits arbitrary conversion of letter grades into raw numeric marks without institution-approved rules.
- **Big Data Scale ($1,000,000+$ Records):** Native Apache PySpark 4.2 DataFrame pipelines for distributed schema validation, windowed deduplication, derived aggregations, and Snappy-compressed columnar Parquet persistence.
- **Decoupled Asynchronous Processing:** Flask web requests remain responsive ($< 20\text{ ms}$) while PySpark batch jobs run in background worker threads with real-time status heartbeats in `data/jobs/`.
- **11-Stage Guided Import Wizard:** Safe ingestion of CSV, XLSX, and XLS with automated header discovery, column candidate mapping, live preview, formula injection (`CWE-1236`) defenses, and cryptographic JSON audit manifests (`SHA-256`).
- **Interactive Faculty Spreadsheet:** 30+ student live grid with real-time red highlight range checks, draft persistence, and instant CSV template export/import.
- **Executive Analytics & Drill-Downs:** Interactive Plotly.js charts, subject difficulty indices ($1.0 - \text{mean percentage}$), and transparent rule-based Student Support Indicators with explicit human-readable reasons (no black-box AI).
- **Downloadable Reports & Briefings:** Printable, standalone HTML executive briefings with `@media print` styling, along with CSV exports for course summaries, support flags, and clean lakehouse records.
- **Local-First Privacy Default:** Operates 100% locally with zero external network dependencies. Student roll numbers and PII are redacted from application logs.
- **Optional AWS S3 Cloud Integration:** Disabled by default (`AWS_ENABLED=false`). Cloud synchronization requires explicit authorization, pre-upload payload review, cost transparency, and random confirmation tokens.

---

## 📂 Project Directory Structure

```text
edupulse-analytics/
├── app.py                      # Master Flask Application Factory & Server Entrypoint
├── requirements.txt            # System dependencies
├── README.md                   # Project documentation & setup guide
├── .env.example                # Environment variables template
├── .gitignore                  # Git ignore rules
├── config/
│   ├── __init__.py
│   ├── settings.py             # Configuration, storage paths & privacy log filters
│   └── assessment_rules.py     # Marks thresholds & 10-point grade scale mappings
├── dashboard/
│   ├── __init__.py
│   ├── routes/
│   │   ├── core.py             # Landing page & health endpoints
│   │   ├── data_management.py  # Ingestion catalog & 11-step import wizard
│   │   ├── class_entry.py      # Interactive class marks entry grid
│   │   ├── processing_monitor.py # PySpark batch monitoring & synthetic generator
│   │   ├── dashboard.py        # Executive institutional overview & KPI cards
│   │   ├── academic_analysis.py# Subject drill-down & difficulty index ranking
│   │   ├── student_performance.py # Longitudinal student trajectory & credit tracking
│   │   ├── reports.py          # Executive briefing downloads & CSV exports
│   │   └── settings.py         # Assessment cutoffs & local storage policy editor
│   ├── templates/              # Jinja2 templates (Bootstrap 5.3, Lucide icons, Plotly)
│   └── static/
│       ├── css/style.css       # Master stylesheet & WCAG 2.1 AA focus rings
│       └── js/main.js          # Client-side scripts & animations
├── src/
│   ├── data_validation.py      # CWE-1236 defense, range checks & validation scorecard
│   ├── import_service.py       # 11-stage ingestion workflow & manifest generation
│   ├── grade_service.py        # University result unpivoting & SGPA calculation
│   ├── data_generator.py       # Scalable synthetic generation (10k to 1M+ records)
│   ├── spark_processing.py     # Native PySpark 4.2 distributed batch pipeline
│   ├── analytics.py            # Analytics calculation & support indicators engine
│   └── report_generator.py     # Printable HTML briefings & CSV report generator
├── services/
│   ├── class_entry_service.py  # Grid unpivoting & template import/export
│   ├── processing_service.py   # Asynchronous Spark background job coordinator
│   └── analytics_service.py    # Pre-computed cache coordinator & query coordinator
├── storage/
│   ├── local_storage.py        # Atomic writes, path sandboxing & manifest registry
│   └── s3_storage.py           # Optional AWS S3 cloud adapter with token guardrails
├── scripts/
│   └── benchmark_runner.py     # Empirical PySpark scale benchmark harness
├── data/                       # Local lakehouse repository
│   ├── raw/                    # Immutable original uploads
│   ├── validated/              # Schema-normalized, cleaned CSVs
│   ├── processed/              # Snappy Parquet partitions with _SUCCESS markers
│   ├── analytics/              # Pre-computed AGG JSON metadata
│   ├── manifests/              # Auditable cryptographic JSON manifests
│   ├── jobs/                   # Asynchronous background job heartbeats
│   ├── drafts/                 # Autosaved class entry grids
│   └── synthetic/              # Generated benchmark datasets
├── docs/                       # Comprehensive specifications & benchmark reports
│   ├── requirements.md         # System Requirements Specification (SRS)
│   ├── architecture.md         # Component Architecture & Decoupled PySpark Pipeline
│   ├── data_model.md           # Marks & Grade Schemas, Parquet StructTypes
│   ├── import_workflow.md      # 11-Stage Spreadsheet Ingestion Workflow
│   ├── privacy_security.md     # FERPA/DPDP, Log Scrubbing, Threat Models
│   ├── aws_setup.md            # Optional AWS S3 Setup, IAM Policies & Costs
│   ├── testing_strategy.md     # Test Pyramid, Ground-Truth Fixtures
│   ├── implementation_roadmap.md # Phased Engineering Roadmap
│   └── benchmark_report.md     # Empirical PySpark Scale Benchmark Report
├── tests/                      # 44 automated unit, integration, and Spark tests
└── logs/                       # Application logs (with PII masking)
```

---

## 🛠️ Quick Start & Local Setup

### 1. Prerequisites
- **Python 3.10+** (Python 3.12 verified)
- **Java Runtime Environment (JRE 11+ or 17 LTS)**: PySpark requires a local Java runtime. The system automatically detects and configures `JAVA_HOME`.
- **Hadoop Windows Binaries**: `winutils.exe` and `hadoop.dll` are pre-configured in `bin/hadoop/bin`.

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment
```bash
cp .env.example .env
```
*(Default settings run completely locally with AWS disabled).*

### 4. Run the Full Test Suite
```bash
pytest tests/ -v
```
*Executes all 44 automated tests covering baseline setup, imports, class entry, grade unpivoting, PySpark batch pipelines, analytics, reports, settings, and S3 guardrails.*

### 5. Launch the Local Web Server
```bash
python app.py
```
Open your browser and navigate to: **`http://127.0.0.1:5000`**

---

## 📊 Empirical PySpark Scale Benchmarks

Tested on a standard local workstation running standalone PySpark 4.2 (`local[*]`):

| Dataset Scale | Raw CSV Size | Parquet Size | Compression | Generation | Spark Batch Time | Throughput | Peak RAM |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **10,000** | 1.06 MB | 0.26 MB | 4.08x | 0.24s | 54.39s (JVM warm-up) | 181.5 rows/s | 88.4 MB |
| **50,000** | 5.25 MB | 1.28 MB | 4.10x | 1.65s | 16.14s | 3,041.4 rows/s | 88.4 MB |
| **100,000** | 10.47 MB | 2.55 MB | 4.11x | 2.97s | 12.15s | 8,063.8 rows/s | 88.4 MB |
| **500,000** | 52.38 MB | 12.75 MB | 4.11x | 14.82s | 58.21s | 8,416.4 rows/s | 112.5 MB |
| **1,000,000** | 104.75 MB | 25.48 MB | 4.11x | 29.54s | 115.42s | 8,491.8 rows/s | 134.2 MB |

*For complete telemetry and architectural analysis, consult [`docs/benchmark_report.md`](docs/benchmark_report.md).*

---

## 🔒 Security & Data Governance

1. **Local-First Sandboxing:** Data directories are protected against directory traversal attacks (`CWE-22`). File writes use atomic rename patterns with transient Windows lock retries.
2. **Formula Injection Sanitization (`CWE-1236`):** Any cell value prefixed with `=`, `+`, `-`, or `@` is prepended with a single quote (`'`) to protect spreadsheet consumers.
3. **Automated PII Redaction:** The `StudentDataMaskingFilter` automatically masks roll numbers matching `STU***99` patterns before write to disk or console.
4. **Transparent Student Diagnostics:** Student Support Indicators are calculated from documented thresholds (e.g. failing $\ge 2$ subjects) and provide clear, human-readable explanations rather than black-box AI scores.
5. **Zero Unexpected Cloud Charges:** AWS S3 integration is disabled by default (`AWS_ENABLED=false`) and requires explicit approval, pre-upload payload sizing, and confirmation tokens.
