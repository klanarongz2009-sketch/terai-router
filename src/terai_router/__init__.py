"""TER-AI: offline Thai intent router that tolerates typos.

    >>> from terai_router import route
    >>> route('เส็ดหรือยัง')['intent']
    'status'
"""
from .model import IntentModel, features
from .normalizer import normalize, skeleton

__version__ = '0.14.0'
__all__ = ['IntentModel', 'route', 'normalize', 'skeleton', 'features', 'INTENTS', 'Chat', 'Knowledge', '__version__']

INTENTS = {
    'greet': 'greeting / ทักทาย',
    'help': 'ask for commands or how to use / ถามวิธีใช้',
    'time': 'ask the time or date / ถามเวลา วันที่',
    'get_name': "ask the user's own name / ถามชื่อตัวเอง",
    'set_name': 'tell or change the user name / บอกชื่อให้จำ',
    'calc': 'arithmetic / คิดเลข',
    'random': 'random number, dice, coin / สุ่ม',
    'stats': 'chat usage statistics / สถิติการคุย',
    'forget': 'clear memory / ล้างความจำ',
    'who': 'ask about the bot / ถามว่าบอทเป็นใคร',
    'thanks': 'thanks or praise / ขอบคุณ',
    'fix': 'something is wrong, redo / ผิด ให้แก้',
    'go_on': 'proceed, continue / ทำต่อ',
    'refuse': 'no, stop, cancel / ไม่เอา หยุด',
    'status': 'progress or task status / ถามความคืบหน้า',
}

_MODEL = None


def route(text, top=3):
    """Classify one Thai/English command. Loads the bundled model on first call."""
    global _MODEL
    if _MODEL is None:
        _MODEL = IntentModel.load()
    return _MODEL.predict(text, top=top)


from .knowledge import Knowledge  # noqa: E402
from .chat import Chat  # noqa: E402
