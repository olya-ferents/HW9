"""calibrate_run.py: прогнати суддю N разів по ЗАПИСАНИХ відповідях і порахувати
самоузгодженість та узгодженість з інтервалом Вілсона.

Запуск у контейнері з кореня репозиторію (де лежать judge.py і sets/):
  docker compose run --rm --entrypoint python eval tools/calibrate_run.py l09_labels
  (JUDGE_MODEL у .env; необов'язково: RUNS=5, TEMP=0.7, GROUP_BY_DISPUTED=1)

Чому не runner.py: для assertion "judge" ранер судить свіжу відповідь агента на `input`
і бере лише останній з runs. Тут судиться саме `answer_under_test`.
"""
import hashlib, json, os, sys, time
from collections import Counter
from datetime import datetime, timezone
from math import sqrt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from judge import JUDGE_PROMPT_VERSION, RUBRIC_VERSION, judge, judge_once  # noqa: E402
from rubric import text as rubric_text  # noqa: E402


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, c - h, c + h, h


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "l09_labels"
    path = ROOT / "sets" / f"{name}.jsonl"
    runs = int(os.environ.get("RUNS", "5"))
    temp = float(os.environ["TEMP"]) if os.environ.get("TEMP") else None
    model = os.environ.get("JUDGE_MODEL", "")
    single_call = os.environ.get("CALIBRATION_SINGLE_CALL") == "1"
    if not model or model == "not-used":
        sys.exit("JUDGE_MODEL не задано (див. .env)")
    cases = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()
             if l.strip() and not l.startswith("//")]
    cases = [c for c in cases if c["additional_metadata"].get("assertion") == "judge"]
    missing = [c["id"] for c in cases if "label" not in c["additional_metadata"]]
    if missing:
        sys.exit(f"немає label (розмітьте набір до прогону судді): {missing}")

    rows = []
    started = time.monotonic()
    invalid = quote_found = 0
    for c in cases:
        m = c["additional_metadata"]
        vs, quotes, responses = [], [], []
        for _ in range(runs):
            r = (judge_once if single_call else judge)(c["input"], c["answer_under_test"],
                      rubric_text(m), model, temp)
            vs.append(r["verdict"]); quotes.append(r["quote"])
            if single_call:
                found = bool(r["quote"]) and r["quote"] in c["answer_under_test"]
                quote_found += found
                invalid += r["verdict"] == "ERROR"
                responses.append({**r, "quote_found": found})
                if r["verdict"] == "ERROR":
                    print(f'{c["id"]} ERROR: {r["error"]}', flush=True)
        major = Counter(vs).most_common(1)[0][0]
        rows.append({"id": c["id"], "label": m["label"], "disputed": bool(m.get("disputed")),
                     "verdicts": vs, "majority": major, "stable": len(set(vs)) == 1,
                     "agree": major == m["label"], "quote_sample": quotes[0]})
        if single_call:
            rows[-1]["responses"] = responses
            rows[-1]["stable"] = len(set(vs)) == 1 and "ERROR" not in vs
        print(f'{c["id"]:<8} мітка {m["label"]:<4} вердикти {"".join(v[0] for v in vs)}'
              f'  більшість {major:<4} {"збіг" if major == m["label"] else "РОЗБІГ"}'
              f'{"" if len(set(vs)) == 1 else "  (нестабільний)"}')

    n = len(rows)
    stable = sum(r["stable"] for r in rows)
    agree = sum(r["agree"] for r in rows)
    print(f"\nсамоузгодженість: {stable} з {n}")
    p, lo, hi, h = wilson(agree, n)
    print(f"узгодженість:     {agree} з {n} = {p:.2f}, 95 % інтервал {lo:.2f}–{hi:.2f}  →  ±{h:.2f}")
    groups = {}
    for r in rows:
        g = "спірні" if r["disputed"] else ("очевидні " + r["label"])
        groups.setdefault(g, [0, 0]); groups[g][1] += 1; groups[g][0] += r["agree"]
    for g, (k, t) in sorted(groups.items()):
        print(f"  {g:<16} збіглося {k} з {t}")
    elapsed = time.monotonic() - started
    if single_call:
        print(f"без валідного JSON: {invalid} з {n * runs}")
        print(f"цитату знайдено: {quote_found} з {n * runs}")
        print(f"час прогону: {elapsed:.2f} с; середній виклик: {elapsed / (n * runs):.2f} с")

    out = {"set": name, "set_hash": hashlib.sha256(path.read_bytes()).hexdigest()[:12],
           "judge_model": model, "judge_prompt_version": JUDGE_PROMPT_VERSION,
           "rubric_version": RUBRIC_VERSION, "temperature": temp, "runs": runs,
           "ran_at": datetime.now(timezone.utc).isoformat(),
           "self_consistency": [stable, n], "agreement": [agree, n],
           "agreement_wilson": [round(lo, 3), round(hi, 3)], "cases": rows}
    if single_call:
        out.update({"judge_format": os.environ.get("JUDGE_FORMAT", "json"),
                    "call_mode": "single", "elapsed": elapsed,
                    "calls": n * runs, "invalid_json": invalid,
                    "quote_found": quote_found})
    rep = ROOT / "reports"; rep.mkdir(exist_ok=True)
    f = rep / f"calibration-{name}-{time.strftime('%Y%m%dT%H%M%S')}.json"
    f.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("звіт:", f.relative_to(ROOT))


if __name__ == "__main__":
    main()
