# python-module-execution

블로그 포스트 "[Python] python -m과 모듈 실행"의 실습 코드.
파이썬 실행 방식(경로 실행, `-m` 모듈 실행, 런처 실행 파일)에 따라
`sys.path`, import 해석, 인터프리터 선택이 어떻게 달라지는지 확인한다.

## 실행 방법

로컬 파이썬을 쓰지 않고 `python:3.12-slim` 컨테이너 안에서 전체 실험을 돌린다.

```bash
./run.sh
```

## 구성

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

## 실험 요약 (실측 결과)

| # | 검증한 명제 | 결과 |
|---|---|---|
| A | `sys.path[0]`은 실행 방식에 따라 다르다 — 경로 실행은 스크립트 디렉터리, `-m`은 cwd, `-c`는 `''`(cwd), `-P`는 삽입 없음 | 확인 |
| B | 코드와 테스트가 같은 폴더에 있으면 `-m` 없이 `pytest`만으로도 import가 성공한다 (pytest가 basedir를 `sys.path`에 삽입) | 확인 — 4가지 조합 모두 통과 |
| B-4 | `tests/` 분리 레이아웃에서는 `-m` 여부가 import 성패를 가른다 | 확인 — `pytest tests/`는 `ModuleNotFoundError`, `python3 -m pytest tests/`는 통과 |
| C | `pytest` 명령의 정체는 셔뱅으로 특정 인터프리터에 고정된 entry point 런처 스크립트다 | 확인 — venv를 PATH 앞에 두면 다른 버전의 pytest가 실행됨 |
| D | `-m`으로 패키지를 실행하면 `<pkg>/__main__.py`가, 단일 모듈이면 그 파일이 `__name__ == "__main__"`으로 실행된다 | 확인 |
