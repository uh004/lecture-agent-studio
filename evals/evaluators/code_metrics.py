from __future__ import annotations

import re
import unicodedata
from collections import Counter
from itertools import zip_longest
from typing import Any, Dict, Iterable, List, Sequence, Tuple


def safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    return numerator / denominator if denominator else default


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def _tokens(value: Any) -> List[str]:
    return re.findall(r"[가-힣A-Za-z0-9]+", normalize_text(value).lower())


def token_prf(expected: Any, actual: Any) -> Dict[str, float]:
    expected_tokens = Counter(_tokens(expected))
    actual_tokens = Counter(_tokens(actual))
    overlap = sum((expected_tokens & actual_tokens).values())
    expected_count = sum(expected_tokens.values())
    actual_count = sum(actual_tokens.values())
    precision = safe_div(overlap, actual_count, 1.0 if expected_count == 0 else 0.0)
    recall = safe_div(overlap, expected_count, 1.0 if actual_count == 0 else 0.0)
    f1 = safe_div(2 * precision * recall, precision + recall)
    return {"precision": precision, "recall": recall, "f1": f1}


def _flatten_scalars(value: Any) -> List[str]:
    if isinstance(value, dict):
        flattened: List[str] = []
        for key in sorted(value):
            flattened.extend(_flatten_scalars(value[key]))
        return flattened
    if isinstance(value, (list, tuple)):
        flattened = []
        for item in value:
            flattened.extend(_flatten_scalars(item))
        return flattened
    return [normalize_text(value)]


def positional_accuracy(expected: Sequence[Any], actual: Sequence[Any]) -> float:
    expected_values = [normalize_text(value) for value in expected]
    actual_values = [normalize_text(value) for value in actual]
    total = max(len(expected_values), len(actual_values))
    if total == 0:
        return 1.0
    matches = sum(
        expected_value == actual_value
        for expected_value, actual_value in zip_longest(expected_values, actual_values, fillvalue=None)
    )
    return matches / total


def evaluate_parser(reference: Dict[str, Any], actual: Dict[str, Any]) -> Dict[str, float]:
    expected_title = normalize_text(reference.get("title", ""))
    actual_title = normalize_text(actual.get("title", ""))
    expected_text = normalize_text(reference.get("text", ""))
    actual_text = normalize_text(actual.get("text", actual.get("body_text", "")))

    text_scores = token_prf(expected_text, actual_text)
    expected_table_cells = _flatten_scalars(reference.get("tables", []))
    actual_table_cells = _flatten_scalars(actual.get("tables", []))
    table_accuracy = positional_accuracy(expected_table_cells, actual_table_cells)

    expected_image_count = int(reference.get("image_count", 0) or 0)
    if "image_count" in actual:
        actual_image_count = int(actual.get("image_count", 0) or 0)
    else:
        actual_image_count = len(actual.get("images", []) or [])
    image_success_rate = (
        1.0
        if expected_image_count == 0 and actual_image_count == 0
        else safe_div(min(actual_image_count, expected_image_count), expected_image_count)
    )
    image_count_accuracy = float(expected_image_count == actual_image_count)
    extraction_error_free = float(not (actual.get("extraction_errors", []) or []))

    metrics = {
        "parser_title_exact": float(expected_title == actual_title),
        "parser_text_exact": float(expected_text == actual_text),
        "parser_text_precision": text_scores["precision"],
        "parser_text_recall": text_scores["recall"],
        "parser_text_f1": text_scores["f1"],
        "parser_table_cell_accuracy": table_accuracy,
        "parser_image_extraction_success_rate": image_success_rate,
        "parser_image_count_accuracy": image_count_accuracy,
        "parser_extraction_error_free": extraction_error_free,
    }
    metrics["parser_slide_success"] = float(
        metrics["parser_title_exact"] == 1.0
        and metrics["parser_text_exact"] == 1.0
        and table_accuracy == 1.0
        and image_count_accuracy == 1.0
        and extraction_error_free == 1.0
    )
    return metrics


def aggregate_binary_classification(
    pairs: Iterable[Tuple[bool, bool]], positive_value: bool = True
) -> Dict[str, float]:
    tp = fp = tn = fn = 0
    for expected, actual in pairs:
        if expected == positive_value and actual == positive_value:
            tp += 1
        elif expected != positive_value and actual == positive_value:
            fp += 1
        elif expected != positive_value and actual != positive_value:
            tn += 1
        else:
            fn += 1

    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    f1 = safe_div(2 * precision * recall, precision + recall)
    total = tp + fp + tn + fn
    return {
        "accuracy": safe_div(tp + tn, total),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_positive_rate": safe_div(fp, fp + tn),
        "false_negative_rate": safe_div(fn, fn + tp),
        "tp": float(tp),
        "fp": float(fp),
        "tn": float(tn),
        "fn": float(fn),
        "cases": float(total),
    }


def aggregate_set_detection(
    pairs: Iterable[Tuple[Iterable[str], Iterable[str]]]
) -> Dict[str, float]:
    true_positive = false_positive = false_negative = 0
    for expected, actual in pairs:
        expected_set = {normalize_text(value) for value in expected if normalize_text(value)}
        actual_set = {normalize_text(value) for value in actual if normalize_text(value)}
        true_positive += len(expected_set & actual_set)
        false_positive += len(actual_set - expected_set)
        false_negative += len(expected_set - actual_set)

    precision = safe_div(true_positive, true_positive + false_positive)
    recall = safe_div(true_positive, true_positive + false_negative)
    f1 = safe_div(2 * precision * recall, precision + recall)
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": float(true_positive),
        "fp": float(false_positive),
        "fn": float(false_negative),
    }

