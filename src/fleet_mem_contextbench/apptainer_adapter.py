#!/usr/bin/env python3
"""Project-local Docker lifecycle adapter backed by Apptainer overlays.

The pinned SWE-ContextBench runner supplies test selection, test execution,
result parsing, and scoring. This adapter maps its image/container lifecycle
to an immutable SIF and job-local writable ext3 snapshots, failing closed on
an unsupported Docker operation or run flag.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


REAL_RUN = subprocess.run
OVERLAY_SIZE_MIB = 2048


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _completed(argv: list[str], returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(argv, returncode, stdout, stderr)


def _path_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while True:
            block = source.read(8 * 1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


class ApptainerDockerAdapter:
    """Handle the pinned evaluator's Docker operations via immutable SIF + ext3."""

    def __init__(self, project: Path, job_tmp: Path, sif: Path, command_log: Path):
        self.project = project.resolve(strict=True)
        self.job_tmp = job_tmp.resolve(strict=True)
        self.sif = sif.resolve(strict=True)
        self.command_log = command_log
        self.image_overlays: dict[str, Path | None] = {}
        self.containers: dict[str, Path] = {}
        self.protected_overlays: set[Path] = set()
        self.events: list[dict[str, Any]] = []
        self.counter = 0
        self.home = self.job_tmp / "container-home"
        self.home.mkdir(mode=0o700, exist_ok=True)

    def _ensure_job_path(self, path: Path) -> Path:
        resolved = path.resolve(strict=False)
        if resolved != self.job_tmp and self.job_tmp not in resolved.parents:
            raise RuntimeError(f"Writable Apptainer state escaped job-local temporary storage: {resolved}")
        return resolved

    def seed_image(self, tag: str, overlay: Path | None) -> None:
        if overlay is not None:
            overlay = self._ensure_job_path(overlay)
            if not overlay.is_file():
                raise RuntimeError(f"Seed overlay does not exist: {overlay}")
            self.protected_overlays.add(overlay)
        self.image_overlays[tag] = overlay

    def _new_overlay_path(self, prefix: str) -> Path:
        self.counter += 1
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", prefix)[:48] or "overlay"
        return self._ensure_job_path(self.job_tmp / f"{safe}-{self.counter:04d}.ext3")

    def create_overlay(self, prefix: str) -> Path:
        path = self._new_overlay_path(prefix)
        result = REAL_RUN(
            ["apptainer", "overlay", "create", "--fakeroot", "--size", str(OVERLAY_SIZE_MIB), "--sparse", str(path)],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=self.job_tmp,
        )
        self.events.append({
            "operation": "overlay_create",
            "path": str(path),
            "size_mib": OVERLAY_SIZE_MIB,
            "command": result.args,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        })
        if result.returncode != 0:
            raise RuntimeError(f"Apptainer overlay creation failed for {path}: {result.stderr}")
        return path

    def clone_overlay(self, source: Path, prefix: str) -> Path:
        source = self._ensure_job_path(source)
        destination = self._new_overlay_path(prefix)
        result = REAL_RUN(
            ["cp", "--reflink=auto", "--sparse=always", "--", str(source), str(destination)],
            capture_output=True,
            text=True,
            timeout=180,
            cwd=self.job_tmp,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Overlay clone failed: {result.stderr}")
        if source.stat().st_ino == destination.stat().st_ino:
            raise RuntimeError("Overlay clone unexpectedly shares the source inode")
        return destination

    def _container_overlay(self, image: str, name: str) -> Path:
        if name in self.containers:
            old = self.containers.pop(name)
            if not self._is_referenced(old):
                old.unlink(missing_ok=True)
        source = self.image_overlays.get(image)
        if image not in self.image_overlays:
            raise RuntimeError(f"Unknown staged image alias: {image}")
        if source is None:
            overlay = self.create_overlay(f"container-{name}")
        else:
            overlay = self.clone_overlay(source, f"container-{name}")
        self.containers[name] = overlay
        return overlay

    def _is_referenced(self, path: Path) -> bool:
        return path in self.protected_overlays or path in self.image_overlays.values() or path in self.containers.values()

    def _collect_unreferenced(self, path: Path) -> None:
        if not self._is_referenced(path):
            path.unlink(missing_ok=True)

    def _apptainer_args(
        self,
        overlay: Path | None,
        command: list[str],
        bind_specs: list[str],
        env_specs: list[str],
        workdir: str | None,
        transient: bool,
    ) -> list[str]:
        argv = [
            "apptainer", "exec", "--cleanenv", "--containall", "--fakeroot",
            "--home", f"{self.home}:/root",
        ]
        if workdir:
            argv.extend(["--pwd", workdir])
        elif self.sif.exists():
            # OCI config for the staged image records /testbed as its WORKDIR.
            argv.extend(["--pwd", "/testbed"])
        if overlay is not None:
            overlay = self._ensure_job_path(overlay)
            argv.extend(["--overlay", f"{overlay}:ro" if transient else str(overlay)])
        if transient:
            # Docker's --rm discards all writes after each invocation.
            argv.append("--writable-tmpfs")
        for spec in bind_specs:
            argv.extend(["--bind", spec])
        for spec in env_specs:
            key, sep, value = spec.partition("=")
            if not sep:
                if key not in os.environ:
                    continue
                value = os.environ[key]
            argv.extend(["--env", f"{key}={value}"])
        argv.extend([str(self.sif), *command])
        return argv

    @staticmethod
    def _parse_run(args: list[str]) -> tuple[bool, str | None, str, list[str], list[str], str | None, list[str]]:
        transient = False
        name = None
        bind_specs: list[str] = []
        env_specs: list[str] = []
        workdir = None
        # ``run`` has already been removed by ``run()`` before this parser is
        # called, so the first token is a Docker run option or image name.
        index = 0
        while index < len(args):
            token = args[index]
            if token == "--rm":
                transient = True
                index += 1
            elif token in ("-i", "--interactive", "-t", "--tty"):
                index += 1
            elif token == "--name":
                name = args[index + 1]
                index += 2
            elif token in ("-v", "--volume"):
                bind_specs.append(args[index + 1])
                index += 2
            elif token in ("-e", "--env"):
                env_specs.append(args[index + 1])
                index += 2
            elif token in ("-w", "--workdir"):
                workdir = args[index + 1]
                index += 2
            elif token.startswith("-"):
                raise RuntimeError(f"Unsupported Docker run flag in pinned evaluator: {token}")
            else:
                image = token
                command = args[index + 1 :]
                if not command:
                    raise RuntimeError("Pinned evaluator issued docker run without an explicit command")
                return transient, name, image, command, bind_specs, workdir, env_specs
        raise RuntimeError("Pinned evaluator issued docker run without an image")

    def _run_container(self, docker_args: list[str], kwargs: dict[str, Any]) -> subprocess.CompletedProcess:
        transient, name, image, command, binds, workdir, envs = self._parse_run(docker_args)
        if image not in self.image_overlays:
            raise RuntimeError(f"Unknown staged image alias in docker run: {image}")
        if name:
            overlay = self._container_overlay(image, name)
        else:
            overlay = self.image_overlays[image]
        argv = self._apptainer_args(overlay, command, binds, envs, workdir, transient=(transient or not name))
        forwarded = {key: value for key, value in kwargs.items() if key in {"input", "timeout", "text", "encoding", "errors", "cwd", "env"}}
        forwarded["cwd"] = str(self.job_tmp)
        result = REAL_RUN(argv, capture_output=True, **forwarded)
        stdout = _as_text(result.stdout)
        stderr = _as_text(result.stderr)
        self.events.append({
            "operation": "docker_run_via_apptainer",
            "docker_argv": ["docker", *docker_args],
            "apptainer_argv": argv,
            "image_alias": image,
            "overlay": str(overlay) if overlay else None,
            "transient_upper": bool(transient or not name),
            "stdin_bytes": len(kwargs.get("input") or b"") if isinstance(kwargs.get("input"), bytes) else len((kwargs.get("input") or "").encode("utf-8")),
            "returncode": result.returncode,
            "stdout": stdout,
            "stderr": stderr,
        })
        if name and transient:
            path = self.containers.pop(name, None)
            if path is not None:
                self._collect_unreferenced(path)
        return _completed(["docker", *docker_args], result.returncode, stdout, stderr)

    def run(self, command: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        if not isinstance(command, (list, tuple)) or not command or command[0] != "docker":
            return REAL_RUN(command, **kwargs)
        docker_command = list(command)
        args = docker_command[1:]
        if not args:
            return _completed(docker_command, 2, "", "Docker adapter requires a subcommand")
        operation = args[0]
        handler = {
            "images": self._images_command,
            "run": lambda rest: self._run_container(rest, kwargs),
            "commit": self._commit_command,
            "tag": self._tag_command,
            "rm": self._remove_container_command,
            "rmi": self._remove_image_command,
        }.get(operation)
        if handler is None:
            return self._adapter_error(docker_command, f"Unsupported Docker operation: {' '.join(args)}")
        try:
            return handler(args[1:])
        except Exception as error:
            return self._adapter_error(docker_command, str(error))

    def _images_command(self, args: list[str]) -> subprocess.CompletedProcess:
        if len(args) != 2 or args[0] != "-q":
            raise RuntimeError(f"Unsupported Docker images arguments: {args}")
        tag = args[1]
        value = "sha256:apptainer-sif\n" if tag in self.image_overlays else ""
        return _completed(["docker", "images", *args], 0, value, "")

    def _commit_command(self, args: list[str]) -> subprocess.CompletedProcess:
        if len(args) != 2:
            raise RuntimeError(f"Unsupported Docker commit arguments: {args}")
        name, tag = args
        if name not in self.containers:
            raise RuntimeError(f"Unknown named container at commit: {name}")
        snapshot = self.clone_overlay(self.containers[name], f"commit-{tag}")
        previous = self.image_overlays.get(tag)
        self.image_overlays[tag] = snapshot
        if previous is not None:
            self._collect_unreferenced(previous)
        self.events.append({"operation": "docker_commit_as_overlay_snapshot", "container": name, "image_alias": tag, "overlay": str(snapshot), "returncode": 0})
        return _completed(["docker", "commit", *args], 0, f"apptainer-overlay:{snapshot}\n", "")

    def _tag_command(self, args: list[str]) -> subprocess.CompletedProcess:
        if len(args) != 2:
            raise RuntimeError(f"Unsupported Docker tag arguments: {args}")
        source, destination = args
        if source not in self.image_overlays:
            raise RuntimeError(f"Unknown image alias in docker tag: {source}")
        self.image_overlays[destination] = self.image_overlays[source]
        self.events.append({"operation": "docker_tag_alias", "source": source, "destination": destination, "returncode": 0})
        return _completed(["docker", "tag", *args], 0, "", "")

    def _remove_container_command(self, args: list[str]) -> subprocess.CompletedProcess:
        if len(args) != 2 or args[0] != "-f":
            raise RuntimeError(f"Unsupported Docker rm arguments: {args}")
        name = args[1]
        path = self.containers.pop(name, None)
        if path is not None:
            self._collect_unreferenced(path)
        result = _completed(
            ["docker", "rm", *args], 0 if path is not None else 1,
            name + "\n" if path is not None else "",
            "" if path is not None else f"No such container: {name}",
        )
        self.events.append({"operation": "docker_rm_container", "container": name, "returncode": result.returncode})
        return result

    def _remove_image_command(self, args: list[str]) -> subprocess.CompletedProcess:
        if len(args) < 1:
            raise RuntimeError("Docker rmi requires an image alias")
        tag = args[-1]
        existed = tag in self.image_overlays
        overlay = self.image_overlays.pop(tag, None)
        if overlay is not None:
            self._collect_unreferenced(overlay)
        result = _completed(
            ["docker", "rmi", *args], 0 if existed else 1,
            f"Untagged: {tag}\n" if existed else "",
            "" if existed else f"No such image alias: {tag}",
        )
        self.events.append({"operation": "docker_rmi_alias", "image_alias": tag, "returncode": result.returncode})
        return result

    def _adapter_error(self, command: list[str], message: str) -> subprocess.CompletedProcess:
        result = _completed(command, 125, "", f"Apptainer evaluator adapter error: {message}")
        self.events.append({"operation": "adapter_error", "docker_argv": command, "error": message, "returncode": 125})
        return result

    def write_log(self) -> None:
        self.command_log.parent.mkdir(parents=True, exist_ok=True)
        with self.command_log.open("w", encoding="utf-8") as target:
            for event in self.events:
                target.write(json.dumps(event, ensure_ascii=False) + "\n")


def local_filesystem_info(path: Path) -> dict[str, str]:
    result = REAL_RUN(
        ["findmnt", "-n", "-o", "FSTYPE,SOURCE,TARGET", "-T", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    parts = result.stdout.strip().split(None, 2)
    if len(parts) != 3:
        raise RuntimeError(f"Could not identify filesystem for job-local temp path {path}: {result.stdout!r}")
    fstype, source, mountpoint = parts
    if fstype.lower().startswith(("nfs", "lustre", "gpfs", "beegfs", "panfs", "ceph", "cifs", "smb")):
        raise RuntimeError(f"Refusing to create writable overlays on non-local filesystem {fstype} ({source})")
    return {"filesystem_type": fstype, "source": source, "mountpoint": mountpoint}


def sha256_file(path: Path) -> str:
    return _path_hash(path)
