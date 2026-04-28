from pathlib import Path

from core import cleaner


class DummyLogger:
    def warning(self, message: str):
        return None

    def error(self, message: str):
        return None

    def log(self, *args, **kwargs):
        return None


def test_safe_remove_file(tmp_path: Path):
    target = tmp_path / "temp.txt"
    target.write_text("abc", encoding="utf-8")
    freed = cleaner._safe_remove(target, DummyLogger())
    assert freed == 3
    assert not target.exists()


def test_is_protected_config_path():
    assert cleaner._is_protected(Path("C:\\Windows\\System32"))
