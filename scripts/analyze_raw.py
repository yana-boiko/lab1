"""Розбір сирих результатів прогонів (results/raw/*.csv).

Для кожного прогону рахує те, чого немає в runs.jsonl:
  - goodput: скільки відповідей 2xx завершилось за секунду вікна вимірювання;
  - розклад затримки на дві частини:
      очікування в генераторі = sent - scheduled (запит чекав вільного потоку),
      час на сервісі          = done - sent (мережа + nginx + сервіс + база);
  - закон Літтла з точною розбіжністю у відсотках.

Запуск: python scripts/analyze_raw.py   (результат також пишеться в results/analysis.csv)
"""
import csv
import glob
import os
import statistics

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
WARMUP, DURATION = 10.0, 30.0


def analyze(path):
    with open(path, newline="") as f:
        rows = [(float(r["scheduled_s"]), float(r["sent_s"]), float(r["done_s"]), int(r["status"]))
                for r in csv.DictReader(f)]
    w0, w1 = WARMUP, WARMUP + DURATION
    measured = [r for r in rows if w0 <= r[0] < w1]           # заплановані у вікні
    completed = [r for r in rows if w0 <= r[2] < w1]          # завершені у вікні
    sent = [r for r in rows if w0 <= r[1] < w1]               # відправлені у вікні

    lam = len(sent) / DURATION
    w_mean = statistics.mean(r[2] - r[1] for r in sent)
    l_meas = sum(max(0.0, min(r[2], w1) - max(r[1], w0)) for r in rows) / DURATION
    return {
        "run": os.path.basename(path)[:-4],
        "achieved_rps": round(len(completed) / DURATION, 1),
        "goodput_2xx_rps": round(sum(1 for r in completed if 200 <= r[3] < 300) / DURATION, 1),
        "timeouts_pct": round(100 * sum(1 for r in measured if r[3] == 0) / len(measured), 2),
        "wait_in_generator_p50_ms": round(statistics.median(r[1] - r[0] for r in measured) * 1000, 1),
        "service_time_p50_ms": round(statistics.median(r[2] - r[1] for r in measured) * 1000, 1),
        "total_latency_p50_ms": round(statistics.median(r[2] - r[0] for r in measured) * 1000, 1),
        "little_lambda": round(lam, 2),
        "little_W_s": round(w_mean, 5),
        "little_lambda_W": round(lam * w_mean, 4),
        "little_L_measured": round(l_meas, 4),
        "little_diff_pct": round(100 * abs(l_meas - lam * w_mean) / (lam * w_mean), 2),
    }


def main():
    rows = [analyze(p) for p in sorted(glob.glob(os.path.join(ROOT, "raw", "*.csv")))]
    out = os.path.join(ROOT, "analysis.csv")
    with open(out, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)
    keys = list(rows[0])
    print(" | ".join(keys))
    for r in rows:
        print(" | ".join(str(r[k]) for k in keys))
    print(f"\nЗбережено в {os.path.relpath(out)}")


if __name__ == "__main__":
    main()
