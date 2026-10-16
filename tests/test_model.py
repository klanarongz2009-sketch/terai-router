import json
import os

import pytest

from terai_router import INTENTS, IntentModel, features, route

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope='module')
def model():
    return IntentModel.load()


def test_classes_match_intents(model):
    assert sorted(model.classes) == sorted(INTENTS)


def test_features_are_deterministic():
    assert features('ทำต่อ') == features('ทำต่อ')
    assert len(set(features('ทำต่อ'))) == len(features('ทำต่อ'))


@pytest.mark.parametrize('text,intent', [
    ('สวัสดีครับ', 'greet'),
    ('12 คูณ 8 ได้เท่าไร', 'calc'),
    ('ผมชื่ออะไร', 'get_name'),
    ('ผมชื่อเจมส์', 'set_name'),
    ('ทำต่อเลย', 'go_on'),
    ('ไม่เอา', 'refuse'),
    ('ขอบคุณมาก', 'thanks'),
    ('กี่โมงแล้ว', 'time'),
])
def test_obvious_sentences(text, intent):
    assert route(text)['intent'] == intent


def test_output_shape():
    r = route('เส็ดหรือยัง')
    assert set(r) == {'intent', 'confidence', 'coverage', 'normalized', 'ranking'}
    assert 0.0 <= r['confidence'] <= 1.0
    assert abs(sum(p for _, p in route('x', top=15)['ranking']) - 1.0) < 1e-9


def test_model_is_small():
    p = os.path.join(REPO, 'src', 'terai_router', 'data', 'model.json')
    assert os.path.getsize(p) < 8 * 1024 * 1024


def _acc(model, name):
    sets = json.load(open(os.path.join(REPO, 'eval', name), encoding='utf-8'))
    items = [it for k, v in sets.items() if not k.startswith('_') for it in v]
    return sum(model.predict(t)['intent'] == y for t, y in items) / len(items)


def test_regression_frozen_test_set(model):
    # v0.6.1 scored 0.653 on this set; v0.7 must not fall back below 0.85
    assert _acc(model, 'test_set.json') >= 0.85


def test_regression_heldout(model):
    assert _acc(model, 'heldout_v07.json') >= 0.85
