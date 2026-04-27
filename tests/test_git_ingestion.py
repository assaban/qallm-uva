from qallm.ingestion.parsers import IngestionManager


def test_ingestion_manager_git_clone():
    """
    Validates GitHub cloning and recursive scanning of a remote repository.
    Targets Stage 1 Ingestion requirements[cite: 76, 146].
    """
    # A small, public repo with .py or .ipynb files for testing
    test_repo_url = "https://github.com/assaban/qallm-uva.git"
    manager = IngestionManager()

    units = manager.collect(test_repo_url)

    # Verify we found the files we just created in previous features
    assert len(units) > 0
    # Ensure at least one unit is the parser we wrote
    filenames = [str(u.original_path) for u in units]
    assert any("parsers.py" in f for f in filenames)


def __test_ingestion_manager_zip_extraction(tmp_path):
    """
    Validates ZIP support for archived datasets.
    """
    import zipfile
    zip_path = tmp_path / "test_data.zip"
    py_content = "def test_func(): return True"

    # Create a dummy ZIP with a python file
    with zipfile.ZipFile(zip_path, 'w') as z:
        z.writestr("research_script.py", py_content)

    manager = IngestionManager()
    units = manager.collect(str(zip_path))

    assert len(units) == 1
    assert "test_func" in units[0].source