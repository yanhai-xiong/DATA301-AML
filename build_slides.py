"""Build all repository notebooks as Reveal.js presentations.

NETLIFY WORKFLOW
1. Netlify clones the GitHub repository.
2. Netlify installs nbconvert.
3. Netlify runs this script from the repository root.
4. The script finds every .ipynb recursively.
5. nbconvert creates Reveal.js HTML without executing notebook cells.
6. The script adds shared CSS and presentation behavior.
7. Netlify publishes the generated public directory.

After this one-time setup, normal course updates only require editing and
pushing notebook files.
"""

from __future__ import annotations

from pathlib import Path
import html
import shutil
import subprocess
import sys


# Netlify runs the build command from the repository root.
ROOT = Path.cwd()

# Netlify publishes this generated directory.
OUTPUT = ROOT / "public"

# Every generated deck loads this one common stylesheet.
STYLESHEET_SOURCE = ROOT / "slides.css"


def prepare_output_directory() -> None:
    """Clean public and then copy shared static files.

    Cleaning removes stale presentations when a notebook is deleted. The CSS
    must be copied after cleaning; copying it before cleaning deletes it.
    """
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True)

    if not STYLESHEET_SOURCE.is_file():
        raise FileNotFoundError(f"Required stylesheet not found: {STYLESHEET_SOURCE}")
    shutil.copy2(STYLESHEET_SOURCE, OUTPUT / "slides.css")


def discover_notebooks() -> list[Path]:
    """Find notebooks recursively, excluding internal/generated directories."""
    ignored_parts = {".git", ".ipynb_checkpoints", "public"}
    return sorted(
        notebook
        for notebook in ROOT.rglob("*.ipynb")
        if not ignored_parts.intersection(notebook.parts)
    )


def convert_notebook(notebook: Path) -> Path:
    """Convert one notebook without running its code cells.

    Notebook cell metadata supplies the presentation structure:
    slide = horizontal slide
    subslide = vertical slide
    fragment = reveal the whole cell incrementally
    skip = omit the cell

    Running nbconvert through the current Python interpreter avoids PATH
    problems in Netlify.
    """
    relative = notebook.relative_to(ROOT)
    destination = OUTPUT / relative.parent
    destination.mkdir(parents=True, exist_ok=True)

    print(f"Building {relative}")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "nbconvert",
            str(notebook),
            "--to",
            "slides",
            "--output",
            notebook.stem,
            "--output-dir",
            str(destination),
            "--SlidesExporter.reveal_theme=simple",
            "--SlidesExporter.reveal_transition=fade",
        ],
        check=True,
    )

    generated = destination / f"{notebook.stem}.slides.html"
    final = destination / f"{notebook.stem}.html"
    if not generated.is_file():
        raise FileNotFoundError(f"nbconvert did not produce {generated}")

    generated.rename(final)
    return final


def enhance_presentation(presentation: Path) -> None:
    """Add shared CSS, incremental bullets, and Reveal configuration.

    Fragment classes are inserted immediately before Reveal.initialize.
    Reveal must see them during initialization or the browser can hide bullets
    without registering them for keyboard navigation.

    A section containing direct child sections is a vertical-stack wrapper.
    It is not an actual slide, so it must not receive fragment processing.
    """
    document = presentation.read_text(encoding="utf-8")

    # Load shared CSS after Reveal's theme so our palette takes precedence.
    stylesheet_link = '<link rel="stylesheet" href="/slides.css">'
    document = document.replace("</head>", f"  {stylesheet_link}\n</head>", 1)

    fragment_setup = r"""
// Make ordinary Markdown bullets appear one at a time.
document.querySelectorAll(".reveal .slides section").forEach((slide) => {
  // Ignore Reveal's wrapper around a vertical stack.
  if (slide.querySelector(":scope > section")) return;

  let sequence = 0;
  slide.querySelectorAll("ul > li, ol > li").forEach((item) => {
    // Use class="no-fragment" on an HTML list item to keep it visible.
    if (item.classList.contains("no-fragment")) return;
    item.classList.add("fragment", "fade-up");
    item.dataset.fragmentIndex = String(sequence);
    sequence += 1;
  });
});
"""

    initializer = "Reveal.initialize("
    if initializer not in document:
        raise RuntimeError(f"Reveal initializer not found in {presentation}")

    # Insert into nbconvert's existing JavaScript block before initialization.
    document = document.replace(
        initializer,
        f"{fragment_setup}\n{initializer}",
        1,
    )

    configuration = r"""
<script>
document.addEventListener("DOMContentLoaded", () => {
  Reveal.configure({
    // Reveal scales this stable 16:9 canvas to the browser.
    width: 1600,
    height: 900,
    margin: 0.035,
    minScale: 0.2,
    maxScale: 2.0,
    center: true,
    controls: true,
    progress: true,
    hash: true,
    transition: "fade",
    backgroundTransition: "fade"
  });
});
</script>
"""

    # CSS must not override Reveal's section width, height, or transforms.
    document = document.replace("</body>", f"{configuration}\n</body>", 1)
    presentation.write_text(document, encoding="utf-8")


def write_index(presentations: list[tuple[Path, Path]]) -> None:
    """Generate the root homepage with a link to every slide deck."""
    items = "\n".join(
        f"""
        <li>
          <a href="/{html.escape(output.relative_to(OUTPUT).as_posix())}">
            {html.escape(source.stem.replace("_", " ").replace("-", " ").title())}
          </a>
          <small>{html.escape(source.relative_to(ROOT).as_posix())}</small>
        </li>
        """
        for source, output in presentations
    )

    index = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Notebook Presentations</title>
  <style>
    body {{ max-width: 900px; margin: 3rem auto; padding: 0 1.5rem;
            font-family: system-ui, sans-serif; line-height: 1.5; }}
    li {{ margin: 1rem 0; }}
    a {{ color: #168aad; font-size: 1.15rem; font-weight: 650; }}
    small {{ display: block; color: #627d98; }}
  </style>
</head>
<body>
  <h1>Notebook Presentations</h1>
  <ul>{items}</ul>
</body>
</html>
"""
    (OUTPUT / "index.html").write_text(index, encoding="utf-8")


def main() -> None:
    """Run the complete GitHub-notebook-to-Netlify-slides workflow."""
    prepare_output_directory()
    notebooks = discover_notebooks()
    presentations: list[tuple[Path, Path]] = []

    for notebook in notebooks:
        presentation = convert_notebook(notebook)
        enhance_presentation(presentation)
        presentations.append((notebook, presentation))

    write_index(presentations)
    print(f"Built {len(presentations)} presentation(s).")


if __name__ == "__main__":
    main()
