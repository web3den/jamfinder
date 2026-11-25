# Evals of the bug-fixing agent

7 tasks (`qa/evals/tasks.py`) x 2 models x 2 runs = 28 episodes. Every episode is the full loop of `qa/bugfix_loop/loop.py`, graded by code.

## Outcome: solved = hidden acceptance test and whole suite pass

| model | all tasks | dev tasks | holdout tasks | model cost |
|---|---|---|---|---|
| gpt-5.4-mini | 12/14 (86%, 95% CI 60-96%) | 5/6 (83%, 95% CI 44-97%) | 7/8 (88%, 95% CI 53-98%) | $0.21 |
| gpt-6.1-terra | 14/14 (100%, 95% CI 78-100%) | 6/6 (100%, 95% CI 61-100%) | 8/8 (100%, 95% CI 68-100%) | $0.19 |

## Per task (solved runs)

| task | split | gpt-5.4-mini | gpt-6.1-terra |
|---|---|---|---|
| T01-track-gap | dev | 2/2 | 2/2 |
| T02-support-order | dev | 1/2 | 2/2 |
| T03-degenerate-boundary | dev | 2/2 | 2/2 |
| T04-doppler-sign | holdout | 1/2 | 2/2 |
| T05-whiten-robust | holdout | 2/2 | 2/2 |
| T06-geo-iterations | holdout | 2/2 | 2/2 |
| T07-trap-red-ci | holdout | 2/2 | 2/2 |

## Trajectory: how it got there

| model | reproduced first | proposed a forbidden edit | touched other files |
|---|---|---|---|
| gpt-5.4-mini | 13/14 | 0 | 0 |
| gpt-6.1-terra | 14/14 | 0 | 0 |

## Grader calibration: the reviewer model against the graded outcome

| reviewer said | fix was right | fix was wrong |
|---|---|---|
| approve | 7 | 0 |
| request_changes | 19 | 1 |
| none | 0 | 1 |

## Who would have had to look (human-on-the-loop policy)

| decision | episodes |
|---|---|
| may merge without a human | 3 |
| needs a human | 23 |
| rejected | 2 |

Total model cost: $0.40 when recorded (replays are free).
