"""Build and smoke-test portable Windows artifacts from a clean source commit.

Run with Windows x64 Python 3.12.10: ``python tools/build_windows.py``.
The outer process creates a fresh, disposable venv and installs only the locked
build wheels. The inner process verifies those versions before building.
Official method: https://pyinstaller.org/en/v6.22.3/operating-mode.html
Resources: https://pyinstaller.org/en/v6.22.3/runtime-information.html
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import venv
import zipfile


PROJECT = Path(__file__).resolve().parents[1]
REPOSITORY = PROJECT.parent
LOCK = PROJECT / "requirements-build-windows.txt"
BUILD_PYTHON = (3, 12, 10)
# Source tests may leave editable-install egg-info next to the app. Keep the
# source import temporary so the isolated venv guard sees only installed wheels.
_original_sys_path = sys.path[:]
try:
    sys.path.insert(0, str(PROJECT))
    from netaudit import __version__
    from netaudit.branding import APPLICATION_NAME, FILE_STEM
finally:
    sys.path[:] = _original_sys_path
del _original_sys_path


def run(command: list[str], *, capture: bool = False, cwd: Path = PROJECT) -> str:
    print("+ " + subprocess.list2cmdline(command), flush=True)
    completed = subprocess.run(
        command, cwd=cwd, check=True, text=True, encoding="utf-8",
        stdout=subprocess.PIPE if capture else None,
    )
    return completed.stdout.strip() if capture else ""


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def locked_versions() -> dict[str, str]:
    pins = {}
    for line in LOCK.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if not re.fullmatch(r"[A-Za-z0-9_-]+==[A-Za-z0-9_.]+", line):
            raise ValueError("Every build dependency must have one exact version: " + line)
        name, version = line.split("==")
        pins[name] = version
    return pins


def source_identity() -> dict[str, object]:
    # Dirty files would make the packaged executable differ from its source ZIP.
    status = run(["git", "status", "--porcelain", "--untracked-files=all"], capture=True, cwd=REPOSITORY)
    if status:
        raise ValueError("Commit or remove local changes before packaging; source must match git HEAD:\n" + status)
    commit = run(["git", "rev-parse", "HEAD"], capture=True, cwd=REPOSITORY)
    timestamp = run(["git", "show", "-s", "--format=%cI", "HEAD"], capture=True, cwd=REPOSITORY)
    return {"commit": commit, "commit_time": timestamp, "dirty": False}


def ensure_build_environment() -> dict[str, str]:
    pins = locked_versions()
    installed = {dist.metadata["Name"].lower().replace("_", "-"): dist.version for dist in metadata.distributions()}
    expected = {name.lower().replace("_", "-"): version for name, version in pins.items()}
    if installed != expected:
        raise ValueError("The build venv does not exactly match the locked dependencies:\n" + json.dumps(installed, indent=2))
    run([sys.executable, "-m", "pip", "check"])
    return pins


def add_user_files(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("Start-NetConfig-Auditor.bat", "Start-NetAudit.bat", "README.md", "LICENSE", "NOTICE"):
        shutil.copy2(PROJECT / name, destination / name)
    instructions = PROJECT / "docs" / "WINDOWS.md"
    shutil.copy2(instructions, destination / "WINDOWS.md")
    shutil.copy2(instructions, destination / "使用说明.txt")
    shutil.copytree(PROJECT / "docs", destination / "docs", dirs_exist_ok=True)
    shutil.copytree(PROJECT / "examples", destination / "examples", dirs_exist_ok=True)
    # Keep public intelligence provenance/licensing readable without running
    # the executable. The executable also embeds the complete data directory.
    intelligence = PROJECT / "netaudit" / "data"
    if intelligence.is_dir():
        shutil.copytree(intelligence, destination / "intelligence-data", dirs_exist_ok=True)


def collect_licenses(destination: Path, pins: dict[str, str]) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name in pins:
        distribution = metadata.distribution(name)
        copied = 0
        for entry in distribution.files or ():
            relative = Path(str(entry))
            if ".." in relative.parts:
                continue
            if not re.match(r"^(LICENSE|LICENCE|COPYING|COPYRIGHT|NOTICE)([._-].*)?$", relative.name, re.IGNORECASE):
                continue
            origin = Path(distribution.locate_file(entry))
            if not origin.is_file():
                continue
            target = destination / name / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origin, target)
            copied += 1
        if not copied:
            raise ValueError("No license file found in the installed build wheel: " + name)
    for candidate in (Path(sys.base_prefix) / "LICENSE.txt", Path(sys.base_prefix) / "LICENSE"):
        if candidate.is_file():
            shutil.copy2(candidate, destination / "Python-LICENSE.txt")
            break
    else:
        raise ValueError("The Windows Python installation must provide its LICENSE.txt for redistribution")
    write_json(destination / "VERSIONS.json", {"python": platform.python_version(), "build_packages": pins})
    (destination / "README.txt").write_text(
        "NetConfig Auditor has no third-party runtime Python package dependencies.\n"
        "The frozen executable contains Python and PyInstaller bootloader/runtime components.\n"
        "Python and all locked build dependency licenses are retained here; listing a build\n"
        "dependency does not imply that the whole package is embedded in the executable.\n"
        "Project license and source attribution remain in the adjacent LICENSE and NOTICE.\n",
        encoding="utf-8",
    )


def smoke(mode: str, target: Path, report: Path) -> dict[str, object]:
    report.parent.mkdir(parents=True, exist_ok=True)
    run([sys.executable, str(PROJECT / "tools" / "smoke_portable.py"), "--" + mode, str(target), "--report", str(report)])
    if not report.is_file():
        raise ValueError("Smoke command succeeded without writing its verification report: " + str(report))
    result = json.loads(report.read_text(encoding="utf-8"))
    if result.get("passed") is not True:
        raise ValueError("The acceptance report does not record a successful verification: " + str(report))
    return result


def write_version_resource(work: Path) -> Path:
    """Set the Windows Properties product identity alongside the file name."""
    version = __version__
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Windows version resource requires a three-part version")
    parts = tuple(map(int, version.split("."))) + (0,)
    strings = {"FileDescription": APPLICATION_NAME, "ProductName": APPLICATION_NAME,
               "FileVersion": version, "ProductVersion": version,
               "OriginalFilename": FILE_STEM + ".exe", "InternalName": FILE_STEM}
    fields = ",\n".join(f"                StringStruct({key!r}, {value!r})" for key, value in strings.items())
    text = f"""# UTF-8 Windows PE VERSIONINFO generated from the project identity.
VSVersionInfo(
    ffi=FixedFileInfo(filevers={parts!r}, prodvers={parts!r}, mask=0x3f,
                      flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
    kids=[StringFileInfo([StringTable('040904B0', [
{fields}
    ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)
"""
    path = work / "windows-version.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def build_executable(mode: str, work: Path) -> Path:
    output = work / ("dist-" + mode)
    version_resource = write_version_resource(work)
    command = [
        sys.executable, "-m", "PyInstaller", "--" + mode,
        "--clean", "--noconfirm", "--console", "--noupx", "--name", FILE_STEM,
        "--version-file", str(version_resource),
        "--paths", str(PROJECT), "--workpath", str(work / ("analysis-" + mode)),
        "--specpath", str(work / ("spec-" + mode)), "--distpath", str(output),
        "--add-data", str(PROJECT / "netaudit" / "web") + ":netaudit/web",
        "--add-data", str(PROJECT / "netaudit" / "data") + ":netaudit/data",
        str(PROJECT / "tools" / "windows_entry.py"),
    ]
    run(command)
    executable = output / (FILE_STEM + "/" + FILE_STEM + ".exe" if mode == "onedir" else FILE_STEM + ".exe")
    if not executable.is_file():
        raise ValueError("Expected Windows executable was not generated: " + str(executable))
    with executable.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise ValueError("Generated file is not a Windows PE executable")
    add_user_files(executable.parent)
    return executable


def file_checksums(directory: Path) -> None:
    rows = []
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.name != "FILES.sha256":
            rows.append(sha256(path) + "  " + path.relative_to(directory).as_posix())
    (directory / "FILES.sha256").write_text("\n".join(rows) + "\n", encoding="utf-8")


def zip_directory(directory: Path, archive: Path) -> None:
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as output:
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                output.write(path, (Path(directory.name) / path.relative_to(directory)).as_posix())
    with zipfile.ZipFile(archive) as bundle:
        damaged = bundle.testzip()
        if damaged:
            raise ValueError("ZIP validation failed for " + damaged)


def package(
    mode: str, executable: Path, output: Path, work: Path, stem: str,
    source_zip: Path, build_manifest: dict[str, object], licenses: Path,
) -> Path:
    folder = work / "packages" / (FILE_STEM if mode == "onedir" else FILE_STEM + "-onefile")
    shutil.copytree(executable.parent, folder)
    shutil.copy2(source_zip, folder / source_zip.name)
    shutil.copytree(licenses, folder / "third-party-licenses")
    shutil.copy2(LOCK, folder / LOCK.name)
    (folder / "build-requirements-freeze.txt").write_text(str(build_manifest["pip_freeze"]) + "\n", encoding="utf-8")
    write_json(folder / "BUILD-MANIFEST.json", {
        **build_manifest, "package_mode": mode,
        "executable_sha256": sha256(folder / (FILE_STEM + ".exe")),
        "source_archive": {"file": source_zip.name, "sha256": sha256(source_zip)},
    })
    reports = folder / "verification"
    reports.mkdir()
    for report in (work / "verification").glob("*.json"):
        shutil.copy2(report, reports / report.name)
    file_checksums(folder)
    archive = output / (stem + ("-portable.zip" if mode == "onedir" else "-onefile.zip"))
    zip_directory(folder, archive)
    return archive


def build(output: Path, work: Path, identity: dict[str, object]) -> None:
    pins = ensure_build_environment()
    expected_web = {"index.html", "style.css", "app.js", "simulator.js",
                    "vendor-syntax.js", "vendor-highlight.js"}
    actual_web = {path.name for path in (PROJECT / "netaudit" / "web").iterdir() if path.is_file()}
    if actual_web != expected_web:
        raise ValueError("Build requires the complete six-file web application")
    # Only this task's generated build directories are removed, never source.
    if work.exists():
        shutil.rmtree(work)
    if output.exists():
        shutil.rmtree(output)
    work.mkdir(parents=True)
    output.mkdir(parents=True)
    source_commit = str(identity["commit"])
    version = run([
        sys.executable, "-c",
        "import pathlib,tomllib; print(tomllib.loads(pathlib.Path('pyproject.toml').read_text(encoding='utf-8'))['project']['version'])",
    ], capture=True)
    if version != __version__:
        raise ValueError("Project metadata version differs from the runtime application version")
    stem = FILE_STEM + "-" + version + "-windows-x64-" + source_commit[:12]
    source_zip = output / (FILE_STEM + "-" + version + "-source-" + source_commit[:12] + ".zip")
    run([
        "git", "archive", "--format=zip", "--prefix=" + FILE_STEM + "-source-" + source_commit[:12] + "/",
        "--output=" + str(source_zip), source_commit,
    ], cwd=REPOSITORY)
    # The same committed source ZIP is bundled inside both distributions.
    reports = work / "verification"
    source_report = smoke("source", PROJECT, reports / "source.json")
    onedir_exe = build_executable("onedir", work)
    onedir_report = smoke("onedir", onedir_exe, reports / "onedir.json")
    # Never create or publish the single-file version until onedir has passed.
    onefile_exe = build_executable("onefile", work)
    onefile_report = smoke("onefile", onefile_exe, reports / "onefile.json")
    licenses = work / "third-party-licenses"
    collect_licenses(licenses, pins)
    freeze = run([sys.executable, "-m", "pip", "freeze", "--all"], capture=True)
    manifest = {
        "schema_version": 1,
        "application": APPLICATION_NAME, "application_version": version,
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": identity,
        "environment": {
            "os": platform.platform(), "architecture": platform.machine(),
            "python": platform.python_version(), "python_bits": struct.calcsize("P") * 8,
            "runner_os": os.environ.get("RUNNER_OS"),
            "runner_image": os.environ.get("ImageOS"), "runner_image_version": os.environ.get("ImageVersion"),
            "github_run_id": os.environ.get("GITHUB_RUN_ID"),
            "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        },
        "build_dependencies": pins, "build_lock_sha256": sha256(LOCK), "pip_freeze": freeze,
        "intelligence_data": [
            {"file": path.relative_to(PROJECT).as_posix(),
             "size_bytes": path.stat().st_size, "sha256": sha256(path)}
            for path in sorted((PROJECT / "netaudit" / "data").rglob("*"))
            if path.is_file()
        ],
        "web_resources": [
            {"file": path.relative_to(PROJECT).as_posix(),
             "size_bytes": path.stat().st_size, "sha256": sha256(path)}
            for path in sorted((PROJECT / "netaudit" / "web").iterdir())
            if path.is_file()
        ],
        "build_method": {
            "tool": "PyInstaller", "modes_in_order": ["onedir", "onefile"],
            "console": True, "upx": False, "runtime_tmpdir": "system default",
            "data_destination": "netaudit/web",
            "data_destinations": ["netaudit/web", "netaudit/data"],
            "official_docs": [
                "https://pyinstaller.org/en/v6.22.3/operating-mode.html",
                "https://pyinstaller.org/en/v6.22.3/runtime-information.html",
            ],
        },
        "verification": {"source": source_report, "onedir": onedir_report, "onefile": onefile_report},
        "limitations": [
            "Automated Windows runner verification; human Explorer double-click and visual browser rendering need a desktop check.",
            "Windows x64 only. Other Windows versions and CPU architectures are not claimed as tested.",
            "Closing a browser tab does not stop the local server; use Ctrl+C or close its console window.",
            "Offline configuration-state learning only; no packet forwarding, protocol convergence, real device commands or live business impact are simulated.",
        ],
    }
    portable_zip = package("onedir", onedir_exe, output, work, stem, source_zip, manifest, licenses)
    onefile_zip = package("onefile", onefile_exe, output, work, stem, source_zip, manifest, licenses)
    standalone_exe = output / (stem + "-onefile.exe")
    shutil.copy2(onefile_exe, standalone_exe)
    downloads = [portable_zip, onefile_zip, standalone_exe, source_zip]
    manifest["artifacts"] = [
        {"file": path.name, "size_bytes": path.stat().st_size, "sha256": sha256(path)}
        for path in downloads
    ]
    write_json(output / "manifest.json", manifest)
    for report in reports.glob("*.json"):
        shutil.copy2(report, output / ("smoke-" + report.name))
    checksum_paths = sorted(path for path in output.iterdir() if path.is_file())
    checksum_text = "\n".join(sha256(path) + "  " + path.name for path in checksum_paths) + "\n"
    (output / "SHA256SUMS.txt").write_text(checksum_text, encoding="utf-8")
    print("\nVerified Windows build: " + json.dumps({"source": identity, "environment": manifest["environment"]}, ensure_ascii=False), flush=True)
    print("Verification reports: smoke-source.json, smoke-onedir.json, smoke-onefile.json", flush=True)
    print("Downloadable files:\n" + "\n".join(path.name for path in downloads), flush=True)
    print("SHA256SUMS.txt:\n" + checksum_text, flush=True)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as stream:
            stream.write("### Verified NetConfig Auditor Windows x64 build\n\nSource: `" + source_commit + "`\n\n")
            stream.write("Python: `" + platform.python_version() + "`; OS: `" + platform.platform() + "`\n\n")
            stream.write("Source, onedir and onefile process smoke checks passed. See the artifact verification JSON for scope and skipped desktop checks.\n\n")
            stream.write("```text\n" + checksum_text + "```\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=PROJECT / "dist" / "windows")
    parser.add_argument("--work-dir", type=Path, default=PROJECT / "build" / "windows")
    parser.add_argument("--_in-build-venv", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Windows EXE must be built on Windows; use the NetConfig Auditor Windows portable GitHub Actions workflow")
    if sys.version_info[:3] != BUILD_PYTHON or struct.calcsize("P") != 8:
        parser.error("Use Windows x64 Python 3.12.10 to reproduce the recorded build environment")
    output, work = args.output.resolve(), args.work_dir.resolve()
    # Keep destructive cleanup confined to ignored generated trees.
    if not output.is_relative_to(PROJECT / "dist") or not work.is_relative_to(PROJECT / "build"):
        parser.error("Output must be under project/dist and work directory under project/build")
    if output == PROJECT / "dist" or work == PROJECT / "build":
        parser.error("Select dedicated subdirectories beneath dist and build")
    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    os.environ["PYTHONNOUSERSITE"] = "1"
    for variable in ("PYTHONPATH", "PYTHONHOME"):
        os.environ.pop(variable, None)
    identity = source_identity()
    if args._in_build_venv:
        if sys.prefix == sys.base_prefix:
            parser.error("The internal build command requires its isolated venv")
        build(output, work, identity)
        return 0
    with tempfile.TemporaryDirectory(prefix="netaudit-build-venv-") as temporary:
        environment = Path(temporary) / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        interpreter = environment / "Scripts" / "python.exe"
        run([
            str(interpreter), "-m", "pip", "install", "--disable-pip-version-check", "--no-deps",
            "--only-binary=:all:", "-r", str(LOCK),
        ])
        run([
            str(interpreter), str(Path(__file__).resolve()), "--_in-build-venv",
            "--output", str(output), "--work-dir", str(work),
        ])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print("Windows build failed: " + str(error), file=sys.stderr, flush=True)
        raise SystemExit(1)
