import os
import sys

# allow `pytest` from a source checkout without installing
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
