"""Main program - Bill notification system CLI"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from bill_notify.config import AppConfig
from bill_notify.pipeline import create_pipeline
from bill_notify.google_services import GoogleServices
from bill_notify.password_providers import YamlPasswordProvider, CompositePasswordProvider, InteractivePasswordProvider


logger = logging.getLogger(__name__)


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Bill notification system - fetch bills from Gmail and create calendar reminders"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without creating calendar events or marking emails as processed",
    )
    parser.add_argument(
        "--force-reprocess",
        action="store_true",
        help="Ignore existing processed records and overwrite them with this run's results",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )
    parser.add_argument(
        "--config", type=str, help="Path to config file (overrides default)"
    )
    parser.add_argument(
        "--label", type=str, help="Gmail label to filter (overrides config)"
    )
    parser.add_argument(
        "--reminder-days",
        type=str,
        help="Reminder days in advance, e.g. 7 or 7,3,1 (overrides config)",
    )
    parser.add_argument(
        "--calendar-id", type=str, help="Calendar ID (overrides config)"
    )
    parser.add_argument(
        "--days-back",
        type=int,
        help="Number of days to look back for emails (overrides config)",
    )
    parser.add_argument(
        "--credentials-file",
        type=str,
        help="Path to Google OAuth credentials JSON (overrides config)",
    )
    parser.add_argument(
        "--token-file",
        type=str,
        help="Path to Google OAuth token JSON (overrides config)",
    )
    parser.add_argument(
        "--download-dir",
        type=str,
        help="Directory for downloaded PDF attachments (overrides config)",
    )
    parser.add_argument(
        "--processed-log",
        type=str,
        help="Path to processed email/attachment log (overrides config)",
    )
    parser.add_argument(
        "--pdf-passwords-file",
        type=str,
        help="Path to PDF passwords YAML (overrides config)",
    )
    parser.add_argument(
        "--ocr-cache-dir",
        type=str,
        help="Directory for cached PaddleOCR/PaddleX models (overrides config)",
    )
    parser.add_argument(
        "--model",
        type=str,
        help="OpenRouter model name (overrides config)",
    )
    return parser.parse_args()


async def main():
    """Program entry point"""
    try:
        args = parse_args()

        # Configure logging
        log_level = logging.DEBUG if args.verbose else logging.INFO
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[logging.StreamHandler(sys.stdout)],
            force=True,
        )

        # Load configuration
        config = AppConfig.load(
            dry_run=args.dry_run,
            verbose=args.verbose,
            force_reprocess=args.force_reprocess,
            config_file=args.config,
            label=args.label,
            reminder_days=args.reminder_days,
            calendar_id=args.calendar_id,
            days_back=args.days_back,
            credentials_file=args.credentials_file,
            token_file=args.token_file,
            download_dir=args.download_dir,
            processed_log=args.processed_log,
            pdf_passwords_file=args.pdf_passwords_file,
            ocr_cache_dir=args.ocr_cache_dir,
            model=args.model,
        )

        # Set up Google services
        google_services = GoogleServices(
            credentials_file=config.gmail.credentials_file,
            token_file=config.gmail.token_file,
        )

        # Set up password provider
        yaml_provider = YamlPasswordProvider.from_file(
            config.pdf_passwords_file
        )
        interactive_provider = InteractivePasswordProvider(
            save_path=config.pdf_passwords_file
        )
        password_provider = CompositePasswordProvider(
            yaml_provider=yaml_provider,
            interactive_provider=interactive_provider,
        )

        # Create and run pipeline
        pipeline = create_pipeline(
            google_services=google_services,
            password_provider=password_provider,
            llm_api_key=config.openrouter.api_key,
            llm_model=config.openrouter.model,
            download_dir=Path(config.download_dir),
            processed_log=Path(config.processed_log),
            ocr_cache_dir=Path(config.ocr_cache_dir),
            calendar_id=config.calendar.calendar_id,
            reminder_days=config.calendar.reminder_days,
            gmail_label=config.gmail.gmail_label,
            days_back=config.gmail.days_back,
            dry_run=config.dry_run,
            verbose=config.verbose,
            force_reprocess=config.force_reprocess,
        )

        logger.debug("Verbose logging enabled")
        await pipeline.run()

    except ValueError as e:
        logger.exception(f"Configuration error: {e}")
        sys.exit(1)
    except FileNotFoundError as e:
        logger.error(f"File error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Execution error: {e}", exc_info=True)
        sys.exit(1)


def cli():
    """CLI entry point for console script"""
    asyncio.run(main())


if __name__ == "__main__":
    asyncio.run(main())
