# /// script
# dependencies = [
#     "httpx~=0.27",
# ]
# ///

from asyncio import gather, run
from asyncio.threads import to_thread
from base64 import b64encode
from hashlib import sha256
from pathlib import Path
from re import findall, sub
from shlex import split
from subprocess import Popen
from sys import argv
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from httpx import AsyncClient


def remove_local_version(string: str):  # local versions is not allowed
    return sub(r"(\d+\.\d+\.\d+\.dev\d+)\+\w+", r"\1", string)  # x.y.z.dev[n]+[hash]


def patch_metadata(content: str):
    return remove_local_version(
        content.replace("Name: pythonmonkey", "Name: pythonmonkey-fork", 1).replace(
            "Requires-Dist: pminit (>=0.4.0)",
            "Requires-Dist: pythonmonkey-node-modules (~=0.1)",
        )
    )


def patch_record(content: str):
    lines = []
    for line in content.split("\n"):
        if line.startswith(("pythonmonkey/require.py", "pythonmonkey/__init__.py")):
            path = line[: line.index(",")]
            file_content = Path("python", path).read_bytes()
            lines.append(f"{path},sha256={b64encode(sha256(file_content).digest()).decode('latin1')},{len(file_content)}")
        else:
            lines.append(line)
    return remove_local_version("\n".join(lines).replace("pythonmonkey-", "pythonmonkey_fork-"))


def run_command(command: str, cwd: str):
    code = Popen(split(command), cwd=cwd).wait()
    if code != 0:
        raise RuntimeError(f"Command failed with code {code}: {command}")


def replace_file_inside_wheel(whl_path: Path, path_inside_whl: str, content: str):
    with TemporaryDirectory() as tmpdir:
        tmpfile = Path(tmpdir, path_inside_whl)
        tmpfile.parent.mkdir(parents=True, exist_ok=True)
        tmpfile.write_text(content)
        run_command(f"zip -q -f {str(whl_path.resolve())!r} {path_inside_whl}", tmpdir)


def rename_dist_info_folder(whl_path: Path, files: list[str]):
    with TemporaryDirectory() as tmpdir:
        run_command(
            f"unzip -q {str(whl_path.resolve())!r} '*dist-info/*' -d {tmpdir}",
            tmpdir,
        )
        run_command(
            f"zip -q -d {str(whl_path.resolve())!r} {' '.join(files)}",
            tmpdir,
        )

        dist_info_folder = next(Path(tmpdir).glob("pythonmonkey-*.dist-info"))
        new_dist_info_folder = dist_info_folder.with_name(remove_local_version(dist_info_folder.name.replace("pythonmonkey-", "pythonmonkey_fork-")))
        dist_info_folder.rename(new_dist_info_folder)
        run_command(
            f"zip -q -r -p {str(whl_path.resolve())!r} {new_dist_info_folder.name}",
            tmpdir,
        )


def patch_wheel(whl: Path):
    with ZipFile(whl, "r") as zf:
        for path in zf.namelist():
            if path.endswith("METADATA"):
                metadata_path = path
                metadata = patch_metadata(zf.read(path).decode("utf-8"))
            elif path.endswith("RECORD"):
                record_path = path
                record = patch_record(zf.read(path).decode("utf-8"))
            # TODO: METADATA's sha256 is not updated

        dist_info_files = [path for path in zf.namelist() if "dist-info/" in path]

    replace_file_inside_wheel(whl, metadata_path, metadata)
    replace_file_inside_wheel(whl, record_path, record)
    for name in ("require.py", "__init__.py"):
        replace_file_inside_wheel(
            whl,
            f"pythonmonkey/{name}",
            Path(f"python/pythonmonkey/{name}").read_text(),
        )
    rename_dist_info_folder(whl, dist_info_files)


def patch_pyproject(content: str):
    lines = content.replace('name = "pythonmonkey"', 'name = "pythonmonkey-fork"').splitlines()
    for i, line in enumerate(lines):
        if line.startswith("pminit = "):
            lines[i] = 'pythonmonkey_node_modules = "~0.1"'
    return "\n".join(lines) + "\n"


def patch_sdist(tar: Path):
    with TemporaryDirectory() as tmpdir:
        run_command(f"tar -xzf {str(tar.resolve())!r}", tmpdir)

        root = Path(tmpdir, tar.name.replace(".tar.gz", ""))

        file = root / "pyproject.toml"
        file.write_text(patch_pyproject(file.read_text()))
        file = root / "PKG-INFO"
        file.write_text(patch_metadata(file.read_text()))
        for name in ("require.py", "__init__.py"):
            name = f"python/pythonmonkey/{name}"
            (root / name).write_bytes(Path(name).read_bytes())

        new_path = root.replace(Path(tmpdir, remove_local_version(root.name.replace("pythonmonkey-", "pythonmonkey_fork-"))))

        run_command(f"tar -czf {str(tar.resolve())!r} {new_path.name}", tmpdir)


client = AsyncClient(headers={"accept": "application/vnd.pypi.simple.v1+json"})


async def fetch_pypi(version: str, names: list[str], links: list[str]):
    res = await client.get("https://pypi.org/simple/pythonmonkey/")
    for file_info in res.raise_for_status().json()["files"]:
        if file_info["filename"].startswith(f"pythonmonkey-{version}"):
            names.append(file_info["filename"])
            links.append(file_info["url"])


async def fetch_nightly(names: list[str], links: list[str]):
    res = await client.get("https://nightly.pythonmonkey.io/pythonmonkey/")
    html = res.raise_for_status().text
    for href in findall(r'href="([^"]+)"', html):
        names.append(filename := href.removeprefix("./"))
        links.append(f"https://nightly.pythonmonkey.io/pythonmonkey/{filename}")


async def patch_version(version: str):
    names: list[str] = []
    links: list[str] = []
    if version == "nightly":
        await fetch_nightly(names, links)
    else:
        await fetch_pypi(version, names, links)

    responses = await gather(*map(client.get, links))

    futures = []

    for filename, res in zip(names, responses):
        path = Path("dist", filename)
        path.write_bytes(res.raise_for_status().content)

        @futures.append
        @to_thread
        def _(filename=filename, path=path):
            if filename.endswith(".whl"):
                patch_wheel(path)

            elif filename.endswith(".tar.gz"):
                patch_sdist(path)

            Path("dist", filename).rename(Path("dist", remove_local_version(filename.replace("pythonmonkey", "pythonmonkey_fork"))))
            print(f"Patched {filename}")

    await gather(*futures)


if __name__ == "__main__":
    Path("dist").mkdir(exist_ok=True)
    run(patch_version(argv[-1]))
