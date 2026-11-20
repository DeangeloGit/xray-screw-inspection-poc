"""Isolated runtime for the additive 5r inspection policy.

Keeps all hash-verified legacy policy files byte-for-byte unchanged.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
from dataclasses import replace


class Engine:
    def __init__(self, home, provider='cpu'):
        self.home = Path(home).resolve()
        config = json.loads((self.home/'settings.json').read_text(encoding='utf8'))
        root = Path(__file__).resolve().parents[2]
        sys.path[:0] = [str(root), str(root/'experiments/dino')]
        os.environ['XRAY_CONFIG'] = str(self.home/'settings.json')
        os.environ['XRAY_WORKSPACE'] = str(self.home/'station')
        os.environ['XRAY_4R_ASSET_ROOT'] = config['asset_root']
        os.environ['XRAY_OVERKILL_PILOT'] = '1'
        os.environ['XRAY_5R_LOCAL_REVIEW'] = '1'
        import cv2
        import new_model_run as experiment
        from model_manager import manager
        from live4r_examples import LiveBanks
        from live5r_review import ReviewBundle
        import spatial5r
        import enclosure_guard5r
        import fragment_core_guard5r
        import enclosure_rescue5r
        import structure_shadow5r
        import confirmed_local_service5r
        import confirmed_local_reference_shadow5r
        import ok_reference_shadow5r
        import structure_cause_shadow5r
        cv2.setNumThreads(4)
        self.lock = threading.RLock()
        self.manager = manager
        manager.execution_override = provider
        original = manager.snapshot()
        if original.error or original.session is None:
            raise ValueError('DINO model unavailable: '+str(original.info()))
        experiment.ROOT = Path(config['asset_root']).resolve()
        manifest, bank, self.review, self.normal, details = experiment.load_banks(original)
        self.cache = experiment.TensorCache(original.session, original.identity, limit=1800)
        identity = hashlib.sha256(('4r-live-'+original.identity+''.join(sorted(details['hashes'].values()))).encode()).hexdigest()
        frozen = replace(original,session=self.cache,manifest=manifest,feature_bank=bank,identity=identity)
        self.banks = LiveBanks(self.home,original,frozen,details,self.lock)
        self.bundle = ReviewBundle(self.home/'local-review')
        self.confirmed_local = confirmed_local_service5r.LocalReferenceReview(
            self.home/'confirmed-local-review', config.get('confirmed_local_manifest_sha256'))
        # Include both orchestration and policy in cache identity.
        self.policy_hash = hashlib.sha256(Path(spatial5r.__file__).read_bytes()+Path(enclosure_guard5r.__file__).read_bytes()+Path(fragment_core_guard5r.__file__).read_bytes()+Path(enclosure_rescue5r.__file__).read_bytes()+Path(structure_shadow5r.__file__).read_bytes()+Path(__file__).read_bytes()+Path(confirmed_local_service5r.__file__).read_bytes()+Path(confirmed_local_reference_shadow5r.__file__).read_bytes()+Path(ok_reference_shadow5r.__file__).read_bytes()+Path(structure_cause_shadow5r.__file__).read_bytes()+str(config.get('confirmed_local_manifest_sha256','')).encode()).hexdigest()
        self.experiment = experiment

    def snapshot(self, version_directory=None):
        base = self.banks.load(version_directory)[0] if version_directory else self.banks.current
        selected = self.bundle.tagged_snapshot(base)
        return replace(selected,identity=hashlib.sha256((selected.identity+'|'+self.policy_hash).encode()).hexdigest())

    def detect(self, reference, target, name, threshold=.13, model_snapshot=None, output_directory=None):
        import detector
        import overkill_pilot as pilot
        import spatial5r
        import enclosure_guard5r
        import fragment_core_guard5r
        import enclosure_rescue5r
        import structure_shadow5r
        if output_directory is None:
            output_directory = self.home/'station/outputs'/name
        directory = Path(output_directory)
        with self.lock:
            self.cache.clear()
            selected = model_snapshot or self.snapshot()
            with self.experiment.four_r(detector,pilot,selected,self.review,self.normal):
                result = detector.detect(reference,target,name,threshold,selected,directory)
            result = self.bundle.apply(selected,result,directory,self.review,self.normal)
            result = spatial5r.apply(selected,self.bundle,result,directory,reference,target,self.review,self.normal)
            result = fragment_core_guard5r.apply(selected,result,directory)
            result = enclosure_guard5r.apply(selected,result,directory)
            result = enclosure_rescue5r.apply(selected,result,directory)
            result = structure_shadow5r.apply(result,directory)
            result = self.confirmed_local.apply(result,directory,reference,target)
            result['experimental_policy'] = '5r alarm-only local review + '+spatial5r.VERSION+' + '+fragment_core_guard5r.VERSION+' + '+enclosure_guard5r.VERSION+' + '+enclosure_rescue5r.VERSION
            result['experimental_main_bank'] = dict(
                screw=len(selected.manifest['example_bank']['screw']['ids']),
                normal=len(selected.manifest['example_bank']['normal']['ids']),
                version=selected.requested,fingerprint=selected.identity)
            result['production_changed'] = False
            temporary = directory/'result.spatial.tmp'
            temporary.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
            temporary.replace(directory/'result.json')
            return result
