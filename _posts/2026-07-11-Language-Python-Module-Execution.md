---
title: "[Python] python -m과 모듈 실행: 어느 파이썬의 무엇이 실행되는가"
excerpt: CI 스크립트에서 만난 python3 -m pytest를 계기로, 파이썬 실행 방식에 따라 sys.path와 import, 인터프리터 선택이 어떻게 달라지는지 정리하고 직접 확인해 보자.
categories:
  - Language
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Python
  - python-m
  - sys.path
  - pytest
  - module
  - import
---

<br>

# TL;DR

- `python3 -m pytest`는 "지금 부른 이 `python3` 인터프리터에 설치된 `pytest` 모듈(module)을 스크립트처럼 실행하라"는 뜻이다. 반면 `pytest` 단독 실행은 `PATH`에서 찾은 **런처 실행 파일**을 실행하는 것이고, 그 런처의 셔뱅(shebang)은 설치 시점의 인터프리터에 고정되어 있다
- 파이썬 코드를 실행하는 방식은 하나가 아니고 — 경로 실행(`python3 script.py`), 모듈 실행(`python3 -m module`), 문자열 실행(`python3 -c '...'`) — **어떤 방식으로 실행했느냐에 따라 인터프리터가 `sys.path` 맨 앞에 자동으로 넣어 주는 경로가 다르다**. 경로 실행은 스크립트가 있는 디렉터리, `-m`은 현재 작업 디렉터리(cwd), `-c`는 `''`(cwd 의미)를 넣고, Python 3.11+의 `-P`(safe path)는 이 자동 삽입을 끈다. 이 차이가 로컬 모듈 import의 성패를 가른다
- 코드와 테스트가 같은 폴더에 있는 레이아웃에서는 `-m` 없이 `pytest`만 실행해도 로컬 import가 성공한다. pytest가 자체적으로 테스트 파일의 기준 디렉터리를 `sys.path` 맨 앞에 삽입하기 때문이다. `-m`이 import 성패를 가르는 건 `tests/` 분리 레이아웃 같은 경우다 — 실습으로 직접 확인했다
- 따라서 `-m`의 언제나 성립하는 효용은 import 구제가 아니라 **인터프리터와 패키지의 짝을 고정**하는 것이다. CI에서 `python3 -m pytest`를 쓰는 관행의 핵심 이유다


<br>

# 들어가며

KodeKloud Engineering의 [MLOps 100 Day Challenge](https://kodekloud.com/100-days-of-mlops)를 진행하면서 셸 기반 CI 실습을 하다가, 테스트 단계에서 이런 명령을 만났다.

```bash
# CI 스크립트의 테스트 단계
python3 -m pytest app/
```

pytest를 실행하고 싶으면 `pytest app/`이라고 치면 될 텐데, 왜 `python3 -m`으로 감싸는 것일까. Python을 처음 배운 이후로 실무 개발, 특히 CI 설정이나 문서에서도 자주 사용해 오던 형태인데, 정작 제대로 정리해 본 적이 없던 듯하다. 이를 계기로, 위의 명령 하나를 축으로 하여 세 가지 질문에 답해 보고자 한다.

- `-m`은 정확히 무슨 일을 하는가
- `pytest`와 `python3 -m pytest`는 무엇이 다른가
- 여러 파이썬이 깔린 환경에서, 지금 실행되는 것은 **어느 파이썬의 pytest**인가

<br>

# 모듈과 패키지

## 모듈

용어부터 잡고 가자. 파이썬에서 **모듈(module)은 `.py` 파일 하나**다. [파이썬 공식 튜토리얼](https://docs.python.org/3/tutorial/modules.html)의 정의 또한 이와 같다 — 모듈은 파이썬 정의와 문장이 담긴 파일이다.

> A module is a file containing Python definitions and statements.

그 파일이 어떤 경로로 시스템에 들어왔는지는 중요하지 않다. 파이썬과 함께 배포되는 표준 라이브러리의 파일이든, pip으로 설치한 서드파티 패키지의 파일이든, 내가 방금 에디터에서 저장한 `hello.py`든, 인터프리터에게는 전부 똑같은 모듈이고 `import hello`처럼 **import의 단위**가 된다. 모듈이 되기 위한 별도의 자격 요건(특정 파일이나 함수의 존재 등)은 없다. 자주 혼동되는 `__main__`은 파일이 아니라 이름인데, 이 구분은 [실행 방식 해부](#실행-방식-해부)에서 후술한다.

## 패키지

여러 모듈이 디렉터리로 묶이면 **패키지(package)**라고 부른다. 디렉터리에 `__init__.py`를 두어 "이 폴더는 패키지다"라고 표시하는 것이 기본형이고, 패키지 안의 모듈은 `import mypkg.tool`처럼 점 표기로 접근한다. 즉 관계는 단순하다 — 파일 하나 = 모듈, 모듈을 담는 디렉터리 = 패키지.

```
hello.py            # 모듈 hello - 내가 방금 만든 파일도 즉시 모듈이다
mypkg/              # 패키지 mypkg
├── __init__.py     # "이 디렉터리는 패키지" 표시 (import mypkg 시 실행됨)
└── tool.py         # 모듈 mypkg.tool
```

## 패키지 설치의 두 산출물

pytest도 결국 누군가 만들어 놓은 파이썬 패키지다. 그리고 `pip install <패키지>`가 하는 일은 일반론으로 두 가지다.

1. **패키지 코드 본체**를 인터프리터의 `site-packages` 디렉터리에 복사한다: `import`로 쓸 수 있게 된다
2. 패키지가 배포 메타데이터에 **console_scripts 진입점(entry point)**을 선언해 놓았다면, 그 선언대로 `bin/` 디렉터리에 **런처 실행 파일**을 생성한다: 터미널 명령으로 쓸 수 있게 된다

첫 번째 산출물의 설치 위치인 `site-packages`는 **인터프리터마다 각자 갖는 디렉터리**라는 점이 중요하다. 즉, 이 위치는 어디에나 하나 있는 전역 폴더가 아니라는 것이다. 파이썬 인터프리터는 자기가 설치된 위치(`sys.prefix`) 아래 `lib/pythonX.Y/site-packages`를 서드파티 패키지 보관소로 쓴다. 예컨대 뒤의 실습에서 쓸 `python:3.12-slim` 도커 이미지는 파이썬이 `/usr/local`에 설치되어 있으므로, 그 파이썬의 보관소는 `/usr/local/lib/python3.12/site-packages`가 된다. venv를 만들면 venv 디렉터리 안에 또 하나의 site-packages가 생긴다. "인터프리터마다 각자의 패키지 보관소"라는 이 구조가, 글 후반부에서 답하게 될 "어느 파이썬의 pytest인가"라는 질문의 뿌리다.

두 번째 산출물 역시 **모든 패키지에 생기는 게 아니라는 점**이 중요하다. CLI를 제공하는 패키지(pytest, pip, black 등)만 console_scripts를 선언하고, `requests`처럼 import해서만 쓰는 라이브러리는 선언 자체가 없어 런처도 생기지 않는다.

pytest를 예시로, 앞서 언급한 `python:3.12-slim` 이미지에서 실제 설치 직후의 모습을 보면 이렇다.

> *참고*: 아래 디렉터리 구조와 entry_points.txt 내용은 실습 컨테이너에서 `pip install pytest` 직후를 실측한 것이다. 재현 명령과 전체 출력은 [실험 C](#실험-c-pytest-런처의-정체와-인터프리터-결속)의 C-0 단계에 있다.

```bash
/usr/local/lib/python3.12/site-packages/    # 인터프리터의 패키지 설치 위치
├── pytest/                     # import pytest가 찾는 패키지 코드 본체
│   ├── __init__.py
│   └── __main__.py             # python3 -m pytest의 진입점 (후술)
├── _pytest/                    # 실제 구현이 들어 있는 내부 패키지
├── pytest-9.1.1.dist-info/     # 배포 메타데이터
│   └── entry_points.txt        # "pytest라는 명령을 만들어라"는 선언
└── (iniconfig, pluggy, ... 의존 패키지들)

/usr/local/bin/
└── pytest                      # 위 선언대로 pip이 생성한 런처 실행 파일
```

런처 생성의 근거가 되는 선언도 파일로 직접 확인할 수 있다.

```ini
# pytest-9.1.1.dist-info/entry_points.txt - 런처 생성 지시서
# "pytest라는 명령을 만들고, 실행되면 _pytest.config의 _console_main을 호출해라"
[console_scripts]
py.test = _pytest.config:_console_main
pytest = _pytest.config:_console_main
```

같은 컨테이너에서 `requests`를 설치하고 dist-info를 열어 보면 `entry_points.txt` 자체가 없다 — 그래서 `requests`라는 터미널 명령도 없다.

`pytest app/`과 `python3 -m pytest app/`이 갈라지는 지점이 바로 여기다. 전자는 두 번째 산출물(런처)을, 후자는 첫 번째 산출물(패키지 코드)을 직접 겨냥한다.

<br>

# 실행 방식 해부

"파이썬 코드를 실행한다"는 한 문장 안에는 겉보기가 다른 여러 방식이 숨어 있다. 이 글에서 다루는 것은 네 가지다.

- **경로 실행** `python3 script.py`: 인터프리터에 파일 경로를 줘서 실행
- **모듈 실행** `python3 -m module`: 인터프리터에 모듈 이름을 줘서 실행
- **런처 실행 파일** `pytest`: 파이썬을 직접 부르지 않고, 설치된 터미널 명령을 실행
- **문자열 실행** `python3 -c '...'`: 코드 문자열을 명령 인자로 직접 줘서 실행 (REPL도 이 부류다)

결론부터 말하면, 차이는 **"무엇을, 어디서 찾아, 실행하는가"**다.

| 명령 | 무엇을 | 어디서 찾나 |
| --- | --- | --- |
| `python3 script.py` | 파일 경로 | 파일 시스템 |
| `python3 -m module` | 모듈 이름 | `sys.path` |
| `pytest` | 실행 파일 이름 | 셸의 `PATH` |
| `python3 -c '...'` | 코드 문자열 | 찾지 않음 (인자로 직접 받음) |

이 글의 주인공은 앞의 셋이라 절을 나눠 뜯어 본다. 문자열 실행은 찾을 대상 자체가 없는 단순한 경우지만, 뒤의 `sys.path` 비교에서 나머지 방식들과 나란히 등장하므로 여기서 함께 세워 두었다.

## 경로 실행: python3 script.py

가장 익숙한 형태다. 인터프리터에게 **파일 경로**를 주면, 파이썬은 그 파일을 읽어 `__main__`이라는 이름의 모듈로 실행한다. 파일 안에서 `__name__` 값이 `"__main__"`이 되는 이유다.

```python
# 직접 실행하면 __name__ == "__main__", import되면 __name__ == 모듈 이름
if __name__ == "__main__":
    main()
```

## 모듈 실행: python3 -m module

`-m`은 파이썬 공식 문서 기준으로 *run library module as a script* 옵션이다. 파일 경로가 아니라 **모듈 이름**을 받는다는 점이 핵심이다.

```bash
python3 hello.py    # 파일 경로를 실행 - "이 파일을 실행해라"
python3 -m hello    # 모듈 이름을 실행 - "hello라는 모듈을 sys.path에서 찾아 실행해라"
```

동작을 정밀하게 쓰면 이렇다.

- 인터프리터가 `sys.path`를 뒤져 해당 이름의 모듈을 찾는다 (내부적으로 표준 라이브러리 `runpy`가 담당한다)
- 찾은 대상이 **단일 모듈**이면 그 파일을 `__name__ == "__main__"`으로 실행한다
- 찾은 대상이 **패키지**면 그 안의 `__main__.py`를 진입점으로 실행한다. `python3 -m pytest`가 동작하는 것도 pytest 패키지 안에 `__main__.py`가 있기 때문이다
- 실행 전에 **현재 작업 디렉터리(cwd)를 `sys.path` 맨 앞에 추가**한다 — `-m`의 숨은 효과이자, 뒤에서 다룰 import 동작의 열쇠다

패키지/모듈에 따라 진입점이 어떻게 달라지는지는 아래 [실습으로 확인](#실습으로-확인) 섹션의 실험 D에서 실측한다.

## 런처 실행 파일: pytest

`pytest`라고만 치면 파이썬은 아직 등장하지 않는다. **셸**이 `PATH` 환경변수의 디렉터리들을 순서대로 뒤져 `pytest`라는 실행 파일을 찾는다. 이 파일의 정체는 [모듈과 패키지](#모듈과-패키지)에서 본 entry_points.txt 선언대로 pip이 설치 시점에 생성한 몇 줄짜리 파이썬 스크립트고, 첫 줄 [셔뱅(shebang)]({% post_url 2022-06-03-Dev-fcgiwrap-python %}#shebang) — 스크립트 첫 줄에 그 파일을 해석할 인터프리터 경로를 명시하는 문자열 — 에 **설치 당시의 인터프리터 절대 경로**가 박혀 있다.

```python
#!/usr/local/bin/python3        <- 설치 시점에 결정된 인터프리터
# pip이 console_scripts entry point로 생성한 런처
import sys
from _pytest.config import _console_main
...
```

즉 `pytest`를 치는 순간 어느 파이썬이 쓰일지는 이미 **설치 시점에** 결정되어 있고, `PATH`는 여러 런처 중 어느 것이 잡히느냐만 결정한다. 이 구조는 실험 C에서 파일을 직접 열어 확인한다.

## `__name__`과 `__main__`

네 방식 모두 결국 어떤 파이썬 코드를 실행하는데, 파이썬은 실행되는 모든 모듈에 이름을 붙이고 그 이름을 `__name__` 변수에 담는다. 규칙은 하나뿐이다. import되어 불려 온 모듈은 자기 이름(`hello.py`면 `"hello"`)을 받고, **프로그램의 진입점으로 실행되는 코드는 `"__main__"`이라는 특별한 이름을 받는다**. `if __name__ == "__main__":` 관용구는 이 규칙을 이용해 "import될 때는 실행하지 말고, 진입점으로 실행될 때만 실행해라"를 표현하는 것이다.

실행 방식별로 무엇이 `"__main__"`이라는 이름을 받는지 정리하면 다음과 같다.

| 실행 방식 | `"__main__"`이 되는 것 |
| --- | --- |
| `python3 script.py` | `script.py` 파일 |
| `python3 -m module` | 그 모듈 파일 |
| `python3 -m package` | 패키지 안의 `__main__.py` 파일 |
| `pytest` (런처) | 런처 스크립트 파일 |
| `python3 -c '...'` | 넘긴 코드 문자열 |

여기서 헷갈리기 쉬운 것은 **이름 `"__main__"`과 파일 `__main__.py`가 서로 다른 존재**라는 점이다. `if __name__ == "__main__":`의 `"__main__"`은 파일을 가리키는 게 아니라, 위 규칙에 따라 `__name__` 변수에 들어오는 값이다. 어떤 `.py` 파일이든 진입점으로 실행되면 이 값을 받으므로, 모듈이 이 값을 받기 위해 특별한 파일을 갖출 필요는 없다. 반면 `__main__.py`라는 **파일**이 등장하는 경우는 딱 하나, 패키지를 `-m`으로 실행할 때다. 패키지는 여러 파일의 묶음이라 "어느 파일부터 실행할지"를 정해 줘야 하는데, 그 약속된 자리가 `__main__.py`다. 물론 이 파일도 진입점으로 실행되는 동안에는 `__name__` 값으로 `"__main__"`을 받는다.

<br>

# sys.path와 import

`-m`의 숨은 효과를 이해하려면 `sys.path`가 무엇인지부터 봐야 한다. 파이썬은 `import 무언가`를 만나면 아무 데서나 찾지 않고, **정해진 디렉터리 목록을 순서대로** 뒤진다. 그 목록이 `sys.path`다.

## sys.path[0] 초기화 규칙

목록의 맨 앞(`sys.path[0]`)에 무엇이 들어가는지가 실행 방식마다 다르다. 이게 이 글에서 가장 중요한 표다.

| 실행 방식 | `sys.path[0]` |
| --- | --- |
| `python3 script.py` | **스크립트가 있는 디렉터리** (cwd가 아니다) |
| `python3 -m module` | **현재 작업 디렉터리(cwd)** |
| `python3 -c '...'`, REPL | `''` (빈 문자열 — import 시점의 cwd로 해석) |
| 위 각각 + `-P` (3.11+) | 자동 삽입 없음 (safe path 모드) |

특히 경로 실행과 `-m`의 차이를 눈여겨보자. `python3 /somewhere/script.py`를 어디서 실행하든 `sys.path[0]`은 `/somewhere`다. 반면 `python3 -m module`은 **지금 서 있는 곳**이 들어간다. 그래서 `-m`은 "cwd 기준의 로컬 코드를 import 가능하게 만든 채로 모듈을 실행"하는 효과를 낸다. Python 3.11부터는 이 자동 삽입이 보안 관점에서 문제가 될 수 있어(악의적 파일이 표준 라이브러리를 가로채는 시나리오) `-P` 옵션과 `PYTHONSAFEPATH` 환경변수로 끌 수 있다.

## 경로 인자와 import 대상의 구분

처음에 헷갈렸던 지점이다. `python3 -m pytest app/`에는 `app`이 두 번 등장하는데, 둘은 **완전히 다른 일**이다.

```bash
python3 -m pytest app/
#          ^^^^^^ sys.path에서 찾는 모듈 이름
#                 ^^^^ pytest에 넘기는 파일 시스템 경로 인자
```

- 명령 인자 `app/`은 pytest에게 "이 폴더에서 테스트 파일을 찾아라"라고 알려 주는 **파일 시스템 경로**다. 그냥 디렉터리 경로라서 `sys.path`와 무관하게 찾을 수 있다. 이걸 위해 `-m`이 필요한 게 아니다
- 테스트 코드 안의 `from app import add`는 **파이썬 import**다. 여기서 `app`은 경로가 아니라 모듈 이름이고, 인터프리터가 `sys.path`에서 찾아야 한다

pytest가 테스트 파일을 *발견*하는 것(경로 탐색)과, 발견한 테스트 파일이 *import에 성공*하는 것(모듈 탐색)은 별개의 단계다. `-m`이 영향을 주는 건 후자뿐이다.

## pytest의 sys.path 삽입

그런데 여기서 통념 하나를 짚어야 한다. "`-m` 없이 `pytest`만 실행하면 cwd가 `sys.path`에 없으니 로컬 import가 깨진다"는 설명이 흔한데, **항상 성립하지는 않는다**. pytest는 기본 import 모드(`prepend`)에서 테스트 파일을 import하기 전에 자체적으로 `sys.path`를 조작한다 — 테스트 파일 위치에서 위로 올라가며 `__init__.py`가 없는 첫 디렉터리(기준 디렉터리, basedir)를 찾아 `sys.path` 맨 앞에 삽입한다.

그래서 레이아웃에 따라 결과가 갈린다.

- **코드와 테스트가 같은 폴더** (`app/app.py` + `app/test_app.py`, `__init__.py` 없음): 기준 디렉터리가 `app/` 자신이라 `import app`이 pytest의 삽입만으로 해결된다 → `-m` 없이도 통과
- **`tests/` 분리 레이아웃** (`proj/mylib.py` + `proj/tests/test_mylib.py`): 기준 디렉터리가 `tests/`라서 프로젝트 루트는 `sys.path`에 들어가지 않는다 → `import mylib`이 실패한다. 이때 `python3 -m pytest`로 실행하면 cwd(프로젝트 루트)가 `sys.path`에 들어가 성공한다

이 갈림은 실험 B에서 두 레이아웃 모두 실측으로 확인한다.

## 어느 파이썬의 pytest인가

한 컴퓨터에 파이썬은 여러 개 있을 수 있다. 시스템 기본 `python3`, 프로젝트 가상환경(virtual environment)의 파이썬, conda 환경의 파이썬. 그리고 [모듈과 패키지](#모듈과-패키지)에서 본 대로 `site-packages`는 인터프리터마다 각자 갖는 보관소이므로, **pytest도 인터프리터 수만큼 따로 설치될 수 있고 버전도 제각각일 수 있다**.

- `pytest`로 실행하면: `PATH`에서 먼저 걸리는 런처가 실행되고, 그 런처의 셔뱅에 박힌 인터프리터가 쓰인다 → 내가 의도한 파이썬이 아닐 수 있다
- `python3 -m pytest`로 실행하면: **방금 부른 그 `python3`에 설치된 pytest**가 실행된다 → 인터프리터와 pytest의 짝이 어긋날 수 없다

한 가지 주의할 점은, `python3`라는 이름 자체도 `PATH`로 해석된다는 것이다. venv를 활성화하면 `python3`가 venv의 인터프리터를 가리키므로 `python3 -m pytest`는 venv의 pytest를 실행한다. `-m`이 보장하는 건 "절대적인 어떤 파이썬"이 아니라 **"내가 지정한 인터프리터와 그 패키지의 결속"**이다. CI에서 인터프리터를 절대 경로나 고정된 이름으로 부르고 `-m`으로 도구를 실행하면, 어느 환경의 어떤 버전이 도는지 예측 가능해진다. `python3 -m pytest`가 CI 관행이 된 이유다.

<br>

# 실습

이론으로 확인한 부분이 어떻게 동작하는지 실제로 확인해 보자. 

<br>

실습 코드 전체는 [`_labs/python-module-execution/`](https://github.com/sirzzang/sirzzang.github.io/tree/master/_labs/python-module-execution)에 있다. 로컬 파이썬 환경을 건드리지 않기 위해 `python:3.12-slim` 도커 이미지 안에서 실행했고, `run.sh` 하나로 전체 실험이 재현된다.

```bash
# 호스트에서 실행 - 컨테이너를 띄워 lab.sh(실험 본체)를 돌린다
docker run --rm -v "$PWD":/lab -w /lab python:3.12-slim bash lab.sh
```

<br>

디렉터리 구성은 다음과 같다.

```
python-module-execution/
├── app/                  # 코드와 테스트가 같은 폴더에 있는 레이아웃 (실험 B)
│   ├── app.py
│   └── test_app.py
├── proj/                 # tests/ 분리 레이아웃 (실험 B-4)
│   ├── mylib.py
│   └── tests/
│       └── test_mylib.py
├── mypkg/                # -m 패키지 실행 (실험 D)
│   ├── __init__.py
│   ├── __main__.py
│   └── tool.py
├── show_syspath.py       # sys.path 출력 스크립트 겸 모듈 (실험 A)
├── lab.sh                # 컨테이너 안에서 실험 A~D를 순서대로 실행
└── run.sh                # 호스트에서 컨테이너를 띄우는 래퍼
```

## 실험 A: 실행 방식별 sys.path[0]

**검증할 명제** — `sys.path[0]`은 경로 실행이면 스크립트 디렉터리, `-m`이면 cwd, `-c`면 `''`이고, `-P`는 삽입을 끈다.

실험 도구는 자신이 어떻게 실행됐는지 출력하는 한 파일짜리 모듈이다.

```python
# show_syspath.py - 스크립트로도, -m 모듈로도 실행할 수 있다
import os
import sys

print(f"__name__    = {__name__}")
print(f"cwd         = {os.getcwd()}")
print(f"sys.path[0] = {sys.path[0]!r}")
```

핵심은 **cwd와 스크립트 위치를 분리**하는 것이다. `/tmp`에 서서 `/lab`의 스크립트를 실행해 본다.

```shell
# 경로 실행 - cwd는 /tmp인데 sys.path[0]은 스크립트가 있는 /lab
/tmp# python3 /lab/show_syspath.py
__name__    = __main__
cwd         = /tmp
sys.path[0] = '/lab'

# -m 실행 (cwd = /lab) - sys.path[0]은 cwd
/lab# python3 -m show_syspath
__name__    = __main__
cwd         = /lab
sys.path[0] = '/lab'

# -m 실행 (cwd = /tmp) - cwd에 모듈이 없으므로 아예 못 찾는다
/tmp# python3 -m show_syspath
/usr/local/bin/python3: No module named show_syspath

# -c 실행 - 빈 문자열 (cwd 의미)
/lab# python3 -c 'import os, sys; print(f"cwd={os.getcwd()}, sys.path[0]={sys.path[0]!r}")'
cwd=/lab, sys.path[0]=''
```

`-P`(safe path)를 붙이면 같은 스크립트 실행에서도 자동 삽입이 사라진다.

```shell
# -P: 스크립트 디렉터리가 삽입되지 않아 sys.path[0]이 표준 라이브러리 경로
/lab# python3 -P show_syspath.py
__name__    = __main__
cwd         = /lab
sys.path[0] = '/usr/local/lib/python312.zip'

# -P + -m: cwd가 sys.path에 없으므로 cwd의 모듈을 못 찾는다
/lab# python3 -P -m show_syspath
/usr/local/bin/python3: No module named show_syspath
```

**판정** — 명제 그대로 확인됐다. 경로 실행은 "그 파일이 있는 곳", `-m`은 "내가 서 있는 곳"이 import 검색 경로에 들어간다.

## 실험 B: pytest와 -m의 import 동작

**검증할 명제** — 코드와 테스트가 같은 폴더에 있으면 `-m` 없이도 import가 성공하고(pytest의 자체 삽입), `tests/` 분리 레이아웃에서는 `-m` 여부가 성패를 가른다.

첫 번째 레이아웃은 CI에서 만난 구조를 외부 의존성 없이 재구성한 것이다.

```python
# app/app.py - 순수 파이썬 함수만 있는 최소 앱 모듈
def add(a, b):
    """두 수를 더한다."""
    return a + b


def greet(name):
    """인사 문자열을 만든다."""
    return f"hello, {name}"
```

```python
# app/test_app.py - 원 레이아웃과 같은 `from app import ...` 형태를 유지
# 실행 시점의 sys.path와 실제 import된 app의 파일 경로를 출력한다
import sys

from app import add, greet


def test_syspath_and_module_origin():
    import app
    print()
    print(f"[test] sys.path[:3] = {sys.path[:3]}")
    print(f"[test] app module   = {app.__file__}")
    assert add(1, 2) == 3


def test_greet():
    assert greet("world") == "hello, world"
```

`-m`을 붙였을 때와 안 붙였을 때를 모두 실행해 보면, **둘 다 통과한다**.

```shell
# -m 실행: sys.path = [pytest가 삽입한 /lab/app, -m이 삽입한 cwd(/lab), ...]
/lab# python3 -m pytest app/ -q -s
[test] sys.path[:3] = ['/lab/app', '/lab', '/usr/local/lib/python312.zip']
[test] app module   = /lab/app/app.py
2 passed in 0.01s

# -m 없이 실행: cwd 대신 런처가 있는 /usr/local/bin이 보이지만, 역시 통과
/lab# pytest app/ -q -s
[test] sys.path[:3] = ['/lab/app', '/usr/local/bin', '/usr/local/lib/python312.zip']
[test] app module   = /lab/app/app.py
2 passed in 0.01s
```

출력을 뜯어 보면 두 가지가 보인다.

- 두 경우 모두 `sys.path` **맨 앞은 `/lab/app`** — `-m`이 넣은 게 아니라 **pytest가 삽입한 기준 디렉터리**다. `from app import add`를 해결한 주인공은 이쪽이다
- 두 번째 원소만 다르다. `-m`이면 cwd(`/lab`), 런처면 런처 스크립트가 있는 `/usr/local/bin`(경로 실행 규칙이 런처 파일에 적용된 것)

즉 이 레이아웃에서 import를 살린 건 `-m`이 아니다. cwd를 `/tmp`로 옮겨 절대 경로로 실행해도 네 조합 모두 통과했다 (전체 출력은 실습 저장소의 `lab.sh` 실행 결과 참고).

이제 `-m`이 정말로 성패를 가르는 레이아웃을 보자. 프로젝트 루트의 모듈을 `tests/` 아래의 테스트가 import하는, 흔한 구조다.

```python
# proj/mylib.py - 프로젝트 루트의 모듈
def double(x):
    """두 배로 만든다."""
    return x * 2
```

```python
# proj/tests/test_mylib.py - 루트의 mylib을 import
# pytest가 삽입하는 기준 디렉터리는 tests/이지 프로젝트 루트가 아니다
import mylib


def test_double():
    assert mylib.double(21) == 42
```

프로젝트 루트(`/lab/proj`)에서 두 방식으로 실행하면 결과가 갈린다.

```shell
# -m 없이: 기준 디렉터리(tests/)만 삽입되고 루트는 sys.path에 없다 -> import 실패
/lab/proj# pytest tests/ -q
ImportError while importing test module '/lab/proj/tests/test_mylib.py'.
tests/test_mylib.py:7: in <module>
    import mylib
E   ModuleNotFoundError: No module named 'mylib'
1 error in 0.07s

# -m: cwd(프로젝트 루트)가 sys.path 맨 앞에 추가된다 -> 통과
/lab/proj# python3 -m pytest tests/ -q
.                                                                        [100%]
1 passed in 0.01s
```

**판정** — 명제 확인. "`-m` 없이 pytest를 돌리면 import가 깨진다"는 통념은 레이아웃 의존적이다. 코드·테스트 동거 레이아웃에서는 pytest의 자체 삽입으로 충분하고, `tests/` 분리 레이아웃에서 비로소 `-m`의 cwd 삽입이 import를 구제한다.

## 실험 C: pytest 런처의 정체와 인터프리터 결속

**검증할 명제** — `pytest` 명령의 정체는 셔뱅으로 특정 인터프리터에 고정된 런처 스크립트이고, `-m`은 "내가 부른 인터프리터"에 결속된다.

이 실험의 첫 단계(C-0)는 설치 산출물 확인이다 — `site-packages` 목록, `pytest/` 패키지 안의 `__init__.py`·`__main__.py`, entry_points.txt의 console_scripts 선언, 그리고 대조군으로 entry_points.txt가 없는 `requests`의 dist-info까지. 그 출력은 [모듈과 패키지](#모듈과-패키지)에서 이미 인용했으므로, 여기서는 다음 단계인 런처 파일부터 직접 열어 본다.

```shell
# pytest 명령의 실체 - PATH에서 찾은 실행 파일
/lab# which pytest
/usr/local/bin/pytest

# 내용을 열어 보면 몇 줄짜리 파이썬 스크립트다
/lab# cat /usr/local/bin/pytest
#!/usr/local/bin/python3
# -*- coding: utf-8 -*-
import re
import sys
from _pytest.config import _console_main
if __name__ == '__main__':
    sys.argv[0] = re.sub(r'(-script\.pyw|\.exe)?$', '', sys.argv[0])
    sys.exit(_console_main())
```

첫 줄 셔뱅이 `/usr/local/bin/python3`으로 고정되어 있다. 이 파일이 pip 설치 시점에 생성된 console_scripts entry point 런처다.

이제 "엉뚱한 pytest" 시나리오를 재현한다. venv를 하나 만들어 **다른 버전**(7.4.4)의 pytest를 설치하고, venv의 `bin`을 `PATH` 맨 앞에 둔다.

```shell
# venv 생성 + 구버전 pytest 설치 후, PATH 맨 앞에 venv/bin 배치
/lab# python3 -m venv /opt/venv
/lab# /opt/venv/bin/pip install -q pytest==7.4.4
/lab# export PATH=/opt/venv/bin:$PATH

# 이제 pytest도, python3도 venv 것이 잡힌다
/lab# which pytest
/opt/venv/bin/pytest
/lab# which python3
/opt/venv/bin/python3

# PATH 우선순위대로 venv의 pytest 7.4.4가 실행된다
/lab# pytest --version
pytest 7.4.4

# python3 -m pytest도 7.4.4 - "python3" 자체가 venv 인터프리터로 해석됐기 때문
/lab# python3 -m pytest --version
pytest 7.4.4

# 인터프리터를 절대 경로로 지정하면 그 파이썬의 pytest(9.1.1)로 완전히 고정된다
/lab# /usr/local/bin/python3 -m pytest --version
pytest 9.1.1
```

`python3 -m pytest`가 7.4.4를 출력한 대목이 흥미롭다. `-m`은 마법처럼 "원래 파이썬"을 찾아 주지 않는다. `python3`라는 이름이 `PATH`에서 venv 인터프리터로 해석됐고, `-m`은 **그** 인터프리터의 pytest를 충실히 실행했을 뿐이다. 결속을 완전히 고정하려면 인터프리터를 절대 경로로 지정해야 한다.

덤으로, `python3 -m pytest`가 애초에 가능한 이유인 pytest 패키지의 `__main__.py`도 열어 봤다.

```python
# site-packages/pytest/__main__.py - -m 실행의 진입점
"""The pytest entry point."""
from _pytest.config import _console_main

if __name__ == "__main__":
    raise SystemExit(_console_main())
```

런처 스크립트와 하는 일이 같다. 결국 `pytest`와 `python3 -m pytest`는 같은 함수(`_console_main`)로 수렴하고, 차이는 **거기까지 가는 길**(PATH의 런처 vs 인터프리터의 모듈 탐색)뿐이다.

**판정** — 명제 확인. 런처는 설치 시점의 인터프리터에 셔뱅으로 결속되고, `-m`은 호출한 인터프리터에 결속된다.

## 실험 D: -m과 __main__

**검증할 명제** — `-m`으로 패키지를 실행하면 `<pkg>/__main__.py`가, 단일 모듈이면 그 파일 자체가 `__name__ == "__main__"`으로 실행된다.

실험용 미니 패키지 `mypkg`는 세 파일로 구성했다. 각 파일이 자기 `__name__`과 `__package__`를 출력한다.

```python
# mypkg/__init__.py - 패키지 import 시 실행된다
print(f"[mypkg/__init__.py] imported, __name__ = {__name__}")
```

```python
# mypkg/__main__.py - `python3 -m mypkg`의 진입점
print(f"[mypkg/__main__.py] __name__ = {__name__}, __package__ = {__package__!r}")
```

```python
# mypkg/tool.py - 단일 모듈 -m 실행 확인용
print(f"[mypkg/tool.py] __name__ = {__name__}, __package__ = {__package__!r}")

if __name__ == "__main__":
    print("[mypkg/tool.py] __main__으로 실행됨")
```

세 가지 방식으로 실행해 본다.

```shell
# 패키지를 -m으로 실행: __init__.py가 먼저 import되고, __main__.py가 진입점
/lab# python3 -m mypkg
[mypkg/__init__.py] imported, __name__ = mypkg
[mypkg/__main__.py] __name__ = __main__, __package__ = 'mypkg'

# 패키지 내 단일 모듈을 -m으로 실행: 그 파일이 __main__이 되고, 패키지 맥락 유지
/lab# python3 -m mypkg.tool
[mypkg/__init__.py] imported, __name__ = mypkg
[mypkg/tool.py] __name__ = __main__, __package__ = 'mypkg'
[mypkg/tool.py] __main__으로 실행됨

# 같은 파일을 경로로 직접 실행: __init__.py가 실행되지 않고, 패키지 맥락도 없다
/lab# python3 mypkg/tool.py
[mypkg/tool.py] __name__ = __main__, __package__ = None
[mypkg/tool.py] __main__으로 실행됨
```

**판정** — 명제 확인. 세 방식 모두 실행 대상의 `__name__`은 `"__main__"`이지만, 차이는 둘이다.

- `-m`은 패키지 맥락을 갖춘다 — `__init__.py`가 먼저 import되고 `__package__`가 채워진다. 파일 경로 실행은 그냥 파일 하나를 떼어 실행하는 것이라 둘 다 없다 (`__package__ = None`). 패키지 내부에서 상대 import를 쓰는 코드가 경로 실행에서만 깨지는 이유가 이것이다
- 대상이 패키지면 `__main__.py`가 진입점이다. 실험 C에서 본 pytest의 `__main__.py`가 정확히 이 자리에 있는 파일이다

<br>

# 정리

이론에서 세운 명제와 실측 결과를 한 표로 모으면 다음과 같다.

| 명제 | 결과 |
| --- | --- |
| `sys.path[0]` — 경로 실행은 스크립트 디렉터리, `-m`은 cwd, `-c`는 `''`, `-P`는 삽입 없음 | 확인 (실험 A) |
| 코드·테스트 동거 레이아웃은 `-m` 없이도 import 성공 (pytest의 기준 디렉터리 삽입) | 확인 (실험 B) |
| `tests/` 분리 레이아웃은 `-m` 여부가 import 성패를 가름 | 확인 (실험 B-4) |
| `pytest` 런처는 셔뱅으로 설치 시점 인터프리터에 고정된 entry point 스크립트 | 확인 (실험 C) |
| `python3 -m pytest`는 "부른 인터프리터"의 pytest에 결속 (venv가 PATH 앞이면 venv 것) | 확인 (실험 C) |
| `-m`은 패키지면 `__main__.py`, 모듈이면 그 파일을 `__main__`으로 실행. 패키지 맥락(`__package__`, `__init__.py`) 유지 | 확인 (실험 D) |

처음의 세 질문에 답하면 이렇다.

- **`-m`은 무엇인가** — 모듈 이름을 `sys.path`에서 찾아 `__main__`으로 실행하는 옵션이고, 부수 효과로 cwd를 `sys.path` 맨 앞에 추가한다
- **`pytest`와 무엇이 다른가** — 도착지는 같고(`_console_main`) 가는 길이 다르다. 런처는 셸의 `PATH`와 설치 시점 셔뱅이, `-m`은 지금 부른 인터프리터가 경로를 결정한다. import 구제 효과는 레이아웃에 따라 있을 수도, 필요 없을 수도 있다
- **어느 파이썬의 pytest인가** — 런처는 "설치했던 그 파이썬", `-m`은 "방금 부른 그 파이썬". CI에서 `python3 -m pytest`를 쓰는 건 후자의 예측 가능성 때문이다

같은 원리로 실무에서 자주 보이는 `-m` 사용처들도 읽을 수 있다.

| 명령 | -m을 쓰는 이유 |
| --- | --- |
| `python3 -m pip install ...` | pip과 인터프리터의 짝 고정 — "pip이 엉뚱한 파이썬에 설치하는" 사고 방지 (pip 공식 문서도 이 형태를 권장) |
| `python3 -m venv .venv` | 어느 인터프리터 기준의 venv인지 명시 |
| `python3 -m http.server` | 표준 라이브러리 모듈을 CLI 도구처럼 즉석 실행 |
| `python3 -m json.tool` | 마찬가지 — 별도 실행 파일 설치 없이 모듈을 도구로 사용 |

<br>

# 참고 링크

- [Python 공식 문서 — Command line and environment (`-m`, `-P`)](https://docs.python.org/3/using/cmdline.html#cmdoption-m)
- [Python 공식 문서 — `__main__` — Top-level code environment](https://docs.python.org/3/library/__main__.html)
- [Python 공식 문서 — The initialization of the sys.path module search path](https://docs.python.org/3/library/sys_path_init.html)
- [Python 공식 문서 — runpy](https://docs.python.org/3/library/runpy.html)
- [pytest 공식 문서 — Calling pytest through `python -m pytest`](https://docs.pytest.org/en/stable/how-to/usage.html#calling-pytest-through-python-m-pytest)
- [pytest 공식 문서 — pytest import mechanisms and sys.path/PYTHONPATH](https://docs.pytest.org/en/stable/explanation/pythonpath.html)
- [setuptools — Entry Points (console_scripts)](https://setuptools.pypa.io/en/latest/userguide/entry_point.html)
- [실습 코드 — sirzzang.github.io/_labs/python-module-execution](https://github.com/sirzzang/sirzzang.github.io/tree/master/_labs/python-module-execution)

<br>
