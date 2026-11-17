"""兼容既有 python -m license_checker.chain 命令（仅当前审计流程）。"""
from .audit_cli import main

if __name__ == "__main__":
    main()
