# Vendor Extension Guide

현재 구조에서 모델, tool, vendor를 추가하거나 변경할 때 어디를 수정해야 하는지 정리한 문서다.

## 핵심 원칙
- 프런트는 provider 내부 구현을 모른다.
- `/api/v1/models`가 프런트의 단일 소스 오브 트루스다.
- 공통 레이어는 public model id, provider id, display name, available, tools만 안다.
- provider-native 정보는 각 provider 패키지 안에만 둔다.
- 실제 SDK 호출 세부사항은 각 provider의 `stream.py`, `client.py`, `config.py`, `tools.py`, `functions.py`, `mapper.py`가 책임진다.

## 현재 경계

공통 레이어:
- `proxy-api/app/providers/types.py`
  - 공통 dataclass 정의
- `proxy-api/app/providers/catalog.py`
  - public model 목록 노출
  - 요청 `model_id`, `tool_ids` 검증
  - `ProviderRoute` 생성
- `proxy-api/app/providers/dispatcher.py`
  - provider별 readiness 확인
  - provider별 stream 함수 호출
- `proxy-api/app/services/chat/stream.py`
  - SSE start/delta/done/error 이벤트 생성

Vertex 내부 레이어:
- `proxy-api/app/providers/vertex/models.py`
  - public model id -> Vertex runtime model id, location, supported tools
- `proxy-api/app/providers/vertex/client.py`
  - `google.genai.Client(vertexai=True, ...)` 생성
- `proxy-api/app/providers/vertex/config.py`
  - provider request config 조립
  - system instruction, hosted tools, function scaffold, provider defaults 결합
- `proxy-api/app/providers/vertex/stream.py`
  - Vertex runtime model 해석
  - contents 조립
  - `generate_content_stream(...)` 호출
- `proxy-api/app/providers/vertex/mapper.py`
  - 공통 chat message -> Vertex `contents`
  - Vertex chunk -> 공통 stream chunk
- `proxy-api/app/providers/vertex/tools.py`
  - backend hosted tool id -> Vertex tool payload
- `proxy-api/app/providers/vertex/functions.py`
  - future custom function declaration payload scaffold

프런트:
- `frontend/src/services/modelService.ts`
  - `/api/v1/models` 응답 파싱
- `frontend/src/pages/ChatPage.tsx`
  - 모델 목록 렌더링
  - 모델별 tool 목록 재계산
  - 선택한 `model_id`, `tool_ids`를 서버로 전송

## SDK 요청 조립 흐름

실제 요청이 조립되는 흐름은 아래 순서다.

1. `frontend`가 `model_id`, `tool_ids`, `messages`를 보낸다.
2. `proxy-api/app/services/chat/preparation.py`
   - 요청 스키마 검증 후 `ProviderRoute`를 만든다.
3. `proxy-api/app/providers/catalog.py`
   - public model id를 찾고
   - 해당 모델에서 허용된 tool id만 통과시킨다.
4. `proxy-api/app/providers/dispatcher.py`
   - `route.model.provider`를 보고 알맞은 provider로 보낸다.
5. `proxy-api/app/providers/vertex/stream.py`
   - `route.model.public_id`로 Vertex runtime spec을 찾는다.
   - runtime model id와 location을 결정한다.
6. `proxy-api/app/providers/vertex/client.py`
   - 해당 location으로 Vertex client를 만든다.
7. `proxy-api/app/providers/vertex/mapper.py`
   - 내부 `messages`를 Vertex `contents`로 바꾼다.
8. `proxy-api/app/providers/vertex/config.py`
   - system instruction과 provider config를 조립한다.
9. `proxy-api/app/providers/vertex/tools.py`
   - 선택된 hosted tool id를 Vertex tool payload로 바꾼다.
10. `proxy-api/app/providers/vertex/stream.py`
   - `aio_client.models.generate_content_stream(...)`를 호출한다.
11. `proxy-api/app/providers/vertex/mapper.py`
   - Vertex stream chunk를 공통 chunk로 바꾼다.
12. `proxy-api/app/services/chat/stream.py`
   - SSE 이벤트로 감싸서 클라이언트에 스트리밍한다.

즉 "실제 SDK 요청을 누가 조립하느냐"를 짧게 말하면:
- 모델별 실행 스펙 선택: `vertex/models.py`
- SDK client 생성: `vertex/client.py`
- provider config 조립: `vertex/config.py`
- hosted tool payload 변환: `vertex/tools.py`
- future function payload scaffold: `vertex/functions.py`
- SDK 호출: `vertex/stream.py`
- 메시지와 chunk 변환: `vertex/mapper.py`

## 새 Vertex 모델 추가

기존 Vertex provider 안에 Gemini 같은 새 모델을 추가할 때 기본 수정 지점은 아래다.

1. `proxy-api/app/providers/vertex/models.py`
   - `_VERTEX_MODELS`에 새 항목 추가
   - `public_id`
   - `provider_model`
   - `display_name`
   - `location`
   - `available`
   - `supported_tools`
2. 필요하면 `docs/API.md`, `README.md` 업데이트
3. 모델 특이점이 있으면 `proxy-api/app/providers/vertex/stream.py` 수정
   - 예: 특정 모델만 다른 config 필요
4. 모델 특이 hosted tool payload가 있으면 `proxy-api/app/providers/vertex/tools.py` 수정

대부분의 단순 모델 추가는 `vertex/models.py`만 바꾸면 끝난다.

## 기존 Vertex 모델 순서 변경

프런트에 보이는 모델 순서는 현재 `list_vertex_models()`가 반환하는 순서를 그대로 따른다.

지금 구현에서는:
- `proxy-api/app/providers/vertex/models.py`의 `_VERTEX_MODELS` 순서
- `proxy-api/app/providers/catalog.py`의 `list_available_models()` 순서

가 그대로 `/api/v1/models` 응답 순서가 된다.

그래서 `gemini-3-flash-preview`를 맨 위로 올리고 싶으면 현재 기준으로는 `_VERTEX_MODELS`에서 그 항목 순서만 바꾸면 된다.

전제:
- 다른 곳에서 별도 정렬을 하지 않아야 한다.
- 지금 코드에는 추가 정렬이 없다.

## 새 Vertex tool 추가

Vertex 모델에만 붙는 새 tool을 추가할 때는 아래 순서로 본다.

1. `proxy-api/app/providers/vertex/models.py`
   - 새 `ProviderToolDefinition` 추가
   - 어떤 모델에 노출할지 `supported_tools`에 연결
2. `proxy-api/app/providers/vertex/tools.py`
   - public hosted tool id -> Vertex payload builder 추가
3. 필요하면 `proxy-api/app/config/providers/vertex.py`
   - tool용 env/config 추가
4. provider request default를 바꾸려면 `proxy-api/app/providers/vertex/config.py`
   - system instruction 외 provider config 조립
5. 필요하면 `docs/ENVIRONMENT.md`
   - 새 env 문서화

중요:
- tool은 전역 공통 개념이 아니다.
- 모델 종속으로 본다.
- 어떤 tool이 보일지는 각 모델의 `supported_tools`가 결정한다.

## 새 vendor 추가

새 provider를 처음 추가할 때는 공통 레이어와 provider 레이어를 같이 만든다.

필수 작업:
1. `proxy-api/app/providers/<provider>/` 디렉터리 생성
2. `<provider>/provider.py`
   - 공개 entry point 작성
3. `<provider>/client.py`
   - SDK client 생성 책임 분리
4. `<provider>/stream.py`
   - 실제 SDK 호출 구현
5. 필요하면 `<provider>/models.py`
   - provider 내부 runtime model metadata 관리
6. 필요하면 `<provider>/mapper.py`
   - 공통 요청/응답 <-> provider payload 변환
7. 필요하면 `<provider>/tools.py`
   - provider-native tool payload 조립
8. `proxy-api/app/providers/dispatcher.py`
   - readiness branch 추가
   - stream branch 추가
9. `proxy-api/app/providers/catalog.py`
   - public model 목록에 새 provider 모델 노출

공통 타입을 늘릴지 말지는 마지막에 판단한다.
provider 내부에서만 해결 가능한 정보는 공통 타입에 올리지 않는다.

## 새 vendor의 새 모델 추가

이미 provider가 있는 상태에서 그 vendor의 모델만 추가한다면 보통 수정 범위는 작다.

예상 수정 지점:
- `<provider>/models.py` 또는 `<provider>/provider.py`
- 필요한 경우만 `<provider>/stream.py`
- 문서

공통 레이어 수정이 필요한 경우:
- `/api/v1/models` 응답 스키마 자체가 바뀔 때
- 공통 `ProviderRoute` 정보가 정말 늘어나야 할 때

그 외에는 공통 레이어를 건드리지 않는 쪽이 맞다.

## 새 vendor의 새 tool 추가

새 vendor가 자기 전용 tool을 갖는다면 그 tool은 그 vendor 패키지 안에서 정의하고 조립한다.

예상 수정 지점:
- `<provider>/models.py` 또는 `<provider>/provider.py`
- `<provider>/tools.py`
- 필요 시 `<provider>/stream.py`

프런트는 `/api/v1/models`에 그 tool이 보이면 렌더링만 한다.

## 체크리스트

모델 추가 후:
- `/api/v1/models`에 노출되는지 확인
- 선택 가능한 tool 목록이 맞는지 확인
- 실제 provider 호출이 성공하는지 확인
- 문서가 현재 public model ids와 맞는지 확인

tool 추가 후:
- 잘못된 모델에서 선택 불가능한지 확인
- provider payload가 기대한 모양인지 확인
- 필요한 env/config가 빠지지 않았는지 확인

vendor 추가 후:
- readiness 실패 메시지가 분리되어 있는지 확인
- dispatcher branch가 연결됐는지 확인
- stream error가 공통 에러로 매핑되는지 확인

## 현재 Vertex 모델 위치

현재 Vertex public model 목록과 실행 스펙은 여기서 관리한다:
- `proxy-api/app/providers/vertex/models.py`

현재 Vertex SDK 호출 진입점은 여기다:
- `proxy-api/app/providers/vertex/stream.py`

현재 SSE 응답 조립은 여기다:
- `proxy-api/app/services/chat/stream.py`
