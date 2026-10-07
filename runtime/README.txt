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

  然后把解释器软链或复制过来：

    mkdir -p runtime/python/bin
    cp $(which python3) runtime/python/bin/python3

  更省事：直接用系统 Python（/usr/bin/python3），什么都不用放，
  本工具会自动找到它。


【linux】
  同理：runtime/python/bin/python3


放好之后，双击「启动_AgentRelay.bat」或运行：

    python app/bootstrap.py

看到 "✓ Python x.y via 移动硬盘自带 runtime" 就说明生效了。
