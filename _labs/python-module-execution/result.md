# python-module-execution 실험

## PreRequisites

### 코드 확인

`README.md` → `run.sh` → `lab.sh`의 위쪽 30줄
- `run.sh`: 한 줄이 전부. `-v "$PWD":/lab`으로 현재 디렉토리를 컨테이너 `/lab`에 마운트, `-w /lab`으로 작업 디렉토리 지정.
- `lab.sh`: `section()`, `run()` 헬퍼 확인. `run()`는 명령을 보여주고 실행하는 역할만 함

### 컨테이너 실행

```bash
cd _labs/python-module-execution
docker run --rm -it -v "$PWD":/lab -w /lab python:3.12-slim bash
# 이제 컨테이너 안. 아래 직접 수행
```

## 1. 실험 A: 실행 방식별 sys.path[0]

### show_syspath.py

`__name__`, cwd, `sys.path[0]` 세 가지 출력
- `__name__`: 스크립트가 어떻게 실행되었는지 보여줌
- `cwd`: 스크립트를 실행한 시점의 현재 작업 디렉토리
- `sys.path[0]!r`: 파이썬이 모듈을 찾을 때 확ㅇ니하는 경로 리스트의 첫 번째 항목

#### Before

아래 네 명령 각각에서 `sys.path[0]`의 결과가 무엇이 나올지 예측
```bash
cd /tmp && python3 /lab/show_syspath.py     # 예측: ?
cd /lab && python3 -m show_syspath          # 예측: ?
cd /tmp && python3 -m show_syspath          # 예측: ?
cd /lab && python3 -c 'import sys; print(sys.path[0])'   # 예측: ?
```

#### After

```bash
# 첫 번째 실험
root@33279c221566:/lab# cd /tmp && python3 /lab/show_syspath.py
__name__    = __main__
cwd         = /tmp
sys.path[0] = '/lab'

# 두 번째 실험
root@33279c221566:/tmp# cd /lab && python3 -m show_syspath
__name__    = __main__
cwd         = /lab
sys.path[0] = '/lab'

# 세 번째 실험: 에러
root@33279c221566:/lab# cd /tmp && python3 -m show_syspath
/usr/local/bin/python3: No module named show_syspath

# 네 번째 실험: 출력 비어 있음
root@33279c221566:/tmp# cd /lab && python3 -c 'import sys; print(sys.path[0])'

root@33279c221566:/lab# 
```

#### 정리

| 실행 명령 | `__name__` | `cwd` | `sys.path[0]` | 비고 |
|---|---|---|---|---|
| `cd /tmp && python3 /lab/show_syspath.py` | `__main__` | `/tmp` | `'/lab'` | 스크립트 경로 실행 → 스크립트가 있는 디렉터리가 들어감. cwd와 다름 |
| `cd /lab && python3 -m show_syspath` | `__main__` | `/lab` | `'/lab'` | `-m` 실행 → cwd가 들어감. 우연히 cwd == 스크립트 위치라 결과가 위와 같아 보임 |
| `cd /tmp && python3 -m show_syspath` | (실행 안 됨) | (실행 안 됨) | (실행 안 됨) | `No module named show_syspath` 에러. `-m`은 cwd(`/tmp`)에서 모듈을 찾는데 거기 없어서 실행 자체가 실패 |
| `cd /lab && python3 -c 'import sys; print(sys.path[0])'` | (해당 없음) | (해당 없음) | `''` (빈 문자열) | `-c` 실행 → `sys.path[0]`이 빈 문자열(cwd를 의미하는 관례적 표기). `print(sys.path[0])`이라 화면엔 빈 줄만 찍힘. 에러 아님, 정상 |

