"""단일 모듈 -m 실행 확인용 (`python3 -m mypkg.tool`)."""
print(f"[mypkg/tool.py] __name__ = {__name__}, __package__ = {__package__!r}")

if __name__ == "__main__":
    print("[mypkg/tool.py] __main__으로 실행됨")
