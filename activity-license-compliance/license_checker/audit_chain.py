"""兼容 v0.4 导入路径；新代码见 pipeline、reporting、audit_cli。"""
from .pipeline import run
from .reporting import write_outputs
from .audit_cli import main

if __name__ == "__main__":
    main()
