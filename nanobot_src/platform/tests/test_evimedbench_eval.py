"""Tests for EviMedBench rubric judge task generation."""

import json

from app.training_eval.evimedbench import (
    build_evimedbench_judge_tasks,
    extract_evimedbench_answer_records_from_traces,
    load_evimedbench_cases,
    main,
    summarize_evimedbench_cases,
)


def write_sample_evimedbench(path):
    path.write_text(
        json.dumps(
            [
                {
                    "eval_id": "内分泌代谢_01",
                    "final_eval_id": "EVAL-001",
                    "question": "对于新诊断的2型糖尿病患者，二甲双胍是否应作为首选降糖药物？",
                    "pico": {
                        "P": "新诊断的2型糖尿病患者",
                        "I": "二甲双胍单药治疗",
                        "C": "其他口服降糖药或生活方式干预",
                        "O": "血糖控制、低血糖风险、不良反应发生率",
                    },
                    "specialty": "内分泌代谢",
                    "grade": "G1",
                    "question_type": "干预性",
                    "rubrics": [
                        {
                            "rubric_id": "R1",
                            "dimension": "问题相关性",
                            "dimension_id": "rule_question_relevance",
                            "criterion": "回答是否明确针对PICO要素，未偏题。",
                            "weight": 3,
                            "verification_hint": "核查回答是否紧扣PICO。",
                        },
                        {
                            "rubric_id": "R2",
                            "dimension": "证据回答一致性",
                            "dimension_id": "",
                            "criterion": "回答是否存在编造研究或错误统计结果。",
                            "weight": -3,
                            "verification_hint": "检查是否存在幻觉或错误数据。",
                        },
                    ],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_load_evimedbench_cases_preserves_pico_and_rubrics(tmp_path):
    dataset_path = tmp_path / "evimedbench.json"
    write_sample_evimedbench(dataset_path)

    cases = load_evimedbench_cases(dataset_path)

    assert len(cases) == 1
    case = cases[0]
    assert case.eval_id == "内分泌代谢_01"
    assert case.final_eval_id == "EVAL-001"
    assert case.pico["P"] == "新诊断的2型糖尿病患者"
    assert case.rubrics[0].dimension_id == "rule_question_relevance"
    assert case.rubrics[1].dimension_id == ""
    assert case.rubrics[1].weight == -3


def test_build_evimedbench_judge_tasks_does_not_auto_score(tmp_path):
    dataset_path = tmp_path / "evimedbench.json"
    write_sample_evimedbench(dataset_path)
    cases = load_evimedbench_cases(dataset_path)
    answers = [
        {
            "eval_id": "EVAL-001",
            "answer": "二甲双胍通常可作为首选，但需结合禁忌证和个体化情况。",
            "trace_id": "trace-1",
            "model": "nanobot-hermes",
        }
    ]

    tasks = build_evimedbench_judge_tasks(cases, answers)

    assert len(tasks) == 1
    task = tasks[0]
    assert task["mode"] == "evimedbench_rubric_judge_task"
    assert task["eval_id"] == "内分泌代谢_01"
    assert task["final_eval_id"] == "EVAL-001"
    assert task["answer"] == answers[0]["answer"]
    assert task["answer_meta"]["trace_id"] == "trace-1"
    assert task["rubrics"][0]["rubric_id"] == "R1"
    assert task["rubrics"][0]["judge_schema"]["passed"] == "boolean"
    assert "score" not in task
    assert "passed" not in task["rubrics"][0]


def test_build_evimedbench_judge_tasks_keeps_multiple_answers_for_same_case(tmp_path):
    dataset_path = tmp_path / "evimedbench.json"
    write_sample_evimedbench(dataset_path)
    cases = load_evimedbench_cases(dataset_path)
    answers = [
        {"eval_id": "EVAL-001", "answer": "first answer", "trace_id": "trace-1"},
        {"eval_id": "EVAL-001", "answer": "second answer", "trace_id": "trace-2"},
    ]

    tasks = build_evimedbench_judge_tasks(cases, answers)

    assert [task["answer"] for task in tasks] == ["first answer", "second answer"]
    assert [task["answer_meta"]["trace_id"] for task in tasks] == ["trace-1", "trace-2"]


def test_summarize_evimedbench_cases_counts_dimensions_and_weights(tmp_path):
    dataset_path = tmp_path / "evimedbench.json"
    write_sample_evimedbench(dataset_path)

    summary = summarize_evimedbench_cases(load_evimedbench_cases(dataset_path))

    assert summary["case_count"] == 1
    assert summary["rubric_count"] == 2
    assert summary["grade_counts"] == {"G1": 1}
    assert summary["dimension_counts"]["问题相关性"] == 1
    assert summary["dimension_counts"]["证据回答一致性"] == 1
    assert summary["negative_weight_rubric_count"] == 1


def test_cli_exports_judge_tasks_as_jsonl(tmp_path, capsys):
    dataset_path = tmp_path / "evimedbench.json"
    answers_path = tmp_path / "answers.jsonl"
    write_sample_evimedbench(dataset_path)
    answers_path.write_text(
        json.dumps({"eval_id": "EVAL-001", "answer": "answer"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    assert main(["--cases", str(dataset_path), "--answers", str(answers_path)]) == 0

    output_lines = capsys.readouterr().out.splitlines()
    assert len(output_lines) == 1
    exported = json.loads(output_lines[0])
    assert exported["mode"] == "evimedbench_rubric_judge_task"
    assert exported["final_eval_id"] == "EVAL-001"


def test_cli_exports_judge_tasks_from_training_trace_jsonl(tmp_path, capsys):
    dataset_path = tmp_path / "evimedbench.json"
    traces_path = tmp_path / "traces.jsonl"
    write_sample_evimedbench(dataset_path)
    traces_path.write_text(
        json.dumps(
            {
                "trace_id": "trace-cli",
                "status": "completed",
                "runtime": "hermes",
                "run_id": "run-cli",
                "model": "innovation",
                "labels": {"final_eval_id": "EVAL-001"},
                "messages": [],
                "final_output": "answer from trace",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    assert main(["--cases", str(dataset_path), "--traces", str(traces_path)]) == 0

    output_lines = capsys.readouterr().out.splitlines()
    assert len(output_lines) == 1
    exported = json.loads(output_lines[0])
    assert exported["answer"] == "answer from trace"
    assert exported["answer_meta"]["trace_id"] == "trace-cli"
    assert exported["answer_meta"]["source"] == "training_trace"


def test_extract_evimedbench_answer_records_from_training_traces_matches_question_text(tmp_path):
    dataset_path = tmp_path / "evimedbench.json"
    write_sample_evimedbench(dataset_path)
    cases = load_evimedbench_cases(dataset_path)
    traces = [
        {
            "trace_id": "trace-1",
            "source": "model_chat",
            "created_at": "2026-05-18T00:00:00+00:00",
            "runtime": "hermes",
            "run_id": "run-1",
            "model": "innovation",
            "status": "completed",
            "messages": [
                {"role": "system", "content": "你是医学助手。"},
                {
                    "role": "user",
                    "content": " 对于新诊断的2型糖尿病患者，二甲双胍是否应作为首选降糖药物？\n",
                },
            ],
            "final_output": "二甲双胍通常可作为首选，但应结合禁忌证、肾功能和个体化风险。",
        }
    ]

    answers = extract_evimedbench_answer_records_from_traces(cases, traces)

    assert answers == [
        {
            "eval_id": "内分泌代谢_01",
            "final_eval_id": "EVAL-001",
            "answer": "二甲双胍通常可作为首选，但应结合禁忌证、肾功能和个体化风险。",
            "trace_id": "trace-1",
            "run_id": "run-1",
            "model": "innovation",
            "runtime": "hermes",
            "source": "training_trace",
            "trace_source": "model_chat",
            "created_at": "2026-05-18T00:00:00+00:00",
        }
    ]
    tasks = build_evimedbench_judge_tasks(cases, answers)
    assert len(tasks) == 1
    assert tasks[0]["answer_meta"]["source"] == "training_trace"


def test_extract_evimedbench_answer_records_skips_incomplete_or_empty_traces(tmp_path):
    dataset_path = tmp_path / "evimedbench.json"
    write_sample_evimedbench(dataset_path)
    cases = load_evimedbench_cases(dataset_path)
    traces = [
        {
            "trace_id": "trace-failed",
            "status": "stream_error",
            "labels": {"final_eval_id": "EVAL-001"},
            "messages": [],
            "final_output": "partial answer",
        },
        {
            "trace_id": "trace-empty",
            "status": "completed",
            "labels": {"final_eval_id": "EVAL-001"},
            "messages": [],
            "final_output": " ",
        },
    ]

    answers = extract_evimedbench_answer_records_from_traces(cases, traces)

    assert answers == []
