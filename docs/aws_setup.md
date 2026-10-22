# EduPulse Analytics — Optional AWS Cloud Integration Guide

**Document Version:** 1.0.0  
**Status:** Architecture & Requirements Phase (Approved for Review)  
**System Name:** EduPulse Analytics  

---

## 1. Cloud Policy & Strict Opt-In Philosophy

> [!IMPORTANT]
> **Cloud Integration Disabled by Default:** All development, testing, validation, and analytics operate 100% locally out of the box. EduPulse Analytics **never** provisions cloud resources, initializes AWS services, creates S3 buckets, or transmits student data over the internet without explicit user configuration and active approval.

AWS integration is designed strictly as an **optional, secure, offsite analytical archiving destination**.

### Core Guarantees:
1. **Zero Automatic Cloud Uploads:** No file is ever synchronized to AWS without an explicit, interactive user click and confirmation dialog.
2. **Never Transmit Real Student Names:** Any dataset destined for cloud archiving must be pseudonymized or synthetic.
3. **No Hardcoded Credentials:** AWS keys are never stored in source code, configuration files committed to Git, or database tables.
4. **Least-Privilege Scoping:** IAM permissions are restricted exclusively to a single private S3 bucket and path prefix.

---

## 2. Target Cloud Architecture (When Enabled)

```mermaid
graph LR
    subgraph LocalInstitution ["Institution Local Environment"]
        App["EduPulse Analytics Application"]
        LocalDisk["Local Storage (data/)"]
        User["Administrator (Manual Confirmation)"]
    end

    subgraph AWSCloud ["Amazon Web Services (Optional Cloud Storage)"]
        S3["Private S3 Bucket<br/>edupulse-archive-{id}"]
        subgraph BucketSecurity ["S3 Security Baseline"]
            BPA["Block All Public Access"]
            SSE["Server-Side Encryption (SSE-S3 / SSE-KMS)"]
            TLS["Enforce TLS 1.3 / aws:SecureTransport"]
            Lifecycle["Glacier Deep Archive Transition (365 Days)"]
        end
    end

    User -->|Explicit Click & Review| App
    App -->|Read Validated Dataset| LocalDisk
    App -->|Encrypted HTTPS (boto3)| S3
    S3 --- BPA
    S3 --- SSE
    S3 --- TLS
    S3 --- Lifecycle
```

---

## 3. S3 Bucket Security Baseline Configuration

When configuring the AWS S3 bucket for EduPulse Analytics, the following security baseline must be enforced:

1. **Bucket Naming Convention:**
   `edupulse-analytics-{institution-id}-{environment}` (e.g., `edupulse-analytics-polytech-prod`)
2. **Block All Public Access:** All four public access block settings enabled (`BlockPublicAcls`, `IgnorePublicAcls`, `BlockPublicPolicy`, `RestrictPublicBuckets`).
3. **Default Encryption:** Enabled with AES-256 (`aws:kms` or `AES256`).
4. **Bucket Policy Enforcing TLS:** Disallow non-HTTPS requests:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EnforceTLSRequestsOnly",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": [
        "arn:aws:s3:::edupulse-analytics-polytech-prod",
        "arn:aws:s3:::edupulse-analytics-polytech-prod/*"
      ],
      "Condition": {
        "Bool": {
          "aws:SecureTransport": "false"
        }
      }
    }
  ]
}
```

---

## 4. Least-Privilege IAM Policy

If creating an IAM user or role for EduPulse Analytics, apply this scoped policy restricting permissions strictly to the target bucket:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowEduPulseBucketList",
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket",
        "s3:GetBucketLocation"
      ],
      "Resource": "arn:aws:s3:::edupulse-analytics-polytech-prod"
    },
    {
      "Sid": "AllowEduPulseObjectOperations",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:GetObjectVersion",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::edupulse-analytics-polytech-prod/archives/*"
    }
  ]
}
```

---

## 5. Credential Management & Configuration

### 5.1 Environment Variables (Development & Local Servers)
Store credentials in a non-committed `.env` file (included in `.gitignore`):

```bash
# .env (Do not commit to version control)
AWS_ENABLED=false
AWS_REGION=us-east-1
AWS_S3_BUCKET=edupulse-analytics-polytech-prod
AWS_S3_PREFIX=archives/
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

### 5.2 IAM Roles (Production EC2 / ECS / EKS)
In production environments, eliminate long-lived access keys completely by attaching an IAM Instance Profile or IAM Role for Service Accounts (IRSA). `boto3` automatically detects and assumes these roles via the AWS credential provider chain.

---

## 6. Pre-Upload Confirmation Workflow & Cost Transparency

To prevent unintentional uploads and unexpected cloud expenses, EduPulse implements an interactive **Cloud Archive Confirmation Modal**:

```text
+--------------------------------------------------------------------------+
|  Cloud Archive Confirmation (AWS S3)                                    |
+--------------------------------------------------------------------------+
|  You are about to synchronize dataset to an external AWS S3 bucket:      |
|                                                                          |
|  Dataset:           VAL_2026_Semester_Spring (1,000,000 records)         |
|  Payload Size:      48.2 MB (Snappy-compressed Parquet)                 |
|  Target Bucket:     s3://edupulse-analytics-polytech-prod/archives/     |
|  Target Region:     us-east-1 (N. Virginia)                              |
|                                                                          |
|  Privacy Notice:                                                         |
|  - Real student names have been omitted.                                 |
|  - Student IDs are cryptographically pseudonymized.                      |
|                                                                          |
|  Estimated Cost Breakdown:                                               |
|  - S3 Storage (Standard):  ~$0.0011 / month                              |
|  - S3 PUT API Request:     ~$0.00025 (50 requests)                       |
|  - Data Transfer In:       FREE                                          |
|                                                                          |
|  [ Cancel / Abort ]                           [ Confirm & Upload to S3 ] |
+--------------------------------------------------------------------------+
```

---

## 7. Cloud Storage Cost Breakdown & Guidance

| AWS S3 Component | Pricing Tier (us-east-1 Benchmark) | Cost for 1,000,000 Academic Records (~50 MB Parquet) | Cost for 100 Datasets (5 GB) |
| :--- | :--- | :--- | :--- |
| **S3 Standard Storage** | $\$0.023$ per GB / month | $\$0.0011$ / month | $\$0.115$ / month |
| **S3 Glacier Deep Archive** | $\$0.00099$ per GB / month | $\$0.00005$ / month | $\$0.005$ / month |
| **PUT / POST Requests** | $\$0.005$ per 1,000 requests | $<\$0.001$ | $<\$0.01$ |
| **Data Ingestion (Transfer In)** | Free | $\$0.00$ | $\$0.00$ |
| **Data Download (Transfer Out)** | Free up to 100 GB / month | $\$0.00$ (within free tier) | $\$0.00$ |

*Summary:* For academic institutions archiving 1 million records per semester, annual AWS S3 cloud costs are negligible (less than $\$2.00\text{ USD}$ per year).

---

## 8. Local Testing Without AWS (Mocking with `moto`)

During testing and CI/CD pipelines, tests run against `moto` (an in-memory AWS mock). Zero AWS accounts, network calls, or billable infrastructure are utilized:

```python
import pytest
from moto import mock_aws
import boto3
from storage.s3_storage import S3Storage

@mock_aws
def test_s3_storage_upload_and_download():
    # Setup mock S3 environment
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-edupulse-bucket")
    
    # Initialize storage adapter
    storage = S3Storage(bucket_name="test-edupulse-bucket", region="us-east-1")
    
    # Verify zero-cost mock file upload
    test_data = b"record_id,student_id,grade\n1,STU001,A"
    success = storage.upload_bytes(test_data, "archives/test.csv")
    assert success is True
    
    # Verify download
    downloaded = storage.download_bytes("archives/test.csv")
    assert downloaded == test_data
```
