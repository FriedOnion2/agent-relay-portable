"""Transfer complete SKILL.md directories as data, never run their instructions."""
import os
import shutil
import stat
import tempfile
import uuid
from pathlib import Path

from . import archive, registry
from .paths import iso
from .native_import import _exclusive_lock, _inside

KIND = "agentrelay-skill"
SKIP_DIRS = {".git", ".ssh", ".aws", "node_modules", "__pycache__", ".venv", "venv"}
SECRET_NAMES = {"auth.json", "credentials.json", "credentials", "id_rsa", "id_ed25519", "id_ecdsa", "id_dsa"}


def _agent(key):
    if not isinstance(key, str) or not key:
        raise ValueError("缺少 Agent 名称")
    native = key.split("_", 1)[1] if key.startswith(("windows_", "ubuntu_")) else key
    if native not in registry._ADAPTERS:
        raise ValueError("未知 Agent")
    return native


def skill_name(value):
    archive.safe_name(value)
    if "/" in value or value.startswith("."):
        raise ValueError("Skill 名称需为非隐藏的单个目录名")
    return value


def skill_roots(agent, skills_dir=None):
    native = _agent(agent)
    if skills_dir:
        path = Path(skills_dir).expanduser()
        if not path.is_absolute():
            raise ValueError("Skill 目录需要当前设备可访问的绝对路径")
        return [path.resolve()]
    source = registry.get(agent)
    adapter = getattr(source, "adapter", source)
    roots = [Path(adapter.root) / "skills"]
    if native == "codex":
        profile = Path(source.profile) if hasattr(source, "profile") else Path.home()
        roots.insert(0, profile / ".agents" / "skills")
    return list(dict.fromkeys(path.resolve() for path in roots))


def discover_skills(agent, skills_dir=None):
    roots = skill_roots(agent, skills_dir)
    skills, errors = [], []
    for root in roots:
        try:
            if not root.exists():
                continue
            for directory in sorted(root.iterdir(), key=lambda p:p.name.casefold()):
                if directory.name.startswith("."):
                    continue
                if directory.is_dir() and (directory / "SKILL.md").is_file():
                    skills.append({"name":directory.name, "path":str(directory), "agent":_agent(agent),
                                   "readable":not archive.is_link(directory),
                                   "error":"符号链接需要选择实际目录" if archive.is_link(directory) else ""})
        except OSError as exc:
            errors.append({"path":str(root), "error":str(exc)})
    return {"ok":True, "roots":[str(root) for root in roots], "skills":skills, "errors":errors}


def store_skill(agent, path, root=None):
    native = _agent(agent)
    directory = Path(path).expanduser()
    if not directory.is_absolute() or not directory.is_dir() or archive.is_link(directory):
        raise ValueError("请选择可访问的实际 Skill 目录绝对路径")
    directory = directory.resolve()
    name = skill_name(directory.name)
    if not (directory / "SKILL.md").is_file():
        raise ValueError("Skill 目录缺少 SKILL.md")
    package = archive.storage_root(root) / "skills" / native / (uuid.uuid4().hex + ".zip")
    if _inside(package, directory):
        raise ValueError("存储目录不能位于待打包的 Skill 内")
    files, excluded = {}, []
    total = 0
    def walk_error(error):
        raise error
    for folder, dirs, filenames in os.walk(directory, followlinks=False, onerror=walk_error):
        for child in list(dirs):
            current = Path(folder) / child
            if child in SKIP_DIRS:
                excluded.append(current.relative_to(directory).as_posix() + "/")
                dirs.remove(child)
            elif archive.is_link(current) or not _inside(current, directory):
                raise ValueError("Skill 内含目录符号链接，不能完整搬迁：" + str(current))
        for filename in filenames:
            current = Path(folder) / filename
            relative = current.relative_to(directory).as_posix()
            low = filename.lower()
            if low in SECRET_NAMES or low.startswith(".env") or current.suffix.lower() in (".pem", ".key"):
                excluded.append(relative)
                continue
            if archive.is_link(current):
                raise ValueError("Skill 内含文件符号链接，不能完整搬迁：" + str(current))
            if not _inside(current, directory):
                raise ValueError("Skill 文件指向目录外部")
            data = archive.read_file(current)
            total += len(data)
            if total > archive.MAX_TOTAL or len(files) >= archive.MAX_FILES:
                raise ValueError("Skill 超过存储包总大小或文件数限制")
            executable = bool(current.stat().st_mode & stat.S_IXUSR) or data.startswith(b"#!")
            files["skill/" + relative] = (data, executable)
    manifest = {"kind":KIND, "agent":native, "created_at":iso(), "skill":{"name":name},
                "excluded":excluded, "notes":["Skill 内容仅保存为数据；不执行脚本，不复制账号配置。"]}
    return archive.write_package(package, manifest, files)


def store_skills(agent, paths=None, all_skills=False, skills_dir=None, root=None):
    paths = list(paths or [])
    if all_skills and paths:
        raise ValueError("--all 与指定 Skill 目录不能同时使用")
    discovered = discover_skills(agent, skills_dir) if all_skills else {"skills":[], "errors":[]}
    if all_skills:
        paths = [row["path"] for row in discovered["skills"]]
    if not paths and not discovered["errors"]:
        raise ValueError("请选择 Skill 目录或 --all；未发现包含 SKILL.md 的技能")
    results, errors = [], list(discovered["errors"])
    for path in dict.fromkeys(paths):
        try:
            results.append(store_skill(agent, path, root))
        except (OSError, ValueError, KeyError) as exc:
            errors.append({"path":path, "error":str(exc)})
    return {"ok":not errors, "stored":results, "errors":errors}


def restore_skill(package, agent=None, skills_dir=None, name=None):
    manifest, files = archive.read_package(package, KIND)
    _agent(manifest.get("agent"))
    selected = agent or manifest.get("agent")
    native = _agent(selected)
    skill = manifest.get("skill")
    if not isinstance(skill, dict):
        raise ValueError("Skill 包元数据无效")
    name = skill_name(name or skill.get("name"))
    if "skill/SKILL.md" not in files or any(not path.startswith("skill/") for path in files):
        raise ValueError("Skill 包缺少 SKILL.md 或包含非 Skill 条目")
    # Codex installs to .agents/skills by default; users can explicitly select
    # legacy/plugin/project locations. Other defaults are conventional candidates.
    root = skill_roots(selected, skills_dir)[0]
    destination = root / name
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("目标 Skill 已存在，不覆盖；可指定另一个 --name")
    root.mkdir(parents=True, exist_ok=True)
    stage = None
    published = False
    with _exclusive_lock(root / (".relay-" + name + ".publish-lock")):
        try:
            stage = Path(tempfile.mkdtemp(prefix=".relay-", suffix=".partial", dir=str(root)))
            archive.unpack(files, stage)
            destination.mkdir()  # exclusive ownership, also refuses empty dirs
            published = True
            for child in (stage / "skill").iterdir():
                os.rename(str(child), str(destination / child.name))
        except BaseException:
            if published:
                shutil.rmtree(destination)
            raise
        finally:
            if stage is not None:
                shutil.rmtree(stage)
    return {"ok":True, "agent":native, "name":name, "path":str(destination),
            "excluded":manifest.get("excluded", []),
            "notes":["已校验并复制 Skill 文件；未执行其中的指令或脚本。",
                     "请在目标 Agent 中检查发现与兼容性；脚本依赖、绝对路径不会自动适配。"]}
