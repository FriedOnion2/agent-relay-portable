"""MkDocs 钩子：把指向 docs/ 之外文件的相对链接改写成 GitHub 上的地址。

源码里这些链接（如 ../../README.md）在 GitHub 与本地编辑器里都能点开，
但站点只包含 docs/ 目录，所以构建时改写成仓库页面的链接。
"""

import posixpath
import re

REPO_BLOB = 'https://github.com/FriedOnion2/agent-relay-portable/blob/main/'
LINK = re.compile(r'(\]\()((?:\.\./)+[^)\s#]*)((?:#[^)\s]*)?\))')


def on_page_markdown(markdown, page, **_):
    here = posixpath.dirname(page.file.src_uri)

    def rewrite(match):
        target = posixpath.normpath(posixpath.join('docs', here, match.group(2)))
        if target.startswith('docs/'):
            return match.group(0)            # 仍在 docs/ 内，交给 MkDocs 处理
        return match.group(1) + REPO_BLOB + target + match.group(3)

    return LINK.sub(rewrite, markdown)
