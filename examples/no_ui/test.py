# -*- coding: utf-8 -*-

import os
from pathlib import Path

dir_path = "C:\Users\swhysc\.vntrader\strategies"
dir_path = dir_path.replace("\\", "\\\\")
abs_path = Path(dir_path).joinPath("poskai.csv")

print(os.path.exists(abs_path))
