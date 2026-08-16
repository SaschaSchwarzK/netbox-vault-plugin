from __future__ import annotations

import argparse
import html
import shutil
from pathlib import Path


def find_report_root(artifact_dir: Path) -> Path | None:
    if (artifact_dir / 'index.html').is_file():
        return artifact_dir

    for candidate in artifact_dir.rglob('index.html'):
        return candidate.parent

    return None


def main() -> None:
    parser = argparse.ArgumentParser(description='Render a consolidated Playwright report index.')
    parser.add_argument('--artifacts-dir', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--base-commit', required=True)
    args = parser.parse_args()

    artifacts_dir = Path(args.artifacts_dir)
    output_dir = Path(args.output_dir)

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    reports: list[tuple[str, str]] = []
    for artifact_dir in sorted(path for path in artifacts_dir.iterdir() if path.is_dir()):
        report_root = find_report_root(artifact_dir)
        if report_root is None:
            continue

        series = artifact_dir.name.removeprefix('netbox-plugin-e2e-report-v')
        destination = output_dir / f'netbox-v{series}'
        shutil.copytree(report_root, destination)
        reports.append((f'NetBox v{series}', f'./{destination.name}/index.html'))

    if not reports:
        raise SystemExit('No Playwright report artifacts were found.')

    items = '\n'.join(
        f'      <li><a href="{html.escape(link)}">{html.escape(label)}</a></li>'
        for label, link in reports
    )

    output_dir.joinpath('index.html').write_text(
        f'''<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>NetBox Vault Playwright Reports</title>
    <style>
      :root {{
        color-scheme: light;
        font-family: Arial, sans-serif;
      }}
      body {{
        margin: 0;
        padding: 2rem;
        background: #f6f8fa;
        color: #1f2328;
      }}
      main {{
        max-width: 48rem;
        margin: 0 auto;
        background: #ffffff;
        border: 1px solid #d0d7de;
        border-radius: 12px;
        padding: 2rem;
        box-shadow: 0 12px 32px rgba(31, 35, 40, 0.08);
      }}
      h1 {{
        margin-top: 0;
      }}
      ul {{
        line-height: 1.8;
      }}
      code {{
        background: #f0f3f6;
        border-radius: 4px;
        padding: 0.1rem 0.35rem;
      }}
    </style>
  </head>
  <body>
    <main>
      <h1>NetBox Vault Playwright Reports</h1>
      <p>Generated from commit <code>{html.escape(args.base_commit)}</code>.</p>
      <p>Select a committed report for the NetBox version you want to inspect.</p>
      <ul>
{items}
      </ul>
    </main>
  </body>
</html>
''',
        encoding='utf-8',
    )


if __name__ == '__main__':
    main()
