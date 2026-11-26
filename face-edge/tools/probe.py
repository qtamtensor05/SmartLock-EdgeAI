"""Prepare pinned JPEG fixtures and build the isolated ESP-IDF probe (no flashing)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
from run_qemu import qemu_environment

MODULE = Path(__file__).resolve().parents[1]
PROJECT = MODULE / 'examples/esp32s3_probe'
UPSTREAM = '24ac077101e77f14f66561b0306158ce42486e1b'


def verify_probe():
    folder = PROJECT / 'main/fixtures'
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['upstream_commit'] != UPSTREAM:
        raise ValueError('Fixture source does not match pinned commit')
    for row in manifest['files']:
        path = folder / row['path']
        if path.parent != folder or path.suffix != '.jpg':
            raise ValueError('Invalid fixture path')
        data = path.read_bytes()
        if len(data) != row['bytes'] or hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError(f'Fixture hash mismatch: {path.name}')
    print('Four fixture hashes verified; no inference performed.')


def prepare_probe():
    folder = PROJECT / 'main/fixtures'
    folder.mkdir(parents=True, exist_ok=True)
    manifest_path = folder / 'manifest.json'
    expected = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else None
    expected_hashes = {row['path']: row['sha256'] for row in expected['files']} if expected else {}
    manifest = {'upstream_commit': UPSTREAM, 'purpose': 'upstream example fixtures, not evaluation data', 'files': []}
    for name in ('bill1', 'bill2', 'musk1', 'musk2'):
        url = f'https://raw.githubusercontent.com/espressif/esp-dl/{UPSTREAM}/examples/human_face_recognition/faces/{name}.jpg'
        dest = folder / f'{name}.jpg'
        data = urllib.request.urlopen(url, timeout=60).read()
        if not (data.startswith(b'\xff\xd8') and data.endswith(b'\xff\xd9')):
            raise ValueError(f'Invalid JPEG: {url}')
        if expected_hashes and hashlib.sha256(data).hexdigest() != expected_hashes[dest.name]:
            raise ValueError(f'Upstream fixture hash mismatch: {dest.name}')
        dest.write_bytes(data)
        manifest['files'].append({'path': dest.name, 'url': url, 'bytes': len(data),
                                  'sha256': hashlib.sha256(data).hexdigest()})
    (folder / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print('Prepared four upstream JPEG fixtures. No face inference performed.')


def build_probe(fixture_compat=False):
    verify_probe()
    # Preserve explicit Windows subst paths; resolve() expands them back to long paths.
    idf = Path(os.environ.get('IDF_PATH', MODULE / '.tools/esp-idf'))
    tools = Path(os.environ.get('IDF_TOOLS_PATH', MODULE / '.tools/idf-tools'))
    project = Path(os.environ.get('FACE_EDGE_PROBE_PATH', PROJECT))
    if not (idf / 'tools/idf.py').is_file():
        raise RuntimeError('Install ESP-IDF v5.5.2; see examples/esp32s3_probe/README.md')
    env = dict(qemu_environment(), IDF_PATH=str(idf), IDF_TOOLS_PATH=str(tools), IDF_TARGET='esp32s3')
    candidates = list((tools / 'python_env').glob('idf5.5*_env/Scripts/python.exe'))
    if os.name != 'nt':
        candidates += list((tools / 'python_env').glob('idf5.5*_env/bin/python'))
    python = str(candidates[0]) if candidates else sys.executable
    env['IDF_PYTHON_ENV_PATH'] = str(Path(python).parent.parent)
    exported = subprocess.check_output([python, str(idf / 'tools/idf_tools.py'), 'export',
                                        '--format', 'key-value'], env=env, text=True)
    for line in exported.splitlines():
        if '=' not in line:
            continue
        key, value = line.split('=', 1)
        value = value.replace('%PATH%', env.get('PATH', '')).replace('$PATH', env.get('PATH', ''))
        env[key] = value
    env['PATH'] = str(Path(python).parent) + os.pathsep + env['PATH']
    version = subprocess.check_output([python, str(idf / 'tools/idf.py'), '--version'], env=env, text=True)
    if 'ESP-IDF v5.5.2' not in version:
        raise RuntimeError(f'Expected ESP-IDF v5.5.2, got {version.strip()}')
    for action in ('build', 'size'):
        subprocess.run([python, str(idf / 'tools/idf.py'), '-C', str(project),
                        '-D', f'FACE_PROBE_FIXTURE_COMPAT={"ON" if fixture_compat else "OFF"}', action],
                       env=env, check=True)
    build = project / 'build'
    size_json = subprocess.check_output([python, '-m', 'esp_idf_size', '--format', 'json',
                                         str(build / 'face_edge_probe.map')], env=env, text=True)
    size = json.loads(size_json)
    config = json.loads((build / 'config/sdkconfig.json').read_text(encoding='utf-8'))
    image = (build / 'face_edge_probe.bin').read_bytes()
    report = {'evidence': 'cross_compile_only_not_execution', 'idf': version.strip(),
              'idf_target': 'esp32s3', 'app_binary_bytes': len(image),
              'app_binary_sha256': hashlib.sha256(image).hexdigest(),
              'fixture_compat_largest_face_only_for_fixed_images': fixture_compat,
              'build_configuration': {key: config[key] for key in (
                  'ESPTOOLPY_FLASHSIZE', 'SPIRAM_MODE_OCT', 'SPIRAM_SPEED_80M',
                  'ESP_DEFAULT_CPU_FREQ_MHZ', 'FLASH_HUMAN_FACE_FEAT_MFN_S8_V1',
                  'FLASH_HUMAN_FACE_DETECT_MSRMNP_S8_V1')},
              'linker_size_report': size,
              'runtime_latency_us': None, 'runtime_heap_bytes': None, 'recognition_accuracy': None}
    output = MODULE / 'output'
    output.mkdir(exist_ok=True)
    (output / 'probe-build.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'verify', 'build'))
    parser.add_argument('--fixture-compat', action='store_true', help='Build upstream largest-face behavior for embedded fixtures only')
    args = parser.parse_args()
    try:
        if args.action == 'build':
            build_probe(args.fixture_compat)
        else:
            {'prepare': prepare_probe, 'verify': verify_probe}[args.action]()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f'Probe failed: {exc}', file=sys.stderr)
        raise SystemExit(1)
