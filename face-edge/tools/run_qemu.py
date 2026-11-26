"""Run the actual ESP32-S3 probe binary in Espressif QEMU; never drives hardware."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import threading
import time

MODULE = Path(__file__).resolve().parents[1]
DEFAULT_BUILD = MODULE / 'examples/esp32s3_probe/build'


def merge_probe_flash(build, output):
    build = build.resolve()
    args = json.loads((build / 'flasher_args.json').read_text(encoding='utf-8'))
    if args['extra_esptool_args']['chip'] != 'esp32s3':
        raise ValueError('Only ESP32-S3 images are supported')
    size_name = args['flash_settings']['flash_size']
    if size_name not in ('2MB', '4MB', '8MB', '16MB'):
        raise ValueError(f'Unsupported QEMU flash size: {size_name}')
    size = int(size_name[:-2]) * 1024 * 1024
    image = bytearray(b'\xff') * size
    segments = []
    previous_end = 0
    for address, filename in sorted(args['flash_files'].items(), key=lambda item: int(item[0], 0)):
        offset = int(address, 0)
        path = (build / filename).resolve()
        if not path.is_relative_to(build):
            raise ValueError('Flash segment escapes build directory')
        data = path.read_bytes()
        if not data or offset < previous_end or offset + len(data) > size:
            raise ValueError(f'Empty, overlapping or oversized flash segment: {filename}')
        image[offset:offset + len(data)] = data
        previous_end = offset + len(data)
        segments.append({'file': filename, 'offset': offset, 'bytes': len(data),
                         'sha256': hashlib.sha256(data).hexdigest()})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(image)
    return {'flash_bytes': size, 'flash_sha256_before_run': hashlib.sha256(image).hexdigest(),
            'segments': segments}


def parse_probe_log(log):
    # Strip terminal escapes without changing UART data saved in the raw log.
    log = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', log)
    matches = {}
    for case, identity, score in re.findall(r'case=(\w+) template_id=(\d+) similarity=([\d.eE+-]+)', log):
        matches[case] = {'template_id': int(identity), 'similarity': float(score)}
    counts = {case: int(count) for case, count in re.findall(r'case=(\w+) match_count=(\d+)', log)}
    timing = [dict(case=case, decode_us=int(dec), detect_us=int(det), feat_db_us=int(feat), total_us=int(total))
              for case, dec, det, feat, total in re.findall(
                  r'TIME case=(\w+) decode_us=(\d+) detect_us=(\d+) feat_db_us=(\d+) total_us=(\d+)', log)]
    checks = {
        'completed': 'PROBE completed=true' in log,
        'cleanup_reached': 'MEM stage=after_cleanup' in log,
        'two_enrollments': all(re.search(rf'case={case} enrolled=ESP_OK template_count={count}\b', log)
                               for case, count in [('enroll_a', 1), ('enroll_b', 2)]),
        'unregistered_b_rejected': counts.get('query_b_before_enroll') == 0,
        'a_and_b_recognized': counts.get('query_a') == 1 and counts.get('query_b') == 1,
        'different_identities': ('query_a' in matches and 'query_b' in matches
                                 and matches['query_a']['template_id'] != matches['query_b']['template_id']),
        # Pinned SDK starts IDs at 1; this probe always clears DB, then enrolls A followed by B.
        'expected_identity_mapping': (matches.get('query_a', {}).get('template_id') == 1
                                      and matches.get('query_b', {}).get('template_id') == 2),
        'five_timing_records': len(timing) == 5,
        'no_guest_fault': not any(marker in log for marker in ('Guru Meditation', 'assert failed', 'abort()')),
    }
    memory = [dict(stage=stage, internal_free=int(free), internal_min_since_boot=int(low),
                   psram_free=int(psram), psram_largest=int(largest))
              for stage, free, low, psram, largest in re.findall(
                  r'MEM stage=(\w+) internal_free=(\d+) internal_min_since_boot=(\d+) psram_free=(\d+) psram_largest=(\d+)', log)]
    rejections = [dict(case=case, face_count=int(count))
                  for case, count in re.findall(r'case=(\w+) rejected face_count=(\d+)', log)]
    return {'checks': checks, 'matches': matches, 'match_counts': counts,
            'emulator_memory_snapshots_not_hardware': memory,
            'fixture_rejections': rejections,
            'model_execution_completed': checks['completed'] and checks['five_timing_records'],
            'emulator_timing_not_hardware': timing,
            'fixture_compat': 'MODE fixture_compat=1' in log,
            'functional_pass': all(checks.values()),
            'strict_detector_pass': all(checks.values()) and 'FIXTURE_COMPAT' not in log}


def find_qemu(explicit):
    if explicit:
        return Path(explicit)
    pinned = MODULE / '.tools/qemu-20261109/qemu/bin/qemu-system-xtensa.exe'
    if os.name == 'nt' and pinned.is_file():
        return pinned
    if os.name == 'nt':
        raise RuntimeError('Run python face-edge/tools/setup_qemu.py to install the tested QEMU release')
    tools = Path(os.environ.get('IDF_TOOLS_PATH', MODULE / '.tools/idf-tools'))
    name = 'qemu-system-xtensa.exe' if os.name == 'nt' else 'qemu-system-xtensa'
    candidates = sorted((tools / 'tools/qemu-xtensa').glob(f'*/qemu/bin/{name}'))
    if not candidates:
        raise RuntimeError('Install qemu-xtensa with ESP-IDF idf_tools.py first; see probe README')
    return candidates[-1]


def qemu_environment():
    env = dict(os.environ)
    # Official Windows archive needs libiconv-2.dll; Git for Windows supplies it.
    if os.name == 'nt':
        git = shutil.which('git')
        if git:
            dll_folder = Path(git).parent.parent / 'mingw64/bin'
            if (dll_folder / 'libiconv-2.dll').is_file():
                env['PATH'] = str(dll_folder) + os.pathsep + env.get('PATH', '')
    return env


def run_qemu_probe(build, output, qemu, psram_mb, timeout):
    output.mkdir(parents=True, exist_ok=True)
    flash = output / 'qemu-flash.bin'
    flash_info = merge_probe_flash(build, flash)
    env = qemu_environment()
    version = subprocess.check_output([str(qemu), '--version'], env=env, text=True, stderr=subprocess.STDOUT)
    machine_list = subprocess.check_output([str(qemu), '-machine', 'help'], env=env, text=True, stderr=subprocess.STDOUT)
    if 'esp32s3' not in machine_list:
        raise RuntimeError('This QEMU build does not advertise the esp32s3 machine')
    # All guest writes go to the disposable merged flash image, never the input binaries.
    command = [str(qemu), '-machine', 'esp32s3', '-m', f'{psram_mb}M',
               '-global', 'driver=ssi_psram,property=is_octal,value=true',
               '-drive', 'file=qemu-flash.bin,if=mtd,format=raw',
               '-display', 'none', '-serial', 'stdio', '-monitor', 'none', '-nic', 'none', '-no-reboot']
    started = time.monotonic()
    lines = []
    messages = queue.Queue()
    process = subprocess.Popen(command, cwd=output, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)

    def read_uart():
        try:
            for line in iter(process.stdout.readline, b''):
                messages.put(line)
        finally:
            messages.put(None)

    reader = threading.Thread(target=read_uart, daemon=True)
    reader.start()
    timed_out = False
    stopped_on_cleanup = False
    try:
        with (output / 'qemu-uart.log').open('wb') as uart:
            while True:
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    timed_out = True
                    break
                try:
                    line = messages.get(timeout=min(0.25, remaining))
                except queue.Empty:
                    continue
                if line is None:
                    break
                uart.write(line)
                uart.flush()
                text = line.decode('utf-8', errors='replace')
                lines.append(text)
                print(text, end='', flush=True)
                if 'MEM stage=after_cleanup' in text:
                    stopped_on_cleanup = True
                    break
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        reader.join(timeout=2)
        process.stdout.close()
    log = ''.join(lines)
    results = parse_probe_log(log)
    if results['functional_pass']:
        status = 'fixture_compat_pass' if results['fixture_compat'] else 'functional_pass'
    elif 'IllegalInstruction' in log or 'illegal instruction' in log.lower():
        status = 'unsupported_instruction_or_firmware_fault'
    elif 'PSRAM unavailable' in log or 'PSRAM ID read error' in log:
        status = 'psram_failure'
    elif 'Guru Meditation' in log or 'assert failed' in log or 'abort()' in log:
        status = 'guest_panic'
    elif 'rejected face_count=' in log:
        status = 'detector_rejected_fixture'
    elif results['model_execution_completed']:
        status = 'recognition_checks_failed'
    elif timed_out:
        status = 'timeout'
    else:
        status = 'incomplete_or_result_mismatch'
    report = {'evidence': 'actual_esp32s3_binary_in_emulator_not_physical_board',
              'status': status, 'qemu_version': version.strip(), 'command': command,
              'psram_mb_emulated_assumption': psram_mb, 'flash': flash_info,
              'host_elapsed_seconds_not_device_latency': time.monotonic() - started,
              'timeout_seconds': timeout, 'timed_out': timed_out,
              'stopped_on_cleanup': stopped_on_cleanup, 'qemu_exit_code': process.returncode,
              'results': results, 'hardware_latency_us': None, 'hardware_peak_ram_bytes': None,
              'recognition_accuracy_on_evaluation_dataset': None}
    (output / 'qemu-result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f'QEMU status: {status}; report: {output / "qemu-result.json"}')
    return results['functional_pass']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir', type=Path, default=DEFAULT_BUILD)
    parser.add_argument('--output-dir', type=Path, default=MODULE / 'output/qemu')
    parser.add_argument('--qemu', help='Path to Espressif qemu-system-xtensa executable')
    parser.add_argument('--psram-mb', type=int, choices=(2, 4, 8, 16, 32), default=8)
    parser.add_argument('--timeout', type=float, default=120)
    args = parser.parse_args()
    try:
        if args.timeout <= 0:
            raise ValueError('Timeout must be positive')
        passed = run_qemu_probe(args.build_dir, args.output_dir.resolve(), find_qemu(args.qemu).resolve(),
                                args.psram_mb, args.timeout)
        raise SystemExit(0 if passed else 1)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f'QEMU probe failed: {exc}', file=sys.stderr)
        raise SystemExit(1)
