import re


def format_timecode(milliseconds: int) -> str:
    if not isinstance(milliseconds, int) or milliseconds < 0:
        raise ValueError("Thời gian phải là số mili giây không âm.")
    seconds, ms = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}.{ms:03}"


def parse_timecode(value: str) -> int:
    match = re.fullmatch(r"(\d{2,}):([0-5]\d):([0-5]\d)\.(\d{3})", value.strip())
    if not match:
        raise ValueError("Nhập thời gian dạng HH:MM:SS.mmm (ví dụ 00:01:10.200).")
    hours, minutes, seconds, ms = map(int, match.groups())
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + ms
