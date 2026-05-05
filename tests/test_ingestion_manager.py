from qallm.ingestion.ingestion_manager import IngestionManager


def test_ingestion_manager_single_py(tmp_path):
    py_file = tmp_path / "script.py"
    py_file.write_text("print('test')")

    manager = IngestionManager()
    units = manager.collect(str(py_file))
    assert len(units) == 1
    assert "print('test')" in units[0].source_code


def test_ingestion_manager_directory(tmp_path):
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "s1.py").write_text("x=1")

    manager = IngestionManager()
    units = manager.collect(str(tmp_path))
    assert len(units) == 1