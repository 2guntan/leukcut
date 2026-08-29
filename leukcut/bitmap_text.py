from __future__ import annotations

import textwrap
import unicodedata


# A deliberately small built-in bitmap face keeps runtime dependencies to
# PyYAML + ffmpeg and works even when ffmpeg was built without libfreetype.
FONT: dict[str, tuple[str, ...]] = {
    " ": ("00000",) * 7,
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01111", "10000", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "J": ("00111", "00010", "00010", "00010", "10010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "11011", "10001"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "10000", "11110", "00001", "00001", "11110"),
    "6": ("01110", "10000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00001", "01110"),
    "_": ("00000", "00000", "00000", "00000", "00000", "00000", "11111"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    ".": ("00000", "00000", "00000", "00000", "00000", "01100", "01100"),
    ",": ("00000", "00000", "00000", "00000", "00110", "00100", "01000"),
    "'": ("00100", "00100", "00000", "00000", "00000", "00000", "00000"),
    '"': ("01010", "01010", "00000", "00000", "00000", "00000", "00000"),
    ":": ("00000", "01100", "01100", "00000", "01100", "01100", "00000"),
    "!": ("00100", "00100", "00100", "00100", "00100", "00000", "00100"),
    "?": ("01110", "10001", "00001", "00010", "00100", "00000", "00100"),
    "/": ("00001", "00010", "00010", "00100", "01000", "01000", "10000"),
}


def ascii_upper(text: str) -> str:
    punctuation = str.maketrans({"’": "'", "‘": "'", "«": '"', "»": '"', "—": "-", "–": "-", "…": "..."})
    decomposed = unicodedata.normalize("NFKD", text.translate(punctuation))
    return "".join(char for char in decomposed if not unicodedata.combining(char)).upper()


def wrap_action(text: str, width: int = 28, max_lines: int = 5) -> list[str]:
    clean = " ".join(ascii_upper(text).split())
    return textwrap.wrap(clean, width=width, break_long_words=False, break_on_hyphens=False)[:max_lines]


def draw_text_filters(
    text: str,
    x: int,
    y: int,
    scale: int,
    color: str = "white@0.7",
    line_gap: int = 3,
) -> list[str]:
    filters: list[str] = []
    for line_no, line in enumerate(text.splitlines()):
        for char_no, char in enumerate(ascii_upper(line)):
            glyph = FONT.get(char, FONT["?"])
            for row, pixels in enumerate(glyph):
                column = 0
                while column < 5:
                    if pixels[column] == "0":
                        column += 1
                        continue
                    end = column + 1
                    while end < 5 and pixels[end] == "1":
                        end += 1
                    px = x + char_no * 6 * scale + column * scale
                    py = y + line_no * (7 * scale + line_gap * scale) + row * scale
                    filters.append(
                        f"drawbox=x={px}:y={py}:w={(end - column) * scale}:h={scale}:color={color}:t=fill"
                    )
                    column = end
    return filters


SEGMENT_DIGITS = {
    "a": (0, 2, 3, 5, 6, 7, 8, 9),
    "b": (0, 1, 2, 3, 4, 7, 8, 9),
    "c": (0, 1, 3, 4, 5, 6, 7, 8, 9),
    "d": (0, 2, 3, 5, 6, 8, 9),
    "e": (0, 2, 6, 8),
    "f": (0, 4, 5, 6, 8, 9),
    "g": (2, 3, 4, 5, 6, 8, 9),
}


def _segment_enable(digit_expression: str, segment: str) -> str:
    return "+".join(f"eq({digit_expression},{digit})" for digit in SEGMENT_DIGITS[segment])


def timecode_filters(width: int, fps: int, color: str = "white@0.7") -> list[str]:
    """Draw dynamic MM:SS:FF with seven-segment boxes using frame number n."""
    second = f"floor(n/{fps})"
    digits = (
        f"mod(floor({second}/600),10)",
        f"mod(floor({second}/60),10)",
        f"mod(floor({second}/10),6)",
        f"mod({second},10)",
        f"floor(mod(n,{fps})/10)",
        "mod(n,10)",
    )
    digit_width, digit_height, thickness, gap = 20, 32, 3, 5
    total_width = 6 * digit_width + 2 * 10 + 7 * gap
    base_x, base_y = width - total_width - 42, 40
    filters: list[str] = []
    positions = [0, 1, 3, 4, 6, 7]
    segment_geometry = {
        "a": (thickness, 0, digit_width - 2 * thickness, thickness),
        "b": (digit_width - thickness, thickness, thickness, digit_height // 2 - thickness),
        "c": (digit_width - thickness, digit_height // 2, thickness, digit_height // 2 - thickness),
        "d": (thickness, digit_height - thickness, digit_width - 2 * thickness, thickness),
        "e": (0, digit_height // 2, thickness, digit_height // 2 - thickness),
        "f": (0, thickness, thickness, digit_height // 2 - thickness),
        "g": (thickness, digit_height // 2 - thickness // 2, digit_width - 2 * thickness, thickness),
    }
    for expression, position in zip(digits, positions, strict=True):
        x = base_x + position * (digit_width + gap)
        for segment, (dx, dy, box_width, box_height) in segment_geometry.items():
            enable = _segment_enable(expression, segment)
            filters.append(
                f"drawbox=x={x + dx}:y={base_y + dy}:w={box_width}:h={box_height}:"
                f"color={color}:t=fill:enable='{enable}'"
            )
    for position in (2, 5):
        x = base_x + position * (digit_width + gap) + 3
        filters.append(f"drawbox=x={x}:y={base_y + 9}:w=3:h=3:color={color}:t=fill")
        filters.append(f"drawbox=x={x}:y={base_y + 21}:w=3:h=3:color={color}:t=fill")
    return filters
