"""Tests for the offline DDI eval seed used by training-data PoCs."""

from app.training_eval.ddi import (
    DdiEvalCase,
    DdiPrediction,
    DdiStructuredPrediction,
    evaluate_structured_prediction_records,
    evaluate_trace_records,
    extract_ddi_predictions_from_trace_records,
    load_default_ddi_eval_cases,
    score_ddi_prediction,
    score_structured_ddi_prediction,
    summarize_ddi_scores,
)


def test_default_ddi_eval_cases_are_synthetic_and_structured():
    cases = load_default_ddi_eval_cases()

    assert len(cases) >= 3
    assert {case.case_id for case in cases} >= {
        "ddi-warfarin-aspirin",
        "ddi-simvastatin-clarithromycin",
        "ddi-lisinopril-spironolactone",
    }
    assert all(case.privacy_level == "synthetic_public" for case in cases)
    assert all(case.expected_drugs for case in cases)
    assert all(case.expected_severity for case in cases)
    assert all(case.expected_risk_terms for case in cases)
    assert all(case.expected_actions for case in cases)
    assert all(case.expected_interaction is True for case in cases)


def test_score_ddi_prediction_checks_key_step_level_signals():
    case = DdiEvalCase(
        case_id="ddi-warfarin-aspirin",
        prompt="Assess the interaction between warfarin and aspirin.",
        expected_drugs=("warfarin", "aspirin"),
        expected_severity="major",
        expected_risk_terms=("bleeding",),
        expected_actions=("monitor", "clinician"),
        reference="synthetic_seed_v0",
        privacy_level="synthetic_public",
    )
    prediction = DdiPrediction(
        case_id="ddi-warfarin-aspirin",
        drugs=("Warfarin", "Aspirin"),
        severity="Major",
        answer=(
            "This is a major interaction because combined anticoagulant and "
            "antiplatelet exposure can increase bleeding risk. Monitor closely "
            "and involve a clinician before changing therapy."
        ),
    )

    score = score_ddi_prediction(case, prediction)

    assert score.case_id == "ddi-warfarin-aspirin"
    assert score.drug_match is True
    assert score.severity_match is True
    assert score.risk_terms_present is True
    assert score.safe_action_present is True
    assert score.score == 1.0
    assert score.missing_signals == ()


def test_score_ddi_prediction_reports_missing_signals():
    case = load_default_ddi_eval_cases()[0]
    prediction = DdiPrediction(
        case_id=case.case_id,
        drugs=(case.expected_drugs[0],),
        severity="minor",
        answer="No special issue.",
    )

    score = score_ddi_prediction(case, prediction)

    assert score.score < 1.0
    assert score.drug_match is False
    assert score.severity_match is False
    assert "drug_match" in score.missing_signals
    assert "severity_match" in score.missing_signals


def test_summarize_ddi_scores_returns_baseline_metrics():
    cases = load_default_ddi_eval_cases()
    perfect_scores = [
        score_ddi_prediction(
            case,
            DdiPrediction(
                case_id=case.case_id,
                drugs=case.expected_drugs,
                severity=case.expected_severity,
                answer=" ".join((*case.expected_risk_terms, *case.expected_actions)),
            ),
        )
        for case in cases
    ]

    summary = summarize_ddi_scores(perfect_scores)

    assert summary["case_count"] == len(cases)
    assert summary["average_score"] == 1.0
    assert summary["drug_match_rate"] == 1.0
    assert summary["severity_match_rate"] == 1.0
    assert summary["risk_terms_present_rate"] == 1.0
    assert summary["safe_action_present_rate"] == 1.0


def test_extract_ddi_predictions_from_completed_model_chat_trace():
    trace_record = {
        "source": "model_chat",
        "status": "completed",
        "messages": [
            {
                "role": "user",
                "content": "Assess the interaction risk for warfarin and aspirin.",
            }
        ],
        "tool_events": [{"event": "tool.completed", "tool": "ddi"}],
        "final_output": (
            "This is a major interaction with increased bleeding risk. "
            "Monitor closely and involve a clinician."
        ),
    }

    predictions = extract_ddi_predictions_from_trace_records([trace_record])

    assert len(predictions) == 1
    assert predictions[0].case_id == "ddi-warfarin-aspirin"
    assert predictions[0].drugs == ("warfarin", "aspirin")
    assert predictions[0].severity == "major"
    assert "bleeding risk" in predictions[0].answer


def test_evaluate_trace_records_skips_unmatched_or_incomplete_traces():
    trace_records = [
        {
            "source": "model_chat",
            "status": "completed",
            "messages": [{"role": "user", "content": "General medical question."}],
            "final_output": "No drug pair is present.",
        },
        {
            "source": "model_chat",
            "status": "failed",
            "messages": [{"role": "user", "content": "warfarin and aspirin"}],
            "final_output": "major bleeding risk monitor clinician",
        },
        {
            "source": "model_chat",
            "status": "completed",
            "messages": [{"role": "user", "content": "warfarin and aspirin"}],
            "final_output": "major bleeding risk monitor clinician",
        },
    ]

    result = evaluate_trace_records(trace_records)

    assert result["mode"] == "trace_smoke"
    assert "not_medical_eval" in result["limitations"]
    assert result["summary"]["case_count"] == 1
    assert result["summary"]["average_score"] == 1.0
    assert result["extracted_prediction_count"] == 1


def test_structured_ddi_baseline_scores_fields_without_free_text_guessing():
    case = DdiEvalCase(
        case_id="ddi-warfarin-aspirin",
        prompt="Assess the interaction between warfarin and aspirin.",
        expected_drugs=("warfarin", "aspirin"),
        expected_interaction=True,
        expected_severity="major",
        expected_risk_terms=("bleeding",),
        expected_actions=("monitor", "clinician"),
        reference="synthetic_seed_v0",
        privacy_level="synthetic_public",
    )
    prediction = DdiStructuredPrediction(
        case_id="ddi-warfarin-aspirin",
        drugs=("aspirin", "warfarin"),
        interaction_present=True,
        severity="major",
        risk_terms=("bleeding",),
        management_actions=("monitor",),
    )

    score = score_structured_ddi_prediction(case, prediction)

    assert score.case_id == "ddi-warfarin-aspirin"
    assert score.mode == "structured_baseline"
    assert score.drug_set_match is True
    assert score.interaction_match is True
    assert score.severity_match is True
    assert score.risk_terms_match is True
    assert score.management_match is True
    assert score.score == 1.0
    assert score.missing_signals == ()


def test_structured_ddi_baseline_rejects_keyword_stuffing_in_answer_text():
    case = load_default_ddi_eval_cases()[0]
    prediction = DdiStructuredPrediction(
        case_id=case.case_id,
        drugs=case.expected_drugs,
        interaction_present=False,
        severity="minor",
        risk_terms=(),
        management_actions=(),
        answer_text="major bleeding monitor clinician",
    )

    score = score_structured_ddi_prediction(case, prediction)

    assert score.score < 1.0
    assert score.interaction_match is False
    assert score.severity_match is False
    assert score.risk_terms_match is False
    assert score.management_match is False
    assert "interaction_match" in score.missing_signals
    assert "severity_match" in score.missing_signals


def test_evaluate_structured_prediction_records_returns_baseline_metrics():
    cases = load_default_ddi_eval_cases()
    prediction_records = [
        {
            "case_id": case.case_id,
            "drugs": list(case.expected_drugs),
            "interaction_present": case.expected_interaction,
            "severity": case.expected_severity,
            "risk_terms": list(case.expected_risk_terms),
            "management_actions": [case.expected_actions[0]],
        }
        for case in cases
    ]

    result = evaluate_structured_prediction_records(prediction_records)

    assert result["mode"] == "structured_baseline"
    assert result["summary"]["case_count"] == len(cases)
    assert result["summary"]["average_score"] == 1.0
    assert result["summary"]["interaction_match_rate"] == 1.0
    assert result["unknown_case_ids"] == []
