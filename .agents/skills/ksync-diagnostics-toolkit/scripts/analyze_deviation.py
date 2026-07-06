#!/usr/bin/env python3
"""
kSync deviation-CSV analyzer. Stdlib only (matplotlib optional for --plot).

Usage:
  python3 analyze_deviation.py logs/sync_deviation.csv [--goal-ms 50] [--plot out.png]

CSV columns (collaborator._log_deviation):
  timestamp,leader_time,video_pos,deviation,rate,hard_seeks
"""
import argparse
import csv
import statistics
import sys


def percentile(sorted_vals, p):
    if not sorted_vals:
        return float("nan")
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def main():
    ap = argparse.ArgumentParser(description="Analyze kSync sync_deviation.csv")
    ap.add_argument("csv_path")
    ap.add_argument("--goal-ms", type=float, default=50.0,
                    help="acceptance threshold for |deviation| p95 (default 50; use 10 for netclock goal)")
    ap.add_argument("--settle-s", type=float, default=10.0,
                    help="ignore the first N seconds (startup convergence, default 10)")
    ap.add_argument("--plot", metavar="OUT.png", help="write a deviation plot (needs matplotlib)")
    args = ap.parse_args()

    rows = []
    with open(args.csv_path, newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header and header[0] != "timestamp":
            f.seek(0)
            reader = csv.reader(f)
        for r in reader:
            if len(r) < 6:
                continue
            try:
                rows.append((float(r[0]), float(r[1]), float(r[2]),
                             float(r[3]), float(r[4]), int(r[5])))
            except ValueError:
                continue

    if len(rows) < 10:
        print(f"ERROR: only {len(rows)} usable rows — not enough to judge anything.")
        return 2

    t0, t_end = rows[0][0], rows[-1][0]
    span = t_end - t0
    settled = [r for r in rows if r[0] - t0 >= args.settle_s]
    if len(settled) < 10:
        print(f"ERROR: fewer than 10 rows after the {args.settle_s}s settle window.")
        return 2

    devs = [r[3] for r in settled]
    abs_devs = sorted(abs(d) for d in devs)
    rates = [r[4] for r in settled]

    # Hard-seek events: counter increments
    seek_events = []
    prev = rows[0][5]
    for r in rows:
        if r[5] > prev:
            seek_events.append((r[0] - t0, r[5]))
        prev = r[5]
    settled_seeks = [e for e in seek_events if e[0] >= args.settle_s]

    # Loop seams: leader_time wrapping backwards by a large amount
    seams = sum(1 for a, b in zip(settled, settled[1:]) if b[1] - a[1] < -5.0)

    # Rate clamp occupancy (against observed extremes)
    rate_lo, rate_hi = min(rates), max(rates)
    at_hi = sum(1 for x in rates if abs(x - rate_hi) < 1e-4) / len(rates) if rate_hi > 1.0005 else 0.0
    at_lo = sum(1 for x in rates if abs(x - rate_lo) < 1e-4) / len(rates) if rate_lo < 0.9995 else 0.0

    print(f"file            : {args.csv_path}")
    print(f"rows            : {len(rows)} total, {len(settled)} after {args.settle_s}s settle")
    print(f"span            : {span:.1f}s  ({len(rows)/span:.1f} samples/s)")
    print(f"deviation (settled, seconds):")
    print(f"  mean/median   : {statistics.mean(devs):+.4f} / {statistics.median(devs):+.4f}")
    print(f"  |dev| p50/p95/max : {percentile(abs_devs,50)*1000:.1f} / "
          f"{percentile(abs_devs,95)*1000:.1f} / {abs_devs[-1]*1000:.1f} ms")
    print(f"rate            : min {rate_lo:.4f}  max {rate_hi:.4f}"
          f"  time-at-max {at_hi*100:.0f}%  time-at-min {at_lo*100:.0f}%")
    print(f"hard seeks      : {len(seek_events)} total, {len(settled_seeks)} after settle"
          + (f"  (last at t+{seek_events[-1][0]:.1f}s)" if seek_events else ""))
    print(f"loop seams seen : {seams}")

    p95_ms = percentile(abs_devs, 95) * 1000
    verdict_fail = []
    if p95_ms > args.goal_ms:
        verdict_fail.append(f"|dev| p95 {p95_ms:.1f}ms > goal {args.goal_ms}ms")
    if settled_seeks:
        verdict_fail.append(f"{len(settled_seeks)} hard seeks after settle (expect 0)")
    if at_hi > 0.5:
        verdict_fail.append(f"rate pinned at max {at_hi*100:.0f}% of the time (decoder can't keep up?)")

    if verdict_fail:
        print("VERDICT: FAIL — " + "; ".join(verdict_fail))
    else:
        print(f"VERDICT: PASS — |dev| p95 {p95_ms:.1f}ms ≤ {args.goal_ms}ms, no post-settle hard seeks")

    if args.plot:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            ts = [r[0] - t0 for r in rows]
            ds = [r[3] * 1000 for r in rows]
            fig, ax = plt.subplots(figsize=(12, 4))
            ax.plot(ts, ds, linewidth=0.6)
            ax.axhline(args.goal_ms, color="r", ls="--", lw=0.8)
            ax.axhline(-args.goal_ms, color="r", ls="--", lw=0.8)
            ax.set_xlabel("t (s)"); ax.set_ylabel("deviation (ms)")
            ax.set_title(args.csv_path)
            fig.tight_layout(); fig.savefig(args.plot, dpi=120)
            print(f"plot written    : {args.plot}")
        except ImportError:
            print("plot skipped    : matplotlib not installed")

    return 1 if verdict_fail else 0


if __name__ == "__main__":
    sys.exit(main())
