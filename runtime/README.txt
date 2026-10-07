runtime/ —— 可选的自带 Python（放了它才算真正免安装）

这个目录是留给 Python 便携版的。留空也能用：程序会自动去找目标机器上
已经装好的 Python。只有当你要在一台没装 Python 的电脑上使用时，才需要放。


【Windows】
  1. 到 python.org 下载 "Windows embeddable package (64-bit)"
     https://www.python.org/downloads/windows/
  2. 解压，把解压出来的全部文件放进： runtime\python\
  3. 确认存在这个文件：
       runtime\python\python.exe
  4. 回到根目录双击「启动_AgentRelay.bat」

  注意：嵌入式版本默认不含 pip，本工具不需要 pip，所以无所谓。


【macOS】
  bash Mac安装依赖.command 会自动创建 runtime/macos-<架构>/，
  并安装读取 DSH 压缩日志所需的 zstandard；Mac 启动器优先使用它。
  这是依赖本机 Python 的虚拟环境，换机器后请重新运行首次准备。

  免安装的最好办法不是拷贝 Python（动态库路径会失效），而是：

    brew install python

  安装后直接启动即可，本工具会自动查找 Homebrew 的 Python。
  不要只复制 python3 可执行文件：它依赖原安装位置的动态库和标准库，
  单独复制不能组成可移植运行时。若使用系统 Python，需确认版本至少为 3.8。


【Ubuntu / Linux】
  推荐在项目目录运行： bash Ubuntu首次准备.sh
  缺少 venv 时先执行： sudo apt install python3 python3-venv
  依赖装在用户级 ~/.local/share/agent-relay/venv，不修改系统 Python。
  RELAY_VENV 可自定义位置；准备与启动时应设置相同值。
  启动： bash 启动_AgentRelay.sh

  Linux 启动器顺序：RELAY_PYTHON（若设置只使用它）→ 用户虚拟环境
  → runtime/linux/bin/python3 → runtime/python/bin/python3 或 python → PATH。
  runtime/linux 可与 Windows 的 runtime/python/python.exe 并存。
  便携 Linux runtime 需要完整标准库和动态库，并匹配 Ubuntu 的 CPU / glibc；
  不要仅复制 python3 文件，Windows python.exe 不能当 Linux Python 使用。
  若项目盘 noexec，用 bash 启动脚本；Python/venv 本身需在允许执行的 Linux 文件系统上。
  双系统读取 Windows 会话见 docs/ubuntu-dual-boot.md。


放好之后，双击「启动_AgentRelay.bat」或运行：

    python app/bootstrap.py

看到 "✓ Python x.y via 移动硬盘自带 runtime" 就说明生效了。
