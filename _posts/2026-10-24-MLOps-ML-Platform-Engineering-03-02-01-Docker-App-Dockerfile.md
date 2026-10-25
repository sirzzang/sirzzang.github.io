---
title: "[Docker] 머신러닝 플랫폼 엔지니어링: K8s와 CI/CD - 3.2.1. 앱 로컬 실행과 Dockerfile"
excerpt: "FastAPI 농담 앱을 로컬에서 띄우고 Dockerfile로 포장하면서, 로컬과 컨테이너의 실행 환경 차이를 확인해 보자."
categories:
  - mlops-foundation
  - cs-container
  - study
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Docker
  - Dockerfile
  - FastAPI
  - uv
  - Python
  - Machine-Learning-Platform-Engineering-Study
  - Machine-Learning-Platform-Engineering-Study-Week-1
use_math: false
last_modified_at: 2026-10-26
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 Machine Learning Platform Engineering Study 1주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- FastAPI로 만든 농담 앱을 로컬 Python 3.11 가상환경에서 실행하고 JSON 응답을 확인했다
- 컨테이너는 `python:3.10-slim-bookworm`의 Python과 설치 경로를 사용한다. 로컬 가상환경을 그대로 실행하는 구조가 아니다
- 실습 저장소의 `.dockerignore`에는 `.venv`가 포함돼 있어 Mac 가상환경은 빌드 컨텍스트에서 제외된다
- 가상환경 활성화 후에도 Homebrew의 `uvicorn`이 실행된 문제는 패키지 설치 뒤 `rehash`로 해결했다

<br>

# 실습 앱 해부

책 3.2.1~3.2.2절에 대응하는 실습이다. 모델 없이 농담 하나를 반환하는 `hello-joker`를 먼저 실행했다. 앱이 단순하므로 실행 환경을 컨테이너와 쿠버네티스로 옮길 때 달라지는 조건을 확인하기 좋다.

FastAPI는 Python으로 웹 API를 만드는 프레임워크다. 초기 `main.py`는 다음과 같다.

```python
# v1: GET / 요청마다 영어 농담 하나를 반환한다
from fastapi import FastAPI
import pyjokes

app = FastAPI()

@app.get("/")
async def root():
    random_joke = pyjokes.get_joke("en", "neutral")
    return {"random_joke": random_joke}
```

`pyjokes.get_joke()`가 영어(`en`)의 `neutral` 카테고리에서 농담을 고르고, FastAPI가 딕셔너리를 JSON 응답으로 변환한다. 뒤의 배포 실습에서 응답에 `version`을 추가했지만, 여기서는 최초 실행한 v1을 기준으로 본다.

HTTP 요청을 받아 이 앱을 실행하는 서버는 Uvicorn이다. Uvicorn은 ASGI(Asynchronous Server Gateway Interface, 비동기 서버 게이트웨이 인터페이스)를 구현한다. 실행 인자 `main:app`은 `main.py` 모듈의 `app` 객체를 가리킨다.

주요 의존성은 다음과 같다. 전체 파일에는 지표 수집용 패키지도 들어 있지만, 이 앱의 응답 경로에서는 아직 쓰지 않는다.

```text
# requirements.txt 발췌: ==가 없는 세 패키지는 버전 미고정
fastapi==0.95.2
numpy==1.25.0
pydantic==1.10.9
starlette==0.27.0
uvicorn==0.22.0
pyjokes
pytest
httpx
```

<br>

# 적용과 관찰

## 로컬 가상환경과 서버 실행

M1 Mac에서는 uv로 Python 3.11 가상환경을 만들었다. uv는 Python 환경과 패키지를 관리하는 도구다. `.venv`를 다시 만드는 경우에는 기존 활성화를 해제하고, 생성 → 활성화 → 설치 순서로 진행한다. 설치 후의 `rehash`는 [트러블슈팅](#트러블슈팅)에서 확인한 조치다.

```bash
# 실습 저장소의 앱 디렉터리에서 실행
cd ~/ml-study/chapters/ch03-k8s
deactivate 2>/dev/null
uv venv --python 3.11
source .venv/bin/activate
uv pip install -r requirements.txt
rehash

# 선택된 Python으로 Uvicorn 모듈을 실행
python --version
python -m uvicorn main:app --host 0.0.0.0 --port 8083
```

`~/ml-study`는 실습 저장소 경로를 줄여 쓴 것이다. 생성 당시 Python은 3.11.10이었다. `--host 0.0.0.0`은 모든 IPv4 인터페이스에서 수신하고, `--port 8083`은 서버가 사용할 포트를 지정한다.

다른 터미널에서 로컬 서버를 호출했다. 아래 농담은 실습 당시 반환된 응답이며, 호출할 때마다 내용이 달라진다.

```bash
# jq로 JSON 응답을 보기 좋게 출력
curl -s localhost:8083 | jq

# 실행 결과
{
  "random_joke": "Hey! It compiles! Ship it!"
}
```

## 의존성 고정 범위

실제 설치 결과에서 `httpx`는 0.28.1, `pyjokes`는 0.8.3이었다. `requirements.txt`에 이들의 버전이 없으므로 같은 명령을 다른 날 실행해도 전체 환경이 같다고 보장할 수 없다.

실제로 이 차이가 문제가 되는 곳이 있다. 로컬에서는 앱 기동과 `curl` 호출만 했으므로 httpx 0.28.1로도 문제가 없었다. 하지만 앱의 테스트가 쓰는 오래된 Starlette `TestClient`는 httpx 0.28과 맞지 않아, CI 저장소의 `requirements.txt`에는 `httpx==0.27.2`가 고정돼 있다. 이 조합의 테스트 결과는 [3.4.3편]({% post_url 2026-10-25-MLOps-ML-Platform-Engineering-03-04-03-CI-Workflow %})에서 다룬다.

<br>

# Dockerfile 해부

로컬에서 실행한 코드를 다른 머신으로 옮기려면 Python, 패키지, 시작 명령도 함께 정해야 한다. Dockerfile은 이 실행 환경을 이미지로 만드는 명령을 담는다. [컨테이너 이미지]({% post_url 2026-02-28-CS-Container-Image %})와 [컨테이너 파일시스템]({% post_url 2026-03-01-CS-Container-Filesystem %})의 상세 구조는 기존 글에서 다뤘다.

## 베이스 이미지 교체

책 예제는 `python:3.10-slim-buster`를 쓰지만 실습 저장소는 `python:3.10-slim-bookworm`으로 바꿨다. Debian 10 buster는 [2024년 6월 30일 LTS가 종료](https://www.debian.org/News/2024/20240615)됐고, 오래된 배포판은 [Debian 아카이브](https://www.debian.org/distrib/archive)에서 제공한다. 기존 미러의 buster 경로를 계속 쓰면 `apt-get update`가 404로 실패할 수 있다.

스터디 자료에는 buster 이미지로 빌드하다 `apt-get update`가 404로 실패해 bookworm으로 바꾼 과정이 있다. 내 실습 저장소도 처음 구성한 직후 베이스 이미지를 bookworm으로 바꾸고 빌드했다.

```dockerfile
# 실습 저장소의 Dockerfile
FROM python:3.10-slim-bookworm
WORKDIR /app

# 시스템 빌드 도구 설치
RUN apt-get update && \
    apt-get install --no-install-recommends -y \
    build-essential \
    && apt-get clean && rm -rf /tmp/* /var/tmp/*

# 의존성을 먼저 설치하고 앱 소스를 나중에 복사
COPY requirements.txt /app/requirements.txt
RUN pip3 install --upgrade pip
RUN pip3 install --no-cache-dir -r requirements.txt
COPY . /app

# 앱 포트와 모듈 검색 경로
EXPOSE 8083
ENV PYTHONPATH "/app"

# 시작 스크립트에 실행 권한 부여
RUN chmod +x /app/entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
```

이 Dockerfile에서 볼 지점은 세 가지다.

- 의존성 파일을 앱 소스보다 먼저 복사한다. 소스만 바뀌면 앞선 패키지 설치 레이어를 캐시로 재사용할 수 있다
- `EXPOSE 8083`은 이미지의 포트 정보를 선언할 뿐 호스트 포트를 열지 않는다. 호스트에서 접속할 포트는 `docker run -p`로 매핑하며, 실제 실행은 [3.2.2편]({% post_url 2026-10-24-MLOps-ML-Platform-Engineering-03-02-02-Docker-Multi-Arch-Build-Push %}#arm64-이미지의-로컬-실행)에서 확인한다
- `ENV PYTHONPATH "/app"`은 옛 표기라 빌드 때 `LegacyKeyValueFormat` 경고가 나왔다. 현재 권장 형식은 `ENV PYTHONPATH="/app"`이며, 경고가 나와도 빌드는 성공했다

스터디 자료의 Dockerfile 예시에는 `ARG environment`와 `ENV ENVIRONMENT` 두 줄이 더 있다. 가시다님은 이 두 줄이 책과 책 코드 저장소에는 빠져 있다고 표시했고, 실습 저장소의 Dockerfile에도 없다.

## 빌드 컨텍스트와 가상환경 제외

빌드 컨텍스트(build context)는 빌더가 `COPY` 등에 사용할 수 있도록 전달받는 파일 집합이다. `COPY . /app`도 이 집합 안에서 복사한다. 현재 `.dockerignore`는 다음 세 패턴을 제외한다.

```text
# .dockerignore: 로컬 가상환경과 캐시 제외
myvenv
__pycache__/*
.venv
```

`.dockerignore`에 `.venv`가 있으므로 Mac의 가상환경은 빌드 컨텍스트에 들어가지 않는다. `docker history`는 이미지의 레이어별 생성 명령과 크기를 보여 주는 명령이다. 로컬의 `hello-joker:v1`(539MB)에서 앱 파일을 복사한 `COPY . /app` 레이어는 495kB였고, 가장 큰 레이어는 `build-essential`을 설치한 `apt-get` 단계의 290MB였다.

{% raw %}
```bash
# 레이어별 크기와 생성 명령 확인
docker history --format '{{.Size}}\t{{.CreatedBy}}' hello-joker:v1

# 실행 결과 중 이 Dockerfile이 만든 레이어(2026-10-25)
# 495kB   COPY . /app # buildkit
# 73.4MB  RUN /bin/sh -c pip3 install --no-cache-dir -…
# 14.7MB  RUN /bin/sh -c pip3 install --upgrade pip # …
# 290MB   RUN /bin/sh -c apt-get update &&     apt-get…
```
{% endraw %}

## entrypoint.sh와 PID 1

`ENTRYPOINT`는 컨테이너가 시작될 때 실행할 프로그램을 지정하는 Dockerfile 명령이다. 이 이미지는 `ENTRYPOINT ["/app/entrypoint.sh"]`로 시작 스크립트를 실행하고, 스크립트가 Uvicorn을 띄운다. 실습 스크립트는 다음과 같다.

```sh
#!/bin/sh
# 컨테이너 시작 시 /app의 FastAPI 앱 실행
uvicorn main:app --proxy-headers --host 0.0.0.0 --port 8083
```

`ENTRYPOINT`가 JSON 배열인 exec 형식이어도 실행 대상이 셸 스크립트이므로, PID 1은 스크립트를 실행하는 `/bin/sh`이고 Uvicorn은 그 자식 프로세스다. 실제 기동 로그에서도 Uvicorn의 프로세스 ID는 7이었다. 셸이 PID 1로 남으면 `docker stop`이나 파드 종료 때 보낸 종료 신호가 Uvicorn에 전달되지 않을 수 있다. 이 PID 1 문제와, 마지막 명령에 `exec`를 붙여 셸을 앱 프로세스로 교체하는 방법은 [CMD와 ENTRYPOINT 글]({% post_url 2026-03-06-CS-Container-CMD-Entrypoint %}#pid-1-문제와-시그널-전달)에서 다뤘다. 실습 이미지는 책 코드의 스크립트를 그대로 사용했다.

## 로컬과 컨테이너의 실행 환경 차이

| 항목 | Mac 로컬 | 이번 컨테이너 이미지 |
|---|---|---|
| Python | Homebrew Python과 `.venv`의 3.11이 함께 존재 | 베이스 이미지의 Python 3.10 |
| 패키지 설치 | `.venv` 안에 설치 | 이미지 내부 Python 환경에 설치 |
| Uvicorn 실행 파일 | `.venv/bin`과 Homebrew 경로가 선택 후보 | `/usr/local/bin/uvicorn` |
| 실행 셸 | 계속 사용하는 zsh 세션 | 컨테이너 시작 때 실행하는 `/bin/sh` |
| 앱 코드 | 로컬 작업 디렉터리 | 빌드 때 `/app`에 복사한 파일 |

컨테이너는 Mac의 Homebrew 경로나 오래된 zsh 해시를 물려받지 않는다. 로컬과 컨테이너는 Python 버전부터 다르므로, 로컬 기동 확인과 이미지 실행 확인은 각각 필요하다.

로컬에서 가상환경을 만드는 이유는 Mac의 여러 프로젝트가 같은 Python 설치를 공유하기 때문이다. 프로젝트마다 `.venv`를 두면 패키지 버전이 서로 섞이지 않는다. 컨테이너 이미지는 그 자체가 이 앱 하나를 위한 파일 시스템이라 격리 단위 역할을 이미 한다. 베이스 이미지의 Python에 이 앱의 의존성만 설치하므로 다른 프로젝트와 충돌할 패키지가 없고, 이미지 안에 가상환경을 따로 만들 필요가 없다.

```bash
# 이미지 안 Python의 위치와 가상환경 여부 확인
docker run --rm --entrypoint sh hello-joker:v1 -c 'command -v python3; python3 -c "import sys; print(sys.prefix, sys.prefix == sys.base_prefix)"'

# 실행 결과
# /usr/local/bin/python3
# /usr/local True
```

`sys.prefix`와 `sys.base_prefix`가 같으면 가상환경이 아닌 기본 Python 환경이다. 공식 `python` 이미지는 Python을 Debian 패키지가 아닌 `/usr/local`에 설치하므로 `pip install`을 바로 쓸 수 있다. 배포판의 `apt`로 설치한 Python을 쓰는 이미지에서는 [PEP 668](https://peps.python.org/pep-0668/)의 외부 관리 환경 표시 때문에 시스템 전역 `pip install`이 거부될 수 있어, 컨테이너 안에서도 가상환경을 만들기도 한다.

<br>

# 트러블슈팅

## 증상

`.venv`를 활성화하고 의존성 설치까지 마쳤는데 `uvicorn main:app ...`을 실행하면 `ModuleNotFoundError: No module named 'fastapi'`가 발생했다.

## 증거

`.venv`의 Python은 3.11.10인데, 실제로 실행된 파일은 Homebrew Python 3.14의 `/opt/homebrew/bin/uvicorn`이었다. 가상환경 활성화 표시만으로는 셸이 어떤 실행 파일을 고르는지 알 수 없으므로, 다음 두 명령으로 실행 파일 검색 결과와 런처의 인터프리터 경로를 확인한다.

```bash
# 먼저 선택되는 uvicorn 경로 확인
type -a uvicorn

# 가상환경 런처 첫 줄의 shebang 확인
head -n 1 .venv/bin/uvicorn
```

`type -a`의 첫 줄이 `.venv/bin/uvicorn`이고 shebang이 그 가상환경의 Python을 가리켜야 정상이다.

## 원인

zsh는 한 번 찾은 명령의 실행 파일 경로를 해시 테이블에 기억한다. 가상환경을 활성화하면 `.venv/bin/activate` 마지막의 `hash -r`이 이 기억을 비운다. 하지만 이 세션에서는 활성화한 뒤, 가상환경에 Uvicorn을 설치하기 전에 `uvicorn`이 Homebrew 경로로 다시 기억됐다. 그 뒤 설치한 `.venv/bin/uvicorn`은 해시에 반영되지 않아 Homebrew 쪽이 계속 실행됐다. 활성화된 상태에서 `.venv`를 다시 만들기도 했다.

## 해결

패키지 설치 **후** `rehash`를 실행하니 가상환경의 Uvicorn이 정상 실행됐다. zsh 문서에서 [`rehash`는 `hash -r`과 같다](https://zsh.sourceforge.io/Doc/Release/Shell-Builtin-Commands.html#index-rehash). 오래된 명령 경로 캐시를 비우는 조치다.

```bash
# 패키지 설치를 마친 뒤 명령 캐시 초기화
rehash
type -a uvicorn

# 선택한 Python 환경의 uvicorn 모듈 실행
python -m uvicorn main:app --host 0.0.0.0 --port 8083
```

`python -m uvicorn`은 별도의 `uvicorn` 실행 파일을 PATH에서 찾지 않고, 선택된 Python의 모듈 검색 경로에서 `uvicorn`을 찾는다. 다만 `python` 자체도 PATH에서 고르므로, 그 `python`이 가상환경의 것인지는 확인해야 한다. 실행 파일과 모듈 실행의 차이는 [Python 모듈 실행]({% post_url 2026-07-11-Language-Python-Module-Execution %})에 정리했다.

<br>

# 정리

같은 `main.py`라도 어떤 Python으로 실행하고 어디에 패키지를 설치했는지가 다르다. 로컬에서는 zsh의 실행 파일 선택이 문제였고, 컨테이너에서는 Dockerfile이 Python과 패키지 설치 경로를 정했다. `.dockerignore`는 로컬 가상환경이 빌드에 섞이지 않도록 제외한다.

ML 플랫폼에서도 모델 코드를 실행하려면 먼저 이 실행 환경을 정의해야 한다. Dockerfile과 시작 명령은 이후 학습 작업과 서빙 앱이 사용하는 공통 기반이다. 여기서는 앱 기동과 실행 환경의 차이까지 확인했고, 같은 이미지를 여러 CPU 아키텍처에 제공하는 과정은 [3.2.2편]({% post_url 2026-10-24-MLOps-ML-Platform-Engineering-03-02-02-Docker-Multi-Arch-Build-Push %})에서 다룬다.

<br>

# 참고 링크

- 예제 코드: https://github.com/practical-mlops/chapter-3
- [Dockerfile reference](https://docs.docker.com/reference/dockerfile/)
- [Docker build context와 .dockerignore](https://docs.docker.com/build/building/context/#dockerignore-files)
- [Debian 10 LTS 종료 공지](https://www.debian.org/News/2024/20240615)
- [zsh Shell Builtin Commands](https://zsh.sourceforge.io/Doc/Release/Shell-Builtin-Commands.html)

<br>
