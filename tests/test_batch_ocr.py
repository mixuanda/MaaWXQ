"""One process, source/ROI binding and candidate preservation, all OCR mocked."""
import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from runtime.batch_ocr import read_regions
from runtime.minimal_state import extract


class BatchOcrTests(unittest.TestCase):
    def fixture(self,command,**kwargs):
        profile_path=Path(command[command.index('-Profile')+1])
        profile=json.loads(profile_path.read_text(encoding='utf-8'))
        result={'schema_version':'strategy-region-ocr/1','image_sha256':self.frame['sha256'],
                'profile_sha256':hashlib.sha256(profile_path.read_bytes()).hexdigest(),'width':1450,'height':869,
                'elapsed_ms':100,'cache_hits':0,'regions':[{'name':row['name'],'bounds':row['bounds'],'scale':3,
                    'pixel_sha256':'b'*64,'text':'第4回合45s'if row['name']=='round'else'28','cache_hit':False}for row in profile['regions']]}
        if self.corrupt=='hash':result['image_sha256']='c'*64
        elif self.corrupt=='roi':result['regions'][0]['bounds']=[0,0,1,1]
        elif self.corrupt=='duplicate':result['regions'][1]=result['regions'][0]
        elif self.corrupt=='profile':result['profile_sha256']='c'*64
        Path(command[command.index('-Output')+1]).write_text(json.dumps(result),encoding='utf-8')
        return Mock(returncode=0)

    def test_two_dynamic_regions_use_one_process_no_png_and_keep_uncalibrated_values(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);image=root/'fixture.bin';image.write_bytes(b'synthetic-fixture')
            self.frame={'image':str(image),'sha256':hashlib.sha256(image.read_bytes()).hexdigest(),
                        'captured_at':'2026-01-01T00:00:00Z','identity':{'identity_version':'fixture'}}
            self.corrupt=None
            with patch('runtime.batch_ocr.subprocess.run',side_effect=self.fixture)as process:
                bundles,result=read_regions(self.frame,root/'ocr')
            self.assertEqual(process.call_count,1);self.assertEqual(set(bundles),{'round','energy'})
            self.assertEqual(list(root.rglob('*.png')),[])
            state={'scene':'battle_controls','match_started':True,'frame_sha256':self.frame['sha256']}
            minimal=extract(self.frame,state,bundles,now='2026-01-01T00:00:01Z')
            self.assertEqual(minimal['round']['candidate'],4)
            self.assertEqual(minimal['resources']['energy']['candidate'],28)
            self.assertIsNone(minimal['resources']['energy']['value']);self.assertIsNone(minimal['resources']['energy']['confidence'])
            self.assertEqual(minimal['resources']['energy']['roi_pixel_sha256'],'b'*64)
            self.assertIsNone(minimal['resources']['energy']['roi_image_sha256'])

    def test_changed_source_profile_roi_or_duplicate_cannot_become_candidate_evidence(self):
        for corrupt in ('hash','roi','duplicate','profile'):
            with self.subTest(corrupt=corrupt),tempfile.TemporaryDirectory()as directory:
                root=Path(directory);image=root/'fixture.bin';image.write_bytes(b'synthetic-fixture')
                self.frame={'image':str(image),'sha256':hashlib.sha256(image.read_bytes()).hexdigest()};self.corrupt=corrupt
                with patch('runtime.batch_ocr.subprocess.run',side_effect=self.fixture),self.assertRaises(ValueError):
                    read_regions(self.frame,root/'ocr')


if __name__=='__main__':unittest.main()
