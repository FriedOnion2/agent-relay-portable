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
  免安装的最好办法不是拷贝 Python（动态库路径会失效），而是：

    brew install python

  安装后直接启动即可，本工具会自动查找 Homebrew 的 Python。
  不要只复制 python3 可执行文件：它依赖原安装位置的动态库和标准库，
  单独复制不能组成可移植运行时。若使用系统 Python，需确认版本至少为 3.8。


【linux】
  同理：runtime/python/bin/python3


放好之后，双击「启动_AgentRelay.bat」或运行：

    python app/bootstrap.py

看到 "✓ Python x.y via 移动硬盘自带 runtime" 就说明生效了。
