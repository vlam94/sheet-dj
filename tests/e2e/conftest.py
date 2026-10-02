import importlib.util

# The browser tests need the `e2e` extra. Without it (as in CI) they are left out instead of
# failing the whole run at import time, before `-m 'not e2e'` can deselect them.
collect_ignore = [] if importlib.util.find_spec("playwright") else ["test_page.py"]
