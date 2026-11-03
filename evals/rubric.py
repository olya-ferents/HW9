from pathlib import Path

ROOT = Path(__file__).resolve().parent


def text(metadata: dict) -> str:
    rubric_file = metadata.get("rubric_file")
    if not rubric_file:
        return metadata.get("rubric", "")

    path = (ROOT / rubric_file).resolve()
    if ROOT not in path.parents:
        raise ValueError(f"rubric_file must be inside {ROOT}: {rubric_file!r}")
    return path.read_text(encoding="utf-8").strip()
