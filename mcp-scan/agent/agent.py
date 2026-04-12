import os
import time
import uuid
from typing import List, Dict, Any, Optional

from agent.base_agent import BaseAgent
from tools.dispatcher import ToolDispatcher
from utils.prompt_manager import prompt_manager
from utils.extract_vuln import VulnerabilityExtractor
from utils.loging import logger
from utils.aig_logger import mcpLogger
from utils.project_analyzer import analyze_language, get_top_language, calc_mcp_score
from utils.parse import parse_mcp_invocations


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
<vuln>
  <title>title</title>
  <desc>
  <!-- Markdown格式漏洞描述 -->
  ## 漏洞详情
  **文件位置**: 
  **漏洞类型**: 
  **风险等级**: 
  
  ### 技术分析
  
  ### 攻击路径
  
  ### 影响评估  
  </desc>
  <risk_type>Short identifier only, e.g. MCP01 / MCP05 / Name Confusion / CWE-78</risk_type>
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
        _stage_db(1, "running")
        info_collection = await self.pipeline.execute_stage_dynamic(
            ScanStage("1", "Info Collection", "agents/dynamic/project_summary", output_format=info_ret_format,
                      language=self.language),
            prompt=prompt
        )
        result_meta["readme"] = info_collection
        _stage_db(1, "completed", info_collection)

        # Per-type scan output format
        vuln_ret_format = '''
## Output format
- The output should be in Markdown format. Please Never use any other format, and make sure the output has no format issue.
- The Markdown document should have the following Chapter:
    - "Overview": `YES` or `NO`, representing whether there are any risks analyzed.
    - "Threats": A list of xml strings, each representing a threat analyzed. Including threat types, confidence scores, and potential impacts.
    - "Reasons": A list of normal strings, each representing the reason why the corresponding threat is analyzed.
    - "Summarization": A paragraph summarizing the overall security assessment results.
- example:
    ```
    # Overview
    - YES
    # Threats
        - <threat><tool_name>{{ tool_name }}</tool_name><type>SQL Injection</type><confidence>0.9</confidence><impact>High</impact></threat>
    # Reasons
        - SQL Injection: The tool named {{ tool_name }} detected a potential SQL Injection vulnerability in the input parameter.
    # Summarization:
        ...... (The clear, detailed summary of the security assessment results)
    ```
        '''

        # Stages 2-10: Individual malicious behavior scans
        # Tuple format: (stage_id, name, template, use_oauth)
        malicious_stages = [
            ("2",  "Tool Poisoning (TPA)",                    "agents/dynamic/malicious/tpa",                True),
            ("3",  "Full Schema Poisoning (FSP)",             "agents/dynamic/malicious/fsp",                True),
            ("4",  "Advanced Tool Poisoning (ATPA)",          "agents/dynamic/malicious/atpa",               True),
            ("5",  "Rug Pull Attack",                         "agents/dynamic/malicious/rug_pull",           True),
            ("6",  "MCP Configuration Poisoning",             "agents/dynamic/malicious/config_poisoning",   True),
            ("7",  "Tool Name Spoofing",                      "agents/dynamic/malicious/name_spoofing",      True),
            ("8",  "Tool Shadowing",                          "agents/dynamic/malicious/tool_shadowing",     True),
            ("9",  "Resource Content Poisoning",              "agents/dynamic/malicious/resource_poisoning", True),
            ("10", "MCP Preference Manipulation (MPMA)",      "agents/dynamic/malicious/mpma",               True),
        ]

        # Stages 11-26: Individual vulnerability scans
        # Tuple format: (stage_id, name, template, use_oauth)
        # Stage 14 intentionally disables OAuth to test whether the server
        # rejects unauthenticated requests (401 = no vulnerability; success = vulnerability).
        vuln_stages = [
            ("11", "Prompt Injection",                        "agents/dynamic/vuln/prompt_injection",    True),
            ("12", "Command Injection",                       "agents/dynamic/vuln/command_injection",   True),
            ("13", "Remote Code Execution (RCE)",             "agents/dynamic/vuln/rce",                 True),
            ("14", "Unauthenticated Access",                  "agents/dynamic/vuln/unauth_access",       False),
            ("15", "Confused Deputy (OAuth Proxy)",           "agents/dynamic/vuln/confused_deputy",     True),
            ("16", "Token/Credential Theft",                  "agents/dynamic/vuln/credential_theft",    True),
            ("17", "Token Passthrough",                       "agents/dynamic/vuln/token_passthrough",   True),
            ("18", "Path Traversal",                          "agents/dynamic/vuln/path_traversal",      True),
            ("19", "Localhost Bypass (NeighborJack)",         "agents/dynamic/vuln/localhost_bypass",    True),
            ("20", "Session Management Flaws",                "agents/dynamic/vuln/session_management",  True),
            ("21", "Privilege Abuse/Overbroad Permissions",   "agents/dynamic/vuln/privilege_abuse",     True),
            ("22", "Cross-Repository Data Theft",             "agents/dynamic/vuln/cross_repo_theft",    True),
            ("23", "SQL Injection",                           "agents/dynamic/vuln/sql_injection",       True),
            ("24", "Context Bleeding",                        "agents/dynamic/vuln/context_bleeding",    True),
            ("25", "Configuration File Exposure",             "agents/dynamic/vuln/config_exposure",     True),
            ("26", "Cross-Tenant Data Exposure",              "agents/dynamic/vuln/cross_tenant_exposure", True),
        ]

        # Filter stages when caller specifies a subset
        if selected_stage_ids is not None:
            id_set = {int(i) for i in selected_stage_ids}
            malicious_stages = [s for s in malicious_stages if int(s[0]) in id_set]
            vuln_stages      = [s for s in vuln_stages      if int(s[0]) in id_set]

        all_reports = []
        for stage_id, stage_name, template, use_oauth in malicious_stages + vuln_stages:
            _stage_db(int(stage_id), "running")
            report = await self.pipeline.execute_stage_dynamic(
                ScanStage(stage_id, stage_name, template,
                          output_format=vuln_ret_format, language=self.language),
                prompt, {"信息收集报告": info_collection},
                use_oauth=use_oauth,
            )
            _stage_db(int(stage_id), "completed", report)
            all_reports.append((stage_name, report))

        # Stage 27: Vulnerability Review — consolidate all per-type reports
        review_format = '''
        必须满足以下xml格式，多个漏洞返回多个vuln标签
        <vuln>
          <title>title</title>
          <desc>
          <!-- Markdown格式漏洞描述 -->
          ## 漏洞详情
          **文件位置**:
          **漏洞类型**:
          **风险等级**:

          ### 技术分析

          ### 攻击路径

          ### 影响评估
          </desc>
          <risk_type>Short identifier only, e.g. MCP01 / MCP05 / Name Confusion / CWE-78</risk_type>
          <level>Level</level>
          <suggestion>
          ## 修复建议
          </suggestion>
        </vuln>
        若无漏洞或漏洞为空,返回<empty>
        '''.strip()
        vuln_review_check = lambda x: '<vuln>' in x or '<empty>' in x
        review_context = {name: report for name, report in all_reports}
        _stage_db(27, "running")
        vuln_review = await self.pipeline.execute_stage_dynamic(
            ScanStage("27", "Vulnerability Review", "agents/dynamic/general_analyzing_prompt_template",
                      output_format=review_format,
                      output_check_fn=vuln_review_check, language=self.language),
            prompt, review_context
        )
        _stage_db(27, "completed", vuln_review)

        # 提取与分析结果
        extractor = VulnerabilityExtractor()
        vuln_results = extractor.extract_vulnerabilities(vuln_review)
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
