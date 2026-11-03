import os
import sys
from pathlib import Path

os.environ['NMS_BUBBLE_LOW_RES'] = '1'
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_native_bubble_preview import *
