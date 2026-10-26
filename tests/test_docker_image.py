import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_changelog_is_copied_into_the_image():
    # Setari -> Despre citeste CHANGELOG.md din imagine; *.md e exclus din .dockerignore
    lines = [l.strip() for l in open(os.path.join(ROOT, ".dockerignore"), encoding="utf-8")]
    assert "*.md" not in lines or lines.index("!CHANGELOG.md") > lines.index("*.md")


def test_untracked_files_do_not_mark_the_build_dirty():
    src = open(os.path.join(ROOT, "tools", "version.py"), encoding="utf-8").read()
    assert '"--untracked-files=no"' in src
