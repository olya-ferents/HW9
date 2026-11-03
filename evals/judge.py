""
import json
import http.client
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.request

RUBRIC_VERSION = "rubric.v1"
JUDGE_PROMPT_VERSION = "judge.v2"

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["PASS", "FAIL"]},
        "trigger": {"type": "string"},
        "evidence_turn": {"type": "integer"},
        "quote": {"type": "string"},
    },
    "required": ["verdict", "trigger", "evidence_turn", "quote"],
    "additionalProperties": False,
}

SYSTEM = """You are a quality judge for a bank support agent. You are given a
customer question, the agent's answer, and a rubric. Apply the rubric exactly
as written — do not add criteria of your own, and do not reward or punish
length, politeness or formatting.

For a human-handoff trigger, require an explicit affirmative commitment that
a human agent, colleague, or specialist will take over, follow up, or contact
the customer. Do not infer this from a case being assigned or sent to a team,
from a review being escalated, or from possible/conditional wording such as
"might contact".

Reply with ONE compact line of JSON and nothing else. Keep `trigger` to
at most 8 words:
{"verdict": "PASS" | "FAIL", "trigger": "<the rubric clause you applied>",
 "evidence_turn": <int>, "quote": "<verbatim words from the answer>"}

`quote` must be copied from the answer character for character. If nothing in
the answer supports the verdict, use an empty quote."""

_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _anthropic(prompt: str, model: str, temperature: float | None) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    body = {"model": model, "max_tokens": 800, "system": SYSTEM,
            "messages": [{"role": "user", "content": prompt}]}
    if temperature is not None:
        body["temperature"] = temperature
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=payload,
        headers={"Content-Type": "application/json", "x-api-key": key,
                 "anthropic-version": "2023-06-01"})
    delay = 2.0
    for attempt in range(4):
        try:
            with _opener.open(req, timeout=60) as r:
                data = json.loads(r.read().decode("utf-8"))
                return "".join(b.get("text", "") for b in data.get("content", []))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8")[:200]
            if "temperature" in detail and "temperature" in payload.decode("utf-8"):
                body.pop("temperature", None)
                payload = json.dumps(body).encode("utf-8")
                req = urllib.request.Request(
                    "https://api.anthropic.com/v1/messages", data=payload,
                    headers={"Content-Type": "application/json",
                             "x-api-key": key,
                             "anthropic-version": "2023-06-01"})
                continue
            if e.code in (429, 500, 502, 503, 529) and attempt < 3:
                time.sleep(delay)
                delay *= 2
                continue
            raise RuntimeError(f"judge {e.code}: {detail}") from e
        except (urllib.error.URLError, TimeoutError, ConnectionError,
                socket.timeout, http.client.HTTPException) as e:
            if attempt < 3:
                time.sleep(delay)
                delay *= 2
                continue
            raise RuntimeError(
                f"judge connection failed after retries: {e}") from e
    raise RuntimeError("judge unreachable")


def _ollama(prompt: str, model: str, temperature: float | None) -> str:
    ""
    base = os.environ.get("OLLAMA_URL", "http://host.docker.internal:11434")
    model = model.removeprefix("ollama:")
    output_format = os.environ.get("JUDGE_FORMAT", "json")
    if output_format not in ("json", "schema", "none"):
        raise ValueError(
            f"Invalid JUDGE_FORMAT: {output_format!r}; expected json, schema or none")
    body = {
        "model": model, "stream": False,
        "options": {"temperature": 0 if temperature is None else temperature},
        "system": SYSTEM, "prompt": prompt,
    }
    if output_format == "json":
        body["format"] = "json"
    elif output_format == "schema":
        body["format"] = JUDGE_SCHEMA
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        base.rstrip("/") + "/api/generate", data=payload,
        headers={"Content-Type": "application/json"})
    with _opener.open(req, timeout=180) as r:
        return json.loads(r.read().decode("utf-8")).get("response", "")


def _parse(raw: str) -> dict:
    ""
    match = re.search(r"\{.*\}", raw or "", re.S)
    if not match:
        raise ValueError(f"judge returned no JSON: {raw[:160]!r}")
    data = json.loads(match.group(0))
    verdict = str(data.get("verdict", "")).upper()
    if verdict not in ("PASS", "FAIL"):
        raise ValueError(f"judge returned a non-binary verdict: {verdict!r}")
    return {"verdict": verdict, "trigger": data.get("trigger", ""),
            "evidence_turn": data.get("evidence_turn", 0),
            "quote": data.get("quote", "")}


def judge_once(question: str, answer: str, rubric: str,
               model: str, temperature: float | None = None) -> dict:
    prompt = (f"CUSTOMER QUESTION:\n{question}\n\n"
              f"AGENT ANSWER:\n{answer}\n\n"
              f"RUBRIC:\n{rubric}\n\nJSON:")
    call = (_ollama if model.startswith("ollama:")
            or os.environ.get("JUDGE_BACKEND") == "ollama" else _anthropic)
    raw = call(prompt, model, temperature)
    try:
        data = json.loads(raw)
        if not isinstance(data, dict) or set(data) != set(JUDGE_SCHEMA["required"]):
            raise ValueError("judge JSON must contain exactly the four schema fields")
        if any(not isinstance(data[k], str) for k in ("verdict", "trigger", "quote")):
            raise ValueError("verdict, trigger and quote must be strings")
        if data["verdict"] not in ("PASS", "FAIL") or type(data["evidence_turn"]) is not int:
            raise ValueError("invalid verdict or evidence_turn")
    except ValueError as exc:
        return {"verdict": "ERROR", "quote": "", "raw": raw, "error": str(exc)}
    return {**data, "raw": raw, "error": None}


def judge(question: str, answer: str, rubric: str,
          model: str | None = None, temperature: float | None = None) -> dict:
    model = model or os.environ.get("JUDGE_MODEL") or "claude-haiku-5-5"
    prompt = (f"CUSTOMER QUESTION:\n{question}\n\n"
              f"AGENT ANSWER:\n{answer}\n\n"
              f"RUBRIC:\n{rubric}\n\nJSON:")
    call = (_ollama if model.startswith("ollama:")
            or os.environ.get("JUDGE_BACKEND") == "ollama" else _anthropic)
    for attempt in range(3):
        raw = call(prompt, model, temperature)
        try:
            out = _parse(raw)
            break
        except ValueError as e:
            if attempt == 2:
                raise ValueError(
                    f"judge returned invalid JSON after two retries: {e}") from e
            prompt += (
                "\n\nFORMAT CORRECTION: Your previous response was invalid. "
                "Return exactly one compact JSON object with string fields "
                '"verdict", "trigger", "quote" and integer field '
                '"evidence_turn". Keep trigger short and quote verbatim.')
    out["judge_model"] = model
    out["rubric_version"] = RUBRIC_VERSION
    return out


def verdict(question: str, answer: str, rubric: str, model: str):
    ""
    result = judge(question, answer, rubric, model)
    detail = (f"{result['verdict']} — {result['trigger']} "
              f"| quote: {result['quote'][:80]!r}")
    return result["verdict"] == "PASS", detail


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps(judge(
        "What is the dispute window for a duplicate charge?",
        "The window is 60 days from the transaction date.",
        "PASS when the answer states 60 days. FAIL otherwise."),
        ensure_ascii=False, indent=2))