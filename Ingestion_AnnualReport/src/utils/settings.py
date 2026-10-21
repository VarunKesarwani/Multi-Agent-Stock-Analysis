"""Environment configuration shared by scripts and notebooks."""

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import dotenv_values

MODULE_DIR = Path(__file__).resolve().parents[2]


def env_values(env_file: Path | str | None = None) -> tuple[dict[str, str], Path]:
    """Resolve .env beside this module, independently of the working directory."""
    path = Path(env_file).expanduser().resolve() if env_file else MODULE_DIR / ".env"
    file_values = {
        key: value for key, value in dotenv_values(path).items() if value is not None
    }
    config_name = os.environ.get(
        "RAG_CONFIG_FILE", file_values.get("RAG_CONFIG_FILE", "config.yaml")
    )
    config_path = env_path(config_name, path.parent)
    defaults = (
        yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if config_path.exists()
        else {}
    )
    if defaults is None:
        defaults = {}
    if not isinstance(defaults, dict) or any(
        not isinstance(k, str) or isinstance(v, (dict, list))
        for k, v in defaults.items()
    ):
        raise ValueError(
            "config.yaml must contain a flat mapping of setting names to scalar values"
        )
    values = {
        k: str(v).lower() if isinstance(v, bool) else str(v)
        for k, v in defaults.items()
        if v is not None
    }
    values.update(file_values)
    values.update(os.environ)
    return values, path.parent


def env_path(value: str, root: Path) -> Path:
    """Resolve relative paths against the environment file's directory."""
    path = Path(value).expanduser()
    return path if path.is_absolute() else (root / path).resolve()


def boolean(value: str) -> bool:
    """Parse explicit booleans; reject misspellings instead of silently disabling."""
    value = value.strip().lower()
    if value not in {"true", "false", "1", "0"}:
        raise ValueError("Boolean settings must be true/false or 1/0")
    return value in {"true", "1"}


@dataclass(frozen=True)
class DocumentSettings:
    annual_pdf_dir: Path
    educational_pdf_dir: Path
    markdown_dir: Path
    symbols_csv: Path
    summary_csv: Path
    educational_source: str
    educational_topic: str

    @classmethod
    def from_env(cls, env_file: Path | str | None = None) -> "DocumentSettings":
        """Read PDF/Markdown paths and default education metadata."""
        values, root = env_values(env_file)
        return cls(
            annual_pdf_dir=env_path(
                values.get("ANNUAL_PDF_DIR", "../RAG_Fin_Learning/AnnualReport"), root
            ),
            educational_pdf_dir=env_path(
                values.get("EDUCATIONAL_PDF_DIR", "../RAG_Fin_Learning/Education"), root
            ),
            markdown_dir=env_path(
                values.get("MARKDOWN_DIR", "../RAG_Fin_Learning/Processed_Markdown"),
                root,
            ),
            symbols_csv=env_path(values.get("SYMBOLS_CSV", "../symbols.csv"), root),
            summary_csv=env_path(
                values.get("PDF_SUMMARY_CSV", "processing_summary.csv"), root
            ),
            educational_source=values.get("EDUCATIONAL_SOURCE", "unspecified"),
            educational_topic=values.get("EDUCATIONAL_TOPIC", "financial_education"),
        )
