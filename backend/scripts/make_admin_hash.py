"""生成管理员密码哈希（bcrypt）：python scripts/make_admin_hash.py <密码>

输出填入环境变量 ADMIN_PASSWORD_HASH；密码本身不写入任何文件。
"""
import getpass
import sys

import bcrypt


def main() -> None:
    password = sys.argv[1] if len(sys.argv) > 1 else getpass.getpass("管理员密码：")
    print(bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode())


if __name__ == "__main__":
    main()
