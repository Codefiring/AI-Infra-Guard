#!/usr/bin/env python3
"""
Agent Framework - 主入口文件

这是一个模仿 Claude Code / Gemini CLI 的 Agent 框架。
Agent 可以自动调用工具完成任务。
"""
import asyncio
import os
import sys
import argparse
import yaml
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from agent.agent import Agent
from utils.llm import LLM
# 配置专用模型
from utils.llm_manager import LLMManager
from utils.loging import logger
from utils.aig_logger import mcpLogger
from utils import config

# 重要：导入 tools 包以触发工具注册
import tools as _


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="Agent Framework - 代码扫描和漏洞检测工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # 必需参数
    parser.add_argument(
        "--repo",
        default="",
        help="要扫描的项目文件夹路径"
    )

    # 可选参数
    parser.add_argument(
        "-p", "--prompt",
        default="",
        help="自定义扫描提示词（可选）"
    )

    parser.add_argument(
        "-m", "--model",
        default=config.DEFAULT_MODEL,
        help=f"LLM 模型名称（默认: {config.DEFAULT_MODEL}）"
    )

    parser.add_argument(
        "-k", "--api_key",
        default=None,
        help="API Key（如果不提供，将从环境变量 OPENROUTER_API_KEY 读取）"
    )

    parser.add_argument(
        "-u", "--base_url",
        default=config.DEFAULT_BASE_URL,
        help=f"API 基础 URL（默认: {config.DEFAULT_BASE_URL}）"
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="启用 debug 模式（包括 Laminar 跟踪）",
        default=False,
    )

    parser.add_argument(
        "--server_url",
        help=f"remote MCP server URL",
        default=None
    )

    parser.add_argument(
        "--header",
        action="append",
        dest="headers",
        help="Custom header in key:value format (can be used multiple times)",
        default=[]
    )

    parser.add_argument("--language", default="zh", help="Output language (zh/en)")

    parser.add_argument(
        "--stages",
        default=None,
        help="Comma-separated stage IDs to run (e.g. 2,5,11,14). "
             "Stages 1 and 27 always run. Default: all stages."
    )

    parser.add_argument(
        "-c", "--config",
        default=None,
        help="Path to YAML config file containing target list (for batch scanning)"
    )

    # OAuth 2.0 Client Credentials (all three required together; scope is optional)
    parser.add_argument(
        "--oauth-client-id",
        default=None,
        help="OAuth 2.0 client ID (Client Credentials flow)",
    )
    parser.add_argument(
        "--oauth-client-secret",
        default=None,
        help="OAuth 2.0 client secret (Client Credentials flow)",
    )
    parser.add_argument(
        "--oauth-token-url",
        default=None,
        help="OAuth 2.0 token endpoint URL",
    )
    parser.add_argument(
        "--oauth-scope",
        default=None,
        help="OAuth 2.0 scope (optional, space-separated)",
    )

    parser.add_argument(
        "--task-id",
        default=None,
        help="DB task ID (set by web server for direct DB writes)",
    )
    parser.add_argument(
        "--target-id",
        default=None,
        help="DB task_target ID (set by web server for direct DB writes)",
    )

    return parser.parse_args()


def sanitize_url_for_filename(url: str, name: str = None) -> str:
    """Convert URL to a safe filename by extracting host and port, optionally with a name prefix"""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or "unknown"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        # Replace dots and colons with underscores for safe filename
        filename = f"{host.replace('.', '_')}_{port}"

        # Add name prefix if provided
        if name:
            filename = f"{name}_{filename}"

        return filename
    except Exception as e:
        logger.warning(f"Failed to parse URL {url}: {e}")
        # Fallback: use a sanitized version of the full URL
        sanitized = url.replace("://", "_").replace("/", "_").replace(":", "_").replace(".", "_")
        if name:
            sanitized = f"{name}_{sanitized}"
        return sanitized


def setup_target_logging(output_dir: Path, target_url: str, target_name: str = None):
    """Setup logging for a specific target"""
    from loguru import logger as loguru_logger

    # Remove existing file handlers
    loguru_logger.remove()

    # Re-add console handler
    loguru_logger.add(
        sys.stderr,
        level="INFO",
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
    )

    # Add target-specific file handler
    filename = sanitize_url_for_filename(target_url, target_name)
    log_file = output_dir / f"{filename}.log"
    loguru_logger.add(
        str(log_file),
        rotation="10 MB",
        retention="10 days",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
        mode="w",
    )

    return log_file


def load_targets_from_config(config_path: str) -> list:
    """Load target URLs from YAML config file

    Supports two formats:
    1. New format (with names):
       targets:
         - name: "MCP01"
           url: "http://ip:port"

    2. Old format (simple strings):
       targets:
         - "http://ip:port"

    Returns list of dicts: [{"name": "MCP01", "url": "http://..."}, ...]
    """
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)

        raw_targets = config_data.get('targets', [])
        if not raw_targets:
            logger.warning(f"No targets found in config file: {config_path}")
            return []

        # Normalize targets to dict format
        normalized_targets = []
        for idx, target in enumerate(raw_targets, 1):
            if isinstance(target, dict):
                # New format with name and url
                if 'url' not in target:
                    logger.warning(f"Target {idx} missing 'url' field, skipping")
                    continue
                normalized_targets.append({
                    'name': target.get('name'),
                    'url': target['url'],
                    'stages': target.get('stages') or None,
                })
            elif isinstance(target, str):
                # Old format - simple URL string
                normalized_targets.append({
                    'name': None,
                    'url': target,
                    'stages': None,
                })
            else:
                logger.warning(f"Invalid target format at index {idx}, skipping")

        logger.info(f"Loaded {len(normalized_targets)} targets from config file")
        return normalized_targets
    except FileNotFoundError:
        logger.error(f"Config file not found: {config_path}")
        sys.exit(1)
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse YAML config: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to load config file: {e}")
        sys.exit(1)


def build_oauth_config(args):
    """
    Build an OAuthConfig from parsed CLI args, or return None if OAuth is not configured.
    Exits with an error if only a partial OAuth config is provided.
    """
    provided = {
        k: v for k, v in {
            "client_id": getattr(args, "oauth_client_id", None),
            "client_secret": getattr(args, "oauth_client_secret", None),
            "token_url": getattr(args, "oauth_token_url", None),
        }.items() if v
    }

    if not provided:
        return None

    required = {"client_id", "client_secret", "token_url"}
    missing = required - provided.keys()
    if missing:
        flag_names = ", ".join(f"--oauth-{k.replace('_', '-')}" for k in sorted(missing))
        logger.error(f"Incomplete OAuth configuration. Missing: {flag_names}")
        sys.exit(1)

    from utils.mcp_oauth import OAuthConfig
    config = OAuthConfig(
        client_id=args.oauth_client_id,
        client_secret=args.oauth_client_secret,
        token_url=args.oauth_token_url,
        scope=getattr(args, "oauth_scope", None),
    )
    logger.info(f"OAuth configured: token_url={config.token_url}, client_id={config.client_id}")
    return config


async def scan_single_target(target_url: str, args, llm, specialized_llms, output_dir: Path, target_name: str = None, oauth_config=None, selected_stage_ids: list = None):
    """Scan a single target and return results"""
    display_name = f"{target_name} ({target_url})" if target_name else target_url

    logger.info(f"\n{'='*60}")
    logger.info(f"Starting scan for target: {display_name}")
    logger.info(f"{'='*60}\n")

    # Setup logging for this target
    log_file = setup_target_logging(output_dir, target_url, target_name)
    logger.info(f"Logging to: {log_file}")

    # Prepare prompt
    prompt = args.prompt
    if args.language == "en":
        prompt += "All responses should be in English."
    elif args.language == "zh":
        prompt += "所有回复都应使用中文。"

    # Parse headers
    headers = {}
    if args.headers:
        for header_item in args.headers:
            try:
                if ':' in header_item:
                    key, value = header_item.split(':', 1)
                    headers[key.strip()] = value.strip()
                elif '=' in header_item:
                    key, value = header_item.split('=', 1)
                    headers[key.strip()] = value.strip()
                else:
                    logger.warning(f"Ignored invalid header format: {header_item}")
            except Exception as e:
                logger.warning(f"Failed to parse header {header_item}: {e}")

    # Create agent for this target
    agent = Agent(
        llm=llm,
        specialized_llms=specialized_llms,
        debug=args.debug,
        server_url=target_url,
        language=args.language,
        headers=headers,
        oauth_config=oauth_config,
    )

    result = None
    try:
        # Run dynamic analysis
        result = await agent.dynamic_analysis(prompt, selected_stage_ids=selected_stage_ids)
        logger.info(f"Scan completed for {display_name}")
        logger.info(f"Results:\n{result}")
        return {"target": target_url, "name": target_name, "status": "success", "result": result}
    except Exception as e:
        logger.error(f"Scan failed for {display_name}: {e}", exc_info=True)
        mcpLogger.error_log(f"Scan failed for {display_name}: {e}")
        return {"target": target_url, "name": target_name, "status": "failed", "error": str(e)}
    finally:
        # Clean up agent resources
        if hasattr(agent, 'dispatcher'):
            try:
                await agent.dispatcher.close()
            except Exception as e:
                logger.warning(f"Failed to close dispatcher for {display_name}: {e}")


async def batch_scan(targets: list, args, llm, specialized_llms):
    """Run scans on multiple targets"""
    # Create time-stamped output directory
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_dir = Path("./logs") / f"scan_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Batch scan started at {timestamp}")
    logger.info(f"Output directory: {output_dir}")
    logger.info(f"Total targets: {len(targets)}")

    oauth_config = build_oauth_config(args)

    results = []
    for idx, target in enumerate(targets, 1):
        target_url = target['url']
        target_name = target.get('name')
        display_name = f"{target_name} ({target_url})" if target_name else target_url

        logger.info(f"\n[{idx}/{len(targets)}] Processing target: {display_name}")
        result = await scan_single_target(
            target_url, args, llm, specialized_llms, output_dir, target_name,
            oauth_config=oauth_config,
            selected_stage_ids=target.get('stages'),
        )
        results.append(result)

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("Batch scan completed")
    logger.info(f"{'='*60}")

    success_count = sum(1 for r in results if r["status"] == "success")
    failed_count = len(results) - success_count

    logger.info(f"Total targets: {len(results)}")
    logger.info(f"Successful: {success_count}")
    logger.info(f"Failed: {failed_count}")
    logger.info(f"Results saved to: {output_dir}")

    return results


async def main():
    """主函数"""
    # 解析命令行参数
    args = parse_args()

    # 获取 API Key（优先使用命令行参数，否则从环境变量读取）
    api_key = args.api_key or os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        logger.error("API Key not provided. Use --api-key or set OPENROUTER_API_KEY environment variable.")
        sys.exit(1)

    # 创建主 LLM 实例
    llm = LLM(model=args.model, api_key=api_key, base_url=args.base_url)
    logger.info(f"Main LLM initialized: {args.model}")

    # 使用主 API Key 作为默认值
    llm_manager = LLMManager(api_key=api_key, base_url=args.base_url)

    # 获取专用LLM实例字典
    specialized_llms = llm_manager.get_specialized_llms(["thinking", "coding"])
    logger.info(f"Specialized LLMs configured: {list(specialized_llms.keys())}")

    # Check if batch scanning mode is enabled
    if args.config:
        logger.info(f"Batch scanning mode enabled with config: {args.config}")
        targets = load_targets_from_config(args.config)
        if not targets:
            logger.error("No targets found in config file")
            sys.exit(1)

        try:
            results = await batch_scan(targets, args, llm, specialized_llms)
            logger.info("All scans completed")
        except KeyboardInterrupt:
            print("\n\nBatch scan interrupted by user.")
            logger.warning("Batch scan interrupted by user")
        except Exception as e:
            print(f"\n\nError during batch scan: {e}")
            logger.error(f"Error during batch scan: {e}", exc_info=True)
            raise
        return

    # Parse --stages flag (single-target mode)
    selected_ids = None
    if getattr(args, "stages", None):
        selected_ids = [int(s.strip()) for s in args.stages.split(",") if s.strip().isdigit()]
        invalid = [s for s in selected_ids if s < 2 or s > 26]
        if invalid:
            logger.error(f"Invalid stage IDs (must be 2-26): {invalid}")
            sys.exit(1)
        logger.info(f"Stage filter: {sorted(selected_ids)}")

    # Single target mode (original logic)
    logger.info(f"Starting scan on: {args.repo}")
    prompt = args.prompt
    if args.language == "en":
        prompt += "All responses should be in English."
    elif args.language == "zh":
        prompt += "所有回复都应使用中文。"
    if prompt:
        logger.info(f"Custom prompt: {prompt}")

    # 解析 headers
    headers = {}
    if args.headers:
        for header_item in args.headers:
            try:
                if ':' in header_item:
                    key, value = header_item.split(':', 1)
                    headers[key.strip()] = value.strip()
                elif '=' in header_item:
                    key, value = header_item.split('=', 1)
                    headers[key.strip()] = value.strip()
                else:
                    logger.warning(f"Ignored invalid header format: {header_item}")
            except Exception as e:
                logger.warning(f"Failed to parse header {header_item}: {e}")

        if headers:
            logger.info(f"Custom headers: {headers}")

    oauth_config = build_oauth_config(args)
    agent = Agent(llm=llm, specialized_llms=specialized_llms, debug=args.debug, server_url=args.server_url,
                  language=args.language, headers=headers, oauth_config=oauth_config)

    task_id_arg   = getattr(args, "task_id",   None)
    target_id_arg = getattr(args, "target_id", None)

    # Mark task/target as running in DB (web server created the rows)
    if task_id_arg:
        try:
            from db import task_set_running, target_set_running as _target_set_running
            task_set_running(task_id_arg, log_file=None)
            if target_id_arg:
                _target_set_running(target_id_arg)
        except Exception as e:
            logger.warning(f"DB init: {e}")

    _scan_succeeded = False
    try:
        if args.server_url:
            logger.info(f"Server mode enabled with URL: {args.server_url}")
            dynamic_results = await agent.dynamic_analysis(
                prompt, selected_stage_ids=selected_ids, task_target_id=target_id_arg
            )
            _scan_succeeded = True
            logger.info(f"Dynamic analysis results:\n{dynamic_results}")
        else:
            # 验证项目路径
            if not os.path.exists(args.repo):
                logger.error(f"Project path does not exist: {args.repo}")
                sys.exit(1)

            if not os.path.isdir(args.repo):
                logger.error(f"Project path is not a directory: {args.repo}")
                sys.exit(1)
            result = await agent.scan(args.repo, prompt)
            _scan_succeeded = True
            logger.info(f"Scan completed successfully:\n\n {result}")
    except KeyboardInterrupt:
        print("\n\nTask interrupted by user.")
        logger.warning("Task interrupted by user")
    except Exception as e:
        print(f"\n\nError during execution: {e}")
        logger.error(f"Error during execution: {e}", exc_info=True)
        mcpLogger.error_log(f"Execution failed: {e}")
        raise Exception(f"Execution failed: {e}")
    finally:
        # Mark task done in DB (poll_task_db in web_server reads this)
        if task_id_arg:
            try:
                from db import task_set_done as _task_set_done
                _task_set_done(task_id_arg, "completed" if _scan_succeeded else "failed")
            except Exception:
                pass
        # 确保关闭资源
        if hasattr(agent, 'dispatcher'):
            await agent.dispatcher.close()


if __name__ == "__main__":
    # 先解析参数以检查是否为 debug 模式
    args = parse_args()
    # 如果是 debug 模式，初始化 Laminar
    asyncio.run(main())
