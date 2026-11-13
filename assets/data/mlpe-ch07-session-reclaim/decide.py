"""세션 신호로 회수 여부를 판정한다. 로컬 실험에 쓴 규칙만 담았다. 파일을 직접 실행하면 규칙을 검사한다."""
from dataclasses import dataclass

MEM_MIB = 100      # 이보다 적으면 GPU를 쓰기 시작하지 않은 것으로 본다
IDLE_LIMIT = 1800  # 초


@dataclass
class Signals:
    gpu_util: float      # 0~100. 실험에서는 파일로 넣는다
    fb_mib: float        # GPU 메모리 사용량
    connected: bool      # IDE 접속이 살아 있는가
    idle_seconds: float  # 마지막 접속 흔적이나 파드 시작 이후 지난 시간


def computing(s: Signals) -> bool:
    """메모리가 비어 있으면 사용률이 높아도 연산으로 세지 않는다."""
    return s.fb_mib >= MEM_MIB and s.gpu_util > 0


def decide(s: Signals, idle_limit: float = IDLE_LIMIT) -> tuple:
    """(상태, 조치)를 돌려준다. 조치는 keep, reclaim 중 하나다."""
    if computing(s):
        return "computing", "keep"
    if s.connected:
        return "coding", "keep"
    if s.idle_seconds < idle_limit:
        return "grace", "keep"
    return "unused", "reclaim"


def check() -> None:
    long = IDLE_LIMIT + 1
    table = [
        # 사용률, 메모리, 접속, 경과 -> 상태, 조치
        ((95, 40000, False, long), ("computing", "keep")),
        ((0, 0, True, long), ("coding", "keep")),
        ((0, 0, False, 60), ("grace", "keep")),
        ((0, 0, False, long), ("unused", "reclaim")),
        ((100, 0, False, long), ("unused", "reclaim")),  # 메모리가 비었으면 사용률 100%도 연산이 아니다
    ]
    for args, expected in table:
        got = decide(Signals(*args))
        assert got == expected, (args, got, expected)
    print(f"ok: {len(table)} cases")


if __name__ == "__main__":
    check()
