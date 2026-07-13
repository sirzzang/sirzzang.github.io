"""프로젝트 루트의 mylib 모듈을 import하는 테스트.

테스트 파일이 tests/ 아래에 있어서, pytest가 sys.path에 삽입하는 basedir는
tests/이지 프로젝트 루트가 아니다. 따라서 import 성공 여부는 프로젝트 루트가
sys.path에 있는지(= -m 실행 여부)에 달려 있다.
"""
import mylib


def test_double():
    assert mylib.double(21) == 42
