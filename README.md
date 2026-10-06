# Claude Router

Claude Code에 질문하기 **전에**, Groq의 빠른 소형 LLM이 질문 난이도를 먼저 분석해서
**어떤 Claude 모델과 노력 수준(effort)이 적당한지** 알려주는 도구입니다.

쉬운 질문에 비싼 모델을 쓰거나, 어려운 작업을 가벼운 모델로 시작했다가 다시 하는 일을 줄여 줍니다.

```
[라우터] 추천: /model sonnet · /effort medium (난이도 5/10) - React 로그인 기능 구현과 테스트 작성은 일반적인 개발 작업입니다.
```

## 동작 방식

```
질문 입력 ─▶ Groq (openai/gpt-oss-20b, 2~5초) ─▶ 모델·노력 추천 표시 ─▶ Claude Code 답변 시작
```

| 추천 모델 | 이럴 때 |
|---|---|
| `haiku` | 간단한 질문, 번역, 한 줄 수정, 이름 바꾸기, 포맷 정리 |
| `sonnet` | 기능 구현, 몇 개 파일에 걸친 버그 수정, 테스트 작성, 리팩터링 |
| `opus` | 여러 파일에 걸친 설계, 까다로운 동시성·성능 버그, 보안 검토, 대규모 마이그레이션 |

| 노력 수준 | 의미 |
|---|---|
| `low` | 답이 명확해서 계획이 필요 없음 |
| `medium` | 약간의 계획이나 몇 단계가 필요함 |
| `high` | 여러 단계의 추론, 파일 간 디버깅, 꼼꼼한 검증이 필요함 |
| `xhigh` | 얽힌 부분이 많고 실수 비용이 큰 아주 어려운 문제 |
| `max` | 예외적으로 어렵고 정답이 열려 있는 문제 |

## 설치

### 1. 필요한 것

- Python 3.8 이상
- Groq API 키: [console.groq.com/keys](https://console.groq.com/keys)에서 무료로 발급받을 수 있습니다.
- (자동 연결을 쓰려면) [Claude Code](https://claude.com/claude-code)

### 2. 내려받기 & 라이브러리 설치

```bash
git clone https://github.com/<your-id>/claude-router.git
```

```bash
cd claude-router
```

```bash
pip install -r requirements.txt
```

### 3. API 키 설정

`.env.example`을 `.env`로 복사하고 키를 넣습니다.

```bash
cp .env.example .env
```

```
GROQ_API_KEY=gsk_여기에_발급받은_키
```

> `.env`는 `.gitignore`에 들어 있어서 GitHub에 올라가지 않습니다. **키를 코드에 직접 쓰지 마세요.**
> 환경 변수 `GROQ_API_KEY`로 설정해도 됩니다.

## 사용법

### 방법 A: 터미널에서 직접 실행

큰 작업을 시작하기 전에 어떤 모델을 쓸지 미리 확인할 때 좋습니다.

```bash
python claude_router.py "React 앱에 로그인 기능 추가하고 테스트 작성해줘"
```

```
• 추천 모델      : sonnet   (Claude Code: /model sonnet)
• 노력 수준      : medium   (Claude Code: /effort medium)
• 난이도         : 5/10
• 판단 사유      : React 로그인 기능 구현과 테스트 작성은 일반적인 프론트엔드 개발 작업이며...
• 라우터 모델    : openai/gpt-oss-20b
```

인자 없이 `python claude_router.py`만 실행하면 질문을 입력하라는 창이 뜹니다.

### 방법 B: Claude Code에 자동 연결 (Hook)

Claude Code에 질문할 때마다 자동으로 추천이 표시되게 합니다.

**특정 프로젝트에서만 쓰기:** 그 프로젝트 폴더에 `.claude/settings.json`을 만듭니다.
**모든 프로젝트에서 쓰기:** `~/.claude/settings.json`(Windows는 `C:\Users\<사용자>\.claude\settings.json`)에 추가합니다.

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python /절대/경로/claude-router/claude_router.py --hook",
            "timeout": 15
          }
        ]
      }
    ]
  }
}
```

- `command`에는 **`claude_router.py`의 절대 경로**를 넣으세요.
  - Windows 예: `python C:/tools/claude-router/claude_router.py --hook`
  - macOS/Linux 예: `python3 /Users/me/claude-router/claude_router.py --hook`
- 이미 `settings.json`에 다른 설정이 있으면 `"hooks"` 부분만 합쳐 넣으세요.
- 설정 후 Claude Code를 다시 시작하면 적용됩니다.

이후 Claude Code에서 질문하면 이렇게 표시됩니다:

```
[라우터] 추천: /model opus · /effort high (난이도 9/10) - 대규모 아키텍처 재구성이 필요합니다.
```

추천을 따르려면 Claude Code에 `/model opus`, `/effort high`처럼 입력하면 됩니다.

#### 확인 모드 (`--confirm`, 추천)

기본 Hook은 추천을 띄우는 **동시에 질문이 현재 모델로 바로 시작**됩니다.
모델을 바꿀 기회를 갖고 싶다면 `command` 끝에 `--confirm`을 붙이세요.

```json
"command": "python /절대/경로/claude-router/claude_router.py --hook --confirm"
```

1. 질문을 보내면 **Claude가 시작하지 않고** 추천만 표시됩니다.
2. 필요하면 `/model`, `/effort`로 바꿉니다.
3. `↑` 키로 같은 질문을 불러와 다시 보내면 그대로 진행됩니다. 추천을 무시하고 싶을 때도 같은 질문을 다시 보내면 됩니다.

- 같은 질문을 10분 안에 다시 보내야 통과합니다. 10분이 지나면 다시 분석합니다.
- Groq 오류나 키 누락 시에는 멈추지 않고 바로 진행합니다.

## Ubuntu / WSL에서 쓰기

Ubuntu(또는 Windows의 WSL)에서 Claude Code를 쓴다면 아래처럼 설정합니다.
Ubuntu 24.04부터는 시스템 Python에 `pip install`이 막혀 있어서 전용 가상환경을 만들어 씁니다.

> **WSL 주의:** `python` 대신 `python3`를 쓰고, Windows 경로 `C:/...`는 `/mnt/c/...`로 바꿔야 합니다.
> 저장소를 Windows 폴더(예: `C:\tools\claude-router`)에 받았다면 아래의 `ROUTER_DIR`을 `/mnt/c/tools/claude-router`로 지정하세요.
> 이렇게 하면 코드와 `.env`를 Windows와 WSL이 함께 씁니다.

### 1. 가상환경 만들고 설치

먼저 `ROUTER_DIR`에 **`claude_router.py`가 실제로 있는 폴더**를 넣습니다. 아래 둘 중 내 상황에 맞는 하나만 실행하세요.

```bash
ROUTER_DIR="$HOME/claude-router"   # Ubuntu 홈에 git clone 한 경우
```

```bash
ROUTER_DIR="/mnt/c/tools/claude-router"   # Windows 폴더(C:\tools\claude-router)에 받은 경우
```

경로가 맞는지 확인합니다. 파일 목록이 나오지 않으면 경로가 틀린 것입니다.

```bash
ls "$ROUTER_DIR/claude_router.py" "$ROUTER_DIR/requirements.txt"
```

```bash
python3 -m venv ~/.claude-router-venv && ~/.claude-router-venv/bin/pip install -r "$ROUTER_DIR/requirements.txt"
```

`python3 -m venv`에서 오류가 나면 먼저 `sudo apt install python3-venv`를 실행하세요.

### 2. `claude-router` 명령 만들기

```bash
mkdir -p ~/.local/bin && printf '#!/usr/bin/env bash\nexec "$HOME/.claude-router-venv/bin/python" "%s/claude_router.py" "$@"\n' "$ROUTER_DIR" > ~/.local/bin/claude-router && chmod +x ~/.local/bin/claude-router
```

터미널을 새로 연 뒤 확인합니다:

```bash
claude-router "파이썬에서 리스트 정렬하는 법"
```

### 3. Claude Code에서 사용

**직접 실행:** Claude Code 입력창에서 `!`를 앞에 붙이면 셸 명령으로 실행됩니다.

```
! claude-router "강의자료.pdf 39~42쪽을 읽고 요약해줘"
```

**자동 실행 (Hook):** `~/.claude/settings.json`에 추가합니다.

```json
{
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [ { "type": "command", "command": "claude-router --hook", "timeout": 15 } ] }
    ]
  }
}
```

설정 후 Claude Code를 다시 시작하세요. `claude-router: command not found`가 뜨면 터미널을 새로 열고 `claude`를 다시 실행하면 됩니다.

## 알아두면 좋은 점

- **추천만 하고 모델을 자동으로 바꾸지는 않습니다.** Hook은 Claude Code의 모델을 바꿀 수 없어서, 직접 `/model`, `/effort`를 입력해야 합니다. 바꿀 시간을 가지려면 [확인 모드](#확인-모드---confirm-추천)를 쓰세요.
- **오류가 나도 질문을 막지 않습니다.** Groq 오류, 키 누락, 시간 초과가 생기면 질문은 그대로 Claude에 전달됩니다.
- `/help` 같은 슬래시 명령이나 5자 미만의 짧은 입력은 분석하지 않습니다.
- 질문 내용이 Groq API로 전송됩니다. 민감한 코드나 정보를 다룬다면 이 점을 고려하세요.
- 질문마다 응답이 2~5초 늦어집니다.

## 설정 변경

| 환경 변수 | 기본값 | 설명 |
|---|---|---|
| `GROQ_API_KEY` | (필수) | Groq API 키 |
| `GROQ_ROUTER_MODEL` | `openai/gpt-oss-20b` | 분석에 쓸 Groq 모델. 실패하면 `openai/gpt-oss-120b`로 자동 전환 |

추천 기준을 바꾸고 싶으면 `claude_router.py`의 `SYSTEM_PROMPT`를 수정하세요.

## 문제 해결

| 증상 | 해결 |
|---|---|
| `GROQ_API_KEY 가 설정되지 않았습니다` | `.env` 파일이 `claude_router.py`와 같은 폴더에 있는지 확인 |
| `model_not_found` 오류 | Groq에서 모델이 내려갔을 수 있습니다. [Groq 모델 목록](https://console.groq.com/docs/models)을 확인하고 `GROQ_ROUTER_MODEL`을 바꾸세요 |
| Hook에서 아무것도 안 뜸 | `command`의 경로가 절대 경로인지, 터미널에서 그 명령이 실행되는지 확인 |
| `python`을 찾을 수 없음 | macOS/Linux는 `python3`, Windows는 `py`로 바꿔 보세요 |
| WSL에서 `No such file` | `C:/...` 경로를 `/mnt/c/...`로 바꾸세요 |
| `externally-managed-environment` 오류 | Ubuntu 24.04의 pip 제한입니다. [Ubuntu / WSL에서 쓰기](#ubuntu--wsl에서-쓰기)처럼 가상환경을 쓰세요 |
| `claude-router: command not found` | 터미널을 새로 열거나 `source ~/.profile` 실행 |
| 한글이 깨짐 | Python 3.8 이상인지 확인 |

Hook 동작은 아래 명령으로 직접 테스트할 수 있습니다:

```bash
echo '{"prompt":"동시성 문제로 가끔 데드락 걸리는 버그 고쳐줘"}' | python claude_router.py --hook
```

## 파일 구성

```
claude-router/
├── claude_router.py   # 라우터 본체 (CLI + Hook 모드)
├── requirements.txt   # groq
├── .env.example       # API 키 템플릿
├── .gitignore         # .env 제외
└── README.md
```

## License

MIT
