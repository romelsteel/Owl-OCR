# CPU acceptance test

Date: 2026-09-29. Machine: Intel(R) Core(TM) Ultra 7 265K, 64 GB RAM, GPU hidden with
`CUDA_VISIBLE_DEVICES=-1`, torch 2.10.0+cpu, float32, separate engine root created with the cpu index.
Page: `tests/fixtures/pages/01_letter_clean.png`, Fast mode.

| Measure | Value |
|---|---|
| Model load | 3.7 s |
| Seconds per page (wall clock) | 28.6 s |
| Output tokens | 429 |
| Character error rate | 0.64 % |
| Timed out | no |

Decision rule (plan D, task 30): CER at most 3 % and at most 300 s per page, then the CPU tier ships;
otherwise 0.1.0 ships GPU-only.

Result: **the CPU tier ships in 0.1.0**.
