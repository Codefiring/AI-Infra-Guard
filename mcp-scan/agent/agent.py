import os
import re
import time
import uuid
from typing import List, Dict, Any, Optional

from agent.base_agent import BaseAgent
from tools.dispatcher import ToolDispatcher
from utils.prompt_manager import prompt_manager
from utils.loging import logger
from utils.aig_logger import mcpLogger
from utils.project_analyzer import analyze_language, get_top_language, calc_mcp_score
from utils.parse import parse_mcp_invocations


def _parse_stage_reports(all_reports: list) -> tuple:
    """Aggregate per-stage findings directly without an LLM review step.

    Returns (vuln_results, summary_markdown) where vuln_results is a list of
    dicts ready for DB insertion and summary_markdown is the Stage 27 display text.
    """
    _impact_order = {"critical": 3, "high": 2, "medium": 1, "low": 0}

    def _map_impact(impact: str) -> str:
        m = impact.strip().capitalize() if impact else ""
        return m if m in ("Critical", "High", "Medium", "Low") else "Medium"

    vuln_results = []
    summary_rows = []

    for stage_name, report, risk_type in all_reports:
        ov = re.search(r'#\s*Overview\s*\n(.*?)(?=\n#|\Z)', report, re.DOTALL | re.IGNORECASE)
        if not ov or "YES" not in ov.group(1).upper():
            continue

        threats = []
        for tm in re.finditer(r'<threat>(.*?)</threat>', report, re.DOTALL):
            tb = tm.group(1)

            def _tag(tag, _tb=tb):
                m = re.search(rf'<{tag}>(.*?)</{tag}>', _tb, re.DOTALL)
                return m.group(1).strip() if m else ""

            threats.append({
                "tool_name": _tag("tool_name"),
                "type":      _tag("type") or risk_type,
                "impact":    _tag("impact"),
            })

        reasons_m = re.search(r'#\s*Reasons\s*\n(.*?)(?=\n#|\Z)', report, re.DOTALL | re.IGNORECASE)
        summary_m = re.search(r'#\s*Summarization[:\s]*\n(.*?)(?=\n#|\Z)', report, re.DOTALL | re.IGNORECASE)
        reasons_text = reasons_m.group(1).strip() if reasons_m else ""
        summary_text = summary_m.group(1).strip() if summary_m else ""

        max_level = "Medium"
        if threats:
            best = max(threats, key=lambda t: _impact_order.get(t["impact"].lower(), 1))
            max_level = _map_impact(best["impact"])

        tool_names = list(dict.fromkeys(t["tool_name"] for t in threats if t["tool_name"]))
        title = stage_name
        tool_name_str = ", ".join(tool_names)

        parts = []
        if reasons_text:
            parts.append(f"## Reasons\n{reasons_text}")
        if summary_text:
            parts.append(f"## Summary\n{summary_text}")
        description = "\n\n".join(parts) or report

        vuln_results.append({
            "title":       title,
            "tool_name":   tool_name_str,
            "description": description,
            "risk_type":   risk_type,
            "level":       max_level,
            "suggestion":  "",
        })
        summary_rows.append(f"| {stage_name} | {tool_name_str or '—'} | {risk_type} | {max_level} |")

    if summary_rows:
        summary_md = (
            "# Vulnerability Review\n\n"
            "| Stage | Interface | Risk Type | Level |\n|---|---|---|---|\n"
            + "\n".join(summary_rows)
        )
    else:
        summary_md = "# Vulnerability Review\n\nNo vulnerabilities found across all stages."

    return vuln_results, summary_md


class ScanStage:
    """定义扫描的一个阶段"""

    def __init__(self, stage_id: str, name: str, template: str, output_format: str = None, output_check_fn=None
                 , language="zh"):
        self.stage_id = stage_id
        self.name = name
        self.template = template
        self.output_format = output_format
        self.output_check_fn = output_check_fn
        self.language = language


class ScanPipeline:
    """标准扫描流水线逻辑"""

    def __init__(self, agent_wrapper: 'Agent'):
        self.agent_wrapper = agent_wrapper
        self.results = {}

    async def execute_stage(self, stage: ScanStage, repo_dir: str, prompt: str,
                            context_data: Dict[str, Any] = None) -> str:
        logger.info(f"=== 阶段 {stage.stage_id}: {stage.name} ===")
        mcpLogger.new_plan_step(stepId=stage.stage_id, stepName=stage.name)

        # 加载提示词模板
        instruction = prompt_manager.load_template(stage.template)

        # 初始化阶段 Agent
        agent = BaseAgent(
            name=f"{stage.name} Agent",
            instruction=instruction,
            llm=self.agent_wrapper.llm,
            dispatcher=self.agent_wrapper.dispatcher,
            specialized_llms=self.agent_wrapper.specialized_llms,
            log_step_id=stage.stage_id,
            debug=self.agent_wrapper.debug,
            output_format=stage.output_format,
            output_check_fn=stage.output_check_fn,
            language=stage.language
        )
        agent.set_repo_dir(repo_dir)
        await agent.initialize()

        # 构造用户消息
        user_msg = f"请进行{stage.name}，文件夹在 {repo_dir}\n{prompt}"
        if context_data:
            user_msg += "\n\n有以下背景信息：\n"
            for key, value in context_data.items():
                user_msg += f"{key}:{value}\n\n"

        agent.add_user_message(user_msg)

        # 运行并返回结果
        result = await agent.run()
        self.results[stage.name] = result
        return result

    async def execute_stage_dynamic(self, stage: ScanStage, prompt: str,
                                    context_data: Dict[str, Any] = None,
                                    use_oauth: bool = True) -> str:
        """
        Execute a single dynamic scan stage with explicit connection lifecycle:
          connect → [OAuth] → run → disconnect

        Args:
            stage: The scan stage to execute.
            prompt: User prompt for the stage.
            context_data: Optional background context passed to the agent.
            use_oauth: Whether to perform OAuth authentication after connecting.
                       Defaults to True. Set to False to skip OAuth even if an
                       OAuthManager is configured on the dispatcher.
        """
        logger.info(f"=== 阶段 {stage.stage_id}: {stage.name} ===")
        mcpLogger.new_plan_step(stepId=stage.stage_id, stepName=stage.name)

        dispatcher = self.agent_wrapper.dispatcher

        # 1. Clear any stale connection from the previous stage
        await dispatcher.close()

        # 2. OAUTH / CONNECT
        if not use_oauth:
            # Strip any previously injected Bearer token so this stage connects
            # with no credentials (required for Unauthenticated Access testing).
            dispatcher.mcp_headers = dict(dispatcher._base_headers)
            logger.debug(f"Stage {stage.stage_id}: OAuth disabled — testing unauthenticated access")
            # The connection outcome IS the test result for this stage.
            try:
                await dispatcher.connect()
                # Server accepted unauthenticated request → potential vulnerability
                # Fall through so the agent can confirm by calling tools.
                logger.info(f"Stage {stage.stage_id}: unauthenticated connect SUCCEEDED — potential vulnerability")
            except RuntimeError as e:
                # Server rejected unauthenticated request → authentication is enforced → no vulnerability
                logger.info(f"Stage {stage.stage_id}: unauthenticated connect rejected ({e}) — no vulnerability")
                result = (
                    "# Overview\n- NO\n\n"
                    "# Threats\n\n"
                    "# Reasons\n"
                    f"- Unauthenticated Access: The server rejected the unauthenticated connection "
                    f"attempt ({e}). Authentication is properly enforced.\n\n"
                    "# Summarization\n"
                    "The MCP server enforces authentication. Unauthenticated connection attempts "
                    "were rejected (401 Unauthorized), indicating no Unauthenticated Access "
                    "vulnerability (CVE-2025-49596) is present."
                )
                self.results[stage.name] = result
                return result
        else:
            if dispatcher.oauth_manager is not None:
                logger.debug(f"Stage {stage.stage_id}: performing OAuth authentication")
                await dispatcher.inject_oauth_token()
            logger.debug(f"Stage {stage.stage_id}: connecting to MCP server")
            await dispatcher.connect()

        try:
            # 3. RUN — execute stage with (optionally authenticated) connection
            instruction = prompt_manager.load_template(stage.template)

            agent = BaseAgent(
                name=f"{stage.name} Agent",
                instruction=instruction,
                llm=self.agent_wrapper.llm,
                dispatcher=dispatcher,
                specialized_llms=self.agent_wrapper.specialized_llms,
                log_step_id=stage.stage_id,
                debug=self.agent_wrapper.debug,
                output_format=stage.output_format,
                output_check_fn=stage.output_check_fn,
            )
            await agent.initialize()

            user_msg = f"请进行{stage.name}，进行MCP动态扫描\n{prompt}"
            if context_data:
                user_msg += "\n\n有以下背景信息：\n"
                for key, value in context_data.items():
                    user_msg += f"{key}:{value}\n\n"

            agent.add_user_message(user_msg)
            result = await agent.run()
            self.results[stage.name] = result
            return result

        finally:
            # 4. DISCONNECT — always tear down after each stage, even on failure
            try:
                logger.debug(f"Stage {stage.stage_id}: disconnecting from MCP server")
                await dispatcher.close()
            except Exception as close_exc:
                logger.warning(
                    f"Stage {stage.stage_id}: non-fatal error during disconnect: {close_exc}"
                )


class Agent:
    def __init__(self, llm, specialized_llms: dict = None, debug: bool = False,
                 server_url: str = None, language='zh', headers=None, oauth_config=None):
        self.llm = llm
        self.specialized_llms = specialized_llms or {}
        self.debug = debug
        self.language = language

        oauth_manager = None
        if oauth_config is not None:
            from utils.mcp_oauth import OAuthManager
            oauth_manager = OAuthManager(oauth_config)

        self.dispatcher = ToolDispatcher(
            mcp_server_url=server_url,
            mcp_headers=headers,
            oauth_manager=oauth_manager,
        )
        self.pipeline = ScanPipeline(self)

    async def scan(self, repo_dir: str, prompt: str):
        result_meta = {
            "readme": "",
            "score": 0,
            "language": "",
            "start_time": time.time(),
            "end_time": 0,
            "results": [],
            "llm": self.llm.model,
        }
        # 1. 信息收集
        info_ret_format = "生成一份详细的信息收集报告，使用Markdown格式。报告需基于输入数据如实总结，确保读者（对项目一无所知）能快速理解项目全貌。"
        info_collection = await self.pipeline.execute_stage(
            ScanStage("1", "Info Collection", "agents/project_summary", output_format=info_ret_format,
                      language=self.language),
            repo_dir, prompt
        )

        # 2. 代码审计
        audit_ret_format = '''
markdown格式返回
对于每个确认的漏洞，必须提供：
- 具体位置：文件路径和行号范围
- 完整代码片段：显示漏洞的代码段
- 技术分析：漏洞原理和利用方法
- 影响评估：可获得的权限和影响范围
- 修复建议：详细的安全加固方案
- 攻击路径：具体的利用步骤（如适用）
严格标准：必须提供完整的漏洞利用路径和影响分析。
        '''
        code_audit = await self.pipeline.execute_stage(
            ScanStage("2", "Code Audit", "agents/code_audit", output_format=audit_ret_format, language=self.language),
            repo_dir, prompt, {"信息收集报告": info_collection}
        )

        # 3. 漏洞整理
        review_format = '''
必须满足以下xml格式，多个漏洞返回多个vuln标签
MCP安全扫描共覆盖15类风险：恶意行为检测包括 MCP02 工具投毒(TPA)、MCP03 全模式投毒(FSP)、MCP04 高级工具投毒(ATPA)、MCP05
    撤毯攻击(Rug Pull)、MCP07 工具名称欺骗、MCP08 工具遮蔽、MCP14 未授权访问、MCP18 路径穿越、MCP21 权限滥用；漏洞扫描包括
    MCP09 资源内容投毒、MCP11 提示词注入、MCP12 命令注入、MCP13 远程代码执行(RCE)、MCP16 令牌/凭证窃取、MCP23 SQL注入。
<vuln>
  <title>title</title>
  <desc>
  <!-- Markdown格式漏洞描述 -->
  ## 漏洞详情
  **接口名称**: 
  **文件位置**: 
  **漏洞类型**: 
  **风险等级**: 
  
  ### 技术分析
  
  ### 攻击路径
  
  ### 影响评估  
  </desc>
  <risk_type>Short identifier only, e.g. MCP01 / MCP05 </risk_type>
  <level>Level</level>
  <suggestion>
  ## 修复建议
  </suggestion>
</vuln>
若无漏洞或漏洞为空,返回<empty>
'''.strip()
        vuln_review_check = lambda x: '<vuln>' in x or '<empty>' in x
        vuln_review = await self.pipeline.execute_stage(
            ScanStage("3", "Vulnerability Review", "agents/vuln_review", output_format=review_format,
                      output_check_fn=vuln_review_check, language=self.language),
            repo_dir, prompt, {"代码审计报告": code_audit}
        )

        # 提取与分析结果
        extractor = VulnerabilityExtractor()
        vuln_results = extractor.extract_vulnerabilities(vuln_review)

        elasped_time = (time.time() - result_meta["start_time"]) / 60
        logger.info(f"扫描任务完成，总耗时 {elasped_time:.2f} 分钟")
        lang_stats = analyze_language(repo_dir)
        top_language = get_top_language(lang_stats)
        safety_score = calc_mcp_score(vuln_results)

        result_meta.update({
            "readme": info_collection,
            "score": safety_score,
            "language": top_language,
            "end_time": time.time(),
            "results": vuln_results
        })
        mcpLogger.result_update(result_meta)
        return result_meta

    async def dynamic_analysis(self, prompt: str, selected_stage_ids: list | None = None,
                               task_target_id: str | None = None):
        result_meta = {
            "readme": "",
            "score": 0,
            "language": "",
            "start_time": time.time(),
            "end_time": 0,
            "results": [],
        }

        # Optional direct DB writes — used when launched from web_server (task_target_id provided)
        _db_mod = None
        if task_target_id:
            try:
                import db as _db_mod
            except ImportError:
                pass

        def _stage_db(stage_id: int, status: str, output: str = ""):
            if _db_mod and task_target_id:
                try:
                    _db_mod.stage_update(task_target_id, stage_id, status, output)
                except Exception:
                    pass

        # Stage 1: Info Collection
        info_ret_format = "生成一份详细的MCP(model context protocol)信息收集报告，使用Markdown格式。报告需基于输入数据如实总结，确保读者（对项目一无所知）能快速理解项目全貌。"
        _stage_db(0, "running")
        info_collection = await self.pipeline.execute_stage_dynamic(
            ScanStage("0", "Info Collection", "agents/dynamic/project_summary", output_format=info_ret_format,
                      language=self.language),
            prompt=prompt
        )
        result_meta["readme"] = info_collection
        _stage_db(0, "completed", info_collection)

        # Per-type scan output format — risk_type is injected per stage to prevent LLM hallucination
        def make_vuln_format(risk_type: str) -> str:
            return f'''## Output format
- The output should be in Markdown format. Please Never use any other format, and make sure the output has no format issue.
- The Markdown document should have the following Chapter:
    - "Overview": `YES` or `NO`, representing whether there are any risks analyzed.
    - "Threats": A list of xml strings, each representing a threat analyzed. Including threat types, confidence scores, and potential impacts.
    - "Reasons": A list of normal strings, each representing the reason why the corresponding threat is analyzed.
    - "Summarization": A paragraph summarizing the overall security assessment results.
- The risk type for this stage is: {risk_type}. You MUST use exactly "{risk_type}" as the <type> value in every threat entry.
- example:
    ```
    # Overview
    - YES
    # Threats
        - <threat><tool_name>{{{{ tool_name }}}}</tool_name><type>{risk_type}</type><confidence>0.9</confidence><impact>High</impact></threat>
    # Reasons
        - {risk_type}: The tool named {{{{ tool_name }}}} detected a potential {risk_type} vulnerability in the input parameter.
    # Summarization:
        ...... (The clear, detailed summary of the security assessment results)
    ```
        '''

        # All scan stages ordered by MCP rank.
        # Tuple format: (stage_id, name, template, use_oauth, risk_type)
        # risk_type follows Adversa AI MCP Top-25 ranking: https://adversa.ai/mcp-security-top-25-mcp-vulnerabilities/
        # Stage 14 intentionally disables OAuth to test whether the server
        # rejects unauthenticated requests (401 = no vulnerability; success = vulnerability).
        all_stages = [
            ("1",  "Prompt Injection",                      "agents/dynamic/vuln/prompt_injection",       True,  "MCP01"),  # rank 1
            ("2",  "Command Injection",                     "agents/dynamic/vuln/command_injection",      True,  "MCP02"),  # rank 2
            ("3",  "Tool Poisoning (TPA)",                  "agents/dynamic/malicious/tpa",               True,  "MCP03"),  # rank 3
            ("4",  "Remote Code Execution (RCE)",           "agents/dynamic/vuln/rce",                    True,  "MCP04"),  # rank 4
            ("5",  "Unauthenticated Access",                "agents/dynamic/vuln/unauth_access",          False, "MCP05"),  # rank 5
            ("6",  "Confused Deputy (OAuth Proxy)",         "agents/dynamic/vuln/confused_deputy",        True,  "MCP06"),  # rank 6
            ("7",  "MCP Configuration Poisoning",           "agents/dynamic/malicious/config_poisoning",  True,  "MCP07"),  # rank 7
            ("8",  "Token/Credential Theft",                "agents/dynamic/vuln/credential_theft",       True,  "MCP08"),  # rank 8
            ("9",  "Token Passthrough",                     "agents/dynamic/vuln/token_passthrough",      True,  "MCP09"),  # rank 9
            ("10", "Path Traversal",                        "agents/dynamic/vuln/path_traversal",         True,  "MCP10"),  # rank 10
            ("11", "Full Schema Poisoning (FSP)",            "agents/dynamic/malicious/fsp",               True,  "MCP11"),  # rank 11
            ("12", "Tool Name Spoofing",                    "agents/dynamic/malicious/name_spoofing",     True,  "MCP12"),  # rank 12
            ("13", "Localhost Bypass (NeighborJack)",       "agents/dynamic/vuln/localhost_bypass",       True,  "MCP13"),  # rank 13
            ("14", "Rug Pull Attack",                       "agents/dynamic/malicious/rug_pull",          True,  "MCP14"),  # rank 14
            ("15", "Advanced Tool Poisoning (ATPA)",        "agents/dynamic/malicious/atpa",              True,  "MCP15"),  # rank 15
            ("16", "Session Management Flaws",              "agents/dynamic/vuln/session_management",     True,  "MCP16"),  # rank 16
            ("17", "Tool Shadowing",                        "agents/dynamic/malicious/tool_shadowing",    True,  "MCP17"),  # rank 17
            ("18", "Resource Content Poisoning",            "agents/dynamic/malicious/resource_poisoning",True,  "MCP18"),  # rank 18
            ("19", "Privilege Abuse/Overbroad Permissions", "agents/dynamic/vuln/privilege_abuse",        True,  "MCP19"),  # rank 19
            ("20", "Cross-Repository Data Theft",           "agents/dynamic/vuln/cross_repo_theft",       True,  "MCP20"),  # rank 20
            ("21", "SQL Injection",                         "agents/dynamic/vuln/sql_injection",          True,  "MCP21"),  # rank 21
            ("22", "Context Bleeding",                      "agents/dynamic/vuln/context_bleeding",       True,  "MCP22"),  # rank 22
            ("23", "Configuration File Exposure",           "agents/dynamic/vuln/config_exposure",        True,  "MCP23"),  # rank 23
            ("24", "MCP Preference Manipulation (MPMA)",    "agents/dynamic/malicious/mpma",              True,  "MCP24"),  # rank 24
            ("25", "Cross-Tenant Data Exposure",            "agents/dynamic/vuln/cross_tenant_exposure",  True,  "MCP25"),  # rank 25
        ]

        # Filter stages when caller specifies a subset
        if selected_stage_ids is not None:
            id_set = {int(i) for i in selected_stage_ids}
            all_stages = [s for s in all_stages if int(s[0]) in id_set]

        all_reports = []
        for stage_id, stage_name, template, use_oauth, risk_type in all_stages:
            _stage_db(int(stage_id), "running")
            report = await self.pipeline.execute_stage_dynamic(
                ScanStage(stage_id, stage_name, template,
                          output_format=make_vuln_format(risk_type), language=self.language),
                prompt, {"信息收集报告": info_collection},
                use_oauth=use_oauth,
            )
            _stage_db(int(stage_id), "completed", report)
            all_reports.append((stage_name, report, risk_type))

        # Stage 26: Vulnerability Review — aggregate per-stage findings directly (no LLM)
        _stage_db(26, "running")
        vuln_results, vuln_review = _parse_stage_reports(all_reports)
        _stage_db(26, "completed", vuln_review)

        safety_score = calc_mcp_score(vuln_results)

        result_meta.update({
            "readme": info_collection,
            "score": safety_score,
            "end_time": time.time(),
            "results": vuln_results
        })

        # Write final results to DB
        if _db_mod and task_target_id:
            try:
                vuln_rows = [
                    {
                        "id":          str(uuid.uuid4())[:8],
                        "title":       v.get("title", ""),
                        "description": v.get("description", ""),
                        "risk_type":   v.get("risk_type", ""),
                        "level":       v.get("level", ""),
                        "suggestion":  v.get("suggestion", ""),
                    }
                    for v in vuln_results
                ]
                _db_mod.vulnerabilities_insert(task_target_id, vuln_rows)
                _db_mod.target_set_done(task_target_id, safety_score, info_collection)
            except Exception:
                pass

        mcpLogger.result_update(result_meta)
        return result_meta
