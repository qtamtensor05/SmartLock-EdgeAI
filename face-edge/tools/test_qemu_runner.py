"""Host checks for the QEMU runner, not evidence of model inference."""
import json
from pathlib import Path
import tempfile
import unittest

from run_qemu import merge_probe_flash, parse_probe_log


def fixture_log():
    rows = ['case=enroll_a enrolled=ESP_OK template_count=1',
            'case=enroll_b enrolled=ESP_OK template_count=2',
            'case=query_b_before_enroll match_count=0',
            'case=query_a match_count=1', 'case=query_b match_count=1',
            'case=query_a template_id=1 similarity=0.9',
            'case=query_b template_id=2 similarity=0.8',
            'PROBE completed=true', 'MEM stage=after_cleanup']
    rows.extend(f'TIME case={name} decode_us=1 detect_us=2 feat_db_us=3 total_us=6'
                for name in ('enroll_a', 'query_b_before_enroll', 'enroll_b', 'query_a', 'query_b'))
    return '\n'.join(rows)


class QemuRunnerTests(unittest.TestCase):
    def test_complete_telemetry(self):
        self.assertTrue(parse_probe_log(fixture_log())['functional_pass'])

    def test_boot_only_is_not_success(self):
        self.assertFalse(parse_probe_log('ESP-ROM:esp32s3\nFIXED_JPEG_PROBE')['functional_pass'])

    def test_compatibility_pass_is_not_strict_detector_pass(self):
        result = parse_probe_log(fixture_log() + '\nMODE fixture_compat=1\nFIXTURE_COMPAT case=enroll_a face_count=7')
        self.assertTrue(result['functional_pass'])
        self.assertTrue(result['fixture_compat'])
        self.assertFalse(result['strict_detector_pass'])

    def test_swapped_identities_are_rejected(self):
        log = fixture_log().replace('query_a template_id=1', 'query_a template_id=2')
        log = log.replace('query_b template_id=2', 'query_b template_id=1')
        self.assertFalse(parse_probe_log(log)['functional_pass'])

    def test_incomplete_or_panicked_run_is_rejected(self):
        self.assertFalse(parse_probe_log(fixture_log().replace('MEM stage=after_cleanup', ''))['functional_pass'])
        self.assertFalse(parse_probe_log(fixture_log() + '\nGuru Meditation')['functional_pass'])

    def test_flash_offsets_and_padding(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'boot.bin').write_bytes(b'BOOT')
            (root / 'app.bin').write_bytes(b'APP')
            args = {'extra_esptool_args': {'chip': 'esp32s3'},
                    'flash_settings': {'flash_size': '2MB'},
                    'flash_files': {'0x0': 'boot.bin', '0x10000': 'app.bin'}}
            (root / 'flasher_args.json').write_text(json.dumps(args))
            dest = root / 'output/flash.bin'
            merge_probe_flash(root, dest)
            image = dest.read_bytes()
            self.assertEqual(len(image), 2 * 1024 * 1024)
            self.assertEqual(image[:4], b'BOOT')
            self.assertEqual(image[4:8], b'\xff' * 4)
            self.assertEqual(image[0x10000:0x10003], b'APP')
            args['flash_files']['0x2'] = 'app.bin'
            (root / 'flasher_args.json').write_text(json.dumps(args))
            with self.assertRaises(ValueError):
                merge_probe_flash(root, dest)


if __name__ == '__main__':
    unittest.main()
