import copy
import hashlib
import importlib.util
import json
from contextlib import contextmanager
from pathlib import Path
import select
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

import numpy as np

from harmonic_analysis.analysis import analyze, decode_audio
from harmonic_analysis import sam_chunks, sam_jobs
from harmonic_analysis.bundle import read_bundle
from harmonic_analysis.sam_chunks import (TEXT_REVISION, coordinates, load_plan, make_plan, overlap_metrics,
                                           stitch_song, validate_plan, validate_song_metadata, validate_song_result, weights)
from harmonic_analysis.sam_jobs import digest, load_job, new_directory, read_wave, save_pair, write_json
from harmonic_analysis.source_features import build_source_bundle

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / 'workers/sam_audio/worker.py'
PLAYER = ROOT / 'build/harmonic-player'
spec = importlib.util.spec_from_file_location('sam_song_worker', WORKER)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class SongChunkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        t = np.arange(7001, dtype=np.float32)
        self.samples = np.column_stack([0.4 * np.sin(t / 13), 0.4 * np.sin(t / 13)]).astype('<f4')
        self.source = {'path': '/synthetic.wav', 'sha256': 'a'*64,
                       'pcm_sha256': hashlib.sha256(self.samples.tobytes()).hexdigest(),
                       'sample_count': len(self.samples)}
        self.plan_path = make_plan(self.samples, self.source, self.root/'plan', chunk=2000, overlap=400,
                                   targets={'vocals':'man singing'})
        self.plan, _ = load_plan(self.plan_path)
        self.results = self.root/'chunks'
        self.session_loads = 0

    @contextmanager
    def fake_session(self, *args, **kwargs):
        self.session_loads += 1
        yield {'simulated': True}

    def fake_separate(self, job_path, destination, session, *, began, level=None):
        job, samples = load_job(job_path)
        mono = samples.mean(axis=1)
        target = mono * 0.75 if level is None else np.full(len(mono), level, dtype=np.float32)
        residual = mono * 0.25
        with new_directory(destination) as temporary:
            pairs = {name: {**save_pair(temporary, name, target, residual, mono, padding_limit=0),
                             'description': description, 'elapsed_seconds': 0.01,
                             'peak_cuda_allocated_bytes':0, 'peak_cuda_reserved_bytes':0}
                     for name, description in job['targets'].items()}
            report = {k:copy.deepcopy(job[k]) for k in ('source','model','settings','seed','semantics',
                                                         'channel_reduction','anchors','start_sample','sample_count')}
            report['model']['files_sha256'] = {k:'b'*64 for k in ('config.json','checkpoint.pt','LICENSE')}
            report.update(schema_version=1,kind='harmonic.sam-audio-result.v1',job_sha256=digest(job_path),
                          sample_rate=48000,channels=1,codec_hop_samples=1920,
                          auxiliary_text_model={'id':'google-t5/t5-base','revision':TEXT_REVISION},
                          normalized_config_sha256='c'*64,worker_code_sha256=digest(WORKER),
                          worker_lock_sha256=digest(WORKER.with_name('uv.lock')),pairs=pairs,
                          elapsed_seconds=0.01,peak_host_rss_bytes=0,runtime={'simulated':True})
            report['run_binding_sha256'] = session['run_binding_sha256']
            write_json(temporary/'report.json',report)
        return destination/'report.json'

    def run_fake(self, separate=None, *, runtime=None):
        with patch.object(worker,'ready_state',return_value=runtime or {'simulated':True}), \
             patch.object(worker,'model_session',side_effect=self.fake_session), \
             patch.object(worker,'separate_job',side_effect=separate or self.fake_separate):
            return worker.run_song(self.plan_path,self.results)

    def test_coordinates_pcm_identity_and_unity_gain_for_short_and_uneven_tails(self):
        self.assertEqual(coordinates(2000,2000,400),[(0,2000)])
        self.assertEqual(coordinates(2001,2000,400),[(0,2000),(1600,401)])
        self.assertEqual(coordinates(100,2000,400),[(0,100)])
        for overlap in (0,-1,1000,1500):
            with self.assertRaises(ValueError): coordinates(7001,2000,overlap)
        total=np.zeros(len(self.samples))
        for i,e in enumerate(self.plan['chunks']):
            a,n=e['start_sample'],e['sample_count']
            total[a:a+n]+=weights(n,400,i==0,i==len(self.plan['chunks'])-1)
        np.testing.assert_allclose(total,1,rtol=0,atol=1e-15)
        self.run_fake()
        merged=stitch_song(self.plan_path,self.results,self.root/'merged')
        report=validate_song_result(self.plan_path,merged)
        np.testing.assert_allclose(read_wave(merged.parent/'vocals-target.wav'),self.samples.mean(axis=1)*.75,
                                   rtol=0,atol=3e-8)
        self.assertEqual(report['sample_count'],7001)
        self.assertEqual(report['pairs']['vocals']['target']['right_trim_samples'],0)
        self.assertEqual(len(validate_song_metadata(report)),len(self.plan['chunks']))
        # Merged output remains verifiable after individual chunk WAVs are discarded.
        shutil.rmtree(self.results)
        validate_song_result(self.plan_path,merged)

    def test_plan_validation_streams_pcm_and_checks_overlaps_and_full_hash(self):
        allocate = np.empty

        def bounded_allocation(shape, *args, **kwargs):
            self.assertNotEqual(shape,self.samples.shape,'validator allocated full-song PCM')
            return allocate(shape,*args,**kwargs)

        with patch.object(sam_chunks.np,'empty',side_effect=bounded_allocation):
            self.assertEqual(validate_plan(self.plan_path),self.plan)
        np.testing.assert_array_equal(load_plan(self.plan_path)[1],self.samples)

        job_path = self.plan_path.parent / self.plan['chunks'][1]['job']
        job, pcm = load_job(job_path)
        for position, problem in ((0,'overlapping source PCM'),(400,'full-song PCM checksum')):
            with self.subTest(problem=problem):
                changed = pcm.copy()
                changed[position,0] += 0.125
                wav_input = job_path.with_name('input.npy')
                np.save(wav_input,changed)
                job['input']['sha256'] = digest(wav_input)
                write_json(job_path,job)
                self.plan['chunks'][1]['sha256'] = digest(job_path)
                write_json(self.plan_path,self.plan)
                with self.assertRaisesRegex(ValueError,problem):
                    validate_plan(self.plan_path)

    def test_single_model_session_and_validated_resume_after_interruption(self):
        calls=0
        def interrupted(*args,**kwargs):
            nonlocal calls
            calls+=1
            if calls==3: raise RuntimeError('simulated interruption')
            return self.fake_separate(*args,**kwargs)
        with self.assertRaisesRegex(RuntimeError,'interruption'): self.run_fake(interrupted)
        self.assertFalse((self.results/'completed.json').exists())
        self.assertEqual(self.session_loads,1)
        path=self.run_fake()
        done=json.loads(path.read_text())
        self.assertEqual(done['reused_chunks'],2)
        self.assertEqual(self.session_loads,2)
        timing=done['timing_seconds']
        self.assertGreater(timing['model_setup'],0)
        self.assertGreater(timing['process_pending_chunks'],0)
        self.assertAlmostEqual(done['elapsed_seconds_through_validation'],sum(timing.values()))
        self.assertAlmostEqual(done['elapsed_seconds_this_invocation'],
                               timing['model_setup']+timing['process_pending_chunks']+timing['final_validation'])
        self.run_fake()
        self.assertEqual(self.session_loads,2)  # All results reused; do not load a model at all.
        history=json.loads(path.read_text())['invocations']
        self.assertEqual(len(history),2)
        self.assertEqual(history[0],done['invocations'][0])
        self.assertEqual(history[-1]['new_chunks'],0)
        cached=history[-1]['timing_seconds']
        self.assertEqual(cached['model_setup'],0)
        self.assertEqual(cached['process_pending_chunks'],0)
        self.assertGreater(cached['output_setup_reuse_scan_and_cleanup'],0)
        self.assertGreater(cached['final_validation'],0)
        self.assertAlmostEqual(history[-1]['elapsed_seconds_through_validation'],sum(cached.values()))
        wave_path=self.results/'chunks/000000/vocals-target.wav'
        wave_path.write_bytes(wave_path.read_bytes()+b'corrupt')
        with self.assertRaisesRegex(ValueError,'checksum'): self.run_fake()
        self.assertEqual(self.session_loads,2)

    def test_resume_rejects_changed_runtime_imported_code_and_chunk_binding(self):
        complete = json.loads(self.run_fake().read_text())
        with self.assertRaisesRegex(ValueError,'different plan/worker/runtime'):
            self.run_fake(runtime={'python':'3.11.99'})
        edited = self.root/'sam_jobs.py'
        edited.write_bytes(Path(sam_jobs.__file__).read_bytes()+b'\n# Change the imported source fingerprint.\n')
        with patch.object(sam_jobs,'__file__',str(edited)):
            with self.assertRaisesRegex(ValueError,'different plan/worker/runtime'):
                self.run_fake()
        chunk = self.results/'chunks/000000/report.json'
        report = json.loads(chunk.read_text())
        self.assertEqual(report['run_binding_sha256'],complete['run_binding_sha256'])
        report['run_binding_sha256'] = 'a'*64
        write_json(chunk,report)
        with self.assertRaisesRegex(ValueError,'incompatible provenance'):
            self.run_fake()
        self.assertEqual(self.session_loads,1)

    def test_song_output_lock_blocks_other_process_and_releases_after_kill(self):
        script = """
import runpy
import sys
from pathlib import Path

lock = runpy.run_path(sys.argv[1])["song_output_lock"]
with lock(Path(sys.argv[2])):
    print("locked", flush=True)
    sys.stdin.read()
"""
        alias = self.root / 'alias'
        alias.symlink_to(self.results.parent, target_is_directory=True)
        with subprocess.Popen([sys.executable,'-c',script,str(WORKER),str(self.results)],
                              stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE) as owner:
            try:
                self.assertTrue(select.select([owner.stdout],[],[],10)[0], 'Lock holder timed out')
                self.assertEqual(owner.stdout.readline(), b'locked\n')
                with patch.object(worker,'ready_state') as preflight:
                    with self.assertRaisesRegex(ValueError,'Another SAM worker'):
                        worker.run_song(self.plan_path,alias/self.results.name)
                    preflight.assert_not_called()
                self.assertFalse(self.results.exists())
            finally:
                owner.kill()
                owner.communicate(timeout=10)
        done = json.loads(self.run_fake().read_text())
        self.assertEqual(done['new_chunks'],len(self.plan['chunks']))
        self.assertEqual(json.loads(self.run_fake().read_text())['new_chunks'],0)

    def test_resume_cleans_only_known_scratch_and_keeps_published_chunks(self):
        def interrupted(job, destination, session, *, began):
            if destination.name == '000001':
                scratch = Path(tempfile.mkdtemp(prefix='.000001-', dir=destination.parent))
                (scratch/'vocals-target.wav').write_bytes(b'partial waveform')
                raise RuntimeError('simulated abrupt exit without staging cleanup')
            return self.fake_separate(job,destination,session,began=began)

        with self.assertRaisesRegex(RuntimeError,'abrupt exit'):
            self.run_fake(interrupted)
        chunk_dir = self.results/'chunks'
        abandoned, = chunk_dir.glob('.000001-*')
        first_wave = chunk_dir/'000000/vocals-target.wav'
        first_hash = digest(first_wave)
        completion_scratch = self.results/'.completed.json.tmp'
        completion_scratch.write_text('{"incomplete":')
        unknown = chunk_dir/'.000001-abcd1234'
        unknown.mkdir()
        (unknown/'notes.txt').write_text('keep')
        outside = self.root/'outside'
        outside.mkdir()
        external_file = outside/'vocals-target.wav'
        external_file.write_text('keep')
        link = chunk_dir/'.000002-abcd1234'
        link.symlink_to(outside, target_is_directory=True)

        binding = self.results/'run.json'
        original = binding.read_text()
        binding.write_text('{}')
        with self.assertRaisesRegex(ValueError,'different plan/worker'):
            self.run_fake()
        self.assertTrue(abandoned.is_dir())
        self.assertTrue(completion_scratch.is_file())
        binding.write_text(original)

        summary = json.loads(self.run_fake().read_text())
        self.assertEqual(summary['reused_chunks'],1)
        self.assertEqual(digest(first_wave),first_hash)
        self.assertFalse(abandoned.exists())
        self.assertFalse(completion_scratch.exists())
        self.assertEqual((unknown/'notes.txt').read_text(),'keep')
        self.assertTrue(link.is_symlink())
        self.assertEqual(external_file.read_text(),'keep')

    def test_crossfade_smooths_known_level_disagreement_without_normalization(self):
        def stepped(job,destination,session,**kwargs):
            index=int(destination.name)
            return self.fake_separate(job,destination,session,level=float(index+1),**kwargs)
        self.run_fake(stepped)
        path=stitch_song(self.plan_path,self.results,self.root/'merged')
        report=validate_song_result(self.plan_path,path)
        target=read_wave(path.parent/'vocals-target.wav')
        self.assertEqual(target[0],1)
        self.assertEqual(target[-1],len(self.plan['chunks']))
        for boundary in report['boundaries']:
            if boundary['role']=='target':
                self.assertEqual(boundary['midpoint_hard_splice_step'],1)
                self.assertLess(boundary['blended_midpoint_step'],0.01)
        self.assertIsNone(overlap_metrics(np.zeros(400),np.zeros(400))['cross_correlation_peak_lag_samples'])
        self.assertGreater(report['pairs']['vocals']['target']['peak'],1)

    def test_corrupt_plans_auxiliary_mismatch_and_retained_provenance_are_rejected(self):
        changed=copy.deepcopy(self.plan)
        changed['chunks'][1]['start_sample']+=1
        write_json(self.plan_path,changed)
        with self.assertRaisesRegex(ValueError,'coordinates'): load_plan(self.plan_path)
        write_json(self.plan_path,self.plan)
        self.run_fake()
        child=self.results/'chunks/000001/report.json'
        original=child.read_text()
        report=json.loads(original)
        report['auxiliary_text_model']['revision']='e'*40
        write_json(child,report)
        with self.assertRaisesRegex(ValueError,'different models'): stitch_song(self.plan_path,self.results,self.root/'bad')
        self.assertFalse((self.root/'bad').exists())
        child.write_text(original)
        merged=stitch_song(self.plan_path,self.results,self.root/'merged')
        report=json.loads(merged.read_text())
        report['chunking']['chunks'][0]['report_json']+='\n'
        write_json(merged,report)
        with self.assertRaisesRegex(ValueError,'checksum'): validate_song_result(self.plan_path,merged)

    @unittest.skipUnless(shutil.which('ffmpeg') and PLAYER.is_file(),'Build the native player and install FFmpeg')
    def test_full_song_feature_bundle_native_reading_and_no_internal_window_padding(self):
        audio=self.root/'source.wav'
        signal=(np.sin(np.arange(96000)*2*np.pi*220/48000)*12000).astype('<i2')
        with wave.open(str(audio),'wb') as handle:
            handle.setnchannels(2);handle.setsampwidth(2);handle.setframerate(48000)
            handle.writeframes(np.column_stack([signal,signal]).tobytes())
        mix=analyze(audio,self.root/'mix')
        manifest=json.loads(mix.read_text())
        full=decode_audio(audio)
        self.plan_path=make_plan(full,{**manifest['source'],'sample_count':len(full)},self.root/'full-plan',
                                 chunk=24000,overlap=4800,targets={'vocals':'man singing'})
        self.plan,_=load_plan(self.plan_path)
        self.run_fake()
        merged=stitch_song(self.plan_path,self.results,self.root/'merged')
        bundle=build_source_bundle(mix,self.plan_path,merged,self.root/'features')
        read_bundle(bundle,digest(audio))
        renamed=self.plan_path.with_name('my-session.json')
        self.plan_path.rename(renamed)
        other=self.root/'renamed-features'
        result=subprocess.run([sys.executable,'-m','harmonic_analysis.sam_cli','features',
                               str(mix),str(renamed),str(merged),'--output',str(other)],
                              capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(digest(other/'sam-vocals-target.arrow'),digest(bundle.parent/'sam-vocals-target.arrow'))
        inspect=subprocess.run([str(PLAYER),str(bundle),'--inspect','--start','0.5'],capture_output=True,text=True,timeout=20)
        self.assertEqual(inspect.returncode,0,inspect.stderr)
        data=json.loads(next(line for line in inspect.stdout.splitlines() if line.startswith('{')))
        expected=np.sqrt(np.mean((full[24000-2048:24000+2048].mean(axis=1).astype(np.float64)*.75)**2))
        self.assertAlmostEqual(data['source_features'][0]['rms'],expected,places=7)

        retained=bundle.parent/'sam-report.json'
        original_report=json.loads(retained.read_text())
        original_bundle=json.loads(bundle.read_text())
        for fault in ('missing index', 'invalid job hash', 'different run binding', 'missing trim', 'negative peak'):
            with self.subTest(fault=fault):
                report=copy.deepcopy(original_report)
                item=report['chunking']['chunks'][0]
                if fault == 'missing index':
                    del item['index']
                else:
                    child=json.loads(item['report_json'])
                    if fault == 'invalid job hash':
                        child['job_sha256']=item['job_sha256']='invalid'
                    elif fault == 'different run binding':
                        child['run_binding_sha256']='a'*64
                    else:
                        wav = child['pairs']['vocals']['target']
                        if fault == 'missing trim':
                            del wav['right_trim_samples']
                        else:
                            wav['peak'] = -1
                    item['report_json']=json.dumps(child)
                    item['report_sha256']=hashlib.sha256(item['report_json'].encode()).hexdigest()
                write_json(retained,report)
                original_bundle['separation']['sha256']=digest(retained)
                write_json(bundle,original_bundle)
                with self.assertRaisesRegex(ValueError,'retained chunk|chunk report'):
                    read_bundle(bundle,digest(audio))
                rejected=subprocess.run([str(PLAYER),str(bundle),'--inspect'],capture_output=True,text=True,timeout=20)
                self.assertNotEqual(rejected.returncode,0)
                self.assertIn('retained chunk',rejected.stderr)
