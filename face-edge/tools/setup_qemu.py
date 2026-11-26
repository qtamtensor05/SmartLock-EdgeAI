"""Install the pinned official Windows QEMU release into the module's tools directory."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import urllib.request

from run_qemu import MODULE, qemu_environment


def setup_qemu():
    if os.name != 'nt':
        raise RuntimeError('This pinned archive is for Windows. Install Espressif qemu-xtensa for your OS and use --qemu.')
    spec = json.loads(Path(__file__).with_name('qemu-tool.json').read_text(encoding='utf-8'))
    root = MODULE / '.tools' / spec['install_dir']
    root.mkdir(parents=True, exist_ok=True)
    archive = root / spec['url'].split('/')[-1]
    if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest() != spec['sha256']:
        chunk = 1024 * 1024
        bounds = [(n, min(n + chunk, spec['bytes']) - 1) for n in range(0, spec['bytes'], chunk)]

        def fetch(bound):
            start, end = bound
            request = urllib.request.Request(spec['url'], headers={'Range': f'bytes={start}-{end}'})
            with urllib.request.urlopen(request, timeout=90) as response:
                if response.status != 206 or response.headers.get('Content-Range') != f'bytes {start}-{end}/{spec["bytes"]}':
                    raise RuntimeError('Server did not return the requested archive range')
                data = response.read()
                if len(data) != end - start + 1:
                    raise RuntimeError('Incomplete download')
                return data

        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            data = b''.join(pool.map(fetch, bounds))
        if len(data) != spec['bytes'] or hashlib.sha256(data).hexdigest() != spec['sha256']:
            raise RuntimeError('QEMU archive integrity check failed')
        archive.write_bytes(data)
    executable = root / 'qemu/bin/qemu-system-xtensa.exe'
    # Extract only after checking the pinned release archive, including its ROM files.
    with tarfile.open(archive) as bundle:
        bundle.extractall(root, filter='data')
    version = subprocess.check_output([str(executable), '--version'], env=qemu_environment(),
                                      text=True, stderr=subprocess.STDOUT)
    if spec['release'].replace('-', '_', 1).replace('-', '_') not in version.replace('-', '_'):
        raise RuntimeError(f'Unexpected QEMU release: {version.strip()}')
    print(version.strip())
    print(f'Installed in workspace: {executable}')


if __name__ == '__main__':
    try:
        setup_qemu()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f'QEMU setup failed: {exc}')
