"""
Claude Code 앞단 라우터: Groq의 소형 LLM으로 질문 난이도를 먼저 판단해
어떤 Claude 모델 / 노력 수준(effort)이 적당한지 추천합니다.

사용법
  python claude_router.py "질문"          # CLI로 바로 분석
  python claude_router.py                 # 대화형 입력
  python claude_router.py --hook          # Claude Code UserPromptSubmit 훅: 추천만 표시하고 질문은 그대로 진행
  python claude_router.py --hook --confirm  # 훅 확인 모드: 첫 전송은 멈추고 추천 표시, 같은 질문을 다시 보내면 진행

API 키: 환경 변수 GROQ_API_KEY 또는 같은 폴더의 .env 파일 (GROQ_API_KEY=gsk_...)
"""
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

from groq import Groq

# Groq에서 현재 제공되는 모델 중 빠르고 JSON 지시 이행이 좋은 순서.
# (llama-3.3-70b-versatile 은 Groq에서 내려가 404가 납니다)
ROUTER_MODELS = [
    os.environ.get("GROQ_ROUTER_MODEL", "openai/gpt-oss-20b"),
    "openai/gpt-oss-120b",
]

# Claude Code에서 /model, /effort 로 바로 쓸 수 있는 값들
VALID_MODELS = ["haiku", "sonnet", "opus"]
VALID_EFFORTS = ["low", "medium", "high", "xhigh", "max"]

SYSTEM_PROMPT = """
You are a prompt router placed in front of Claude Code (an agentic coding assistant).
Judge how hard the user's request is and recommend the cheapest Claude model and effort level
that will still do the job well. Do NOT answer the request itself.

[Model] (Claude Code /model alias)
- "haiku":  trivial lookups, short explanations, translations, one-line fixes, renaming, formatting.
- "sonnet": typical coding work - implementing a feature, fixing a bug in a few files, writing tests,
            refactoring a module, reviewing a diff, writing docs.
- "opus":   hard or high-stakes work - architecture/design across many files, subtle concurrency or
            performance bugs, security review, large migrations, ambiguous research-heavy tasks.

[Effort] (Claude Code /effort level = how much it thinks before acting)
- "low":    answer is obvious, no planning needed.
- "medium": some planning or a few steps.
- "high":   multi-step reasoning, debugging across files, careful verification.
- "xhigh":  very hard problem, many interacting parts, mistakes are costly.
- "max":    only for exceptionally hard, open-ended problems.

Bias toward the cheaper option when unsure. A short or vague request is usually haiku/sonnet + low/medium.

Return ONLY this JSON object:
{
  "model": "haiku | sonnet | opus",
  "effort": "low | medium | high | xhigh | max",
  "complexity": <integer 1-10>,
  "reasoning": "<1-2 sentences in Korean explaining the choice>"
}
""".strip()


def _load_dotenv() -> None:
    """GROQ_API_KEY 가 없으면 스크립트 옆 .env 에서 읽어옵니다 (외부 의존성 없이)."""
    if os.environ.get("GROQ_API_KEY"):
        return
    env_path = Path(__file__).with_name(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _normalize(raw: dict) -> dict:
    """LLM 출력값을 허용된 값으로 정리합니다 (대소문자/오타/누락 방어)."""
    model = str(raw.get("model", "")).lower().strip()
    if model not in VALID_MODELS:
        model = next((m for m in VALID_MODELS if m in model), "sonnet")

    effort = str(raw.get("effort", "")).lower().strip()
    if effort not in VALID_EFFORTS:
        effort = "medium"

    try:
        complexity = max(1, min(10, int(raw.get("complexity", 5))))
    except (TypeError, ValueError):
        complexity = 5

    return {
        "model": model,
        "effort": effort,
        "complexity": complexity,
        "reasoning": str(raw.get("reasoning", "")).strip(),
    }


def analyze_prompt_for_claude(user_query: str, timeout: float = 10.0) -> dict:
    """질문을 분석해 {model, effort, complexity, reasoning} 또는 {error} 를 반환합니다."""
    _load_dotenv()
    if not os.environ.get("GROQ_API_KEY"):
        return {"error": "GROQ_API_KEY 가 설정되지 않았습니다 (환경 변수 또는 .env)."}

    client = Groq(timeout=timeout, max_retries=1)
    last_error = None
    for router_model in dict.fromkeys(ROUTER_MODELS):  # 중복 제거, 순서 유지
        try:
            response = client.chat.completions.create(
                model=router_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Request to classify:\n<request>\n{user_query}\n</request>"},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_completion_tokens=1024,
            )
            result = _normalize(json.loads(response.choices[0].message.content))
            result["router_model"] = router_model
            return result
        except Exception as e:  # 모델 미존재/레이트리밋/JSON 파싱 실패 시 다음 모델로
            last_error = e
    return {"error": f"API 호출 중 오류 발생: {last_error}"}


def format_summary(result: dict) -> str:
    if "error" in result:
        return f"[라우터] {result['error']}"
    return (
        f"[라우터] 추천: /model {result['model']} · /effort {result['effort']} "
        f"(난이도 {result['complexity']}/10) - {result['reasoning']}"
    )


# 확인 모드에서 "멈췄던 질문"을 기억하는 파일 (세션별로 마지막 1개)
PENDING_FILE = Path(tempfile.gettempdir()) / "claude_router_pending.json"
PENDING_TTL_SEC = 600  # 10분 안에 같은 질문을 다시 보내면 통과


def _consume_pending(session_id: str, prompt_hash: str) -> bool:
    """같은 세션에서 직전에 멈춘 질문과 같으면 True (기록은 지움)."""
    try:
        pending = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    entry = pending.pop(session_id, None)
    PENDING_FILE.write_text(json.dumps(pending), encoding="utf-8")
    return bool(entry) and entry["hash"] == prompt_hash and time.time() - entry["time"] < PENDING_TTL_SEC


def _save_pending(session_id: str, prompt_hash: str) -> None:
    try:
        pending = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pending = {}
    pending[session_id] = {"hash": prompt_hash, "time": time.time()}
    PENDING_FILE.write_text(json.dumps(pending), encoding="utf-8")


def _emit(obj: dict) -> None:
    sys.stdout.buffer.write(json.dumps(obj, ensure_ascii=False).encode("utf-8"))
    sys.exit(0)


def run_hook(confirm: bool = False) -> None:
    """Claude Code UserPromptSubmit 훅.

    기본: 추천을 화면에 띄우고 질문은 그대로 진행.
    confirm: 처음 보낸 질문은 멈추고 추천을 보여줌 → /model, /effort 바꾼 뒤 같은 질문을 다시 보내면 진행.
    오류가 나면 어느 모드든 질문을 막지 않습니다.
    """
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
    except json.JSONDecodeError:
        payload = {}
    prompt = str(payload.get("prompt", "")).strip()
    session_id = str(payload.get("session_id", "default"))

    # 슬래시 명령이나 아주 짧은 입력은 분석 생략
    if not prompt or prompt.startswith("/") or len(prompt) < 5:
        sys.exit(0)

    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    if confirm and _consume_pending(session_id, prompt_hash):
        _emit({"systemMessage": "[라우터] 확인됨 - 진행합니다."})

    result = analyze_prompt_for_claude(prompt, timeout=8.0)
    summary = format_summary(result)

    if confirm and "error" not in result:
        _save_pending(session_id, prompt_hash)
        _emit({
            "decision": "block",
            "reason": (
                f"{summary}\n"
                f"→ 필요하면 /model {result['model']} , /effort {result['effort']} 로 바꾼 뒤 "
                f"같은 질문을 다시 보내세요 (↑ 키로 불러오기). 그대로 다시 보내면 현재 설정으로 진행합니다."
            ),
        })

    _emit({"systemMessage": summary})


def main() -> None:
    # Windows 콘솔에서 한글 깨짐 방지
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("=" * 60)
    print("      Claude 프롬프트 난이도 분석 & 모델 라우터 (Groq Powered)")
    print("=" * 60)

    if len(sys.argv) > 1:
        user_prompt = " ".join(sys.argv[1:])
    else:
        user_prompt = input("\nClaude에 전달할 질문을 입력하세요:\n> ")

    if not user_prompt.strip():
        print("질문 내용이 없습니다. 프로그램을 종료합니다.")
        sys.exit(1)

    print("\nGroq AI가 질문 수준을 분석 중입니다...")
    result = analyze_prompt_for_claude(user_prompt)

    if "error" in result:
        print(f"\n[오류] {result['error']}")
        sys.exit(1)

    print("\n" + "=" * 40)
    print("         [분석 결과 추천]")
    print("=" * 40)
    print(f"• 추천 모델      : {result['model']}   (Claude Code: /model {result['model']})")
    print(f"• 노력 수준      : {result['effort']}   (Claude Code: /effort {result['effort']})")
    print(f"• 난이도         : {result['complexity']}/10")
    print(f"• 판단 사유      : {result['reasoning']}")
    print(f"• 라우터 모델    : {result['router_model']}")
    print("=" * 40)


if __name__ == "__main__":
    if "--hook" in sys.argv[1:]:
        run_hook(confirm="--confirm" in sys.argv[1:])
    else:
        main()
