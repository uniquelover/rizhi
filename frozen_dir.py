import sys
import os

def get_app_path():
    """Returns the base application path."""
    if hasattr(sys, 'frozen'):
        exe_dir = os.path.dirname(sys.executable)  # 使用pyinstaller打包后的exe目录
        base_dir = os.path.join(exe_dir, '_internal')
    else:
        base_dir = os.path.abspath(os.path.dirname(__file__))
    return base_dir


app_path = get_app_path()
