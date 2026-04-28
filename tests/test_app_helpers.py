import app


def test_parse_nums_basic():
    assert app._parse_nums("1,3 5", 5) == [0, 2, 4]


def test_parse_nums_out_of_range_and_invalid():
    assert app._parse_nums("0, 6, a, 2", 5) == [1]


def test_fmt_bytes():
    assert app.fmt_bytes(0) == "0.0 B"
    assert app.fmt_bytes(1024) == "1.0 KB"
