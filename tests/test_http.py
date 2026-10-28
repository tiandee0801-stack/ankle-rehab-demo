import json, os, socket, subprocess, sys, tempfile, time, unittest
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
ROOT=Path(__file__).resolve().parents[1]
class HttpTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory()
  with socket.socket() as sock:
   sock.bind(('127.0.0.1',0)); cls.port=sock.getsockname()[1]
  cls.url='http://127.0.0.1:'+str(cls.port)
  cls.log=open(Path(cls.tmp.name)/'server.log','w')
  cls.process=subprocess.Popen([sys.executable,str(ROOT/'server.py'),'--port',str(cls.port)],env={**os.environ,'ANKLE_DATA_DIR':cls.tmp.name},stdout=cls.log,stderr=cls.log)
  for _ in range(80):
   try:
    with urlopen(cls.url+'/api/health',timeout=1) as r:
     if json.load(r)['ok']: return
   except Exception: time.sleep(.05)
  raise RuntimeError('test server did not start')
 @classmethod
 def tearDownClass(cls):
  cls.process.terminate();cls.process.wait(timeout=10);cls.log.close();cls.tmp.cleanup()
 def req(self,path,body=None,headers=None,raw=None):
  data=raw if raw is not None else json.dumps(body).encode() if body is not None else None
  request=Request(self.url+path,data=data,headers={'Content-Type':'application/json',**(headers or {})})
  try:
   with urlopen(request,timeout=10) as response:return response.status,response.read(),dict(response.headers)
  except HTTPError as response:return response.code,response.read(),dict(response.headers)
 def test_health(self):
  status,data,_=self.req('/api/health');self.assertEqual(status,200);self.assertEqual(json.loads(data)['service'],'dee-ankle-rehab')
 def test_foreign_origin_cannot_mutate(self):
  status,_,_=self.req('/api/demo-analysis',{'recordId':'demo-record','side':'left'},{'Origin':'https://example.com'})
  self.assertEqual(status,403)
 def test_host_rebinding_rejected(self):
  status,_,_=self.req('/api/state',headers={'Host':'example.com'});self.assertEqual(status,403)
 def test_cross_side_rejected(self):
  status,_,_=self.req('/api/demo-analysis',{'recordId':'demo-record','side':'right'});self.assertEqual(status,400)
 def test_state_and_export_consistent(self):
  status,data,_=self.req('/api/state');state=json.loads(data)
  self.assertTrue(state['profiles'][0]['isDemo'])
  status,data,headers=self.req('/api/export?profileId=demo-profile')
  self.assertEqual(status,200);self.assertIn('attachment',headers['Content-Disposition'])
  self.assertEqual(json.loads(data)['profile']['id'],'demo-profile')
 def test_invalid_input_rejected_without_nan(self):
  status,_,_=self.req('/api/records',{'profileId':'demo-profile','date':'invalid','side':'left'});self.assertEqual(status,400)
 def test_unknown_and_traversal_not_served(self):
  self.assertEqual(self.req('/api/missing')[0],404)
  self.assertEqual(self.req('/%2e%2e/server.py')[0],404)
  self.assertEqual(self.req('/media/../ankle.sqlite3')[0],404)
 def test_simulation_label_persists(self):
  status,data,_=self.req('/api/demo-analysis',{'recordId':'demo-record','side':'left'});self.assertEqual(status,201)
  result=json.loads(data);self.assertEqual(result['mode'],'simulated_keypoints')
  status,data,_=self.req('/api/analyses/'+result['id']);self.assertEqual(json.loads(data)['result']['repCount'],5)
 def test_missing_next_day_pass_is_error(self):
  status,_,_=self.req('/api/reviews',{'profileId':'demo-profile','recordId':'demo-record','scope':'stage','decision':'PASS','comment':'test'})
  self.assertEqual(status,400)
if __name__=='__main__':unittest.main()
