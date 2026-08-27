from pathlib import Path
import html
import shutil
import subprocess


ROOT = Path.cwd()
OUTPUT = ROOT / "public"

if OUTPUT.exists():
    shutil.rmtree(OUTPUT)

OUTPUT.mkdir()

shutil.copy2(ROOT / "slides.css", OUTPUT / "slides.css")

# Start with a clean Netlify output directory.
if OUTPUT.exists():
    shutil.rmtree(OUTPUT)

OUTPUT.mkdir()

notebooks = sorted(
    path
    for path in ROOT.rglob("*.ipynb")
    if ".ipynb_checkpoints" not in path.parts
    and "public" not in path.parts
    and ".git" not in path.parts
)

presentations = []

for notebook in notebooks:
    relative = notebook.relative_to(ROOT)
    relative_directory = relative.parent
    output_directory = OUTPUT / relative_directory
    output_directory.mkdir(parents=True, exist_ok=True)

    output_name = notebook.stem

    print(f"Building {relative}")

    subprocess.run(
        [
            "jupyter",
            "nbconvert",
            str(notebook),
            "--to",
            "slides",
            "--output",
            output_name,
            "--output-dir",
            str(output_directory),
            "--SlidesExporter.reveal_theme=white",
            "--SlidesExporter.reveal_transition=slide",
        ],
        check=True,
    )

    generated_file = output_directory / f"{output_name}.slides.html"
    final_file = output_directory / f"{output_name}.html"
    generated_file.rename(final_file)

    # Add the common presentation stylesheet.
    html_content = final_file.read_text(encoding="utf-8")

    stylesheet = '<link rel="stylesheet" href="/slides.css">'

    html_content = html_content.replace(
        "</head>",
        f"  {stylesheet}\n</head>",
    )

    final_file.write_text(html_content, encoding="utf-8")

    presentations.append(
        {
            "title": output_name.replace("_", " ").replace("-", " ").title(),
            "source": relative.as_posix(),
            "url": final_file.relative_to(OUTPUT).as_posix(),
        }
    )

items = "\n".join(
    f"""
    <li>
      <a href="/{html.escape(item['url'])}">
        {html.escape(item['title'])}
      </a>
      <small>{html.escape(item['source'])}</small>
    </li>
    """
    for item in presentations
)

index = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Notebook Presentations</title>
  <style>
    body {{
      max-width: 900px;
      margin: 3rem auto;
      padding: 0 1.5rem;
      font-family: system-ui, sans-serif;
      line-height: 1.5;
    }}

    li {{
      margin: 1rem 0;
    }}

    a {{
      font-size: 1.15rem;
      font-weight: 600;
    }}

    small {{
      display: block;
      color: #666;
    }}
  </style>
</head>
<body>
  <h1>Notebook Presentations</h1>
  <ul>
    {items}
  </ul>
</body>
</html>
"""

(OUTPUT / "index.html").write_text(index, encoding="utf-8")

print(f"Built {len(presentations)} presentation(s).")