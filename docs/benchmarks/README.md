# ExecWeave performance benchmarks

ExecWeave keeps reference overhead measurements reproducible and separate from product claims. The committed `v0.6.0-github-actions` result was produced by the package benchmark workflow from an installed wheel, not from an editable source checkout.

## Reproduce

```bash
execweave-overhead \
  --iterations 7 \
  --strace auto \
  --output-json benchmark-results.json \
  --output-svg benchmark-overhead.svg
```

The benchmark workload performs fixed file read/write/hash operations plus short-lived Python subprocesses. It compares:

- `ExecWeave OFF`: the workload without collection.
- `Portable ON`: the cross-platform portable collector.
- `Strace ON`: the Linux syscall-backed reference collector, when `strace` is available.

The trade-off plot uses:

- **X-axis:** additional peak process-tree RSS in MB, low to high.
- **Y-axis:** runtime overhead in percent, low to high.
- **Bubble area:** median ExecWeave artifact size per run.
- **Preferred region:** lower-left.

## v0.6.0 reference result

Environment: GitHub Actions Ubuntu runner, Intel Xeon Platinum 8573C, 4 logical CPUs, Python 3.12.14, `n=7`.

| Profile | Median wall time | Runtime overhead | Additional peak RSS | Median artifacts/run |
| --- | ---: | ---: | ---: | ---: |
| ExecWeave OFF | 236.221 ms | 0.0% | 0.0 MB | 0 KB |
| Portable ON | 391.580 ms | 65.768% | 27.852 MB | 741.355 KB |
| Strace ON | 1226.076 ms | 419.038% | 37.653 MB | 572.838 KB |

Package artifacts from the same workflow were approximately 113 KB for the wheel and 198 KB for the source distribution. The installed ExecWeave distribution footprint reported by the benchmark was about 849 KB; Python and dependency footprints are excluded from that number.

![ExecWeave overhead trade-off](v0.6.0-github-actions.svg)

## Interpretation boundary

This is a deliberately short, file/process-heavy microbenchmark. Percentage overhead can look large when the uninstrumented baseline is only a few hundred milliseconds. It is **not** a universal claim about agent workloads, throughput, or production capacity.

Re-run the benchmark on the target host and representative workload before making deployment or capacity decisions. Portable collection is intended as the cross-platform day-to-day default; Linux `strace` is a higher-fidelity reference path whose overhead is expected to be substantially higher.
