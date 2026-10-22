"""
EduPulse Analytics - Application Configuration & Settings
"""
import os
import re
import logging
from pathlib import Path
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Base Project Root
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Auto-detect JAVA_HOME and HADOOP_HOME for PySpark on Windows
def _configure_pyspark_env():
    import sys
    # Ensure worker matches driver Python
    os.environ["PYSPARK_PYTHON"] = sys.executable
    os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable

    # Configure HADOOP_HOME
    local_hadoop = PROJECT_ROOT / "bin" / "hadoop"
    if local_hadoop.exists() and (local_hadoop / "bin" / "winutils.exe").exists():
        os.environ["HADOOP_HOME"] = str(local_hadoop)
        hadoop_bin = str(local_hadoop / "bin")
        current_path = os.environ.get("PATH", "")
        if hadoop_bin not in current_path:
            os.environ["PATH"] = f"{hadoop_bin};{current_path}"

    # Configure JAVA_HOME
    if not os.environ.get("JAVA_HOME"):
        candidates = [
            Path(r"C:\Program Files\Tableau\Tableau Public 2026.2\bin\jre"),
            Path(r"C:\Program Files\Java\jdk-17"),
            Path(r"C:\Program Files\Java\jdk-11"),
            Path(r"C:\Program Files\Eclipse Adoptium\jdk-17"),
            Path(r"C:\Program Files\Zulu\zulu-17")
        ]
        for candidate in candidates:
            if candidate.exists() and (candidate / "bin" / "java.exe").exists():
                os.environ["JAVA_HOME"] = str(candidate)
                java_bin = str(candidate / "bin")
                current_path = os.environ.get("PATH", "")
                if java_bin not in current_path:
                    os.environ["PATH"] = f"{java_bin};{current_path}"
                break

_configure_pyspark_env()

# Load .env if present
load_dotenv(PROJECT_ROOT / ".env")


class StudentDataMaskingFilter(logging.Filter):
    """
    Privacy Filter: Redacts student identifiers, roll numbers,
    and potential PII from application logs.
    """
    STUDENT_ID_REGEX = re.compile(
        r'\b(STU[-\d\w]+|\d{2,4}[A-Za-z]{2,5}\d{3,6}|[A-Za-z]{2,4}\d{4,8})\b',
        re.IGNORECASE
    )

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self.STUDENT_ID_REGEX.sub(lambda m: self._mask_id(m.group(0)), record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: (self.STUDENT_ID_REGEX.sub(lambda m: self._mask_id(m.group(0)), v) if isinstance(v, str) else v)
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    self.STUDENT_ID_REGEX.sub(lambda m: self._mask_id(m.group(0)), v) if isinstance(v, str) else v
                    for v in record.args
                )
        return True

    @staticmethod
    def _mask_id(identifier: str) -> str:
        if len(identifier) <= 4:
            return "****"
        return f"{identifier[:2]}***{identifier[-2:]}"


@dataclass
class StorageConfig:
    """Directory paths for the file-first repository."""
    data_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data")
    raw_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "raw")
    validated_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "validated")
    processed_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "processed")
    analytics_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "analytics")
    manifests_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "manifests")
    jobs_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "jobs")
    drafts_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "drafts")
    reports_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "reports")
    synthetic_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "synthetic")
    temp_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "temp")
    logs_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "logs")

    def ensure_directories(self) -> None:
        """Create all required data and log directories if they do not exist."""
        for path in [
            self.data_dir, self.raw_dir, self.validated_dir,
            self.processed_dir, self.analytics_dir, self.manifests_dir,
            self.jobs_dir, self.drafts_dir, self.reports_dir,
            self.synthetic_dir, self.temp_dir, self.logs_dir
        ]:
            path.mkdir(parents=True, exist_ok=True)


@dataclass
class SparkConfig:
    """PySpark standalone execution parameters."""
    app_name: str = os.getenv("SPARK_APP_NAME", "EduPulseAnalytics")
    master: str = os.getenv("SPARK_MASTER", "local[*]")
    driver_memory: str = os.getenv("SPARK_DRIVER_MEMORY", "4g")
    executor_memory: str = os.getenv("SPARK_EXECUTOR_MEMORY", "2g")
    shuffle_partitions: int = int(os.getenv("SPARK_SHUFFLE_PARTITIONS", "8"))


@dataclass
class AWSConfig:
    """Optional Amazon S3 Cloud Storage configuration (Disabled by default)."""
    enabled: bool = os.getenv("AWS_ENABLED", "false").lower() in ("true", "1", "yes")
    region: str = os.getenv("AWS_REGION", "us-east-1")
    bucket_name: str = os.getenv("AWS_S3_BUCKET", "")
    prefix: str = os.getenv("AWS_S3_PREFIX", "archives/")
    access_key_id: str = os.getenv("AWS_ACCESS_KEY_ID", "")
    secret_access_key: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")


@dataclass
class AppConfig:
    """Master Application Configuration."""
    env: str = os.getenv("FLASK_ENV", "development")
    debug: bool = os.getenv("FLASK_DEBUG", "true").lower() in ("true", "1", "yes")
    secret_key: str = os.getenv("SECRET_KEY", "edupulse-dev-secret-key-change-in-prod-2026")
    port: int = int(os.getenv("PORT", "5000"))
    host: str = os.getenv("HOST", "127.0.0.1")
    max_content_length: int = 50 * 1024 * 1024  # 50 MB Upload Limit
    storage: StorageConfig = field(default_factory=StorageConfig)
    spark: SparkConfig = field(default_factory=SparkConfig)
    aws: AWSConfig = field(default_factory=AWSConfig)

    def setup_logging(self) -> None:
        """Initializes application logging with privacy masking filters."""
        self.storage.ensure_directories()
        log_file = self.storage.logs_dir / "edupulse.log"

        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(StudentDataMaskingFilter())

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO if not self.debug else logging.DEBUG)
        console_handler.setFormatter(formatter)
        console_handler.addFilter(StudentDataMaskingFilter())

        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        root_logger.handlers = [file_handler, console_handler]

        logging.getLogger("werkzeug").setLevel(logging.WARNING)


def get_config() -> AppConfig:
    """Factory function returning the initialized configuration."""
    cfg = AppConfig()
    cfg.storage.ensure_directories()
    return cfg
