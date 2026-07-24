#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Wind MCP 服务监控脚本
====================

用途
----
每小时调用一批固定的 wind-mcp-skill 工具样例（都是已知能成功的用例），
把每次调用的时间、成功/失败、失败原因写进按天切分的日志文件；
每天 08:00 汇总过去 24 小时的调用情况，生成一个报告文件。

这是一个「服务是否正常运行」的探活监控：
- 程序不中断：任何单次调用异常、解析异常、写盘异常都被捕获，主循环永不退出。
- 所有记录都保留：日志按天追加，不覆盖。
- 日志按日期命名切分，单个文件不会无限增大。

被监控的工具（server_type / tool_name）
--------------------------------------
  stock_data     / get_stock_quote
  stock_data     / get_stock_kline
  stock_data     / get_stock_price_indicators   (用户口述的 get_stock_indicators 实际工具名)
  analytics_data / get_financial_data
  financial_docs / get_financial_news
  economic_data  / natural_language_get_edb_data

运行
----
  python3 wind_service_monitor.py                # 正常常驻：整点探活 + 每天08:00出报告
  python3 wind_service_monitor.py --self-test    # 跑一轮探活并立刻出报告后退出（验证用）
  python3 wind_service_monitor.py --once         # 只跑一轮探活后退出
  python3 wind_service_monitor.py --report-now   # 只根据已有日志生成一次报告后退出

环境变量（可选）
  WIND_SKILL_DIR    覆盖 skill 目录（内含 scripts/cli.mjs 与 config.json）
  WIND_MONITOR_OUT  覆盖日志/报告输出目录
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict

# ----------------------------------------------------------------------------
# 配置
# ----------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent


def _resolve_skill_dir() -> Path:
    """定位含 cli.mjs 的 skill 目录。优先环境变量，其次仓库内相对路径，最后兜底绝对路径。"""
    env = os.environ.get("WIND_SKILL_DIR")
    if env:
        return Path(env)
    # 本脚本提交在 <repo>/monitoring/ 下，skill 在 <repo>/skills/wind-mcp-skill
    candidate = SCRIPT_DIR.parent / "skills" / "wind-mcp-skill"
    if (candidate / "scripts" / "cli.mjs").exists():
        return candidate
    return Path("/home/wind/ybyu/wind-skills/skills/wind-mcp-skill")


SKILL_DIR = _resolve_skill_dir()
CLI_REL = "scripts/cli.mjs"                      # 相对 SKILL_DIR

OUT_DIR = Path(os.environ.get("WIND_MONITOR_OUT", SCRIPT_DIR / "monitor_data"))
LOG_DIR = OUT_DIR / "logs"
REPORT_DIR = OUT_DIR / "reports"

CALL_TIMEOUT = 120          # 单次工具调用超时（秒）
REPORT_HOUR = 8             # 每天该整点生成日报（本地时间）
REPORT_WINDOW_HOURS = 24    # 日报统计窗口长度（小时）

# 固定的成功样例：(展示名, server_type, tool_name, params)
# 日期一律 yyyy-MM-dd（当前 CLI 归一层要求），过去的固定交易日，历史数据长期可查。
SAMPLES = [
    ("get_stock_quote", "stock_data", "get_stock_quote",
     {"windcode": "600519.SH", "begin": "2026-07-24", "end": "2026-07-24"}),
    ("get_stock_kline", "stock_data", "get_stock_kline",
     {"windcode": "600519.SH", "begin_date": "2026-07-01", "end_date": "2026-07-24"}),
    ("get_stock_price_indicators", "stock_data", "get_stock_price_indicators",
     {"windcode": "600519.SH", "indexes": "中文简称,最新成交价,涨跌幅"}),
    ("get_financial_data", "analytics_data", "get_financial_data",
     {"question": "查询中国A股市场过去一年的平均成交量"}),
    ("get_financial_news", "financial_docs", "get_financial_news",
     {"query": "美联储利率政策", "top_k": 3}),
    ("natural_language_get_edb_data", "economic_data", "natural_language_get_edb_data",
     {"executionMode": "searchFetch", "question": "中国CPI同比", "observation": "12"}),
]


# ----------------------------------------------------------------------------
# 基础工具
# ----------------------------------------------------------------------------
def now() -> datetime:
    return datetime.now()


def console(msg: str) -> None:
    print(f"{now():%Y-%m-%d %H:%M:%S} {msg}", flush=True)


def ensure_dirs() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)


def log_file_for(dt: datetime) -> Path:
    return LOG_DIR / f"wind_monitor_{dt:%Y-%m-%d}.jsonl"


def report_file_for(dt: datetime) -> Path:
    return REPORT_DIR / f"wind_report_{dt:%Y-%m-%d}.txt"


def write_record(rec: dict) -> None:
    """追加一条 JSONL 记录到当天日志。写盘失败也不能让监控崩。"""
    try:
        ensure_dirs()
        with open(log_file_for(now()), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as exc:  # noqa: BLE001
        print(f"[LOG-ERROR] 写日志失败: {exc}", file=sys.stderr, flush=True)


# ----------------------------------------------------------------------------
# 调用与结果分类
# ----------------------------------------------------------------------------
def classify(proc: subprocess.CompletedProcess):
    """把 CLI 输出判定为 成功/失败。返回 (ok, error_code, error_detail, result_bytes)。"""
    out = (proc.stdout or "").strip()
    try:
        obj = json.loads(out)
    except Exception:  # noqa: BLE001
        detail = out or (proc.stderr or "")
        return False, "PARSE_ERROR", detail[:600], len(out)

    if isinstance(obj, dict) and obj.get("ok") is False:
        err = obj.get("error", {}) or {}
        code = err.get("code", "UNKNOWN")
        detail = err.get("agent_action") or err.get("details") or err.get("message") or ""
        if not isinstance(detail, str):
            detail = json.dumps(detail, ensure_ascii=False)
        return False, code, detail[:600], len(out)

    if isinstance(obj, dict) and "content" in obj:
        if obj.get("isError"):  # 防御：正常成功 isError 应为 false
            return False, "IS_ERROR_TRUE", json.dumps(obj, ensure_ascii=False)[:600], len(out)
        return True, None, None, len(out)

    # 结构不符合预期
    return (proc.returncode == 0), "UNEXPECTED_SHAPE", json.dumps(obj, ensure_ascii=False)[:600], len(out)


def call_tool(name: str, server: str, tool: str, params: dict) -> dict:
    started = now()
    rec: Dict[str, Any] = {
        "ts": started.isoformat(timespec="seconds"),
        "tool": name,
        "server_type": server,
    }
    try:
        proc = subprocess.run(
            ["node", CLI_REL, "call", server, tool, json.dumps(params, ensure_ascii=False)],
            cwd=str(SKILL_DIR),
            capture_output=True,
            text=True,
            timeout=CALL_TIMEOUT,
        )
        ok, code, detail, rbytes = classify(proc)
        rec["ok"] = ok
        rec["exit_code"] = proc.returncode
        rec["result_bytes"] = rbytes
        if not ok:
            rec["error_code"] = code
            rec["error_detail"] = detail
    except subprocess.TimeoutExpired:
        rec.update(ok=False, exit_code=None, error_code="TIMEOUT",
                   error_detail=f"调用超过 {CALL_TIMEOUT}s 未返回")
    except FileNotFoundError as exc:
        rec.update(ok=False, exit_code=None, error_code="NODE_OR_CLI_NOT_FOUND",
                   error_detail=f"{exc} (SKILL_DIR={SKILL_DIR})")
    except Exception as exc:  # noqa: BLE001
        rec.update(ok=False, exit_code=None, error_code="MONITOR_EXCEPTION",
                   error_detail=f"{type(exc).__name__}: {exc}")

    rec["duration_ms"] = int((now() - started).total_seconds() * 1000)
    write_record(rec)
    status = "OK " if rec.get("ok") else "ERR"
    tail = rec.get("error_code") or f"{rec.get('result_bytes', 0)}B"
    console(f"  [{status}] {name:<30} {tail}")
    return rec


def run_probe_cycle() -> None:
    console(f"==== 探活开始（{len(SAMPLES)} 个工具）====")
    for name, server, tool, params in SAMPLES:
        try:
            call_tool(name, server, tool, params)
        except Exception:  # noqa: BLE001  —— 单个样例再怎么炸也不能停
            console(f"  [FATAL-GUARD] {name} 未捕获异常，已记录并继续")
            write_record({
                "ts": now().isoformat(timespec="seconds"),
                "tool": name,
                "ok": False,
                "error_code": "MONITOR_EXCEPTION",
                "error_detail": traceback.format_exc()[:600],
            })
    console("==== 探活结束 ====")


# ----------------------------------------------------------------------------
# 报告
# ----------------------------------------------------------------------------
def iter_records(window_start: datetime, window_end: datetime):
    """遍历窗口涉及到的每天日志文件，产出 ts 落在 [start, end) 的记录。"""
    day = window_start.date()
    last = window_end.date()
    while day <= last:
        path = log_file_for(datetime(day.year, day.month, day.day))
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                            ts = datetime.fromisoformat(rec.get("ts"))
                        except Exception:  # noqa: BLE001
                            continue
                        if window_start <= ts < window_end:
                            yield rec
            except Exception as exc:  # noqa: BLE001
                console(f"[REPORT] 读取日志 {path} 失败（跳过）: {exc}")
        day += timedelta(days=1)


def generate_report(window_start: datetime, window_end: datetime,
                    report_dt: datetime, reason: str = "scheduled") -> Path:
    ensure_dirs()
    recs = list(iter_records(window_start, window_end))
    total = len(recs)
    succ = sum(1 for r in recs if r.get("ok"))
    fail = total - succ

    per_tool = {}
    for r in recs:
        d = per_tool.setdefault(r.get("tool", "?"), {"total": 0, "succ": 0, "fail": 0})
        d["total"] += 1
        d["succ" if r.get("ok") else "fail"] += 1

    fails = {}
    for r in recs:
        if r.get("ok"):
            continue
        key = (r.get("tool", "?"), r.get("error_code", "UNKNOWN"))
        g = fails.setdefault(key, {"count": 0, "last_ts": None, "last_detail": ""})
        g["count"] += 1
        g["last_ts"] = r.get("ts")
        g["last_detail"] = r.get("error_detail", "") or ""

    rate = (succ / total * 100) if total else 0.0
    lines = [
        "=" * 64,
        "Wind MCP 服务监控日报",
        "=" * 64,
        f"报告生成时间 : {now():%Y-%m-%d %H:%M:%S}",
        f"统计窗口     : {window_start:%Y-%m-%d %H:%M} ~ {window_end:%Y-%m-%d %H:%M}",
        f"触发方式     : {reason}",
        f"Skill 目录   : {SKILL_DIR}",
        "",
        f"总调用次数   : {total}",
        f"成功         : {succ}",
        f"失败         : {fail}",
        f"成功率       : {rate:.1f}%",
        "",
        "-- 按工具 --",
        f"{'工具':<30}{'调用':>6}{'成功':>6}{'失败':>6}",
    ]
    known = [s[0] for s in SAMPLES]
    for t in known:
        d = per_tool.get(t, {"total": 0, "succ": 0, "fail": 0})
        lines.append(f"{t:<30}{d['total']:>6}{d['succ']:>6}{d['fail']:>6}")
    for t, d in per_tool.items():           # 兜底：出现在日志里但不在样例里的（如异常记录）
        if t not in known:
            lines.append(f"{t:<30}{d['total']:>6}{d['succ']:>6}{d['fail']:>6}")

    lines.append("")
    lines.append("-- 失败明细（按 工具 + 原因 分组，按次数降序）--")
    if not fails:
        lines.append("本窗口无失败调用。")
    else:
        for (tool, code), g in sorted(fails.items(), key=lambda kv: -kv[1]["count"]):
            lines.append(f"[{code}] {tool}  次数={g['count']}  最近={g['last_ts']}")
            det = " ".join((g["last_detail"] or "").split())
            if det:
                lines.append(f"    详情: {det[:400]}")
    lines.append("=" * 64)

    text = "\n".join(lines) + "\n"
    path = report_file_for(report_dt)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        console(f"[REPORT] 已生成 -> {path}  (调用{total} 成功{succ} 失败{fail})")
    except Exception as exc:  # noqa: BLE001
        console(f"[REPORT-ERROR] 写报告失败: {exc}")
    return path


def maybe_scheduled_report() -> None:
    """整点回调：若当前是 REPORT_HOUR 且今天还没出报告，则汇总过去 24h。"""
    n = now()
    if n.hour != REPORT_HOUR:
        return
    path = report_file_for(n)
    if path.exists():
        return  # 今天已生成，避免重复（重启也安全）
    end = n.replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(hours=REPORT_WINDOW_HOURS)
    generate_report(start, end, n, reason=f"scheduled@{REPORT_HOUR:02d}:00")


# ----------------------------------------------------------------------------
# 调度
# ----------------------------------------------------------------------------
def sleep_until_next_hour() -> None:
    n = now()
    nxt = n.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    time.sleep(max(1.0, (nxt - n).total_seconds()))


def _guarded_cycle() -> None:
    """一轮探活 + 报告。普通异常吞掉继续；仅 KeyboardInterrupt 放行给上层做优雅退出。"""
    try:
        run_probe_cycle()
        maybe_scheduled_report()
    except KeyboardInterrupt:
        raise
    except Exception:  # noqa: BLE001  —— 任何异常都不能中断监控
        console("探活/报告异常（已捕获，继续）:\n" + traceback.format_exc())


def run_forever() -> None:
    console("Wind MCP 服务监控启动")
    console(f"  SKILL_DIR = {SKILL_DIR}")
    console(f"  日志目录  = {LOG_DIR}")
    console(f"  报告目录  = {REPORT_DIR}")
    console(f"  策略      = 每个整点探活一次；每天 {REPORT_HOUR:02d}:00 出过去{REPORT_WINDOW_HOURS}h日报")

    try:
        _guarded_cycle()                 # 启动即探活一次，立刻确认存活
        while True:
            try:
                sleep_until_next_hour()
                _guarded_cycle()
            except KeyboardInterrupt:
                raise
            except Exception:  # noqa: BLE001  —— 双保险，主循环永不退出
                console("主循环异常（已捕获，60s 后继续）:\n" + traceback.format_exc())
                time.sleep(60)
    except KeyboardInterrupt:            # SIGINT / SIGTERM 在任何阶段都优雅退出
        console("收到停止信号，退出。")


# ----------------------------------------------------------------------------
# 入口
# ----------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="Wind MCP 服务探活监控")
    ap.add_argument("--once", action="store_true", help="只跑一轮探活后退出")
    ap.add_argument("--report-now", action="store_true", help="仅根据已有日志生成一次报告后退出")
    ap.add_argument("--self-test", action="store_true", help="跑一轮探活并立即生成报告后退出（验证用）")
    args = ap.parse_args()

    # 让 SIGTERM（kill / systemctl stop）也走 KeyboardInterrupt 的优雅退出路径
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))

    if args.self_test:
        run_probe_cycle()
        end = now() + timedelta(minutes=1)          # +1min 以纳入刚写入的记录
        start = end - timedelta(hours=REPORT_WINDOW_HOURS)
        generate_report(start, end, now(), reason="self-test")
        return
    if args.once:
        run_probe_cycle()
        return
    if args.report_now:
        end = now() + timedelta(minutes=1)
        start = end - timedelta(hours=REPORT_WINDOW_HOURS)
        generate_report(start, end, now(), reason="manual --report-now")
        return

    run_forever()


if __name__ == "__main__":
    main()
