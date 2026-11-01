"""Integration checks against real classifier and isolated SQLite database."""
import re, tempfile, unittest
from pathlib import Path
from app import create_app, ROOT
class WebsiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.path=Path(self.tmp.name)/'reviews.db'; self.app=create_app(self.path); self.client=self.app.test_client(); self.client.get('/')
    def tearDown(self): self.tmp.cleanup()
    def csrf(self):
        with self.client.session_transaction() as s: return s['csrf']
    def test_browsing_search(self):
        for path in ['/','/?department=Tops','/?category=Dresses','/items/1077','/static/dress.svg','/static/top.svg','/static/bottom.svg']:
            with self.client.get(path) as response:
                self.assertEqual(response.status_code,200,path)
        def ids(q): return re.findall(rb'/items/(\d+)"',self.client.get('/?q='+q).data)
        self.assertEqual(ids('dress'),ids('dresses')); self.assertTrue(ids('dress'))
        self.assertIn(b'0</strong> matching',self.client.get('/?q=zzzzimpossible').data)
        self.assertEqual(self.client.get('/items/999999').status_code,404)
    def test_review_override_and_persistence(self):
        r=self.client.post('/items/1077/review',data={'csrf':self.csrf(),'title':'Integration test','body':'Beautiful dress, comfortable fabric and a perfect fit. I love it.','rating':'5'})
        self.assertEqual(r.status_code,302)
        preview=self.client.get(r.location); self.assertIn(b'MODEL SUGGESTION',preview.data)
        with self.client.session_transaction() as s: token=s['draft_token']
        import json
        draft=json.loads((ROOT/'data/drafts'/f'{token}.json').read_text()); override=1-draft['predicted']
        published=self.client.post(r.location,data={'csrf':self.csrf(),'recommended':str(override)})
        self.assertEqual(published.status_code,302); url=published.location
        self.assertIn(b'buyer overrode',self.client.get(url).data)
        self.assertIn(b'Integration test',self.client.get('/items/1077').data)
        restarted=create_app(self.path).test_client()
        self.assertIn(b'Integration test',restarted.get(url).data)
        self.assertIn(('Recommended (1)' if override else 'Not recommended (0)').encode(),restarted.get(url).data)
    def test_validation_and_escape(self):
        self.assertEqual(self.client.post('/items/1077/review',data={}).status_code,400)
        r=self.client.post('/items/1077/review',data={'csrf':self.csrf(),'title':'','body':'tiny','rating':'9'})
        self.assertIn(b'Enter a title',r.data)
        self.assertNotIn(b'<script>alert(1)</script>',self.client.get('/?q=<script>alert(1)</script>').data)
if __name__=='__main__': unittest.main(verbosity=2)
