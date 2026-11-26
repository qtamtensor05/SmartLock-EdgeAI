"""Host-only contract simulation. Synthetic vectors are NOT face-model outputs."""
import argparse
import configparser
import json
import math
import re
from pathlib import Path


class FaceEdgeSimulator:
    """Exercise proposed enrollment and 1:N matching without camera or AI."""

    def __init__(self, threshold=0.8, margin=0.05):
        self.threshold = threshold
        self.margin = margin
        self.templates = {}
        self.dimension = None

    def normalize(self, vector):
        if not vector or not all(math.isfinite(x) for x in vector):
            raise ValueError('invalid embedding')
        norm = math.sqrt(sum(x * x for x in vector))
        if norm == 0:
            raise ValueError('zero embedding')
        if self.dimension is not None and len(vector) != self.dimension:
            raise ValueError('embedding dimension mismatch')
        return [x / norm for x in vector]

    def enroll(self, person_id, vector):
        if not person_id:
            raise ValueError('person_id is required')
        normalized = self.normalize(vector)
        self.dimension = len(normalized)
        self.templates.setdefault(person_id, []).append(normalized)

    def remove(self, person_id):
        self.templates.pop(person_id, None)
        if not self.templates:
            self.dimension = None

    def identify(self, vector=None, face_count=1, quality_ok=True):
        result = {'status': 'unknown', 'person_id': None, 'similarity': None,
                  'evidence': 'synthetic_embedding_contract_only'}
        if face_count != 1:
            result['status'] = 'no_face' if face_count == 0 else 'multiple_faces'
            return result
        if not quality_ok:
            result['status'] = 'low_quality'
            return result
        try:
            query = self.normalize(vector)
        except (ValueError, TypeError):
            result['status'] = 'error'
            return result
        scores = sorted(((max(sum(a*b for a, b in zip(query, sample))
                              for sample in samples), person_id)
                         for person_id, samples in self.templates.items()), reverse=True)
        if scores:
            score, person_id = scores[0]
            result['similarity'] = score
            if score >= self.threshold and (len(scores) == 1 or score - scores[1][0] >= self.margin):
                result.update(status='recognized', person_id=person_id)
        return result


def collect_project_profile(root):
    ini = configparser.ConfigParser(interpolation=None)
    ini.read(root / 'platformio.ini', encoding='utf-8')
    env = ini['env:esp32-s3-devkitc-1']
    pins = (root / 'src/config/PinConfig.h').read_text(encoding='utf-8')
    camera = (root / 'src/camera/CameraService.cpp').read_text(encoding='utf-8')
    main = (root / 'src/main.cpp').read_text(encoding='utf-8')
    app = (root / 'src/config/AppConfig.h').read_text(encoding='utf-8')
    diagram = json.loads((root / 'diagram.json').read_text(encoding='utf-8'))
    groups = {}
    for name, body in re.findall(r'namespace\s+(\w+)\s*\{([^{}]*)\}', pins):
        groups[name] = {key: int(value, 0) for key, value in
                        re.findall(r'constexpr\s+\w+\s+(\w+)\s*=\s*(-?(?:0x[0-9a-fA-F]+|\d+))\s*;', body)}
    occupied = {}
    for group, values in groups.items():
        for key, value in values.items():
            if value not in (-1, 255):
                occupied.setdefault(value, []).append(f'{group}.{key}')
    interval = re.search(r'CAMERA_STREAM_INTERVAL_MS\s*=\s*(\d+)', main)
    otp = re.search(r'namespace Otp\s*\{([^{}]*)\}', app).group(1)
    return {
        'evidence': 'source_configuration_not_hardware_measurement',
        'sources': ['platformio.ini', 'src/config/PinConfig.h', 'src/config/AppConfig.h',
                    'src/camera/CameraService.cpp', 'src/main.cpp', 'diagram.json'],
        'board': env['board'], 'framework': env['framework'],
        'flash_configured': env['board_build.flash_size'],
        'psram_type_configured': env['board_build.psram_type'],
        'psram_capacity_bytes': None,
        'serial_baud_configured': int(env['monitor_speed']),
        'camera_format': re.search(r'config.pixel_format\s*=\s*(\w+)', camera).group(1),
        'camera_frame_modes': re.findall(r'config.frame_size\s*=\s*(\w+)', camera),
        'preview_interval_ms': int(interval.group(1)),
        'preview_nominal_hz_not_measured': 1000 / int(interval.group(1)),
        'otp': {k: int(v) for k, v in re.findall(r'constexpr\s+[\w ]+?\s+(\w+)\s*=\s*(\d+);', otp)},
        'pins': groups,
        'pin_conflicts': {str(k): v for k, v in occupied.items() if len(v) > 1},
        'wokwi_parts': [part['type'] for part in diagram['parts']],
        'hardware_measurements': {'inference_ms': None, 'free_heap_bytes': None,
                                  'peak_psram_bytes': None, 'recognition_accuracy': None},
    }


def run_scenarios():
    sim = FaceEdgeSimulator()
    sim.enroll('person-a', [1, 0, 0])
    sim.enroll('person-b', [0, 1, 0])
    cases = [
        ('known_a', {'vector': [0.99, 0.01, 0]}, 'recognized', 'person-a'),
        ('known_b', {'vector': [0.01, 0.99, 0]}, 'recognized', 'person-b'),
        ('stranger', {'vector': [0, 0, 1]}, 'unknown', None),
        ('ambiguous', {'vector': [1, 1, 0]}, 'unknown', None),
        ('no_face', {'face_count': 0}, 'no_face', None),
        ('multiple_faces', {'face_count': 2}, 'multiple_faces', None),
        ('poor_quality', {'quality_ok': False}, 'low_quality', None),
        ('bad_dimension', {'vector': [1, 0]}, 'error', None),
        ('zero_vector', {'vector': [0, 0, 0]}, 'error', None),
        ('nonfinite_vector', {'vector': [float('nan'), 0, 0]}, 'error', None),
    ]
    rows = []
    for name, args, status, person in cases:
        result = sim.identify(**args)
        rows.append({'case': name, 'result': result,
                     'passed': result['status'] == status and result['person_id'] == person})
    sim.remove('person-a')
    result = sim.identify([1, 0, 0])
    rows.append({'case': 'deleted_identity', 'result': result, 'passed': result['status'] == 'unknown'})
    empty = FaceEdgeSimulator().identify([1, 0, 0])
    rows.append({'case': 'empty_database', 'result': empty, 'passed': empty['status'] == 'unknown'})
    # Exercise high-scoring ambiguity independently of the minimum-score threshold.
    ambiguous = FaceEdgeSimulator(threshold=0.6).identify([1, 1, 0])
    tied = FaceEdgeSimulator(threshold=0.6)
    tied.enroll('a', [1, 0, 0])
    tied.enroll('b', [0, 1, 0])
    ambiguous = tied.identify([1, 1, 0])
    rows.append({'case': 'above_threshold_tie', 'result': ambiguous,
                 'passed': ambiguous['status'] == 'unknown'})
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, default=next((p for p in Path(__file__).resolve().parents if (p / 'platformio.ini').is_file()), None))
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent / 'output/report.json')
    args = parser.parse_args()
    if args.project_root is None:
        parser.error('--project-root must point to the SmartLock firmware repository')
    report = {'mode': 'host_contract_simulation_no_ai_model',
              'project_profile': collect_project_profile(args.project_root),
              'illustrative_threshold_not_calibrated': 0.8,
              'scenarios': run_scenarios()}
    report['passed'] = all(row['passed'] for row in report['scenarios'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"{sum(row['passed'] for row in report['scenarios'])}/{len(report['scenarios'])} contract scenarios passed")
    print(f"Report: {args.output.resolve()}")
    print('No camera, face model, ESP32 firmware execution or hardware performance was tested.')
    raise SystemExit(0 if report['passed'] else 1)
