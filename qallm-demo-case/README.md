# Research Pipeline Demo

A small research data pipeline for demonstrating QALLM's quality assessment capabilities.

## Structure

- `src/research_pipeline/config.py` - Configuration (contains intentional security issues)
- `src/research_pipeline/data_loader.py` - Data loading and preprocessing
- `src/research_pipeline/model.py` - Model training and evaluation
- `src/research_pipeline/utils.py` - Utility functions
- `src/research_pipeline/pipeline.py` - Pipeline orchestration
- `data/sample_dataset.csv` - Sample dataset

## Usage

```
python -m research_pipeline.pipeline data/sample_dataset.csv target
```

## Known Issues (for QALLM demo)

This codebase intentionally contains quality issues across all categories:
- Security: hardcoded secrets, eval(), subprocess with shell=True, pickle.load
- Complexity: high cyclomatic complexity in scoring and branching functions
- Code smells: unused imports, unsorted imports, duplicated patterns
- Poor documentation: minimal comments, no docstrings
- No tests
