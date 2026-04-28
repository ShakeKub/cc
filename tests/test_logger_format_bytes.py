from core.logger import CleanerLogger


def test_logger_format_bytes():
    assert CleanerLogger._format_bytes(0) == "0.0 B"
    assert CleanerLogger._format_bytes(1024) == "1.0 KB"
    assert CleanerLogger._format_bytes(1024 * 1024) == "1.0 MB"
