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
        "-c", "--config",
        default=None,
        help="Path to YAML config file containing target list (for batch scanning)"
    )

    return parser.parse_args()


def sanitize_url_for_filename(url: str) -> str:
    """Convert URL to a safe filename by extracting host and port"""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or "unknown"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        # Replace dots and colons with underscores for safe filename
        return f"{host.replace('.', '_')}_{port}"
    except Exception as e:
        logger.warning(f"Failed to parse URL {url}: {e}")
        # Fallback: use a sanitized version of the full URL
        return url.replace("://", "_").replace("/", "_").replace(":", "_").replace(".", "_")


def setup_target_logging(output_dir: Path, target_url: str):
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
    filename = sanitize_url_for_filename(target_url)
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
    """Load target URLs from YAML config file"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)

        targets = config_data.get('targets', [])
        if not targets:
            logger.warning(f"No targets found in config file: {config_path}")
            return []

        logger.info(f"Loaded {len(targets)} targets from config file")
        return targets
    except FileNotFoundError:
        logger.error(f"Config file not found: {config_path}")
        sys.exit(1)
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse YAML config: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to load config file: {e}")
        sys.exit(1)


async def scan_single_target(target_url: str, args, llm, specialized_llms, output_dir: Path):
    """Scan a single target and return results"""
    logger.info(f"\n{'='*60}")
    logger.info(f"Starting scan for target: {target_url}")
    logger.info(f"{'='*60}\n")

    # Setup logging for this target
    log_file = setup_target_logging(output_dir, target_url)
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
        headers=headers
    )

    result = None
    try:
        # Run dynamic analysis
        result = await agent.dynamic_analysis(prompt)
        logger.info(f"Scan completed for {target_url}")
        logger.info(f"Results:\n{result}")
        return {"target": target_url, "status": "success", "result": result}
    except Exception as e:
        logger.error(f"Scan failed for {target_url}: {e}", exc_info=True)
        mcpLogger.error_log(f"Scan failed for {target_url}: {e}")
        return {"target": target_url, "status": "failed", "error": str(e)}
    finally:
        # Clean up agent resources
        if hasattr(agent, 'dispatcher'):
            try:
                await agent.dispatcher.close()
            except Exception as e:
                logger.warning(f"Failed to close dispatcher for {target_url}: {e}")


async def batch_scan(targets: list, args, llm, specialized_llms):
    """Run scans on multiple targets"""
    # Create time-stamped output directory
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_dir = Path("./logs") / f"scan_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Batch scan started at {timestamp}")
    logger.info(f"Output directory: {output_dir}")
    logger.info(f"Total targets: {len(targets)}")

    results = []
    for idx, target in enumerate(targets, 1):
        logger.info(f"\n[{idx}/{len(targets)}] Processing target: {target}")
        result = await scan_single_target(target, args, llm, specialized_llms, output_dir)
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

    agent = Agent(llm=llm, specialized_llms=specialized_llms, debug=args.debug, server_url=args.server_url,
                  language=args.language, headers=headers)
    try:
        if args.server_url:
            logger.info(f"Server mode enabled with URL: {args.server_url}")
            dynamic_results = await agent.dynamic_analysis(prompt)
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
        # 确保关闭资源
        if hasattr(agent, 'dispatcher'):
            await agent.dispatcher.close()


if __name__ == "__main__":
    # 先解析参数以检查是否为 debug 模式
    args = parse_args()
    # 如果是 debug 模式，初始化 Laminar
    asyncio.run(main())
