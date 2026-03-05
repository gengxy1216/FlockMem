from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]

METHOD_PROFILE: dict[str, dict[str, str]] = {
    "keyword": {"decision_mode": "static", "ingest_profile": "keyword"},
    "vector": {"decision_mode": "static", "ingest_profile": "hybrid"},
    "hybrid": {"decision_mode": "static", "ingest_profile": "hybrid"},
    "agentic": {"decision_mode": "rule", "ingest_profile": "hybrid"},
}


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(round((len(ordered) - 1) * p))
    idx = max(0, min(len(ordered) - 1, idx))
    return float(ordered[idx])


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in value)


def _extract_case_latency_stats(report: dict[str, Any]) -> dict[str, float]:
    cases = report.get("cases")
    if not isinstance(cases, list):
        return {"case_p50_ms": 0.0, "case_p95_ms": 0.0}
    latencies: list[float] = []
    for row in cases:
        if not isinstance(row, dict):
            continue
        if row.get("skipped"):
            continue
        value = row.get("case_ms")
        try:
            latencies.append(float(value))
        except Exception:
            continue
    return {
        "case_p50_ms": round(_percentile(latencies, 0.50), 3),
        "case_p95_ms": round(_percentile(latencies, 0.95), 3),
    }


def _build_command(
    *,
    dataset: Path,
    report_path: Path,
    data_dir: Path,
    method: str,
    decision_mode: str,
    ingest_profile: str,
    top_k: int,
    sample_size: int,
    sample_seed: int,
    isolate_by_case: bool,
) -> list[str]:
    command = [
        sys.executable,
        str(ROOT_DIR / "tools" / "run_locomo_eval.py"),
        "--dataset",
        str(dataset),
        "--top-k",
        str(top_k),
        "--sample-size",
        str(sample_size),
        "--sample-seed",
        str(sample_seed),
        "--method",
        method,
        "--decision-mode",
        decision_mode,
        "--ingest-profile",
        ingest_profile,
        "--data-dir",
        str(data_dir),
        "--report-out",
        str(report_path),
    ]
    if isolate_by_case:
        command.append("--isolate-by-case")
    return command


def _run_once(
    *,
    dataset: Path,
    method: str,
    round_id: int,
    seed: int,
    top_k: int,
    sample_size: int,
    output_dir: Path,
    isolate_by_case: bool,
    force_local_embedding: bool,
) -> dict[str, Any]:
    profile = METHOD_PROFILE.get(method)
    if profile is None:
        raise ValueError(f"unsupported method: {method}")

    tag = f"r{round_id:02d}-{_safe_name(method)}-seed{seed}"
    report_path = output_dir / f"locomo-{tag}.json"
    data_dir = output_dir / "runtime" / tag
    data_dir.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    command = _build_command(
        dataset=dataset,
        report_path=report_path,
        data_dir=data_dir,
        method=method,
        decision_mode=profile["decision_mode"],
        ingest_profile=profile["ingest_profile"],
        top_k=top_k,
        sample_size=sample_size,
        sample_seed=seed,
        isolate_by_case=isolate_by_case,
    )
    env = dict(os.environ)
    if force_local_embedding:
        env.update(
            {
                "LITE_EMBEDDING_PROVIDER": "local",
                "LITE_EMBEDDING_MODEL": "local-hash-384",
            }
        )

    started = time.perf_counter()
    proc = subprocess.run(
        command,
        cwd=str(ROOT_DIR),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
    if proc.returncode != 0:
        raise RuntimeError(
            f"run failed ({method}, round={round_id}, seed={seed})\n"
            f"exit={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    if not report_path.exists():
        raise RuntimeError(
            f"run completed but report file missing: {report_path}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    metrics = {
        "round": round_id,
        "seed": seed,
        "method": method,
        "decision_mode": profile["decision_mode"],
        "ingest_profile": profile["ingest_profile"],
        "report_path": str(report_path),
        "runtime_ms": elapsed_ms,
        "evaluated_cases": int(report.get("evaluated_cases", 0)),
        "recall_at_k": float(report.get("recall_at_k", 0.0)),
        "mrr": float(report.get("mrr", 0.0)),
        "ms_case_avg": float(report.get("ms_case_avg", 0.0)),
    }
    metrics.update(_extract_case_latency_stats(report))
    return metrics


def _summarize(results: list[dict[str, Any]], methods: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for method in methods:
        rows = [x for x in results if x.get("method") == method]
        recalls = [float(x["recall_at_k"]) for x in rows]
        mrrs = [float(x["mrr"]) for x in rows]
        p50s = [float(x["case_p50_ms"]) for x in rows]
        p95s = [float(x["case_p95_ms"]) for x in rows]
        case_avg = [float(x["ms_case_avg"]) for x in rows]
        out[method] = {
            "rounds": len(rows),
            "recall_at_k_avg": round(statistics.mean(recalls), 4) if recalls else 0.0,
            "mrr_avg": round(statistics.mean(mrrs), 4) if mrrs else 0.0,
            "case_p50_ms_avg": round(statistics.mean(p50s), 3) if p50s else 0.0,
            "case_p95_ms_avg": round(statistics.mean(p95s), 3) if p95s else 0.0,
            "case_avg_ms_avg": round(statistics.mean(case_avg), 3) if case_avg else 0.0,
        }
    return out


def run_compare(
    *,
    dataset: Path,
    methods: list[str],
    rounds: int,
    seed_base: int,
    top_k: int,
    sample_size: int,
    output_dir: Path,
    isolate_by_case: bool,
    force_local_embedding: bool,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    runs: list[dict[str, Any]] = []
    for round_id in range(1, rounds + 1):
        for method in methods:
            seed = seed_base + round_id - 1
            runs.append(
                _run_once(
                    dataset=dataset,
                    method=method,
                    round_id=round_id,
                    seed=seed,
                    top_k=top_k,
                    sample_size=sample_size,
                    output_dir=output_dir,
                    isolate_by_case=isolate_by_case,
                    force_local_embedding=force_local_embedding,
                )
            )
    return {
        "dataset": str(dataset),
        "methods": methods,
        "rounds": rounds,
        "seed_base": seed_base,
        "top_k": top_k,
        "sample_size": sample_size,
        "isolate_by_case": isolate_by_case,
        "force_local_embedding": force_local_embedding,
        "runs": runs,
        "summary": _summarize(runs, methods),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run multi-round LoCoMo risk comparison across retrieval methods."
    )
    parser.add_argument("--dataset", required=True, help="Prepared LoCoMo eval jsonl.")
    parser.add_argument(
        "--methods",
        default="keyword,agentic,vector,hybrid",
        help="Comma separated methods from: keyword,agentic,vector,hybrid",
    )
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--seed-base", type=int, default=42)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--sample-size", type=int, default=120)
    parser.add_argument(
        "--output-dir",
        default="tools/perf/results",
        help="Directory for per-run and summary reports.",
    )
    parser.add_argument("--isolate-by-case", action="store_true")
    parser.add_argument("--force-local-embedding", action="store_true")
    parser.add_argument("--report-out", default="")
    args = parser.parse_args()

    dataset = Path(args.dataset).resolve()
    if not dataset.exists():
        raise SystemExit(f"dataset not found: {dataset}")

    methods = [m.strip() for m in str(args.methods).split(",") if m.strip()]
    if not methods:
        methods = ["keyword", "agentic", "vector", "hybrid"]
    invalid = [m for m in methods if m not in METHOD_PROFILE]
    if invalid:
        raise SystemExit(f"unsupported methods: {invalid}")

    report = run_compare(
        dataset=dataset,
        methods=methods,
        rounds=max(1, int(args.rounds)),
        seed_base=int(args.seed_base),
        top_k=max(1, int(args.top_k)),
        sample_size=max(0, int(args.sample_size)),
        output_dir=Path(args.output_dir).resolve(),
        isolate_by_case=bool(args.isolate_by_case),
        force_local_embedding=bool(args.force_local_embedding),
    )

    out_path_text = str(args.report_out).strip()
    if out_path_text:
        out_path = Path(out_path_text).resolve()
    else:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        out_path = Path(args.output_dir).resolve() / f"locomo-risk-compare-{stamp}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
