import hashlib
import json
from pathlib import Path
import tempfile
from unittest.mock import Mock
import unittest
from saint_bait.updates import UpdateService,validate_repository,version_tuple


class UpdateTests(unittest.TestCase):
    def test_versions_are_numeric_and_repository_is_bounded(self):
        self.assertGreater(version_tuple('1.10.0'),version_tuple('1.9.0'))
        self.assertEqual(validate_repository('https://github.com/l2gorynych/saint-bait'),'l2gorynych/saint-bait')
        for value in ('../file','https://evil.example/a/b','owner/repo/releases'):
            with self.assertRaises(ValueError):validate_repository(value)

    def responses(self,checksum=None):
        content=b'MZ'+b'x'*1_000_000
        root='https://github.com/l2gorynych/saint-bait/releases/download/v2.0.0/'
        def response(url,payload):
            value=Mock(url=url);value.json.return_value=payload
            return value
        release=response('https://api.github.com/repos/l2gorynych/saint-bait/releases/latest',
            {'tag_name':'v2.0.0','assets':[{'name':'update.json','size':200,'browser_download_url':root+'update.json'},
             {'name':'Saint Bait.exe','size':len(content),'browser_download_url':root+'Saint%20Bait.exe'}]})
        manifest=response(root+'update.json',{'version':'2.0.0','file':'Saint Bait.exe',
            'size':len(content),'sha256':checksum or hashlib.sha256(content).hexdigest()})
        binary=response(root+'Saint%20Bait.exe',None);binary.iter_content.return_value=[content]
        return [release,manifest,binary]

    def test_new_binary_is_staged_only_after_size_and_hash_verification(self):
        with tempfile.TemporaryDirectory() as folder:
            http=Mock();http.get.side_effect=self.responses()
            updater=UpdateService(folder,http);updater._check('l2gorynych/saint-bait')
            self.assertEqual(updater.staged['version'],'2.0.0')
            self.assertTrue(Path(updater.staged['source']).exists())
            self.assertFalse((Path(folder)/'Saint Bait.exe').exists())

    def test_bad_hash_never_becomes_an_installable_update(self):
        with tempfile.TemporaryDirectory() as folder:
            http=Mock();http.get.side_effect=self.responses('0'*64)
            updater=UpdateService(folder,http);updater._check('l2gorynych/saint-bait')
            self.assertIsNone(updater.staged)
            self.assertEqual(list(Path(folder).glob('updates/*.exe')),[])
