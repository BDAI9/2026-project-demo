"""Conservative guards for input that the current condition schema cannot carry.

The caller must resolve blocking questions before searching. This heuristic is
not a complete natural-language parser or an allergy-safety guarantee.
"""
from __future__ import annotations

import re

from .rule_parser import Message, _segments
from .vocab import NEG_CUE_RE, EXCEPT_RE, find_terms


_BUDGET = re.compile(
    r"예산|비싸|가격|경비|비용|(?:\d[\d,.]*\s*(?:(?:만|천)\s*원?|원))|"
    r"(?:[일이삼사오육칠팔구십백천]+)?만원"
)
_ALLERGY = re.compile(r"알레르기|알러지")
_CUES = re.compile(
    r"알레르기|알러지|싫(?:어(?:요)?|다|습니다)?|"
    r"빼(?:주세요|줘|고요|고|자|기)?|제외(?:해주세요|해줘|하고|해요|요)?|"
    r"못\s?먹(?:어요|어|는다)?|안\s?먹(?:어요|어|는다)?|"
    r"별로(?:예요|야)?|피하(?:고|기|자)?|피해(?:요|줘)?|말고|패스|불호|"
    r"안\s?가(?:요)?|못\s?가(?:요)?|안\s?좋(?:아|아요)?|"
    r"안\s?마(?:셔|셔요)|못\s?마(?:셔|셔요)|금주|질렸(?:어|어요)?|질려(?:요)?"
)
_PERSON_COUNT = re.compile(r"\d+\s*(?:명|사람|인)(?!당)")
# Only allow grammatical fillers after recognized terms and negation are removed.
_FILLERS = re.compile(
    r"(?:\s|[,.!?~;/]|→|->|은|는|이|가|을|를|과|와|랑|하고|도|에서|"
    r"근처|부근|인근|쪽|으로|에는|에게|한테|님|저|나|우리|저희|"
    r"난|전|그거|그건|음식|요리|메뉴|종류|거|것|걸|주세요|해줘|요|요청|"
    r"제발|가능하면|가능한|선택|좀|많이|아예|같이|포함|전부|모두|다|없어|있어)*"
)


def _has_unrecognized_exclusion(segment: str) -> bool:
    if not (NEG_CUE_RE.search(segment) or EXCEPT_RE.search(segment)):
        return False
    terms = find_terms(segment)
    if not any(term.kind != "region" for _, _, term in terms):
        # A region-only exclusion such as '강남 말고 홍대' is already handled
        # by region selection. Any other exclusion without a known term is not.
        if terms and all(term.kind == "region" for _, _, term in terms) and EXCEPT_RE.search(segment):
            return False
        return True
    residue = segment
    for start, end, _ in reversed(terms):
        residue = residue[:start] + " " * (end - start) + residue[end:]
    residue = _PERSON_COUNT.sub(" ", residue)
    residue = _CUES.sub(" ", residue)
    return _FILLERS.fullmatch(residue) is None


def unresolved_inputs(messages: list[Message]) -> list[dict]:
    """Return source-preserving unresolved conditions, independent of AI output."""
    items = []
    for message in messages:
        # Preserve the whole budget message: punctuation may be a decimal
        # separator, and scope (per person/per place/total) can occur elsewhere.
        if _BUDGET.search(message.text):
            items.append({"kind": "budget", "speaker": message.speaker, "text": message.text})
        for start, end in _segments(message.text):
            raw = message.text[start:end].strip()
            kinds = []
            if _ALLERGY.search(raw):
                kinds.append("allergy")
            elif _has_unrecognized_exclusion(raw) and (not _BUDGET.search(raw) or re.search(r"싫|못\s?먹|안\s?먹|제외|빼|피하", raw)):
                kinds.append("exclusion")
            for kind in kinds:
                items.append({"kind": kind, "speaker": message.speaker, "text": raw})
    return items
