from pathlib import Path
import tempfile
from unittest.mock import Mock
import unittest
from saint_bait.community import SupabaseClient,validate_service_url
from saint_bait.telemetry.location import parse_coordinates


class CommunityTests(unittest.TestCase):
    def test_real_minimap_coordinates_and_bad_labels(self):
        self.assertEqual(parse_coordinates('71 : 87'),(71,87))
        self.assertEqual(parse_coordinates(' -2:30 '),(-2,30))
        for value in (None,'loading','71/87','x71:87'):self.assertIsNone(parse_coordinates(value))

    def test_connection_rejects_embedded_credentials_and_unencrypted_remote(self):
        for value in ('http://example.com','https://user:pass@example.com','https://example.com/token?a=1'):
            with self.assertRaises(ValueError):validate_service_url(value)
        self.assertEqual(validate_service_url('https://example.supabase.co/'),'https://example.supabase.co')

    def test_secret_keys_are_not_accepted_as_public_project_keys(self):
        with self.assertRaises(ValueError):SupabaseClient('https://example.supabase.co','sb_secret_test','unused.json')

    def test_upload_is_authenticated_and_idempotent_and_nearby_is_server_filtered(self):
        with tempfile.TemporaryDirectory() as folder:
            http=Mock()
            auth=Mock();auth.json.return_value={'access_token':'access','refresh_token':'refresh',
                'expires_at':9999999999,'user':{'id':'account-id'}}
            result=Mock();result.json.return_value=[]
            http.request.side_effect=[auth,result,result]
            client=SupabaseClient('https://example.supabase.co','publishable',Path(folder)/'session.json',http)
            client.upload([{'id':'catch-id','clip_m':8}])
            upload=http.request.call_args_list[1]
            self.assertEqual(upload.kwargs['json'][0]['contributor_id'],'account-id')
            self.assertIn('ignore-duplicates',upload.kwargs['headers']['Prefer'])
            self.assertEqual(upload.kwargs['headers']['Authorization'],'Bearer access')
            client.nearby('lake',71,87)
            self.assertEqual(http.request.call_args.kwargs['json'],
                             {'p_waterbody':'lake','p_x':71,'p_y':87,'p_radius':3,'p_limit':100})
