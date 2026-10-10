"""Transfer complete SKILL.md directories as data, never run their instructions."""

from .messages import text as message_text, error_text
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
        raise ValueError(message_text('err.missing_agent_name_required'))
    native = key.split("_", 1)[1] if key.startswith(("windows_", "ubuntu_")) else key
    if native not in registry._ADAPTERS:
        raise ValueError(message_text('err.unknown_agent'))
    return native


def skill_name(value):
    archive.safe_name(value)
    if "/" in value or value.startswith("."):
        raise ValueError(message_text('err.skill_name_must_be_a_single_non_hidden_directory_name'))
    return value


def skill_roots(agent, skills_dir=None):
    native = _agent(agent)
    if skills_dir:
        path = Path(skills_dir).expanduser()
        if not path.is_absolute():
            raise ValueError(message_text('err.skill_directory_must_be_an_absolute_path_accessible_from_this_device'))
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
                                   "error":message_text('msg.select_the_real_directory_instead_of_a_symbolic_link') if archive.is_link(directory) else ""})
        except OSError as exc:
            errors.append({"path":str(root), "error":error_text(exc)})
    return {"ok":True, "roots":[str(root) for root in roots], "skills":skills, "errors":errors}


def store_skill(agent, path, root=None):
    native = _agent(agent)
    directory = Path(path).expanduser()
    if not directory.is_absolute() or not directory.is_dir() or archive.is_link(directory):
        raise ValueError(message_text('err.select_an_accessible_real_skill_directory_with_an_absolute_path'))
    directory = directory.resolve()
    name = skill_name(directory.name)
    if not (directory / "SKILL.md").is_file():
        raise ValueError(message_text('err.skill_directory_lacks_skill_md'))
    package = archive.storage_root(root) / "skills" / native / (uuid.uuid4().hex + ".zip")
    if _inside(package, directory):
        raise ValueError(message_text('err.storage_directory_cannot_be_inside_the_skill_being_packaged'))
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
                raise ValueError(message_text('err.skill_contains_a_directory_symbolic_link_and_cannot_be_moved_completely_value', value=str(current)))
        for filename in filenames:
            current = Path(folder) / filename
            relative = current.relative_to(directory).as_posix()
            low = filename.lower()
            if low in SECRET_NAMES or low.startswith(".env") or current.suffix.lower() in (".pem", ".key"):
                excluded.append(relative)
                continue
            if archive.is_link(current):
                raise ValueError(message_text('err.skill_contains_a_file_symbolic_link_and_cannot_be_moved_completely_value', value=str(current)))
            if not _inside(current, directory):
                raise ValueError(message_text('err.skill_file_points_outside_the_directory'))
            data = archive.read_file(current)
            total += len(data)
            if total > archive.MAX_TOTAL or len(files) >= archive.MAX_FILES:
                raise ValueError(message_text('err.skill_exceeds_the_storage_package_size_or_file_count_limit'))
            executable = bool(current.stat().st_mode & stat.S_IXUSR) or data.startswith(b"#!")
            files["skill/" + relative] = (data, executable)
    manifest = {"kind":KIND, "agent":native, "created_at":iso(), "skill":{"name":name},
                "excluded":excluded, "notes":[message_text('msg.skill_content_is_stored_only_as_data_scripts_are_not_executed_and_account_configuration_is')]}
    return archive.write_package(package, manifest, files)


def store_skills(agent, paths=None, all_skills=False, skills_dir=None, root=None):
    paths = list(paths or [])
    if all_skills and paths:
        raise ValueError(message_text('err.all_cannot_be_used_together_with_a_specific_skill_directory'))
    discovered = discover_skills(agent, skills_dir) if all_skills else {"skills":[], "errors":[]}
    if all_skills:
        paths = [row["path"] for row in discovered["skills"]]
    if not paths and not discovered["errors"]:
        raise ValueError(message_text('err.select_a_skill_directory_or_all_no_skills_containing_skill_md_found'))
    results, errors = [], list(discovered["errors"])
    for path in dict.fromkeys(paths):
        try:
            results.append(store_skill(agent, path, root))
        except (OSError, ValueError, KeyError) as exc:
            errors.append({"path":path, "error":error_text(exc)})
    return {"ok":not errors, "stored":results, "errors":errors}


def restore_skill(package, agent=None, skills_dir=None, name=None):
    manifest, files = archive.read_package(package, KIND)
    _agent(manifest.get("agent"))
    selected = agent or manifest.get("agent")
    native = _agent(selected)
    skill = manifest.get("skill")
    if not isinstance(skill, dict):
        raise ValueError(message_text('err.invalid_skill_package_metadata'))
    name = skill_name(name or skill.get("name"))
    if "skill/SKILL.md" not in files or any(not path.startswith("skill/") for path in files):
        raise ValueError(message_text('err.skill_package_lacks_skill_md_or_contains_non_skill_entries'))
    # Codex installs to .agents/skills by default; users can explicitly select
    # legacy/plugin/project locations. Other defaults are conventional candidates.
    root = skill_roots(selected, skills_dir)[0]
    destination = root / name
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(message_text('err.target_skill_already_exists_and_will_not_be_overwritten_choose_another_name'))
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
            "notes":[message_text('msg.skill_files_verified_and_copied_no_instructions_or_scripts_were_executed'),
                     message_text('msg.check_discovery_and_compatibility_in_the_target_agent_script_dependencies_and_absolute_pat')]}
