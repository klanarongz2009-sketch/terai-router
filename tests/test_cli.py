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


def test_chat_commands_require_existing_explicit_syntax():
    from terai_router.cli import _parse_chat_command

    assert _parse_chat_command('/quit') == ('exit',)
    assert _parse_chat_command('/exit') == ('exit',)
    assert _parse_chat_command('/image photo.png what is this?') == ('image', 'photo.png', 'what is this?')
    assert _parse_chat_command('/image') == ('usage',)
    assert _parse_chat_command('Could you explain /quit to me?') is None
    assert _parse_chat_command('Please show me the /image command') is None
    assert _parse_chat_command('ordinary chat about images') is None
