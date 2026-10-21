"""The web demo UI is English only (memory M113); see eval/check_web_ui_english.py."""
import importlib.util
from pathlib import Path


def test_web_ui_is_english_only():
    path = Path(__file__).resolve().parent.parent / 'eval' / 'check_web_ui_english.py'
    spec = importlib.util.spec_from_file_location('check_web_ui_english', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.check() == []
