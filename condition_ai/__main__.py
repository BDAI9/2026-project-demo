"""터미널에서 바로 확인하기.

    python -m condition_ai --mode group "강남에서 4명, 매운 음식과 해산물은 제외"
    python -m condition_ai --mode date --no-llm "홍대에서 카페 → 식사 → 술집"
"""

import argparse
import json
import sys

from . import parse_conditions


def main() -> None:
    p = argparse.ArgumentParser(description="조건 해석 테스트")
    p.add_argument("text", nargs="?", help="입력 문장 (생략하면 표준 입력에서 읽음)")
    p.add_argument("--mode", default="group", help="group 또는 date")
    p.add_argument("--no-llm", action="store_true", help="AI 없이 규칙 기반만 사용")
    args = p.parse_args()

    text = args.text if args.text is not None else sys.stdin.read()
    result = parse_conditions(text, args.mode, use_llm=False if args.no_llm else None)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
