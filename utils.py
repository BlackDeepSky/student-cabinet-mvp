"""
Мелкие вспомогательные функции.
"""


def sanitize_filename(filename: str) -> str:
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
    return safe[:100]
