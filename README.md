# healthcare-ai

A robust, production-ready Python project scaffold engineered for artificial intelligence and machine learning applications in healthcare, clinical data analysis, and medical research.

## Overview

The primary objective of this repository is to maximize developer productivity, research reproducibility, and code reliability while providing foundational scaffolding for safe, compliant, and scalable healthcare AI development.

### Core Principles
- **Reproducibility & Modularity:** Clean separation of data processing, model architectures, configuration management, and exploratory analysis.
- **Data Governance & Safety:** Safe handling of healthcare datasets with strict `.gitignore` safeguards against accidental leakage of Protected Health Information (PHI/PII), large medical imaging formats (e.g., DICOM, NIfTI), or large binary model weights.
- **Quality Assurance & CI/CD:** Automated linting, static typing, unit testing, and multi-version Python verification via GitHub Actions.

---

## Project Structure

```text
healthcare-ai/
├── .github/
│   └── workflows/
│       └── ci.yml              # GitHub Actions CI, one job per area (core: Python 3.10–3.14, document-hub: 3.12/3.14)
├── .junie/
│   └── guidelines.md           # Junie entry point (points to AGENTS.md)
├── packages/
│   └── healthcare-ai-core/     # Core library, imported as `healthcare_ai`
│       ├── src/healthcare_ai/  # Reusable library and pipeline implementations
│       ├── tests/              # Pytest suite for the core library
│       ├── pyproject.toml      # Package build, pytest and mypy config
│       ├── requirements.txt    # Production dependency specifications
│       ├── requirements-dev.txt # Development, testing, and static analysis tooling
│       └── AGENTS.md           # Assistant guidance for core
├── services/                   # Deployable web services, one folder each
│   ├── document-hub/           # Django document service (uv, Docker)
│   └── README.md               # Conventions for adding a service
├── configs/                    # Experiment configurations, hyperparameters, model configs
├── data/                       # Healthcare and tabular/imaging datasets (gitignored)
│   ├── raw/                    # Immutable raw datasets (read-only)
│   └── processed/              # Sanitized, preprocessed, or featurized data
├── docs/                       # Architecture notes (architecture.md) and write-ups
├── models/                     # Model checkpoints, serialized artifacts (.pt, .onnx, etc.)
├── notebooks/                  # Jupyter notebooks for exploratory analysis and prototyping
├── .env.example                # Template for environment variables and secrets
├── .gitignore                  # Rules ignoring caches, data files, models, and environments
├── AGENTS.md                   # Assistant guidance: repo map, commands, PHI rules
├── CLAUDE.md                   # Claude Code entry point (imports AGENTS.md)
├── pyproject.toml              # Shared ruff lint/format config (not a package)
└── README.md                   # Repository documentation
```

---

## Detailed Directory Guide

- **`packages/healthcare-ai-core/`**: The core package (`healthcare_ai`). Designed to house modular subpackages for data loaders, preprocessing pipelines, model architectures, loss functions, evaluation metrics, and inference serving.
- **`data/`**: Structured into `raw/` and `processed/`. Configured with `.gitkeep` files while ensuring all actual medical data remains untracked to protect patient privacy and keep repository storage optimal.
- **`configs/`**: Centralized storage for YAML/JSON configurations, enabling deterministic runs and experiment tracking without hardcoding parameters.
- **`models/`**: Dedicated directory for local checkpoints and weights. Binary artifacts are excluded from version control.
- **`notebooks/`**: Scratchpad and exploratory workspace for exploratory data analysis (EDA) and experimental validation.
- **`packages/healthcare-ai-core/tests/`**: Pytest test suite ensuring code robustness and preventing regressions across package components.
- **`services/`**: Web services built on the core library, each an independent project. See [`services/README.md`](services/README.md) and [`docs/architecture.md`](docs/architecture.md) for the mono-repo layout and rationale.

---

## Getting Started

### Prerequisites

- **Python:** 3.10 or higher
- **Git:** Version control
- **Virtual Environment Tool:** `venv`, `conda`, or `uv`

### Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd healthcare-ai
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install the package and dependencies:**
   To install the core package in editable mode along with development and test tools:
   ```bash
   pip install --upgrade pip
   pip install -e "packages/healthcare-ai-core[dev]"
   ```

4. **Set up local environment variables:**
   ```bash
   cp .env.example .env
   ```
   Modify `.env` to configure storage paths, logging levels, or experiment tracking credentials (e.g., Weights & Biases, MLflow).

---

## Development & Code Quality Standards

To maintain high code quality and prevent defects before deployment, standardized tools are configured in `pyproject.toml` files: ruff in the root one (shared by every package and service), pytest and mypy per project.

- **Run Automated Tests** (from the core directory):
  ```bash
  cd packages/healthcare-ai-core
  pytest --cov=healthcare_ai
  ```

- **Run Code Formatting & Linting (Ruff)** (from the repo root):
  ```bash
  ruff check .
  ruff format --check .
  ```
  To automatically apply formatting and safe fixes:
  ```bash
  ruff format .
  ruff check --fix .
  ```

- **Static Type Checking (Mypy)** (from the core directory):
  ```bash
  cd packages/healthcare-ai-core
  mypy src
  ```

---

## Continuous Integration (CI)

A GitHub Actions pipeline (`.github/workflows/ci.yml`) has one job per area. The `core` job triggers on pushes and pull requests targeting `main` / `master` that touch `packages/healthcare-ai-core/`, the root `pyproject.toml` or the workflow file. It validates:
- Installation of the core package across Python 3.10, 3.11, 3.12 and 3.14.
- Code style and linting compliance with `ruff`.
- Type correctness with `mypy`.
- Unit test execution and test coverage reports with `pytest`.

---

## Healthcare Data Ethics & Compliance Notice

When utilizing this repository for healthcare and biomedical data:
- Never commit actual patient data, PHI, or credentials to Git.
- Ensure all raw data placed in `data/raw/` is de-identified in compliance with relevant data privacy regulations (e.g., HIPAA, GDPR).
- Utilize `.env` for managing API keys and secrets securely.
