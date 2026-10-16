import json
import shutil
import subprocess
import sys

from terai_router.cli import main


def test_cli_json(capsys):
    assert main(['--json', 'ทำต่อเลย']) == 0
    out = json.loads(capsys.readouterr().out)
    assert out['intent'] == 'go_on' and len(out['top']) == 3


def test_cli_threshold_unknown(capsys):
    main(['--threshold', '1.01', 'ทำต่อ'])
    assert capsys.readouterr().out.startswith('unknown')


def test_python_m():
    r = subprocess.run([sys.executable, '-m', 'terai_router', 'ไม่เอา'], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.startswith('refuse')


def test_entry_point_if_installed():
    exe = shutil.which('terai')
    if exe is None:
        return  # not installed as a script in this environment
    r = subprocess.run([exe, 'สวัสดี'], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.startswith('greet')
