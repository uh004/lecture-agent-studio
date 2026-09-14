# Lecture Agent 평가

이 폴더는 `lecture_agent_final.ipynb`의 운영 흐름과 분리된 오프라인 평가 공간입니다. 평가 대상 코드는 변경하지 않고, 고정 Dataset과 동일 지표로 버전별 성능을 비교합니다.

## 평가 흐름

1. 평가용 PPTX를 고정합니다. 현재 기준 파일은 `data/sample.pptx`입니다.
2. `datasets/lecture_agent_v1.jsonl`에 PPT 파싱·검색 판단·Script 핵심점 정답을 기록합니다.
3. `datasets/validation_cases_v1.jsonl`에는 같은 슬라이드로 만든 고정 PASS/FAIL Script를 기록합니다.
4. 확인이 끝난 Case만 `metadata.label_status`를 `VERIFIED`로 관리합니다.
5. 노트북 실행 중 `NotebookEvalCapture`로 Prediction JSONL을 만듭니다.
6. 로컬 Code Evaluator를 실행하고, 필요할 때 LangSmith LLM-as-a-Judge를 실행합니다.

`DRAFT` Case는 모든 평가에서 제외됩니다. Parser가 만든 값을 그대로 정답으로 복사하면 순환 평가가 되므로, 반드시 사람이 원본 PPT와 대조합니다.

## Dataset 계약

두 Dataset을 분리하는 이유는 매번 달라지는 생성 Script를 Validation 정답으로 사용하지 않기 위해서입니다. `lecture_agent_v1.jsonl`은 파이프라인 품질용이고, `validation_cases_v1.jsonl`은 Validation Agent 자체 성능용입니다.

각 JSONL 레코드는 다음 세 영역을 가집니다.

- `inputs`: PPT 경로, 슬라이드 번호, 원본 가시 정보, 직전 승인 Script
- `reference_outputs`: Parser 정답, 검색 필요 판단, Script 핵심점 또는 Validation 정답
- `metadata`: `DRAFT` 또는 `VERIFIED`, Dataset split, 메모

Validation 오류 유형은 현재 Schema 필드명과 동일하게 아래 값만 사용합니다.

- `unsupported_claims`
- `missing_points`
- `distortions`

Validation Dataset의 `reference_outputs.validation.status`는 고정된 `inputs.script_draft`에 대한 정답입니다. 현재 Dataset은 세 정상 Script와 `unsupported_claims`, `missing_points`, `distortions`를 하나씩 주입한 세 오류 Script로 구성됩니다.

## 노트북 Prediction 캡처

프로젝트 루트가 Python 경로에 포함된 상태에서 E2E 셀에 아래 방식으로 연결할 수 있습니다.

```python
from evals.capture import NotebookEvalCapture

eval_capture = NotebookEvalCapture(TEST_PPTX_PATH)

for graph_output in graph_app.stream(initial_state, {"recursion_limit": 1000}):
    for node_name, node_state in graph_output.items():
        eval_capture.observe(node_name, node_state)

prediction_path = eval_capture.write(e2e_work_dir / "eval_predictions.jsonl")
print("평가 Prediction:", prediction_path)
```

노트북을 `notebooks/`에서 실행해 import가 되지 않으면 프로젝트 루트를 한 번 추가합니다.

```python
import sys
sys.path.insert(0, str(Path.cwd().parent))
```

## 로컬 Code 평가

```powershell
python -m evals.run_code_evals `
  --dataset evals/datasets/lecture_agent_v1.jsonl `
  --predictions path/to/eval_predictions.jsonl
```

주요 출력은 Parser 정확도와 검색 필요 판단 Precision/Recall/F1입니다. Script 품질은 LangSmith LLM Judge로 평가합니다.

Validation Agent의 결과를 아래 형식의 Prediction JSONL로 저장한 뒤 별도 평가합니다.

```json
{"case_id":"validation_sample_slide_001_pass","outputs":{"validation":{"status":"PASS","error_types":[]}}}
```

```powershell
python -m evals.run_validation_evals `
  --dataset evals/datasets/validation_cases_v1.jsonl `
  --predictions path/to/validation_predictions.jsonl
```

## LangSmith 평가

`.env`에 `LANGSMITH_API_KEY`, `LANGSMITH_TRACING=true`, `OPENAI_API_KEY`를 설정합니다.

먼저 `VERIFIED` Case를 Dataset으로 한 번 업로드합니다.

```powershell
python -m evals.upload_langsmith_dataset `
  --dataset evals/datasets/lecture_agent_v1.jsonl `
  --name lecture-agent-v1
```

Code Evaluator만 실행하려면:

```powershell
python -m evals.run_langsmith_evals `
  --dataset-name lecture-agent-v1 `
  --predictions path/to/eval_predictions.jsonl
```

검색·Script LLM Judge까지 실행하려면 `--with-llm-judge`를 추가합니다. 이 옵션은 별도의 Judge API 비용이 발생합니다.

```powershell
python -m evals.run_langsmith_evals `
  --dataset-name lecture-agent-v1 `
  --predictions path/to/eval_predictions.jsonl `
  --with-llm-judge `
  --judge-model gpt-4o-mini
```

## 초기 목표값

아래 값은 첫 Dataset 결과를 본 뒤 조정할 임시 기준입니다.

- Parser Slide Success Rate: 0.95 이상
- Search Decision F1: 0.85 이상
- Validation FAIL Recall: 0.90 이상
- Validation False PASS Rate: 0.05 이하
- Script Groundedness / Completeness / Clarity / Continuity: 각각 4점 이상
- Unsupported Claim Rate: 0.02 이하
- End-to-End completed 비율: 0.95 이상

LLM Judge의 신뢰성은 전체 Case 중 일부를 사람이 다시 채점해 Judge 점수와 비교합니다.
