"""sys.path 확인용 스크립트 겸 모듈.

실행 방식(경로 실행, -m, -c)에 따라 sys.path[0]이 어떻게 달라지는지 출력한다.
"""
import os
import sys

print(f"__name__    = {__name__}")
print(f"cwd         = {os.getcwd()}")
print(f"sys.path[0] = {sys.path[0]!r}")
