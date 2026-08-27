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
import os
import re


# Netlify runs the build command from the repository root.
ROOT = Path.cwd()

# Netlify publishes this generated directory.
OUTPUT = ROOT / "public"

# Every generated deck loads this one common stylesheet.
STYLESHEET_SOURCE = ROOT / "slides.css"

# Empty on root-domain hosts; "/DATA301-AML" on GitHub Pages.
SITE_BASE = os.environ.get(
    "SITE_BASE",
    "",
).rstrip("/")

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
    """Add CSS, responsive canvas settings, and static bullet fragments.

    This function performs static text transformations only. It does not insert
    JavaScript that runs before Reveal.initialize. That distinction matters:
    an error in injected runtime JavaScript can prevent Reveal from starting.

    Bullet fragments are written directly into the final HTML. Consequently,
    Reveal sees them during its normal initialization and handles keyboard
    navigation without any post-initialization synchronization.
    """
    document = presentation.read_text(encoding="utf-8")

    def make_content_fragment(match: re.Match[str]) -> str:
        """Add Reveal fragment classes to an opening paragraph or list-item tag."""
        tag = match.group("tag")
        attributes = match.group("attributes") or ""

        class_pattern = re.compile(
            r'\bclass=(["\'])(.*?)\1',
            re.IGNORECASE,
        )
        class_match = class_pattern.search(attributes)

        # Preserve elements explicitly marked as always visible.
        if class_match:
            existing_classes = class_match.group(2).split()

            if "no-fragment" in existing_classes:
                return match.group(0)

            if "fragment" not in existing_classes:
                existing_classes.extend(["fragment", "fade-up"])

                quote = class_match.group(1)
                replacement = (
                    f'class={quote}'
                    f'{" ".join(existing_classes)}'
                    f'{quote}'
                )

                attributes = (
                    attributes[:class_match.start()]
                    + replacement
                    + attributes[class_match.end():]
                )
        else:
            attributes = f' class="fragment fade-up"{attributes}'

        return f"<{tag}{attributes}>"

    # Make paragraphs, list items, and images Reveal fragments.
    document = re.sub(
        r"<(?P<tag>p|li|img|pre)(?P<attributes>\s[^>]*)?>",
        make_content_fragment,
        document,
        flags=re.IGNORECASE,
    )

    # Add responsive sizing to nbconvert's existing Reveal configuration.
    initializer = "Reveal.initialize({"

    responsive_options = """Reveal.initialize({
    width: "100%",
    height: "100%",
    margin: 0.025,
    center: true,"""

    if initializer not in document:
        raise RuntimeError(
            f"Reveal initializer not found in {presentation}"
        )

    document = document.replace(
        initializer,
        responsive_options,
        1,
    )

    # Load shared CSS after Reveal's theme.
    stylesheet_link = (
    f'<link rel="stylesheet" '
    f'href="{SITE_BASE}/slides.css">'
)

    document = document.replace(
        "</head>",
        f"  {stylesheet_link}\n</head>",
        1,
    )

    # Add the fixed Structure button.
    overview_button = r"""
    <button
      id="slide-overview-button"
      type="button"
      aria-label="View slide structure"
      title="View slide structure (O or Esc)"
      onclick="Reveal.toggleOverview(); return false;">
      <span aria-hidden="true">▦</span>
      <span>Structure</span>
    </button>
    """

    document = document.replace(
        "</body>",
        f"{overview_button}\n</body>",
        1,
    )

    presentation.write_text(document, encoding="utf-8")

def write_index(presentations: list[tuple[Path, Path]]) -> None:
    """Generate the root homepage with a link to every slide deck."""
    items = "\n".join(
        f"""
        <li>
          <a href="{SITE_BASE}/{html.escape(output.relative_to(OUTPUT).as_posix())}">
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
