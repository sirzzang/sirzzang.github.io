"""실습용 최소 앱 모듈.

CI 스크립트에서 만난 레이아웃(app/ 아래 앱 코드 + 테스트)을 재구성한 것으로,
외부 의존성 없이 순수 파이썬 함수만 둔다.
"""


def add(a, b):
    """두 수를 더한다."""
    return a + b


def greet(name):
    """인사 문자열을 만든다."""
    return f"hello, {name}"


if __name__ == "__main__":
    # 직접 실행했을 때만 동작하는 진입점
    print(add(1, 2))
