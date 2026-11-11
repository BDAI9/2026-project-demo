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

### 잇플·코스 담당 모듈 (개발 중)

Python 3.10 이상과 표준 라이브러리만으로 저장소 루트에서 다음 명령을 실행합니다. Windows, macOS, Linux에서 명령은 같습니다 (`python`이 없는 환경에서는 `python3` 사용).

```bash
python -m backend.server
python -m backend.demo
python -m unittest discover -s tests -v
```

서버를 실행한 뒤 브라우저에서 `http://127.0.0.1:8000/`을 엽니다. 화면에서 **샘플 데이터**와 가상 지역을 선택하면 데이트 코스를 볼 수 있습니다. `python -m backend.demo`는 별도 콘솔 데모입니다. 이 화면은 담당 기능을 시험하기 위한 로컬 데모이며 공유 방과 팀의 프론트엔드는 아직 연결되지 않았습니다.

현재 앱의 실제 잇플 검색은 **직접 제휴 API** 경로이며 기관명 발급과 서버 IP 등록이 필요합니다. 서버를 실행할 셸에서 기관명을 환경변수 `EATPL_INSTITUTION`으로 설정하세요. `EATPL_ENV`는 생략하면 개발 서버(`dev`)이며, 운영 허가 후에만 `prod`를 사용합니다. `EATPL_TRACE_DB`는 거래추적번호 순번을 보관할 SQLite 파일의 경로로, 생략하면 실행 디렉터리의 `eatpl_traces.sqlite3`를 사용합니다. 같은 기관의 모든 호출 인스턴스가 동일한 순번 저장소를 공유해야 중복을 피할 수 있으므로, 이 로컬 데모를 여러 서버에 그대로 배포하면 안 됩니다. 인증 정보는 소스나 채팅에 적지 마세요. 직접 API의 실서버 호출과 앱에서 잇플 상세 이동은 아직 검증 전입니다.

k-skill 공개 프록시로 개인이 단발 조회하는 진단은 별도로 실행할 수 있습니다. 다음 명령은 실제 가맹점과 링크를 보여 주며, 캐시 응답인지도 표시합니다. 로컬 화면에서도 `k-skill 개인 단발 테스트`를 선택하면 한 번 조회할 수 있습니다. 개발 테스트·팀 서비스에서의 이용 조건은 [연동 문서](docs/integration.md)를 참고하세요.

```powershell
python -m backend.skill_probe
```

담당 범위 및 남은 통합 작업은 [작업 현황](docs/eatpl-course-tasks.md), 팀 통합 시 차이점은 [팀 공유 메모](docs/team-handoff.md), 데이터와 모듈 계약은 [계약](docs/contracts.md)을 참고하세요.
