"""Audit completed custom-license results without making API calls."""
import json
from collections import Counter
from scripts.run_custom_license_experiment import (
    OUT, INPUT, load_input, has_custom, prepare_row, case_id, report, save,
)
from license_checker.llm.client import extract_text
from license_checker.llm.schema import parse_result


def main():
    payload, _ = load_input(INPUT)
    selected = [(i, prepare_row(r)) for i, r in enumerate(payload['rows']) if has_custom(r)]
    expected = {case_id(r, i) for i, r in selected}
    assert {p.stem for p in (OUT / 'results').glob('*.json')} == expected
    entries = []
    for i, row in selected:
        cid = case_id(row, i)
        e = json.loads((OUT / 'results' / (cid + '.json')).read_text())
        assert e['row'] == row and e['source_csv_line'] == i + 2
        assert e['status'] in {'SUCCESS', 'ERROR', 'SKIPPED'}
        if e['status'] == 'SUCCESS':
            request = json.loads((OUT / 'requests' / (cid + '.json')).read_text())
            raw = json.loads((OUT / 'responses' / (cid + '.json')).read_text())
            meta = request['metadata']
            assert meta['example_count'] == 12
            assert parse_result(extract_text(raw), cid, meta['allowed_subjects'], meta['allowed_refs']) == e['analysis']
        for folder, field in [('license_license', 'license_license_findings'),
                              ('license_activity', 'license_behavior_findings'),
                              ('obligations', 'obligations')]:
            output = json.loads((OUT / 'three_outputs' / folder / (cid + '.json')).read_text())
            assert output['case_id'] == cid
            assert output['output'] == (e['analysis'][field] if e['status'] == 'SUCCESS' else None)
        entries.append(e)
    for folder in ('license_license', 'license_activity', 'obligations'):
        assert {p.stem for p in (OUT / 'three_outputs' / folder).glob('*.json')} == expected
    for path in (OUT / 'requests').glob('*.json'):
        assert json.loads(path.read_text())['metadata']['example_count'] == 12
    report(entries)
    verification = {
        'selected_relationships': len(entries),
        'status': dict(Counter(e['status'] for e in entries)),
        'request_count': len(list((OUT / 'requests').glob('*.json'))),
        'raw_response_count': len(list((OUT / 'responses').glob('*.json'))),
        'reported_models': dict(Counter(e['reported_model'] for e in entries if e['status'] == 'SUCCESS')),
        'input_identity_and_three_outputs_verified': True,
        'successful_results_reparsed_against_contract': True,
        'all_requests_have_12_figure10_cases': True,
    }
    save(OUT / 'verification.json', verification)
    print(json.dumps(verification, ensure_ascii=False))


if __name__ == '__main__':
    main()
