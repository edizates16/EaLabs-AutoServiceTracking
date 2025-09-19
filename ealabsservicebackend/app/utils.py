import re

def norm_plate(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", s.upper().strip())