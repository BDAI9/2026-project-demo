# 2026 Project Demo

4인 팀이 함께 만드는 장소 추천 서비스의 초기 저장소입니다. 현재 기획과 기술 검토 단계이며, 아래 기능은 구현 목표입니다.

## 서비스 방향

- **단체 모임**: 여러 사람의 선호와 제외 조건을 모아 장소 선택을 돕습니다. 공유·실시간 구현 방식은 검토 중입니다.
- **데이트·소개팅**: 선호와 장소 간 이동을 고려해 식사·카페 등 코스 선택을 돕습니다.

잇플 스킬의 호출 방법과 제공 정보, 위치·거리 데이터 사용 가능 여부는 먼저 확인합니다.

## 브랜치와 역할

| 브랜치 | 작업 |
| --- | --- |
| `main` | 검토를 마친 통합본 |
| `dev` | 기능을 통합하고 테스트 |
| `feature/frontend` | 두 모드의 입력·결과 화면 |
| `feature/condition-ai` | 사용자 조건 해석 및 입력 형식 |
| `feature/eatpl-course` | 잇플 연동 검토 및 코스 구성 |
| `feature/data-validation` | 데이터 정의와 테스트 |

## 협업 흐름

1. 할 일을 정하고 해당 작업 브랜치에서 변경합니다.
2. 작업이 끝나면 PR의 **base를 `dev`**, compare를 작업 브랜치로 선택합니다.
3. 팀원이 변경 사항을 확인한 후 `dev`에 병합합니다.
4. 통합 테스트 후 `dev`에서 `main`으로 PR을 보냅니다.
5. 시작 전 최신 `dev` 변경을 작업 브랜치에 반영합니다.

### 처음 저장소 받기

```bash
git clone https://github.com/BDAI9/2026-project-demo.git
cd 2026-project-demo
git fetch origin
git switch --track origin/feature/frontend
```

마지막 줄의 브랜치 이름은 본인 역할에 맞게 바꿉니다. 이미 같은 이름의 로컬 브랜치가 있으면 `git switch feature/frontend`를 사용합니다.

## 공용 참고 자료

[Git & GitHub Team Work 협업하기](https://velog.io/@won11/Git-GitHub-Team-Work-%ED%98%91%EC%97%85%ED%95%98%EA%B8%B0)

참고 글은 Fork와 `develop`을 사용합니다. 이 팀의 기본 제안은 쓰기 권한이 있는 팀원이 공동 저장소의 `feature/*` 브랜치에서 작업하고 `dev`로 PR을 보내는 방식입니다.

## 실행 환경

기술 스택과 실행 방법은 팀 합의 후 추가합니다. API 키나 개인 비밀값은 저장소에 올리지 않습니다.
