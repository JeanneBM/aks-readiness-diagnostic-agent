"""Post-hoc citation review of preserved responses; never invokes a provider."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from readiness_agent.evaluation import load_cases, score
from readiness_agent.models import Diagnosis


def rescore(source, cases_path, rubric, output):
    cases = {case_id: (bundle, truth) for case_id, bundle, truth in load_cases(cases_path)}
    revised = json.loads((rubric / 'R003.json').read_text(encoding='utf-8'))
    original = cases['R003'][1]
    if {k: v for k, v in revised.items() if k not in ('required_evidence_ids', 'evidence_options')} != {
            k: v for k, v in original.items() if k not in ('required_evidence_ids', 'evidence_options')}:
        raise ValueError('Rubric revision must not alter ground truth or case metadata')
    rows = []
    hashes = {}
    for path in sorted(source.glob('R*-*.json')):
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        old = json.loads(path.read_text(encoding='utf-8'))
        bundle, truth = cases[old['case_id']]
        updated = revised if old['case_id'] == 'R003' else truth
        row = {k: old[k] for k in ('case_id', 'variant', 'repetition', 'status')}
        row['original_risk'] = old['diagnostic_risk']
        if old['status'] == 'OK':
            diagnosis = Diagnosis.parse(old['diagnosis'], bundle)
            row.update(score(diagnosis, updated))
        else:
            row.update(error_kind=old['error_kind'], diagnostic_risk=old['diagnostic_risk'])
        rows.append(row)
    if len(rows) != 72:
        raise ValueError('Expected all 72 historical attempts')
    variants = {}
    for variant in ('A1', 'C1', 'H'):
        selected = [r for r in rows if r['variant'] == variant]
        variants[variant] = dict(Counter({
            'attempts': len(selected),
            'correct_attempts': sum(r.get('cause_correct', False) for r in selected),
            'errors': sum(r['status'] == 'ERROR' for r in selected),
            'original_risk_attempts': sum(r['original_risk'] for r in selected),
            'revised_risk_attempts': sum(r['diagnostic_risk'] for r in selected),
            'citation_coverage_gaps': sum(r.get('citation_coverage_gap', False) for r in selected),
            'cause_mismatches': sum(r.get('cause_mismatch', False) for r in selected),
        }))
    result = {'analysis': 'post-hoc-rubric-v2', 'new_model_calls': 0,
              'changed_label_fields': {'R003': ['required_evidence_ids', 'evidence_options']},
              'rubric_sha256': hashlib.sha256((rubric / 'R003.json').read_bytes()).hexdigest(),
              'source_attempts_sha256': hashes, 'variants': variants, 'rows': rows}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    base = ROOT / 'eval/2026-11-05-kind-paired'
    result = rescore(base / 'sanitized', ROOT / 'data/recorded-dev/2026-11-02-kind',
                     base / 'rubric-v2', args.output)
    print(json.dumps(result['variants'], indent=2))
