from __future__ import annotations

from typing import List, Dict, Set, Optional, Any, Tuple, TypedDict, Literal, Union
from pathlib import Path
from dataclasses import dataclass, field
from gpt_researcher.utils.notebook import NotebookSerializer
from utils.llm import code_llm, fix_llm, revise_llm
from actions.utils import stream_output
from nbclient import NotebookClient
import nbformat
from langgraph.graph import StateGraph, END
from utils.validators import PipelinePlanResponse


# ---------- LangGraph 状态定义 ----------
class CGState(TypedDict, total=False):
    cg: "CodeGenerator"
    plan: PipelinePlanResponse
    phase: Literal["init", "build", "execute", "verify", "fix_or_revise", "collect"]
    route_hint: Literal["build", "end"]  # collect 后的路由提示（回到 build 或结束）


class CodeGenerator:
    def __init__(
        self,
        researcher: Any,
        *,
        kernel: str = "python3",
        timeout_sec: int = 1200,
        max_attempts_per_step: int = 3,
        max_revisions: int = 2,
    ):
        # ===== 基础配置 =====
        self.researcher = researcher
        config = getattr(self.researcher, "cfg", None)
        self.research_params = {
            "query": getattr(self.researcher, "query", None),
            "agent_role_prompt": getattr(config, "agent_role", None) or getattr(self.researcher, "role", None),
            "report_type": getattr(self.researcher, "report_type", None),
            "report_source": getattr(self.researcher, "report_source", None),
            "tone": getattr(self.researcher, "tone", None),
            "websocket": getattr(self.researcher, "websocket", None),
            "cfg": config,
            "headers": getattr(self.researcher, "headers", None),
        }
        self.plan: Optional[PipelinePlanResponse] = None
        self.output_dir: str = self.researcher.cfg.output_dir
        self.kernel = kernel
        self.timeout_sec = timeout_sec
        self.code_libs = self.researcher.cfg.code_libs
        self.config = config

        # ===== 运行期依赖 =====
        self.code_llm = code_llm
        self.fix_llm = fix_llm
        self.revise_llm = revise_llm

        # ===== Notebook & 运行态 =====
        self.nb: Optional["NotebookSerializer"] = None
        self.nb_path: Optional[Path] = None
        self.cell_index: Dict[str, int] = {}
        self.idx: int = 0
        self.attempts: Dict[str, int] = {}
        self.max_attempts_per_step = max_attempts_per_step
        self.max_revisions = max_revisions
        self.revisions_done: int = 0

        # ===== 执行状态 =====
        self.executed_up_to: Optional[str] = None
        self.last_error: Optional[str] = None
        self.logs: List[str] = []
        self.assets: Dict[str, Dict[str, List[str]]] = {}

    # ============ 工具函数 ============
    @staticmethod
    def _norm(p: str) -> str:
        return str(p).replace("\\", "/")

    @staticmethod
    def _prep_output_dirs(output_dir: str) -> Dict[str, Path]:
        root = Path(output_dir).absolute()
        (root / "figures").mkdir(parents=True, exist_ok=True)
        (root / "tables").mkdir(parents=True, exist_ok=True)
        (root / "metrics").mkdir(parents=True, exist_ok=True)
        (root / "notebooks").mkdir(parents=True, exist_ok=True)
        return {
            "root": root,
            "fig": root / "figures",
            "tab": root / "tables",
            "met": root / "metrics",
            "nb": root / "notebooks",
        }

    @staticmethod
    def _execute_until_cell(notebook_path: Union[str, Path], upto: int, kernel: str = "python3", timeout: int = 1200) -> Tuple[bool, Optional[str]]:
        """
        执行 notebook 到指定 cell 索引（包含）。
        """
        nb = nbformat.read(notebook_path, as_version=4)
        client = NotebookClient(nb, kernel_name=kernel, timeout=timeout)
        try:
            for i, cell in enumerate(nb.cells[: upto + 1]):
                client.execute_cell(cell, i, store_history=True)
            with open(notebook_path, "w", encoding="utf-8") as f:
                nbformat.write(nb, f)
            return True, None
        except Exception as e:
            return False, repr(e)

    @staticmethod
    def _as_list(v) -> List[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        if isinstance(v, (list, tuple)):
            return [str(x) for x in v]
        return [str(v)]

    @staticmethod
    def _check_artifacts(step, output_dir: Union[str, Path]) -> Tuple[bool, List[str]]:
        """
        校验指定 step 的产物是否已在 output_dir 中生成。
        step 支持字段：
          - expected_artifacts (dict[str, list[str]])
          - artifacts / outputs / expected_patterns (兼容字段)
          - required_artifacts (list[str])  # 只声明类别
        """
        output_dir = Path(output_dir)
        sid = getattr(step, "id", "unknown_step")

        CATEGORY_DIRS: Dict[str, str] = {
            "figures": "figures",
            "tables": "tables",
            "metrics": "metrics",
        }
        DEFAULT_EXT: Dict[str, str] = {
            "figures": "*.png",
            "tables": "*.csv",
            "metrics": "*.jsonl",
        }

        expected: Dict[str, List[str]] = {}
        for key in ("expected_artifacts", "artifacts", "outputs", "expected_patterns"):
            if hasattr(step, key) and isinstance(getattr(step, key), dict):
                expected = dict(getattr(step, key))
                break

        required_categories = []
        if not expected:
            required_categories = getattr(step, "required_artifacts", []) or []
            required_categories = [c for c in dict.fromkeys(required_categories) if c in CATEGORY_DIRS]

        missing: List[str] = []

        if expected:
            for cat, patterns in expected.items():
                if cat not in CATEGORY_DIRS:
                    continue
                subdir = output_dir / CATEGORY_DIRS[cat]
                subdir.mkdir(parents=True, exist_ok=True)

                for pat in CodeGenerator._as_list(patterns):
                    pat = pat.format(sid=sid)
                    if any(ch in pat for ch in "*?[]"):
                        matches = list(subdir.glob(pat))
                    else:
                        p = subdir / pat
                        matches = [p] if p.exists() else []

                    if not matches:
                        missing.append(f"{cat}: missing `{pat}` under `{subdir}`")

            return len(missing) == 0, missing

        if required_categories:
            for cat in required_categories:
                subdir = output_dir / CATEGORY_DIRS[cat]
                subdir.mkdir(parents=True, exist_ok=True)
                pattern = f"{sid}__{DEFAULT_EXT[cat]}"
                matches = list(subdir.glob(pattern))
                if not matches:
                    missing.append(f"{cat}: need at least one `{pattern}` in `{subdir}`")
            return len(missing) == 0, missing

        return True, []

    # ========= 统一日志出口 ========= #
    async def _log(self, cg: "CodeGenerator", phase: str, msg: str) -> None:
        cg.logs.append(msg)
        try:
            if getattr(cg.researcher, "verbose", False):
                await stream_output("logs", phase, msg, getattr(cg.researcher, "websocket", None))
        except Exception:
            pass  # 日志失败不影响主流程

    # ========= LangGraph 节点（接收 CGState，返回 partial dict） ========= #
    async def n_init(self, state: CGState) -> Dict:
        cg = state["cg"]
        dirs = self._prep_output_dirs(cg.output_dir)
        nb_dir = dirs["nb"]
        cg.nb = NotebookSerializer(work_dir=str(nb_dir), notebook_name="analysis.ipynb")
        cg.nb_path = nb_dir / "analysis.ipynb"

        s = state["plan"].settings
        ds = "\n".join(self._norm(p) for p in (getattr(s, "data_sources", None) or [])[:5])
        kc = ", ".join((getattr(s, "key_columns", None) or []))
        seed = getattr(s, "random_seed", None)

        cg.nb.add_markdown_to_notebook(
            f"# 自动化分析流水线\n\n"
            f"- 随机种子: **{seed if seed is not None else 42}**\n"
            f"- 数据源:\n```\n{ds}\n```\n"
            f"- 关键列: `{kc}`\n"
            f"- 输出目录: `{self._norm(cg.output_dir)}`"
        )
        cg.idx = 0
        cg.attempts = {}
        cg.last_error = None

        await self._log(cg, "init", "🚀 初始化完成：Notebook 已创建，写入元信息。")
        return {"phase": "init"}

    async def n_build(self, state: CGState) -> Dict:
        cg = state["cg"]
        plan = state["plan"]

        if cg.idx < 0 or cg.idx >= len(plan.pipeline):
            msg = f"❌ BUILD 索引越界：idx={cg.idx}"
            cg.last_error = msg
            await self._log(cg, "build", msg)
            return {"phase": "build"}

        step = plan.pipeline[cg.idx]
        sid = step.id
        cg.nb.add_markdown_segmentation_to_notebook(f"## {sid} · {step.name}\n\n**目标**：{step.objective}", sid)
        await self._log(cg, "build", f"🧱 开始构建步骤：{sid}（{step.name}）")

        seed = getattr(plan.settings, "random_seed", None) or 42

        code: Optional[str] = None
        if cg.code_llm:
            try:
                resp = await cg.code_llm(
                    step=step,
                    out_dir=cg.output_dir,
                    seed=seed,
                    allowed_libs=cg.code_libs,
                    plan=plan,
                    config=cg.config,
                    prompt_family=self.researcher.prompt_family
                )
                if isinstance(resp, str) and resp.strip():
                    code = resp.strip()
                else:
                    await self._log(cg, "build", f"⚠️ [{sid}] code_llm 未返回有效代码，将写入占位单元。")
            except Exception as e:
                await self._log(cg, "build", f"❌ [{sid}] code_llm 异常：{e!r}")

        if not code:
            code = (
                "# Auto-generated placeholder to keep notebook executable\n"
                f"print('Step \"{sid}\" has no generated code yet; placeholder executed.')\n"
            )
            await self._log(cg, "build", f"ℹ️ [{sid}] 已插入占位代码单元。")

        cg.nb.add_code_cell_to_notebook(code)
        cg.cell_index[sid] = len(cg.nb.nb["cells"]) - 1
        cg.last_error = None
        await self._log(cg, "build", f"✅ [{sid}] 构建完成，代码单元索引 {cg.cell_index[sid]}")
        return {"phase": "build"}

    async def n_execute(self, state: CGState) -> Dict:
        cg = state["cg"]
        plan = state["plan"]
        step = plan.pipeline[cg.idx]
        sid = step.id

        if not cg.nb_path:
            cg.last_error = "Notebook path is not initialized."
            await self._log(cg, "execute", f"❌ [{sid}] 执行失败：{cg.last_error}")
            return {"phase": "execute"}

        upto = cg.cell_index.get(sid)
        if upto is None:
            cg.last_error = f"No cell index for step {sid}."
            await self._log(cg, "execute", f"❌ [{sid}] 执行失败：{cg.last_error}")
            return {"phase": "execute"}

        await self._log(cg, "execute", f"▶️ [{sid}] 开始执行至单元 {upto}")
        ok, err = self._execute_until_cell(cg.nb_path, upto, cg.kernel, cg.timeout_sec)
        if ok:
            cg.executed_up_to = sid
            cg.last_error = None
            await self._log(cg, "execute", f"✅ [{sid}] 执行成功。")
        else:
            cg.executed_up_to = None
            cg.last_error = err or "Unknown execution error."
            await self._log(cg, "execute", f"❌ [{sid}] 执行错误：{cg.last_error}")
        return {"phase": "execute"}

    @staticmethod
    def cond_after_execute(state: CGState) -> str:
        cg = state["cg"]
        return "ok" if cg.last_error is None else "fail"

    async def n_verify(self, state: CGState) -> Dict:
        cg = state["cg"]
        plan = state["plan"]
        step = plan.pipeline[cg.idx]
        sid = step.id
        ok, missing = self._check_artifacts(step, cg.output_dir)
        if ok:
            cg.last_error = None
            await self._log(cg, "verify", f"✅ [{sid}] 产物校验通过。")
        else:
            cg.last_error = f"Missing artifacts: {missing}"
            await self._log(cg, "verify", f"❌ [{sid}] 校验失败：{cg.last_error}")
        return {"phase": "verify"}

    @staticmethod
    def cond_after_verify(state: CGState) -> str:
        cg = state["cg"]
        return "ok" if cg.last_error is None else "need_fix"

    async def n_fix_or_revise(self, state: CGState) -> Dict:
        cg = state["cg"]
        plan = state["plan"]
        step = plan.pipeline[cg.idx]
        sid = step.id

        att = cg.attempts.get(sid, 0) + 1
        cg.attempts[sid] = att

        seed = getattr(plan.settings, "random_seed", None) or 42
        prev_idx = cg.cell_index.get(sid, None)
        prev_code = None
        if prev_idx is not None:
            prev_code = cg.nb.nb["cells"][prev_idx]["source"]

        # 尝试修补
        if att <= cg.max_attempts_per_step:
            await self._log(cg, "fix", f"🩹 [{sid}] 修补尝试第 {att}/{cg.max_attempts_per_step} 次。")
            new_code: Optional[str] = None
            if cg.fix_llm:
                try:
                    resp = await cg.fix_llm(
                        step=step,
                        error_text=cg.last_error or "",
                        prev_code=prev_code or "",
                        out_dir=cg.output_dir,
                        seed=seed,
                        allowed_libs=cg.code_libs,
                        plan=plan,
                        config=cg.config,
                        prompt_family=self.researcher.prompt_family
                    )
                    if isinstance(resp, str) and resp.strip():
                        new_code = resp.strip()
                except Exception as e:
                    await self._log(cg, "fix", f"❌ [{sid}] fix_llm 异常：{e!r}")

            if new_code:
                cg.nb.add_markdown_to_notebook(f"> ♻️ 第 {sid} 步修补尝试（第 {att} 次）")
                cg.nb.add_code_cell_to_notebook(new_code)
                cg.cell_index[sid] = len(cg.nb.nb["cells"]) - 1
                await self._log(cg, "fix", f"✅ [{sid}] 修补代码已写入，转入执行。")
                return {"phase": "fix_or_revise"}

            await self._log(cg, "fix", f"⚠️ [{sid}] 第 {att} 次修补未生成可用代码。")

        # 修订
        if cg.revisions_done >= cg.max_revisions:
            await self._log(
                cg,
                "revise",
                f"⛔ [{sid}] 已超过最大修补（{cg.max_attempts_per_step}）与修订次数（{cg.max_revisions}），终止进一步尝试。",
            )
            return {"phase": "fix_or_revise"}

        revised = False
        if cg.revise_llm:
            await self._log(cg, "revise", f"🧭 [{sid}] 进入修订流程（已修订 {cg.revisions_done}/{cg.max_revisions} 次）。")
            try:
                resp = await cg.revise_llm(
                    step=step,
                    error_text=cg.last_error or "",
                    prev_code=prev_code or "",
                    out_dir=cg.output_dir,
                    seed=seed,
                    allowed_libs=cg.code_libs,
                    plan=plan,
                    config=cg.config,
                    prompt_family=self.researcher.prompt_family
                )

                if isinstance(resp, dict):
                    kind = resp.get("kind")
                    if kind == "step" and resp.get("step"):
                        plan.pipeline[cg.idx] = resp["step"]
                        cg.nb.add_markdown_to_notebook(f"> 🔁 已修订当前步骤：{sid}")
                        await self._log(cg, "revise", f"✅ [{sid}] 已替换为新的 step。")
                        revised = True
                    elif kind == "plan" and resp.get("plan"):
                        state["plan"] = resp["plan"]  # 用新的 plan 更新到 state
                        cg.nb.add_markdown_to_notebook("> 🔁 已修订整体计划")
                        await self._log(cg, "revise", f"✅ [{sid}] 已替换为新的 plan。")
                        revised = True
                    elif kind == "code" and isinstance(resp.get("code"), str) and resp.get("code").strip():
                        cg.nb.add_markdown_to_notebook(f"> 🔁 修订直接给出新代码：{sid}")
                        cg.nb.add_code_cell_to_notebook(resp["code"].strip())
                        cg.cell_index[sid] = len(cg.nb.nb["cells"]) - 1
                        await self._log(cg, "revise", f"✅ [{sid}] 修订代码已写入。")
                        revised = True
                    else:
                        cg.nb.add_markdown_to_notebook("> ⚠️ revise 未返回可用对象，保留原计划")
                        await self._log(cg, "revise", f"⚠️ [{sid}] revise 未返回可用对象。")
                elif isinstance(resp, str) and resp.strip():
                    cg.nb.add_markdown_to_notebook(f"> 🔁 修订直接给出新代码：{sid}")
                    cg.nb.add_code_cell_to_notebook(resp.strip())
                    cg.cell_index[sid] = len(cg.nb.nb["cells"]) - 1
                    await self._log(cg, "revise", f"✅ [{sid}] 修订代码已写入（字符串）。")
                    revised = True
                else:
                    cg.nb.add_markdown_to_notebook("> ⚠️ revise 未返回内容")
                    await self._log(cg, "revise", f"⚠️ [{sid}] revise 未返回内容。")
            except Exception as e:
                await self._log(cg, "revise", f"❌ [{sid}] revise_llm 异常：{e!r}")

        if revised:
            cg.revisions_done += 1
            await self._log(cg, "revise", f"🔢 修订计数 +1：{cg.revisions_done}/{cg.max_revisions}")

        return {"phase": "fix_or_revise"}

    async def n_collect(self, state: CGState) -> Dict:
        cg = state["cg"]
        plan = state["plan"]
        root = Path(cg.output_dir)
        out: Dict[str, Dict[str, List[str]]] = {}
        for st in plan.pipeline:
            sid = st.id
            figs = sorted(str(p.as_posix()) for p in (root / "figures").glob(f"{sid}__*.png"))
            tabs = sorted(str(p.as_posix()) for p in (root / "tables").glob(f"{sid}__*.csv"))
            mets = sorted(str(p.as_posix()) for p in (root / "metrics").glob(f"{sid}__*.jsonl"))
            out[sid] = {"figures": figs, "tables": tabs, "metrics": mets}
        cg.assets = out
        cg.last_error = None
        await self._log(cg, "collect", "📦 产物归集完成。")

        # 路由：还有下一步则回到 build，否则结束
        if cg.idx < len(plan.pipeline) - 1:
            cg.idx += 1
            return {"phase": "collect", "route_hint": "build"}
        return {"phase": "collect", "route_hint": "end"}

    @staticmethod
    def after_collect(state: CGState) -> str:
        return state.get("route_hint", "end")

    # ========= 对外运行入口 ========= #
    async def run(self, plan: PipelinePlanResponse) -> "CodeGenerator":
        # 将 plan 也存到实例上（保留你原有的行为）
        self.plan = plan

        # 1) 用 StateGraph 声明 **状态 schema**（不是业务类）
        g = StateGraph(CGState)

        # 2) 注册节点（节点函数均返回 dict 增量）
        g.add_node("init", self.n_init)
        g.add_node("build", self.n_build)
        g.add_node("execute", self.n_execute)
        g.add_node("verify", self.n_verify)
        g.add_node("fix_or_revise", self.n_fix_or_revise)
        g.add_node("collect", self.n_collect)

        # 3) 连接边
        g.set_entry_point("init")
        g.add_edge("init", "build")
        g.add_edge("build", "execute")
        g.add_conditional_edges("execute", CodeGenerator.cond_after_execute, {
            "ok": "verify",
            "fail": "fix_or_revise",
        })
        g.add_conditional_edges("verify", CodeGenerator.cond_after_verify, {
            "ok": "collect",
            "need_fix": "fix_or_revise",
        })
        g.add_edge("fix_or_revise", "execute")
        g.add_conditional_edges("collect", CodeGenerator.after_collect, {
            "build": "build",
            "end": END,
        })

        app = g.compile()

        # 4) 以 **初始 state（dict）** 运行，而不是把 self 当作 state
        final_state: CGState = await app.ainvoke({
            "cg": self,
            "plan": plan,
        })

        # 5) 需要的结果直接返回实例（实例中的 nb/assets/logs 等都已更新）
        return self
