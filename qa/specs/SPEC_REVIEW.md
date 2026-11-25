# Specification review

Vague requirement: *"Report the transmitter's location when the evidence is strong enough."*

Questions raised by gpt-5.4-mini; mapped to `qa/specs/requirements.toml` by gpt-4.1-mini. A person decides the open ones.

| # | question | testable criterion | answered by |
|---|---|---|---|
| 1 | What does “strong enough” mean quantitatively, and what confidence threshold is required before reporting a location? | The requirement specifies a measurable confidence rule, such as: report only when posterior probability of the estimated location is at least X% and/or the 95% confidence radius is no more than Y km. | REQ-GATE-002 |
| 2 | What form should the reported location take: a point estimate, an uncertainty region, or both? | The output definition states whether the system must emit latitude/longitude only, a bounding polygon/circle, a confidence ellipse, or a combination, and the exact fields are present in every report. | **open: a product decision** |
| 3 | How accurate must the reported location be to be considered correct? | The requirement includes a maximum allowable error, such as median horizontal error ≤ X meters or 95% of reports within Y meters of truth under defined conditions. | **open: a product decision** |
| 4 | What minimum evidence inputs are required, such as number of aircraft passes, number of echoes, or spatial/temporal diversity of reports? | The requirement states minimum observation criteria, for example: at least N echoes from at least M distinct aircraft positions separated by at least D meters or T seconds. | REQ-GATE-003, REQ-TRK-001 |
| 5 | How should the system handle conflicting, noisy, missing, or duplicate aircraft position reports? | The requirement defines acceptance/rejection rules for invalid, duplicate, stale, or inconsistent reports, and test cases can verify that such inputs are ignored or weighted according to those rules. | REQ-GATE-003 |
| 6 | What latency is acceptable between receiving evidence and issuing the location report? | The requirement specifies a maximum end-to-end delay, such as: once the evidence threshold is met, the system must publish the location within X seconds. | **open: a product decision** |
| 7 | Should the system produce one report and stop, or continue updating the location as more evidence arrives? | The requirement states whether outputs are one-time, periodic, or event-driven updates, and defines whether later evidence can revise a prior report and under what conditions. | **open: a product decision** |
| 8 | What are the boundaries of the operating conditions in which the requirement applies, such as aircraft speed/altitude, receiver coverage, terrain, or transmitter motion? | The requirement lists explicit operating assumptions and exclusions, such as supported altitude range, allowed transmitter motion rate, terrain constraints, and receiver coverage geometry, with tests only required within that envelope. | REQ-GEO-002, REQ-GEO-003, REQ-PIPE-001, REQ-PIPE-002 |

4 of 8 questions are settled by a written requirement; 4 are open.

Why each question matters:

1. Without a numeric decision threshold, the system could under-report or over-report depending on interpretation, making behavior impossible to verify consistently.
2. A single point and an area of probable location serve different operational needs and require different algorithms; the output format changes what counts as success.
3. “Location” is vague unless bounded by an error tolerance; otherwise there is no way to determine whether the system’s estimate is acceptable.
4. The system may need multiple independent observations to triangulate; without minimum input conditions, it is unclear when reporting is even permitted.
5. Real-world position reports are imperfect; the location estimate depends heavily on filtering and data quality rules.
6. A correct estimate that arrives too late may be operationally useless; timeliness is part of the product behavior.
7. The reporting policy affects user expectations, downstream automation, and whether successive outputs can change over time.
8. The same evidence may be valid in one environment and misleading in another; without scope limits, it is unclear when the system is expected to work.
