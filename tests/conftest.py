import sys
from pathlib import Path

# `pytest`만 입력해도 condition_ai 패키지를 찾도록 저장소 루트를 경로에 넣는다
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
