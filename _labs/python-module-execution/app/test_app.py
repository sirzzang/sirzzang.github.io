"""app 모듈 유닛 테스트.

로컬 모듈 import가 어떻게 해석되는지 관찰하기 위해, 원 CI 레이아웃과 같은
`from app import ...` 형태를 그대로 쓴다. 테스트 실행 시점의 sys.path와
실제로 import된 app 모듈의 파일 경로도 출력한다.
"""
import sys

from app import add, greet


def test_syspath_and_module_origin():
    """어떤 경로가 sys.path에 있고, app이 어디서 import됐는지 출력한다."""
    import app
    print()
    print(f"[test] sys.path[:3] = {sys.path[:3]}")
    print(f"[test] app module   = {app.__file__}")
    assert add(1, 2) == 3


def test_greet():
    assert greet("world") == "hello, world"
