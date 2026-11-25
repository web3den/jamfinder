# N-version programming: the reporting rule written twice

Second version: gpt-5.4-mini, from the written definition only (`qa/differential/nversion_generated.py`). Compared with `jf/rules.py` on generated inputs.

| output | agreement | smallest input where they differ | jf/rules.py | second version |
|---|---|---|---|---|
| a_flip | **differs** | `{'cands': [[0.0, 0.0, 0.0, 0.0]], 'nulls': [{'kind': 'flip', 'best': 0.0, 'verdict': 'nothing', 'frac': 0.0}], 'residual': 0.0}` | False | True |
| b | **differs** | `{'cands': [[0.0, 0.0, 0.0, 0.0]], 'nulls': [{'kind': 'flip', 'best': 0.0, 'verdict': 'nothing', 'degenerate': True}], 'residual': 0.0}` | False | True |
| c | **differs** | `{'cands': [[0.0, 0.0, 0.0, 0.0]], 'nulls': [{'kind': 'flip', 'best': 1.0, 'verdict': 'nothing', 'degenerate': True}], 'residual': 0.0}` | False | True |
| d | **differs** | `{'cands': [[1.0, 0.0, 0.0, 0.0]], 'nulls': [{'kind': 'flip', 'best': 0.0, 'verdict': 'nothing', 'frac': 0.0}], 'residual': 0.0}` | True | False |
| v32 | **differs** | `{'cands': [[3.0, 0.0, 0.0, 0.0]], 'nulls': [{'kind': 'flip', 'best': 1.0, 'verdict': 'nothing', 'frac': 1.0}], 'residual': 0.0}` | one | nothing |
