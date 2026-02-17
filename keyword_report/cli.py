"""CLI entry point for keyword report generation."""

import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.status import Status

from .main import generate_keyword_report


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(
        prog="keyword-report",
        description="Generate a keyword opportunity PDF for any business website.",
    )
    parser.add_argument(
        "--url",
        required=True,
        help="Website URL to analyze",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output PDF path (default: keyword_report_{business}.pdf)",
    )
    args = parser.parse_args()

    console = Console()
    status = Status("", console=console)
    status.start()

    def on_progress(msg: str):
        status.update(f"[bold cyan]{msg}[/]")

    try:
        pdf_path = asyncio.run(
            generate_keyword_report(
                url=args.url,
                output_path=args.output,
                on_progress=on_progress,
            )
        )
        status.stop()
        console.print(f"\n[bold green]Done![/] Report saved to [bold]{pdf_path}[/]\n")
    except KeyboardInterrupt:
        status.stop()
        console.print("\n[yellow]Cancelled.[/]")
        sys.exit(1)
    except Exception as e:
        status.stop()
        console.print(f"\n[bold red]Error:[/] {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
