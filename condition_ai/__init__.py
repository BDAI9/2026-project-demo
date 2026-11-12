"""백엔드 ① 조건 해석·AI 모듈.

사용 예:
    from condition_ai import parse_conditions
    result = parse_conditions("강남에서 4명, 매운 음식과 해산물은 제외", mode="group")
"""

from .parser import parse_conditions
from .schema import SCHEMA_VERSION, ConditionResult

__all__ = ["parse_conditions", "ConditionResult", "SCHEMA_VERSION"]
