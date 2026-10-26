"""biaslens —— 用可统计的方式看评测集里的分组差异。

设计原则：
1. **样本量不够，就别下结论**。工具直接把样本量写在结论旁边，
   不足的组拒绝给出结论。
2. **分组差异要带区间**。给点估计不给区间，等于没给。
3. **多重比较要提示**。组一多，随机出现「有差异」很正常。

仅依赖 Python 标准库。

用法:
    python biaslens.py --help
    python biaslens.py --results results.jsonl --group gender --metric score
    python biaslens.py --results results.jsonl --group gender --metric score --json
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import defaultdict

# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------

# 低于这个样本量就不给结论
MIN_SAMPLE = 5

# 置信区间用的 z 值（双侧 95%）
Z_95 = 1.96


def mean_ci(values: list[float]) -> dict:
    """均值与 95% 置信区间。"""
    n = len(values)
    if n == 0:
        return {"n": 0, "mean": None, "ci_low": None, "ci_high": None,
                "std": None}
    mean = statistics.fmean(values)
    if n < 2:
        return {"n": n, "mean": round(mean, 6), "ci_low": None,
                "ci_high": None, "std": None}
    std = statistics.stdev(values)
    margin = Z_95 * std / math.sqrt(n)
    return {
        "n": n,
        "mean": round(mean, 6),
        "std": round(std, 6),
        "ci_low": round(mean - margin, 6),
        "ci_high": round(mean + margin, 6),
    }


def welch(a: list[float], b: list[float]) -> dict:
    """Welch t 检验（不等方差）。返回 t 与近似 p 值。"""
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return {"t": None, "p": None, "df": None, "note": "样本量不足"}

    ma, mb = statistics.fmean(a), statistics.fmean(b)
    va, vb = statistics.variance(a), statistics.variance(b)
    se2 = va / na + vb / nb
    if se2 <= 0:
        return {"t": None, "p": None, "df": None, "note": "方差为零"}
    t = (ma - mb) / math.sqrt(se2)

    # Welch–Satterthwaite 自由度
    num = se2 ** 2
    den = (va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1)
    df = num / den if den else na + nb - 2

    # 双侧 p 值：t 分布的近似（用不完全 beta 的级数展开）
    p = _t_sf(abs(t), df)
    return {
        "t": round(t, 4),
        "p": round(p, 6),
        "df": round(df, 2),
        "note": "",
    }


def _t_sf(t: float, df: float) -> float:
    """t 分布的生存函数（双侧 p = 2 * sf）。用不完全 beta 近似。"""
    x = df / (df + t * t)
    try:
        p = _betainc(df / 2.0, 0.5, x)
    except (ValueError, ZeroDivisionError, OverflowError):
        return 1.0
    return 2.0 * min(1.0, max(0.0, p))


def _betainc(a: float, b: float, x: float) -> float:
    """正则化不完全 beta 函数 I_x(a,b)（连分数展开）。"""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbeta = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
             + a * math.log(x) + b * math.log(1 - x))
    front = math.exp(lbeta)
    if x < (a + 1) / (a + b + 2):
        return front * _betacf(a, b, x) / a
    else:
        return 1.0 - math.exp(
            math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
            + b * math.log(1 - x) + a * math.log(x)
        ) * _betacf(b, a, 1 - x) / b


def _betacf(a: float, b: float, x: float, itmax: int = 200,
            eps: float = 3e-14) -> float:
    """连分数展开。"""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < 1e-30:
        d = 1e-30
    d = 1.0 / d
    h = d
    for m in range(1, itmax + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < eps:
            break
    return h


# ---------------------------------------------------------------------------
# 输入
# ---------------------------------------------------------------------------

def load_results(path: str) -> list[dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read().strip()
    except OSError as e:
        raise ValueError(f"读不了 {path}：{e}") from e
    if not raw:
        return []
    if raw.startswith("["):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON 解析失败：{e}") from e
        return [x for x in data if isinstance(x, dict)]

    rows: list[dict] = []
    for lineno, line in enumerate(raw.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"第 {lineno} 行 JSON 解析失败：{e}") from e
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _val(rec: dict, field: str):
    cur = rec
    for part in field.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


# ---------------------------------------------------------------------------
# 分组分析
# ---------------------------------------------------------------------------

def analyze(rows: list[dict], group_field: str, metric: str,
            min_sample: int) -> dict:
    """按分组统计并做组间比较。"""
    groups: dict[str, list[float]] = defaultdict(list)
    skipped: list[dict] = []

    for i, rec in enumerate(rows):
        g = _val(rec, group_field)
        m = _val(rec, metric)
        if g is None:
            skipped.append({"index": i, "reason": f"没有 {group_field}"})
            continue
        if not isinstance(m, (int, float)) or isinstance(m, bool):
            skipped.append({"index": i, "reason": f"{metric} 不是数值"})
            continue
        groups[str(g)].append(float(m))

    stats = {}
    insufficient = []
    for name, vals in sorted(groups.items()):
        s = mean_ci(vals)
        stats[name] = s
        if s["n"] < min_sample:
            insufficient.append(name)

    # 组间两两比较
    comparisons: list[dict] = []
    names = sorted(stats)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            va, vb = groups[a], groups[b]
            if len(va) < min_sample or len(vb) < min_sample:
                comparisons.append({
                    "a": a, "b": b,
                    "verdict": "insufficient_sample",
                    "detail": f"{a}(n={len(va)}) 与 {b}(n={len(vb)}) "
                              f"至少有一组低于 {min_sample}，不下结论",
                    "a_n": len(va), "b_n": len(vb),
                })
                continue
            w = welch(va, vb)
            diff = stats[a]["mean"] - stats[b]["mean"]
            significant = (w["p"] is not None and w["p"] < 0.05)
            comparisons.append({
                "a": a, "b": b,
                "a_n": len(va), "b_n": len(vb),
                "a_mean": stats[a]["mean"], "b_mean": stats[b]["mean"],
                "diff": round(diff, 6),
                "t": w["t"], "p": w["p"], "df": w["df"],
                "verdict": "significant" if significant else "not_significant",
                "detail": (
                    f"p={w['p']:.4f}，"
                    + ("组间差异在统计上显著" if significant
                       else "差异未达统计显著")
                    if w["p"] is not None else "无法计算 p 值"
                ),
            })

    # 多重比较提示
    n_tests = len(comparisons)
    bonferroni = 0.05 / n_tests if n_tests else 0.05
    bonferroni_flag = n_tests >= 10

    # 有多少组在整体上偏离合散
    spread = None
    if len(stats) >= 2:
        means = [s["mean"] for s in stats.values() if s["mean"] is not None]
        if means:
            spread = round(max(means) - min(means), 6)

    return {
        "group_field": group_field,
        "metric": metric,
        "groups": stats,
        "insufficient_groups": insufficient,
        "comparisons": comparisons,
        "skipped": skipped,
        "summary": {
            "group_count": len(stats),
            "total_samples": sum(len(v) for v in groups.values()),
            "skipped_count": len(skipped),
            "insufficient_count": len(insufficient),
            "significant_count": sum(1 for c in comparisons
                                     if c["verdict"] == "significant"),
            "test_count": n_tests,
            "bonferroni_alpha": round(bonferroni, 6),
            "mean_spread": spread,
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def render(result: dict) -> str:
    out: list[str] = []
    s = result["summary"]
    out.append("分组差异分析")
    out.append("=" * 64)
    out.append(f"分组字段 {result['group_field']} ｜ 指标 {result['metric']}")
    out.append(f"样本 {s['total_samples']} 条 ｜ {s['group_count']} 组 ｜ "
               f"跳过 {s['skipped_count']} 条")
    out.append("")

    out.append("各组统计：")
    for name, st in result["groups"].items():
        flag = ""
        if name in result["insufficient_groups"]:
            flag = f"  ★样本量不足（< {5}），不据此下结论"
        if st["ci_low"] is not None:
            out.append(f"  {name:<16} n={st['n']:<5} 均值 {st['mean']:.4f}  "
                       f"95%CI [{st['ci_low']:.4f}, {st['ci_high']:.4f}]{flag}")
        else:
            mean_text = (f"{st['mean']:.4f}" if st["mean"] is not None else "—")
            out.append(f"  {name:<16} n={st['n']:<5} 均值 {mean_text}{flag}")
    out.append("")

    out.append("组间比较（Welch t 检验）：")
    for c in result["comparisons"]:
        mark = {"significant": "≠", "not_significant": "=",
                "insufficient_sample": "?"}.get(c["verdict"], "?")
        out.append(f"  {mark} {c['a']} vs {c['b']}")
        out.append(f"      {c['detail']}")
    out.append("")

    if s["test_count"] >= 10:
        out.append(f"★ 做了 {s['test_count']} 次比较。多个比较里出现"
                   f"「有差异」可能是随机波动。")
        out.append(f"  若要控制多重比较，Bonferroni 校正后的显著性水平是 "
                   f"{s['bonferroni_alpha']:.4f}（未 0.05）。")
        out.append("")

    if result["skipped"]:
        out.append(f"跳过的样本 {s['skipped_count']} 条（前 5 条原因）：")
        for sk in result["skipped"][:5]:
            out.append(f"  · 第 {sk['index']} 条：{sk['reason']}")
        out.append("")

    out.append("注：显著性不等于重要，也不等于有害——请结合业务影响看。")
    return "\n".join(out).rstrip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="biaslens",
        description="用可统计的方式看评测集里的分组差异（仅依赖标准库）",
        epilog=(
            "记录格式：\n"
            "  {\"gender\":\"f\",\"score\":0.82,\"model\":\"gpt-4o\"}\n"
            "  python biaslens.py --results results.jsonl --group gender "
            "--metric score\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--results", required=True, help="评测结果文件")
    ap.add_argument("--group", required=True, help="分组字段")
    ap.add_argument("--metric", required=True, help="指标字段")
    ap.add_argument("--min-sample", type=int, default=MIN_SAMPLE,
                    help="低于这个样本量就不下结论")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    try:
        rows = load_results(args.results)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    if not rows:
        print("没有数据。", file=sys.stderr)
        return 2

    result = analyze(rows, args.group, args.metric, args.min_sample)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(render(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
