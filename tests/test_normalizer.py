from terai_router.normalizer import fold, normalize, skeleton


def test_known_typo_pairs():
    assert normalize('เส็ดหรือยัง') == 'เสร็จหรือยัง'


def test_guard_keeps_correct_word():
    # 'พิม' inside the correct word 'พิมพ์' must not be touched
    assert normalize('พิมพ์ผิด') == 'พิมพ์ผิด'


def test_repeat_collapse():
    assert normalize('ไม่ต้องแล้ววววว').endswith('แล้ว')


def test_return_changes():
    out, ch = normalize('เส็ดยัง', return_changes=True)
    assert out != 'เส็ดยัง' and ch


def test_fold_digits_and_space():
    assert fold('  12  คูณ ๑๒ ') == '0 คูณ 0'
    assert fold('ABC') == 'abc'


def test_skeleton_merges_same_sound():
    assert skeleton('หน่อย') == skeleton('น้อย')
    assert skeleton('ได้') == skeleton('ใด้')
