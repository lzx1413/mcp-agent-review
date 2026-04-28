import os
import pytest


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch, tmp_path):
    """Ensure tests don't touch real git repos or make API calls."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("REVIEW_MODEL", raising=False)


SAMPLE_DIFF = """\
diff --git a/src/main.py b/src/main.py
index 1234567..abcdefg 100644
--- a/src/main.py
+++ b/src/main.py
@@ -10,6 +10,8 @@ def hello():
     print("hello")
+    print("world")
+    return True
"""

SAMPLE_DIFF_MULTI = """\
diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1,3 +5,4 @@
 line1
+added
diff --git a/b.py b/b.py
--- a/b.py
+++ b/b.py
@@ -20,2 +20,3 @@
 existing
+new_line
"""
