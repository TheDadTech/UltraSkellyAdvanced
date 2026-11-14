#!/usr/bin/env python3
"""Repack verified 0.30.0 with a frozen experimental overlay; never access devices.

This does not install packages or run ARM code. It preserves the original
firmware/kernel and applies the network/console overlay to disposable file copies.
"""
import argparse
import base64
import csv
import hashlib
import io
import json
import lzma
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import time

BASE_SHA256 = "a32fafb3d10a3f994ec5e37e6a8ddd805aa4306d428cdba55dbed880c715f21a"
VERSION = "0.30.1-beta1"


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""): h.update(chunk)
    return h.hexdigest()


def run(args, **kwargs):
    p = subprocess.run(args, text=True, capture_output=True, **kwargs)
    if p.returncode:
        raise RuntimeError(f"{args[0]} failed ({p.returncode}): {p.stderr[-2000:]}")
    return p


class RootImage:
    def __init__(self, image, work):
        self.image, self.work, self.changes = image, work, {}
        self.payloads = work / "payloads"
        self.payloads.mkdir(mode=0o700)

    def command(self, command, write=False):
        args = ["debugfs"] + (["-w"] if write else []) + ["-R", command, str(self.image)]
        return run(args)

    def exists(self, path):
        return "Inode:" in self.command(f"stat {path}").stdout

    def read(self, path):
        p = self.command(f"cat {path}")
        if "not found" in p.stderr.lower(): raise FileNotFoundError(path)
        return p.stdout

    def mkdir(self, path):
        for p in reversed(Path(path).parents):
            if str(p) != "/" and not self.exists(str(p)):
                self.command(f"mkdir {p}", True)
        if not self.exists(path): self.command(f"mkdir {path}", True)

    def remove(self, path):
        if self.exists(path): self.command(f"rm {path}", True)

    def write(self, path, data, mode=None):
        assert path.startswith("/") and "\n" not in path and " " not in path
        stat = self.command(f"stat {path}").stdout
        old_mode = re.search(r"Mode:\s+([0-7]+)", stat)
        old_gid = re.search(r"Group:\s+(\d+)", stat)
        old_uid = re.search(r"User:\s+(\d+)", stat)
        content = data.encode() if isinstance(data, str) else data
        temporary = self.payloads / hashlib.sha256(path.encode()).hexdigest()
        temporary.write_bytes(content)
        temporary.chmod(0o600)
        self.mkdir(str(Path(path).parent))
        self.remove(path)
        result = self.command(f'write "{temporary}" {path}', True)
        if "Allocated inode" not in result.stdout: raise RuntimeError(result.stdout + result.stderr)
        permissions = mode if mode is not None else int(old_mode.group(1), 8) if old_mode else 0o644
        self.command(f"set_inode_field {path} mode 0{0o100000 | permissions:o}", True)
        if old_gid: self.command(f"set_inode_field {path} gid {old_gid.group(1)}", True)
        if old_uid: self.command(f"set_inode_field {path} uid {old_uid.group(1)}", True)
        check = self.work / "verify-payload"
        check.unlink(missing_ok=True)
        self.command(f'dump {path} "{check}"')
        if check.read_bytes() != content: raise RuntimeError(f"Image write verification failed: {path}")
        check.unlink()
        self.changes[path] = {"sha256": hashlib.sha256(content).hexdigest(), "mode": oct(permissions)}

    def symlink(self, path, target):
        self.mkdir(str(Path(path).parent))
        self.remove(path)
        self.command(f"symlink {path} {target}", True)
        if f'Fast link dest: "{target}"' not in self.command(f"stat {path}").stdout:
            raise RuntimeError(f"Symlink verification failed: {path}")
        self.changes[path] = {"symlink": target}


def replace_fat_file(image, filename, content):
    """Replace an existing small boot file without reallocating its FAT chain."""
    with image.open("r+b") as f:
        header = f.read(512)
        bps = struct.unpack_from("<H", header, 11)[0]
        spc, nf = header[13], header[16]
        reserved = struct.unpack_from("<H", header, 14)[0]
        fatsz = struct.unpack_from("<I", header, 36)[0]
        root = struct.unpack_from("<I", header, 44)[0]
        data = (reserved + nf * fatsz) * bps
        def chain(cluster):
            seen = set()
            while 2 <= cluster < 0xffffff8:
                if cluster in seen: raise ValueError("FAT loop")
                seen.add(cluster)
                yield cluster
                f.seek(reserved * bps + cluster * 4)
                cluster = struct.unpack("<I", f.read(4))[0] & 0xfffffff
        directory = list(chain(root))
        long_name = {}
        found = False
        for cluster in directory:
            offset = data + (cluster - 2) * spc * bps
            f.seek(offset); entries = f.read(spc * bps)
            for i in range(0, len(entries), 32):
                entry = entries[i:i + 32]
                if entry[0] in (0, 0xe5): long_name = {}; continue
                if entry[11] == 15:
                    long_name[entry[0] & 31] = (entry[1:11] + entry[14:26] + entry[28:32]).decode("utf-16le")
                    continue
                name = ("".join(long_name[k] for k in sorted(long_name)).split("\0")[0]
                        if long_name else entry[:8].decode().strip() + "." + entry[8:11].decode().strip())
                long_name = {}
                if name.lower() != filename.lower(): continue
                first = struct.unpack_from("<H", entry, 20)[0] * 65536 + struct.unpack_from("<H", entry, 26)[0]
                clusters = list(chain(first))
                assert len(content) <= len(clusters) * spc * bps, "Boot replacement exceeds allocation"
                padded = content.ljust(len(clusters) * spc * bps, b"\0")
                for n, c in enumerate(clusters):
                    f.seek(data + (c - 2) * spc * bps); f.write(padded[n * spc * bps:(n + 1) * spc * bps])
                f.seek(offset + i + 28); f.write(struct.pack("<I", len(content)))
                found = True
        if not found: raise FileNotFoundError(filename)


def extract(source, work):
    with lzma.open(source, "rb") as stream:
        prefix = stream.read(8 * 1024 * 1024)
        assert prefix[510:512] == b"\x55\xaa"
        parts = []
        for i in range(4):
            start, sectors = struct.unpack_from("<II", prefix, 446 + i * 16 + 8)
            if sectors: parts.append((start * 512, sectors * 512, i + 1))
        for offset, size, number in parts:
            stream.seek(offset)
            destination = work / f"partition{number}.img"
            with destination.open("wb") as f:
                left = size
                while left:
                    chunk = stream.read(min(left, 4 * 1024 * 1024))
                    if not chunk: raise ValueError("Truncated base")
                    if chunk == bytes(len(chunk)): f.seek(len(chunk), 1)
                    else: f.write(chunk)
                    left -= len(chunk)
                f.truncate(size)
            print(f"Extracted base partition {number}", flush=True)
        while stream.read(4 * 1024 * 1024): pass
    return prefix, parts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.base.is_file() or args.base.is_symlink(): raise ValueError("Base must be a regular image file")
    if digest(args.base) != BASE_SHA256: raise ValueError("Unexpected base image checksum")
    if args.output.exists(): raise FileExistsError("Refusing to overwrite an existing beta build")
    args.output.mkdir(parents=True)
    work = args.output / "work"; work.mkdir(mode=0o700)
    prefix, parts = extract(args.base, work)
    root = RootImage(work / "partition2.img", work)
    source = args.source.resolve()
    deploy = source / "deploy"
    installed = {
        "usa-system-helper.py": ("/usr/local/libexec/usa-system-helper", 0o755),
        "usa_network.py": ("/usr/local/libexec/usa_network.py", 0o644),
        "usa-network-console.py": ("/usr/local/libexec/usa-network-console", 0o755),
        "beta-diagnostics.py": ("/usr/local/libexec/usa-beta-diagnostics", 0o755),
        "local-brain-guard.py": ("/usr/local/libexec/usa-local-brain-guard", 0o755),
        "usa-console.sudoers": ("/etc/sudoers.d/usa-console", 0o440),
        "USA-Ethernet.nmconnection": ("/etc/NetworkManager/system-connections/USA-Ethernet.nmconnection", 0o600),
        "usa-beta-journal.conf": ("/etc/systemd/journald.conf.d/usa-beta.conf", 0o644),
        "skelly-brain-policy.conf": ("/etc/systemd/system/skelly-brain.service.d/usa-policy.conf", 0o644),
    }
    for filename in ("usa-network.service", "usa-setup-hotspot.service", "usa-setup-hotspot.timer",
                     "usa-network-console.service", "usa-beta-diagnostics.service", "usa-beta-diagnostics.timer"):
        installed[filename] = ("/etc/systemd/system/" + filename, 0o644)
    for filename, (path, mode) in installed.items(): root.write(path, (deploy / filename).read_bytes(), mode)
    passwd, group = root.read("/etc/passwd"), root.read("/etc/group")
    used = {int(line.split(":")[2]) for line in (passwd + group).splitlines() if line}
    uid = next(n for n in range(998, 899, -1) if n not in used)
    assert "usa-console:" not in passwd
    root.write("/etc/passwd", passwd + f"usa-console:x:{uid}:{uid}:USA local setup:/nonexistent:/usr/sbin/nologin\n")
    root.write("/etc/group", group + f"usa-console:x:{uid}:\n")
    root.write("/etc/shadow", root.read("/etc/shadow") + f"usa-console:!:{int(time.time() // 86400)}:0:99999:7:::\n")
    root.write("/etc/gshadow", root.read("/etc/gshadow") + "usa-console:!::\n")
    for unit in ("usa-setup-hotspot.timer", "usa-beta-diagnostics.timer"):
        root.symlink("/etc/systemd/system/timers.target.wants/" + unit, "/etc/systemd/system/" + unit)
    root.symlink("/etc/systemd/system/multi-user.target.wants/usa-network-console.service",
                 "/etc/systemd/system/usa-network-console.service")
    root.remove("/etc/systemd/system/getty.target.wants/getty@tty1.service")
    root.symlink("/etc/systemd/system/getty@tty1.service", "/dev/null")
    package = "/opt/skelly-ai/venv/lib/python3.13/site-packages"
    root.write(package + "/skelly_ai/__init__.py", (source / "src/skelly_ai/__init__.py").read_bytes())
    metadata_path = package + "/skelly_ai-0.30.0.dist-info/METADATA"
    root.write(metadata_path, root.read(metadata_path).replace("Version: 0.30.0\n", "Version: 0.30.1b1\n"))
    record_path = package + "/skelly_ai-0.30.0.dist-info/RECORD"
    rows = list(csv.reader(io.StringIO(root.read(record_path))))
    for row in rows:
        target = package + "/" + row[0]
        if target in root.changes and row[0] != "skelly_ai-0.30.0.dist-info/RECORD":
            content = root.read(target).encode()
            row[1] = "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(content).digest()).decode().rstrip("=")
            row[2] = str(len(content))
    record = io.StringIO(); csv.writer(record, lineterminator="\n").writerows(rows)
    root.write(record_path, record.getvalue())
    issue = f"UltraSkellyAdvanced {VERSION} - experimental Raspberry Pi 3B support\nDerived from verified 0.30.0; hardware validation pending.\n"
    root.write("/etc/rpi-issue", issue)
    root.write("/etc/usa-experimental-image.json", json.dumps({"version": VERSION, "base_sha256": BASE_SHA256,
        "hardware_validation": "pending", "build_method": "offline overlay of verified clean image"}, indent=2) + "\n")
    replace_fat_file(work / "partition1.img", "issue.txt", issue.encode())
    readme = (source / "EXPERIMENTAL-FIRST-BOOT.txt").read_bytes()
    replace_fat_file(work / "partition1.img", "SKELLY-AI-README.txt", readme)
    for path in ("/var/lib/skelly-ai/onboarding.json", "/etc/skelly-ai/pi3b-qwen-enabled"):
        assert not root.exists(path), f"Unexpected owner state in beta: {path}"
    assert root.exists("/usr/lib/firmware/brcm/brcmfmac43430-sdio.raspberrypi,3-model-b.txt")
    assert root.exists("/usr/lib/python3.13/lib-dynload/_curses.cpython-313-aarch64-linux-gnu.so")
    print("Overlay written and every payload read back", flush=True)
    fsck = run(["e2fsck", "-f", "-n", str(root.image)])
    (args.output / "root-filesystem-check.txt").write_text(fsck.stdout + fsck.stderr)
    fat = run(["fsck.fat", "-n", "-v", str(work / "partition1.img")])
    (args.output / "boot-filesystem-check.txt").write_text(fat.stdout + fat.stderr)
    manifest = {str(p.relative_to(source)): digest(p) for p in sorted(source.rglob("*"))
                if p.is_file() and "__pycache__" not in p.parts and not p.name.endswith(".pyc")}
    (args.output / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (args.output / "image-overlay-manifest.json").write_text(json.dumps(root.changes, indent=2) + "\n")
    image = args.output / f"UltraSkellyAdvanced-{VERSION}-experimental.img"
    with image.open("wb") as f:
        f.write(prefix)
        for offset, size, number in parts:
            f.seek(offset)
            with (work / f"partition{number}.img").open("rb") as part:
                for chunk in iter(lambda: part.read(4 * 1024 * 1024), b""):
                    if chunk == bytes(len(chunk)): f.seek(len(chunk), 1)
                    else: f.write(chunk)
        f.truncate(max(offset + size for offset, size, _ in parts))
    print("Compressing experimental image", flush=True)
    run(["xz", "-T2", "-3", "--keep", str(image)])
    compressed = image.with_suffix(".img.xz")
    run(["xz", "--test", str(compressed)])
    checksum = digest(compressed)
    (args.output / (compressed.name + ".sha256")).write_text(checksum + "  " + compressed.name + "\n")
    info = {"version": VERSION, "base_sha256": BASE_SHA256, "image_sha256": checksum,
            "compressed_bytes": compressed.stat().st_size, "expanded_bytes": image.stat().st_size,
            "hardware_validation": "pending", "source_manifest_sha256": digest(args.output / "source-manifest.json")}
    (args.output / "build-info.json").write_text(json.dumps(info, indent=2) + "\n")
    print(json.dumps(info, indent=2), flush=True)


if __name__ == "__main__": main()
